"""Tests del hash de integridad de la traza.

Lo que se comprueba aquí es que el hash exista en todo vuelo grabado, que se
pueda recalcular sobre el fichero releído y dé lo mismo, y que solo dependa
de la traza: evaluar un vuelo después no puede invalidarlo.
"""
import json

from avcars import integrity
from avcars.schema import EvaluationInfo, FlightLog, TrackPoint

from test_flight_log_writer import _recorder, _state


def _punto(**overrides) -> TrackPoint:
    base = dict(
        t=0.0,
        lat=40.4719,
        lon=-3.5626,
        alt_msl_ft=2000.0,
        alt_agl_ft=0.0,
        hdg_deg=182.0,
        gs_kt=0.0,
        ias_kt=0.0,
        vs_fpm=0.0,
        on_ground=True,
    )
    base.update(overrides)
    return TrackPoint(**base)


def _grabar(tmp_path):
    """Graba un vuelo mínimo de dos muestras y devuelve el fichero escrito."""
    rec = _recorder([_state()], tmp_path)
    rec._started_monotonic = 0.0
    rec._process(_state(), t=0.0, gap=1.0)
    rec._process(_state(on_ground=False, alt_agl_ft=100, ias_kt=70), t=1.0, gap=1.0)
    return rec._write_log()


# --- El hash se escribe -------------------------------------------------


def test_el_vuelo_grabado_lleva_el_hash_de_la_traza(tmp_path):
    """El campo existía en el esquema pero nadie lo rellenaba: quedaba a None."""
    log = FlightLog.model_validate(json.loads(_grabar(tmp_path).read_text("utf-8")))

    assert log.integrity is not None
    assert log.integrity.hash_algorithm == "SHA-256"
    assert len(log.integrity.track_hash) == 64


def test_el_hash_escrito_es_el_de_su_propia_traza(tmp_path):
    """Recalcularlo sobre el fichero releído tiene que dar lo mismo.

    Es la única prueba que importa: si la serialización no sobreviviera al ida
    y vuelta por disco, el hash no serviría para verificar nada.
    """
    log = FlightLog.model_validate(json.loads(_grabar(tmp_path).read_text("utf-8")))

    assert log.integrity.track_hash == integrity.track_hash(log.track)


def test_el_volcado_parcial_tambien_lleva_hash(tmp_path):
    """Un vuelo interrumpido se recupera como vuelo normal: necesita el suyo."""
    rec = _recorder([_state()], tmp_path)
    rec._started_monotonic = 0.0
    rec._partial_path = tmp_path / "en_curso.parcial"
    rec._process(_state(), t=0.0, gap=1.0)
    rec._autosave()

    parcial = FlightLog.model_validate(
        json.loads(rec._partial_path.read_text("utf-8"))
    )
    assert parcial.integrity is not None
    assert parcial.integrity.track_hash == integrity.track_hash(parcial.track)


# --- Qué cubre y qué no -------------------------------------------------


def test_evaluar_el_vuelo_no_invalida_el_hash(tmp_path):
    """`evaluation` se añade después de grabar y no forma parte de la traza.

    Si el hash cubriera el documento entero, todo vuelo evaluado pasaría a
    parecer manipulado.
    """
    destino = _grabar(tmp_path)
    log = FlightLog.model_validate(json.loads(destino.read_text("utf-8")))

    log.evaluation = EvaluationInfo(
        score=88, passed=True, profile="normal", rules_version="1.0"
    )
    destino.write_text(log.model_dump_json(indent=2, exclude_none=True), "utf-8")

    releido = FlightLog.model_validate(json.loads(destino.read_text("utf-8")))
    assert releido.integrity.track_hash == integrity.track_hash(releido.track)


def test_retocar_un_punto_cambia_el_hash():
    """Es para lo que existe: delatar la edición a mano del fichero."""
    traza = [_punto(t=0.0, vs_fpm=-900.0), _punto(t=1.0)]
    original = integrity.track_hash(traza)

    traza[0].vs_fpm = -200.0  # una toma dura convertida en suave
    assert integrity.track_hash(traza) != original


def test_el_orden_de_los_puntos_cuenta():
    traza = [_punto(t=0.0), _punto(t=1.0, lat=40.5)]
    assert integrity.track_hash(traza) != integrity.track_hash(list(reversed(traza)))


# --- Serialización canónica ---------------------------------------------


def test_el_hash_no_depende_del_orden_de_los_campos_del_modelo():
    """Las claves van ordenadas, así que reordenar `schema.py` no lo cambia."""
    bytes_traza = integrity.canonical_track_bytes([_punto()])
    claves = [c for c in json.loads(bytes_traza)[0]]

    assert claves == sorted(claves)


def test_un_campo_ausente_y_uno_a_none_hashean_igual():
    """El fichero se escribe con `exclude_none`: al releerlo vuelven como None.

    Si ambas formas no dieran el mismo hash, verificar un vuelo guardado sería
    imposible.
    """
    con_none = _punto(bank_deg=None)
    sin_campo = TrackPoint.model_validate(
        {k: v for k, v in con_none.model_dump().items() if v is not None}
    )

    assert integrity.track_hash([sin_campo]) == integrity.track_hash([con_none])


def test_una_traza_vacia_tambien_tiene_hash():
    """Un vuelo sin puntos se graba igual; el campo nunca queda a None."""
    assert len(integrity.track_hash([])) == 64
