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
