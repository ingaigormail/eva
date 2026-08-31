"""Estadísticas globales de EvA Airliner: el Home de la aerolínea.

No es la cartilla de un piloto (esa sigue siendo `dueno_del_vuelo`/`es_de` sobre
ficheros): es un **resumen agregado** de todos los vuelos de todos los
pilotos, en la tabla `vuelos_resumen` de `eva.db`. Se escribe una fila **en el
momento de integrar el vuelo a la cartilla** (`/api/registro/upload`), no
recorriendo ficheros en cada carga del dashboard — que era lo que hacía lento
y frágil calcular esto sobre JSON disperso.

Principio del proyecto, aplicado aquí: EvA no es solo un contador de vuelos,
es una escuela con motor de evaluación. Por eso la tabla guarda **calidad**
(APTO/NO APTO/NO EVALUABLE) e **incidencias**, no solo distancia y duración.
Los `.csv` de fstelemetry no pasan hoy por el motor de evaluación, así que su
`calidad` queda `None` — no se les inventa un veredicto que no existe.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import cuentas

APTO = "apto"
NO_APTO = "no_apto"
NO_EVALUABLE = "no_evaluable"

#: Bajo este número de vuelos, un piloto no entra en el ranking de calidad:
#: un solo vuelo perfecto no debe ganarle a quien vuela con regularidad.
MINIMO_VUELOS_RANKING_CALIDAD = 5


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _calidad_de(verdict) -> str:
    if not verdict.evaluable:
        return NO_EVALUABLE
    return APTO if verdict.passed else NO_APTO


def _incidencias_de(verdict) -> list[str]:
    """Nombres de las reglas falladas, para «incidencia más repetida»."""
    return [item.rule for item in verdict.items if not item.passed]


def borrar_por_huella(huella: str) -> None:
    """Quita el resumen de ese vuelo. Para cuando el vuelo se borra del todo."""
    with cuentas.conexion() as con:
        con.execute("DELETE FROM vuelos_resumen WHERE huella = ?", (huella,))


def ya_registrado(huella: str) -> bool:
    with cuentas.conexion() as con:
        return (
            con.execute(
                "SELECT 1 FROM vuelos_resumen WHERE huella = ?", (huella,)
            ).fetchone()
            is not None
        )


def registrar_avlog(
    huella: str, flight, verdict, *, perfil: str = "", fecha: str | None = None
) -> None:
    """Resumen de un `.avlog.json` recién integrado. Idempotente por huella.

    `verdict` es el `Verdict` de `evaluate_flight()`: la calidad que se guarda
    es la evaluación real, la misma que ve el piloto en su informe. `perfil`
    es el nombre del perfil con que se evaluó (easy/normal/hard), no el dict.
    """
    if ya_registrado(huella):
        return

    resumen = flight.summary
    plan = flight.flight_plan
    # getattr, no flight.payload: los dobles de test (SimpleNamespace) no
    # siempre lo traen, y un vuelo real de antes de esta fecha tampoco.
    payload = getattr(flight, "payload", None)
    momento = _ahora()
    with cuentas.conexion() as con:
        con.execute(
            "INSERT OR IGNORE INTO vuelos_resumen (huella, license_id, "
            "callsign, origen, destino, aeronave, matricula, reglas, red, "
            "control_atc, distancia_nm, duracion_min, combustible_usado_kg, "
            "combustible_restante_kg, calidad, puntuacion, perfil_evaluacion, "
            "incidencias, fecha, creado, pasajeros_aplicados, carga_kg_aplicada) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                huella,
                flight.pilot.license_id,
                flight.pilot.callsign or flight.pilot.license_id,
                plan.departure_icao,
                plan.arrival_icao,
                plan.aircraft_icao_type or "",
                plan.aircraft_registration or "",
                plan.rules or "",
                plan.network or "",
                1 if plan.atc_controlled else 0,
                float(resumen.total_distance_nm) if resumen and resumen.total_distance_nm else 0.0,
                float(resumen.flight_time_min) if resumen and resumen.flight_time_min else 0.0,
                float(resumen.fuel_used_kg) if resumen and resumen.fuel_used_kg is not None else None,
                float(resumen.fuel_remaining_kg) if resumen and resumen.fuel_remaining_kg is not None else None,
                _calidad_de(verdict),
                int(verdict.score) if verdict.evaluable else None,
                perfil,
                json.dumps(_incidencias_de(verdict), ensure_ascii=False),
                fecha or momento,
                momento,
                # Solo si el simulador confirmó haber escrito la carga: un
                # intento fallido no debe parecer "vuelo sin pasajeros".
                payload.requested_passengers if payload and payload.cargo_written_ok else None,
                payload.applied_cargo_kg if payload and payload.cargo_written_ok else None,
            ),
        )


def registrar_csv(
    huella: str,
    license_id: str,
    *,
    distancia_nm: float,
    duracion_min: float,
    fecha: str | None = None,
) -> None:
    """Resumen de un `.csv` de fstelemetry. Sin calidad: no se evalúa hoy."""
    if ya_registrado(huella):
        return

    momento = _ahora()
    with cuentas.conexion() as con:
        con.execute(
            "INSERT OR IGNORE INTO vuelos_resumen (huella, license_id, "
            "callsign, origen, destino, aeronave, matricula, reglas, red, "
            "control_atc, distancia_nm, duracion_min, combustible_usado_kg, "
            "combustible_restante_kg, calidad, puntuacion, perfil_evaluacion, "
            "incidencias, fecha, creado) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                huella, license_id, license_id, "", "", "", "", "", "",
                None,
                float(distancia_nm or 0), float(duracion_min or 0),
                None, None, None, None, "",
                "[]", fecha or momento, momento,
            ),
        )


# -- agregados: el Home de la aerolínea ------------------------------------


def kpis_globales() -> dict:
    """Los números de cabecera. `pct_apto` y `pct_no_evaluable` solo cuentan
    vuelos con `calidad` conocida (los `.csv` no entran en ese cálculo)."""
    hoy = datetime.now(timezone.utc).date().isoformat()
    with cuentas.conexion() as con:
        totales = con.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(duracion_min),0) AS minutos "
            "FROM vuelos_resumen"
        ).fetchone()
        hoy_n = con.execute(
            "SELECT COUNT(*) AS n FROM vuelos_resumen WHERE fecha LIKE ?",
            (f"{hoy}%",),
        ).fetchone()["n"]
        pilotos = con.execute(
            "SELECT COUNT(DISTINCT license_id) AS n FROM vuelos_resumen"
        ).fetchone()["n"]
        calidad = con.execute(
            "SELECT calidad, COUNT(*) AS n FROM vuelos_resumen "
            "WHERE calidad IS NOT NULL GROUP BY calidad"
        ).fetchall()

    por_calidad = {fila["calidad"]: fila["n"] for fila in calidad}
    evaluados = sum(por_calidad.values())

    return {
        "total_vuelos": totales["n"],
        "vuelos_hoy": hoy_n,
        "horas_totales": round(totales["minutos"] / 60, 1),
        "total_pilotos": pilotos,
        "pct_apto": round(100 * por_calidad.get(APTO, 0) / evaluados, 1) if evaluados else None,
        "pct_no_evaluable": round(100 * por_calidad.get(NO_EVALUABLE, 0) / evaluados, 1) if evaluados else None,
        "vuelos_evaluados": evaluados,
    }


def top_pilotos_actividad(limite: int = 10) -> list[dict]:
    """Ranking por volumen: quién más vuela."""
    with cuentas.conexion() as con:
        filas = con.execute(
            "SELECT license_id, COUNT(*) AS vuelos, "
            "ROUND(SUM(duracion_min)/60.0, 1) AS horas, "
            "ROUND(SUM(distancia_nm), 0) AS distancia_nm "
            "FROM vuelos_resumen GROUP BY license_id "
            "ORDER BY vuelos DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [dict(f) for f in filas]


def top_pilotos_calidad(
    limite: int = 10, minimo_vuelos: int = MINIMO_VUELOS_RANKING_CALIDAD
) -> list[dict]:
    """Ranking por calidad: mejor % de vuelos APTO, con un mínimo de vuelos
    evaluados para que uno solo no decida el puesto."""
    with cuentas.conexion() as con:
        filas = con.execute(
            "SELECT license_id, "
            "COUNT(*) AS vuelos_evaluados, "
            "SUM(CASE WHEN calidad = ? THEN 1 ELSE 0 END) AS aptos "
            "FROM vuelos_resumen WHERE calidad IS NOT NULL "
            "GROUP BY license_id HAVING COUNT(*) >= ? "
            "ORDER BY (1.0 * aptos / vuelos_evaluados) DESC, vuelos_evaluados DESC "
            "LIMIT ?",
            (APTO, minimo_vuelos, limite),
        ).fetchall()
    return [
        {**dict(f), "pct_apto": round(100 * f["aptos"] / f["vuelos_evaluados"], 1)}
        for f in filas
    ]


def actividad_reciente_por_piloto(dias: int = 30) -> dict[str, dict]:
    """Por piloto: su último vuelo (fecha, origen, destino) y cuántos ha
    hecho en los últimos `dias` días.

    Para `/gestion/usuarios`: es una ficha por piloto, no un ranking — se
    calcula todo en una sola pasada sobre `vuelos_resumen` (barato, el
    volumen de EvA no lo justifica) en vez de una consulta por piloto, que
    con muchos usuarios sería N+1.
    """
    from datetime import datetime, timedelta, timezone

    limite_iso = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()

    with cuentas.conexion() as con:
        filas = con.execute(
            "SELECT license_id, origen, destino, fecha FROM vuelos_resumen "
            "ORDER BY fecha DESC"
        ).fetchall()

    resultado: dict[str, dict] = {}
    for f in filas:
        piloto = f["license_id"]
        ficha = resultado.setdefault(
            piloto,
            {
                "ultima_fecha": None,
                "ultimo_origen": None,
                "ultimo_destino": None,
                "vuelos_recientes": 0,
            },
        )
        if ficha["ultima_fecha"] is None:
            # Primera fila que se ve de este piloto: como viene ORDER BY
            # fecha DESC, es su vuelo más reciente.
            ficha["ultima_fecha"] = f["fecha"]
            ficha["ultimo_origen"] = f["origen"]
            ficha["ultimo_destino"] = f["destino"]
        if f["fecha"] >= limite_iso:
            ficha["vuelos_recientes"] += 1
    return resultado


def top_rutas(limite: int = 10) -> list[dict]:
    with cuentas.conexion() as con:
        filas = con.execute(
            "SELECT origen, destino, COUNT(*) AS vuelos, "
            "ROUND(SUM(distancia_nm), 0) AS distancia_total_nm "
            "FROM vuelos_resumen WHERE origen != '' AND destino != '' "
            "GROUP BY origen, destino ORDER BY vuelos DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [dict(f) for f in filas]


def top_aeropuertos(limite: int = 10) -> list[dict]:
    """Operaciones por aeropuerto: cuenta como salida y como llegada."""
    with cuentas.conexion() as con:
        filas = con.execute(
            """
            SELECT icao,
                   SUM(salidas) AS salidas,
                   SUM(llegadas) AS llegadas,
                   SUM(salidas) + SUM(llegadas) AS operaciones
            FROM (
                SELECT origen AS icao, COUNT(*) AS salidas, 0 AS llegadas
                FROM vuelos_resumen WHERE origen != '' GROUP BY origen
                UNION ALL
                SELECT destino AS icao, 0 AS salidas, COUNT(*) AS llegadas
                FROM vuelos_resumen WHERE destino != '' GROUP BY destino
            )
            GROUP BY icao ORDER BY operaciones DESC LIMIT ?
            """,
            (limite,),
        ).fetchall()
    return [dict(f) for f in filas]


def actividad_mensual(meses: int = 12) -> list[dict]:
    """Vuelos, horas y km por mes, los últimos `meses`, en orden cronológico."""
    with cuentas.conexion() as con:
        filas = con.execute(
            "SELECT substr(fecha, 1, 7) AS mes, COUNT(*) AS vuelos, "
            "ROUND(SUM(duracion_min)/60.0, 1) AS horas, "
            "ROUND(SUM(distancia_nm), 0) AS distancia_nm "
            "FROM vuelos_resumen GROUP BY mes ORDER BY mes DESC LIMIT ?",
            (meses,),
        ).fetchall()
    return [dict(f) for f in reversed(filas)]


def incidencia_mas_frecuente(limite: int = 5) -> list[dict]:
    """Las reglas que más veces fallan en toda la flota, con su % de vuelos."""
    with cuentas.conexion() as con:
        filas = con.execute(
            "SELECT incidencias FROM vuelos_resumen WHERE calidad IS NOT NULL"
        ).fetchall()

    total = len(filas)
    if not total:
        return []

    conteo: dict[str, int] = {}
    for fila in filas:
        try:
            reglas = json.loads(fila["incidencias"])
        except (ValueError, TypeError):
            continue
        for regla in reglas:
            conteo[regla] = conteo.get(regla, 0) + 1

    return [
        {"regla": regla, "vuelos": n, "pct": round(100 * n / total, 1)}
        for regla, n in sorted(conteo.items(), key=lambda kv: kv[1], reverse=True)[:limite]
    ]
