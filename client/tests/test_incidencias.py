"""Tests de la Fase 1: incidencias situadas, ámbito por regla y persistencia.

Lo que se comprueba aquí es que una incidencia sepa **cuándo y dónde** pasó,
que las reglas declaren a qué tipo de vuelo aplican, y que el resultado de la
evaluación se pueda guardar junto al vuelo sin perder nada.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from avcars.config import get_profile, load_profiles
from avcars.evaluation.scoring import (
    DEFAULT_SCOPE,
    RULE_SCOPE,
    RULES_VERSION,
    evaluate_flight,
    rule_applies,
)
from avcars.schema import EvaluationInfo, FlightLog, Incident, IntegrityInfo

FIXTURES = Path(__file__).parent / "fixtures"
PROFILES = load_profiles()


def _load(name: str) -> FlightLog:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return FlightLog.model_validate(data)


# --- Incidencias situadas en el tiempo y el espacio ---------------------


def test_las_incidencias_que_fallan_llevan_hora():
    """Sin hora no hay línea de tiempo ni forma de ordenar el relato del vuelo.

    La hora es lo exigible: sale del evento o de la muestra y siempre se
    conoce. La posición es distinta —ver los tests siguientes—: se toma de la
    traza cuando la hay, y se deja vacía cuando no, en vez de inventarla.
    """
    flight = _load("sample_flight_fail.json")
    verdict = evaluate_flight(flight, get_profile("normal", PROFILES))

    fallos = [i for i in verdict.items if not i.passed]
    assert fallos, "el fixture de fallo debería producir alguna incidencia"

    con_momento = [i for i in fallos if i.rule != "time_compression"]
    for item in con_momento:
        assert item.utc is not None, f"{item.rule} se quedó sin hora"


def test_una_incidencia_situada_lleva_las_dos_coordenadas():
    """Media posición no sirve para nada: o las dos o ninguna."""
    flight = _load("sample_flight_fail.json")
    verdict = evaluate_flight(flight, get_profile("normal", PROFILES))

    situadas = [i for i in verdict.items if i.lat is not None or i.lon is not None]
    assert situadas, "ninguna incidencia quedó situada en el espacio"
    for item in situadas:
        assert item.lat is not None and item.lon is not None


def test_una_pausa_tiene_hora_pero_no_posicion():
    """Durante una pausa el simulador no manda muestras.

    No es una carencia que haya que tapar: si no hubo muestras, no hay
    posición que darle. Se conserva la hora, que es lo que sitúa la pausa en
    la línea de tiempo, y la posición se queda vacía.
    """
    flight = _load("sample_flight_fail.json")
    verdict = evaluate_flight(flight, get_profile("normal", PROFILES))

    pausas = [i for i in verdict.items if i.rule == "pause_duration"]
    assert pausas, "el fixture tiene una pausa larga"
    assert pausas[0].utc is not None
    assert pausas[0].lat is None


def test_la_posicion_de_la_incidencia_esta_dentro_de_la_traza():
    """Una posición inventada sería peor que ninguna: debe salir de la traza."""
    flight = _load("sample_flight_fail.json")
    verdict = evaluate_flight(flight, get_profile("normal", PROFILES))

    lats = {round(p.lat, 6) for p in flight.track}
    lons = {round(p.lon, 6) for p in flight.track}
    for item in verdict.items:
        if item.lat is not None:
            assert round(item.lat, 6) in lats
            assert round(item.lon, 6) in lons


def test_timeline_ordenado_y_solo_con_fallos():
    flight = _load("sample_flight_fail.json")
    verdict = evaluate_flight(flight, get_profile("normal", PROFILES))

    timeline = verdict.timeline
    assert all(not i.passed for i in timeline), "el timeline es el relato de lo que salió mal"
    assert all(i.utc is not None for i in timeline)
    assert timeline == sorted(timeline, key=lambda i: i.utc)


def test_situar_no_cambia_ninguna_nota():
    """La ventana de situado es ancha a propósito; no debe tocar el veredicto.

    Situar ocurre cuando la incidencia ya está decidida, así que ampliar la
    ventana solo mueve el alfiler en el mapa. Juzgar (p. ej. si el tren estaba
    abajo en la toma) sigue usando una ventana estrecha.
    """
    flight = _load("sample_flight_fail.json")
    profile = get_profile("normal", PROFILES)

    verdict = evaluate_flight(flight, profile)
    antes = [(i.rule, i.passed, i.points) for i in verdict.items]

    otra_vez = evaluate_flight(_load("sample_flight_fail.json"), profile)
    assert [(i.rule, i.passed, i.points) for i in otra_vez.items] == antes
    assert otra_vez.score == verdict.score


def test_una_incidencia_sin_punto_no_se_inventa_posicion():
    """La compresión de tiempo es una propiedad de todo el vuelo, no de un instante."""
    flight = _load("sample_flight_fail.json")
    verdict = evaluate_flight(flight, get_profile("normal", PROFILES))

    tc = [i for i in verdict.items if i.rule == "time_compression"]
    assert tc, "el fixture usa compresión de tiempo"
    assert tc[0].lat is None and tc[0].lon is None


# --- Ámbito de reglas de vuelo -----------------------------------------


def test_toda_regla_conocida_declara_un_ambito_valido():
    for rule, scope in RULE_SCOPE.items():
        assert scope in {"VFR", "IFR", "ambas"}, f"{rule} tiene un ámbito raro: {scope}"


def test_una_regla_de_ambas_aplica_a_cualquier_tipo_de_vuelo():
    assert rule_applies("landing_vs", "VFR")
    assert rule_applies("landing_vs", "IFR")


def test_una_regla_solo_vfr_no_aplica_en_ifr():
    assert RULE_SCOPE["cruise_altitude_semicircular"] == "VFR"
    assert rule_applies("cruise_altitude_semicircular", "VFR")
    assert not rule_applies("cruise_altitude_semicircular", "IFR")


def test_una_regla_desconocida_se_evalua_por_defecto():
    """Mejor evaluar de más que hacer desaparecer una regla nueva en silencio."""
    assert DEFAULT_SCOPE == "ambas"
    assert rule_applies("regla_que_no_existe_todavia", "VFR")


def test_en_vfr_las_reglas_solo_ifr_van_a_no_aplica_y_no_a_no_evaluado():
    """Distinguir «no viene al caso» de «falta el dato» es el sentido del campo."""
    flight = _load("sample_flight_pass.json")
    assert flight.flight_plan.rules == "VFR"
    verdict = evaluate_flight(flight, get_profile("normal", PROFILES))

    for rule in verdict.not_applicable:
        assert not rule_applies(rule, "VFR")
    assert not set(verdict.not_applicable) & set(verdict.not_evaluated)


def test_el_ambito_no_cambia_la_nota_de_un_vuelo_vfr():
    """Hoy todo lo implementado aplica a VFR: el filtro no debe alterar nada."""
    flight = _load("sample_flight_pass.json")
    profile = get_profile("normal", PROFILES)
    verdict = evaluate_flight(flight, profile)

    aplicables = [i for i in verdict.items if rule_applies(i.rule, "VFR")]
    assert len(aplicables) == len(verdict.items)


# --- Persistencia del resultado ----------------------------------------


def test_el_resultado_se_puede_guardar_y_releer_sin_perder_nada(tmp_path):
    flight = _load("sample_flight_fail.json")
    verdict = evaluate_flight(flight, get_profile("hard", PROFILES))

    flight.evaluation = EvaluationInfo(
        score=verdict.score,
        passed=verdict.passed,
        failed_hard=list(verdict.failed_hard),
        incidents=[
            Incident(
                rule=i.rule, passed=i.passed, points=i.points, detail=i.detail,
                utc=i.utc, lat=i.lat, lon=i.lon,
            )
            for i in verdict.items
        ],
        not_evaluated=list(verdict.not_evaluated),
        not_applicable=list(verdict.not_applicable),
        profile="hard",
        rules_version=RULES_VERSION,
        evaluated_at_utc=datetime.now(timezone.utc),
    )

    destino = tmp_path / "vuelo.avlog.json"
    destino.write_text(flight.model_dump_json(indent=2), encoding="utf-8")
    releido = FlightLog.model_validate(json.loads(destino.read_text(encoding="utf-8")))

    assert releido.evaluation is not None
    assert releido.evaluation.score == verdict.score
    assert releido.evaluation.profile == "hard"
    assert releido.evaluation.rules_version == RULES_VERSION
    assert len(releido.evaluation.incidents) == len(verdict.items)


def test_guardar_la_evaluacion_deja_la_traza_byte_a_byte_igual(tmp_path):
    """El hash de integridad cubre la traza: reescribir no puede alterarla.

    No basta con que sigan estando los mismos puntos. Si al reescribir el
    fichero cambiase la representación de un solo decimal, cualquiera que
    recalculase el hash obtendría otro y concluiría que el log fue manipulado.
    Por eso se compara la serialización exacta, no la longitud.
    """
    flight = _load("sample_flight_pass.json")
    flight.integrity = IntegrityInfo(hash_algorithm="sha256", track_hash="x" * 64)
    traza_antes = json.dumps(
        [p.model_dump() for p in flight.track], sort_keys=True, default=str
    )

    verdict = evaluate_flight(flight, get_profile("normal", PROFILES))
    flight.evaluation = EvaluationInfo(
        score=verdict.score, passed=verdict.passed,
        profile="normal", rules_version=RULES_VERSION,
    )

    destino = tmp_path / "vuelo.avlog.json"
    destino.write_text(
        flight.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )
    releido = FlightLog.model_validate(json.loads(destino.read_text(encoding="utf-8")))

    traza_despues = json.dumps(
        [p.model_dump() for p in releido.track], sort_keys=True, default=str
    )
    assert traza_despues == traza_antes
    assert releido.integrity is not None
    assert releido.integrity.track_hash == "x" * 64


def test_sin_evaluar_el_campo_evaluation_es_none():
    flight = _load("sample_flight_pass.json")
    assert flight.evaluation is None


# --- Peso ---------------------------------------------------------------


def test_el_esquema_admite_peso_total_y_es_opcional():
    """Si el simulador no lo da, el vuelo se graba igual."""
    flight = _load("sample_flight_pass.json")
    assert flight.track[0].total_weight_kg is None

    punto = flight.track[0].model_copy(update={"total_weight_kg": 1043.5})
    assert punto.total_weight_kg == 1043.5
