"""Máquina de estados robusta para el modo automático.

Gestiona el ciclo completo de un vuelo, desde la espera del simulador hasta
la grabación finalizada, evitando falsos positivos por rebotes, touch-and-go
y arranques espurios.

Estados y transiciones:

    ESPERANDO_SIMULADOR
        ↓ hay conexión y datos válidos
    EN_TIERRA (armado, no graba)
        ↓ en tierra y velocidad > 50 kt
    CARRERA_DESPEGUE ← empieza a grabar
        ↓ sin contacto 3s y altitud > 50 ft
    EN_VUELO
        ↓ toca tierra
    EN_PISTA ← en confirmación
        ↑ vuelve a volar (touch-and-go)
        ↓ en tierra 5s y velocidad < 50 kt
    DETENIDO
        ↓ transición automática
    GUARDANDO ← escribe fichero
        ↓ éxito o error
    EN_TIERRA (listo para otro vuelo)

La robustez viene de:
- Exigir permanencia temporal, no cambios por un dato aislado.
- Comprobar velocidad Y contacto, no solo uno de ellos.
- Permitir volver atrás desde EN_PISTA (rebotes, touch-and-go).
- Describir siempre por qué está en cada estado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ..connectors.base import SimState

from .. import timing

# Velocidad de arranque: decisión cerrada del proyecto, no configurable.
# Por encima de cualquier rodaje y por debajo de cualquier rotación.
SPEED_THRESHOLD_KT = 50.0

# Los tiempos de confirmación se definen en avcars/timing.py, donde se
# comprueba que encajan con la cadencia de muestreo y con la detección de
# datos congelados.
MIN_ALTITUDE_AFTER_LIFTOFF_FT = timing.CONFIRM_LIFTOFF_AGL_FT
DEFAULT_CONFIRMATION_LIFTOFF_S = timing.CONFIRM_LIFTOFF_S
DEFAULT_CONFIRMATION_LANDING_S = timing.CONFIRM_LANDING_S
DEFAULT_CONFIRMATION_STOPPED_S = timing.CONFIRM_STOPPED_S


class FlightState(Enum):
    """Estados posibles del vuelo."""

    ESPERANDO_SIMULADOR = "esperando_simulador"
    EN_TIERRA = "en_tierra"
    CARRERA_DESPEGUE = "carrera_despegue"
    EN_VUELO = "en_vuelo"
    EN_PISTA = "en_pista"
    DETENIDO = "detenido"
    GUARDANDO = "guardando"
    ERROR_GUARDADO = "error_guardado"


@dataclass
class FlightStateMachine:
    """Máquina de estados del vuelo.

    Uso:

        machine = FlightStateMachine()
        action, reason = machine.update(state, elapsed_s)

    `elapsed_s` es el tiempo desde la última llamada; se pasa en vez de leer
    el reloj para que los tests sean deterministas y para que se adapte a
    muestreo irregular.
    """

    confirmation_liftoff_s: float = DEFAULT_CONFIRMATION_LIFTOFF_S
    confirmation_landing_s: float = DEFAULT_CONFIRMATION_LANDING_S
    confirmation_stopped_s: float = DEFAULT_CONFIRMATION_STOPPED_S

    state: FlightState = FlightState.ESPERANDO_SIMULADOR
    recording: bool = False
    has_flown: bool = False

    # Acumuladores de tiempo para confirmaciones
    _time_without_contact_s: float = 0.0
    _time_with_contact_s: float = 0.0
    _time_below_threshold_s: float = 0.0

    # Para generar descripciones
    _last_reason: str = "iniciando"

    def reset(self) -> None:
        """Reinicia la máquina para otro vuelo."""
        self.state = FlightState.ESPERANDO_SIMULADOR
        self.recording = False
        self.has_flown = False
        self._time_without_contact_s = 0.0
        self._time_with_contact_s = 0.0
        self._time_below_threshold_s = 0.0
        self._last_reason = "reiniciado"

    @property
    def last_reason(self) -> str:
        """Por qué está en el estado actual."""
        return self._last_reason

    def describe_state(self) -> str:
        """Frase para mostrar en la interfaz."""
        if self.state == FlightState.ESPERANDO_SIMULADOR:
            return "esperando conexión con el simulador"
        if self.state == FlightState.EN_TIERRA:
            return "listo en tierra, empezará a grabar al despegar"
        if self.state == FlightState.CARRERA_DESPEGUE:
            return "carrera de despegue, grabando"
        if self.state == FlightState.EN_VUELO:
            return "en vuelo, grabando"
        if self.state == FlightState.EN_PISTA:
            remaining = max(0, int(self.confirmation_landing_s - self._time_with_contact_s))
            return f"confirmando aterrizaje ({remaining}s), grabando"
        if self.state == FlightState.DETENIDO:
            return "vuelo completado, preparando cierre"
        if self.state == FlightState.GUARDANDO:
            return "guardando el vuelo"
        if self.state == FlightState.ERROR_GUARDADO:
            return f"error al guardar: {self._last_reason}"
        return "estado desconocido"

    def update(self, state: SimState, elapsed_s: float) -> tuple[str, str]:
        """Procesa el estado del simulador y devuelve (acción, motivo).

        Acción es uno de: "nada", "empezar_grabacion", "parar_grabacion",
        "guardar_vuelo", "error_guardado".

        Devuelve también el motivo para la interfaz.
        """
        action = "nada"

        # Datos inválidos: velocidad negativa o imposible
        if state.gs_kt < 0 or state.gs_kt > 1500:
            if self.state != FlightState.ESPERANDO_SIMULADOR:
                self._last_reason = "datos inválidos del simulador"
                self.state = FlightState.ESPERANDO_SIMULADOR
            return action, self.describe_state()

        # Máquina de estados
        if self.state == FlightState.ESPERANDO_SIMULADOR:
            if state.on_ground and state.gs_kt < 5:
                # Datos válidos: el avión está en el suelo y parado.
                self.state = FlightState.EN_TIERRA
                self.has_flown = False
                self._last_reason = "conectado, avión en tierra"
            elif not state.on_ground and state.alt_agl_ft > MIN_ALTITUDE_AFTER_LIFTOFF_FT:
                # EvA se abrió con el avión ya en el aire. Entra en EN_VUELO
                # pero sin grabar: solo se graba desde EN_TIERRA en adelante.
                self.state = FlightState.EN_VUELO
                self.has_flown = True
                self._last_reason = "EvA abierto en pleno vuelo"
            return action, self.describe_state()

        if self.state == FlightState.EN_TIERRA:
            if state.on_ground and state.gs_kt >= SPEED_THRESHOLD_KT:
                # Empieza la carrera de despegue.
                self.state = FlightState.CARRERA_DESPEGUE
                self.recording = True
                action = "empezar_grabacion"
                self._last_reason = "carrera de despegue iniciada"
                self._time_without_contact_s = 0.0
            return action, self.describe_state()

        if self.state == FlightState.CARRERA_DESPEGUE:
            if state.on_ground:
                # Sigue en tierra: acumular o reiniciar según velocidad.
                if state.gs_kt < SPEED_THRESHOLD_KT:
                    # Ha frenado durante la carrera: vuelve a tierra.
                    self.state = FlightState.EN_TIERRA
                    self.recording = False
                    action = "parar_grabacion"
                    self._last_reason = "frenó en carrera, vuelta a tierra"
            else:
                # Sin contacto: contar hacia la confirmación.
                self._time_without_contact_s += elapsed_s
                if (
                    self._time_without_contact_s >= self.confirmation_liftoff_s
                    and state.alt_agl_ft > MIN_ALTITUDE_AFTER_LIFTOFF_FT
                ):
                    self.state = FlightState.EN_VUELO
                    self.has_flown = True
                    self._last_reason = "despegue confirmado"
                    self._time_without_contact_s = 0.0

            return action, self.describe_state()

        if self.state == FlightState.EN_VUELO:
            if state.on_ground:
                # Toca tierra: entra en confirmación de aterrizaje.
                self.state = FlightState.EN_PISTA
                self._time_with_contact_s = 0.0
                self._last_reason = "tocó tierra, confirmando"
            return action, self.describe_state()

        if self.state == FlightState.EN_PISTA:
            if not state.on_ground and state.alt_agl_ft > MIN_ALTITUDE_AFTER_LIFTOFF_FT:
                # Vuelve a volar: touch-and-go o rebote significativo.
                self.state = FlightState.EN_VUELO
                self._last_reason = "volvió a despegar (touch-and-go)"
                self._time_without_contact_s = 0.0
                return action, self.describe_state()

            if state.on_ground:
                # Sigue en tierra: contar hacia la confirmación.
                self._time_with_contact_s += elapsed_s
                if self._time_with_contact_s >= self.confirmation_landing_s:
                    # Confirmado en tierra: esperar a que se detenga.
                    self.state = FlightState.DETENIDO
                    self._last_reason = "aterrizaje confirmado, esperando parada"
                    self._time_below_threshold_s = 0.0
            else:
                # Rebote: reiniciar el contador.
                self._time_with_contact_s = 0.0
                self._last_reason = "rebote detectado"

            return action, self.describe_state()

        if self.state == FlightState.DETENIDO:
            if state.gs_kt < SPEED_THRESHOLD_KT:
                self._time_below_threshold_s += elapsed_s
                if self._time_below_threshold_s >= self.confirmation_stopped_s:
                    # Parado de verdad: cierra el vuelo.
                    self.state = FlightState.GUARDANDO
                    self.recording = False
                    action = "parar_grabacion"
                    self._last_reason = "avión parado, guardando"
                    return action, self.describe_state()
            else:
                # Se movió de nuevo: vuelve a tierra.
                self.state = FlightState.EN_TIERRA
                self._last_reason = "se movió de nuevo"

            return action, self.describe_state()

        if self.state == FlightState.GUARDANDO:
            # La transición a GUARDANDO es una señal de que hay que guardar
            # el fichero. El estado es principalmente informativo; se sale de
            # aquí cuando la interfaz haya guardado y llamado a reset().
            return action, self.describe_state()

        if self.state == FlightState.ERROR_GUARDADO:
            # Igual: informativo. Se sale cuando se solucione o desista.
            return action, self.describe_state()

        return action, self.describe_state()
