"""Gestión de vuelos: solo un administrador sube por otro o borra cualquiera.

    python -m pytest web/test_gestion_vuelos.py
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
    cuentas.configurar_almacen(tmp_path / "usuarios.json")  # semilla: pruebas (admin)
    cuentas.crear_cuenta("EVA18L", "clave", "eva18l@ejemplo.com")

    hogar = tmp_path / "hogar"
    grabaciones = hogar / "EvA" / "grabaciones"
    grabaciones.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: hogar))
    monkeypatch.setattr(app_module, "SEARCH_DIRS", [grabaciones])
    monkeypatch.setattr(importacion, "REGISTRO_PATH", tmp_path / "importados.json")

    app.config["TESTING"] = True
    yield
    cuentas.configurar_almacen(original)


def _entrar(user_id, password):
    c = app.test_client()
    c.post("/login", data={"user_id": user_id, "password": password})
    return c


@pytest.fixture
def admin():
    return _entrar("pruebas", "pruebas")


@pytest.fixture
def piloto():
    return _entrar("EVA18L", "clave")


def _vuelo_de(license_id: str, huella: str) -> bytes:
    datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    datos["pilot"] = {"license_id": license_id, "callsign": license_id}
    datos["integrity"] = {"hash_algorithm": "sha256", "track_hash": huella}
    return json.dumps(datos).encode("utf-8")


# -- quién entra -----------------------------------------------------------


def test_un_piloto_normal_no_entra_en_la_gestion_de_vuelos(piloto):
    assert piloto.get("/gestion/vuelos").status_code == 403
    assert piloto.post("/gestion/vuelos/subir", data={}).status_code == 403
    assert piloto.post("/gestion/vuelos/x.avlog.json/borrar").status_code == 403


def test_sin_sesion_al_login(client_anonimo=None):
    anonimo = app.test_client()
    assert anonimo.get("/gestion/vuelos").status_code == 302


# -- subir en nombre de otro ------------------------------------------------


def test_el_admin_sube_un_vuelo_a_la_cartilla_de_otro(admin):
    r = admin.post(
        "/gestion/vuelos/subir",
        data={
            "license_id": "EVA18L",
            "file": (BytesIO(_vuelo_de("EVA18L", "h-admin-1")), "circuito.avlog.json"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Vuelo importado" in r.get_data(as_text=True)

    html = admin.get("/gestion/vuelos").get_data(as_text=True)
    assert "EVA18L" in html
    assert "circuito.avlog.json" in html
    # Y también cuenta en las estadísticas de la aerolínea.
    assert estadisticas.top_pilotos_actividad()[0]["license_id"] == "EVA18L"


def test_no_se_le_puede_atribuir_a_alguien_el_vuelo_de_otro(admin):
    """El fichero declara EVA18L; el admin intenta colgárselo a `pruebas`."""
    r = admin.post(
        "/gestion/vuelos/subir",
        data={
            "license_id": "pruebas",
            "file": (BytesIO(_vuelo_de("EVA18L", "h-admin-2")), "circuito.avlog.json"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "No se pudo subir" in r.get_data(as_text=True)
    assert estadisticas.kpis_globales()["total_vuelos"] == 0


def test_hay_que_elegir_un_piloto_dado_de_alta(admin):
    r = admin.post(
        "/gestion/vuelos/subir",
        data={
            "license_id": "NOEXISTE",
            "file": (BytesIO(_vuelo_de("NOEXISTE", "h-admin-3")), "circuito.avlog.json"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Elige un piloto dado de alta" in r.get_data(as_text=True)


# -- borrar cualquiera -------------------------------------------------------


def test_el_admin_borra_el_vuelo_de_cualquier_piloto(admin):
    admin.post(
        "/gestion/vuelos/subir",
        data={
            "license_id": "EVA18L",
            "file": (BytesIO(_vuelo_de("EVA18L", "h-admin-4")), "borrame.avlog.json"),
        },
        content_type="multipart/form-data",
    )
    assert estadisticas.kpis_globales()["total_vuelos"] == 1

    r = admin.post("/gestion/vuelos/borrame.avlog.json/borrar", follow_redirects=True)
    assert "borrado" in r.get_data(as_text=True)

    html = admin.get("/gestion/vuelos").get_data(as_text=True)
    assert "borrame.avlog.json" not in html
    # No solo desaparece de la lista: las estadísticas también se limpian.
    assert estadisticas.kpis_globales()["total_vuelos"] == 0


def test_borrar_libera_la_huella_y_se_puede_volver_a_subir(admin):
    admin.post(
        "/gestion/vuelos/subir",
        data={
            "license_id": "EVA18L",
            "file": (BytesIO(_vuelo_de("EVA18L", "h-admin-5")), "reintento.avlog.json"),
        },
        content_type="multipart/form-data",
    )
    admin.post("/gestion/vuelos/reintento.avlog.json/borrar")

    r = admin.post(
        "/gestion/vuelos/subir",
        data={
            "license_id": "EVA18L",
            "file": (BytesIO(_vuelo_de("EVA18L", "h-admin-5")), "reintento.avlog.json"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Vuelo importado" in r.get_data(as_text=True)


def test_borrar_algo_que_no_existe_no_revienta(admin):
    r = admin.post("/gestion/vuelos/fantasma.avlog.json/borrar", follow_redirects=True)
    assert r.status_code == 200
    assert "no existe" in r.get_data(as_text=True)


def test_no_se_puede_borrar_saliendo_de_la_carpeta(admin):
    """Un nombre con `../` no llega ni a mi vista: Flask lo normaliza y da 404
    antes de resolver la ruta, o cae en `_find_by_name` y no encuentra nada
    real que borrar. Cualquiera de las dos formas, nada fuera de sitio."""
    r = admin.post("/gestion/vuelos/..%2f..%2fetc%2fpasswd/borrar")
    assert r.status_code in (302, 404)
