"""Máquina de estados robusta para el modo automático.

Gestiona el ciclo completo de un vuelo, desde la espera del simulador hasta
la grabación finalizada, evitando falsos positivos por rebotes, touch-and-go
y arranques espurios.

Estados y transiciones:

    ESPERANDO_SIMULADOR
        ↓ hay conexión y datos válidos
    EN_TIERRA (armado, no graba)
        ↓ en tierra y velocidad > 2,7 kt (empieza a rodar)
    RODANDO (tampoco graba: solo informa de la fase)
        ↓ en tierra y velocidad > 50 kt
    CARRERA_DESPEGUE ← **aquí empieza a grabar**
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

**La grabación empieza en la carrera de despegue (50 kt), no en el rodaje.**
Hubo una época en que arrancaba al primer movimiento, para poder verificar
las reglas de luces de rodaje (`taxi_light` y la antigua `strobe_taxi`).
Esas reglas ya no puntúan —de las luces solo queda `strobe_airborne`, que
se comprueba en el aire—, así que grabar el rodaje ya no aporta nada y sí
traía problemas: es la fase donde el simulador da datos menos fiables, y
además obligaba a que un backtrack hasta la cabecera de pista entrara en el
vuelo. `RODANDO` se conserva **sin grabar**, solo para que el piloto vea en
qué fase está.

Que el vuelo llegue a su destino o no ya no lo decide esta máquina: lo
filtra el servidor al subirlo (solo cuentan para estadísticas los vuelos
completos).

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

# Velocidad de rotación: decisión cerrada del proyecto, no configurable.
# Marca la carrera de despegue (y, si se frena por debajo tras alcanzarla,
# el aborto). Por encima de cualquier rodaje y por debajo de cualquier
# rotación real.
SPEED_THRESHOLD_KT = 50.0

# Velocidad para EMPEZAR a grabar: el primer movimiento de rodaje, no el
# despegue (~5 km/h). Deliberadamente bajo para capturar el rodaje entero.
TAXI_MOVEMENT_THRESHOLD_KT = 2.7

# Los tiempos de confirmación se definen en avcars/timing.py, donde se
# comprueba que encajan con la cadencia de muestreo y con la detección de
# datos congelados.
MIN_ALTITUDE_AFTER_LIFTOFF_FT = timing.CONFIRM_LIFTOFF_AGL_FT

# Velocidad mínima para creerse que un avión está en el aire.
#
# Nace de un fallo real (2026-08-25): al abrir EvA con el avión aparcado, el
# simulador contestó `on_ground = False` con altura de sobra —pasa mientras
# el avión se está asentando después de cargar la escena— y la máquina se
# fue a EN_VUELO con el avión a 0,0 kt. Desde EN_VUELO no se graba nunca (es
# la protección para no grabar medio vuelo si abres EvA por la mitad), así
# que la grabación no arrancaba ni en automático ni a mano.
#
# Un avión que de verdad va por el aire se mueve. Muy por debajo de
# cualquier velocidad de vuelo, y muy por encima del ruido de un avión
# parado: solo sirve para descartar el 0 kt, no para decidir nada más.
MIN_GROUNDSPEED_EN_VUELO_KT = 30.0

# Cuánto tiene que durar "parado + freno puesto + motores apagados" para dar
# el vuelo por abandonado. Generoso a propósito: nadie apaga los motores un
# minuto entero en mitad de un rodaje, y cortar la grabación de un vuelo
# bueno es mucho peor que grabar unos minutos de más.
SEGUNDOS_PARA_DAR_POR_ABANDONADO = 60.0
DEFAULT_CONFIRMATION_LIFTOFF_S = timing.CONFIRM_LIFTOFF_S
DEFAULT_CONFIRMATION_LANDING_S = timing.CONFIRM_LANDING_S
DEFAULT_CONFIRMATION_STOPPED_S = timing.CONFIRM_STOPPED_S


class FlightState(Enum):
    """Estados posibles del vuelo."""

    ESPERANDO_SIMULADOR = "esperando_simulador"
    EN_TIERRA = "en_tierra"
    RODANDO = "rodando"
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
    #: Cuánto lleva parado, frenado y sin motores (ver `_vuelo_abandonado`).
    _tiempo_abandonado_s: float = 0.0
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
            return "listo en tierra, empezará a grabar al rodar"
        if self.state == FlightState.RODANDO:
            return "rodando, grabará al acelerar para despegar"
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

    def _vuelo_abandonado(self, state: SimState, elapsed_s: float) -> bool:
        """Rodaje que termina sin vuelo: parado, frenado y sin motores.

        Se exige que el simulador dé **las dos** variables (freno y motores).
        Si falta cualquiera se devuelve False, porque no hay dato: es mejor
        seguir grabando de más que cortarle el vuelo a alguien por una
        suposición.

        Y se exige que la situación **se mantenga**, no que se dé un
        instante. Cortar la grabación de un vuelo bueno es mucho peor que
        grabar de más, y ya pasó una vez: una variable de motores que
        devolvía siempre 0 cortó la grabación de un avión que estaba parado
        con el freno puesto esperando para entrar en pista, con el motor en
        marcha. Aquello se arregló, pero el margen se queda.
        """
        if state.parking_brake is None or state.engine_running is None:
            self._tiempo_abandonado_s = 0.0
            return False

        cumple = (
            state.gs_kt < TAXI_MOVEMENT_THRESHOLD_KT
            and state.parking_brake
            and not state.engine_running
        )
        if not cumple:
            self._tiempo_abandonado_s = 0.0
            return False

        self._tiempo_abandonado_s += elapsed_s
        return self._tiempo_abandonado_s >= SEGUNDOS_PARA_DAR_POR_ABANDONADO

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
            if state.on_ground:
                # En el suelo, parado o ya moviéndose. Antes se exigía
                # `gs_kt < 5` y eso dejaba un callejón sin salida: quien
                # abría EvA con el avión ya rodando no cumplía ni esta
                # condición ni la de estar en el aire, así que se quedaba
                # aquí para siempre y la grabación automática no arrancaba
                # nunca (visto en el vuelo de pruebas del 2026-08-25, con el
                # avión a 25 kt y la ventana diciendo "esperando conexión").
                # No hace falta distinguir la velocidad: de eso ya se ocupa
                # EN_TIERRA en la vuelta siguiente.
                self.state = FlightState.EN_TIERRA
                self.has_flown = False
                self._last_reason = (
                    "conectado, avión en tierra"
                    if state.gs_kt < TAXI_MOVEMENT_THRESHOLD_KT
                    else "conectado con el avión ya rodando"
                )
            elif (
                not state.on_ground
                and state.alt_agl_ft > MIN_ALTITUDE_AFTER_LIFTOFF_FT
                # La velocidad es la que desempata. Sin ella, un avión
                # aparcado al que el simulador contesta `on_ground = False`
                # mientras carga la escena se daba por volando, y como desde
                # EN_VUELO no se graba, el vuelo entero se perdía.
                and state.gs_kt >= MIN_GROUNDSPEED_EN_VUELO_KT
            ):
                # EvA se abrió con el avión ya en el aire. Entra en EN_VUELO
                # pero sin grabar: solo se graba desde EN_TIERRA en adelante.
                self.state = FlightState.EN_VUELO
                self.has_flown = True
                self._last_reason = "EvA abierto en pleno vuelo"
            return action, self.describe_state()

        if self.state == FlightState.EN_TIERRA:
            if state.on_ground and state.gs_kt >= SPEED_THRESHOLD_KT:
                # Ya iba a velocidad de rotación desde la primera muestra:
                # directo a la carrera de despegue, sin pasar por rodaje.
                self.state = FlightState.CARRERA_DESPEGUE
                self.recording = True
                action = "empezar_grabacion"
                self._last_reason = "carrera de despegue iniciada"
                self._time_without_contact_s = 0.0
            elif state.on_ground and state.gs_kt >= TAXI_MOVEMENT_THRESHOLD_KT:
                # Empieza a rodar. **No se graba todavía**: la grabación
                # arranca en la carrera de despegue (ver RODANDO). El estado
                # existe para que el piloto vea en qué fase está.
                self.state = FlightState.RODANDO
                self._last_reason = "rodando, aún no se graba"
            return action, self.describe_state()

        if self.state == FlightState.RODANDO:
            if state.on_ground and state.gs_kt >= SPEED_THRESHOLD_KT:
                # Velocidad de rotación: **aquí empieza la grabación**.
                self.state = FlightState.CARRERA_DESPEGUE
                self.recording = True
                action = "empezar_grabacion"
                self._last_reason = "carrera de despegue iniciada"
                self._time_without_contact_s = 0.0
            elif self._vuelo_abandonado(state, elapsed_s):
                # Parado, con el freno de aparcamiento puesto y los motores
                # apagados: el piloto ha desistido sin llegar a volar. No hay
                # grabación que parar (aquí todavía no se graba); solo se
                # vuelve a EN_TIERRA para dejarlo listo para el siguiente.
                #
                # Hacen falta las tres cosas a la vez **a propósito**: el
                # freno solo no vale, porque hay quien lo usa para
                # mantenerse quieto en el punto de espera cuando no tiene
                # pedales, y ahí el motor sigue en marcha.
                self.state = FlightState.EN_TIERRA
                self._last_reason = "motores parados y freno puesto sin haber volado"
            # Rodar despacio, parar en un cruce, esperar en el punto de
            # espera o hacer backtrack no cambian nada: se sigue en RODANDO
            # sin grabar hasta que se acelera para despegar.
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
            # Parado es parado. Esto comparaba contra SPEED_THRESHOLD_KT
            # (50 kt, la velocidad de rotación), así que daba por detenido
            # un avión que iba a 25 kt saliendo de pista y cerraba el vuelo
            # en mitad del rodaje de llegada — visto en el vuelo de pruebas
            # del 2026-08-25: "avión parado, guardando (GS 25.1 kt)".
            if state.gs_kt < TAXI_MOVEMENT_THRESHOLD_KT:
                self._time_below_threshold_s += elapsed_s
                if self._time_below_threshold_s >= self.confirmation_stopped_s:
                    # Parado de verdad: cierra el vuelo.
                    self.state = FlightState.GUARDANDO
                    self.recording = False
                    action = "parar_grabacion"
                    self._last_reason = "avión parado, guardando"
                    return action, self.describe_state()
            elif not state.on_ground:
                # Volvió a despegar: no era el final del vuelo.
                #
                # De aquí **solo** se sale por el aire, nunca por velocidad.
                # Con un umbral de velocidad, la carrera de deceleración tras
                # aterrizar —que pasa varios segundos por encima de 50 kt—
                # se confundía con un despegue nuevo: EN_TIERRA veía la
                # velocidad alta, saltaba a CARRERA_DESPEGUE, y al seguir
                # frenando lo daba por despegue abortado y cortaba la
                # grabación en plena pista (visto el 2026-08-25 a las
                # 14:45:24, cinco transiciones en dos segundos).
                self.state = FlightState.EN_VUELO
                self._time_without_contact_s = 0.0
                self._last_reason = "volvió a despegar"
            else:
                # Frenando en pista o rodando al aparcamiento: se sigue
                # grabando y el contador espera a que pare de verdad.
                self._time_below_threshold_s = 0.0

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
