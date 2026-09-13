"""Tests de la capa de decision. No requieren Kodi: cec.py no lo importa."""

import pytest


from cec import BUILTINS, SETTING_FOR, CecError, parse_action, resolve

TODO_PERMITIDO = lambda _setting: True
NADA_PERMITIDO = lambda _setting: False


@pytest.mark.parametrize("argv, esperado", [
    (["default.py", "standby"], "standby"),
    (["default.py", "action=standby"], "standby"),
    (["default.py", "?action=standby"], "standby"),
    (["default.py", "?action=activate&foo=1"], "activate"),
    (["default.py", "ACTION=Standby"], "standby"),
    (["default.py", "", "toggle"], "toggle"),
])
def test_parse_action_acepta_las_formas_reales(argv, esperado):
    """Addons.ExecuteAddon entrega los parametros de varias formas segun el llamante."""
    assert parse_action(argv) == esperado


@pytest.mark.parametrize("argv", [["default.py"], ["default.py", ""], ["default.py", "?"]])
def test_parse_action_sin_accion_es_error(argv):
    with pytest.raises(CecError):
        parse_action(argv)


def test_toda_accion_publica_tiene_builtin_y_ajuste():
    """Evita que se anada una accion y se olvide su interruptor de seguridad."""
    assert set(BUILTINS) == set(SETTING_FOR)


@pytest.mark.parametrize("accion, builtin", sorted(BUILTINS.items()))
def test_resolve_devuelve_el_builtin(accion, builtin):
    assert resolve(accion, TODO_PERMITIDO) == builtin


def test_resolve_rechaza_accion_desconocida():
    with pytest.raises(CecError) as exc:
        resolve("apagar_todo", TODO_PERMITIDO)
    assert "desconocida" in str(exc.value)


@pytest.mark.parametrize("accion", sorted(BUILTINS))
def test_resolve_respeta_el_veto_de_los_ajustes(accion):
    """Un ajuste desactivado tiene que impedir la accion, no solo ocultarla."""
    with pytest.raises(CecError) as exc:
        resolve(accion, NADA_PERMITIDO)
    assert "desactivada" in str(exc.value)


def test_resolve_consulta_el_ajuste_que_corresponde():
    """Vetar una accion no puede vetar las demas."""
    consultados = []

    def espia(setting_id):
        consultados.append(setting_id)
        return setting_id == "allow_standby"

    assert resolve("standby", espia) == "CECStandby"
    with pytest.raises(CecError):
        resolve("activate", espia)
    assert consultados == ["allow_standby", "allow_activate"]
