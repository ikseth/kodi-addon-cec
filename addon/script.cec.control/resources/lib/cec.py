"""Capa de decision del addon, sin dependencias de Kodi para poder testearla.

Cada accion se traduce a un builtin de Kodi. Excepcion desde 0.3.0: el standby se
envia primero directamente por el API CEC del kernel (modo iniciador no exclusivo,
el mismo que usa la lectura del estado), porque CECStandby solo actua si Kodi es la
fuente activa. Si el envio directo falla o esta desactivado, se usa el builtin.
"""

# Accion publica -> builtin de Kodi que la ejecuta.
BUILTINS = {
    "standby": "CECStandby",
    "activate": "CECActivateSource",
    "toggle": "CECToggleState",
}

# Cada accion se puede vetar por separado desde los ajustes del addon.
SETTING_FOR = {
    "standby": "allow_standby",
    "activate": "allow_activate",
    "toggle": "allow_toggle",
}


# Ajuste que activa el envio directo del standby por el kernel (0.3.0).
SETTING_STANDBY_DIRECT = "standby_direct"


def plan_standby(direct_enabled, device, send):
    """Decide como ejecutar el standby.

    `send(device)` envia el standby por el kernel y devuelve None o un error.
    Devuelve (via, error): via es 'kernel' si se envio directamente, o 'builtin'
    si hay que recurrir a CECStandby (con el motivo en `error`, o None si el envio
    directo esta desactivado).
    """
    if not direct_enabled:
        return "builtin", None
    if not device:
        return "builtin", "no_adapter"
    error = send(device)
    if error is None:
        return "kernel", None
    return "builtin", error


class CecError(Exception):
    """Error de uso: accion ausente, desconocida o desactivada en ajustes."""


def parse_action(argv):
    """Extrae la accion de los argumentos con los que Kodi arranca el script.

    Addons.ExecuteAddon entrega los parametros de formas distintas segun quien
    llame y como los pase, asi que se aceptan las tres que se dan en la practica:
    'standby', 'action=standby' y '?action=standby'.
    """
    for raw in argv[1:]:
        if raw is None:
            continue
        item = raw.strip()
        if item.startswith("?"):
            item = item[1:]
        for pieza in item.split("&"):
            if not pieza:
                continue
            if "=" in pieza:
                clave, _, valor = pieza.partition("=")
                if clave.strip().lower() == "action":
                    return valor.strip().lower()
            elif pieza.lower() in BUILTINS:
                return pieza.lower()
    raise CecError("falta el parametro 'action'")


def resolve(action, is_allowed):
    """Devuelve el builtin de Kodi para una accion ya validada.

    `is_allowed` recibe el id del ajuste y responde si esa accion esta permitida.
    Se inyecta para que esta capa no dependa de la API de ajustes de Kodi.
    """
    if action not in BUILTINS:
        raise CecError(
            "accion desconocida: %s (validas: %s)"
            % (action, ", ".join(sorted(BUILTINS)))
        )
    if not is_allowed(SETTING_FOR[action]):
        raise CecError("la accion '%s' esta desactivada en los ajustes" % action)
    return BUILTINS[action]
