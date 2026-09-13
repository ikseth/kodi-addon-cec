"""Capa de decision del addon, sin dependencias de Kodi para poder testearla.

El addon no habla con el bus CEC por su cuenta: traduce una accion a un builtin
de Kodi y deja que sea Kodi quien transmita. Ese reparto es deliberado. libCEC
va compilado dentro de Kodi y mantiene el adaptador abierto en modo exclusivo,
asi que cualquier proceso externo que intente abrirlo recibe EBUSY. Pidiendoselo
a Kodi el problema desaparece.
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
