"""El transporte de correo. Ningún test abre una conexión de verdad.

Lo que se prueba aquí es lo que costó una tarde averiguar: que EvA **no diga
que envió** lo que el proveedor rechazó. Por SMTP eso era imposible de saber
(un `250 OK` con la cuenta bloqueada); por la API, el motivo viene escrito.
"""
import io
import json
import urllib.error

import pytest

from avcars import correo


@pytest.fixture
def config_mailjet(tmp_path, monkeypatch):
    """Configuración completa apuntando a Mailjet, sin modo memoria."""
    from avcars import cuentas

    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    (tmp_path / "correo.json").write_text(
        json.dumps(
            {
                "host": "in-v3.mailjet.com",
                "puerto": 587,
                "usuario": "clave-publica",
                "password": "clave-secreta",
                "remitente": "eva@ejemplo.com",
                "gestion": "gestion@ejemplo.com",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("EVA_SMTP_MODO", raising=False)
    yield
    cuentas.configurar_almacen(original)


def _respuesta(payload: dict):
    return io.BytesIO(json.dumps(payload).encode())


def test_con_mailjet_se_usa_la_api_no_el_smtp(config_mailjet):
    assert correo.configuracion().transporte == correo.TRANSPORTE_API


def test_con_otro_proveedor_se_sigue_usando_smtp(tmp_path, monkeypatch):
    from avcars import cuentas

    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    try:
        monkeypatch.setenv("EVA_SMTP_HOST", "smtp.midominio.com")
        assert correo.configuracion().transporte == correo.TRANSPORTE_SMTP
    finally:
        cuentas.configurar_almacen(original)


def test_se_puede_forzar_el_smtp_aunque_sea_mailjet(config_mailjet, monkeypatch):
    monkeypatch.setenv("EVA_CORREO_TRANSPORTE", "smtp")
    assert correo.configuracion().transporte == correo.TRANSPORTE_SMTP


def test_valen_los_nombres_de_variable_de_la_documentacion_de_mailjet(
    tmp_path, monkeypatch
):
    """Sus ejemplos usan MJ_APIKEY_PUBLIC / MJ_APIKEY_PRIVATE."""
    from avcars import cuentas

    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    try:
        monkeypatch.setenv("EVA_SMTP_HOST", "in-v3.mailjet.com")
        monkeypatch.setenv("MJ_APIKEY_PUBLIC", "publica-de-mailjet")
        monkeypatch.setenv("MJ_APIKEY_PRIVATE", "privada-de-mailjet")

        cfg = correo.configuracion()
        assert cfg.usuario == "publica-de-mailjet"
        assert cfg.password == "privada-de-mailjet"
    finally:
        cuentas.configurar_almacen(original)


def test_un_envio_aceptado_no_lanza_nada(config_mailjet, monkeypatch):
    enviado = {}

    def falso_urlopen(peticion, timeout=None):
        enviado["url"] = peticion.full_url
        enviado["cuerpo"] = json.loads(peticion.data)
        enviado["auth"] = peticion.headers.get("Authorization", "")
        return _respuesta(
            {"Messages": [{"Status": "success", "To": [{"MessageID": 1}]}]}
        )

    monkeypatch.setattr(correo.urllib.request, "urlopen", falso_urlopen)
    correo.enviar("piloto@ejemplo.com", "Asunto", "Cuerpo")

    assert enviado["url"] == correo.API_URL_POR_DEFECTO
    mensaje = enviado["cuerpo"]["Messages"][0]
    assert mensaje["From"]["Email"] == "eva@ejemplo.com"
    assert mensaje["To"][0]["Email"] == "piloto@ejemplo.com"
    assert mensaje["Subject"] == "Asunto"
    assert enviado["auth"].startswith("Basic ")


def test_la_cuenta_bloqueada_ya_no_pasa_por_envio_correcto(config_mailjet, monkeypatch):
    """El caso real del 2026-08-18: por SMTP era un `250 OK` silencioso."""
    def falso_urlopen(peticion, timeout=None):
        raise urllib.error.HTTPError(
            peticion.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(
                json.dumps(
                    {
                        "ErrorCode": "mj-0001",
                        "StatusCode": 401,
                        "ErrorMessage": "Your account has been temporarily blocked.",
                    }
                ).encode()
            ),
        )

    monkeypatch.setattr(correo.urllib.request, "urlopen", falso_urlopen)

    with pytest.raises(correo.CorreoNoEnviado) as fallo:
        correo.enviar("piloto@ejemplo.com", "Asunto", "Cuerpo")
    assert "temporarily blocked" in str(fallo.value)
    assert "mj-0001" in str(fallo.value)


def test_un_error_por_mensaje_tambien_se_cuenta(config_mailjet, monkeypatch):
    def falso_urlopen(peticion, timeout=None):
        return _respuesta(
            {
                "Messages": [
                    {
                        "Status": "error",
                        "Errors": [
                            {
                                "ErrorCode": "mj-0013",
                                "ErrorMessage": '"piloto" is an invalid email address.',
                                "ErrorRelatedTo": ["To[0].Email"],
                            }
                        ],
                    }
                ]
            }
        )

    monkeypatch.setattr(correo.urllib.request, "urlopen", falso_urlopen)

    with pytest.raises(correo.CorreoNoEnviado) as fallo:
        correo.enviar("piloto", "Asunto", "Cuerpo")
    assert "invalid email address" in str(fallo.value)
    assert "To[0].Email" in str(fallo.value)


def test_un_certificado_interceptado_se_explica(config_mailjet, monkeypatch):
    """Lo de Norton: el mensaje tiene que orientar, no soltar un volcado."""
    import ssl

    def falso_urlopen(peticion, timeout=None):
        raise ssl.SSLError("CERTIFICATE_VERIFY_FAILED")

    monkeypatch.setattr(correo.urllib.request, "urlopen", falso_urlopen)

    with pytest.raises(correo.CorreoNoEnviado) as fallo:
        correo.enviar("piloto@ejemplo.com", "Asunto", "Cuerpo")
    assert "antivirus" in str(fallo.value).lower()


def test_una_respuesta_rara_no_se_toma_por_buena(config_mailjet, monkeypatch):
    def falso_urlopen(peticion, timeout=None):
        return io.BytesIO(b"<html>vaya</html>")

    monkeypatch.setattr(correo.urllib.request, "urlopen", falso_urlopen)

    with pytest.raises(correo.CorreoNoEnviado):
        correo.enviar("piloto@ejemplo.com", "Asunto", "Cuerpo")


def test_el_modo_memoria_sigue_sin_tocar_la_red(config_mailjet, monkeypatch):
    monkeypatch.setenv("EVA_SMTP_MODO", "memoria")
    correo.BANDEJA.clear()

    def no_se_llama(*_a, **_k):
        raise AssertionError("no debería salir a la red en modo memoria")

    monkeypatch.setattr(correo.urllib.request, "urlopen", no_se_llama)
    correo.enviar("piloto@ejemplo.com", "Asunto", "Cuerpo")

    assert len(correo.BANDEJA) == 1
    correo.BANDEJA.clear()


# -- Transporte de Gmail --------------------------------------------------
#
# Existe porque Render bloquea los puertos de SMTP en su plan gratuito: por
# ahí no se puede enviar por mucho que la contraseña sea correcta.


@pytest.fixture
def config_gmail(tmp_path, monkeypatch):
    """Credenciales de la API de Gmail, sin modo memoria."""
    from avcars import cuentas

    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    (tmp_path / "correo.json").write_text(
        json.dumps(
            {
                "transporte": "gmail",
                "usuario": "id-de-cliente.apps.googleusercontent.com",
                "password": "secreto-de-cliente",
                "refresh_token": "testigo-de-refresco",
                "remitente": "eva@ejemplo.com",
                "gestion": "gestion@ejemplo.com",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("EVA_SMTP_MODO", raising=False)
    yield
    cuentas.configurar_almacen(original)


def test_se_elige_el_transporte_de_gmail(config_gmail):
    assert correo.configuracion().transporte == correo.TRANSPORTE_GMAIL


def test_gmail_esta_configurado_sin_host_ni_puerto(config_gmail):
    """No hay servidor al que conectarse: basta el permiso de la cuenta."""
    assert correo.configurado() is True


def test_sin_testigo_de_refresco_no_se_da_por_configurado(config_gmail, monkeypatch):
    monkeypatch.setenv("EVA_GMAIL_REFRESH_TOKEN", " ")
    monkeypatch.setenv("EVA_CORREO_TRANSPORTE", "gmail")
    # El fichero lo trae, así que se fuerza el caso quitándolo del todo.
    monkeypatch.setattr(
        correo, "_del_fichero", lambda: {"transporte": "gmail", "usuario": "u",
                                         "password": "p", "remitente": "e@e.com"}
    )
    assert correo.configurado() is False


def test_un_envio_por_gmail_pide_permiso_y_manda_el_mensaje(config_gmail, monkeypatch):
    llamadas = []

    def falso_urlopen(peticion, timeout=None):
        llamadas.append(peticion)
        if peticion.full_url == correo.GMAIL_TOKEN_URL:
            return _respuesta({"access_token": "permiso-temporal"})
        return _respuesta({"id": "18f3a"})

    monkeypatch.setattr(correo.urllib.request, "urlopen", falso_urlopen)
    # Con acentos y «ñ» a propósito: son los bytes que, al codificar, sacan
    # los caracteres «+» y «/» que distinguen base64url del base64 normal.
    # Con un cuerpo soso los dos dan lo mismo y el test no probaría nada.
    correo.enviar("piloto@ejemplo.com", "Aviación", "Añadido: ¿qué tal? ñáéíóú" * 8)

    assert [p.full_url for p in llamadas] == [correo.GMAIL_TOKEN_URL, correo.GMAIL_URL]

    envio = llamadas[1]
    assert envio.headers["Authorization"] == "Bearer permiso-temporal"

    # El mensaje viaja en base64url dentro de «raw», tal como pide la API.
    import base64

    crudo = json.loads(envio.data.decode())["raw"]

    # La API **exige** base64url: con «+» o «/» dentro, rechaza el mensaje.
    assert "+" not in crudo and "/" not in crudo, "tiene que ser base64url"
    # Y que no sea base64url por casualidad: el normal aquí sí los mete.
    normal = base64.b64encode(base64.urlsafe_b64decode(crudo)).decode()
    assert "+" in normal or "/" in normal, "el cuerpo no distingue los dos"

    descifrado = base64.urlsafe_b64decode(crudo).decode()
    assert "piloto@ejemplo.com" in descifrado


def test_si_google_retira_el_permiso_se_dice_por_que(config_gmail, monkeypatch):
    """`invalid_grant` = alguien revocó el acceso. Hay que verlo escrito.

    Solo falla la petición del permiso; la del envío contestaría que sí. Así,
    si algún día el código se tragara este error y siguiera adelante, el test
    lo cazaría en vez de aprobarlo por el fallo de la llamada siguiente.
    """
    intentos = []

    def falso_urlopen(peticion, timeout=None):
        intentos.append(peticion.full_url)
        if peticion.full_url == correo.GMAIL_TOKEN_URL:
            raise urllib.error.HTTPError(
                peticion.full_url,
                400,
                "Bad Request",
                {},
                io.BytesIO(
                    json.dumps(
                        {
                            "error": "invalid_grant",
                            "error_description": "Token has been expired or revoked.",
                        }
                    ).encode()
                ),
            )
        return _respuesta({"id": "18f3a"})

    monkeypatch.setattr(correo.urllib.request, "urlopen", falso_urlopen)

    with pytest.raises(correo.CorreoNoEnviado) as fallo:
        correo.enviar("piloto@ejemplo.com", "Asunto", "Cuerpo")

    assert "revoked" in str(fallo.value)
    # Sin permiso no se intenta mandar nada: sería un envío condenado.
    assert correo.GMAIL_URL not in intentos


def test_si_gmail_rechaza_el_envio_se_dice_por_que(config_gmail, monkeypatch):
    def falso_urlopen(peticion, timeout=None):
        if peticion.full_url == correo.GMAIL_TOKEN_URL:
            return _respuesta({"access_token": "permiso-temporal"})
        raise urllib.error.HTTPError(
            peticion.full_url,
            403,
            "Forbidden",
            {},
            io.BytesIO(
                json.dumps(
                    {"error": {"message": "Gmail API has not been used in project"}}
                ).encode()
            ),
        )

    monkeypatch.setattr(correo.urllib.request, "urlopen", falso_urlopen)

    with pytest.raises(correo.CorreoNoEnviado) as fallo:
        correo.enviar("piloto@ejemplo.com", "Asunto", "Cuerpo")
    assert "has not been used" in str(fallo.value)


def test_gmail_en_modo_memoria_no_toca_la_red(config_gmail, monkeypatch):
    monkeypatch.setenv("EVA_SMTP_MODO", "memoria")
    correo.BANDEJA.clear()

    def no_se_llama(*_a, **_k):
        raise AssertionError("no debería salir a la red en modo memoria")

    monkeypatch.setattr(correo.urllib.request, "urlopen", no_se_llama)
    correo.enviar("piloto@ejemplo.com", "Asunto", "Cuerpo")

    assert len(correo.BANDEJA) == 1
    correo.BANDEJA.clear()


def test_el_error_de_certificado_se_reconoce_aunque_venga_envuelto(
    config_gmail, monkeypatch
):
    """`urlopen` mete el SSLError dentro de un URLError, en `.reason`.

    Un `except ssl.SSLError` alrededor de `urlopen` no salta nunca. Se coló
    justo así el 2026-08-21: el aviso del antivirus estaba escrito, pero el
    usuario veía un «no se pudo hablar con Google» que no decía nada.
    """
    import ssl

    def falso_urlopen(peticion, timeout=None):
        raise urllib.error.URLError(
            ssl.SSLCertVerificationError(
                1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
            )
        )

    monkeypatch.setattr(correo.urllib.request, "urlopen", falso_urlopen)

    with pytest.raises(correo.CorreoNoEnviado) as fallo:
        correo.enviar("piloto@ejemplo.com", "Asunto", "Cuerpo")
    assert "antivirus" in str(fallo.value).lower()
