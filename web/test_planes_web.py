"""Guardar un plan desde el planificador y volver a abrirlo (D3).

    python -m pytest web/test_planes_web.py
"""
import sys
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

from app import app  # noqa: E402
from avcars import cuentas, planes, sesion_web  # noqa: E402

PLAN = {
    "callsign": "EVA321",
    "rules": "V",
    "departure": "LEMD",
    "arrival": "LEIB",
    "alternate": "LEPA",
    "aircraft": "C172",
    "route": "DCT TERSA DCT",
    "cruise_alt_ft": 8000,
}


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(sesion_web, "SESION_PATH", tmp_path / "sesion_activa.json")
    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    cuentas.crear_cuenta("EvA18L", "clave", "uno@ejemplo.com")
    cuentas.crear_cuenta("EVA999", "clave", "otro@ejemplo.com")
    app.config["TESTING"] = True
    yield
    cuentas.configurar_almacen(original)


def _cliente(user_id="EvA18L"):
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = user_id
    return c


def test_sin_sesion_no_se_guarda_ni_se_lista():
    anonimo = app.test_client()
    assert anonimo.post("/api/plan/guardar", json=PLAN).status_code == 302
    assert anonimo.get("/planes-de-vuelo").status_code == 302
    assert planes.cuantos("EvA18L") == 0


def test_guardar_desde_el_planificador_y_verlo_en_la_lista():
    c = _cliente()
    r = c.post("/api/plan/guardar", json=PLAN)

    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    html = c.get("/planes-de-vuelo").get_data(as_text=True)
    assert "LEMD" in html and "LEIB" in html
    assert "C172" in html


def test_un_plan_incompleto_no_se_guarda_y_lo_dice():
    c = _cliente()
    r = c.post("/api/plan/guardar", json={"callsign": "EVA321"})

    assert r.status_code == 422
    assert "origen y destino" in r.get_json()["mensaje"]
    assert planes.cuantos("EvA18L") == 0


def test_guardar_dos_veces_el_mismo_plan_no_lo_duplica():
    c = _cliente()
    ident = c.post("/api/plan/guardar", json=PLAN).get_json()["id"]
    c.post("/api/plan/guardar", json={**PLAN, "arrival": "LEZL", "plan_id": ident})

    assert planes.cuantos("EvA18L") == 1
    assert planes.obtener(ident, "EvA18L")["destino"] == "LEZL"


def test_al_reabrirlo_el_planificador_trae_los_datos():
    c = _cliente()
    ident = c.post("/api/plan/guardar", json=PLAN).get_json()["id"]

    html = c.get(f"/plan?plan={ident}").get_data(as_text=True)
    assert "LEMD" in html and "TERSA" in html
    assert f"planAbiertoId = {ident}" in html


def test_el_plan_de_otro_ni_se_abre_ni_se_borra():
    ajeno = planes.guardar("EVA999", PLAN)
    c = _cliente("EvA18L")

    # No aparece en su lista.
    assert "LEMD" not in c.get("/planes-de-vuelo").get_data(as_text=True)
    # Y pedirlo por su número deja el planificador en blanco, sin confirmar
    # que exista.
    assert f"planAbiertoId = {ajeno}" not in c.get(
        f"/plan?plan={ajeno}"
    ).get_data(as_text=True)
    # Borrarlo da 404, igual que si no existiera.
    assert c.post(f"/planes-de-vuelo/{ajeno}/borrar").status_code == 404
    assert planes.obtener(ajeno, "EVA999") is not None


def test_borrar_un_plan_propio():
    c = _cliente()
    ident = c.post("/api/plan/guardar", json=PLAN).get_json()["id"]

    assert c.post(f"/planes-de-vuelo/{ident}/borrar").status_code == 302
    assert planes.cuantos("EvA18L") == 0


def test_sin_planes_se_dice_y_se_ofrece_el_planificador():
    html = _cliente().get("/planes-de-vuelo").get_data(as_text=True)
    assert "No tienes planes guardados" in html
    assert 'href="/plan"' in html


def test_el_boton_guardar_ya_no_esta_deshabilitado():
    html = _cliente().get("/plan").get_data(as_text=True)
    assert 'id="btn-guardar"' in html
    assert "pendiente" not in html.split('id="btn-guardar"')[1][:200]
