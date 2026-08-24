"""Alta por solicitud y recuperación de contraseña, desde la web.

Se ejecutan con:

    python -m pytest web/test_cuentas_web.py

Ningún test abre una conexión SMTP: `EVA_SMTP_MODO=memoria` deja los correos
en `correo.BANDEJA`.
"""
import re
import sys
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

from app import app  # noqa: E402
from avcars import correo, cuentas, restablecer, sesion_web, solicitudes  # noqa: E402


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    """Almacén de cuentas y buzón aislados: el repo no se toca."""
    monkeypatch.setenv("EVA_SMTP_MODO", "memoria")
    monkeypatch.setenv("EVA_CORREO_GESTION", "gestion@eva.test")
    monkeypatch.setattr(sesion_web, "SESION_PATH", tmp_path / "sesion_activa.json")

    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    cuentas.crear_cuenta("EVA18L", "vieja", "eva18l@ejemplo.com")
    correo.BANDEJA.clear()

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    yield

    correo.BANDEJA.clear()
    cuentas.configurar_almacen(original)


@pytest.fixture
def cliente():
    return app.test_client()


# -- El alta se pide, no se toma -----------------------------------------


def test_al_entrar_se_aterriza_en_la_home_de_la_aerolinea(cliente):
    """Lo primero que ve el piloto es la aerolínea, no su lista de vuelos."""
    r = cliente.post("/login", data={"user_id": "EVA18L", "password": "vieja"})

    assert r.status_code == 302
    assert "/aerolinea" in r.headers.get("Location", "")


def test_el_login_de_un_desconocido_explica_como_pedir_el_alta(cliente):
    r = cliente.post(
        "/login", data={"user_id": "NADIE", "password": "x"}, follow_redirects=True
    )
    texto = r.get_data(as_text=True)

    assert "ID de piloto o contraseña incorrectos" in texto
    assert "/solicitar-alta" in texto
    assert "no hay auto-registro" in texto


def test_la_solicitud_de_alta_llega_a_gestion_y_no_crea_la_cuenta(cliente):
    r = cliente.post(
        "/solicitar-alta",
        data={
            "license_id": "EVA777",
            "nombre": "Ana Pérez López",
            "vatsim_cid": "1234567",
            "correo": "ana@ejemplo.com",
        },
    )
    texto = r.get_data(as_text=True)

    assert r.status_code == 200
    assert "Solicitud enviada" in texto
    assert "pendiente de aprobación" in texto

    # La cuenta NO existe: sigue haciendo falta que alguien la dé de alta.
    assert not cuentas.existe_usuario("EVA777")
    assert not cuentas.autenticar("EVA777", "cualquiera")

    assert len(correo.BANDEJA) == 1
    mensaje = correo.BANDEJA[0]
    assert mensaje["para"] == "gestion@eva.test"
    assert "Solicitud de alta" in mensaje["asunto"]
    assert "EVA777" in mensaje["asunto"]
    for dato in ("EVA777", "Ana Pérez López", "1234567", "ana@ejemplo.com"):
        assert dato in mensaje["cuerpo"]
    # La fecha la pone el sistema.
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", mensaje["cuerpo"])


def test_la_solicitud_queda_guardada_en_la_tabla(cliente):
    cliente.post(
        "/solicitar-alta",
        data={
            "license_id": "EVA777",
            "nombre": "Ana Pérez López",
            "vatsim_cid": "1234567",
            "correo": "ana@ejemplo.com",
        },
    )

    pendientes = solicitudes.pendientes()
    assert len(pendientes) == 1
    assert pendientes[0]["license_id"] == "EVA777"
    assert pendientes[0]["nombre"] == "Ana Pérez López"
    assert pendientes[0]["vatsim_cid"] == "1234567"


def test_si_el_correo_falla_la_solicitud_no_se_pierde(cliente, monkeypatch):
    """El motivo de tener tabla: un aviso perdido no puede perder al piloto."""
    def revienta(*_args, **_kwargs):
        raise correo.CorreoNoEnviado("el servidor no contesta")

    monkeypatch.setattr(correo, "enviar", revienta)

    r = cliente.post(
        "/solicitar-alta",
        data={
            "license_id": "EVA888",
            "nombre": "Luis Ruiz",
            "correo": "luis@ejemplo.com",
        },
    )
    texto = r.get_data(as_text=True)

    assert "Solicitud enviada" in texto
    assert "no ha salido" in texto  # se le dice la verdad al solicitante
    assert [s["license_id"] for s in solicitudes.pendientes()] == ["EVA888"]
    assert not cuentas.existe_usuario("EVA888")


def test_insistir_no_llena_la_bandeja_de_copias(cliente):
    for _ in range(3):
        cliente.post(
            "/solicitar-alta",
            data={
                "license_id": "EVA777",
                "nombre": "Ana",
                "correo": "ana@ejemplo.com",
            },
        )
    assert solicitudes.cuantas_pendientes() == 1


def test_la_solicitud_valida_los_datos_minimos(cliente):
    faltan_datos = [
        {"license_id": "", "nombre": "Ana", "correo": "ana@ejemplo.com"},
        {"license_id": "EVA777", "nombre": "", "correo": "ana@ejemplo.com"},
        {"license_id": "EVA777", "nombre": "Ana", "correo": "no-es-correo"},
    ]
    for datos in faltan_datos:
        r = cliente.post("/solicitar-alta", data=datos)
        assert "Solicitud enviada" not in r.get_data(as_text=True)
    assert correo.BANDEJA == []
    assert solicitudes.cuantas_pendientes() == 0


def test_quien_ya_tiene_cuenta_no_solicita_alta_sino_contraseña(cliente):
    r = cliente.post(
        "/solicitar-alta",
        data={
            "license_id": "EVA18L",
            "nombre": "Ya Registrado",
            "correo": "otro@ejemplo.com",
        },
    )
    assert "ya está dado de alta" in r.get_data(as_text=True)
    assert correo.BANDEJA == []
    assert solicitudes.cuantas_pendientes() == 0


def test_la_pantalla_de_alta_es_publica(cliente):
    assert cliente.get("/solicitar-alta").status_code == 200
    assert cliente.get("/recuperar").status_code == 200


# -- Recuperación de contraseña ------------------------------------------


def _enlace_del_correo(cuerpo: str) -> str:
    encontrado = re.search(r"/restablecer/\S+", cuerpo)
    assert encontrado, cuerpo
    return encontrado.group(0)


def test_recuperar_manda_un_enlace_y_cambia_la_contraseña(cliente):
    r = cliente.post("/recuperar", data={"identificador": "EVA18L"})
    assert "te hemos enviado un enlace" in r.get_data(as_text=True)

    assert len(correo.BANDEJA) == 1
    mensaje = correo.BANDEJA[0]
    assert mensaje["para"] == "eva18l@ejemplo.com"
    # Nunca viaja la contraseña actual.
    assert "vieja" not in mensaje["cuerpo"]

    enlace = _enlace_del_correo(mensaje["cuerpo"])
    assert cliente.get(enlace).status_code == 200

    r = cliente.post(enlace, data={"password": "nueva123", "password2": "nueva123"})
    assert "Contraseña cambiada" in r.get_data(as_text=True)

    assert cuentas.autenticar("EVA18L", "nueva123")
    assert not cuentas.autenticar("EVA18L", "vieja")


def test_tambien_vale_el_correo_como_identificador(cliente):
    cliente.post("/recuperar", data={"identificador": "EVA18L@EJEMPLO.COM"})
    assert len(correo.BANDEJA) == 1


def test_el_enlace_no_sirve_dos_veces(cliente):
    cliente.post("/recuperar", data={"identificador": "EVA18L"})
    enlace = _enlace_del_correo(correo.BANDEJA[0]["cuerpo"])
    cliente.post(enlace, data={"password": "nueva123", "password2": "nueva123"})

    r = cliente.post(enlace, data={"password": "otra1234", "password2": "otra1234"})
    assert "ya no vale" in r.get_data(as_text=True)
    assert cuentas.autenticar("EVA18L", "nueva123")


def test_las_dos_contraseñas_tienen_que_coincidir(cliente):
    cliente.post("/recuperar", data={"identificador": "EVA18L"})
    enlace = _enlace_del_correo(correo.BANDEJA[0]["cuerpo"])

    r = cliente.post(enlace, data={"password": "nueva123", "password2": "distinta"})
    assert "no coinciden" in r.get_data(as_text=True)
    assert cuentas.autenticar("EVA18L", "vieja")


def test_pedirla_para_un_desconocido_no_dice_si_existe_ni_envia_nada(cliente):
    r = cliente.post("/recuperar", data={"identificador": "NOEXISTE"})
    assert "te hemos enviado un enlace" in r.get_data(as_text=True)
    assert correo.BANDEJA == []


def test_un_enlace_inventado_no_abre_nada(cliente):
    r = cliente.get("/restablecer/loquesea")
    assert r.status_code == 200
    assert "ya no vale" in r.get_data(as_text=True)


# -- El alta sigue sin poder tomarse por la fuerza ------------------------


def test_no_hay_endpoint_de_autoregistro(cliente):
    for ruta in ("/registrar", "/signup", "/alta"):
        assert cliente.get(ruta).status_code in (302, 404)


def test_una_cuenta_bloqueada_no_entra_ni_sigue_dentro(cliente):
    login = {"user_id": "EVA18L", "password": "vieja"}
    assert cliente.post("/login", data=login).status_code == 302  # entra

    cuentas.bloquear("EVA18L")
    # La sesión abierta deja de valer en la siguiente petición.
    assert cliente.get("/").status_code == 302

    r = cliente.post("/login", data=login)
    assert "bloqueada" in r.get_data(as_text=True).lower()
