"""Contrato de propiedades publicadas y planificacion de lecturas.

No importa nada de Kodi. El contrato es lo que leen los consumidores externos
(p. ej. un sistema domotico) con XBMC.GetInfoLabels sobre
Window(Home).Property(<nombre>). Cualquier cambio incompatible exige subir
PROTOCOL.
"""

PROTOCOL = "1"

PROP_PROTOCOL = "cec.protocol"
PROP_TV_POWER = "cec.tv_power"            # on | standby | unknown
PROP_TV_POWER_TS = "cec.tv_power_ts"      # epoch (s) de la ultima consulta
PROP_ERROR = "cec.error"                  # vacio si la consulta dio un estado
PROP_DEVICE = "cec.device"                # adaptador consultado
PROP_POLL_INTERVAL = "cec.poll_interval"  # segundos entre consultas

PUBLISHED_PROPERTIES = (PROP_PROTOCOL, PROP_TV_POWER, PROP_TV_POWER_TS,
                        PROP_ERROR, PROP_DEVICE, PROP_POLL_INTERVAL)

# La escribe el script tras enviar una orden; el servicio la usa para releer ya.
PROP_REFRESH_REQUEST = "cec.refresh_request"

CANDIDATE_DEVICES = ("/dev/cec0", "/dev/cec1", "/dev/cec2", "/dev/cec3")

DEFAULT_INTERVAL = 30
MIN_INTERVAL = 10
MAX_INTERVAL = 300

# Tras una orden el televisor tarda en cambiar, y mientras cambia no contesta:
# medido, un standby se ve a los ~5 s, pero un encendido no contesta hasta ~40 s.
# Por eso no hay rafaga fija: se relee cada BURST_STEP hasta obtener un estado
# definitivo distinto del que habia al dar la orden, con BURST_MAX de tope.
BURST_FIRST = 2
BURST_STEP = 3
BURST_MAX = 60
_DEFINITIVE = ("on", "standby")


def clamp_interval(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL
    return max(MIN_INTERVAL, min(MAX_INTERVAL, value))


def select_device(setting, finder):
    """`setting` es el ajuste del usuario; `finder` detecta el adaptador."""
    if not setting or setting == "auto":
        return finder()
    return setting


def build_properties(reading, now, interval):
    return {
        PROP_PROTOCOL: PROTOCOL,
        PROP_TV_POWER: reading.state,
        PROP_TV_POWER_TS: str(int(now)),
        PROP_ERROR: reading.error or "",
        PROP_DEVICE: reading.device or "",
        PROP_POLL_INTERVAL: str(interval),
    }


class RefreshScheduler(object):
    """Decide cuando toca consultar.

    En reposo, cada `interval` segundos. Tras una peticion de refresco entra en
    modo rafaga: consulta cada BURST_STEP segundos hasta ver un estado definitivo
    distinto del de partida, o hasta BURST_MAX. `now` puede ser cualquier reloj
    monotonico: el planificador no mira la hora de pared.
    """

    def __init__(self, interval, now):
        self.interval = interval
        self._next = now
        self._burst_next = None
        self._burst_until = None
        self._burst_from = None

    @property
    def in_burst(self):
        return self._burst_next is not None

    def request_refresh(self, now, current_state):
        """`current_state` es el ultimo estado publicado al recibir la orden."""
        self._burst_next = now + BURST_FIRST
        self._burst_until = now + BURST_MAX
        self._burst_from = current_state

    def due(self, now):
        if self.in_burst and now >= self._burst_next:
            return True
        return now >= self._next

    def done(self, now, state):
        """Registra una consulta hecha en `now` que devolvio `state`."""
        if self.in_burst:
            changed = state in _DEFINITIVE and state != self._burst_from
            if changed or now >= self._burst_until:
                self._burst_next = self._burst_until = self._burst_from = None
            else:
                self._burst_next = now + BURST_STEP
        self._next = now + self.interval
