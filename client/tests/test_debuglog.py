"""Pruebas del diario de incidencias.

Andamio de la fase de pruebas: este fichero se borra junto con
`avcars/debuglog.py` cuando se pase a producción.
"""
from __future__ import annotations

import pytest

from avcars import debuglog


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    """Cada prueba con su carpeta y sin heredar el interruptor del entorno."""
    monkeypatch.setattr(debuglog.paths, "base_dir", lambda: tmp_path)
    monkeypatch.delenv("EVA_DEBUG", raising=False)
    debuglog.reiniciar_deteccion()
    yield
    debuglog.reiniciar_deteccion()


def test_apagado_por_defecto(tmp_path):
    """Sin encenderlo no se escribe nada: en producción no debe estorbar."""
    assert not debuglog.activo()
    debuglog.apunte("no deberia aparecer")
    assert not debuglog.ruta().exists()


def test_se_enciende_por_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("EVA_DEBUG", "1")
    debuglog.reiniciar_deteccion()

    debuglog.apunte("probando")

    assert "probando" in debuglog.ruta().read_text(encoding="utf-8")


def test_se_enciende_por_fichero_interruptor(tmp_path):
    """El piloto que prueba no tiene por qué tocar variables de entorno."""
    (tmp_path / debuglog.NOMBRE_INTERRUPTOR).touch()
    debuglog.reiniciar_deteccion()

    debuglog.apunte("desde el fichero")

    assert "desde el fichero" in debuglog.ruta().read_text(encoding="utf-8")


def test_fallo_guarda_la_traza(monkeypatch):
    """El motivo del fallo es justo lo que se perdía al tragarse la excepción."""
    monkeypatch.setenv("EVA_DEBUG", "1")
    debuglog.reiniciar_deteccion()

    try:
        {}["ausente"]
    except Exception as exc:
        debuglog.fallo("prueba de traza", exc)

    escrito = debuglog.ruta().read_text(encoding="utf-8")
    assert "prueba de traza" in escrito
    assert "KeyError" in escrito
    assert "ausente" in escrito


def test_se_corta_al_pasarse_de_tamano(monkeypatch):
    """Un vuelo largo no puede llenar el disco del piloto."""
    monkeypatch.setenv("EVA_DEBUG", "1")
    monkeypatch.setattr(debuglog, "TAMANO_MAXIMO_BYTES", 200)
    debuglog.reiniciar_deteccion()

    for i in range(50):
        debuglog.apunte(f"linea de relleno numero {i}")

    assert debuglog.ruta().stat().st_size < 2000


def test_nunca_lanza_aunque_no_se_pueda_escribir(monkeypatch):
    """Un diario roto no puede tirar EvA."""
    monkeypatch.setenv("EVA_DEBUG", "1")
    debuglog.reiniciar_deteccion()
    monkeypatch.setattr(
        debuglog, "ruta", lambda: (_ for _ in ()).throw(OSError("disco lleno"))
    )

    debuglog.apunte("da igual")  # no debe propagar
    debuglog.fallo("tampoco aqui")
