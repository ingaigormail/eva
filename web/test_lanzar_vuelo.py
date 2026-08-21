"""El icono VUELO abre EVA Airliner, y solo cuando es seguro hacerlo.

    python -m pytest web/test_lanzar_vuelo.py

Una ruta que arranca procesos es lo más peligroso que puede tener un servidor
público, así que lo que más se prueba aquí es **cuándo se niega**.
"""
import sys
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

import app as app_module  # noqa: E402
from app import app  # noqa: E402
from avcars import cuentas, sesion_web  # noqa: E402


class PopenFalso:
    def __init__(self, cmd, cwd=None):
        self.cmd = cmd
        self.cwd = cwd
        self.vivo = True

    def poll(self):
        return None if self.vivo else 0


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(sesion_web, "SESION_PATH", tmp_path / "sesion_activa.json")
    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    cuentas.crear_cuenta("EvA18L", "clave", "uno@ejemplo.com")
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app_module._grabador = None
    yield
    app_module._grabador = None
    cuentas.configurar_almacen(original)


@pytest.fixture
def lanzados(monkeypatch):
    hechos = []

    def falso(cmd, cwd=None):
        hechos.append((cmd, cwd))
        return PopenFalso(cmd, cwd)

    monkeypatch.setattr(app_module.subprocess, "Popen", falso)
    return hechos


@pytest.fixture
def permitido(monkeypatch):
    """En local y en modo desarrollo: el caso del PC del piloto."""
    monkeypatch.setenv("EVA_LANZAR_LOCAL", "1")


def _cliente():
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "EvA18L"
    return c


def test_en_local_lanza_eva_airliner(permitido, lanzados):
    r = _cliente().post("/api/vuelo/lanzar")

    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert len(lanzados) == 1
    cmd, cwd = lanzados[0]
    assert cmd == [sys.executable, "-m", "client.avcars.gui"]
    assert (Path(cwd) / "client" / "avcars" / "gui.py").exists()


def test_no_se_abren_dos_grabadores(permitido, lanzados):
    c = _cliente()
    c.post("/api/vuelo/lanzar")
    r = c.post("/api/vuelo/lanzar")

    assert r.status_code == 409
    assert "ya está abierto" in r.get_json()["mensaje"]
    assert len(lanzados) == 1


def test_si_se_cerro_se_puede_volver_a_lanzar(permitido, lanzados):
    c = _cliente()
    c.post("/api/vuelo/lanzar")
    app_module._grabador.vivo = False
    c.post("/api/vuelo/lanzar")

    assert len(lanzados) == 2


def test_desde_fuera_de_la_maquina_se_niega(permitido, lanzados):
    """Aunque esté permitido, si no viene de local no se arranca nada."""
    c = _cliente()
    r = c.post("/api/vuelo/lanzar", environ_base={"REMOTE_ADDR": "192.168.1.50"})

    assert r.status_code == 403
    assert lanzados == []


def test_sin_permiso_explicito_ni_modo_desarrollo_se_niega(monkeypatch, lanzados):
    monkeypatch.delenv("EVA_LANZAR_LOCAL", raising=False)
    monkeypatch.setattr(app, "debug", False)

    r = _cliente().post("/api/vuelo/lanzar")

    assert r.status_code == 403
    assert "desde el escritorio" in r.get_json()["mensaje"]
    assert lanzados == []


def test_se_puede_apagar_a_mano_aunque_sea_local(monkeypatch, lanzados):
    """`EVA_LANZAR_LOCAL=0` manda sobre el modo desarrollo."""
    monkeypatch.setenv("EVA_LANZAR_LOCAL", "0")
    monkeypatch.setattr(app, "debug", True)

    assert _cliente().post("/api/vuelo/lanzar").status_code == 403
    assert lanzados == []


def test_sin_sesion_no_se_lanza_nada(permitido, lanzados):
    r = app.test_client().post("/api/vuelo/lanzar")

    assert r.status_code == 302  # al login
    assert lanzados == []


def test_el_icono_solo_sale_cuando_se_puede(permitido, monkeypatch):
    html = _cliente().get("/").get_data(as_text=True)
    assert 'id="lanzar-vuelo"' in html

    monkeypatch.setenv("EVA_LANZAR_LOCAL", "0")
    html = _cliente().get("/").get_data(as_text=True)
    assert 'id="lanzar-vuelo"' not in html
    assert "se abre desde el escritorio" in html
