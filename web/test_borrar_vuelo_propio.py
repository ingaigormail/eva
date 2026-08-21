"""Un piloto borra un vuelo suyo desde «Mis vuelos». Nunca el de otro.

    python -m pytest web/test_borrar_vuelo_propio.py
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
    import app as app_module
    import importacion

    monkeypatch.setattr(sesion_web, "SESION_PATH", tmp_path / "sesion_activa.json")

    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    cuentas.crear_cuenta("EVA18L", "clave", "eva18l@ejemplo.com")
    cuentas.crear_cuenta("EVA999", "clave", "eva999@ejemplo.com")

    hogar = tmp_path / "hogar"
    grabaciones = hogar / "EvA" / "grabaciones"
    grabaciones.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: hogar))
    monkeypatch.setattr(app_module, "SEARCH_DIRS", [grabaciones])
    monkeypatch.setattr(importacion, "REGISTRO_PATH", tmp_path / "importados.json")

    app.config["TESTING"] = True
    yield
    cuentas.configurar_almacen(original)


def _entrar(user_id, password="clave"):
    c = app.test_client()
    c.post("/login", data={"user_id": user_id, "password": password})
    return c


def _subir(cliente, license_id, huella, nombre="mio.avlog.json"):
    datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    datos["pilot"] = {"license_id": license_id, "callsign": license_id}
    datos["integrity"] = {"hash_algorithm": "sha256", "track_hash": huella}
    return cliente.post(
        "/api/registro/upload",
        data={"file": (BytesIO(json.dumps(datos).encode()), nombre)},
        content_type="multipart/form-data",
    )


def test_un_piloto_borra_su_propio_vuelo():
    c = _entrar("EVA18L")
    _subir(c, "EVA18L", "h-mio-1")
    assert estadisticas.kpis_globales()["total_vuelos"] == 1

    r = c.post("/vuelos/mio.avlog.json/borrar", follow_redirects=True)
    assert "borrado" in r.get_data(as_text=True)

    html = c.get("/vuelos").get_data(as_text=True)
    assert "mio.avlog.json" not in html
    # También sale de las estadísticas de la aerolínea.
    assert estadisticas.kpis_globales()["total_vuelos"] == 0


def test_no_se_puede_borrar_el_vuelo_de_otro_piloto():
    dueno = _entrar("EVA18L")
    _subir(dueno, "EVA18L", "h-ajeno-1", nombre="ajeno.avlog.json")

    otro = _entrar("EVA999")
    r = otro.post("/vuelos/ajeno.avlog.json/borrar")

    assert r.status_code == 404
    # Sigue intacto para su dueño.
    html = dueno.get("/vuelos").get_data(as_text=True)
    assert "ajeno.avlog.json" in html


def test_borrar_algo_que_no_existe_da_404():
    c = _entrar("EVA18L")
    assert c.post("/vuelos/fantasma.avlog.json/borrar").status_code == 404


def test_sin_sesion_no_se_puede_borrar_nada():
    anonimo = app.test_client()
    r = anonimo.post("/vuelos/loquesea.avlog.json/borrar")
    assert r.status_code == 302


def test_borrar_libera_la_huella_para_volver_a_subirlo():
    c = _entrar("EVA18L")
    _subir(c, "EVA18L", "h-repetido")
    c.post("/vuelos/mio.avlog.json/borrar")

    r = _subir(c, "EVA18L", "h-repetido")
    assert r.get_json()["success"] is True
