"""Planes de vuelo guardados (D3).

Lo que el piloto guarda con el botón GUARDAR del planificador. Hasta ahora ese
botón estaba deshabilitado y no existía dónde guardar: esto es ese sitio.

**Cada plan es de su piloto.** Todas las funciones piden `license_id` y filtran
por él: no hay forma de listar, abrir ni borrar el plan de otro, ni siquiera
acertando el número. Es la misma regla que ya rige los vuelos.

Se guarda el JSON **entero** tal como lo arma el planificador
(`cuerpoDelPlan()` en `plan.html`), para poder devolver el plan exactamente
como estaba. Las columnas sueltas (origen, destino, aeronave…) son solo para
poder pintar la lista sin abrir el JSON de cada uno.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import cuentas

#: Campos que se copian a columna propia, para listar sin abrir el JSON.
_COLUMNAS = {
    "callsign": "callsign",
    "departure": "origen",
    "arrival": "destino",
    "alternate": "alterno",
    "aircraft": "aeronave",
    "cruise_alt_ft": "nivel",
    "route": "ruta",
}


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resumen(datos: dict) -> dict:
    """Saca a columnas los campos con los que se pinta la lista."""
    fuera = {}
    for clave, columna in _COLUMNAS.items():
        valor = datos.get(clave)
        fuera[columna] = "" if valor is None else str(valor).strip()
    return fuera


#: Valores válidos de `via`: con cuál de los tres botones se guardó.
VIA_VATSIM = "vatsim"
VIA_SIN_VATSIM = "sin_vatsim"
VIA_ICAO = "icao"
_VIAS_VALIDAS = {VIA_VATSIM, VIA_SIN_VATSIM, VIA_ICAO}


def guardar(
    license_id: str, datos: dict, *, plan_id: int | None = None, via: str = ""
) -> int:
    """Guarda un plan nuevo, o actualiza uno del propio piloto.

    `via` deja constancia de cómo se guardó (guardar directo, generar ICAO,
    o abrir VATSIM) — así se sabe después cómo se declaró ese vuelo, no solo
    qué contenía. Cadena vacía si no se especifica (no bloquea el guardado:
    un valor desconocido es preferible a que falle guardar el plan).

    Devuelve el id. Lanza ValueError si faltan los datos mínimos o si el plan
    que se pretende actualizar no es suyo.
    """
    if not license_id:
        raise ValueError("Hace falta saber de qué piloto es el plan")
    if not isinstance(datos, dict) or not datos:
        raise ValueError("El plan viene vacío")

    resumen = _resumen(datos)
    if not resumen["origen"] or not resumen["destino"]:
        raise ValueError("Un plan necesita al menos origen y destino")
    via = via if via in _VIAS_VALIDAS else ""

    momento = _ahora()
    crudo = json.dumps(datos, ensure_ascii=False)

    with cuentas.conexion() as con:
        if plan_id is not None:
            # El WHERE lleva el piloto: actualizar el plan de otro no cambia
            # ninguna fila y se responde igual que si no existiera.
            cambiadas = con.execute(
                "UPDATE planes SET callsign=?, origen=?, destino=?, alterno=?, "
                "aeronave=?, nivel=?, ruta=?, via=COALESCE(NULLIF(?, ''), via), "
                "datos=?, actualizado=? "
                "WHERE id=? AND license_id=? COLLATE NOCASE",
                (
                    resumen["callsign"], resumen["origen"], resumen["destino"],
                    resumen["alterno"], resumen["aeronave"], resumen["nivel"],
                    resumen["ruta"], via, crudo, momento, plan_id, license_id,
                ),
            ).rowcount
            if not cambiadas:
                raise ValueError("Ese plan no existe o no es tuyo")
            return int(plan_id)

        cursor = con.execute(
            "INSERT INTO planes (license_id, callsign, origen, destino, "
            "alterno, aeronave, nivel, ruta, via, datos, creado, actualizado) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                license_id, resumen["callsign"], resumen["origen"],
                resumen["destino"], resumen["alterno"], resumen["aeronave"],
                resumen["nivel"], resumen["ruta"], via, crudo, momento, momento,
            ),
        )
        return int(cursor.lastrowid)


def listar(license_id: str) -> list[dict]:
    """Los planes de ese piloto, el último guardado primero."""
    if not license_id:
        return []
    with cuentas.conexion() as con:
        filas = con.execute(
            "SELECT id, callsign, origen, destino, alterno, aeronave, nivel, "
            "ruta, via, creado, actualizado FROM planes "
            "WHERE license_id = ? COLLATE NOCASE ORDER BY actualizado DESC",
            (license_id,),
        ).fetchall()
    return [dict(f) for f in filas]


def obtener(plan_id: int, license_id: str) -> dict | None:
    """El plan completo, con sus `datos`, **solo si es de ese piloto**."""
    if not license_id:
        return None
    with cuentas.conexion() as con:
        fila = con.execute(
            "SELECT * FROM planes WHERE id = ? AND license_id = ? COLLATE NOCASE",
            (plan_id, license_id),
        ).fetchone()
    if fila is None:
        return None

    plan = dict(fila)
    try:
        plan["datos"] = json.loads(plan["datos"])
    except (ValueError, TypeError):
        plan["datos"] = {}
    return plan


def borrar(plan_id: int, license_id: str) -> bool:
    """Borra un plan propio. Devuelve si borró algo."""
    if not license_id:
        return False
    with cuentas.conexion() as con:
        borradas = con.execute(
            "DELETE FROM planes WHERE id = ? AND license_id = ? COLLATE NOCASE",
            (plan_id, license_id),
        ).rowcount
    return bool(borradas)


def cuantos(license_id: str) -> int:
    with cuentas.conexion() as con:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM planes WHERE license_id = ? COLLATE NOCASE",
            (license_id,),
        ).fetchone()
    return int(fila["n"])
