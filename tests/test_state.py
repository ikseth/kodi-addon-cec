"""Tests del contrato de propiedades y del planificador de lecturas."""
import pytest

import state
from cec_kernel import Reading


def test_propiedades_publicadas():
    props = state.build_properties(Reading("on", None, "/dev/cec0"), 1000.9, 30)
    assert props == {
        "cec.protocol": state.PROTOCOL, "cec.tv_power": "on",
        "cec.tv_power_ts": "1000", "cec.error": "", "cec.device": "/dev/cec0",
        "cec.poll_interval": "30"}
    assert set(props) == set(state.PUBLISHED_PROPERTIES)


def test_propiedades_con_error_y_sin_adaptador():
    props = state.build_properties(Reading("unknown", "no_adapter", None), 5, 30)
    assert props["cec.tv_power"] == "unknown"
    assert props["cec.error"] == "no_adapter"
    assert props["cec.device"] == ""


@pytest.mark.parametrize("value, expected", [
    (30, 30), (5, 10), (999, 300), ("45", 45), ("x", 30), (None, 30)])
def test_clamp_interval(value, expected):
    assert state.clamp_interval(value) == expected


def test_select_device():
    assert state.select_device("auto", lambda: "/dev/cec1") == "/dev/cec1"
    assert state.select_device("", lambda: "/dev/cec1") == "/dev/cec1"
    assert state.select_device("/dev/cec0", lambda: "/dev/cec1") == "/dev/cec0"


def test_scheduler_consulta_al_arrancar_y_luego_cada_intervalo():
    s = state.RefreshScheduler(30, now=100)
    assert s.due(100)
    s.done(100, "on")
    assert not s.due(129)
    assert s.due(130)


def _simular(scheduler, respuestas, desde, hasta):
    """Recorre el tiempo segundo a segundo consultando cuando toca.
    `respuestas(t)` da el estado que devolveria el televisor en el instante t."""
    consultas = []
    for t in range(desde, hasta):
        if scheduler.due(t):
            estado = respuestas(t)
            consultas.append((t, estado))
            scheduler.done(t, estado)
    return consultas


def test_rafaga_de_apagado_termina_al_ver_standby():
    s = state.RefreshScheduler(30, now=0)
    s.done(0, "on")
    s.request_refresh(10, "on")
    consultas = _simular(s, lambda t: "unknown" if t < 15 else "standby", 10, 39)
    assert consultas == [(12, "unknown"), (15, "standby")]
    assert not s.in_burst


def test_rafaga_de_encendido_espera_a_que_la_tele_conteste():
    """Medido en real: tras encender, la tele no contesta por CEC en ~40 s."""
    s = state.RefreshScheduler(30, now=0)
    s.done(0, "standby")
    s.request_refresh(10, "standby")
    consultas = _simular(s, lambda t: "unknown" if t < 50 else "on", 10, 80)
    # rafaga a 12, 15, ... de 3 en 3: la primera tras t=50 es 51
    assert consultas[-1] == (51, "on")
    assert all(b - a == 3 for (a, _), (b, _) in zip(consultas, consultas[1:]))
    assert not s.in_burst


def test_rafaga_no_para_con_el_estado_de_partida_todavia_sin_cambiar():
    """Justo tras un standby la tele puede contestar aun 'on': no es el final."""
    s = state.RefreshScheduler(30, now=0)
    s.done(0, "on")
    s.request_refresh(10, "on")
    consultas = _simular(s, lambda t: "on" if t < 18 else "standby", 10, 40)
    assert (12, "on") in consultas and consultas[-1] == (18, "standby")


def test_rafaga_tiene_tope_si_el_estado_nunca_cambia():
    s = state.RefreshScheduler(30, now=0)
    s.done(0, "on")
    s.request_refresh(10, "on")          # activate con la tele ya encendida
    consultas = _simular(s, lambda t: "on", 10, 200)
    en_rafaga = [t for t, _ in consultas if t <= 70]
    assert en_rafaga[-1] >= 70 - state.BURST_STEP and not s.in_burst
    # tras el tope vuelve al ritmo normal de 30 s
    despues = [t for t, _ in consultas if t > 70]
    assert all(b - a == 30 for a, b in zip(despues, despues[1:]))
