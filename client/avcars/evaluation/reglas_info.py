"""Ficha de cada regla de puntuación: de dónde sale el dato, con qué se
compara y por qué (si es el caso) no se puede evaluar todavía.

Fuente única de verdad para el panel de administración de reglas
(`/gestion/reglas` en la web) y para `docs/matriz_reglas.md`/`.csv`. Antes
esos dos documentos se mantenían a mano por separado — bastaba con editar
`scoring.py` sin acordarse de actualizarlos para que la trazabilidad
publicada empezara a mentir. Aquí solo se escribe una vez.

Lo que SÍ se deriva en vivo del propio motor (nunca se escribe a mano
aquí, para que no pueda desincronizarse):
- El alcance (VFR/IFR/ambas) sale de `scoring.RULE_SCOPE`.
- Qué reglas están hoy bloqueadas sale de la lista `not_evaluated` inicial
  de `scoring.evaluate_flight()`.

Lo que si es prosa a mano, porque no se puede derivar del código (describe
una intención o una carencia, no un estado presente):
- Nombre y descripción en español.
- Por qué está bloqueada una regla, y qué hace falta para desbloquearla.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import scoring


@dataclass(frozen=True)
class ReglaInfo:
    id: str
    nombre: str
    descripcion: str
    campo_log: str
    referencia: str
    logica: str
    scoring_ref: str
    # Solo si esta regla no depende de cada vuelo sino de una condición
    # estructural (p.ej. un avión de tren fijo): eso es lo único que separa
    # 🟡 de 🟢 aquí. Que a un vuelo concreto le falte el evento no cuenta —
    # eso ya lo resuelve `not_evaluated` por vuelo, no es un estado de la
    # regla.
    condicion_estructural: Optional[str] = None
    # Solo para las bloqueadas (🔴):
    motivo_bloqueo: str = ""
    que_falta: str = ""


_REGLAS: list[ReglaInfo] = [
    ReglaInfo(
        "runway_alignment_takeoff", "Alineación de pista al despegar",
        "El rumbo del avión al iniciar la carrera de despegue debe quedar "
        "razonablemente alineado con la pista.",
        "events[takeoff].runway_alignment_deg", "runway_alignment_deg_max (10°)",
        "abs(desviación) <= máximo -> OK; si no, penalización fija.",
        "scoring.py:476",
    ),
    ReglaInfo(
        "runway_alignment_landing", "Alineación de pista al aterrizar",
        "Igual que en despegue, pero en el momento del touchdown.",
        "events[touchdown].runway_alignment_deg", "runway_alignment_deg_max (10°)",
        "abs(desviación) <= máximo -> OK; si no, penalización fija.",
        "scoring.py:493",
    ),
    ReglaInfo(
        "touchdown_zone", "Punto de toma",
        "La distancia desde el umbral de pista hasta donde se produce el "
        "touchdown no debe pasar de un máximo.",
        "events[touchdown].distance_from_threshold_m", "touchdown_zone_m_max (600 m)",
        "distancia <= máximo -> OK; si no, penalización fija.",
        "scoring.py:507",
    ),
    ReglaInfo(
        "landing_vs", "Velocidad de descenso al aterrizar",
        "Clasifica la toma en bandas (butter/smooth/normal/hard/very_hard) "
        "según la velocidad vertical; la peor banda es fallo directo.",
        "events[touchdown].vs_fpm",
        "landing_vs_bands: butter 60, smooth 180, normal 300, hard 600 fpm",
        "banda según |vs_fpm|; very_hard -> FAIL, el resto resta puntos según su banda.",
        "scoring.py:520",
    ),
    ReglaInfo(
        "stabilized_500ft", "Aproximación estabilizada a 500 ft",
        "En el punto más cercano a 500 ft AGL, la velocidad vertical debe "
        "estar dentro de un rango razonable (ni en picado ni subiendo).",
        "track[].alt_agl_ft + vs_fpm",
        "stabilization: alt 500 ft ±100, vs entre -1000 y 0 fpm",
        "se busca el punto del track más cercano a 500 ft AGL y se comprueba su vs_fpm.",
        "scoring.py:545",
    ),
    ReglaInfo(
        "fuel_reserve", "Reserva de combustible al final",
        "El combustible restante al terminar el vuelo no debe bajar de un "
        "mínimo de reserva.",
        "summary.fuel_remaining_kg (o track[-1])", "fuel_reserve_kg_min (20 kg)",
        "combustible final >= mínimo -> OK; si no, penalización fija.",
        "scoring.py:566",
    ),
    ReglaInfo(
        "pause_duration", "Duración de las pausas",
        "Ninguna pausa del simulador debe superar un máximo razonable.",
        "events[pause].duration_s", "pause_duration_s_max (120 s)",
        "cada pausa se compara con el máximo; las que se pasan penalizan.",
        "scoring.py:583",
    ),
    ReglaInfo(
        "time_compression", "Compresión de tiempo",
        "El vuelo no puede haberse acelerado por encima de velocidad real "
        "(x1) en ningún momento.",
        "timing.max_sim_rate_observed", "límite fijo: 1.0",
        "si se observó una tasa >1.0 en algún punto, FAIL directo.",
        "scoring.py:597",
    ),
    ReglaInfo(
        "bank_angle", "Ángulo de alabeo (bank)",
        "El alabeo no debe superar un máximo duro, ni mantenerse por "
        "encima de un aviso durante varias muestras seguidas.",
        "track[].bank_deg", "bank_angle: aviso 30°, fallo 60°, 3 muestras sostenidas",
        "máximo absoluto -> FAIL; sostenido por encima del aviso -> penalización.",
        "scoring.py:226",
    ),
    ReglaInfo(
        "landing_light_takeoff", "Luces de aterrizaje encendidas al despegar",
        "En el momento del despegue, las luces de aterrizaje deben estar "
        "encendidas.",
        "events[takeoff].utc + track.landing_light más cercano",
        "lights.check_tolerance_s (30 s)",
        "se busca el punto del track a ±tolerancia del despegue y se mira si estaba encendida.",
        "scoring.py:380",
    ),
    ReglaInfo(
        "landing_light_landing", "Luces de aterrizaje encendidas al aterrizar",
        "Igual que la anterior, pero en el touchdown.",
        "events[touchdown].utc + track.landing_light más cercano",
        "lights.check_tolerance_s (30 s)",
        "mismo mecanismo que landing_light_takeoff, con el evento de touchdown.",
        "scoring.py:380",
    ),
    ReglaInfo(
        "beacon_airborne", "Luz anticolisión (beacon) encendida en vuelo",
        "Con el avión en el aire, la luz beacon debe estar encendida en "
        "todo momento.",
        "track[airborne].beacon_light", "penalización fija si falla en algún punto",
        "todos los puntos en el aire deben tener beacon=True; si no, FAIL.",
        "scoring.py:397",
    ),
    ReglaInfo(
        "nav_light_airborne", "Luces de navegación encendidas en vuelo",
        "Igual que el beacon, pero con las luces de navegación.",
        "track[airborne].nav_light", "penalización fija si falla en algún punto",
        "todos los puntos en el aire deben tener nav_light=True; si no, FAIL.",
        "scoring.py:413",
    ),
    ReglaInfo(
        "taxi_light", "Luz de rodaje encendida al rodar",
        "Con el avión en tierra y moviéndose, la luz de rodaje debe estar "
        "encendida.",
        "track[en tierra, gs>2 kt].taxi_light", "penalización fija si falla",
        "todos los puntos rodando deben tener taxi_light=True.",
        "scoring.py:427",
    ),
    ReglaInfo(
        "strobe_taxi", "Luz estroboscópica apagada al rodar",
        "Al contrario que las demás: la estroboscópica debe estar APAGADA "
        "mientras se rueda (se reserva para pista activa).",
        "track[rodando].strobe_light", "penalización fija si está encendida",
        "todos los puntos rodando deben tener strobe_light=False.",
        "scoring.py:443",
    ),
    ReglaInfo(
        "stall_warning", "Sin aviso de pérdida",
        "El avión no debe haber activado el aviso de entrada en pérdida "
        "(stall warning) en ningún momento.",
        "track[].stall_warning", "—",
        "si el aviso se activó en algún punto, FAIL directo.",
        "scoring.py:284",
    ),
    ReglaInfo(
        "overspeed_warning", "Sin aviso de sobrevelocidad del simulador",
        "El avión no debe haber superado la velocidad límite según el "
        "propio aviso del simulador (no un VNE recalculado por EvA).",
        "track[].overspeed_warning", "—",
        "si el aviso se activó en algún punto, FAIL directo.",
        "scoring.py:301",
    ),
    ReglaInfo(
        "qnh", "QNH ajustado dentro de rango",
        "El QNH configurado en el altímetro debe quedar dentro de un rango "
        "físicamente razonable.",
        "track[].qnh_inhg", "qnh: 28.5–31.2 inHg",
        "cada punto se compara contra el rango; fuera de rango penaliza.",
        "scoring.py:318",
    ),
    ReglaInfo(
        "gear_on_touchdown", "Tren de aterrizaje extendido al tomar contacto",
        "En el touchdown, el tren debe estar bajado — salvo en aviones de "
        "tren fijo, donde la pregunta no tiene sentido y se salta.",
        "events[touchdown].utc + track.gear_down (±5 s)",
        "penalties.gear_up_touchdown", "gear_down debe ser True en ese instante.",
        "scoring.py:338",
        condicion_estructural=(
            "Se salta por completo en aviones con configuracion.tren='fijo' "
            "(aircraft.yaml): en esos, la pregunta \"¿bajó el tren?\" no aplica."
        ),
    ),
    ReglaInfo(
        "route_deviation", "Desviación de la ruta planificada",
        "Comprobar que la trayectoria volada no se aleja demasiado de la "
        "ruta declarada en el plan de vuelo.",
        "flight_plan.route (texto sin parsear) + track[].lat/lon",
        "puntos_vfr_es (coords) + airports.json (origen/destino)",
        "—",
        "scoring.py:466",
        motivo_bloqueo="El campo `flight_plan.route` es texto libre (p.ej. "
        "\"DCT TERSA DCT\"), y hoy nada lo convierte en una lista de "
        "puntos con coordenadas para poder medir la distancia a la ruta.",
        que_falta="Un parser de `route` a waypoints, resueltos contra "
        "`puntos_vfr_es` (lat/lon por punto VFR).",
    ),
    ReglaInfo(
        "cruise_altitude_semicircular", "Altitud de crucero según regla semicircular",
        "En VFR, la altitud de crucero debe cumplir la regla semicircular "
        "según el rumbo de la ruta.",
        "flight_plan.planned_cruise_alt_ft + track[].alt_msl_ft",
        "—", "—",
        "scoring.py:467",
        motivo_bloqueo="No hay una altitud de crucero fiable con la que "
        "comparar: la declarada en el plan puede no coincidir con ninguna "
        "fase real sostenida del vuelo, y la regla semicircular no está "
        "implementada.",
        que_falta="Determinar la altitud de crucero real (fase estable del "
        "track) y programar la regla semicircular (rumbo -> altitudes "
        "pares/impares +500 ft).",
    ),
    ReglaInfo(
        "speed_below_10000ft", "Velocidad limitada por debajo de 10 000 ft",
        "La velocidad indicada no debe superar el límite del avión (o uno "
        "genérico) por debajo de 10 000 ft.",
        "track[].ias_kt + alt_msl_ft/alt_agl_ft",
        "aircraft.yaml: limites_poh.vno/vne",
        "—",
        "scoring.py:468",
        motivo_bloqueo="`limites_poh.vno`/`vne` está a `null` (no "
        "verificado) en 6 de los 8 aviones de `aircraft.yaml` — inventar "
        "un límite es peor que no evaluar.",
        que_falta="Publicar `vno`/`vne` reales (del POH) para los aviones "
        "que faltan en `aircraft.yaml`.",
    ),
    ReglaInfo(
        "assigned_squawk", "Squawk asignado por ATC",
        "El transpondedor debe llevar el código que ATC asignó en el plan, "
        "no uno cualquiera.",
        "track[].squawk + transponder_state",
        "—", "—",
        "scoring.py:469",
        motivo_bloqueo="Ni el plan de vuelo ni los eventos guardan qué "
        "squawk se asignó — solo el que el transpondedor llevaba puesto, "
        "que no sirve de referencia contra sí mismo.",
        que_falta="Añadir `squawk_asignado` a `flight_plan` (vendría de "
        "ATC/VATSIM, no del propio vuelo).",
    ),
    ReglaInfo(
        "planned_runway_match", "Pista usada coincide con la planificada",
        "La pista real de despegue/aterrizaje debería coincidir con la que "
        "se declaró al planificar el vuelo.",
        "events[].runway + flight_plan.departure_icao/arrival_icao",
        "pistas_es (designador, rumbos) + aerodromos_es.default_runway",
        "—",
        "scoring.py:470",
        motivo_bloqueo="El plan de vuelo no incluye qué pista se pensaba "
        "usar — solo el aeródromo. Sin pista planificada no hay con qué "
        "comparar la pista real.",
        que_falta="Un campo de pista planificada en el plan (o, como "
        "mínimo, usar `aerodromos_es.default_runway` como referencia "
        "cuando no se declaró ninguna).",
    ),
    ReglaInfo(
        "runway_excursion", "Excursión de pista",
        "El avión no debe salirse de los límites físicos de la pista "
        "mientras rueda por ella.",
        "track[].lat/lon + on_ground + events[].position_pct",
        "pistas_es / airports.json (solo coordenadas de punto, sin geometría)",
        "—",
        "scoring.py:471",
        motivo_bloqueo="Solo se conoce el punto central del aeródromo, no "
        "el polígono real de cada pista — no hay con qué comprobar si el "
        "avión se salió de los límites.",
        que_falta="Geometría de pista (ancho, orientación, extremos) en "
        "`pistas_es`, no solo el punto del aeródromo.",
    ),
    ReglaInfo(
        "structural_overspeed", "Sobrevelocidad estructural (VNE/VMO)",
        "La velocidad indicada no debe superar el límite certificado del "
        "avión (VMO si existe, si no VNE), sacado del POH real.",
        "track[].ias_kt",
        "aircraft.yaml: limites_poh.vne/vmo (POH primero, sim solo si no hay POH)",
        "se compara el IAS máximo observado contra el límite; por encima -> FAIL. "
        "Independiente de `overspeed_warning` (el aviso del propio simulador).",
        "scoring.py:472",
    ),
]

_POR_ID: dict[str, ReglaInfo] = {r.id: r for r in _REGLAS}


def listar() -> list[dict]:
    """Las 26 reglas, con alcance derivado en vivo del motor."""
    _avisar_si_hay_desajuste()
    return [_a_dict(r) for r in _REGLAS]


def obtener(regla_id: str) -> Optional[dict]:
    r = _POR_ID.get(regla_id)
    if r is None:
        return None
    return _a_dict(r)


def _reglas_no_evaluadas_por_defecto() -> list[str]:
    """La lista `not_evaluated` con la que arranca `evaluate_flight()`.

    Se usa solo como comprobación cruzada contra `motivo_bloqueo` (ver
    `_avisar_si_hay_desajuste`) — parsear el código fuente es frágil (ya dio
    un falso negativo con `structural_overspeed`), así que no manda por sí
    sola: el texto autoría en `_REGLAS` es la fuente de verdad real.
    """
    import inspect

    fuente = inspect.getsource(scoring.evaluate_flight)
    marcador = "not_evaluated: list[str] = ["
    inicio = fuente.index(marcador) + len(marcador)
    fin = fuente.index("]", inicio)
    bloque = fuente[inicio:fin]
    return [
        linea.strip().strip('",').strip("'")
        for linea in bloque.splitlines()
        if '"' in linea or "'" in linea
    ]


def _avisar_si_hay_desajuste() -> None:
    """Si el código y esta ficha se desincronizan, que se note en el log.

    No bloquea nada — mejor una pantalla con un aviso que una que calla y
    miente. Compara la lista `not_evaluated` real contra qué reglas tienen
    `motivo_bloqueo` escrito aquí.
    """
    import warnings

    en_vivo = set(_reglas_no_evaluadas_por_defecto())
    en_ficha = {r.id for r in _REGLAS if r.motivo_bloqueo}
    diferencia = en_vivo ^ en_ficha
    if diferencia:
        warnings.warn(
            "reglas_info desincronizado con scoring.py — revisar "
            f"motivo_bloqueo de: {sorted(diferencia)}",
            stacklevel=2,
        )


def _a_dict(r: ReglaInfo) -> dict:
    alcance = scoring.RULE_SCOPE.get(r.id, "ambas")
    if r.motivo_bloqueo:
        estado = "bloqueada"
    elif r.condicion_estructural:
        estado = "condicional"
    else:
        estado = "evaluable"
    return {
        "id": r.id,
        "nombre": r.nombre,
        "descripcion": r.descripcion,
        "alcance": alcance,
        "campo_log": r.campo_log,
        "referencia": r.referencia,
        "logica": r.logica,
        "scoring_ref": r.scoring_ref,
        "condicion_estructural": r.condicion_estructural,
        "estado": estado,
        "motivo_bloqueo": r.motivo_bloqueo,
        "que_falta": r.que_falta,
    }
