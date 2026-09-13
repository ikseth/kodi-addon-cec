"""Servicio del addon: consulta periodicamente el estado del televisor por CEC y
lo publica como propiedades de Window(Home) para que se pueda leer desde fuera
por JSON-RPC. La logica vive en resources/lib (sin dependencias de Kodi); aqui
solo esta el bucle y la conexion con la API de Kodi.
"""
import os
import sys
import time

import xbmc
import xbmcaddon
import xbmcgui

sys.path.insert(0, os.path.join(
    xbmcaddon.Addon().getAddonInfo("path"), "resources", "lib"))

from cec_kernel import POWER_UNKNOWN, CecKernel, Reading  # noqa: E402
from state import (CANDIDATE_DEVICES, PROP_REFRESH_REQUEST, PROP_TV_POWER,  # noqa: E402
                   PUBLISHED_PROPERTIES, RefreshScheduler, build_properties,
                   clamp_interval, select_device)

NAME = xbmcaddon.Addon().getAddonInfo("name")
HOME_WINDOW_ID = 10000
# Errores que indican que el adaptador ya no esta: se vuelve a detectar.
_REDETECT_ERRORS = ("ENOENT", "ENODEV", "ENXIO")


class Service(object):

    def __init__(self):
        self.monitor = xbmc.Monitor()
        self.home = xbmcgui.Window(HOME_WINDOW_ID)
        self.kernel = CecKernel()
        self.device = None
        self.last_refresh = self.home.getProperty(PROP_REFRESH_REQUEST)
        self.last_logged = None

    @staticmethod
    def _settings():
        addon = xbmcaddon.Addon()  # instancia nueva: recoge cambios de ajustes
        return (addon.getSettingBool("publish_state"),
                clamp_interval(addon.getSettingInt("poll_interval")),
                addon.getSettingString("cec_device"))

    def _publish(self, properties):
        for key, value in properties.items():
            self.home.setProperty(key, value)

    def _clear(self):
        for key in PUBLISHED_PROPERTIES:
            self.home.clearProperty(key)

    def _log_if_changed(self, reading):
        # Una linea por cambio, no una por consulta: evita llenar el log.
        key = (reading.state, reading.error, reading.device)
        if key != self.last_logged:
            self.last_logged = key
            level = xbmc.LOGWARNING if reading.error else xbmc.LOGINFO
            xbmc.log("%s: estado del televisor %r" % (NAME, reading), level)

    def _read(self, device_setting):
        if self.device is None or device_setting not in ("", "auto"):
            self.device = select_device(
                device_setting, lambda: self.kernel.find_adapter(CANDIDATE_DEVICES))
        if self.device is None:
            return Reading(POWER_UNKNOWN, "no_adapter", None)
        reading = self.kernel.query_power(self.device)
        if reading.error in _REDETECT_ERRORS:
            self.device = None
        return reading

    def run(self):
        enabled, interval, device_setting = self._settings()
        # El planificador va con reloj monotonico: al arrancar, algunos equipos
        # tienen la hora sin sincronizar (p. ej. 1980) y luego salta. La marca
        # publicada, en cambio, si es hora de pared, porque la leen desde fuera.
        scheduler = RefreshScheduler(interval, time.monotonic())
        xbmc.log("%s: servicio iniciado (intervalo %ss)" % (NAME, interval), xbmc.LOGINFO)
        while not self.monitor.abortRequested():
            now = time.monotonic()
            request = self.home.getProperty(PROP_REFRESH_REQUEST)
            if request and request != self.last_refresh:
                self.last_refresh = request
                scheduler.request_refresh(now, self.home.getProperty(PROP_TV_POWER))
            if scheduler.due(now):
                enabled, interval, device_setting = self._settings()
                scheduler.interval = interval
                if enabled:
                    try:
                        reading = self._read(device_setting)
                    except Exception as exc:  # el servicio no debe morir nunca
                        reading = Reading(POWER_UNKNOWN, "internal:%s" % type(exc).__name__, self.device)
                    self._publish(build_properties(reading, time.time(), interval))
                    self._log_if_changed(reading)
                    scheduler.done(now, reading.state)
                else:
                    self._clear()
                    scheduler.done(now, None)
            if self.monitor.waitForAbort(1):
                break
        self._clear()
        xbmc.log("%s: servicio detenido" % NAME, xbmc.LOGINFO)


if __name__ == "__main__":
    Service().run()
