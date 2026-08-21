"""Circuito completo: subir un vuelo llega a las estadísticas de la aerolínea.

No son tests del módulo `estadisticas` (esos están en `client/tests/`, con
dobles): esto sube un `.avlog.json` real por HTTP a `/api/registro/upload` y
comprueba que **el motor de evaluación de verdad** lo procesa y que
`/aerolinea` enseña el resultado. Es la prueba de que el enganche —el punto
más frágil, porque nunca debe romper una subida si algo falla— funciona de
extremo a extremo.

    python -m pytest web/test_estadisticas_web.py
"""
import json
import sys
from io import BytesIO
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

from app import app  # noqa: E402
from avcars import cuentas, estadisticas, sesion_web  # noqa: E402

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "client" / "tests" / "fixtures" / "sample_flight_pass.json"
)


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(sesion_web, "SESION_PATH", tmp_path / "sesion_activa.json")
    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    cuentas.crear_cuenta("EVA777", "clave", "eva777@ejemplo.com")

    import importacion
    hogar = tmp_path / "hogar"
    (hogar / "EvA" / "grabaciones").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: hogar))
    monkeypatch.setattr(importacion, "REGISTRO_PATH", tmp_path / "importados.json")

    app.config["TESTING"] = True
    yield
    cuentas.configurar_almacen(original)


def _cliente(user_id="EVA777"):
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = user_id
    return c


def _vuelo_de(license_id: str, callsign: str, huella: str) -> bytes:
    """El fixture real, con otro dueño y otra huella para no chocar con nada."""
    datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    datos["pilot"] = {"license_id": license_id, "callsign": callsign}
    datos["integrity"] = {"hash_algorithm": "sha256", "track_hash": huella}
    return json.dumps(datos).encode("utf-8")


def test_subir_un_vuelo_real_llega_a_la_aerolinea():
    """El vuelo pasa por evaluate_flight de verdad y aparece en /aerolinea."""
    c = _cliente()
    subida = c.post(
        "/api/registro/upload",
        data={"file": (BytesIO(_vuelo_de("EVA777", "EVA777", "h-circuito-1")), "circuito.avlog.json")},
        content_type="multipart/form-data",
    )
    assert subida.status_code == 200

    kpis = estadisticas.kpis_globales()
    assert kpis["total_vuelos"] == 1
    # El fixture está construido para dar APTO con el perfil normal.
    assert kpis["pct_apto"] == 100.0

    top = estadisticas.top_pilotos_actividad()
    assert top[0]["license_id"] == "EVA777"

    html = c.get("/aerolinea").get_data(as_text=True)
    assert "EVA777" in html
    assert "mapa-flota" in html
    assert "grafico-mensual" in html


def test_si_evaluar_falla_la_subida_no_se_entera(monkeypatch):
    """El resumen es un extra: un fallo ahí no puede tirar la subida del piloto."""
    import app as app_module

    def revienta(*_a, **_k):
        raise RuntimeError("motor roto, a propósito")

    monkeypatch.setattr(app_module, "evaluate_flight", revienta)

    c = _cliente()
    subida = c.post(
        "/api/registro/upload",
        data={"file": (BytesIO(_vuelo_de("EVA777", "EVA777", "h-circuito-2")), "circuito.avlog.json")},
        content_type="multipart/form-data",
    )

    assert subida.status_code == 200
    assert subida.get_json()["success"] is True
    # El vuelo del piloto está a salvo; el resumen, simplemente, no se creó.
    assert estadisticas.kpis_globales()["total_vuelos"] == 0


def test_un_csv_tambien_llega_sin_calidad():
    c = _cliente()
    csv = b"PLANE_LATITUDE,PLANE_LONGITUDE,PLANE_ALTITUDE\n40.47,-3.56,1200\n40.48,-3.55,1800\n"
    subida = c.post(
        "/api/registro/upload",
        data={"file": (BytesIO(csv), "circuito.csv")},
        content_type="multipart/form-data",
    )
    assert subida.status_code == 200

    kpis = estadisticas.kpis_globales()
    assert kpis["total_vuelos"] == 1
    assert kpis["vuelos_evaluados"] == 0  # el CSV no pasa por el motor
