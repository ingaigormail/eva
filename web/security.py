"""Configuración de seguridad para EvA web."""

import secrets

from flask import Flask, g, request
from markupsafe import escape
import bleach


def setup_security_headers(app: Flask):
    """Configura headers de seguridad HTTP."""

    @app.before_request
    def _generar_csp_nonce():
        # Un nonce por petición: autoriza justo los <script> que la propia
        # plantilla ha marcado con él, sin abrir la puerta a 'unsafe-inline'
        # (que dejaría colar cualquier script inyectado).
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def _exponer_csp_nonce():
        return {"csp_nonce": g.get("csp_nonce", "")}

    @app.after_request
    def add_security_headers(response):
        # Protección contra clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevenir MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # CSP básico: solo recursos desde el mismo origen, más el nonce de
        # esta petición para los <script> inline que lo llevan.
        nonce = g.get("csp_nonce", "")
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https://*.tile.openstreetmap.org; "
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
