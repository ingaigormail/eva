"""Grabador del log de vuelo.

Toma muestras del simulador a través de un `SimConnector`, detecta los
eventos relevantes (despegue, touchdown, tren, flaps, pausa, aceleración de
tiempo) y escribe un fichero `.avlog.json` conforme a
`docs/formato_log_vuelo.md`.

Muestreo adaptativo
-------------------
Cerca del suelo pasan cosas rápido (rotación, flare, toma) y lejos del suelo
no pasa casi nada. Guardar 1 muestra/segundo durante un vuelo de 3 horas
genera un fichero enorme sin aportar información, así que:

- por debajo de `NEAR_GROUND_AGL_FT` de altura sobre el terreno: 1 muestra/s
- por encima: 1 muestra cada 10 s

La captura del simulador siempre va a 1 Hz; lo que se filtra es qué muestras
se escriben en el log.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from .. import timing
from .. import __version__
from ..connectors.base import SimState
from ..integrity import build_integrity

if TYPE_CHECKING:
    from ..connectors.sim_poller import Reading
from ..schema import (
    ClientInfo,
    DiagnosticsInfo,
    Event,
    FlightLog,
    FlightPlanInfo,
    PayloadInfo,
    PilotInfo,
    SummaryInfo,
    TimingInfo,
    TrackPoint,
)

SCHEMA_VERSION = "1.0"
CLIENT_NAME = "EvA"
#: De `avcars.__version__`, que es la fuente única. Estuvo duplicada aquí y
#: se quedó en 0.1.0 mientras la del paquete iba por otro lado.
CLIENT_VERSION = __version__

LOG_SUFFIX = ".avlog.json"
PARTIAL_SUFFIX = ".parcial"
PARTIAL_PREFIX = "en_curso_"
FILENAME_TIMESTAMP = "%Y-%m-%d_%H-%M-%S"

# Espacio mínimo que se exige antes de escribir. Un vuelo largo con muestreo
# adaptativo ronda los pocos MB, así que 50 MB es margen de sobra; el aviso
# sirve para no llegar a la situación de disco lleno a mitad de vuelo.
MIN_FREE_SPACE_MB = 50.0

# Los tiempos se definen en avcars/timing.py, donde se comprueba que encajan
# entre sí. Aquí solo se les da un nombre local.
NEAR_GROUND_AGL_FT = timing.NEAR_GROUND_AGL_FT
SAMPLE_INTERVAL_NEAR_GROUND_S = timing.SAMPLE_NEAR_GROUND_S
SAMPLE_INTERVAL_CRUISE_S = timing.SAMPLE_CRUISE_S
PAUSE_GAP_S = timing.PAUSE_GAP_S
PAUSE_SUSPICIOUS_S = timing.PAUSE_SUSPICIOUS_S
POLL_INTERVAL_S = timing.POLL_INTERVAL_S

NM_PER_DEG_LAT = 60.0

#: Caracteres que Windows no admite en un nombre de fichero. La barra es el
#: caso que muerde de verdad: un distintivo como "N/A" convertía el vuelo en
#: una carpeta "..._N" con el fichero "A.avlog.json" dentro.
CARACTERES_PROHIBIDOS = '<>:"/\\|?*'


def _safe_filename_part(texto: str) -> str:
    """Deja un texto en condiciones de formar parte de un nombre de fichero."""
    limpio = "".join(
        "-" if c in CARACTERES_PROHIBIDOS or ord(c) < 32 else c
        for c in (texto or "")
    ).strip(" .")
    return limpio or "SIN-DISTINTIVO"


class FlightRecorder:
    """Graba un vuelo en segundo plano y lo vuelca a un `.avlog.json`.

    Uso típico:

        rec = FlightRecorder(connector, pilot, flight_plan, output_dir)
        rec.start()
        ...
        path = rec.stop()
    """

    def __init__(
        self,
        source: Callable[[int], Optional["Reading"]],
        pilot: PilotInfo,
        flight_plan: FlightPlanInfo,
        output_dir: Path,
        simulator: str = "MSFS2024",
        autosave_interval_s: float = 30.0,
        on_sample: Optional[Callable[[SimState], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        # `source(sequence)` devuelve la última lectura del simulador si es
        # posterior al número que se le pasa, o None si no hay nada nuevo.
        # No se recibe el conector directamente porque SimConnect solo puede
        # consultarse desde el hilo que abrió la conexión: de eso se encarga
        # SimPoller, y el grabador se limita a consumir lo que publica.
        self._source = source
        self._pilot = pilot
        self._flight_plan = flight_plan
        self._output_dir = Path(output_dir)
        self._simulator = simulator
        self._autosave_interval_s = autosave_interval_s
        self._on_sample = on_sample
        self._on_error = on_error

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._partial_path: Optional[Path] = None
        self._last_autosave: float = 0.0

        self._track: list[TrackPoint] = []
        self._events: list[Event] = []
        self._timing = TimingInfo()
        self._started_monotonic: float = 0.0
        self._last_state: Optional[SimState] = None
        self._last_written_t: float = -999.0
        self._max_sim_rate: float = 1.0
        self._distance_nm: float = 0.0
        self._initial_fuel_kg: Optional[float] = None
        self._sample_count: int = 0
        self._repeated_count: int = 0
        self._repeated_total: int = 0
        self._longest_repeated_streak: int = 0
        self._process_errors: int = 0
        self._payload: Optional[PayloadInfo] = None

    # -- ciclo de vida -------------------------------------------------

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def elapsed_s(self) -> float:
        """Segundos transcurridos desde que empezó la grabación."""
        if self._started_monotonic == 0.0:
            return 0.0
        return time.monotonic() - self._started_monotonic

    @property
    def track_points(self) -> int:
        return len(self._track)

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    def registrar_payload_aplicado(
        self,
        *,
        requested_passengers: int,
        requested_cargo_kg: float,
        requested_fuel_pct: int,
        aircraft_icao_type: str,
        resultado: dict,
    ) -> None:
        """Guarda en el vuelo lo que `SimConnectConnector.set_payload()` aplicó de verdad.

        `resultado` es el dict que devuelve `set_payload()`: no se reinterpreta,
        se traslada tal cual, porque ese diccionario ya es "lo que de verdad
        pasó" y no hay que volver a decidirlo aquí. Si se aplica más de una
        vez en el mismo vuelo (el piloto cambia de idea a medio vuelo), gana
        la última: es la que describe el avión en el momento de aterrizar.
        """
        self._payload = PayloadInfo(
            requested_passengers=requested_passengers,
            requested_cargo_kg=requested_cargo_kg,
            requested_fuel_pct=requested_fuel_pct,
            aircraft_icao_type=aircraft_icao_type,
            cargo_written_ok=bool(resultado.get("carga", False)),
            applied_cargo_kg=resultado.get("carga_kg"),
            fuel_written_ok=resultado.get("combustible"),
            applied_fuel_kg=resultado.get("combustible_kg"),
            applied_at_utc=_utc_now(),
            note=resultado.get("motivo") or None,
        )

    def start(self) -> None:
        if self.running:
            return
        self._reset()
        self._stop_event.clear()
        self._started_monotonic = time.monotonic()
        self._last_autosave = time.monotonic()
        self._timing.block_off_utc = _utc_now()

        # Fichero de trabajo: se va rellenando durante el vuelo para que un
        # cierre inesperado no se lleve la grabación por delante.
        stamp = datetime.now().strftime(FILENAME_TIMESTAMP)
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            self._partial_path = self._output_dir / self._partial_name(
                stamp, self._pilot.callsign
            )
        except OSError as exc:
            self._partial_path = None
            if self._on_error is not None:
                self._on_error(exc)

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> Optional[Path]:
        """Detiene la grabación y escribe el fichero. Devuelve su ruta."""
        if self._thread is None:
            return None
        self._stop_event.set()
        self._thread.join(timeout=5.0)
        self._thread = None
        self._timing.block_on_utc = _utc_now()
        return self._write_log()

    def check_disk_space(self) -> Optional[float]:
        """MB libres si van justos, None si hay de sobra o no se sabe."""
        from .. import paths

        free = paths.free_space_mb(self._output_dir)
        if free is not None and free < MIN_FREE_SPACE_MB:
            return free
        return None

    def _reset(self) -> None:
        self._track = []
        self._events = []
        self._timing = TimingInfo()
        self._last_state = None
        self._last_written_t = -999.0
        self._max_sim_rate = 1.0
        self._distance_nm = 0.0
        self._initial_fuel_kg = None
        self._sample_count = 0
        self._repeated_count = 0
        self._repeated_total = 0
        self._longest_repeated_streak = 0
        self._process_errors = 0
        self._partial_path = None

    # -- bucle de captura ----------------------------------------------

    def _run(self) -> None:
        """Consume las lecturas que publica el poller, sin reloj propio.

        El grabador no consulta al simulador ni marca su propio ritmo: espera
        a que aparezca una lectura con número nuevo. Así no procesa dos veces
        la misma ni se pierde ninguna, aunque el poller vaya más lento de lo
        previsto porque el simulador esté cargando.
        """
        last_sequence = 0
        last_reading_monotonic = self._started_monotonic

        # Se comprueba más a menudo que la cadencia del poller para no añadir
        # retraso propio al detectar una lectura nueva.
        check_interval = POLL_INTERVAL_S / 4

        while not self._stop_event.is_set():
            try:
                reading = self._source(last_sequence)
            except Exception as exc:  # el simulador puede cerrarse a mitad
                if self._on_error is not None:
                    self._on_error(exc)
                self._stop_event.wait(POLL_INTERVAL_S)
                continue

            if reading is None:
                self._stop_event.wait(check_interval)
                continue

            last_sequence = reading.sequence

            # El poller ya venía publicando antes de que se pulsara grabar.
            # Esa primera lectura es anterior al inicio y produciría un
            # instante negativo en el track.
            if reading.monotonic < self._started_monotonic:
                continue

            now = reading.monotonic
            gap = now - last_reading_monotonic
            last_reading_monotonic = now

            t = now - self._started_monotonic

            # Un fallo procesando una muestra no puede matar el hilo en
            # silencio: eso dejaría al grabador aparentemente vivo pero sin
            # grabar nada, que es justo lo que cuesta descubrir.
            try:
                # `changed` lo calcula el poller comparando con la lectura
                # anterior: la misma información para todos los que consumen.
                self._process(reading.state, t, gap, repeated=not reading.changed)
            except Exception as exc:
                self._process_errors += 1
                if self._on_error is not None:
                    self._on_error(exc)

            if self._on_sample is not None:
                self._on_sample(reading.state)

            if time.monotonic() - self._last_autosave >= self._autosave_interval_s:
                self._autosave()

    def _process(
        self, state: SimState, t: float, gap: float, repeated: bool = False
    ) -> None:
        self._sample_count += 1

        # Lecturas corruptas del simulador: a veces devuelve lat o lon a 0
        # (una petición fallida que el conector degrada a 0.0). Saltar de la
        # posición real a (0, 0) añadiría un tramo de miles de NM, y el punto
        # posterior se mediría contra esa posición falsa. Se descarta la
        # muestra entera sin tocarlo, y la siguiente lectura válida se
        # compara contra la última válida.
        if not _is_valid_position(state):
            return

        # Una lectura repetida no puede disparar eventos: dos estados
        # iguales nunca son una transición. Pero **sí se guarda** como punto
        # del track. Descartarla entera fue un error que dejó un vuelo de 42
        # minutos con un solo punto: el avión estaba ahí, y el tiempo pasó.
        if repeated:
            self._repeated_count += 1
            self._repeated_total += 1
            self._longest_repeated_streak = max(
                self._longest_repeated_streak, self._repeated_count
            )
        else:
            self._repeated_count = 0

        if self._initial_fuel_kg is None and state.fuel_kg:
            self._initial_fuel_kg = state.fuel_kg

        if state.sim_rate > self._max_sim_rate:
            self._max_sim_rate = state.sim_rate
            self._events.append(
                Event(type="sim_rate_change", utc=_utc_now(), rate=state.sim_rate)
            )

        previous = self._last_state
        if previous is not None and not repeated:
            self._distance_nm += _distance_nm(previous, state)
            self._detect_events(previous, state, gap)

        if self._should_write(state, t):
            self._track.append(_to_track_point(state, t))
            self._last_written_t = t

        self._last_state = state

    def _should_write(self, state: SimState, t: float) -> bool:
        near_ground = state.on_ground or state.alt_agl_ft <= NEAR_GROUND_AGL_FT
        interval = (
            SAMPLE_INTERVAL_NEAR_GROUND_S if near_ground else SAMPLE_INTERVAL_CRUISE_S
        )
        return (t - self._last_written_t) >= interval

    def _detect_events(self, previous: SimState, state: SimState, gap: float) -> None:
        now = _utc_now()

        # Pausa del simulador. Un hueco grande entre lecturas **no** basta
        # para afirmar que hubo pausa: en la primera prueba real cada
        # consulta a SimConnect tardaba 3,1 s y eso llenó el log de 27 pausas
        # que nunca ocurrieron.
        #
        # Si el simulador dice explícitamente si está pausado, se le hace
        # caso. Si no, se infiere: hubo pausa si pasó el tiempo y el avión no
        # se movió nada.
        if state.paused is not None:
            paused = state.paused
        else:
            paused = gap > PAUSE_GAP_S and _is_static(previous, state)

        if paused and gap > PAUSE_GAP_S:
            self._events.append(
                Event(type="pause", utc=now, duration_s=round(gap, 1))
            )

        # Despegue: dejamos de tocar el suelo.
        if previous.on_ground and not state.on_ground:
            self._timing.takeoff_utc = now
            self._events.append(
                Event(
                    type="takeoff",
                    utc=now,
                    heading_deg=state.hdg_deg,
                    ias_kt=state.ias_kt,
                )
            )

        # Toma: volvemos a tocar el suelo. La VS del momento del contacto la
        # tomamos de la lectura anterior, que es la del avión aún en el aire.
        if not previous.on_ground and state.on_ground:
            self._timing.touchdown_utc = now
            self._events.append(
                Event(
                    type="touchdown",
                    utc=now,
                    heading_deg=state.hdg_deg,
                    ias_kt=previous.ias_kt,
                    vs_fpm=previous.vs_fpm,
                )
            )

        if previous.gear_down is not None and state.gear_down is not None:
            if previous.gear_down != state.gear_down:
                self._events.append(
                    Event(
                        type="gear_down" if state.gear_down else "gear_up",
                        utc=now,
                        ias_kt=state.ias_kt,
                    )
                )

        if previous.flaps_pct is not None and state.flaps_pct is not None:
            if abs(previous.flaps_pct - state.flaps_pct) >= 1.0:
                self._events.append(
                    Event(
                        type="flap_change",
                        utc=now,
                        position_pct=state.flaps_pct,
                        ias_kt=state.ias_kt,
                    )
                )

    # -- escritura ------------------------------------------------------

    def build_log(self) -> FlightLog:
        """Construye el log con lo grabado hasta ahora.

        Se usa tanto para el fichero definitivo como para los volcados
        periódicos, así que un vuelo interrumpido tiene exactamente la misma
        estructura que uno terminado.

        El hash de la traza se calcula aquí, también en los volcados
        parciales, y no solo al cerrar. Un parcial se puede recuperar como
        vuelo normal (`recover`), y si el hash apareciera únicamente al
        cerrar, los vuelos recuperados serían los únicos sin él: justo los que
        más dudas levantan. Cuesta unos milisegundos cada 30 s sobre una traza
        que en un vuelo de tres horas ronda los pocos miles de puntos.
        """
        self._timing.max_sim_rate_observed = self._max_sim_rate

        last = self._last_state
        fuel_remaining = last.fuel_kg if last is not None else None
        fuel_used = None
        if self._initial_fuel_kg is not None and fuel_remaining is not None:
            fuel_used = round(self._initial_fuel_kg - fuel_remaining, 2)

        flight_minutes = None
        if self._timing.block_off_utc:
            end = self._timing.block_on_utc or _utc_now()
            delta = end - self._timing.block_off_utc
            flight_minutes = round(delta.total_seconds() / 60.0, 1)

        # El hash se calcula sobre la misma lista que se escribe, no sobre
        # `self._track`: el hilo de captura puede añadir un punto entre una
        # lectura y la otra, y el fichero quedaría con un hash que no es el de
        # su traza.
        track = list(self._track)

        return FlightLog(
            schema_version=SCHEMA_VERSION,
            client=ClientInfo(
                name=CLIENT_NAME, version=CLIENT_VERSION, simulator=self._simulator
            ),
            pilot=self._pilot,
            flight_plan=self._flight_plan,
            timing=self._timing,
            events=self._events,
            track=track,
            summary=SummaryInfo(
                total_distance_nm=round(self._distance_nm, 1),
                fuel_used_kg=fuel_used,
                fuel_remaining_kg=round(fuel_remaining, 2)
                if fuel_remaining is not None
                else None,
                flight_time_min=flight_minutes,
            ),
            diagnostics=DiagnosticsInfo(
                samples_total=self._sample_count,
                samples_repeated=self._repeated_total,
                process_errors=self._process_errors,
                longest_repeated_streak=self._longest_repeated_streak,
            ),
            integrity=build_integrity(track),
            payload=self._payload,
        )

    def _target_path(self) -> Path:
        """Nombre definitivo del vuelo, sin pisar ninguno anterior.

        La fecha y la hora van primero para que el explorador de Windows los
        ordene cronológicamente por sí solo.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime(FILENAME_TIMESTAMP)
        callsign = _safe_filename_part(self._pilot.callsign)
        path = self._output_dir / f"{stamp}_{callsign}{LOG_SUFFIX}"

        counter = 2
        while path.exists():
            path = self._output_dir / f"{stamp}_{callsign}_{counter}{LOG_SUFFIX}"
            counter += 1
        return path

    @staticmethod
    def _partial_name(stamp: str, callsign: str) -> str:
        return f"{PARTIAL_PREFIX}{stamp}_{_safe_filename_part(callsign)}{PARTIAL_SUFFIX}"

    def _autosave(self) -> None:
        """Vuelca lo grabado al fichero parcial.

        Si esto falla no se interrumpe la grabación: se avisa y se sigue,
        porque seguir grabando en memoria es mejor que parar.
        """
        if self._partial_path is None:
            return
        try:
            _write_json_atomic(self._partial_path, self.build_log())
            self._last_autosave = time.monotonic()
        except OSError as exc:
            if self._on_error is not None:
                self._on_error(exc)

    def _write_log(self) -> Path:
        """Escribe el fichero definitivo y retira el parcial."""
        path = self._target_path()
        _write_json_atomic(path, self.build_log())

        if self._partial_path is not None:
            try:
                self._partial_path.unlink(missing_ok=True)
            except OSError:
                pass  # dejar un parcial huérfano es preferible a fallar aquí
            self._partial_path = None

        return path


# -- escritura segura ---------------------------------------------------


def _write_json_atomic(path: Path, log: FlightLog) -> None:
    """Escribe el log de forma que nunca quede un fichero a medias.

    Se escribe primero en un fichero temporal y después se renombra. El
    renombrado es atómico en el sistema de ficheros: o está el fichero
    completo, o no está. Si se escribiera directamente sobre el destino, un
    corte a mitad dejaría un JSON truncado que nadie puede leer.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        log.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )
    temporary.replace(path)


# -- recuperación de vuelos interrumpidos -------------------------------


def find_interrupted(output_dir: Path) -> list[Path]:
    """Busca vuelos que quedaron a medias por un cierre inesperado.

    Devuelve los ficheros parciales ordenados del más reciente al más
    antiguo.
    """
    try:
        partials = list(Path(output_dir).glob(f"{PARTIAL_PREFIX}*{PARTIAL_SUFFIX}"))
    except OSError:
        return []
    return sorted(partials, key=lambda p: p.stat().st_mtime, reverse=True)


def describe_interrupted(partial: Path) -> Optional[dict]:
    """Resumen de un vuelo interrumpido, para poder preguntar al piloto.

    Devuelve None si el fichero no es legible: un parcial corrupto no debe
    impedir arrancar.
    """
    try:
        data = json.loads(partial.read_text(encoding="utf-8"))
        log = FlightLog.model_validate(data)
    except (OSError, ValueError):
        return None

    return {
        "callsign": log.pilot.callsign,
        "puntos": len(log.track),
        "minutos": log.summary.flight_time_min if log.summary else None,
        "salida": log.flight_plan.departure_icao,
        "llegada": log.flight_plan.arrival_icao,
    }


def describe_flight(path: Path) -> Optional[dict]:
    """Resumen de un vuelo ya guardado, para enseñárselo al piloto al acabar.

    Se lee del fichero escrito, no de lo que el grabador tenga en memoria: así
    lo que se muestra es exactamente lo que ha quedado en disco, y de paso se
    comprueba que el fichero se puede volver a leer.

    Devuelve None si no es legible.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        log = FlightLog.model_validate(data)
    except (OSError, ValueError):
        return None

    return {
        "ruta": Path(path),
        "callsign": log.pilot.callsign,
        "salida": log.flight_plan.departure_icao,
        "llegada": log.flight_plan.arrival_icao,
        "minutos": log.summary.flight_time_min if log.summary else None,
        "distancia_nm": log.summary.total_distance_nm if log.summary else None,
        "combustible_kg": log.summary.fuel_used_kg if log.summary else None,
        "puntos": len(log.track),
        "eventos": len(log.events),
        "despegue_utc": log.timing.takeoff_utc if log.timing else None,
        "aterrizaje_utc": log.timing.touchdown_utc if log.timing else None,
    }


def recover(partial: Path) -> Optional[Path]:
    """Convierte un vuelo interrumpido en un vuelo normal.

    Devuelve la ruta del fichero recuperado, o None si no se ha podido.
    """
    try:
        data = json.loads(partial.read_text(encoding="utf-8"))
        log = FlightLog.model_validate(data)
    except (OSError, ValueError):
        return None

    # El nombre sale de la fecha del propio parcial, para que el vuelo
    # recuperado conserve la hora a la que ocurrió y no la de hoy.
    stem = partial.name[len(PARTIAL_PREFIX) : -len(PARTIAL_SUFFIX)]
    destination = partial.parent / f"{stem}{LOG_SUFFIX}"

    counter = 2
    while destination.exists():
        destination = partial.parent / f"{stem}_{counter}{LOG_SUFFIX}"
        counter += 1

    try:
        _write_json_atomic(destination, log)
        partial.unlink(missing_ok=True)
    except OSError:
        return None

    return destination


def discard_interrupted(partial: Path) -> bool:
    """Descarta un vuelo interrumpido que el piloto no quiere recuperar."""
    try:
        partial.unlink(missing_ok=True)
        return True
    except OSError:
        return False


# -- utilidades ---------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_static(a: SimState, b: SimState) -> bool:
    """True si el avión no se ha movido nada entre dos lecturas.

    Se compara con tolerancia porque incluso un avión parado en parking
    tiene pequeñas variaciones; lo que interesa es distinguir «congelado»
    de «volando».
    """
    return (
        abs(a.lat - b.lat) < 1e-7
        and abs(a.lon - b.lon) < 1e-7
        and abs(a.alt_msl_ft - b.alt_msl_ft) < 1.0
    )


def _to_track_point(state: SimState, t: float) -> TrackPoint:
    return TrackPoint(
        t=round(t, 1),
        lat=round(state.lat, 6),
        lon=round(state.lon, 6),
        alt_msl_ft=round(state.alt_msl_ft, 1),
        alt_agl_ft=round(state.alt_agl_ft, 1),
        hdg_deg=round(state.hdg_deg, 1),
        gs_kt=round(state.gs_kt, 1),
        ias_kt=round(state.ias_kt, 1),
        vs_fpm=round(state.vs_fpm, 1),
        on_ground=state.on_ground,
        bank_deg=round(state.bank_deg, 1) if state.bank_deg is not None else None,
        pitch_deg=round(state.pitch_deg, 1) if state.pitch_deg is not None else None,
        gear_down=state.gear_down,
        flaps_pct=round(state.flaps_pct, 1) if state.flaps_pct is not None else None,
        qnh_inhg=round(state.qnh_inhg, 3) if state.qnh_inhg is not None else None,
        stall_warning=state.stall_warning,
        overspeed_warning=state.overspeed_warning,
        autopilot_engaged=state.autopilot_engaged,
        fuel_kg=round(state.fuel_kg, 2),
        total_weight_kg=state.total_weight_kg,
        squawk=state.squawk or None,
        transponder_state=state.transponder_state,
        landing_light=state.landing_light,
        beacon_light=state.beacon_light,
        nav_light=state.nav_light,
        taxi_light=state.taxi_light,
        strobe_light=state.strobe_light,
    )


def _is_valid_position(state: SimState) -> bool:
    """True si la posición es plausible para un avión.

    El simulador devuelve a veces lat o lon exactamente a 0.0 en lecturas
    corruptas (el conector degrada a 0.0 un valor que no pudo leer). Un
    avión real en vuelo VFR nunca está en el ecuador ni en el meridiano de
    Greenwich a la vez, así que un 0.0 exacto delata la lectura fallida.
    """
    if state.lat == 0.0 or state.lon == 0.0:
        return False
    return -90.0 <= state.lat <= 90.0 and -180.0 <= state.lon <= 180.0


def _distance_nm(a: SimState, b: SimState) -> float:
    """Distancia aproximada entre dos posiciones, en millas náuticas.

    Aproximación plana con corrección de latitud: a un segundo de vuelo la
    diferencia frente a la fórmula del gran círculo es despreciable, y evita
    depender de una librería geodésica.
    """
    import math

    dlat = b.lat - a.lat
    dlon = b.lon - a.lon
    mean_lat = math.radians((a.lat + b.lat) / 2.0)
    x = dlon * math.cos(mean_lat)
    return math.hypot(dlat, x) * NM_PER_DEG_LAT
