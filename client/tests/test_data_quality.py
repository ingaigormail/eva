"""Tests del control de calidad del dato.

Motivo: el vuelo real EVA18L (42 minutos, un solo punto de trayectoria)
sacaba 90/100 y salía APROBADO. Aprobaba porque casi ningún criterio era
comprobable, no porque el vuelo fuera bueno. Aprobar por falta de pruebas es
peor que no evaluar.
"""
import json
from pathlib import Path

from avcars.config import get_profile, load_profiles
from avcars.evaluation.data_quality import Quality, check
from avcars.evaluation.scoring import evaluate_flight
from avcars.schema import FlightLog

FIXTURES = Path(__file__).parent / "fixtures"
PROFILES = load_profiles()


def _load(name: str) -> FlightLog:
    return FlightLog.model_validate(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


# -- el vuelo real que motivó esto -------------------------------------


def test_el_vuelo_eva18l_no_es_evaluable():
    """42 minutos con un punto: no hay nada que juzgar."""
    flight = _load("vuelo_eva18l.json")

    report = check(flight)

    assert report.quality is Quality.NO_EVALUABLE
    assert not report.evaluable
    assert report.problemas


def test_el_vuelo_eva18l_no_aprueba_por_falta_de_pruebas():
    flight = _load("vuelo_eva18l.json")
    verdict = evaluate_flight(flight, get_profile("normal", PROFILES))

    assert not verdict.passed
    assert not verdict.evaluable


def test_el_vuelo_de_datos_congelados_no_es_evaluable():
    """Muchos puntos, pero todos en la misma posición.

    Es la forma del fallo del 15 de agosto de 2026: SimConnect devolvía
    siempre la lectura cacheada y el track salía con una sola posición
    repetida. El vuelo se congela aquí en vez de cargar aquel fichero porque
    `vuelo_datos_congelados.json` se perdió y no está en el historial de git;
    lo que importa es que `check()` reconozca la forma, no aquel vuelo.
    """
    flight = _load("sample_flight_pass.json")
    primero = flight.track[0]
    for punto in flight.track:
        punto.lat = primero.lat
        punto.lon = primero.lon
        punto.alt_msl_ft = primero.alt_msl_ft
        punto.gs_kt = primero.gs_kt

    report = check(flight)

    assert report.quality is Quality.NO_EVALUABLE
    assert any("posici" in p for p in report.problemas)


# -- un vuelo normal sí se evalúa --------------------------------------


def test_un_vuelo_completo_es_evaluable():
    flight = _load("sample_flight_pass.json")

    report = check(flight)

    assert report.evaluable
    assert report.track_points >= 10
    assert report.distinct_positions >= 5


def test_un_vuelo_completo_sigue_aprobando():
    flight = _load("sample_flight_pass.json")
    verdict = evaluate_flight(flight, get_profile("normal", PROFILES))

    assert verdict.passed
    assert verdict.evaluable


# -- casos concretos ---------------------------------------------------


def test_un_vuelo_sin_track_no_es_evaluable():
    flight = _load("sample_flight_pass.json")
    flight.track = []

    report = check(flight)

    assert report.quality is Quality.NO_EVALUABLE
    assert "ningún punto" in report.problemas[0]


def test_pocas_posiciones_distintas_lo_delatan():
    flight = _load("sample_flight_pass.json")
    # Muchos puntos, pero todos en el mismo sitio.
    primero = flight.track[0]
    for punto in flight.track:
        punto.lat, punto.lon, punto.alt_msl_ft = (
            primero.lat,
            primero.lon,
            primero.alt_msl_ft,
        )

    report = check(flight)

    assert report.quality is Quality.NO_EVALUABLE


def test_demasiadas_lecturas_repetidas_lo_delatan():
    flight = _load("sample_flight_pass.json")
    flight.diagnostics = type(flight.diagnostics or object())  # placeholder
    from avcars.schema import DiagnosticsInfo

    flight.diagnostics = DiagnosticsInfo(
        samples_total=1000, samples_repeated=980, process_errors=0
    )

    report = check(flight)

    assert report.quality is Quality.NO_EVALUABLE
    assert report.repeated_ratio is not None
    assert report.repeated_ratio > 0.9


def test_repeticiones_moderadas_solo_avisan():
    from avcars.schema import DiagnosticsInfo

    flight = _load("sample_flight_pass.json")
    flight.diagnostics = DiagnosticsInfo(
        samples_total=1000, samples_repeated=600, process_errors=0
    )

    report = check(flight)

    assert report.evaluable  # se puede evaluar
    assert report.quality is Quality.DUDOSA
    assert report.avisos


def test_el_resumen_explica_el_veredicto():
    assert "insuficientes" in check(_load("vuelo_eva18l.json")).resumen
    assert "correctos" in check(_load("sample_flight_pass.json")).resumen
