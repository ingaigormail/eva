"""La puerta que usa EvA Airliner para leer el plan del piloto.

El grabador no tiene sesión de navegador: entra una vez con las credenciales
del piloto y se queda con una clave de solo lectura. Lo que se prueba aquí es
sobre todo que esa clave **no vale para más de lo que debe**.

    python -m pytest web/test_grabador_api.py
"""
import sys
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

from app import app  # noqa: E402
from avcars import cuentas, planes, sesion_web  # noqa: E402


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_SMTP_MODO", "memoria")
    monkeypatch.setattr(sesion_web, "SESION_PATH", tmp_path / "sesion_activa.json")

    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    cuentas.crear_cuenta("EVA18L", "clave-buena", "eva18l@ejemplo.com")

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    yield
    cuentas.configurar_almacen(original)


@pytest.fixture
def cliente():
    return app.test_client()


def _entrar(cliente, license_id="EVA18L", password="clave-buena"):
    return cliente.post(
        "/api/grabador/login",
        json={"license_id": license_id, "password": password},
    )


# -- Entrar ---------------------------------------------------------------


def test_entrar_devuelve_una_clave_y_no_la_contrasena(cliente):
    r = _entrar(cliente)
    assert r.status_code == 200
    datos = r.get_json()
    assert datos["ok"] is True
    assert datos["license_id"] == "EVA18L"
    assert datos["clave"]
    # Lo que se devuelve no puede ser la contraseña ni derivar de ella.
    assert "clave-buena" not in str(datos)


def test_la_contrasena_no_queda_guardada_en_claro(cliente):
    """Solo se guarda la huella: la clave entera se enseña una vez y ya."""
    clave = _entrar(cliente).get_json()["clave"]
    with cuentas.conexion() as con:
        fila = con.execute(
            "SELECT clave_grabador FROM usuarios WHERE license_id = ?", ("EVA18L",)
        ).fetchone()
    assert fila["clave_grabador"]
    assert fila["clave_grabador"] != clave


def test_credenciales_malas_no_dan_clave(cliente):
    r = _entrar(cliente, password="me-la-invento")
    assert r.status_code == 401
    assert "clave" not in r.get_json()


def test_un_piloto_que_no_existe_da_el_mismo_error(cliente):
    """Mismo mensaje: probando IDs no se averigua quién está dado de alta."""
    desconocido = _entrar(cliente, license_id="FANTASMA").get_json()
    malo = _entrar(cliente, password="no").get_json()
    assert desconocido["mensaje"] == malo["mensaje"]


def test_una_cuenta_bloqueada_no_puede_entrar(cliente):
    cuentas.cambiar_estado("EVA18L", cuentas.ESTADO_BLOQUEADA)
    assert _entrar(cliente).status_code == 401


# -- Leer el plan ---------------------------------------------------------


def test_devuelve_el_ultimo_plan_del_piloto(cliente):
    planes.guardar("EVA18L", {"departure": "LEMD", "arrival": "LEIB"})
    planes.guardar(
        "EVA18L",
        {"departure": "LEVC", "arrival": "LECH", "cruise_alt_ft": 4500,
         "rules": "VFR"},
    )
    clave = _entrar(cliente).get_json()["clave"]

    r = cliente.get("/api/grabador/plan", headers={"X-EvA-Clave": clave})
    assert r.status_code == 200
    plan = r.get_json()["plan"]
    assert plan["origen"] == "LEVC"      # el último, no el primero
    assert plan["destino"] == "LECH"
    assert plan["nivel"] == 4500
    assert plan["reglas"] == "VFR"


def test_sin_planes_guardados_no_se_inventa_ninguno(cliente):
    clave = _entrar(cliente).get_json()["clave"]
    r = cliente.get("/api/grabador/plan", headers={"X-EvA-Clave": clave})
    assert r.status_code == 200
    assert r.get_json()["plan"] is None


def test_sin_clave_no_se_lee_nada(cliente):
    planes.guardar("EVA18L", {"departure": "LEMD", "arrival": "LEIB"})
    assert cliente.get("/api/grabador/plan").status_code == 401
    r = cliente.get("/api/grabador/plan", headers={"X-EvA-Clave": "inventada"})
    assert r.status_code == 401


def test_la_clave_de_un_piloto_no_abre_el_plan_de_otro(cliente):
    """Lo importante: la clave es de quien es, y solo ve lo suyo."""
    cuentas.crear_cuenta("EVA99Z", "otra-clave", "otro@ejemplo.com")
    planes.guardar("EVA99Z", {"departure": "LEBL", "arrival": "LEZL"})
    planes.guardar("EVA18L", {"departure": "LEVC", "arrival": "LECH"})

    clave_18l = _entrar(cliente).get_json()["clave"]
    plan = cliente.get(
        "/api/grabador/plan", headers={"X-EvA-Clave": clave_18l}
    ).get_json()["plan"]
    assert plan["origen"] == "LEVC"      # el suyo
    assert plan["origen"] != "LEBL"      # nunca el del otro


def test_generar_una_clave_nueva_anula_la_anterior(cliente):
    """Es la forma de revocarla si se le escapó a alguien."""
    vieja = _entrar(cliente).get_json()["clave"]
    nueva = _entrar(cliente).get_json()["clave"]
    assert vieja != nueva

    assert cliente.get(
        "/api/grabador/plan", headers={"X-EvA-Clave": vieja}
    ).status_code == 401
    assert cliente.get(
        "/api/grabador/plan", headers={"X-EvA-Clave": nueva}
    ).status_code == 200


def test_bloquear_al_piloto_deja_su_clave_sin_efecto(cliente):
    """Cerrarle la web tiene que cerrarle también el grabador."""
    clave = _entrar(cliente).get_json()["clave"]
    cuentas.cambiar_estado("EVA18L", cuentas.ESTADO_BLOQUEADA)
    r = cliente.get("/api/grabador/plan", headers={"X-EvA-Clave": clave})
    assert r.status_code == 401


def test_la_clave_no_sirve_para_entrar_en_la_web(cliente):
    """Solo abre el plan: no es un pase de sesión."""
    clave = _entrar(cliente).get_json()["clave"]
    for ruta in ("/vuelos", "/plan", "/gestion/usuarios"):
        r = cliente.get(ruta, headers={"X-EvA-Clave": clave})
        assert r.status_code == 302, ruta
        assert "/login" in r.headers.get("Location", ""), ruta
