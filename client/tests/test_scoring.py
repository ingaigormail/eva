"""Tests del motor de evaluación (avcars/evaluation/scoring.py)."""
import json
from pathlib import Path

from avcars.config import get_profile, load_profiles
from avcars.evaluation.scoring import evaluate_flight
from avcars.schema import FlightLog, TrackPoint

FIXTURES = Path(__file__).parent / "fixtures"
PROFILES = load_profiles()


def _load(name: str) -> FlightLog:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return FlightLog.model_validate(data)


def _track_point_at_touchdown(flight: FlightLog, touchdown) -> TrackPoint:
    """Construye un TrackPoint justo en el instante del touchdown, basado en
    la geometría del último punto del track."""
    base = flight.track[-1]
    td_t = (touchdown.utc - flight.timing.block_off_utc).total_seconds()
    return TrackPoint(
        t=td_t,
        lat=base.lat,
        lon=base.lon,
        alt_msl_ft=base.alt_msl_ft,
        alt_agl_ft=0,
        hdg_deg=base.hdg_deg,
        gs_kt=base.gs_kt,
        ias_kt=base.ias_kt,
        vs_fpm=base.vs_fpm,
        on_ground=True,
        bank_deg=base.bank_deg,
        gear_down=True,
    )


def test_good_flight_passes():
    flight = _load("sample_flight_pass.json")
    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    assert verdict.passed
    assert verdict.score >= profile["pass_score"]
    assert not verdict.failed_hard


def test_hard_landing_and_time_compression_fail_automatically():
    flight = _load("sample_flight_fail.json")
    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    assert not verdict.passed
    assert "landing_vs_very_hard" in verdict.failed_hard
    assert "time_compression_used" in verdict.failed_hard


def test_score_never_negative():
    flight = _load("sample_flight_fail.json")
    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    assert verdict.score >= 0


def test_unsupported_rules_are_reported_not_faked():
    flight = _load("sample_flight_pass.json")
    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    assert "route_deviation" in verdict.not_evaluated
    # El fixture antiguo no graba avisos del simulador, así que estas reglas
    # se reportan como no evaluadas en vez de fingir que se comprobaron.
    assert "overspeed_warning" in verdict.not_evaluated
    assert "stall_warning" in verdict.not_evaluated


def test_warnings_and_config_are_evaluated_with_data():
    """Con los nuevos campos del log (avisos, QNH, tren), las reglas se
    evalúan de verdad y no quedan en 'not_evaluated'."""
    flight = _load("sample_flight_pass.json")
    # Añade avisos y configuración al track.
    for point in flight.track:
        point.stall_warning = False
        point.overspeed_warning = False
        point.qnh_inhg = 29.92
        point.gear_down = True
    touchdown = next(e for e in flight.events if e.type == "touchdown")
    # El fixture muestrea cada ~60 s; añade un punto justo en el touchdown
    # con el tren abajo para que la regla tenga datos.
    flight.track.append(_track_point_at_touchdown(flight, touchdown))

    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    by_rule = {item.rule: item for item in verdict.items}
    assert "overspeed_warning" not in verdict.not_evaluated
    assert by_rule["overspeed_warning"].passed
    assert "stall_warning" not in verdict.not_evaluated
    assert by_rule["stall_warning"].passed
    assert "qnh" not in verdict.not_evaluated
    assert by_rule["qnh"].passed
    assert "gear_on_touchdown" not in verdict.not_evaluated
    assert by_rule["gear_on_touchdown"].passed


def test_stall_warning_is_fail():
    flight = _load("sample_flight_pass.json")
    flight.track[0].stall_warning = True

    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    assert "stall_warning_triggered" in verdict.failed_hard
    assert not verdict.passed


def test_overspeed_warning_is_fail():
    flight = _load("sample_flight_pass.json")
    flight.track[0].overspeed_warning = True

    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    assert "overspeed_warning_triggered" in verdict.failed_hard
    assert not verdict.passed


def test_qnh_out_of_range_is_penalized():
    flight = _load("sample_flight_pass.json")
    for point in flight.track:
        point.qnh_inhg = 33.0  # fuera del rango plausible

    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    by_rule = {item.rule: item for item in verdict.items}
    assert not by_rule["qnh"].passed
    assert by_rule["qnh"].points == profile["penalties"]["qnh_out_of_range"]


def test_gear_up_on_touchdown_is_penalized():
    flight = _load("sample_flight_pass.json")
    touchdown = next(e for e in flight.events if e.type == "touchdown")
    # Punto en el touchdown con el tren arriba.
    point = _track_point_at_touchdown(flight, touchdown)
    point.gear_down = False
    flight.track.append(point)

    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    by_rule = {item.rule: item for item in verdict.items}
    assert not by_rule["gear_on_touchdown"].passed
    assert by_rule["gear_on_touchdown"].points == profile["penalties"]["gear_up_touchdown"]


def test_good_flight_has_no_bank_or_light_penalties():
    flight = _load("sample_flight_pass.json")
    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    assert "bank_angle" not in verdict.not_evaluated
    assert "lights" not in verdict.not_evaluated
    assert all(item.passed for item in verdict.items if item.rule == "bank_angle")
    light_rules = {"landing_light_takeoff", "landing_light_landing", "beacon_airborne",
                   "nav_light_airborne", "taxi_light", "strobe_taxi"}
    assert all(item.passed for item in verdict.items if item.rule in light_rules)


def test_excessive_bank_angle_is_fail():
    flight = _load("sample_flight_fail.json")
    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    assert "excessive_bank_angle" in verdict.failed_hard


def test_light_violations_are_penalized():
    flight = _load("sample_flight_fail.json")
    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    by_rule = {item.rule: item for item in verdict.items}
    assert by_rule["landing_light_takeoff"].passed is False
    assert by_rule["taxi_light"].passed is False
    assert by_rule["strobe_taxi"].passed is False
