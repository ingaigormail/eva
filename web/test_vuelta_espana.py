"""La Vuelta a España: la página, el progreso y el aviso en la ficha de vuelo.

No hay orden obligatorio: cualquier etapa cuenta en cuanto se sube el vuelo
que la cubre, sin necesidad de haber hecho la anterior.
"""
import json
import sys
from io import BytesIO
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

from app import app  # noqa: E402
from avcars import cuentas  # noqa: E402


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_SMTP_MODO", "memoria")
    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    cuentas.crear_cuenta("EVA18L", "clave", "eva18l@ejemplo.com")

    import importar_vuelta_espana

    importar_vuelta_espana.importar(dst=cuentas.DB_PATH)

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    yield
    cuentas.configurar_almacen(original)


@pytest.fixture
def piloto():
    cliente = app.test_client()
    cliente.post("/login", data={"user_id": "EVA18L", "password": "clave"})
    return cliente


@pytest.fixture
def cartilla_aislada(tmp_path, monkeypatch):
    """Subidas contra carpetas de usar y tirar.

    Sin esto, cada ejecución deja ficheros en la carpeta de grabaciones real
    del piloto y anota el vuelo en el registro de importados de verdad: la
    segunda vez que se corre el test, ese mismo vuelo ya está «importado» y
    la subida falla con 409, aunque la base de datos sea otra. Mismo fixture
    que en test_app.py — el registro de duplicados vive fuera de `cuentas`.
    """
    import app as app_module
    import importacion

    hogar = tmp_path / "hogar"
    grabaciones = hogar / "EvA" / "grabaciones"
    grabaciones.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: hogar))
    # SEARCH_DIRS se calcula una sola vez, al importar app.py, con el
    # Path.home() real de ese momento — parchear Path.home aquí no lo toca
    # retroactivamente. Sin esto, `_importar_vuelo` guarda en el hogar falso
    # pero las rutas que buscan el fichero (`/registro/<nombre>`) siguen
    # mirando el hogar real, y dan 404.
    monkeypatch.setattr(app_module, "SEARCH_DIRS", [grabaciones])
    monkeypatch.setattr(importacion, "REGISTRO_PATH", tmp_path / "importados.json")
    return hogar / "EvA" / "grabaciones"


def _fixture_avlog(origen: str, destino: str, huella: str) -> bytes:
    ruta = (
        WEB_DIR.parent / "client" / "tests" / "fixtures"
        / "2026-08-16_21-59-00_WVN89 9.avlog.json"
    )
    doc = json.loads(ruta.read_text(encoding="utf-8"))
    doc["pilot"] = {"license_id": "EVA18L", "callsign": "VAE"}
    doc["flight_plan"]["departure_icao"] = origen
    doc["flight_plan"]["arrival_icao"] = destino
    doc["integrity"] = {"hash_algorithm": "sha256", "track_hash": huella}
    # El fixture real aterriza en Barcelona: sin esto, la comprobación de
    # "vuelo completo" (importacion.vuelo_llego_a_destino) rechazaría este
    # vuelo sintético por no coincidir con el destino que se declara aquí.
    from app import AIRPORTS

    aeropuerto = AIRPORTS.get(destino.upper())
    if aeropuerto and doc.get("track"):
        doc["track"][-1]["lat"] = aeropuerto["lat"]
        doc["track"][-1]["lon"] = aeropuerto["lon"]
        doc["track"][-1]["on_ground"] = True
    return json.dumps(doc).encode("utf-8")


def test_sin_sesion_no_se_ve(monkeypatch):
    respuesta = app.test_client().get("/vuelta-espana")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


def test_las_21_etapas_salen_pendientes_al_principio(piloto):
    html = piloto.get("/vuelta-espana").get_data(as_text=True)
    assert "0<span" in html or "0 " in html  # 0 completadas
    assert html.count("pendiente</span>") == 21
    assert "LXGB" in html and "LEMG" in html  # etapa 1
    assert "1.900" in html.replace(",", ".").replace(" ", "") or "1900" in html


def test_subir_una_etapa_la_marca_hecha_en_la_pagina(piloto, cartilla_aislada):
    piloto.post(
        "/api/registro/upload",
        data={"file": (BytesIO(_fixture_avlog("LXGB", "LEMG", "h-vae-1")), "e1.avlog.json")},
        content_type="multipart/form-data",
    )
    html = piloto.get("/vuelta-espana").get_data(as_text=True)
    assert html.count("hecha</span>") == 1
    assert html.count("pendiente</span>") == 20


def test_una_etapa_cualquiera_cuenta_sin_haber_hecho_las_anteriores(piloto, cartilla_aislada):
    """Orden libre: la etapa 15 vale aunque no se hayan volado la 1-14."""
    piloto.post(
        "/api/registro/upload",
        data={"file": (BytesIO(_fixture_avlog("LECO", "LEVX", "h-vae-15")), "e15.avlog.json")},
        content_type="multipart/form-data",
    )
    html = piloto.get("/vuelta-espana").get_data(as_text=True)
    assert html.count("hecha</span>") == 1


def test_la_ficha_del_vuelo_avisa_si_cuenta_para_la_vuelta(piloto, cartilla_aislada):
    piloto.post(
        "/api/registro/upload",
        data={"file": (BytesIO(_fixture_avlog("LXGB", "LEMG", "h-vae-2")), "e2.avlog.json")},
        content_type="multipart/form-data",
    )
    html = piloto.get("/registro/e2.avlog.json").get_data(as_text=True)
    assert "Cuenta para la" in html
    assert "Etapa 1 de 21" in html


def test_un_vuelo_que_no_es_ninguna_etapa_no_avisa_de_nada(piloto, cartilla_aislada):
    piloto.post(
        "/api/registro/upload",
        data={"file": (BytesIO(_fixture_avlog("LEMD", "LEBL", "h-vae-3")), "e3.avlog.json")},
        content_type="multipart/form-data",
    )
    html = piloto.get("/registro/e3.avlog.json").get_data(as_text=True)
    assert "Cuenta para la" not in html


def test_completar_todas_las_etapas_se_celebra(piloto):
    import importar_vuelta_espana

    with cuentas.conexion() as con:
        for i, (o, d) in enumerate(
            [(e[1], e[2]) for e in importar_vuelta_espana.ETAPAS], start=1
        ):
            ruta = con.execute(
                "SELECT id FROM rutas_vfr WHERE origin_icao=? AND destination_icao=?",
                (o, d),
            ).fetchone()
            con.execute(
                """INSERT INTO progreso_rutas
                   (license_id, ruta_id, estado, vuelo_huella, completada_en)
                   VALUES ('EVA18L', ?, 'completada', ?, datetime('now'))""",
                (ruta["id"], f"h-completa-{i}"),
            )

    html = piloto.get("/vuelta-espana").get_data(as_text=True)
    assert "Vuelta completada" in html
    assert html.count("hecha</span>") == 21


def test_menu_lleva_a_la_vuelta(piloto):
    html = piloto.get("/vuelos").get_data(as_text=True)
    assert 'href="/vuelta-espana"' in html
