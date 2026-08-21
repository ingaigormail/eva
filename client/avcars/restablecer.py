"""Testigos de un solo uso para restablecer la contraseña.

Reglas del proyecto:

- Nunca se muestra ni se envía una contraseña existente. Lo que viaja por
  correo es un **enlace con un testigo de un solo uso y con caducidad**.
- Al usarlo, la contraseña anterior deja de valer y el testigo se quema.
- En la base solo queda el **hash** del testigo: quien lea el fichero no puede
  usarlo para entrar.

Viven en la tabla `testigos` de `eva.db`, la misma base que las cuentas: si
dos peticiones coinciden, quemar un testigo es una operación atómica y no una
carrera entre dos reescrituras de un JSON.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from . import cuentas

MINUTOS_VALIDEZ = 60


def _huella(testigo: str) -> str:
    return hashlib.sha256((testigo or "").encode("utf-8")).hexdigest()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(momento: datetime) -> str:
    return momento.isoformat(timespec="seconds")


def crear(license_id: str, *, minutos: int = MINUTOS_VALIDEZ) -> str:
    """Emite un testigo para ese piloto y devuelve el valor en claro.

    El valor en claro solo existe aquí y en el correo: no se guarda. Pedir uno
    nuevo invalida el anterior del mismo piloto.
    """
    if not cuentas.existe_usuario(license_id):
        raise ValueError(f"El piloto {license_id} no está dado de alta")

    ahora = _ahora()
    testigo = secrets.token_urlsafe(32)
    with cuentas.conexion() as con:
        con.execute("DELETE FROM testigos WHERE license_id = ?", (license_id,))
        con.execute("DELETE FROM testigos WHERE caduca <= ?", (_iso(ahora),))
        con.execute(
            "INSERT INTO testigos (huella, license_id, creado, caduca) "
            "VALUES (?, ?, ?, ?)",
            (
                _huella(testigo),
                license_id,
                _iso(ahora),
                _iso(ahora + timedelta(minutes=minutos)),
            ),
        )
    return testigo


def piloto_de(testigo: str) -> str | None:
    """Piloto al que pertenece un testigo vigente, o None."""
    with cuentas.conexion() as con:
        fila = con.execute(
            "SELECT license_id FROM testigos WHERE huella = ? AND caduca > ?",
            (_huella(testigo), _iso(_ahora())),
        ).fetchone()
    if fila is None:
        return None
    license_id = fila["license_id"]
    return license_id if cuentas.existe_usuario(license_id) else None


def consumir(testigo: str, nueva_password: str) -> str | None:
    """Cambia la contraseña y quema el testigo. Devuelve el piloto o None.

    El borrado va primero y mira cuántas filas tocó: si dos peticiones llegan
    con el mismo testigo, solo una encuentra fila que borrar y solo esa cambia
    la contraseña.
    """
    if not nueva_password:
        raise ValueError("La contraseña es obligatoria")

    with cuentas.conexion() as con:
        fila = con.execute(
            "SELECT license_id FROM testigos WHERE huella = ? AND caduca > ?",
            (_huella(testigo), _iso(_ahora())),
        ).fetchone()
        if fila is None:
            return None
        quemado = con.execute(
            "DELETE FROM testigos WHERE huella = ?", (_huella(testigo),)
        ).rowcount
    if not quemado:
        return None

    license_id = fila["license_id"]
    if not cuentas.existe_usuario(license_id):
        return None

    cuentas.establecer_password(license_id, nueva_password)
    return license_id


def purgar() -> None:
    """Tira los testigos caducados."""
    with cuentas.conexion() as con:
        con.execute("DELETE FROM testigos WHERE caduca <= ?", (_iso(_ahora()),))
