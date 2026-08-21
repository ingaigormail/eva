"""Dummy correo module for when avcars.correo is not available."""


class CorreoNoConfigurado(RuntimeError):
    """Correo no configurado."""
    pass


class CorreoNoEnviado(RuntimeError):
    """No se pudo enviar el correo."""
    pass


def configurado() -> bool:
    """Simula que el correo no está configurado."""
    return False


def correo_de_gestion() -> str:
    """Retorna una dirección dummy."""
    return ""


def enviar(destinatario: str, asunto: str, cuerpo: str) -> None:
    """Simula envío, pero falla."""
    raise CorreoNoConfigurado("Módulo correo no disponible")
