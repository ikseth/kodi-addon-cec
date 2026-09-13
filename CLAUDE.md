# CLAUDE.md — kodi-addon-cec

Contexto operativo del proyecto. Leelo entero antes de tocar codigo o documentacion.

## Que es esto

Addon de Kodi (`script.cec.control`) que expone las acciones CEC de Kodi para poder
invocarlas desde fuera por JSON-RPC. La mitad domotica de esta funcionalidad vive
aparte, en el repositorio `ha-addons` (componente `cec_tv`, pendiente); este repo
es solo la mitad que corre dentro de Kodi.

## La restriccion que define el diseno

**No se puede hablar con el bus CEC desde fuera de Kodi.** libCEC va compilado
dentro de Kodi y mantiene el adaptador abierto en modo exclusivo; cualquier
proceso externo recibe `EBUSY` (`ioctl CEC_S_MODE failed - errno=16`). Medido en
LibreELEC y en Recalbox.

Consecuencia: el addon **no transmite CEC por su cuenta**. Traduce una accion a un
builtin de Kodi (`CECStandby`, `CECActivateSource`, `CECToggleState`) y deja que
transmita Kodi. Si alguna vez hace falta *leer* el estado del televisor, hay un
camino validado que no pasa por Kodi: ver `docs/DESIGN.md`.

## Reglas

1. Nada ad hoc. Antes de anadir una accion, anadir su ajuste y su test.
2. `resources/lib/cec.py` **no importa `xbmc`**. Es la frontera que permite testear
   sin Kodi, y no se cruza: todo lo que dependa de Kodi va en `default.py`.
3. Toda accion publica necesita entrada en `BUILTINS`, en `SETTING_FOR`, en
   `settings.xml` y en los dos `strings.po`. Hay un test que vigila las dos primeras.
4. Los ajustes son de seguridad, no decorativos: una accion vetada tiene que
   **fallar**, no ocultarse.
5. Commits solo tras validacion funcional en un equipo real. Los tests pasan sin
   Kodi, pero no demuestran que el televisor obedezca.

## Protocolo de validacion funcional

Con el televisor en standby y Kodi arrancado:

1. `activate` -> el televisor se enciende y cambia a la entrada HDMI del equipo.
2. `standby` -> el televisor se apaga.
3. Repetir la llamada desde el sistema domotico (`kodi.call_method`) y no solo
   con `RunScript`, para cubrir el camino completo.
4. Con `allow_standby` desactivado, `standby` debe quedar rechazada y registrada.

## Entorno de pruebas

Se indica en la sesion de trabajo. **No fijar aqui IPs, nombres de equipo ni
credenciales**: este repositorio es publico.
