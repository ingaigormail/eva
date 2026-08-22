"""La página desde la que los pilotos se bajan EvA Airliner.

Lo que importa aquí es que un piloto que llega sin saber nada acabe con el
programa instalado: que encuentre el enlace, sepa que Windows le va a
avisar, y sepa a dónde volver con el fichero del vuelo.
"""
import sys
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
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    yield
    cuentas.configurar_almacen(original)


@pytest.fixture
def piloto():
    cliente = app.test_client()
    cliente.post("/login", data={"user_id": "EVA18L", "password": "clave"})
    return cliente


def test_sin_sesion_no_se_ve(monkeypatch):
    """Es para pilotos dados de alta, no para cualquiera que pase."""
    respuesta = app.test_client().get("/descargar")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


def test_el_piloto_encuentra_el_enlace(piloto):
    html = piloto.get("/descargar").get_data(as_text=True)
    assert "releases/latest/download/setup.exe" in html


def test_se_avisa_de_lo_que_dira_windows(piloto):
    """Sin este aviso, el piloto cree que le estamos colando un virus.

    Al no estar firmado el ejecutable, Windows suelta «Windows protegió su
    PC». Quien no lo espera, cancela y no instala nada.
    """
    html = piloto.get("/descargar").get_data(as_text=True).lower()
    assert "protegió su pc" in html
    assert "ejecutar de todas formas" in html


def test_dice_que_el_simulador_va_primero(piloto):
    """El orden importa: EvA Airliner no engancha si el sim no está abierto."""
    html = piloto.get("/descargar").get_data(as_text=True).lower()
    assert "abre primero el simulador" in html


def test_lleva_de_vuelta_a_registro_para_subir_el_vuelo(piloto):
    """Grabar sin subir no sirve de nada: hay que cerrar el círculo."""
    html = piloto.get("/descargar").get_data(as_text=True)
    assert 'href="/registro"' in html


def test_el_menu_lleva_a_la_descarga(piloto):
    """El botón VUELO estaba apagado en el servidor; ahora lleva aquí."""
    html = piloto.get("/vuelos").get_data(as_text=True)
    assert 'href="/descargar"' in html


def test_el_enlace_se_puede_cambiar_sin_tocar_codigo(monkeypatch, piloto):
    """El día que la descarga se mueva, se cambia una variable y ya."""
    import app as modulo

    monkeypatch.setattr(modulo, "DESCARGA_URL", "https://otro.sitio/eva.exe")
    html = piloto.get("/descargar").get_data(as_text=True)
    assert "https://otro.sitio/eva.exe" in html
