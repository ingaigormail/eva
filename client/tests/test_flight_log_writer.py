"""Tests del grabador de vuelo.

Se usa un conector falso que reproduce una secuencia de estados prefijada, de
modo que el grabador se puede probar sin simulador: es la misma interfaz
(`SimConnector`) que implementan SimConnect y X-Plane.
"""
import json

from avcars.connectors.base import SimConnector, SimState
from avcars.connectors.sim_poller import Reading
from avcars.recorder.flight_log_writer import FlightRecorder, _distance_nm, _to_track_point
from avcars.schema import FlightLog, FlightPlanInfo, PilotInfo


def _state(**overrides) -> SimState:
    base = dict(
        lat=40.4719,
        lon=-3.5626,
        alt_msl_ft=2000.0,
        alt_agl_ft=0.0,
        hdg_deg=182.0,
        gs_kt=0.0,
        ias_kt=0.0,
        vs_fpm=0.0,
        on_ground=True,
        fuel_kg=150.0,
        squawk="7000",
        sim_rate=1.0,
        bank_deg=0.0,
    )
    base.update(overrides)
    return SimState(**base)


class FakeConnector(SimConnector):
    """Devuelve una secuencia fija de estados; repite el último al agotarse."""

    def __init__(self, states: list[SimState]) -> None:
        self.states = states
        self.index = 0

    def connect(self) -> None:  # pragma: no cover - nada que hacer
        pass

    def disconnect(self) -> None:  # pragma: no cover - nada que hacer
        pass

    def poll(self) -> SimState:
        state = self.states[min(self.index, len(self.states) - 1)]
        self.index += 1
        return state


class FakeSource:
    """Imita a `SimPoller.reading_after`: entrega lecturas numeradas.

    El grabador consume lecturas con número de orden, no estados sueltos:
    así no procesa dos veces la misma ni se pierde ninguna.
    """

    def __init__(self, states: list[SimState]) -> None:
        self.states = states
        self.sequence = 0

    def __call__(self, since: int):
        if self.sequence >= len(self.states):
            return None  # no hay nada nuevo

        state = self.states[self.sequence]
        previous = self.states[self.sequence - 1] if self.sequence else None
        self.sequence += 1

        return Reading(
            sequence=self.sequence,
            state=state,
            monotonic=float(self.sequence),
            changed=previous is None or _differs(previous, state),
        )


def _differs(a: SimState, b: SimState) -> bool:
    return (a.lat, a.lon, a.alt_msl_ft, a.gs_kt) != (b.lat, b.lon, b.alt_msl_ft, b.gs_kt)


def _recorder(states: list[SimState], tmp_path) -> FlightRecorder:
    return FlightRecorder(
        source=FakeSource(states),
        pilot=PilotInfo(license_id="AVH-1", callsign="AVH100"),
        flight_plan=FlightPlanInfo(
            rules="VFR",
            departure_icao="LEMD",
            arrival_icao="LEBL",
            network="OFFLINE",
            atc_controlled=False,
        ),
        output_dir=tmp_path,
    )


def test_takeoff_and_touchdown_events_are_detected(tmp_path):
    states = [
        _state(on_ground=True, ias_kt=0),
        _state(on_ground=False, alt_agl_ft=50, ias_kt=70, vs_fpm=700),
        _state(on_ground=False, alt_agl_ft=40, ias_kt=68, vs_fpm=-150),
        _state(on_ground=True, alt_agl_ft=0, ias_kt=60),
    ]
    rec = _recorder(states, tmp_path)
    rec._started_monotonic = 0.0

    for i, state in enumerate(states):
        rec._process(state, t=float(i), gap=1.0)

    types = [e.type for e in rec.events]
    assert "takeoff" in types
    assert "touchdown" in types

    touchdown = next(e for e in rec.events if e.type == "touchdown")
    # La VS del contacto se toma de la lectura anterior, aún en el aire.
    assert touchdown.vs_fpm == -150


def test_adaptive_sampling_writes_less_in_cruise(tmp_path):
    rec = _recorder([_state()], tmp_path)
    rec._started_monotonic = 0.0

    cruise = _state(on_ground=False, alt_agl_ft=8000.0)
    for second in range(20):
        rec._process(cruise, t=float(second), gap=1.0)

    # 20 segundos en crucero a 1 muestra/10 s -> 2 o 3 puntos, no 20.
    assert len(rec._track) <= 3

    rec2 = _recorder([_state()], tmp_path)
    rec2._started_monotonic = 0.0
    low = _state(on_ground=False, alt_agl_ft=300.0)
    for second in range(20):
        rec2._process(low, t=float(second), gap=1.0)

    assert len(rec2._track) >= 19


def test_time_compression_is_recorded(tmp_path):
    rec = _recorder([_state()], tmp_path)
    rec._started_monotonic = 0.0

    rec._process(_state(), t=0.0, gap=1.0)
    rec._process(_state(sim_rate=4.0), t=1.0, gap=1.0)

    assert rec._max_sim_rate == 4.0
    assert any(e.type == "sim_rate_change" for e in rec.events)


def test_pause_is_detected_from_wall_clock_gap(tmp_path):
    rec = _recorder([_state()], tmp_path)
    rec._started_monotonic = 0.0

    rec._process(_state(), t=0.0, gap=1.0)
    rec._process(_state(), t=1.0, gap=30.0)

    pause = next(e for e in rec.events if e.type == "pause")
    assert pause.duration_s == 30.0


def test_written_log_validates_against_schema(tmp_path):
    rec = _recorder([_state()], tmp_path)
    rec._started_monotonic = 0.0
    rec._timing.block_off_utc = None

    rec._process(_state(), t=0.0, gap=1.0)
    rec._process(_state(on_ground=False, alt_agl_ft=100, ias_kt=70), t=1.0, gap=1.0)

    path = rec._write_log()
    assert path.exists()
    assert path.name.endswith(".avlog.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    log = FlightLog.model_validate(data)
    assert log.client.name == "EvA"
    assert log.pilot.callsign == "AVH100"
    assert len(log.track) == 2


def test_track_point_keeps_lights_and_bank(tmp_path):
    state = _state(
        bank_deg=12.4,
        landing_light=True,
        beacon_light=True,
        nav_light=True,
        taxi_light=False,
        strobe_light=False,
    )
    point = _to_track_point(state, t=5.0)

    assert point.bank_deg == 12.4
    assert point.landing_light is True
    assert point.taxi_light is False


def test_distance_between_two_positions_is_reasonable():
    a = _state(lat=40.0, lon=-3.0)
    b = _state(lat=41.0, lon=-3.0)
    # Un grado de latitud son 60 NM por definición.
    assert 59.0 < _distance_nm(a, b) < 61.0


def test_lectura_corrupta_con_lat_cero_no_se_guarda_ni_suma_distancia(tmp_path):
    """Regresión: un punto con lat=0 (lectura fallida) no debe crear un
    salto de miles de NM ni aparecer en el track."""
    a = _state(lat=40.0, lon=-3.0, on_ground=False, gs_kt=100.0)
    corrupta = _state(lat=0.0, lon=-3.0, on_ground=False, gs_kt=100.0)
    b = _state(lat=41.0, lon=-3.0, on_ground=False, gs_kt=100.0)

    rec = _recorder([a, corrupta, b], tmp_path)
    rec._started_monotonic = 0.0

    for i, state in enumerate([a, corrupta, b]):
        rec._process(state, t=float(i), gap=1.0)

    # El punto corrupto no entra en el track...
    assert all(p.lat != 0.0 for p in rec._track)
    # ...ni infla la distancia: solo se cuenta el tramo a→b (60 NM).
    assert 55.0 < rec._distance_nm < 65.0


def test_lectura_corrupta_con_lon_cero_no_se_guarda(tmp_path):
    rec = _recorder([_state(), _state(lon=0.0), _state()], tmp_path)
    rec._started_monotonic = 0.0

    for i, state in enumerate([_state(), _state(lon=0.0), _state()]):
        rec._process(state, t=float(i), gap=1.0)

    assert all(p.lon != 0.0 for p in rec._track)
