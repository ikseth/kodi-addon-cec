"""Coherencia entre addon.xml, settings.xml, traducciones y codigo."""
import os
import re
import xml.etree.ElementTree as ET

from conftest import ADDON_DIR

import cec
import state


def _read(*parts):
    with open(os.path.join(ADDON_DIR, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_addon_declara_script_y_servicio_y_sus_ficheros_existen():
    root = ET.fromstring(_read("addon.xml"))
    points = {e.get("point"): e.get("library") for e in root.findall("extension")}
    assert points["xbmc.python.script"] == "default.py"
    assert points["xbmc.service"] == "service.py"
    for library in ("default.py", "service.py"):
        assert os.path.isfile(os.path.join(ADDON_DIR, library))


def test_la_version_encabeza_las_novedades():
    root = ET.fromstring(_read("addon.xml"))
    news = root.find("extension[@point='xbmc.addon.metadata']/news").text
    assert news.strip().splitlines()[0].strip() == root.get("version")


def _setting_ids():
    return {s.get("id") for s in ET.fromstring(_read("resources", "settings.xml")).iter("setting")}


def test_todos_los_ajustes_que_usa_el_codigo_existen():
    usados = set(cec.SETTING_FOR.values()) | {"notify_on_run", "publish_state", "poll_interval", "cec_device"}
    assert usados <= _setting_ids()


def test_todas_las_etiquetas_estan_traducidas_en_ambos_idiomas():
    xml = _read("resources", "settings.xml")
    ids = set(re.findall(r'(?:label|help)="(\d+)"', xml)) | {"30200"}
    for lang in ("es_es", "en_gb"):
        po = _read("resources", "language", "resource.language.%s" % lang, "strings.po")
        definidos = set(re.findall(r'msgctxt "#(\d+)"', po))
        assert ids <= definidos, (lang, sorted(ids - definidos))


def test_la_logica_no_depende_de_kodi():
    """La frontera que permite testear sin Kodi."""
    for modulo in ("cec.py", "cec_kernel.py", "state.py"):
        codigo = _read("resources", "lib", modulo)
        assert not re.search(r"^\s*(import|from)\s+xbmc", codigo, re.M), modulo


def test_protocolo_definido():
    assert state.PROTOCOL.isdigit()


def test_el_servicio_planifica_con_reloj_monotonico_y_publica_hora_de_pared():
    """Al arrancar, la hora del sistema puede estar sin sincronizar y saltar despues."""
    codigo = _read("service.py")
    assert "RefreshScheduler(interval, time.monotonic())" in codigo
    assert "now = time.monotonic()" in codigo
    assert "build_properties(reading, time.time(), interval)" in codigo
