"""Configuración de seguridad para EvA web."""

from flask import Flask, request
from markupsafe import escape
import bleach


def setup_security_headers(app: Flask):
    """Configura headers de seguridad HTTP."""

    @app.after_request
    def add_security_headers(response):
        # Protección contra clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevenir MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # CSP básico: solo recursos desde el mismo origen
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'"
        )

        # HSTS: force HTTPS durante 1 año
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

        # Control de referrer
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Controlar APIs del navegador
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        )

        return response


def sanitize_input(value: str, max_length: int = 255) -> str:
    """Sanitiza entrada de usuario: remove HTML tags, escape special chars."""
    if not isinstance(value, str):
        return ""

    # Remove HTML tags
    value = bleach.clean(value, tags=[], strip=True)

    # Limit length
    value = value[:max_length]

    # Escape any remaining special characters
    value = escape(value)

    return str(value)


def validate_callsign(callsign: str) -> bool:
    """Valida formato de callsign (ICAO: max 7 alphanumeric)."""
    import re
    return bool(re.match(r"^[A-Z0-9]{1,7}$", callsign.upper()))


def validate_email(email: str) -> bool:
    """Validación básica de email."""
    import re
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))
