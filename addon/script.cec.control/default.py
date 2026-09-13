"""Punto de entrada del addon. Lo invoca Kodi con RunScript o Addons.ExecuteAddon.

Ejemplo desde Home Assistant:

    action: kodi.call_method
    target: {entity_id: media_player.my_kodi}
    data:
      method: Addons.ExecuteAddon
      addonid: script.cec.control
      params: {action: standby}
"""
import os
import sys
import time

import xbmc
import xbmcaddon
import xbmcgui

sys.path.insert(0, os.path.join(
    xbmcaddon.Addon().getAddonInfo("path"), "resources", "lib"))

from cec import CecError, parse_action, resolve  # noqa: E402  (tras ajustar sys.path)
from state import PROP_REFRESH_REQUEST  # noqa: E402

ADDON = xbmcaddon.Addon()
NOMBRE = ADDON.getAddonInfo("name")


def _permitida(setting_id):
    return ADDON.getSettingBool(setting_id)


def _avisar(mensaje, error=False):
    """Notificacion en pantalla. Los errores se muestran siempre; los exitos,
    solo si el usuario ha dejado activado el aviso en los ajustes."""
    if error or ADDON.getSettingBool("notify_on_run"):
        xbmcgui.Dialog().notification(
            NOMBRE, mensaje,
            xbmcgui.NOTIFICATION_ERROR if error else xbmcgui.NOTIFICATION_INFO,
            4000)


def main(argv):
    try:
        accion = parse_action(argv)
        builtin = resolve(accion, _permitida)
    except CecError as exc:
        xbmc.log("%s: %s" % (NOMBRE, exc), xbmc.LOGERROR)
        _avisar(str(exc), error=True)
        return 1

    xbmc.log("%s: accion '%s' -> builtin %s" % (NOMBRE, accion, builtin), xbmc.LOGINFO)
    xbmc.executebuiltin(builtin)
    # El servicio relee el estado del televisor en rafaga al ver este cambio.
    xbmcgui.Window(10000).setProperty(PROP_REFRESH_REQUEST, "%.3f" % time.time())
    _avisar(ADDON.getLocalizedString(30200) % accion)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
