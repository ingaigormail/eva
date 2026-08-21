"""Regresión de la primera prueba en vuelo real (15 de agosto de 2026).

La grabación salió inservible por dos motivos que van juntos:

1. **Datos congelados.** 99 puntos con la misma posición, altitud y
   velocidad, porque SimConnect se consultaba desde un hilo distinto al que
   abrió la conexión y devolvía siempre la lectura cacheada.
2. **27 pausas inventadas.** Cada consulta tardaba 3,1 s, y el detector de
   pausas se disparaba solo con ver un hueco grande entre lecturas.

El fichero de aquel vuelo está en `fixtures/vuelo_datos_congelados.json` y
sirve para comprobar que sabemos reconocer el problema.
"""
import json
import time
from pathlib import Path

from avcars.connectors.base import SimState
from avcars.connectors.sim_poller import Reading
from avcars.recorder.flight_log_writer import FlightRecorder, _is_static
from avcars.schema import FlightLog, FlightPlanInfo, PilotInfo

FIXTURES = Path(__file__).parent / "fixtures"


def _load_bad_flight() -> FlightLog:
    data = json.loads(
        (FIXTURES / "vuelo_datos_congelados.json").read_text(encoding="utf-8")
    )
    return FlightLog.model_validate(data)


def _state(**overrides) -> SimState:
    """Estado tomado del vuelo real que salió mal, para partir de sus datos."""
    base = dict(
        lat=38.655759,
        lon=-35.553045,
        alt_msl_ft=4260.3,
        alt_agl_ft=1348.8,
        hdg_deg=337.3,
        gs_kt=113.2,
        ias_kt=104.0,
        vs_fpm=1239.1,
        on_ground=False,
        fuel_kg=70.22,
        squawk="7000",
        sim_rate=1.0,
    )
    base.update(overrides)
    return SimState(**base)


def _recorder(tmp_path, source) -> FlightRecorder:
    return FlightRecorder(
        source=source,
        pilot=PilotInfo(license_id="AVH100", callsign="AVH100"),
        flight_plan=FlightPlanInfo(
            rules="VFR",
            departure_icao="ZZZZ",
            arrival_icao="ZZZZ",
            network="OFFLINE",
            atc_controlled=False,
        ),
        output_dir=tmp_path,
    )


# -- el vuelo que salió mal --------------------------------------------


def test_el_vuelo_real_tenia_todos_los_puntos_iguales():
    """Documenta el fallo: 99 puntos, una sola posición."""
    log = _load_bad_flight()

    posiciones = {(p.lat, p.lon, p.alt_msl_ft, p.gs_kt) for p in log.track}

    assert len(log.track) == 99
    assert len(posiciones) == 1  # esto es lo que no puede volver a pasar


def test_el_vuelo_real_tenia_pausas_inventadas():
    log = _load_bad_flight()

    pausas = [e for e in log.events if e.type == "pause"]

    assert len(pausas) == 27
    # Todas con la misma duración: era el tiempo que tardaba la consulta.
    assert {p.duration_s for p in pausas} == {3.1}


# -- que no vuelva a pasar ---------------------------------------------


def test_los_estados_repetidos_se_siguen_guardando(tmp_path):
    """Segundo fallo real (vuelo EVA18L): 42 minutos con un solo punto.

    Al descartar las muestras repetidas se descartaba también el paso del
    tiempo. Un avión parado, o un simulador que repite datos, sigue siendo
    información: el track tiene que reflejar que ese rato existió.
    """
    rec = _recorder(tmp_path, lambda _since: None)
    rec._started_monotonic = 0.0

    for segundo in range(30):
        repetido = segundo > 0  # el primero es nuevo, el resto son iguales
        rec._process(_state(), t=float(segundo), gap=1.0, repeated=repetido)

    # Cerca del suelo se guarda una muestra por segundo, repetida o no.
    assert len(rec._track) == 30
    assert rec._repeated_total == 29
    assert rec._longest_repeated_streak == 29


def test_los_estados_repetidos_no_disparan_eventos(tmp_path):
    """Dos lecturas iguales nunca son una transición."""
    rec = _recorder(tmp_path, lambda _since: None)
    rec._started_monotonic = 0.0

    # En tierra y luego en el aire, pero marcado como repetido: no puede
    # generar un despegue, porque el simulador no ha actualizado nada.
    rec._process(_state(on_ground=True), t=0.0, gap=1.0, repeated=False)
    rec._process(_state(on_ground=False), t=1.0, gap=1.0, repeated=True)

    assert not any(e.type == "takeoff" for e in rec.events)


def test_un_avion_que_avanza_si_se_apunta(tmp_path):
    rec = _recorder(tmp_path, lambda _since: None)
    rec._started_monotonic = 0.0

    for segundo in range(10):
        estado = _state(lat=38.65 + segundo * 0.01, alt_agl_ft=300.0)
        rec._process(estado, t=float(segundo), gap=1.0, repeated=False)

    assert len(rec._track) == 10


def test_un_hueco_grande_sin_movimiento_si_es_pausa(tmp_path):
    """Pausa de verdad: pasa el tiempo y el avión sigue en el mismo sitio."""
    rec = _recorder(tmp_path, lambda _since: None)
    rec._started_monotonic = 0.0

    quieto = _state()
    rec._process(quieto, t=0.0, gap=1.0)
    rec._process(quieto, t=1.0, gap=30.0)

    assert any(e.type == "pause" for e in rec.events)


def test_un_hueco_grande_con_movimiento_no_es_pausa(tmp_path):
    """El fallo real: la consulta iba lenta, pero el avión volaba."""
    rec = _recorder(tmp_path, lambda _since: None)
    rec._started_monotonic = 0.0

    rec._process(_state(lat=38.65), t=0.0, gap=1.0)
    rec._process(_state(lat=38.70), t=1.0, gap=3.1)

    assert not any(e.type == "pause" for e in rec.events)


def test_si_el_simulador_dice_estar_pausado_se_le_hace_caso(tmp_path):
    """Con la variable de pausa no hay que inferir nada."""
    rec = _recorder(tmp_path, lambda _since: None)
    rec._started_monotonic = 0.0

    rec._process(_state(paused=True), t=0.0, gap=1.0)
    rec._process(_state(paused=True), t=1.0, gap=10.0)

    assert any(e.type == "pause" for e in rec.events)


def test_si_el_simulador_dice_que_no_esta_pausado_no_se_inventa(tmp_path):
    """Aunque el avión no se mueva: puede estar parado en parking."""
    rec = _recorder(tmp_path, lambda _since: None)
    rec._started_monotonic = 0.0

    quieto = _state(paused=False, gs_kt=0.0, on_ground=True)
    rec._process(quieto, t=0.0, gap=1.0)
    rec._process(quieto, t=1.0, gap=30.0)

    assert not any(e.type == "pause" for e in rec.events)


def test_comparacion_de_estados_estaticos():
    quieto_a = _state()
    quieto_b = _state()
    movido = _state(lat=38.70)

    assert _is_static(quieto_a, quieto_b)
    assert not _is_static(quieto_a, movido)


def test_el_grabador_aguanta_que_no_haya_datos(tmp_path):
    """Si el poller aún no tiene estado, el grabador no debe romperse."""
    rec = _recorder(tmp_path, lambda _since: None)
    rec.start()
    try:
        assert rec.running
    finally:
        rec.stop()


def test_el_grabador_no_procesa_dos_veces_la_misma_lectura(tmp_path):
    """El grabador comprueba más a menudo de lo que el poller publica."""
    entregas = []

    def source(since: int):
        # Solo existe la lectura número 1: quien ya la tiene no recibe nada.
        if since >= 1:
            return None
        # El instante va en la misma escala que usa el grabador para medir
        # el tiempo transcurrido (`time.monotonic`).
        reading = Reading(
            sequence=1, state=_state(), monotonic=time.monotonic(), changed=True
        )
        entregas.append(reading)
        return reading

    rec = _recorder(tmp_path, source)
    rec.start()
    try:
        time.sleep(0.8)
    finally:
        rec.stop()

    assert len(entregas) == 1
    assert len(rec._track) == 1
