"""Envío de correo de EvA: solicitudes de alta y recuperación de contraseña.

Solo biblioteca estándar, sin dependencias nuevas. **Nada de esto se escribe
en el código**: ni la contraseña, ni la dirección del remitente. Hay dos
sitios donde ponerlo, y el entorno manda sobre el fichero:

1. **Fichero** `web/data/correo.json` (lo cómodo en Windows). No va al repo.
   Se crea copiando `web/data/correo.ejemplo.json`.

2. **Variables de entorno**, que pisan lo anterior:

       EVA_SMTP_HOST / EVA_SMTP_PORT / EVA_SMTP_USER / EVA_SMTP_PASSWORD
       EVA_SMTP_FROM / EVA_CORREO_GESTION / EVA_CORREO_TRANSPORTE
       EVA_SMTP_MODO  ("memoria" en los tests: no abre ninguna conexión)

## Dos transportes, y por qué el de por defecto es la API

- **`api`** — la Send API v3.1 de Mailjet por HTTPS (`urllib`, stdlib).
- **`smtp`** — el relé SMTP de toda la vida (`smtplib`, stdlib).

Por defecto se usa la **API** cuando el proveedor es Mailjet. La razón la
aprendimos a base de perder una tarde (2026-08-18): con la cuenta bloqueada,
**el SMTP contestaba `250 OK` y se tragaba el mensaje**, así que EvA le habría
dicho a un piloto «te hemos enviado el enlace» sin haber enviado nada. La
misma operación por la API devuelve el motivo escrito: *«Your account has been
temporarily blocked»*. Un `250 OK` **no** es prueba de envío.

Con `"transporte": "smtp"` se vuelve al relé, que es lo que hará falta el día
que el proveedor no sea Mailjet (un servidor propio, otro relé). El resto del
código llama a `enviar()` y no sabe cuál de los dos está debajo.

El día que EvA tenga dominio propio se cambian `host`, `usuario`, `remitente`
y `gestion` en ese fichero, y no se toca una línea de código.

Regla del proyecto: **nunca fallar en silencio**. Si falta configuración,
`enviar` lanza `CorreoNoConfigurado`; si el proveedor rechaza el mensaje,
`CorreoNoEnviado` **con el motivo que dio el proveedor**.
"""
from __future__ import annotations

import base64
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

HOST_POR_DEFECTO = "smtp.gmail.com"
PUERTO_POR_DEFECTO = 587
CUENTA_POR_DEFECTO = "aviacionmsfs@gmail.com"

TRANSPORTE_API = "api"
TRANSPORTE_SMTP = "smtp"
TRANSPORTES = (TRANSPORTE_API, TRANSPORTE_SMTP)

API_URL_POR_DEFECTO = "https://api.mailjet.com/v3.1/send"

MODO_MEMORIA = "memoria"

# Modo pruebas: aquí caen los correos en vez de salir a Internet.
BANDEJA: list[dict] = []


class CorreoNoConfigurado(RuntimeError):
    """Falta configuración de SMTP; no se ha enviado nada."""


class CorreoNoEnviado(RuntimeError):
    """El servidor rechazó el mensaje o no se pudo contactar con él."""


@dataclass(frozen=True)
class Configuracion:
    host: str
    puerto: int
    usuario: str
    password: str
    remitente: str
    gestion: str
    transporte: str = TRANSPORTE_SMTP
    api_url: str = API_URL_POR_DEFECTO


def ruta_config() -> Path:
    """`web/data/correo.json`, junto al almacén de cuentas."""
    from . import cuentas  # import perezoso: cuentas no depende de correo

    return cuentas.directorio_datos() / "correo.json"


def _del_fichero() -> dict:
    path = ruta_config()
    if not path.exists():
        return {}
    try:
        datos = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _valor(fichero: dict, clave: str, variable: str, defecto: str = "") -> str:
    """Entorno primero, luego el fichero, luego el valor por defecto."""
    del_entorno = os.environ.get(variable)
    if del_entorno is not None and del_entorno.strip():
        return del_entorno.strip()
    return str(fichero.get(clave, defecto) or defecto).strip()


def configuracion() -> Configuracion:
    """Se relee en cada llamada: cambiarla no exige reiniciar el servidor."""
    fichero = _del_fichero()

    try:
        puerto = int(_valor(fichero, "puerto", "EVA_SMTP_PORT", str(PUERTO_POR_DEFECTO)))
    except ValueError:
        puerto = PUERTO_POR_DEFECTO

    # `MJ_APIKEY_PUBLIC` / `MJ_APIKEY_PRIVATE` son los nombres que usa Mailjet
    # en toda su documentación: se admiten para que sus recetas funcionen tal
    # cual. Los de EvA mandan si están puestos los dos.
    usuario = _valor(
        fichero, "usuario", "EVA_SMTP_USER", ""
    ) or os.environ.get("MJ_APIKEY_PUBLIC", "").strip() or CUENTA_POR_DEFECTO
    host = _valor(fichero, "host", "EVA_SMTP_HOST", HOST_POR_DEFECTO)

    # Con Mailjet se usa su API, que sí dice por qué falla algo. Con cualquier
    # otro proveedor no hay más remedio que SMTP.
    por_defecto = TRANSPORTE_API if "mailjet" in host.lower() else TRANSPORTE_SMTP
    transporte = _valor(
        fichero, "transporte", "EVA_CORREO_TRANSPORTE", por_defecto
    ).lower()

    return Configuracion(
        transporte=transporte if transporte in TRANSPORTES else por_defecto,
        api_url=_valor(fichero, "api_url", "EVA_CORREO_API_URL", API_URL_POR_DEFECTO),
        host=host,
        puerto=puerto,
        usuario=usuario,
        # Los espacios de dentro se respetan; la de aplicación de Google se
        # copia en cuatro grupos y vale igual con ellos que sin ellos.
        password=(
            os.environ.get("EVA_SMTP_PASSWORD")
            or str(fichero.get("password", "") or "")
            or os.environ.get("MJ_APIKEY_PRIVATE", "")
        ).strip(),
        remitente=_valor(fichero, "remitente", "EVA_SMTP_FROM", usuario),
        gestion=_valor(fichero, "gestion", "EVA_CORREO_GESTION", usuario),
    )


def modo_memoria() -> bool:
    return os.environ.get("EVA_SMTP_MODO", "").strip().lower() == MODO_MEMORIA


def configurado() -> bool:
    """¿Se puede enviar de verdad ahora mismo?"""
    if modo_memoria():
        return True
    cfg = configuracion()
    return bool(cfg.host and cfg.usuario and cfg.password and cfg.remitente)


def correo_de_gestion() -> str:
    """Dirección del responsable que recibe las solicitudes de alta."""
    return configuracion().gestion


def enviar(destinatario: str, asunto: str, cuerpo: str) -> None:
    """Envía un mensaje de texto. Lanza si no se pudo."""
    cfg = configuracion()

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = cfg.remitente or cfg.usuario
    mensaje["To"] = destinatario
    mensaje.set_content(cuerpo)

    if modo_memoria():
        BANDEJA.append(
            {
                "para": destinatario,
                "asunto": asunto,
                "cuerpo": cuerpo,
                "de": mensaje["From"],
            }
        )
        return

    if not configurado():
        raise CorreoNoConfigurado(
            "Falta la configuración de correo (EVA_SMTP_PASSWORD y compañía)."
        )

    if cfg.transporte == TRANSPORTE_API:
        _enviar_por_api(cfg, destinatario, asunto, cuerpo)
    else:
        _enviar_por_smtp(cfg, mensaje)


def _enviar_por_smtp(cfg: Configuracion, mensaje: EmailMessage) -> None:
    """El relé de toda la vida. Ojo: un `250 OK` no garantiza la entrega."""
    try:
        if cfg.puerto == 465:
            with smtplib.SMTP_SSL(cfg.host, cfg.puerto, timeout=20) as smtp:
                smtp.login(cfg.usuario, cfg.password)
                smtp.send_message(mensaje)
        else:
            with smtplib.SMTP(cfg.host, cfg.puerto, timeout=20) as smtp:
                smtp.starttls()
                smtp.login(cfg.usuario, cfg.password)
                smtp.send_message(mensaje)
    except (smtplib.SMTPException, OSError) as exc:
        raise CorreoNoEnviado(str(exc)) from exc


def _motivo_del_rechazo(respuesta: dict) -> str:
    """Saca el motivo de las dos formas en que v3.1 informa de un error.

    A nivel de cuenta viene arriba del todo (`ErrorMessage`); a nivel de
    mensaje, dentro de `Messages[].Errors[]`. Se lee con cuidado: lo que no
    puede pasar es quedarse sin explicación que enseñar.
    """
    arriba = respuesta.get("ErrorMessage")
    if arriba:
        codigo = respuesta.get("ErrorCode", "")
        return f"{arriba} ({codigo})" if codigo else str(arriba)

    motivos = []
    for m in respuesta.get("Messages", []) or []:
        if not isinstance(m, dict) or m.get("Status") == "success":
            continue
        for err in m.get("Errors", []) or []:
            if isinstance(err, dict) and err.get("ErrorMessage"):
                relativo = ", ".join(err.get("ErrorRelatedTo", []) or [])
                texto = str(err["ErrorMessage"])
                motivos.append(f"{texto} [{relativo}]" if relativo else texto)
    if motivos:
        return "; ".join(motivos)

    return "el proveedor no aceptó el mensaje y no dijo por qué"


def _enviar_por_api(
    cfg: Configuracion, destinatario: str, asunto: str, cuerpo: str
) -> None:
    """Send API v3.1 de Mailjet. A diferencia del SMTP, aquí sí hay motivo."""
    peticion = urllib.request.Request(
        cfg.api_url,
        method="POST",
        data=json.dumps(
            {
                "Messages": [
                    {
                        "From": {"Email": cfg.remitente, "Name": "EvA"},
                        "To": [{"Email": destinatario}],
                        "Subject": asunto,
                        "TextPart": cuerpo,
                    }
                ]
            }
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Basic "
            + base64.b64encode(
                f"{cfg.usuario}:{cfg.password}".encode()
            ).decode(),
        },
    )

    try:
        with urllib.request.urlopen(peticion, timeout=25) as r:
            crudo = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        # El cuerpo del error es justo lo que interesa: ahí va el motivo.
        cuerpo_error = exc.read().decode("utf-8", "replace")
        try:
            motivo = _motivo_del_rechazo(json.loads(cuerpo_error))
        except (ValueError, AttributeError):
            motivo = cuerpo_error[:300] or f"HTTP {exc.code}"
        raise CorreoNoEnviado(motivo) from exc
    except ssl.SSLError as exc:
        raise CorreoNoEnviado(
            "No se pudo verificar el certificado del proveedor de correo. "
            "Suele ser un antivirus que inspecciona el tráfico cifrado "
            f"(en el equipo de desarrollo era Norton). Detalle: {exc}"
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise CorreoNoEnviado(f"No se pudo contactar con el proveedor: {exc}") from exc

    try:
        respuesta = json.loads(crudo)
    except ValueError as exc:
        raise CorreoNoEnviado(f"Respuesta ilegible del proveedor: {crudo[:200]}") from exc

    mensajes = respuesta.get("Messages") or []
    if not mensajes or any(m.get("Status") != "success" for m in mensajes):
        raise CorreoNoEnviado(_motivo_del_rechazo(respuesta))
