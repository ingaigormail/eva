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
- El umbral con el que se puntúa cada regla (`valores`) sale en vivo del
  perfil `normal` (`config/profiles.yaml`, el único que de verdad afecta a
  la nota — ver `web/app.py:DEFAULT_PROFILE`) con los overrides de
  `reglas_config.py` ya aplicados encima. Nunca se copia el número aquí a
  mano: `config_paths` solo dice DÓNDE mirar, no cuánto vale.
- Si la regla está activa o no (`activa`) sale de `reglas_config.py`.

Lo que si es prosa a mano, porque no se puede derivar del código (describe
una intención o una carencia, no un estado presente):
- Nombre y descripción en español.
- Por qué está bloqueada una regla, y qué hace falta para desbloquearla.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .. import config as avcars_config
from . import reglas_config, scoring

#: Perfil que de verdad afecta a la nota y a las estadísticas — ver
#: `DEFAULT_PROFILE` en `web/app.py`. "easy"/"hard" son solo una vista
#: alternativa para releer un vuelo ya subido, no cambian lo que se guarda.
_PERFIL_QUE_PUNTUA = "normal"

#: Unidad para mostrar cada valor de configuración. Solo cosmético — el tipo
#: y el valor de verdad los da el propio perfil, nunca se inventan aquí.
_UNIDADES: dict[str, str] = {
    "runway_alignment_deg_max": "°",
    "touchdown_zone_m_max": " m",
    "fuel_reserve_kg_min": " kg",
    "pause_duration_s_max": " s",
    "bank_angle.warn_deg": "°",
    "bank_angle.fail_deg": "°",
    "bank_angle.sustained_samples": " muestras",
    "qnh.min_inhg": " inHg",
    "qnh.max_inhg": " inHg",
    "lights.check_tolerance_s": " s",
    "stabilization.alt_agl_ft": " ft",
    "stabilization.alt_agl_tolerance_ft": " ft",
    "stabilization.vs_fpm_min": " fpm",
    "stabilization.vs_fpm_max": " fpm",
    "landing_vs_bands.butter.max_fpm": " fpm",
    "landing_vs_bands.smooth.max_fpm": " fpm",
    "landing_vs_bands.normal.max_fpm": " fpm",
    "landing_vs_bands.hard.max_fpm": " fpm",
    "airspace.margen_nm": " NM",
    "airspace.permanencia_s": " s",
    "airspace.muestras_minimas": " muestras",
    "airspace.penalizacion_maxima": " puntos",
    "penalties.airspace_intrusion": " puntos por zona",
}


def _formatear_valor(ruta: str, valor: Any) -> str:
    return f"{valor}{_UNIDADES.get(ruta, '')}"


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
    # Rutas punteadas dentro del perfil de dificultad (p.ej.
    # "bank_angle.fail_deg") de donde sale el "valor de evaluación" en vivo
    # de esta regla. Vacío si la regla no tiene un umbral en `profiles.yaml`
    # (p.ej. es un aviso booleano del simulador, o su límite sale de
    # `aircraft.yaml` en vez de del perfil — como `structural_overspeed`).
    config_paths: list[str] = field(default_factory=list)


_REGLAS: list[ReglaInfo] = [
    ReglaInfo(
        "runway_alignment_takeoff", "Alineación de pista al despegar",
        "El rumbo del avión al iniciar la carrera de despegue debe quedar "
        "razonablemente alineado con la pista.",
        "events[takeoff].runway_alignment_deg", "runway_alignment_deg_max",
        "abs(desviación) <= máximo -> OK; si no, penalización fija.",
        "scoring.py:476",
        config_paths=["runway_alignment_deg_max"],
    ),
    ReglaInfo(
        "runway_alignment_landing", "Alineación de pista al aterrizar",
        "Igual que en despegue, pero en el momento del touchdown.",
        "events[touchdown].runway_alignment_deg", "runway_alignment_deg_max",
        "abs(desviación) <= máximo -> OK; si no, penalización fija.",
        "scoring.py:493",
        config_paths=["runway_alignment_deg_max"],
    ),
    ReglaInfo(
        "touchdown_zone", "Punto de toma",
        "La distancia desde el umbral de pista hasta donde se produce el "
        "touchdown no debe pasar de un máximo.",
        "events[touchdown].distance_from_threshold_m", "touchdown_zone_m_max",
        "distancia <= máximo -> OK; si no, penalización fija.",
        "scoring.py:507",
        config_paths=["touchdown_zone_m_max"],
    ),
    ReglaInfo(
        "landing_vs", "Velocidad de descenso al aterrizar",
        "Clasifica la toma en bandas (butter/smooth/normal/hard/very_hard) "
        "según la velocidad vertical; la peor banda es fallo directo.",
        "events[touchdown].vs_fpm",
        "landing_vs_bands: máximo de cada banda (butter/smooth/normal/hard)",
        "banda según |vs_fpm|; very_hard -> FAIL, el resto resta puntos según su banda.",
        "scoring.py:520",
        config_paths=[
            "landing_vs_bands.butter.max_fpm",
            "landing_vs_bands.smooth.max_fpm",
            "landing_vs_bands.normal.max_fpm",
            "landing_vs_bands.hard.max_fpm",
        ],
    ),
    ReglaInfo(
        "stabilized_500ft", "Aproximación estabilizada a 500 ft",
        "En el punto más cercano a 500 ft AGL, la velocidad vertical debe "
        "estar dentro de un rango razonable (ni en picado ni subiendo).",
        "track[].alt_agl_ft + vs_fpm",
        "stabilization: altura objetivo ±tolerancia, rango de vs admitido",
        "se busca el punto del track más cercano a 500 ft AGL y se comprueba su vs_fpm.",
        "scoring.py:545",
        config_paths=[
            "stabilization.alt_agl_ft",
            "stabilization.alt_agl_tolerance_ft",
            "stabilization.vs_fpm_min",
            "stabilization.vs_fpm_max",
        ],
    ),
    ReglaInfo(
        "fuel_reserve", "Reserva de combustible al final",
        "El combustible restante al terminar el vuelo no debe bajar de un "
        "mínimo de reserva.",
        "summary.fuel_remaining_kg (o track[-1])", "fuel_reserve_kg_min",
        "combustible final >= mínimo -> OK; si no, penalización fija.",
        "scoring.py:566",
        config_paths=["fuel_reserve_kg_min"],
    ),
    ReglaInfo(
        "pause_duration", "Duración de las pausas",
        "Ninguna pausa del simulador debe superar un máximo razonable.",
        "events[pause].duration_s", "pause_duration_s_max",
        "cada pausa se compara con el máximo; las que se pasan penalizan.",
        "scoring.py:583",
        config_paths=["pause_duration_s_max"],
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
        "track[].bank_deg", "bank_angle: aviso, fallo, muestras sostenidas",
        "máximo absoluto -> FAIL; sostenido por encima del aviso -> penalización.",
        "scoring.py:226",
        config_paths=[
            "bank_angle.warn_deg", "bank_angle.fail_deg", "bank_angle.sustained_samples",
        ],
    ),
    ReglaInfo(
        "landing_light_takeoff", "Luces de aterrizaje encendidas al despegar",
        "En el momento del despegue, las luces de aterrizaje deben estar "
        "encendidas.",
        "events[takeoff].utc + track.landing_light más cercano",
        "lights.check_tolerance_s",
        "se busca el punto del track a ±tolerancia del despegue y se mira si estaba encendida.",
        "scoring.py:380",
        config_paths=["lights.check_tolerance_s"],
    ),
    ReglaInfo(
        "landing_light_landing", "Luces de aterrizaje encendidas al aterrizar",
        "Igual que la anterior, pero en el touchdown.",
        "events[touchdown].utc + track.landing_light más cercano",
        "lights.check_tolerance_s",
        "mismo mecanismo que landing_light_takeoff, con el evento de touchdown.",
        "scoring.py:380",
        config_paths=["lights.check_tolerance_s"],
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
        "transponder_airborne", "Transpondedor puesto en vuelo",
        "En IVAO y en VATSIM se vuela con el transpondedor transmitiendo: "
        "apagado o en espera, ni el control ni el resto del tráfico ven al "
        "avión. Valen tanto ON como ALT.",
        "track[en vuelo].transponder_state", "penalización fija si va apagado",
        "todos los puntos en vuelo deben tener el transpondedor en ON o ALT.",
        "scoring.py:498",
    ),
    ReglaInfo(
        "strobe_airborne", "Luz estroboscópica encendida en vuelo",
        "La estroboscópica debe ir ENCENDIDA mientras se vuela. De las "
        "luces, es la única que penaliza: las demás se dejaron de puntuar "
        "por decisión de la aerolínea.",
        "track[en vuelo].strobe_light", "penalización fija si está apagada",
        "todos los puntos en vuelo deben tener strobe_light=True.",
        "scoring.py:493",
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
        "track[].qnh_inhg", "qnh: mínimo y máximo admitidos",
        "cada punto se compara contra el rango; fuera de rango penaliza.",
        "scoring.py:318",
        config_paths=["qnh.min_inhg", "qnh.max_inhg"],
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
        "airspace_zones", "Invasión de zona prohibida, restringida o peligrosa",
        "El vuelo no debe atravesar zonas P, R, D ni de prohibición VFR. "
        "Para acusar hacen falta tres cosas a la vez: estar dentro del "
        "polígono, a más de un margen del borde, y de forma continuada un "
        "tiempo mínimo. Una zona cuya referencia vertical no se entiende se "
        "deja fuera en vez de suponer.",
        "track[].lat/lon + alt_msl_ft + alt_agl_ft",
        "web/data/aeronautica.db (capas D_P_R, PROHIBIDO_VFR, NO_SOBREVUELO)",
        "Penaliza por cada zona invadida, con tope. No es fallo duro: la "
        "traza en crucero guarda 1 punto cada 10 s, así que detecta "
        "travesías, no roces.",
        "scoring.py:_evaluate_airspace",
        condicion_estructural=(
            "Necesita la base de espacio aéreo de ENAIRE, que genera "
            "web/tools/descargar_enaire.py y se rehace cada ciclo AIRAC. Sin "
            "ella la regla queda sin evaluar y el resto del vuelo se puntúa "
            "igual. El cliente no la lleva: solo se evalúa en el servidor."
        ),
        config_paths=[
            "airspace.margen_nm",
            "airspace.permanencia_s",
            "airspace.muestras_minimas",
            "airspace.penalizacion_maxima",
            "penalties.airspace_intrusion",
        ],
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


def _perfil_y_overrides() -> tuple[dict, dict]:
    """El perfil que de verdad puntúa + los overrides guardados. Siempre en
    vivo, sin caché: un cambio guardado se ve en la siguiente petición."""
    perfiles = avcars_config.load_profiles()
    base = avcars_config.get_profile(_PERFIL_QUE_PUNTUA, perfiles)
    overrides = reglas_config.cargar_overrides()
    return base, overrides


def listar() -> list[dict]:
    """Las 26 reglas, con alcance, activación y umbrales derivados en vivo del motor."""
    _avisar_si_hay_desajuste()
    perfil_base, overrides = _perfil_y_overrides()
    return [_a_dict(r, perfil_base, overrides) for r in _REGLAS]


def obtener(regla_id: str) -> Optional[dict]:
    r = _POR_ID.get(regla_id)
    if r is None:
        return None
    perfil_base, overrides = _perfil_y_overrides()
    return _a_dict(r, perfil_base, overrides)


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


def _a_dict(r: ReglaInfo, perfil_base: dict, overrides: dict) -> dict:
    alcance = scoring.RULE_SCOPE.get(r.id, "ambas")
    activa = reglas_config.regla_activa(r.id, overrides)

    if not activa:
        estado = "inactiva"
    elif r.motivo_bloqueo:
        estado = "bloqueada"
    elif r.condicion_estructural:
        estado = "condicional"
    else:
        estado = "evaluable"

    # Verde solo si de verdad está puntuando ahora mismo: activa Y con
    # código que la evalúe. Una regla bloqueada (sin implementar) no se
    # pone verde aunque nadie la haya desactivado a mano — no hay nada que
    # activar todavía.
    led = "verde" if activa and estado in ("evaluable", "condicional") else "rojo"

    valores = []
    for ruta in r.config_paths:
        valor_original = reglas_config.valor_efectivo(perfil_base, ruta, {})
        valor_actual = reglas_config.valor_efectivo(perfil_base, ruta, overrides)
        valores.append({
            "ruta": ruta,
            "valor": valor_actual,
            "unidad": _UNIDADES.get(ruta, ""),
            "formateado": _formatear_valor(ruta, valor_actual),
            "valor_original": valor_original,
            "modificado": ruta in overrides.get("umbral", {}),
        })

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
        "activa": activa,
        "led": led,
        "valores": valores,
        "editable": bool(r.config_paths),
    }
