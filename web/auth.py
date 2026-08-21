"""Sesión Flask. Las altas viven en avcars.cuentas (mismo fichero que D1).

Semilla: `pruebas` / `pruebas`, con rol de administrador.
"""
from __future__ import annotations

from functools import wraps

from flask import abort, redirect, session, url_for

from avcars import cuentas
from avcars.cuentas import (  # noqa: F401 — reexport para app.py / tests
    AUTH_BLOQUEADA,
    AUTH_DESCONOCIDO,
    AUTH_OK,
    AUTH_PASSWORD,
    ESTADO_ACTIVA,
    ESTADO_BLOQUEADA,
    PASSWORD_PRUEBAS,
    PERM_GESTIONAR_USUARIOS,
    PERM_VOLAR,
    ROL_ADMIN,
    ROL_PILOTO,
    USUARIO_PRUEBAS,
    autenticar,
    autenticar_detallado,
    crear_cuenta,
    es_admin,
    esta_activa,
    existe_usuario,
    listar_usuarios,
    registrar_usuario,
    rol_de,
    tiene_permiso,
)


def login_requerido(f):
    """Decorador para rutas que requieren autenticación."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function


def permiso_requerido(permiso: str):
    """Rutas que además del login exigen un permiso concreto (por rol).

    Añadir otro administrador es cambiarle el rol en `cuentas`, no tocar esto.
    """
    def decorador(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user_id = session.get("user_id", "")
            if not user_id:
                return redirect(url_for("login_page"))
            if not cuentas.tiene_permiso(user_id, permiso):
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorador


def obtener_usuario_actual() -> str:
    """Devuelve el ID del usuario actual (si está autenticado)."""
    return session.get("user_id", "")
