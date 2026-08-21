"""Tests de la escritura incremental y la recuperación de vuelos.

El escenario que importa: EvA se cierra de golpe a mitad de un vuelo de dos
horas. Ese vuelo no se puede perder.
"""
import json

from avcars.recorder.flight_log_writer import (
    LOG_SUFFIX,
    PARTIAL_SUFFIX,
    FlightRecorder,
    describe_interrupted,
    discard_interrupted,
    find_interrupted,
    recover,
)
from avcars.schema import FlightLog, FlightPlanInfo, PilotInfo

from test_flight_log_writer import FakeSource, _state


def _recorder(tmp_path, **kwargs) -> FlightRecorder:
    return FlightRecorder(
        source=FakeSource([_state()]),
        pilot=PilotInfo(license_id="AVH-1", callsign="AVH100"),
        flight_plan=FlightPlanInfo(
            rules="VFR",
            departure_icao="LEMD",
            arrival_icao="LEBL",
            network="OFFLINE",
            atc_controlled=False,
        ),
        output_dir=tmp_path,
        **kwargs,
    )


def _grabar_algo(rec: FlightRecorder) -> None:
    """Simula unos segundos de vuelo sin arrancar el hilo."""
    rec._started_monotonic = 0.0
    rec._process(_state(), t=0.0, gap=1.0)
    rec._process(_state(on_ground=False, alt_agl_ft=500, ias_kt=90), t=1.0, gap=1.0)


# -- escritura atómica -------------------------------------------------


def test_el_fichero_final_nunca_queda_a_medias(tmp_path):
    rec = _recorder(tmp_path)
    _grabar_algo(rec)

    path = rec._write_log()

    # Sin restos temporales y JSON válido.
    assert not list(tmp_path.glob("*.tmp"))
    FlightLog.model_validate(json.loads(path.read_text(encoding="utf-8")))


def test_dos_vuelos_en_el_mismo_segundo_no_se_pisan(tmp_path):
    primero = _recorder(tmp_path)
    _grabar_algo(primero)
    ruta1 = primero._write_log()

    segundo = _recorder(tmp_path)
    _grabar_algo(segundo)
    ruta2 = segundo._write_log()

    assert ruta1 != ruta2
    assert ruta1.exists() and ruta2.exists()


# -- volcado periódico -------------------------------------------------


def test_el_volcado_deja_un_parcial_legible(tmp_path):
    rec = _recorder(tmp_path)
    rec._partial_path = tmp_path / f"en_curso_2026-08-15_12-00-00_AVH100{PARTIAL_SUFFIX}"
    _grabar_algo(rec)

    rec._autosave()

    assert rec._partial_path.exists()
    log = FlightLog.model_validate(
        json.loads(rec._partial_path.read_text(encoding="utf-8"))
    )
    assert len(log.track) == 2


def test_al_cerrar_bien_no_queda_ningun_parcial(tmp_path):
    rec = _recorder(tmp_path)
    rec._partial_path = tmp_path / f"en_curso_2026-08-15_12-00-00_AVH100{PARTIAL_SUFFIX}"
    _grabar_algo(rec)
    rec._autosave()

    rec._write_log()

    assert not find_interrupted(tmp_path)


def test_un_fallo_al_volcar_no_detiene_la_grabacion(tmp_path, monkeypatch):
    errores = []
    rec = _recorder(tmp_path, on_error=errores.append)
    rec._partial_path = tmp_path / f"en_curso_x{PARTIAL_SUFFIX}"
    _grabar_algo(rec)

    def falla(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr("pathlib.Path.write_text", falla)
    rec._autosave()

    # Se avisa del problema, pero no se lanza la excepción hacia arriba.
    assert errores
    assert isinstance(errores[0], OSError)


# -- recuperación ------------------------------------------------------


def test_se_encuentra_un_vuelo_interrumpido(tmp_path):
    rec = _recorder(tmp_path)
    rec._partial_path = tmp_path / f"en_curso_2026-08-15_12-00-00_AVH100{PARTIAL_SUFFIX}"
    _grabar_algo(rec)
    rec._autosave()

    # EvA se cierra de golpe: el parcial se queda ahí.
    interrumpidos = find_interrupted(tmp_path)

    assert len(interrumpidos) == 1


def test_se_puede_describir_para_preguntar_al_piloto(tmp_path):
    rec = _recorder(tmp_path)
    rec._partial_path = tmp_path / f"en_curso_2026-08-15_12-00-00_AVH100{PARTIAL_SUFFIX}"
    _grabar_algo(rec)
    rec._autosave()

    resumen = describe_interrupted(rec._partial_path)

    assert resumen is not None
    assert resumen["callsign"] == "AVH100"
    assert resumen["puntos"] == 2
    assert resumen["salida"] == "LEMD"


def test_recuperar_convierte_el_parcial_en_un_vuelo_normal(tmp_path):
    rec = _recorder(tmp_path)
    rec._partial_path = tmp_path / f"en_curso_2026-08-15_12-00-00_AVH100{PARTIAL_SUFFIX}"
    _grabar_algo(rec)
    rec._autosave()
    parcial = rec._partial_path

    recuperado = recover(parcial)

    assert recuperado is not None
    assert recuperado.name.endswith(LOG_SUFFIX)
    assert not parcial.exists()
    FlightLog.model_validate(json.loads(recuperado.read_text(encoding="utf-8")))


def test_el_vuelo_recuperado_conserva_su_fecha_original(tmp_path):
    rec = _recorder(tmp_path)
    rec._partial_path = tmp_path / f"en_curso_2026-08-15_12-00-00_AVH100{PARTIAL_SUFFIX}"
    _grabar_algo(rec)
    rec._autosave()

    recuperado = recover(rec._partial_path)

    assert recuperado is not None
    assert recuperado.name.startswith("2026-08-15_12-00-00")


def test_un_parcial_corrupto_no_rompe_nada(tmp_path):
    corrupto = tmp_path / f"en_curso_2026-08-15_12-00-00_AVH100{PARTIAL_SUFFIX}"
    corrupto.write_text("{esto no es json", encoding="utf-8")

    assert describe_interrupted(corrupto) is None
    assert recover(corrupto) is None
    assert corrupto.exists()  # no se borra: el piloto decide


def test_descartar_borra_el_parcial(tmp_path):
    parcial = tmp_path / f"en_curso_x{PARTIAL_SUFFIX}"
    parcial.write_text("{}", encoding="utf-8")

    assert discard_interrupted(parcial)
    assert not parcial.exists()


def test_sin_parciales_no_encuentra_nada(tmp_path):
    assert find_interrupted(tmp_path) == []


def test_carpeta_inexistente_no_rompe_la_busqueda(tmp_path):
    assert find_interrupted(tmp_path / "no_existe") == []
