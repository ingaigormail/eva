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


class TestReglasActivas:
    """Una regla desactivada de verdad deja de puntuar (`reglas_config.py`)."""

    def test_regla_desactivada_pasa_a_not_active_y_no_puntua(self):
        flight = _load("sample_flight_fail.json")
        profile = get_profile("normal", PROFILES)

        con_todo_activo = evaluate_flight(flight, profile)
        assert "bank_angle" in [i.rule for i in con_todo_activo.items]

        sin_bank_angle = evaluate_flight(
            flight, profile, reglas_activas={"bank_angle": False}
        )
        assert "bank_angle" not in [i.rule for i in sin_bank_angle.items]
        assert "bank_angle" in sin_bank_angle.not_active
        # Sin bank_angle, la nota no puede ser menor que con ella activa:
        # como mucho se recuperan los puntos que quitaba.
        assert sin_bank_angle.score >= con_todo_activo.score

    def test_desactivar_un_fallo_duro_deja_de_tirar_el_vuelo(self):
        """`excessive_bank_angle` es failed_hard, no un item con puntos: hace
        falta el mapa motivo->regla de `scoring.py` para poder filtrarlo."""
        flight = _load("sample_flight_fail.json")
        profile = get_profile("normal", PROFILES)

        con_todo_activo = evaluate_flight(flight, profile)
        assert "landing_vs_very_hard" in con_todo_activo.failed_hard

        sin_landing_vs = evaluate_flight(
            flight, profile, reglas_activas={"landing_vs": False}
        )
        assert "landing_vs_very_hard" not in sin_landing_vs.failed_hard

    def test_regla_sin_dato_desactivada_pasa_de_not_evaluated_a_not_active(self):
        """Una regla bloqueada (sin código) que se desactiva a mano dice por
        qué de verdad no cuenta: apagada, no "falta el dato"."""
        flight = _load("sample_flight_pass.json")
        profile = get_profile("normal", PROFILES)

        normal = evaluate_flight(flight, profile)
        assert "route_deviation" in normal.not_evaluated

        desactivada = evaluate_flight(
            flight, profile, reglas_activas={"route_deviation": False}
        )
        assert "route_deviation" not in desactivada.not_evaluated
        assert "route_deviation" in desactivada.not_active

    def test_sin_reglas_activas_se_comporta_como_antes(self):
        """Parámetro opcional: sin él, ninguna regla se apaga (compatibilidad)."""
        flight = _load("sample_flight_pass.json")
        profile = get_profile("normal", PROFILES)

        con_parametro = evaluate_flight(flight, profile, reglas_activas=None)
        sin_parametro = evaluate_flight(flight, profile)

        assert con_parametro.score == sin_parametro.score
        assert con_parametro.not_active == sin_parametro.not_active == []


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


# -- structural_overspeed: IAS contra el limite real del avion (POH primero,
# simulador solo de respaldo) -- independiente de overspeed_warning, que
# solo confia en el aviso interno del propio simulador.


def test_sin_aircraft_structural_overspeed_no_se_evalua():
    """Sin pasar `aircraft`, la regla se queda en not_evaluated -- nunca
    finge un limite que no se le ha dado."""
    flight = _load("sample_flight_pass.json")
    profile = get_profile("normal", PROFILES)

    verdict = evaluate_flight(flight, profile)

    assert "structural_overspeed" in verdict.not_evaluated
    assert not any(i.rule == "structural_overspeed" for i in verdict.items)


def test_con_aircraft_pero_sin_limite_usable_sigue_sin_evaluarse():
    """Un avion sin VNE ni VMO en ninguna fuente (ni POH ni simulador)
    tampoco se evalua -- no hay con que comparar."""
    flight = _load("sample_flight_pass.json")
    profile = get_profile("normal", PROFILES)
    avion_sin_datos = {"limites_poh": {"vne": None, "vmo": None}}

    verdict = evaluate_flight(flight, profile, aircraft=avion_sin_datos)

    assert "structural_overspeed" in verdict.not_evaluated


def test_dentro_del_limite_pasa_y_cita_la_fuente():
    flight = _load("sample_flight_pass.json")
    profile = get_profile("normal", PROFILES)
    avion = {"limites_poh": {"vne": 163, "vmo": "no_aplica"}}

    verdict = evaluate_flight(flight, profile, aircraft=avion)

    item = next(i for i in verdict.items if i.rule == "structural_overspeed")
    assert item.passed
    assert "163" in item.detail
    assert "poh" in item.detail


def test_por_encima_del_limite_es_fail_duro():
    flight = _load("sample_flight_pass.json")
    flight.track[0].ias_kt = 200.0
    profile = get_profile("normal", PROFILES)
    avion = {"limites_poh": {"vne": 163, "vmo": "no_aplica"}}

    verdict = evaluate_flight(flight, profile, aircraft=avion)

    assert "structural_overspeed" in verdict.failed_hard
    assert not verdict.passed
    item = next(i for i in verdict.items if i.rule == "structural_overspeed")
    assert not item.passed
    assert "200" in item.detail and "163" in item.detail


def test_usa_referencia_de_simulador_solo_si_no_hay_poh():
    """El POH manda si existe; el simulador solo entra cuando el POH esta
    a None -- confirma el orden de las DOS FUENTES, no solo que exista un
    valor cualquiera."""
    flight = _load("sample_flight_pass.json")
    flight.track[0].ias_kt = 170.0
    profile = get_profile("normal", PROFILES)

    # POH real dice 163 (se supera con 170) -> debe fallar pese a que el
    # simulador (mas permisivo, 250) lo habria dejado pasar.
    avion_con_poh = {
        "limites_poh": {"vne": 163, "vmo": "no_aplica"},
        "referencia_sim": {"vne": 250},
    }
    veredicto_con_poh = evaluate_flight(flight, profile, aircraft=avion_con_poh)
    item_poh = next(
        i for i in veredicto_con_poh.items if i.rule == "structural_overspeed"
    )
    assert not item_poh.passed
    assert "poh" in item_poh.detail

    # Sin POH, cae al simulador (250) -> con 170 kt no lo supera, pasa.
    avion_sin_poh = {"referencia_sim": {"vne": 250}}
    veredicto_sin_poh = evaluate_flight(flight, profile, aircraft=avion_sin_poh)
    item_sim = next(
        i for i in veredicto_sin_poh.items if i.rule == "structural_overspeed"
    )
    assert item_sim.passed
    assert "sim" in item_sim.detail


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
