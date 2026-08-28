"""Motor de evaluación de vuelos VFR.

Aplica las reglas de ../../docs/criterios_vfr.md a un `FlightLog` ya cargado
(ver avcars/schema.py) usando los umbrales de un perfil de dificultad
(ver avcars/config.py y config/profiles.yaml).

Implementado en este sprint: alineación de pista en despegue y aterrizaje,
tasa de descenso al touchdown, punto de toma, estabilización a 500 ft AGL,
combustible final, pausas prolongadas, compresión de tiempo, escora
(bank angle) excesiva/sostenida, estados de luces (aterrizaje, beacon, nav,
rodaje, strobe) y sobrevelocidad estructural (VNE/VMO, contra el límite real
del avión — ver `evaluate_flight(..., aircraft=...)`).

Pendiente (requiere ampliar el esquema del log, ver CONTEXT.md): desviación
de ruta, altitud de crucero semicircular, velocidad por debajo de 10.000 ft,
squawk asignado, pista planificada vs. pista real, excursión de pista,
beacon durante rodaje con motores en marcha. Estas reglas aparecen listadas
en `Verdict.not_evaluated` en lugar de fingir que se han comprobado.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import espacio_aereo
from .data_quality import check as check_quality
from datetime import datetime, timedelta

from avcars.config import limite_efectivo
from avcars.connectors.base import TRANSPONDER_ALT, TRANSPONDER_ON
from avcars.schema import Event, FlightLog, TrackPoint


#: Versión del conjunto de reglas. Se guarda con cada vuelo evaluado: sin
#: ella, comparar dos notas obtenidas con criterios distintos induce a error.
#: Subirla cada vez que cambie un umbral o se añada/quite una regla.
RULES_VERSION = "1.0"

#: Ámbito de reglas de vuelo de cada regla: "VFR", "IFR" o "ambas".
#:
#: Hoy EvA solo evalúa VFR, así que este mapa no cambia ningún resultado. Está
#: porque el IFR llegará más adelante (ver D-01 de la especificación
#: funcional), y sin declarar el ámbito desde el principio habría que abrir el
#: motor y revisar regla por regla cuáles siguen valiendo. Con él, añadir IFR
#: es añadir entradas.
#:
#: Casi todo lo implementado hoy es "ambas": las luces, la escora, el QNH o la
#: toma de contacto se evalúan igual con cualquier regla de vuelo. Lo
#: específico de VFR está sobre todo en lo que aún no se evalúa.
RULE_SCOPE: dict[str, str] = {
    "runway_alignment_takeoff": "ambas",
    "runway_alignment_landing": "ambas",
    "touchdown_zone": "ambas",
    "landing_vs": "ambas",
    "stabilized_500ft": "ambas",
    "fuel_reserve": "ambas",
    "pause_duration": "ambas",
    "time_compression": "ambas",
    "bank_angle": "ambas",
    "landing_light_takeoff": "ambas",
    "landing_light_landing": "ambas",
    "beacon_airborne": "ambas",
    "nav_light_airborne": "ambas",
    "taxi_light": "ambas",
    "strobe_airborne": "ambas",
    "stall_warning": "ambas",
    "overspeed_warning": "ambas",
    "qnh": "ambas",
    "gear_on_touchdown": "ambas",
    "airspace_zones": "ambas",
    # Pendientes de implementar, con el ámbito ya declarado.
    "route_deviation": "ambas",
    "cruise_altitude_semicircular": "VFR",
    "speed_below_10000ft": "ambas",
    "assigned_squawk": "ambas",
    "planned_runway_match": "ambas",
    "runway_excursion": "ambas",
    "structural_overspeed": "ambas",
}

#: Ámbito de una regla que no esté en el mapa. "ambas" es el valor prudente:
#: una regla nueva se evalúa hasta que alguien decida lo contrario, en vez de
#: desaparecer sin que nadie se entere.
DEFAULT_SCOPE = "ambas"


def rule_applies(rule: str, flight_rules: str | None) -> bool:
    """True si la regla aplica a las reglas de vuelo del vuelo evaluado."""
    scope = RULE_SCOPE.get(rule, DEFAULT_SCOPE)
    if scope == "ambas" or not flight_rules:
        return True
    return scope == flight_rules.upper()


@dataclass
class VerdictItem:
    rule: str
    passed: bool
    points: int
    detail: str
    # Cuándo y dónde ocurrió. Es lo que permite ordenar las incidencias en una
    # línea de tiempo y pintarlas en un mapa; sin esto una incidencia solo se
    # puede listar, no situar. None cuando la regla no se refiere a un
    # instante concreto (por ejemplo la compresión de tiempo, que es una
    # propiedad de todo el vuelo).
    utc: datetime | None = None
    lat: float | None = None
    lon: float | None = None


@dataclass
class Verdict:
    score: int
    passed: bool
    failed_hard: list[str]
    items: list[VerdictItem]
    not_evaluated: list[str]
    # Calidad de los datos. Si el vuelo no es evaluable, `passed` es False y
    # la puntuación no significa nada: no se aprueba por falta de pruebas.
    quality: object | None = None
    # Reglas que no aplican a este tipo de vuelo. Distinto de
    # `not_evaluated`, que significa "aplica pero falta el dato". Mezclarlas
    # haría creer que falta información cuando en realidad la regla no venía
    # al caso.
    not_applicable: list[str] = field(default_factory=list)
    # Reglas apagadas a mano (ver `evaluation/reglas_config.py`), distinto de
    # `not_evaluated` (aplica pero falta el dato) y de `not_applicable` (no
    # viene al caso para VFR/IFR): aquí sí había datos y sí venía al caso,
    # pero un administrador decidió que no puntuara.
    not_active: list[str] = field(default_factory=list)

    @property
    def evaluable(self) -> bool:
        return self.quality is None or getattr(self.quality, "evaluable", True)

    @property
    def timeline(self) -> list[VerdictItem]:
        """Incidencias con hora, ordenadas cronológicamente.

        Solo las que fallaron: el relato de un vuelo es lo que salió mal, no
        la lista de todo lo que se comprobó.
        """
        located = [i for i in self.items if not i.passed and i.utc is not None]
        return sorted(located, key=lambda i: i.utc)


def _find_event(flight: FlightLog, event_type: str) -> Event | None:
    for ev in flight.events:
        if ev.type == event_type:
            return ev
    return None


def _utc_for_track_point(flight: FlightLog, point: TrackPoint) -> datetime | None:
    """Calcula la hora UTC de un punto de `track` a partir de `timing.block_off_utc` + `t`."""
    if flight.timing is None or flight.timing.block_off_utc is None:
        return None
    return flight.timing.block_off_utc + timedelta(seconds=point.t)


def _nearest_track_point(
    flight: FlightLog, target_utc: datetime, tolerance_s: float
) -> TrackPoint | None:
    """Busca el punto de `track` más cercano en el tiempo a `target_utc`, dentro de `tolerance_s`."""
    best: TrackPoint | None = None
    best_diff: float | None = None
    for point in flight.track:
        point_utc = _utc_for_track_point(flight, point)
        if point_utc is None:
            continue
        diff = abs((point_utc - target_utc).total_seconds())
        if diff <= tolerance_s and (best_diff is None or diff < best_diff):
            best, best_diff = point, diff
    return best


def _at(item: VerdictItem, flight: FlightLog, point: TrackPoint | None) -> VerdictItem:
    """Sitúa una incidencia en el punto del vuelo donde ocurrió.

    Se devuelve el mismo objeto para poder encadenarlo en el `append`. Si no
    hay punto, la incidencia se queda sin situar en vez de inventarse una
    posición.
    """
    if point is not None:
        item.utc = _utc_for_track_point(flight, point)
        item.lat = point.lat
        item.lon = point.lon
    return item


#: Ventana para SITUAR una incidencia en el mapa, distinta de la que se usa
#: para JUZGAR.
#:
#: No son lo mismo y conviene no confundirlas. Para decidir si el tren estaba
#: abajo en la toma hace falta un punto muy cercano al instante (5 s): usar
#: uno de medio minuto antes respondería sobre otro momento del vuelo y podría
#: cambiar el veredicto. Para pintar un alfiler en un mapa, en cambio, errar
#: unos segundos solo desplaza el alfiler un poco: no altera ninguna nota,
#: porque situar ocurre cuando la incidencia ya está decidida.
#:
#: Con muestreo de 1 Hz cerca del suelo —que es donde caen casi todos los
#: eventos— siempre hay un punto a menos de un segundo. Esta ventana ancha
#: solo entra en juego con trazas muy pobres.
LOCATION_TOLERANCE_S = 60.0


def _at_utc(
    item: VerdictItem,
    flight: FlightLog,
    utc: datetime | None,
    tolerance_s: float = LOCATION_TOLERANCE_S,
) -> VerdictItem:
    """Sitúa una incidencia a partir de una hora, buscando el punto más cercano.

    La hora sale del evento y es exacta. La posición es lo mejor que da la
    traza: si no hay ningún punto cerca, se queda sin posición en vez de
    inventarse una.
    """
    if utc is None:
        return item
    item.utc = utc
    point = _nearest_track_point(flight, utc, tolerance_s)
    if point is not None:
        item.lat = point.lat
        item.lon = point.lon
    return item


def _first(points: list[TrackPoint], predicate) -> TrackPoint | None:
    """Primer punto que cumple la condición. Sirve para señalar dónde empezó algo."""
    for point in points:
        if predicate(point):
            return point
    return None


def _evaluate_bank_angle(
    flight: FlightLog, profile: dict
) -> tuple[list[VerdictItem], list[str], bool]:
    """Evalúa escora excesiva (FAIL) y sostenida (penalización). Ver criterios_vfr.md."""
    cfg = profile.get("bank_angle")
    samples = [p for p in flight.track if p.bank_deg is not None]
    if not cfg or not samples:
        return [], [], True  # not evaluado: falta configuración o datos

    max_bank = max(abs(p.bank_deg) for p in samples)
    if max_bank > cfg["fail_deg"]:
        item = VerdictItem(
            "bank_angle", False, 0,
            f"máximo {max_bank:.0f}° (límite {cfg['fail_deg']}°) - escora excesiva",
        )
        # Se sitúa donde se alcanzó la escora máxima, que es el momento que
        # el piloto necesita revisar.
        worst = _first(samples, lambda p: abs(p.bank_deg) == max_bank)
        return [_at(item, flight, worst)], ["excessive_bank_angle"], False

    consecutive = 0
    sustained = False
    sustained_start: TrackPoint | None = None
    for point in samples:
        if abs(point.bank_deg) > cfg["warn_deg"]:
            consecutive += 1
            if consecutive >= cfg["sustained_samples"] and not sustained:
                sustained = True
                sustained_start = point
        else:
            consecutive = 0

    pts = profile["penalties"]["sustained_bank_angle"] if sustained else 0
    detail = f"máximo {max_bank:.0f}° (aviso {cfg['warn_deg']}°)"
    if sustained:
        detail += ", sostenida"
    item = VerdictItem("bank_angle", not sustained, pts, detail)
    # Si fue sostenida, interesa dónde se confirmó; si no, dónde escoró más.
    anchor = sustained_start or _first(samples, lambda p: abs(p.bank_deg) == max_bank)
    return [_at(item, flight, anchor)], [], False


def _evaluate_airspace(
    flight: FlightLog, profile: dict, zonas: list | None = None
) -> tuple[list[VerdictItem], list[str], bool]:
    """Evalúa si el vuelo se metió en zonas P, R, D o de prohibición VFR.

    `zonas` viene de fuera (`espacio_aereo.cargar_zonas()`) y no se carga
    aquí: el motor vive en el cliente y la base de espacio aéreo en el
    servidor, que es quien evalúa. Sin ella la regla queda en
    `not_evaluated`, igual que `structural_overspeed` sin `aircraft`.

    Los datos son de ENAIRE, oficiales y con ciclo AIRAC, pero la traza en
    crucero solo guarda un punto cada 10 s: esto detecta travesías, no roces.
    Por eso **penaliza y no suspende**. Cuando lleve unos meses funcionando y
    se sepa que no da falsos positivos, subirlo a fallo duro es cambiar una
    línea.
    """
    cfg = profile.get("airspace")
    if not cfg or not zonas or not flight.track:
        return [], [], True

    invasiones = espacio_aereo.invasiones(
        flight.track,
        zonas,
        margen_nm=cfg.get("margen_nm", 0.5),
        permanencia_s=cfg.get("permanencia_s", 20.0),
        muestras_minimas=cfg.get("muestras_minimas", 2),
    )
    if not invasiones:
        return [
            VerdictItem("airspace_zones", True, 0, "sin invasiones de zona")
        ], [], False

    # Una sola entrada, aunque haya varias zonas: al piloto le sirve más
    # "invadiste estas dos" que dos apuntes sueltos que no sabe relacionar.
    peor = max(invasiones, key=lambda i: i.duracion_s)
    detalle = "; ".join(
        f"{i.zona.etiqueta} [{i.zona.capa}] {i.duracion_s:.0f}s a "
        f"{i.altitud_ft:.0f} ft"
        for i in invasiones[:3]
    )
    if len(invasiones) > 3:
        detalle += f"; y {len(invasiones) - 3} más"

    pts = profile["penalties"]["airspace_intrusion"] * len(invasiones)
    pts = min(pts, cfg.get("penalizacion_maxima", 40))
    item = VerdictItem("airspace_zones", False, pts, detalle)
    # Se sitúa donde empezó la peor invasión, que es el momento que el piloto
    # tiene que ir a revisar en la traza.
    entrada = _first(flight.track, lambda p: p.t >= peor.t_entrada)
    return [_at(item, flight, entrada)], [], False


def _evaluate_warnings_and_config(
    flight: FlightLog, profile: dict, aircraft: dict | None = None
) -> tuple[list[VerdictItem], list[str], bool]:
    """Evalúa avisos del simulador (stall/overspeed), QNH y tren en la toma.

    Stall y overspeed ya no se fingen como "not_evaluated": el conector graba
    los avisos del simulador en el track, así que si hay dato se evalúa. Si
    no hay dato (fixture antiguo o simulador sin esa variable) se reporta
    como no evaluado.
    """
    cfg = profile.get("qnh")
    penalties = profile["penalties"]
    items: list[VerdictItem] = []
    failed_hard: list[str] = []
    not_evaluated: list[str] = []

    # Aviso de stall: es condición de fallo inmediato (FAIL).
    stall_samples = [p for p in flight.track if p.stall_warning is not None]
    if stall_samples:
        triggered = any(p.stall_warning for p in stall_samples)
        if triggered:
            failed_hard.append("stall_warning_triggered")
        items.append(_at(
            VerdictItem(
                "stall_warning", not triggered, penalties.get("stall_warning", 0),
                "stall warning disparado" if triggered else "sin aviso de stall",
            ),
            flight,
            _first(stall_samples, lambda p: p.stall_warning) if triggered else None,
        ))
    else:
        not_evaluated.append("stall_warning")

    # Aviso de overspeed: es la detección del overspeed estructural, FAIL.
    overspeed_samples = [p for p in flight.track if p.overspeed_warning is not None]
    if overspeed_samples:
        triggered = any(p.overspeed_warning for p in overspeed_samples)
        if triggered:
            failed_hard.append("overspeed_warning_triggered")
        items.append(_at(
            VerdictItem(
                "overspeed_warning", not triggered, 0,
                "overspeed warning disparado" if triggered else "sin aviso de overspeed",
            ),
            flight,
            _first(overspeed_samples, lambda p: p.overspeed_warning) if triggered else None,
        ))
    else:
        not_evaluated.append("overspeed_warning")

    # Sobrevelocidad estructural: IAS por encima del limite certificado
    # (POH real si existe; referencia del simulador solo si no hay POH -
    # ver `avcars.config.limite_efectivo`). Independiente de
    # `overspeed_warning`: aquella confia en el aviso interno del propio
    # simulador, esta compara contra el limite de verdad del avion. No
    # comprueba MMO: el log no guarda numero de Mach, y no se inventa uno
    # a partir de IAS/altitud.
    if aircraft is not None:
        limite, fuente = limite_efectivo(aircraft, "vmo")
        if limite is None or limite == "no_aplica":
            limite, fuente = limite_efectivo(aircraft, "vne")
        if isinstance(limite, (int, float)):
            ias_samples = [p for p in flight.track if p.ias_kt is not None]
            over = [p for p in ias_samples if p.ias_kt > limite]
            if over:
                peor = max(over, key=lambda p: p.ias_kt)
                failed_hard.append("structural_overspeed")
                items.append(_at(
                    VerdictItem(
                        "structural_overspeed", False, 0,
                        f"{peor.ias_kt} kt IAS > limite {limite} kt "
                        f"(fuente: {fuente})",
                    ),
                    flight, peor,
                ))
            elif ias_samples:
                items.append(_at(
                    VerdictItem(
                        "structural_overspeed", True, 0,
                        f"maximo observado dentro del limite {limite} kt "
                        f"(fuente: {fuente})",
                    ),
                    flight, None,
                ))
            else:
                not_evaluated.append("structural_overspeed")
        else:
            # Ni POH ni simulador dan un limite usable (None o "no_aplica"
            # en ambas fuentes): no hay con que comparar.
            not_evaluated.append("structural_overspeed")
    else:
        not_evaluated.append("structural_overspeed")

    # QNH fuera de rango plausible.
    qnh_samples = [p for p in flight.track if p.qnh_inhg is not None]
    if cfg and qnh_samples:
        out_of_range = [
            p for p in qnh_samples
            if not (cfg["min_inhg"] <= p.qnh_inhg <= cfg["max_inhg"])
        ]
        pts = penalties.get("qnh_out_of_range", 0) if out_of_range else 0
        items.append(_at(
            VerdictItem(
                "qnh", not out_of_range, pts,
                f"QNH {qnh_samples[-1].qnh_inhg} inHg (rango {cfg['min_inhg']}–{cfg['max_inhg']})",
            ),
            flight,
            out_of_range[0] if out_of_range else None,
        ))
    else:
        not_evaluated.append("qnh")

    # Tren arriba en el touchdown.
    touchdown = _find_event(flight, "touchdown")
    if touchdown is not None and touchdown.utc is not None:
        point = _nearest_track_point(flight, touchdown.utc, 5.0)
        if point is not None and point.gear_down is not None:
            # Detectar si es avión de tren fijo: si gear_down es siempre True,
            # probablemente sea un C172 u otro avión de tren fijo.
            gear_samples = [p.gear_down for p in flight.track if p.gear_down is not None]
            is_fixed_gear = gear_samples and all(gear_samples)

            if is_fixed_gear:
                # Avión de tren fijo: no evaluar este criterio
                not_evaluated.append("gear_on_touchdown")
            else:
                ok = point.gear_down
                pts = penalties.get("gear_up_touchdown", 0) if not ok else 0
                items.append(_at(
                    VerdictItem(
                        "gear_on_touchdown", ok, pts,
                        "tren abajo en la toma" if ok else "tren arriba en la toma",
                    ),
                    flight,
                    point,
                ))
        else:
            not_evaluated.append("gear_on_touchdown")
    else:
        not_evaluated.append("gear_on_touchdown")

    return items, failed_hard, not_evaluated


def _evaluate_lights(flight: FlightLog, profile: dict) -> tuple[list[VerdictItem], bool]:
    """Evalúa el uso de luces (aterrizaje, beacon, nav, rodaje, strobe). Ver criterios_vfr.md."""
    cfg = profile.get("lights")
    if not cfg:
        return [], True

    items: list[VerdictItem] = []
    evaluated_any = False
    tolerance = cfg["check_tolerance_s"]
    penalties = profile["penalties"]

    for event_type, rule_name in (("takeoff", "landing_light_takeoff"), ("touchdown", "landing_light_landing")):
        event = _find_event(flight, event_type)
        if event is None or event.utc is None:
            continue
        point = _nearest_track_point(flight, event.utc, tolerance)
        if point is None or point.landing_light is None:
            continue
        evaluated_any = True
        ok = point.landing_light
        pts = 0 if ok else penalties["landing_light_off"]
        items.append(_at(
            VerdictItem(rule_name, ok, pts, f"encendida={point.landing_light}"),
            flight, point,
        ))

    airborne = [p for p in flight.track if not p.on_ground]

    with_beacon = [p for p in airborne if p.beacon_light is not None]
    if with_beacon:
        evaluated_any = True
        ok = all(p.beacon_light for p in with_beacon)
        pts = 0 if ok else penalties["beacon_off_airborne"]
        items.append(_at(
            VerdictItem(
                "beacon_airborne", ok, pts,
                "beacon encendido todo el vuelo" if ok else "beacon apagado en algún punto del vuelo",
            ),
            flight,
            # Se señala el primer momento en que estaba apagado, que es
            # cuando el piloto tenía que haberlo encendido.
            None if ok else _first(with_beacon, lambda p: not p.beacon_light),
        ))

    with_nav = [p for p in airborne if p.nav_light is not None]
    if with_nav:
        evaluated_any = True
        ok = all(p.nav_light for p in with_nav)
        pts = 0 if ok else penalties["nav_light_off_airborne"]
        items.append(_at(
            VerdictItem(
                "nav_light_airborne", ok, pts,
                "luces de navegación encendidas todo el vuelo" if ok else "luces de navegación apagadas en algún punto",
            ),
            flight,
            None if ok else _first(with_nav, lambda p: not p.nav_light),
        ))

    taxiing = [p for p in flight.track if p.on_ground and p.gs_kt > 2]

    with_taxi = [p for p in taxiing if p.taxi_light is not None]
    if with_taxi:
        evaluated_any = True
        ok = all(p.taxi_light for p in with_taxi)
        pts = 0 if ok else penalties["taxi_light_off"]
        items.append(_at(
            VerdictItem(
                "taxi_light", ok, pts,
                "luz de rodaje correcta" if ok else "luz de rodaje apagada mientras rodaba",
            ),
            flight,
            None if ok else _first(with_taxi, lambda p: not p.taxi_light),
        ))

    # Transpondedor puesto en vuelo. En IVAO y en VATSIM se vuela con el
    # transpondedor transmitiendo: si va apagado o en espera, el resto del
    # tráfico y el control no ven al avión. `mode_charlie` da por bueno ON
    # y ALT (ver `SimState.mode_charlie`).
    with_xpdr = [p for p in airborne if p.transponder_state is not None]
    if with_xpdr:
        evaluated_any = True
        ok = all(
            p.transponder_state in (TRANSPONDER_ON, TRANSPONDER_ALT)
            for p in with_xpdr
        )
        pts = 0 if ok else penalties["transponder_off_airborne"]
        items.append(_at(
            VerdictItem(
                "transponder_airborne", ok, pts,
                "transpondedor puesto en vuelo" if ok
                else "transpondedor apagado o en espera en algún punto del vuelo",
            ),
            flight,
            None if ok else _first(
                with_xpdr,
                lambda p: p.transponder_state not in (TRANSPONDER_ON, TRANSPONDER_ALT),
            ),
        ))

    # Estrobos: se mira que estén **encendidos en el aire**, no que estén
    # apagados rodando. Antes era al revés (`strobe_taxi`) y se cambió por
    # decisión de la aerolínea el 2026-08-25: de las luces, la única que
    # penaliza es esta.
    with_strobe = [p for p in airborne if p.strobe_light is not None]
    if with_strobe:
        evaluated_any = True
        ok = all(p.strobe_light for p in with_strobe)
        pts = 0 if ok else penalties["strobe_wrong_state"]
        items.append(_at(
            VerdictItem(
                "strobe_airborne", ok, pts,
                "estrobos encendidos en vuelo" if ok else "estrobos apagados en algún punto del vuelo",
            ),
            flight,
            None if ok else _first(with_strobe, lambda p: not p.strobe_light),
        ))

    return items, not evaluated_any


#: `failed_hard` usa sus propios nombres de motivo, no el id de la regla
#: (p.ej. "landing_vs_very_hard" en vez de "landing_vs"): hace falta este
#: mapa para poder filtrar por regla desactivada. Si se añade un fallo duro
#: nuevo, hay que añadirlo aquí también — si no, una regla desactivada
#: podría seguir tirando el vuelo por un fallo duro que no debería contar.
_MOTIVO_FALLO_DURO_A_REGLA: dict[str, str] = {
    "stall_warning_triggered": "stall_warning",
    "overspeed_warning_triggered": "overspeed_warning",
    "structural_overspeed": "structural_overspeed",
    "landing_vs_very_hard": "landing_vs",
    "time_compression_used": "time_compression",
    "excessive_bank_angle": "bank_angle",
}


def evaluate_flight(
    flight: FlightLog,
    profile: dict,
    aircraft: dict | None = None,
    reglas_activas: dict[str, bool] | None = None,
    zonas: list | None = None,
) -> Verdict:
    """Evalúa un vuelo y devuelve el veredicto (puntuación, aprobado/suspendido, desglose).

    `aircraft` es el bloque de ESE avión en `aircraft.yaml` (ya resuelto por
    el llamador via `flight.flight_plan.aircraft_icao_type`), no el fichero
    entero — igual que `profile` ya llega resuelto, no el fichero de
    perfiles completo. Opcional: sin él, `structural_overspeed` queda en
    `not_evaluated`, como si no existiera este parámetro.

    `zonas` son las zonas de espacio aéreo de `espacio_aereo.cargar_zonas()`.
    Vienen de fuera porque la base la tiene el servidor, que es quien evalúa,
    y el motor vive en el cliente. Sin ellas `airspace_zones` queda en
    `not_evaluated`, igual que `structural_overspeed` sin `aircraft`.

    `reglas_activas` es el `{regla_id: bool}` de
    `evaluation/reglas_config.py` — qué reglas ha apagado un administrador.
    Una regla ausente del dict se trata como activa: por defecto todo
    puntúa, hasta que alguien decida apagarlo explícitamente. Opcional: sin
    él, se comporta exactamente igual que antes de que existiera esto.
    """
    score = 100
    items: list[VerdictItem] = []
    failed_hard: list[str] = []
    not_evaluated: list[str] = [
        "route_deviation",
        "cruise_altitude_semicircular",
        "speed_below_10000ft",
        "assigned_squawk",
        "planned_runway_match",
        "runway_excursion",
    ]

    takeoff = _find_event(flight, "takeoff")
    if takeoff is not None and takeoff.runway_alignment_deg is not None:
        max_deg = profile["runway_alignment_deg_max"]
        ok = abs(takeoff.runway_alignment_deg) <= max_deg
        pts = 0 if ok else profile["penalties"]["runway_alignment_takeoff"]
        score -= pts
        items.append(_at_utc(
            VerdictItem(
                "runway_alignment_takeoff", ok, pts,
                f"{takeoff.runway_alignment_deg}° (máx {max_deg}°)",
            ),
            flight, takeoff.utc,
        ))
    else:
        not_evaluated.append("runway_alignment_takeoff")

    touchdown = _find_event(flight, "touchdown")
    if touchdown is not None:
        if touchdown.runway_alignment_deg is not None:
            max_deg = profile["runway_alignment_deg_max"]
            ok = abs(touchdown.runway_alignment_deg) <= max_deg
            pts = 0 if ok else profile["penalties"]["runway_alignment_landing"]
            score -= pts
            items.append(_at_utc(
                VerdictItem(
                    "runway_alignment_landing", ok, pts,
                    f"{touchdown.runway_alignment_deg}° (máx {max_deg}°)",
                ),
                flight, touchdown.utc,
            ))

        if touchdown.distance_from_threshold_m is not None:
            max_m = profile["touchdown_zone_m_max"]
            ok = touchdown.distance_from_threshold_m <= max_m
            pts = 0 if ok else profile["penalties"]["touchdown_zone_exceeded"]
            score -= pts
            items.append(_at_utc(
                VerdictItem(
                    "touchdown_zone", ok, pts,
                    f"{touchdown.distance_from_threshold_m} m (máx {max_m} m)",
                ),
                flight, touchdown.utc,
            ))

        if touchdown.vs_fpm is not None:
            bands = profile["landing_vs_bands"]
            vs_abs = abs(touchdown.vs_fpm)
            if vs_abs <= bands["butter"]["max_fpm"]:
                band, pts = "butter", bands["butter"]["points"]
            elif vs_abs <= bands["smooth"]["max_fpm"]:
                band, pts = "smooth", bands["smooth"]["points"]
            elif vs_abs <= bands["normal"]["max_fpm"]:
                band, pts = "normal", bands["normal"]["points"]
            elif vs_abs <= bands["hard"]["max_fpm"]:
                band, pts = "hard", bands["hard"]["points"]
            else:
                band, pts = "very_hard", 0
                failed_hard.append("landing_vs_very_hard")
            score -= pts
            items.append(_at_utc(
                VerdictItem(
                    "landing_vs", band != "very_hard", pts,
                    f"{touchdown.vs_fpm} fpm ({band})",
                ),
                flight, touchdown.utc,
            ))
    else:
        not_evaluated += ["runway_alignment_landing", "touchdown_zone", "landing_vs"]

    stab = profile["stabilization"]
    candidates = [
        p for p in flight.track
        if not p.on_ground
        and abs(p.alt_agl_ft - stab["alt_agl_ft"]) <= stab["alt_agl_tolerance_ft"]
    ]
    if candidates:
        point = candidates[-1]
        ok = stab["vs_fpm_min"] <= point.vs_fpm <= stab["vs_fpm_max"]
        pts = 0 if ok else profile["penalties"]["not_stabilized_500ft"]
        score -= pts
        items.append(_at(
            VerdictItem(
                "stabilized_500ft", ok, pts,
                f"vs={point.vs_fpm} fpm a {point.alt_agl_ft} ft AGL",
            ),
            flight, point,
        ))
    else:
        not_evaluated.append("stabilized_500ft")

    if flight.summary is not None and flight.summary.fuel_remaining_kg is not None:
        min_kg = profile["fuel_reserve_kg_min"]
        ok = flight.summary.fuel_remaining_kg >= min_kg
        pts = 0 if ok else profile["penalties"]["fuel_below_reserve"]
        score -= pts
        items.append(_at(
            VerdictItem(
                "fuel_reserve", ok, pts,
                f"{flight.summary.fuel_remaining_kg} kg (mín {min_kg} kg)",
            ),
            # El combustible se juzga al final del vuelo: se sitúa en el
            # último punto grabado.
            flight, flight.track[-1] if flight.track else None,
        ))
    else:
        not_evaluated.append("fuel_reserve")

    max_pause = profile["pause_duration_s_max"]
    for ev in flight.events:
        if ev.type == "pause" and ev.duration_s is not None:
            ok = ev.duration_s <= max_pause
            pts = 0 if ok else profile["penalties"]["pause_exceeded"]
            score -= pts
            items.append(_at_utc(
                VerdictItem(
                    "pause_duration", ok, pts,
                    f"{ev.duration_s}s (máx {max_pause}s)",
                ),
                flight, ev.utc,
            ))

    if flight.timing is not None and flight.timing.max_sim_rate_observed is not None:
        ok = flight.timing.max_sim_rate_observed <= 1
        if not ok:
            failed_hard.append("time_compression_used")
        items.append(VerdictItem(
            "time_compression", ok, 0,
            f"rate máximo observado: {flight.timing.max_sim_rate_observed}x",
        ))
    else:
        not_evaluated.append("time_compression")

    bank_items, bank_fails, bank_not_evaluated = _evaluate_bank_angle(flight, profile)
    items += bank_items
    failed_hard += bank_fails
    for item in bank_items:
        score -= item.points
    if bank_not_evaluated:
        not_evaluated.append("bank_angle")

    aire_items, aire_fails, aire_not_evaluated = _evaluate_airspace(
        flight, profile, zonas
    )
    items += aire_items
    failed_hard += aire_fails
    for item in aire_items:
        score -= item.points
    if aire_not_evaluated:
        not_evaluated.append("airspace_zones")

    light_items, lights_not_evaluated = _evaluate_lights(flight, profile)
    items += light_items
    for item in light_items:
        score -= item.points
    if lights_not_evaluated:
        not_evaluated.append("lights")

    warn_items, warn_fails, warn_not_evaluated = _evaluate_warnings_and_config(
        flight, profile, aircraft
    )
    items += warn_items
    failed_hard += warn_fails
    for item in warn_items:
        score -= item.points
    not_evaluated += warn_not_evaluated

    # Reglas que no vienen al caso para este tipo de vuelo. Hoy no aparta
    # ninguna, porque todo lo implementado aplica a VFR y a IFR; existe para
    # que añadir criterios IFR más adelante no obligue a rehacer el motor.
    flight_rules = flight.flight_plan.rules if flight.flight_plan else None
    not_applicable = [r for r in not_evaluated if not rule_applies(r, flight_rules)]
    not_evaluated = [r for r in not_evaluated if r not in not_applicable]

    discarded = [i for i in items if not rule_applies(i.rule, flight_rules)]
    if discarded:
        # Se devuelven los puntos de una regla que no debía haberse aplicado.
        for item in discarded:
            score += item.points
        not_applicable += [i.rule for i in discarded]
        items = [i for i in items if rule_applies(i.rule, flight_rules)]

    # Reglas apagadas a mano. Mismo patrón que el filtro de arriba: se
    # aparta lo que sobra y se devuelven los puntos, para que una regla
    # desactivada no pueda afectar a la nota ni al aprobado/suspendido.
    reglas_activas = reglas_activas or {}

    def _activa(regla_id: str) -> bool:
        return reglas_activas.get(regla_id, True)

    not_active = [r for r in not_evaluated if not _activa(r)]
    not_evaluated = [r for r in not_evaluated if r not in not_active]

    discarded_inactive = [i for i in items if not _activa(i.rule)]
    if discarded_inactive:
        for item in discarded_inactive:
            score += item.points
        not_active += [i.rule for i in discarded_inactive]
        items = [i for i in items if _activa(i.rule)]

    failed_hard = [
        motivo for motivo in failed_hard
        if _activa(_MOTIVO_FALLO_DURO_A_REGLA.get(motivo, motivo))
    ]

    score = max(0, score)

    # Un vuelo cuyos datos no dan la talla no aprueba: sacaría buena nota
    # solo porque no hay pruebas de nada, que es justo lo contrario de
    # evaluar. Ver evaluation/data_quality.py.
    quality = check_quality(flight)
    passed = (
        score >= profile["pass_score"] and not failed_hard and quality.evaluable
    )

    return Verdict(
        score=score,
        passed=passed,
        failed_hard=failed_hard,
        items=items,
        not_evaluated=not_evaluated,
        quality=quality,
        not_applicable=not_applicable,
        not_active=not_active,
    )
