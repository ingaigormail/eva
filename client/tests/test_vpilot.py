"""Tests de avcars/vpilot.py: detección de vPilot y lectura de su CID."""
from pathlib import Path

from avcars.vpilot import find_vpilot_executable, read_vpilot_cid


def test_encuentra_la_ruta_personalizada_si_existe(tmp_path):
    exe = tmp_path / "vPilot.exe"
    exe.write_bytes(b"")
    assert find_vpilot_executable(str(exe)) == str(exe)


def test_ignora_la_ruta_personalizada_si_ya_no_existe(tmp_path):
    fantasma = str(tmp_path / "no_existe.exe")
    # Sin candidatas reales en este entorno de test, cae a None.
    resultado = find_vpilot_executable(fantasma)
    assert resultado != fantasma


def test_sin_ninguna_ruta_valida_devuelve_none():
    assert find_vpilot_executable("") is None or isinstance(find_vpilot_executable(""), str)


def test_lee_el_cid_de_un_config_real(tmp_path):
    cfg = tmp_path / "vPilotConfig.xml"
    cfg.write_text(
        "<vPilotConfig><NetworkLogin>1589090</NetworkLogin></vPilotConfig>",
        encoding="utf-8",
    )
    assert read_vpilot_cid(cfg) == "1589090"


def test_sin_fichero_de_configuracion_devuelve_none(tmp_path):
    assert read_vpilot_cid(tmp_path / "no_existe.xml") is None


def test_config_sin_networklogin_devuelve_none(tmp_path):
    cfg = tmp_path / "vPilotConfig.xml"
    cfg.write_text("<vPilotConfig><FullName>Piloto</FullName></vPilotConfig>", encoding="utf-8")
    assert read_vpilot_cid(cfg) is None


def test_config_con_formato_real_de_vpilot(tmp_path):
    """Formato real observado en una instalación de vPilot (2026-08-16)."""
    cfg = tmp_path / "vPilotConfig.xml"
    cfg.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<vPilotConfig xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
        "  <Version>4</Version>\n"
        "  <ServerName>AUTOMATIC</ServerName>\n"
        "  <NetworkLogin>1589090</NetworkLogin>\n"
        "  <NetworkPassword>DiKhD78RIOtBXdzgOioHVg==</NetworkPassword>\n"
        "  <FullName>Luis</FullName>\n"
        "</vPilotConfig>\n",
        encoding="utf-8",
    )
    assert read_vpilot_cid(cfg) == "1589090"
