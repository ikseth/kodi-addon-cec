# kodi-addon-cec

Addon de Kodi que expone las acciones **CEC** del propio Kodi para que se puedan
invocar desde fuera por JSON-RPC. Pensado para domotica.

## El problema que resuelve

Un televisor conectado por red se controla bien... hasta que pierde la red. A
partir de ahi el sistema domotico no sabe si esta encendido ni puede apagarlo,
y un televisor puede quedarse toda la noche encendido sin que nadie se entere.

**CEC viaja por el cable HDMI**, asi que no depende de la red del televisor. Si
hay un Kodi enchufado a ese HDMI, ese Kodi puede apagar el televisor aunque el
televisor este incomunicado.

## Por que un addon y no un script por SSH

Porque el camino directo no funciona. libCEC va **compilado dentro de Kodi**, que
mantiene el adaptador CEC abierto en modo exclusivo. Cualquier proceso externo
que intente abrirlo recibe `EBUSY`:

```
ioctl CEC_S_MODE failed - errno=16
unable to open the device on port Linux
```

Se comprobo en LibreELEC y en Recalbox. En Recalbox, con dos adaptadores CEC,
`kodi.bin` los tenia tomados los dos.

Pidiendoselo a Kodi el conflicto desaparece, y ademas:

- no hace falta acceso por SSH al reproductor, ni distribuir claves;
- se reutiliza la conexion JSON-RPC que el sistema domotico ya tiene configurada;
- se usa exactamente el mismo camino CEC que usa Kodi para su propio mando.

## Acciones

| Accion | Builtin de Kodi | Efecto |
|---|---|---|
| `standby` | `CECStandby` | Apaga el televisor |
| `activate` | `CECActivateSource` | Lo enciende y lo cambia a la entrada HDMI de este equipo |
| `toggle` | `CECToggleState` | Alterna |

Cada una se habilita o veta por separado en los ajustes del addon. `toggle` viene
**desactivada por defecto**: su resultado depende de un estado que quien llama no
ve, asi que es facil usarla por error.

## Estado del televisor (desde 0.2.0)

Un servicio del addon pregunta al televisor por CEC si esta encendido y publica
la respuesta como propiedades de `Window(Home)`. Asi un sistema domotico conoce el
estado **real**, aunque el televisor haya perdido la red.

Se leen desde fuera por JSON-RPC:

```json
{"jsonrpc": "2.0", "id": 1, "method": "XBMC.GetInfoLabels",
 "params": {"labels": ["Window(Home).Property(cec.tv_power)",
                       "Window(Home).Property(cec.tv_power_ts)"]}}
```

| Propiedad | Contenido |
|---|---|
| `cec.protocol` | Version del contrato. Un cambio incompatible la sube |
| `cec.tv_power` | `on`, `standby` o `unknown` |
| `cec.tv_power_ts` | Hora (epoch, s) de la ultima consulta |
| `cec.error` | Vacio si hubo respuesta; si no, el motivo (`nack`, `no_reply`, `EBUSY`...) |
| `cec.device` | Adaptador consultado |
| `cec.poll_interval` | Segundos entre consultas |

Reglas para quien consuma el estado:

- **`unknown` no significa apagado.** Un televisor desenchufado de la corriente no
  contesta (`nack`); no se puede afirmar nada de el.
- **Una propiedad vacia o antigua es estado desconocido.** Las propiedades viven en
  memoria de Kodi: desaparecen al reiniciarlo o si se desactiva la publicacion.
  Se considera antigua si `cec.tv_power_ts` supera en varias veces
  `cec.poll_interval`.
- Tras `standby` o `activate` el servicio relee el estado cada 3 s hasta ver el
  cambio, con un maximo de 60 s.
- **Durante una transicion el televisor puede no contestar** y publicarse `unknown`
  (medido: tras un `standby`, `unknown` a los 2 s y `standby` a los 5 s; tras un
  encendido, `unknown` durante mas de 30 s).
  Un consumidor no deberia marcar el televisor como no disponible por una sola
  lectura `unknown`: conviene mantener el ultimo estado conocido un margen breve.

La consulta abre el adaptador en modo **no exclusivo**, compatible con el CEC de
Kodi: ver `docs/DESIGN.md`.

## Uso

Desde Home Assistant:

```yaml
action: kodi.call_method
target:
  entity_id: media_player.my_kodi
data:
  method: Addons.ExecuteAddon
  addonid: script.cec.control
  params:
    action: standby
```

Desde el propio Kodi:

```
RunScript(script.cec.control, action=standby)
```

## Instalacion

```bash
./build_zip.sh addon/script.cec.control
```

y se instala el ZIP resultante de `dist/` desde Kodi, con
**Add-ons -> Instalar desde archivo ZIP**.

## Requisitos

- Kodi 19 o superior (probado en Kodi 21 Omega).
- Un equipo con CEC funcionando: el televisor debe tener CEC activado, que cada
  fabricante bautiza a su manera (Anynet+, Bravia Sync, EasyLink, Simplink...).

## Tests

```bash
python3 -m pytest tests/ -q
```

La capa de decision (`resources/lib/cec.py`) no importa `xbmc`, justamente para
poder probarla sin Kodi.
