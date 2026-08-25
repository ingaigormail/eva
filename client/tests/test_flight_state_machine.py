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
    parking_brake: bool | None = None,
    engine_running: bool | None = None,
) -> SimState:
    """Estado de simulador con mínimos especificados.

    `parking_brake` y `engine_running` van a None por defecto a propósito:
    es lo que devuelve un simulador que no dé esas variables, y así el resto
    de pruebas siguen reflejando el caso normal.
    """
    return SimState(
        parking_brake=parking_brake,
        engine_running=engine_running,
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


class TestRodando:
    def test_empezar_a_rodar_no_graba_todavia(self):
        """La grabación empieza en la carrera de despegue, no al rodar.

        Arrancaba al primer movimiento para poder verificar las luces de
        rodaje; esas reglas ya no puntúan, así que grabar el rodaje solo
        añadía ruido — y metía en el vuelo el backtrack a cabecera.
        """
        machine = FlightStateMachine()
        machine.state = FlightState.EN_TIERRA

        action, _ = machine.update(_state(gs_kt=5, on_ground=True), 1.0)

        assert action == "nada"
        assert not machine.recording
        assert machine.state == FlightState.RODANDO

    def test_por_debajo_del_umbral_no_arranca(self):
        machine = FlightStateMachine()
        machine.state = FlightState.EN_TIERRA

        action, _ = machine.update(_state(gs_kt=1, on_ground=True), 1.0)

        assert action == "nada"
        assert not machine.recording
        assert machine.state == FlightState.EN_TIERRA

    def test_parar_en_un_cruce_no_corta_la_grabacion(self):
        """A diferencia de la carrera de despegue, aquí frenar no aborta."""
        machine = FlightStateMachine()
        machine.state = FlightState.RODANDO

        for gs in (10, 0, 0, 3, 15):
            action, _ = machine.update(_state(gs_kt=gs, on_ground=True), 1.0)
            assert action == "nada"
            assert machine.state == FlightState.RODANDO

    def test_alcanza_velocidad_de_rotacion_pasa_a_carrera_despegue(self):
        machine = FlightStateMachine()
        machine.state = FlightState.RODANDO

        action, _ = machine.update(_state(gs_kt=60, on_ground=True), 1.0)

        # Aquí es donde arranca la grabación.
        assert action == "empezar_grabacion"
        assert machine.recording
        assert machine.state == FlightState.CARRERA_DESPEGUE


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

    def test_moverse_por_el_suelo_no_saca_de_detenido(self):
        """Este test decía justo lo contrario, y ahí estaba el fallo.

        Daba por bueno que moverse a 60 kt en DETENIDO devolviera a
        EN_TIERRA. Pero después de aterrizar se pasan varios segundos
        frenando por encima de esa velocidad, así que en un vuelo real
        (2026-08-25) eso encadenaba EN_TIERRA → CARRERA_DESPEGUE →
        "frenó en carrera" y cortaba la grabación en plena pista.
        """
        machine = FlightStateMachine()
        machine.state = FlightState.DETENIDO

        machine.update(_state(gs_kt=60, on_ground=True), 1.0)

        assert machine.state == FlightState.DETENIDO


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


class TestAbrirEvAConElAvionYaRodando:
    """El fallo del vuelo de pruebas del 2026-08-25.

    `ESPERANDO_SIMULADOR` solo tenía dos salidas: en tierra **y parado**
    (`gs_kt < 5`), o en el aire por encima de 50 ft. Quien abría EvA con el
    avión ya rodando no cumplía ninguna de las dos y se quedaba encallado:
    la ventana decía "esperando conexión con el simulador" con el avión a
    25 kt, y como nunca se llegaba a `EN_TIERRA`, la comprobación de los
    2,7 kt no se hacía jamás y la grabación automática no arrancaba.
    """

    def test_sale_de_esperando_aunque_el_avion_ya_este_rodando(self):
        machine = FlightStateMachine()

        machine.update(_state(gs_kt=25, on_ground=True), 1.0)

        assert machine.state != FlightState.ESPERANDO_SIMULADOR

    def test_acaba_grabando_sin_tener_que_parar_el_avion(self):
        """Lo que de verdad importa: que termine grabando al despegar.

        Ya no graba al rodar, así que se comprueba que la máquina sale del
        atasco y llega a grabar cuando el piloto acelera.
        """
        machine = FlightStateMachine()

        machine.update(_state(gs_kt=25, on_ground=True), 1.0)
        accion, _ = machine.update(_state(gs_kt=60, on_ground=True), 1.0)

        assert accion == "empezar_grabacion"
        assert machine.recording

    def test_con_el_avion_parado_sigue_funcionando_como_antes(self):
        """El caso normal no puede haberse roto por el arreglo."""
        machine = FlightStateMachine()

        machine.update(_state(gs_kt=0, on_ground=True), 1.0)

        assert machine.state == FlightState.EN_TIERRA
        assert not machine.recording

    def test_abrir_en_pleno_vuelo_sigue_sin_grabar(self):
        """La otra salida de ESPERANDO_SIMULADOR no se ha tocado."""
        machine = FlightStateMachine()

        machine.update(_state(gs_kt=250, on_ground=False, alt_agl_ft=8000), 1.0)

        assert machine.state == FlightState.EN_VUELO
        assert not machine.recording


class TestRodajeQueNuncaDespega:
    """Rodar y aparcar sin llegar a volar.

    Antes esto importaba mucho: la grabación arrancaba al rodar y, si el
    piloto desistía, no paraba nunca. Ahora no se graba hasta la carrera de
    despegue, así que no hay nada que cortar — pero la máquina sí tiene que
    volver a EN_TIERRA para quedar lista para el intento siguiente.
    """

    def _rodando(self) -> FlightStateMachine:
        machine = FlightStateMachine()
        machine.update(_state(gs_kt=0, on_ground=True), 1.0)
        machine.update(_state(gs_kt=10, on_ground=True), 1.0)
        assert machine.state == FlightState.RODANDO
        assert not machine.recording
        return machine

    def test_aparcar_deja_la_maquina_lista_para_otro_intento(self):
        machine = self._rodando()
        parado = _state(
            gs_kt=0, on_ground=True, parking_brake=True, engine_running=False
        )

        # No basta un instante: la condición tiene que mantenerse.
        machine.update(parado, 1.0)
        assert machine.state == FlightState.RODANDO

        machine.update(parado, 60.0)

        assert machine.state == FlightState.EN_TIERRA
        assert not machine.recording

    def test_el_freno_con_el_motor_en_marcha_no_hace_nada(self):
        """El piloto sin pedales que frena en el punto de espera."""
        machine = self._rodando()

        machine.update(
            _state(gs_kt=0, on_ground=True, parking_brake=True, engine_running=True),
            120.0,
        )

        assert machine.state == FlightState.RODANDO

    def test_sin_esos_datos_no_se_decide_por_suposiciones(self):
        machine = self._rodando()

        machine.update(_state(gs_kt=0, on_ground=True), 120.0)

        assert machine.state == FlightState.RODANDO

    def test_desde_ahi_todavia_se_puede_despegar(self):
        """Aparcar no puede impedir grabar el vuelo siguiente."""
        machine = self._rodando()
        machine.update(
            _state(gs_kt=0, on_ground=True, parking_brake=True, engine_running=False),
            60.0,
        )

        accion, _ = machine.update(_state(gs_kt=60, on_ground=True), 1.0)

        assert accion == "empezar_grabacion"
        assert machine.recording


class TestAvionAparcadoQueElSimuladorDaComoVolando:
    """El fallo del 2026-08-25, visto en el registro de un vuelo real.

    Al abrir EvA con el avión aparcado, el simulador contestó
    `on_ground = False` con altura de sobra —pasa mientras la escena
    termina de cargar— y la máquina saltó a EN_VUELO con el avión a
    0,0 kt. Desde EN_VUELO no se graba nunca, así que el vuelo no se
    grabó ni en automático ni dándole a mano: la ventana decía
    "detenido" todo el rato.
    """

    def test_a_cero_nudos_no_se_esta_volando(self):
        machine = FlightStateMachine()

        machine.update(
            _state(gs_kt=0.0, on_ground=False, alt_agl_ft=500), 1.0
        )

        assert machine.state != FlightState.EN_VUELO
        assert not machine.has_flown

    def test_y_acaba_grabando_cuando_el_avion_empieza_a_rodar(self):
        """Lo que importa: que el vuelo no se pierda."""
        machine = FlightStateMachine()

        # Escena cargando: el simulador miente sobre `on_ground`.
        machine.update(_state(gs_kt=0.0, on_ground=False, alt_agl_ft=500), 1.0)
        # Ya asentado: rueda y luego acelera para despegar.
        machine.update(_state(gs_kt=0.0, on_ground=True), 1.0)
        machine.update(_state(gs_kt=8.0, on_ground=True), 1.0)
        accion, _ = machine.update(_state(gs_kt=60.0, on_ground=True), 1.0)

        assert accion == "empezar_grabacion"
        assert machine.recording

    def test_abrir_de_verdad_en_pleno_vuelo_sigue_detectandose(self):
        """El caso legítimo no puede haberse roto: ahí el avión va rápido."""
        machine = FlightStateMachine()

        machine.update(
            _state(gs_kt=250.0, on_ground=False, alt_agl_ft=8000), 1.0
        )

        assert machine.state == FlightState.EN_VUELO
        assert machine.has_flown
        assert not machine.recording


class TestSalidaDePistaDespuesDeAterrizar:
    """Del registro de un vuelo real (2026-08-25):

        DETENIDO → GUARDANDO: avión parado, guardando (GS 25.1 kt)

    `DETENIDO` comparaba contra los 50 kt de la velocidad de rotación, así
    que daba por detenido un avión que salía de pista a 25 kt y cerraba el
    vuelo en mitad del rodaje de llegada. Peor aún: al seguir rodando,
    arrancaba acto seguido una segunda grabación del mismo vuelo.
    """

    def _aterrizado(self) -> FlightStateMachine:
        machine = FlightStateMachine(confirmation_stopped_s=10.0)
        machine.state = FlightState.DETENIDO
        machine.recording = True
        machine.has_flown = True
        return machine

    def test_saliendo_de_pista_no_se_cierra_el_vuelo(self):
        machine = self._aterrizado()

        for _ in range(6):
            accion, _ = machine.update(_state(gs_kt=25.1, on_ground=True), 5.0)
            assert accion == "nada"

        assert machine.recording

    def test_se_cierra_cuando_para_de_verdad(self):
        machine = self._aterrizado()

        machine.update(_state(gs_kt=25.0, on_ground=True), 5.0)   # rodando
        machine.update(_state(gs_kt=0.0, on_ground=True), 5.0)    # frena
        accion, _ = machine.update(_state(gs_kt=0.0, on_ground=True), 6.0)

        assert accion == "parar_grabacion"
        assert machine.state == FlightState.GUARDANDO

    def test_el_rodaje_de_llegada_entero_queda_grabado(self):
        """Un rodaje largo hasta el aparcamiento no puede perderse."""
        machine = self._aterrizado()

        for gs in (30, 20, 15, 8, 12, 5, 20, 10):
            machine.update(_state(gs_kt=gs, on_ground=True), 5.0)
            assert machine.recording


class TestCarreraDeDeceleracionTrasAterrizar:
    """Del registro del 2026-08-25, cinco transiciones en dos segundos:

        EN_PISTA  → DETENIDO           (GS 57.6 kt)
        DETENIDO  → EN_TIERRA          "se movió de nuevo"
        EN_TIERRA → CARRERA_DESPEGUE   (GS 52.8 kt)
        CARRERA_DESPEGUE → EN_TIERRA   "frenó en carrera"
        grabación detenida

    Al aterrizar se pasan varios segundos frenando por encima de 50 kt, y
    eso se confundía con un despegue nuevo que acababa "abortado". De
    DETENIDO solo se sale por el aire, nunca por velocidad.
    """

    def _recien_aterrizado(self) -> FlightStateMachine:
        machine = FlightStateMachine(confirmation_stopped_s=10.0)
        machine.state = FlightState.DETENIDO
        machine.recording = True
        machine.has_flown = True
        return machine

    def test_frenar_en_pista_no_corta_la_grabacion(self):
        machine = self._recien_aterrizado()

        for gs in (57.6, 52.8, 47.8, 30.0, 15.0):
            accion, _ = machine.update(_state(gs_kt=gs, on_ground=True), 1.0)
            assert accion == "nada", f"cortó a {gs} kt"
            assert machine.recording
            assert machine.state == FlightState.DETENIDO

    def test_un_despegue_de_verdad_si_saca_de_detenido(self):
        """Stop and go: si vuelve al aire, el vuelo continúa."""
        machine = self._recien_aterrizado()

        machine.update(
            _state(gs_kt=80.0, on_ground=False, alt_agl_ft=200), 1.0
        )

        assert machine.state == FlightState.EN_VUELO
        assert machine.recording

    def test_el_vuelo_se_cierra_al_parar_tras_el_rodaje(self):
        machine = self._recien_aterrizado()

        for gs in (57.6, 40.0, 20.0, 8.0):
            machine.update(_state(gs_kt=gs, on_ground=True), 2.0)
        machine.update(_state(gs_kt=0.0, on_ground=True), 5.0)
        accion, _ = machine.update(_state(gs_kt=0.0, on_ground=True), 6.0)

        assert accion == "parar_grabacion"
        assert machine.state == FlightState.GUARDANDO
