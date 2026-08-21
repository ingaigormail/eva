"""Tests de la máquina de estados robusta.

Casos de prueba exhaustivos para evitar falsos positivos, especialmente:
- Arranque espurio si EvA se abre en pleno vuelo.
- Cierre por rebote.
- Cierre por touch-and-go.
- Cambios sin permanencia temporal.
"""
from avcars.connectors.base import SimState
from avcars.recorder.flight_state_machine import FlightState, FlightStateMachine


def _state(
    gs_kt: float = 0,
    on_ground: bool = True,
    alt_agl_ft: float = 0,
) -> SimState:
    """Estado de simulador con mínimos especificados."""
    return SimState(
        lat=40.0,
        lon=-3.0,
        alt_msl_ft=2000.0,
        alt_agl_ft=alt_agl_ft,
        hdg_deg=180.0,
        gs_kt=gs_kt,
        ias_kt=gs_kt,
        vs_fpm=0.0,
        on_ground=on_ground,
        fuel_kg=100.0,
        squawk="7000",
        sim_rate=1.0,
    )


class TestInitAndReset:
    def test_comienza_esperando_simulador(self):
        machine = FlightStateMachine()
        assert machine.state == FlightState.ESPERANDO_SIMULADOR
        assert not machine.recording
        assert not machine.has_flown

    def test_reset_limpia_todo(self):
        machine = FlightStateMachine()
        machine.state = FlightState.EN_VUELO
        machine.recording = True
        machine.has_flown = True
        machine.reset()

        assert machine.state == FlightState.ESPERANDO_SIMULADOR
        assert not machine.recording
        assert not machine.has_flown


class TestEsperandoSimulador:
    def test_datos_invalidos_se_quedan_esperando(self):
        machine = FlightStateMachine()
        machine.update(_state(gs_kt=-50), 1.0)
        assert machine.state == FlightState.ESPERANDO_SIMULADOR

        machine.update(_state(gs_kt=9999), 1.0)
        assert machine.state == FlightState.ESPERANDO_SIMULADOR

    def test_transicion_a_tierra_con_datos_validos(self):
        machine = FlightStateMachine()
        action, _ = machine.update(_state(gs_kt=0, on_ground=True), 1.0)

        assert machine.state == FlightState.EN_TIERRA
        assert action == "nada"
        assert not machine.recording


class TestAbrir_Eva_Volando:
    """El fallo que reportó Igor."""

    def test_abrir_eva_en_pleno_vuelo_no_arranca_grabacion(self):
        """Si EvA se abre con el avión ya en el aire, no graba."""
        machine = FlightStateMachine()

        # El simulador reporta vuelo en progreso.
        for _ in range(10):
            action, _ = machine.update(
                _state(gs_kt=120, on_ground=False, alt_agl_ft=2000), 1.0
            )
            assert action == "nada"
            assert not machine.recording

        # El avión sigue volando, máquina en EN_VUELO pero sin grabar.
        assert machine.state == FlightState.EN_VUELO


class TestEnTierra:
    def test_transicion_a_carrera_con_velocidad(self):
        machine = FlightStateMachine()
        machine.state = FlightState.EN_TIERRA
        action, _ = machine.update(_state(gs_kt=60, on_ground=True), 1.0)

        assert action == "empezar_grabacion"
        assert machine.recording
        assert machine.state == FlightState.CARRERA_DESPEGUE

    def test_no_arranca_con_pico_aislado(self):
        """Un aumento puntual de velocidad no dispara nada."""
        machine = FlightStateMachine()
        machine.state = FlightState.EN_TIERRA

        # Pico
        machine.update(_state(gs_kt=55, on_ground=True), 1.0)
        # Pero luego vuelve a bajar
        machine.update(_state(gs_kt=20, on_ground=True), 1.0)

        assert machine.state == FlightState.EN_TIERRA
        assert not machine.recording


class TestCarreraDespegue:
    def test_frena_durante_carrera_vuelve_a_tierra(self):
        """Despegue abortado: frena y queda en tierra."""
        machine = FlightStateMachine()
        machine.state = FlightState.CARRERA_DESPEGUE
        machine.recording = True

        machine.update(_state(gs_kt=10, on_ground=True), 1.0)

        assert machine.state == FlightState.EN_TIERRA
        assert not machine.recording

    def test_despegue_real_con_confirmacion(self):
        """Sin contacto 3s + altura > 50 ft confirma despegue."""
        machine = FlightStateMachine(confirmation_liftoff_s=3.0)
        machine.state = FlightState.CARRERA_DESPEGUE
        machine.recording = True

        for i in range(5):
            action, _ = machine.update(
                _state(gs_kt=80, on_ground=False, alt_agl_ft=100), 1.0
            )
            if i < 2:
                assert machine.state == FlightState.CARRERA_DESPEGUE
            else:
                assert machine.state == FlightState.EN_VUELO
                break


class TestEnVuelo:
    def test_toca_tierra_entra_en_pista(self):
        machine = FlightStateMachine()
        machine.state = FlightState.EN_VUELO
        machine.recording = True

        action, _ = machine.update(_state(gs_kt=80, on_ground=True), 1.0)

        assert machine.state == FlightState.EN_PISTA
        assert machine.recording  # sigue grabando


class TestEnPista_Rebote_TouchAndGo:
    def test_rebote_simple_reinicia_contador(self):
        """Un rebote corto (sin despegar de verdad) reinicia el contador."""
        machine = FlightStateMachine(confirmation_landing_s=5.0)
        machine.state = FlightState.EN_PISTA
        machine.recording = True

        # Toca tierra
        machine.update(_state(gs_kt=50, on_ground=True), 1.0)

        # Rebota
        for _ in range(2):
            machine.update(_state(gs_kt=60, on_ground=False, alt_agl_ft=20), 1.0)

        # Vuelve a tocar
        machine.update(_state(gs_kt=40, on_ground=True), 1.0)

        # El contador se reinicia con el rebote
        assert machine.state == FlightState.EN_PISTA

    def test_touch_and_go_vuelve_a_en_vuelo(self):
        """Si despega de verdad desde EN_PISTA, vuelve a EN_VUELO."""
        machine = FlightStateMachine()
        machine.state = FlightState.EN_PISTA
        machine.recording = True

        # Despega
        action, _ = machine.update(
            _state(gs_kt=100, on_ground=False, alt_agl_ft=500), 1.0
        )

        assert machine.state == FlightState.EN_VUELO
        assert machine.recording
        assert action == "nada"

    def test_aterrizaje_confirmado_tras_5_segundos(self):
        """5s en tierra confirma aterrizaje."""
        machine = FlightStateMachine(confirmation_landing_s=5.0)
        machine.state = FlightState.EN_PISTA

        for i in range(6):
            machine.update(_state(gs_kt=30, on_ground=True), 1.0)
            if i < 4:
                assert machine.state == FlightState.EN_PISTA
            else:
                assert machine.state == FlightState.DETENIDO


class TestDetenido:
    def test_parada_confirmada_tras_10_segundos(self):
        """10s < 50 kt confirma parada total."""
        machine = FlightStateMachine(confirmation_stopped_s=10.0)
        machine.state = FlightState.DETENIDO

        # 10 iteraciones de 1 segundo cada una
        for i in range(10):
            action, _ = machine.update(_state(gs_kt=0, on_ground=True), 1.0)
            if i < 9:
                assert machine.state == FlightState.DETENIDO
                assert action == "nada"
            else:
                # En la iteración 9 (10 segundos), transiciona
                assert machine.state == FlightState.GUARDANDO
                assert action == "parar_grabacion"

    def test_se_mueve_de_nuevo_vuelve_a_tierra(self):
        """Si se mueve mientras está detenido, vuelve a EN_TIERRA."""
        machine = FlightStateMachine()
        machine.state = FlightState.DETENIDO

        machine.update(_state(gs_kt=60, on_ground=True), 1.0)

        assert machine.state == FlightState.EN_TIERRA


class TestDescripciones:
    def test_describe_state_cambia_segun_estado(self):
        machine = FlightStateMachine()

        assert "esperando" in machine.describe_state().lower()

        machine.state = FlightState.EN_TIERRA
        assert "tierra" in machine.describe_state().lower()

        machine.state = FlightState.EN_VUELO
        assert "vuelo" in machine.describe_state().lower()

        machine.state = FlightState.GUARDANDO
        assert "guardando" in machine.describe_state().lower()


class TestVueloCompleto:
    def test_vuelo_tipico_completo(self):
        """Vuelo típico de inicio a fin."""
        machine = FlightStateMachine(
            confirmation_liftoff_s=2.0,
            confirmation_landing_s=2.0,
            confirmation_stopped_s=2.0,
        )

        # Inicio: conectar
        machine.update(_state(gs_kt=0, on_ground=True), 1.0)
        assert machine.state == FlightState.EN_TIERRA

        # Carrera de despegue
        action, _ = machine.update(_state(gs_kt=60, on_ground=True), 1.0)
        assert action == "empezar_grabacion"
        assert machine.state == FlightState.CARRERA_DESPEGUE

        # Despegue real
        for _ in range(3):
            machine.update(_state(gs_kt=120, on_ground=False, alt_agl_ft=200), 1.0)
        assert machine.state == FlightState.EN_VUELO

        # Vuelo normal
        for _ in range(5):
            machine.update(_state(gs_kt=100, on_ground=False, alt_agl_ft=5000), 1.0)
        assert machine.state == FlightState.EN_VUELO

        # Aterrizaje
        machine.update(_state(gs_kt=80, on_ground=True, alt_agl_ft=0), 1.0)
        assert machine.state == FlightState.EN_PISTA

        for _ in range(3):
            machine.update(_state(gs_kt=20, on_ground=True, alt_agl_ft=0), 1.0)
        assert machine.state == FlightState.DETENIDO

        # Parada
        for _ in range(3):
            machine.update(_state(gs_kt=0, on_ground=True), 1.0)
        assert machine.state == FlightState.GUARDANDO

        # Listo para siguiente vuelo
        machine.reset()
        assert machine.state == FlightState.ESPERANDO_SIMULADOR
        assert not machine.recording
