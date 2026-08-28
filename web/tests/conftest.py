"""Arnés para probar las rutas web sin tocar nada real.

`web/app.py` importa el motor y el esquema desde `client/`, así que los dos
directorios tienen que estar en el path antes de importarlo. Y hay tres cosas
que hay que desviar a un sitio temporal o los tests escribirían en producción:

- la base de cuentas (`cuentas.configurar_almacen`),
- las carpetas donde se buscan los vuelos (`app.SEARCH_DIRS`),
- el registro de importaciones, que `dueno_del_vuelo()` consulta.

Ver `client/tests/test_cuentas.py`: el 2026-08-18 un `pytest` que creía usar un
directorio temporal dejó una tabla con esquema equivocado en el `eva.db` de
verdad. De ahí que las fixtures restauren siempre lo que había.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
for carpeta in (RAIZ / "web", RAIZ / "client"):
    if str(carpeta) not in sys.path:
        sys.path.insert(0, str(carpeta))


#: Los dos pilotos del escenario. Ni uno es responsable: lo que se prueba aquí
#: es lo que puede ver un piloto normal, que es donde estaba el agujero.
PILOTO = "EVA001"
OTRO = "EVA002"


def _vuelo(license_id: str) -> dict:
    """Un vuelo mínimo pero válido para el esquema, del piloto indicado."""
    punto = {
        "t": 0.0,
        "lat": 40.4719,
        "lon": -3.5626,
        "alt_msl_ft": 2000.0,
        "alt_agl_ft": 0.0,
        "hdg_deg": 182.0,
        "gs_kt": 0.0,
        "ias_kt": 0.0,
        "vs_fpm": 0.0,
        "on_ground": True,
    }
    return {
        "schema_version": "1.0",
        "client": {"name": "pruebas", "version": "0", "simulator": "MSFS"},
        "pilot": {"license_id": license_id, "callsign": license_id},
        "flight_plan": {
            "rules": "VFR",
            "departure_icao": "LEMD",
            "arrival_icao": "LETO",
            "network": "OFFLINE",
            "atc_controlled": False,
        },
        "timing": {"started_utc": "2026-08-27T10:00:00Z"},
        "events": [],
        "track": [punto],
        "summary": {"distance_nm": 20.0, "flight_time_min": 15.0},
    }


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Deja el mundo entero apuntando a `tmp_path` y lo devuelve al terminar.

    Cede un diccionario con el cliente de pruebas y el nombre del fichero de
    cada piloto, que es lo que necesitan los tests para pedir rutas.
    """
    # `importacion` es un módulo de `web/`, no del paquete `avcars`.
    import importacion
    from avcars import cuentas

    original_almacen = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")

    grabaciones = tmp_path / "grabaciones"
    grabaciones.mkdir()

    import app as modulo_app

    monkeypatch.setattr(modulo_app, "SEARCH_DIRS", [grabaciones])
    # `dueno_del_vuelo()` cae aquí para los `.csv`, que no llevan piloto
    # dentro. Si apuntara al registro real, un vuelo de producción podría
    # colarse en el escenario.
    monkeypatch.setattr(
        importacion, "REGISTRO_PATH", tmp_path / "importados.json"
    )

    ficheros = {}
    for quien in (PILOTO, OTRO):
        nombre = f"2026-08-27_10-00-00_{quien}.avlog.json"
        (grabaciones / nombre).write_text(
            json.dumps(_vuelo(quien)), encoding="utf-8"
        )
        ficheros[quien] = nombre

    for quien in (PILOTO, OTRO):
        cuentas.crear_cuenta(quien, "secreto-de-prueba", f"{quien}@ejemplo.es")

    modulo_app.app.config["TESTING"] = True
    cliente = modulo_app.app.test_client()

    def como(piloto: str) -> None:
        """Abre sesión como ese piloto, sin pasar por el formulario de login."""
        with cliente.session_transaction() as sesion:
            sesion["user_id"] = piloto

    # Todo va dentro de la fixture, incluidos los nombres y el ayudante. Los
    # tests NO hacen `from conftest import ...`: ese import resuelve por
    # sys.path, y al ejecutar `pytest web/tests client/tests` de una vez se
    # quedaba con el conftest de client/ y la colección fallaba entera.
    yield {
        "cliente": cliente,
        "app": modulo_app,
        "ficheros": ficheros,
        "grabaciones": grabaciones,
        "piloto": PILOTO,
        "otro": OTRO,
        "como": como,
    }

    cuentas.configurar_almacen(original_almacen)
