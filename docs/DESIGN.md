# Diseno y hallazgos

## Reparto de responsabilidades

```
Sistema domotico  --JSON-RPC-->  Kodi  --builtin-->  libCEC (dentro de Kodi)  --HDMI-->  TV
                  Addons.ExecuteAddon      CECStandby
```

El addon es una pieza fina a proposito: valida la accion, comprueba su ajuste y
delega. Toda la complejidad de CEC ya esta resuelta dentro de Kodi.

## Por que no se transmite CEC directamente

Es el hallazgo que determina el diseno, y se midio antes de escribir codigo.

`cec-client` (libCEC) falla en cuanto Kodi esta arrancado:

```
opening a connection to the CEC adapter...
ERROR: CLinuxCECAdapterCommunication::Open - ioctl CEC_S_MODE failed - errno=16
unable to open the device on port Linux
```

`errno=16` es `EBUSY`. libCEC pide modo **iniciador exclusivo**, y Kodi ya lo
tiene. Comprobado en LibreELEC y en Recalbox; en Recalbox, `kodi.bin` mantenia
abiertos los dos adaptadores del equipo.

Conclusion: para **actuar**, pedirselo a Kodi es la unica via limpia. No es un
rodeo, es lo correcto: se usa el mismo camino que Kodi usa para su propio mando.

## Camino validado para *leer* el estado del televisor

Actuar se delega en Kodi, pero **leer** el estado no se puede: Kodi no expone por
JSON-RPC ni por su API de Python el estado de encendido del televisor.

Existe una via que **si** convive con Kodi, y esta verificada. El API CEC del
kernel (`/dev/cecN`) distingue dos modos de iniciador: el **exclusivo** que pide
libCEC, y el **normal**, que el kernel concede en paralelo. Abriendo el
dispositivo con `CEC_MODE_INITIATOR` (`0x1`) en vez de `CEC_MODE_EXCL_INITIATOR`
se puede transmitir sin desalojar a Kodi, reutilizando la direccion logica que
Kodi ya tiene registrada en el bus.

Verificado con `cec-ctl -d /dev/cec0 --to 0 --give-device-power-status` y con una
implementacion propia de ~40 lineas sobre `fcntl.ioctl`. Ambas dan el mismo
resultado, y funcionan tambien en el equipo que no trae `cec-ctl`:

| Mensaje | Respuesta |
|---|---|
| `GIVE_DEVICE_POWER_STATUS` (0x8f) | `REPORT_POWER_STATUS` (0x90) con `pwr-state` |
| `0x01` | standby |
| `0x00` | encendido |

Tiempo de respuesta medido: **20 ms**.

Detalles que costaron una iteracion, por si se retoma:

- `CEC_TRANSMIT` es `_IOWR('a', 5, struct cec_msg)`, y `struct cec_msg` ocupa
  **56 bytes**. El buffer del mensaje (`msg[16]`) empieza en el **offset 32**, no
  en el 36: leerlo mal devuelve ceros, que se interpretan como "encendido".
- El primer byte del mensaje es `(direccion_origen << 4) | direccion_destino`, y
  el televisor es siempre la direccion logica **0**.
- La direccion logica propia se lee con `CEC_ADAP_G_LOG_ADDRS`. En los equipos
  probados era la 1 (Recording Device 1), que es el valor por defecto de libCEC.

Esta via **no esta implementada en el addon**. Se documenta porque es lo que
habilitaria publicar el estado real del televisor como sensor, que es justo el
punto ciego que motivo el proyecto: un televisor encendido que el sistema
domotico da por apagado porque perdio la red.

## Verificacion desde dentro de Kodi (prototipo previo a 0.2.0)

Lo anterior se habia medido con el Python del sistema. Antes de construir el
servicio de lectura se comprobo lo mismo **desde el Python embebido de Kodi**
(3.11), con libCEC activo y un video en pausa en ese momento:

| Comprobacion | Resultado |
|---|---|
| Abrir `/dev/cec0` con `CEC_MODE_INITIATOR` desde el addon | correcto, sin `EBUSY` |
| `GIVE_DEVICE_POWER_STATUS` al televisor | `tx_status` 1, `rx_status` 1, respuesta `019000` (encendido) |
| Publicar `cec.tv_power`, `cec.tv_power_ts` y `cec.protocol` en `Window(Home)` | correcto |
| Leerlas desde fuera con `XBMC.GetInfoLabels` y `Window(Home).Property(...)` | correcto, lectura con 0 s de antiguedad |
| Efecto visible en el televisor o en la reproduccion | ninguno |

Con esto quedan validados los dos supuestos de la 0.2.0: el servicio puede leer el
estado sin desalojar a Kodi, y el sistema domotico puede recogerlo por el mismo
JSON-RPC que ya usa, sin puertos ni credenciales nuevas.

Queda por medir en uso real que una consulta periodica no interfiera con el mando
por CEC.

Nota: las propiedades de `Window(Home)` viven en memoria de Kodi y desaparecen al
reiniciarlo. El consumidor debe tratar una propiedad vacia o antigua como estado
desconocido, nunca como apagado.

## Medidas del servicio en uso real (0.2.0)

Instalado en un equipo Recalbox, con el televisor conectado por HDMI:

| Situacion | Resultado |
|---|---|
| Arranque del equipo | la primera consulta sale con la hora del sistema sin sincronizar (1980) y da `no_reply`: el HDMI aun no esta listo. Se corrige sola en la siguiente |
| Deteccion del adaptador (`auto`) | elige el correcto entre `/dev/cec0` y `/dev/cec1` |
| Consultas periodicas | cada 30-31 s |
| Encendido automatico del televisor al arrancar Kodi | detectado por el servicio 2 s despues de que lo viera el sistema domotico por red |
| `standby` enviado | `unknown` a los 2 s (en transicion no contesta), `standby` a los 5,8 s. La red lo reflejo a los 16,8 s |
| `activate` enviado | `unknown` durante mas de 30 s; `on` a los 41,9 s, en el ciclo normal. La red lo reflejo a los 34,2 s |

Dos correcciones que salieron de estas medidas, incluidas en 0.2.1:

1. **Reloj monotonico para planificar.** La hora de pared salta tras el arranque;
   con ella, un salto hacia atras dejaria el servicio sin consultar.
2. **Rafaga adaptativa tras una orden.** La rafaga fija (2, 5 y 10 s) servia para el
   apagado pero no para el encendido, porque el televisor tarda mas de 30 s en
   volver a contestar. Ahora se relee cada 3 s hasta ver un estado definitivo
   distinto del de partida, con 60 s de tope. No basta con parar en la primera
   respuesta definitiva: justo despues de un `standby` el televisor puede contestar
   todavia `on`.

Implicacion para quien consuma el estado: un `unknown` suelto durante una
transicion es normal y no debe tratarse como perdida de disponibilidad.

### Validacion de 0.2.1 en el mismo equipo

| Situacion | 0.2.0 | 0.2.1 | Por red |
|---|---|---|---|
| Arranque: primera consulta con la hora sin sincronizar | `no_reply`, marca de 1980 | igual, pero la siguiente consulta sale a los 30 s con la hora buena | - |
| `standby` enviado | `standby` a 5,8 s | `standby` a 6,4 s | 16,8 / 19,6 s |
| `activate` enviado | `on` a 41,9 s, en el ciclo normal | `on` a **22,7 s**, en rafaga (consultas cada ~3 s) | 34,2 / 32,2 s |

Con la rafaga adaptativa el encendido se publica antes de que el televisor vuelva
a la red.

Se publico sin el periodo de varios dias de uso normal previsto para descartar
interferencias de la consulta periodica con el mando por CEC: se considero que el
alcance del proyecto y los resultados medidos lo justificaban. Si apareciera esa
interferencia, se mitiga sin tocar codigo subiendo `poll_interval` o desactivando
la publicacion del estado en los ajustes.
