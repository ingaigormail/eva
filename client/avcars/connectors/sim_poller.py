"""Hilo único que consulta al simulador y publica el último estado.

Por qué existe
--------------
SimConnect no admite que la conexión se abra en un hilo y se lea desde otro:
devuelve siempre la primera lectura cacheada. En la primera prueba en vuelo
real eso produjo una grabación de 99 puntos **todos idénticos**, con el avión
congelado en la misma posición durante tres minutos.

Además, leer las veintitantas variables una a una tarda; en aquella prueba
cada ciclo tardaba 3,1 segundos, lo que disparaba el detector de pausas y
llenaba el log de pausas que nunca ocurrieron.

La solución es que **un solo hilo sea el dueño de la conexión**: la abre, la
consulta en bucle y publica el resultado. La ventana y el grabador leen ese
último estado publicado, sin tocar SimConnect.

Detección de datos congelados
-----------------------------
Si el simulador devuelve exactamente el mismo estado muchas veces seguidas,
algo va mal (conexión perdida, simulador en un menú, caché atascada). El
poller lo detecta y lo expone para que la interfaz pueda avisar en vez de
grabar un vuelo inútil.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .. import timing
from .base import SimConnector, SimState

# Los tiempos viven en avcars/timing.py, donde se comprueba que encajan entre
# sí. Aquí solo se les pone un nombre corto.
DEFAULT_INTERVAL_S = timing.POLL_INTERVAL_S
FROZEN_THRESHOLD = timing.FROZEN_READS


@dataclass(frozen=True)
class Reading:
    """Una lectura del simulador, con su número de orden.

    El número permite a quien consume saber si lo que está viendo es nuevo o
    es la misma lectura de antes. Sin él, el grabador y la ventana, que van
    a su propio ritmo, procesarían el mismo estado varias veces o se
    perderían alguno.
    """

    sequence: int
    state: SimState
    monotonic: float
    changed: bool  # False si es idéntica a la anterior


def _signature(state: SimState) -> tuple:
    """Valores que deberían cambiar entre lecturas de un avión en marcha."""
    return (
        state.lat,
        state.lon,
        state.alt_msl_ft,
        state.gs_kt,
        state.ias_kt,
        state.vs_fpm,
        state.fuel_kg,
    )


class SimPoller:
    """Consulta el simulador en su propio hilo y publica el último estado.

    Uso:

        poller = SimPoller(connector)
        poller.start()
        ...
        state = poller.latest        # último estado conocido, o None
        if poller.is_frozen: ...     # el simulador no está actualizando
        poller.stop()
    """

    def __init__(
        self,
        connector: SimConnector,
        interval_s: float = DEFAULT_INTERVAL_S,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._connector = connector
        self._interval_s = interval_s
        self._on_error = on_error

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._reading: Optional[Reading] = None
        self._sequence = 0
        self._connected = False
        self._identical_reads = 0
        self._last_signature: Optional[tuple] = None
        self._last_error: Optional[Exception] = None
        self._poll_duration_s: float = 0.0

    # -- ciclo de vida --------------------------------------------------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        try:
            self._connector.disconnect()
        except Exception:
            pass
        with self._lock:
            self._connected = False

    # -- estado publicado -----------------------------------------------

    @property
    def latest(self) -> Optional[SimState]:
        """Último estado leído, o None si todavía no hay ninguno."""
        with self._lock:
            return self._reading.state if self._reading else None

    @property
    def reading(self) -> Optional[Reading]:
        """Última lectura completa, con su número de orden."""
        with self._lock:
            return self._reading

    def reading_after(self, sequence: int) -> Optional[Reading]:
        """Devuelve la última lectura solo si es posterior a `sequence`.

        Así quien consume no procesa dos veces la misma lectura, aunque
        consulte más a menudo de lo que el poller publica.
        """
        with self._lock:
            if self._reading is None or self._reading.sequence <= sequence:
                return None
            return self._reading

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def is_frozen(self) -> bool:
        """True si los datos no cambian y no es porque esté pausado.

        Una pausa del simulador también congela los datos, pero es una
        situación normal: no hay que avisar de nada. Solo preocupa cuando el
        simulador no dice estar pausado y aun así no actualiza.
        """
        with self._lock:
            if self._identical_reads < FROZEN_THRESHOLD:
                return False
            if self._reading is not None and self._reading.state.paused:
                return False
            return True

    @property
    def is_paused(self) -> bool:
        """True si el simulador declara estar en pausa."""
        with self._lock:
            if self._reading is None:
                return False
            return bool(self._reading.state.paused)

    @property
    def identical_reads(self) -> int:
        with self._lock:
            return self._identical_reads

    @property
    def age_s(self) -> Optional[float]:
        """Antigüedad del último estado, en segundos."""
        with self._lock:
            if self._reading is None:
                return None
            return time.monotonic() - self._reading.monotonic

    @property
    def connection_lost(self) -> bool:
        """True si hace demasiado que no llega una lectura."""
        age = self.age_s
        return age is not None and age > timing.CONNECTION_LOST_S

    @property
    def poll_duration_s(self) -> float:
        """Cuánto tardó la última consulta. Útil para diagnosticar lentitud."""
        with self._lock:
            return self._poll_duration_s

    @property
    def last_error(self) -> Optional[Exception]:
        with self._lock:
            return self._last_error

    # -- bucle ----------------------------------------------------------

    def _run(self) -> None:
        # La conexión se abre **aquí**, dentro del hilo que la va a usar.
        #
        # Si el simulador todavía no está listo (se abrió EvA antes que él),
        # se reintenta en vez de morir: el manual promete que EvA lo espera, y
        # salirse al primer intento dejaría el botón deshabilitado para
        # siempre, sin grabar ni en manual ni en automático.
        while not self._stop_event.is_set():
            try:
                self._connector.connect()
                with self._lock:
                    self._connected = True
                    self._last_error = None
                break
            except Exception as exc:
                with self._lock:
                    self._connected = False
                    self._last_error = exc
                if self._on_error is not None:
                    self._on_error(exc)
                self._stop_event.wait(self._interval_s)

        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                state = self._connector.poll()
            except Exception as exc:
                # La conexión puede caerse a mitad de vuelo y volver
                # (simulador recargado, equipo saturado). Se intenta
                # restablecer en vez de seguir consultando una conexión
                # muerta para siempre.
                self._reconnect()
                if self._on_error is not None:
                    self._on_error(exc)
                self._stop_event.wait(self._interval_s)
                continue

            duration = time.monotonic() - started
            self._publish(state, duration)

            # Se descuenta lo que ha tardado la consulta para mantener el
            # ritmo pedido aunque el simulador vaya lento.
            self._stop_event.wait(max(0.0, self._interval_s - duration))

    def _reconnect(self) -> None:
        """Reintenta abrir la conexión con el simulador.

        Se llama cuando una consulta falla: el simulador pudo haberse cerrado
        y vuelto a abrir, o estar en un menú. No se distingue la causa: se
        cierra la conexión vieja y se vuelve a intentar.
        """
        try:
            self._connector.disconnect()
        except Exception:
            pass

        try:
            self._connector.connect()
            with self._lock:
                self._connected = True
                self._last_error = None
        except Exception as exc:
            with self._lock:
                self._connected = False
                self._last_error = exc
            if self._on_error is not None:
                self._on_error(exc)

    def _publish(self, state: SimState, duration: float) -> None:
        signature = _signature(state)
        with self._lock:
            changed = signature != self._last_signature
            if changed:
                self._identical_reads = 0
                self._last_signature = signature
            else:
                self._identical_reads += 1

            self._sequence += 1
            self._reading = Reading(
                sequence=self._sequence,
                state=state,
                monotonic=time.monotonic(),
                changed=changed,
            )
            self._poll_duration_s = duration
            self._connected = True
            self._last_error = None
