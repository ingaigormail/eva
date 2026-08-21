"""Pruebas de los controles de importación de la cartilla.

Las dos reglas que se comprueban aquí las pidió el usuario el 2026-08-17: un
vuelo no se importa dos veces, y no lo importa otro piloto. Viven en
`web/importacion.py`; se prueban desde aquí porque es donde está la suite.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "web"))

import importacion  # noqa: E402


@pytest.fixture(autouse=True)
def _registro_aislado(tmp_path, monkeypatch):
    """Cada prueba con su propio registro de importados."""
    monkeypatch.setattr(importacion, "REGISTRO_PATH", tmp_path / "importados.json")


def _vuelo(license_id: str = "AHI001", track_hash: str = "abc123") -> bytes:
    return json.dumps(
        {
            "pilot": {"license_id": license_id, "callsign": "AHI500"},
            "integrity": {"hash_algorithm": "SHA-256", "track_hash": track_hash},
            "track": [],
        }
    ).encode("utf-8")


# -- nombre del fichero -------------------------------------------------


@pytest.mark.parametrize(
    "nombre",
    ["../../fuera.avlog.json", "..\\arriba.avlog.json", "C:/Windows/mal.avlog.json"],
)
def test_el_nombre_pierde_las_carpetas(nombre):
    """Un nombre con rutas no puede escribir fuera de las grabaciones."""
    try:
        limpio = importacion.nombre_seguro(nombre)
    except importacion.ImportacionRechazada:
        return  # rechazarlo también vale
    assert "/" not in limpio and "\\" not in limpio
    assert not Path(limpio).is_absolute()


def test_nombre_vacio_se_rechaza():
    with pytest.raises(importacion.ImportacionRechazada):
        importacion.nombre_seguro("")


# -- no dos veces -------------------------------------------------------


def test_el_mismo_vuelo_no_entra_dos_veces():
    contenido = _vuelo()
    nombre, huella = importacion.revisar(contenido, "vuelo.avlog.json", "AHI001")
    importacion.anotar(huella, "AHI001", nombre)

    with pytest.raises(importacion.ImportacionRechazada) as fallo:
        importacion.revisar(contenido, "vuelo.avlog.json", "AHI001")
    assert fallo.value.codigo == 409


def test_renombrar_el_fichero_no_cuela():
    """La huella es de la traza, no del nombre."""
    contenido = _vuelo()
    _, huella = importacion.revisar(contenido, "vuelo.avlog.json", "AHI001")
    importacion.anotar(huella, "AHI001", "vuelo.avlog.json")

    with pytest.raises(importacion.ImportacionRechazada):
        importacion.revisar(contenido, "otro-nombre-distinto.avlog.json", "AHI001")


def test_dos_vuelos_distintos_entran_los_dos():
    """El control no puede bloquear vuelos legítimos."""
    primero = _vuelo(track_hash="aaa")
    segundo = _vuelo(track_hash="bbb")

    _, huella = importacion.revisar(primero, "uno.avlog.json", "AHI001")
    importacion.anotar(huella, "AHI001", "uno.avlog.json")

    nombre, _ = importacion.revisar(segundo, "dos.avlog.json", "AHI001")
    assert nombre == "dos.avlog.json"


# -- de quién es el vuelo -----------------------------------------------


def test_no_se_importa_el_vuelo_de_otro():
    with pytest.raises(importacion.ImportacionRechazada) as fallo:
        importacion.revisar(_vuelo(license_id="AHI001"), "v.avlog.json", "AHI999")
    assert fallo.value.codigo == 403
    assert "AHI001" in fallo.value.mensaje


def test_un_vuelo_sin_dueno_lo_toma_quien_lo_sube():
    """Los vuelos viejos no llevan license_id; no hay nada que contradiga."""
    sin_dueno = json.dumps(
        {"pilot": {"callsign": "AHI500"}, "integrity": {"track_hash": "zzz"}, "track": []}
    ).encode("utf-8")

    nombre, _ = importacion.revisar(sin_dueno, "viejo.avlog.json", "AHI999")
    assert nombre == "viejo.avlog.json"


def test_un_vuelo_ya_importado_por_otro_no_se_reclama():
    contenido = _vuelo(license_id="AHI001")
    _, huella = importacion.revisar(contenido, "v.avlog.json", "AHI001")
    importacion.anotar(huella, "AHI001", "v.avlog.json")

    # Otro piloto con el mismo fichero, ya editado para figurar como suyo.
    ajeno = _vuelo(license_id="AHI999")
    with pytest.raises(importacion.ImportacionRechazada) as fallo:
        importacion.revisar(ajeno, "v.avlog.json", "AHI999")
    assert fallo.value.codigo == 403


# -- formatos -----------------------------------------------------------


def test_el_csv_se_reconoce_por_su_contenido():
    uno = b"tiempo,alt\n1,100\n"
    _, huella = importacion.revisar(uno, "vuelo.csv", "AHI001")
    importacion.anotar(huella, "AHI001", "vuelo.csv")

    with pytest.raises(importacion.ImportacionRechazada):
        importacion.revisar(uno, "copia.csv", "AHI001")


def test_otros_formatos_se_rechazan():
    with pytest.raises(importacion.ImportacionRechazada) as fallo:
        importacion.revisar(b"lo que sea", "vuelo.txt", "AHI001")
    assert fallo.value.codigo == 400


def test_un_avlog_ilegible_no_revienta():
    with pytest.raises(importacion.ImportacionRechazada) as fallo:
        importacion.revisar(b"{roto", "vuelo.avlog.json", "AHI001")
    assert fallo.value.codigo == 400
