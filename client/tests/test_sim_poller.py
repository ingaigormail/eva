"""Tests del hilo que consulta al simulador.

Regresión del fallo encontrado en la primera prueba en vuelo real: la
grabación salió con 99 puntos idénticos porque SimConnect devolvía siempre
la misma lectura cacheada. El poller tiene que detectar esa situación en vez
de dejar que se grabe un vuelo inútil.
"""
import threading
import time

from avcars.connectors.base import SimConnector, SimState
from avcars.connectors.sim_poller import FROZEN_THRESHOLD, SimPoller


def _state(lat: float = 40.0, gs_kt: float = 100.0, paused=None) -> SimState:
    return SimState(
        lat=lat,
        lon=-3.0,
        alt_msl_ft=4000.0,
        alt_agl_ft=3000.0,
        hdg_deg=180.0,
        gs_kt=gs_kt,
        ias_kt=gs_kt,
        vs_fpm=0.0,
        on_ground=False,
        fuel_kg=70.0,
        squawk="7000",
        sim_rate=1.0,
        paused=paused,
    )


class FrozenConnector(SimConnector):
    """Devuelve siempre el mismo estado: reproduce el fallo real."""

    def __init__(self) -> None:
        self.polls = 0

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def poll(self) -> SimState:
        self.polls += 1
        return _state()


class MovingConnector(SimConnector):
    """Devuelve un avión que avanza, como debería ser."""

    def __init__(self) -> None:
        self.polls = 0

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def poll(self) -> SimState:
        self.polls += 1
        return _state(lat=40.0 + self.polls * 0.001)


class FailingConnector(SimConnector):
    """No consigue conectar con el simulador."""

    def connect(self) -> None:
        raise RuntimeError("simulador no encontrado")

    def disconnect(self) -> None:
        pass

    def poll(self) -> SimState:
        raise RuntimeError("sin conexión")


class LateConnector(SimConnector):
    """El simulador no está cuando EvA arranca, pero llega poco después."""

    def __init__(self) -> None:
        self.attempts = 0

    def connect(self) -> None:
        self.attempts += 1
        if self.attempts < 3:
            raise RuntimeError("simulador todavía no está listo")

    def disconnect(self) -> None:
        pass

    def poll(self) -> SimState:
        return _state()


class IntermittentConnector(SimConnector):
    """Se cae a mitad y vuelve: la conexión hay que restablecerla."""

    def __init__(self) -> None:
        self.polls = 0

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def poll(self) -> SimState:
        self.polls += 1
        if 3 <= self.polls <= 5:
            raise RuntimeError("simulador cerrado a mitad de vuelo")
        return _state(lat=40.0 + self.polls * 0.001)


def _run_until(poller: SimPoller, condition, timeout: float = 3.0) -> bool:
    """Espera a que se cumpla una condición, sin dormir de más."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


# -- publicación de estado ---------------------------------------------


def test_publica_el_ultimo_estado():
    poller = SimPoller(MovingConnector(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(poller, lambda: poller.latest is not None)
        assert poller.connected
    finally:
        poller.stop()


def test_la_conexion_se_abre_en_el_hilo_del_poller():
    """SimConnect exige que quien lee sea quien abrió la conexión."""
    hilos: dict[str, int] = {}

    class RecordingConnector(SimConnector):
        def connect(self) -> None:
            hilos["connect"] = threading.get_ident()

        def disconnect(self) -> None:
            pass

        def poll(self) -> SimState:
            hilos["poll"] = threading.get_ident()
            return _state()

    poller = SimPoller(RecordingConnector(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(poller, lambda: "poll" in hilos)
    finally:
        poller.stop()

    assert hilos["connect"] == hilos["poll"]
    assert hilos["connect"] != threading.get_ident()


# -- detección de datos congelados -------------------------------------


def test_detecta_datos_congelados():
    """El fallo real: el simulador devuelve siempre la misma lectura."""
    poller = SimPoller(FrozenConnector(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(poller, lambda: poller.is_frozen, timeout=5.0)
    finally:
        poller.stop()


def test_un_avion_en_movimiento_no_se_considera_congelado():
    poller = SimPoller(MovingConnector(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(
            poller, lambda: poller.identical_reads == 0 and poller.latest is not None
        )
        time.sleep(0.2)
        assert not poller.is_frozen
    finally:
        poller.stop()


def test_el_contador_se_reinicia_al_moverse():
    class SometimesFrozen(SimConnector):
        def __init__(self) -> None:
            self.polls = 0

        def connect(self) -> None:
            pass

        def disconnect(self) -> None:
            pass

        def poll(self) -> SimState:
            self.polls += 1
            # Congelado las primeras lecturas, luego se mueve.
            if self.polls < FROZEN_THRESHOLD:
                return _state()
            return _state(lat=41.0 + self.polls * 0.01)

    poller = SimPoller(SometimesFrozen(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(
            poller, lambda: poller.latest is not None and poller.latest.lat > 40.5
        )
        assert poller.identical_reads == 0
        assert not poller.is_frozen
    finally:
        poller.stop()


# -- errores -----------------------------------------------------------


def test_si_no_conecta_lo_reporta():
    errores: list[Exception] = []
    poller = SimPoller(FailingConnector(), interval_s=0.01, on_error=errores.append)
    poller.start()
    try:
        assert _run_until(poller, lambda: bool(errores))
        assert not poller.connected
        assert poller.latest is None
    finally:
        poller.stop()


def test_parar_es_idempotente():
    poller = SimPoller(MovingConnector(), interval_s=0.01)
    poller.start()
    poller.stop()
    poller.stop()  # no debe lanzar

    assert not poller.connected


def test_reintenta_conectar_hasta_que_el_simulador_llega():
    """EvA se abre antes que el simulador: debe esperarle y conectar luego.

    Regresión del fallo reportado: si la primera conexión fallaba, el hilo
    moría y el botón quedaba deshabilitado para siempre, sin grabar ni en
    manual ni en automático.
    """
    poller = SimPoller(LateConnector(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(poller, lambda: poller.connected, timeout=5.0)
        assert _run_until(poller, lambda: poller.latest is not None)
    finally:
        poller.stop()


def test_restablece_la_conexion_si_se_cae_a_mitad():
    """Si el simulador se cierra y vuelve, el poller se reconecta solo."""
    poller = SimPoller(IntermittentConnector(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(poller, lambda: (poller.reading or None) is not None)
        primera = poller.reading
        assert primera is not None

        # El fallo de las consultas 3-5 no mata el hilo: después sigue
        # publicando lecturas nuevas, con la conexión en pie.
        assert _run_until(
            poller,
            lambda: poller.connected
            and (poller.reading or None) is not None
            and poller.reading.sequence > primera.sequence,
            timeout=5.0,
        )
        assert poller.latest is not None
        assert poller.connected
    finally:
        poller.stop()


# -- numeración de lecturas --------------------------------------------


def test_cada_lectura_lleva_su_numero_de_orden():
    poller = SimPoller(MovingConnector(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(poller, lambda: (poller.reading or None) is not None)
        primera = poller.reading
        assert primera is not None

        assert _run_until(
            poller, lambda: (poller.reading.sequence > primera.sequence)
        )
    finally:
        poller.stop()


def test_reading_after_no_devuelve_lo_ya_visto():
    """Quien consume no debe procesar dos veces la misma lectura."""
    poller = SimPoller(MovingConnector(), interval_s=0.05)
    poller.start()
    try:
        assert _run_until(poller, lambda: poller.reading is not None)
        actual = poller.reading
        assert actual is not None

        # Pidiendo lo posterior a la que ya tenemos, no hay nada nuevo aún.
        assert poller.reading_after(actual.sequence) is None

        # Y con un número anterior, sí.
        assert poller.reading_after(actual.sequence - 1) is not None
    finally:
        poller.stop()


def test_la_lectura_indica_si_ha_cambiado():
    poller = SimPoller(FrozenConnector(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(poller, lambda: poller.identical_reads >= 2)
        reading = poller.reading
        assert reading is not None
        assert not reading.changed
    finally:
        poller.stop()


# -- pausa frente a datos congelados -----------------------------------


def test_un_simulador_pausado_no_se_considera_congelado():
    """Una pausa también congela los datos, pero es normal: no hay que avisar."""

    class PausedConnector(SimConnector):
        def connect(self) -> None:
            pass

        def disconnect(self) -> None:
            pass

        def poll(self) -> SimState:
            return _state(paused=True)

    poller = SimPoller(PausedConnector(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(poller, lambda: poller.identical_reads > FROZEN_THRESHOLD)
        assert poller.is_paused
        assert not poller.is_frozen  # pausado no es lo mismo que averiado
    finally:
        poller.stop()


def test_datos_congelados_sin_pausa_si_preocupan():
    """El fallo real: el simulador no decía estar pausado y no actualizaba."""
    poller = SimPoller(FrozenConnector(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(poller, lambda: poller.is_frozen, timeout=5.0)
        assert not poller.is_paused
    finally:
        poller.stop()


def test_mide_lo_que_tarda_la_consulta():
    class SlowConnector(SimConnector):
        def connect(self) -> None:
            pass

        def disconnect(self) -> None:
            pass

        def poll(self) -> SimState:
            time.sleep(0.05)
            return _state()

    poller = SimPoller(SlowConnector(), interval_s=0.01)
    poller.start()
    try:
        assert _run_until(poller, lambda: poller.poll_duration_s > 0)
        assert poller.poll_duration_s >= 0.05
    finally:
        poller.stop()
