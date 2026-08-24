"""Peticiones de alta de pilotos que aún no tienen cuenta.

Una solicitud **no es una cuenta**: no tiene contraseña ni la tendrá. Solo
dice quién quiere entrar y con qué datos, para que un administrador decida.
Antes solo salían por correo, y un correo se pierde, se borra o se va a spam;
ahora quedan en la tabla `solicitudes` de `eva.db` y se ven en la pantalla de
gestión aunque el envío falle.

Cada piloto tiene como mucho **una solicitud pendiente**: volver a pedirlo
actualiza la que había en vez de amontonar copias.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import cuentas

PENDIENTE = "pendiente"
APROBADA = "aprobada"
RECHAZADA = "rechazada"
ESTADOS = (PENDIENTE, APROBADA, RECHAZADA)


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def crear(license_id: str, nombre: str, correo: str, *, vatsim_cid: str = "") -> int:
    """Guarda (o refresca) la solicitud y devuelve su id."""
    license_id = (license_id or "").strip()
    nombre = (nombre or "").strip()
    correo = cuentas.normalizar_correo(correo)

    if not license_id:
        raise ValueError("El Callsign o ID de EVA es obligatorio")
    if not nombre:
        raise ValueError("El nombre y los apellidos son obligatorios")
    if not cuentas.correo_valido(correo):
        raise ValueError("El correo electrónico no es válido")

    momento = _ahora()
    with cuentas.conexion() as con:
        fila = con.execute(
            "SELECT id FROM solicitudes WHERE license_id = ? AND estado = ?",
            (license_id, PENDIENTE),
        ).fetchone()
        if fila:
            con.execute(
                "UPDATE solicitudes SET nombre = ?, vatsim_cid = ?, correo = ?, "
                "creado = ? WHERE id = ?",
                (nombre, (vatsim_cid or "").strip(), correo, momento, fila["id"]),
            )
            return int(fila["id"])

        cursor = con.execute(
            "INSERT INTO solicitudes (license_id, nombre, vatsim_cid, correo, "
            "creado, estado) VALUES (?, ?, ?, ?, ?, ?)",
            (license_id, nombre, (vatsim_cid or "").strip(), correo, momento, PENDIENTE),
        )
        return int(cursor.lastrowid)


def pendientes() -> list[dict]:
    """Las que esperan decisión, la más reciente primero."""
    with cuentas.conexion() as con:
        filas = con.execute(
            "SELECT * FROM solicitudes WHERE estado = ? ORDER BY creado DESC",
            (PENDIENTE,),
        ).fetchall()
    return [dict(f) for f in filas]


def cuantas_pendientes() -> int:
    with cuentas.conexion() as con:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM solicitudes WHERE estado = ?", (PENDIENTE,)
        ).fetchone()
    return int(fila["n"])


def obtener(solicitud_id: int) -> dict | None:
    with cuentas.conexion() as con:
        fila = con.execute(
            "SELECT * FROM solicitudes WHERE id = ?", (solicitud_id,)
        ).fetchone()
    return dict(fila) if fila else None


def resolver(solicitud_id: int, estado: str, *, por: str) -> dict:
    """Marca la solicitud como aprobada o rechazada. Nunca se borra.

    Queda quién la resolvió y cuándo: con las altas conviene saberlo.
    """
    if estado not in (APROBADA, RECHAZADA):
        raise ValueError(f"Estado de solicitud desconocido: {estado}")

    with cuentas.conexion() as con:
        fila = con.execute(
            "SELECT * FROM solicitudes WHERE id = ? AND estado = ?",
            (solicitud_id, PENDIENTE),
        ).fetchone()
        if fila is None:
            raise ValueError("Esa solicitud ya no está pendiente")
        con.execute(
            "UPDATE solicitudes SET estado = ?, resuelta_por = ?, resuelta_en = ? "
            "WHERE id = ?",
            (estado, por, _ahora(), solicitud_id),
        )
    return dict(fila)


def historial(limite: int = 50) -> list[dict]:
    """Todas, resueltas incluidas: quién pidió entrar y en qué quedó."""
    with cuentas.conexion() as con:
        filas = con.execute(
            "SELECT * FROM solicitudes ORDER BY creado DESC LIMIT ?", (limite,)
        ).fetchall()
    return [dict(f) for f in filas]
