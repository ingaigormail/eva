"""Tests de `plan_web.py`: el lado del grabador que habla con la web.

Sin red real: se sustituye `urllib.request.urlopen` por un doble que
devuelve la respuesta que cada prueba necesita. El contrato importante es
"nunca lanza": cualquier fallo de red, clave o formato es un `None`/`False`
silencioso, porque esto corre en un grabador que no se puede caer por un
servidor lento.
"""
import json
import urllib.error

from avcars import plan_web


class _RespuestaFalsa:
    def __init__(self, cuerpo: dict, status: int = 200):
        self._cuerpo = json.dumps(cuerpo).encode("utf-8")
        self.status = status

    def read(self):
        return self._cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _urlopen_que_devuelve(cuerpo, status=200):
    def _fake(peticion, timeout=None):
        return _RespuestaFalsa(cuerpo, status)
    return _fake


def _urlopen_que_falla(excepcion):
    def _fake(peticion, timeout=None):
        raise excepcion
    return _fake


# -- payload_pendiente ------------------------------------------------------


def test_payload_pendiente_sin_clave_no_llama_a_la_red(monkeypatch):
    llamado = False

    def _fake(*a, **k):
        nonlocal llamado
        llamado = True
    monkeypatch.setattr("urllib.request.urlopen", _fake)

    assert plan_web.payload_pendiente("https://eva.example", "") is None
    assert llamado is False


def test_payload_pendiente_sin_solicitud_es_none(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", _urlopen_que_devuelve({"ok": True, "solicitud": None})
    )
    assert plan_web.payload_pendiente("https://eva.example", "clave123") is None


def test_payload_pendiente_devuelve_el_dict_de_la_solicitud(monkeypatch):
    solicitud = {"passengers": 4, "cargo_kg": 100, "fuel_pct": 0, "aeronave": "C172"}
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _urlopen_que_devuelve({"ok": True, "solicitud": solicitud}),
    )
    assert plan_web.payload_pendiente("https://eva.example", "clave123") == solicitud


def test_payload_pendiente_ante_un_fallo_de_red_no_lanza(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _urlopen_que_falla(urllib.error.URLError("sin red")),
    )
    assert plan_web.payload_pendiente("https://eva.example", "clave123") is None


def test_payload_pendiente_ante_un_401_es_none(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _urlopen_que_devuelve({"ok": False, "mensaje": "Clave no válida"}, status=401),
    )
    assert plan_web.payload_pendiente("https://eva.example", "clave-mala") is None


def test_payload_pendiente_ante_una_respuesta_rara_no_lanza(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _urlopen_que_devuelve({"solicitud": "no-es-un-dict"}))
    assert plan_web.payload_pendiente("https://eva.example", "clave123") is None


# -- reportar_payload_resultado ---------------------------------------------


def test_reportar_resultado_sin_clave_no_llama_a_la_red(monkeypatch):
    llamado = False

    def _fake(*a, **k):
        nonlocal llamado
        llamado = True
    monkeypatch.setattr("urllib.request.urlopen", _fake)

    ok = plan_web.reportar_payload_resultado("https://eva.example", "", {"carga": True})
    assert ok is False
    assert llamado is False


def test_reportar_resultado_con_exito_devuelve_true(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _urlopen_que_devuelve({"ok": True}))
    ok = plan_web.reportar_payload_resultado(
        "https://eva.example", "clave123", {"carga": True, "carga_kg": 440.0}
    )
    assert ok is True


def test_reportar_resultado_ante_un_fallo_de_red_devuelve_false_no_lanza(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _urlopen_que_falla(urllib.error.URLError("sin red")),
    )
    ok = plan_web.reportar_payload_resultado(
        "https://eva.example", "clave123", {"carga": False}
    )
    assert ok is False


# -- clave_valida ------------------------------------------------------------


def test_clave_valida_sin_clave_es_false_sin_llamar_a_la_red(monkeypatch):
    llamado = False

    def _fake(*a, **k):
        nonlocal llamado
        llamado = True
    monkeypatch.setattr("urllib.request.urlopen", _fake)

    assert plan_web.clave_valida("https://eva.example", "") is False
    assert llamado is False


def test_clave_valida_con_200_es_true(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", _urlopen_que_devuelve({"ok": True, "plan": None})
    )
    assert plan_web.clave_valida("https://eva.example", "clave123") is True


def test_clave_valida_con_401_es_false(monkeypatch):
    def _fake(peticion, timeout=None):
        raise urllib.error.HTTPError(
            "https://eva.example/api/grabador/plan", 401, "no autorizado", None, None
        )
    monkeypatch.setattr("urllib.request.urlopen", _fake)
    assert plan_web.clave_valida("https://eva.example", "clave-mala") is False


def test_clave_valida_con_otro_error_http_es_none(monkeypatch):
    def _fake(peticion, timeout=None):
        raise urllib.error.HTTPError(
            "https://eva.example/api/grabador/plan", 500, "roto", None, None
        )
    monkeypatch.setattr("urllib.request.urlopen", _fake)
    assert plan_web.clave_valida("https://eva.example", "clave123") is None


def test_clave_valida_ante_un_fallo_de_red_es_none_no_lanza(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _urlopen_que_falla(urllib.error.URLError("sin red")),
    )
    assert plan_web.clave_valida("https://eva.example", "clave123") is None
