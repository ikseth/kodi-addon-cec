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
