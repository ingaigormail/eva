"""Tests del conector SimConnect.

Se prueba con un doble de `AircraftRequests`, porque SimConnect solo existe
en Windows con el simulador abierto. Lo que se verifica aquí es la lógica de
resolución de variables y de conversión de unidades, que es donde ha habido
problemas reales.
"""
import math

from avcars.connectors.simconnect_client import (
    SimConnectConnector,
    _coerce_angle_deg,
    _coerce_latlon_deg,
    _coerce_squawk,
    _coerce_vs_fpm,
)


class FakeRequests:
    """Doble de AircraftRequests que cuenta las consultas."""

    def __init__(self, values: dict) -> None:
        self.values = values
        self.calls: list[str] = []

    def get(self, name: str):
        self.calls.append(name)
        if name not in self.values:
            raise KeyError(name)
        return self.values[name]


def _connector(values: dict) -> SimConnectConnector:
    connector = SimConnectConnector()
    connector._requests = FakeRequests(values)
    return connector


# -- resolución de variables -------------------------------------------


def test_recuerda_que_variable_funciono():
    """Sin memoria, cada ciclo reintenta los nombres que no existen."""
    connector = _connector({"PLANE_LATITUDE": 40.0})
    fake = connector._requests

    connector._read("lat")
    primera_ronda = len(fake.calls)

    connector._read("lat")
    segunda_ronda = len(fake.calls) - primera_ronda

    assert segunda_ronda == 1  # va directa a la que funcionó


def test_no_reintenta_las_variables_que_no_existen():
    """El caso que hacía que cada ciclo tardara segundos."""
    connector = _connector({})
    fake = connector._requests

    connector._read("gear_down")
    llamadas_primera = len(fake.calls)

    for _ in range(10):
        connector._read("gear_down")

    # Tras descartarla una vez, no se vuelve a preguntar.
    assert len(fake.calls) == llamadas_primera


def test_un_campo_ausente_se_marca_como_ausente():
    connector = _connector({})

    assert connector._read("taxi_light") is None
    assert "taxi_light" in connector.missing_variables


def test_usa_el_segundo_candidato_si_el_primero_falla():
    # PLANE_ALTITUDE no está, pero INDICATED_ALTITUDE sí.
    connector = _connector({"INDICATED_ALTITUDE": 3500.0})

    assert connector._read("alt_msl_ft") == 3500.0


def test_si_la_variable_deja_de_responder_se_vuelve_a_buscar():
    connector = _connector({"PLANE_LATITUDE": 40.0})

    assert connector._read("lat") == 40.0

    # El simulador deja de ofrecerla.
    connector._requests.values.clear()
    assert connector._read("lat") is None


# -- conversión de unidades --------------------------------------------


def test_escora_en_radianes_se_convierte_a_grados():
    assert round(_coerce_angle_deg(math.radians(30)), 1) == 30.0


def test_escora_ya_en_grados_se_respeta():
    """Un valor imposible en radianes se interpreta como grados."""
    assert _coerce_angle_deg(45.0) == 45.0


def test_velocidad_vertical_en_fpm_se_respeta():
    assert _coerce_vs_fpm(500.0) == 500.0


def test_velocidad_vertical_pequena_no_se_infla():
    """Regresión: una VS de 54 fpm no debe grabarse como 3240.

    El heurístico antiguo la confundía con pies/segundo y la multiplicaba
    por 60.
    """
    assert _coerce_vs_fpm(54.0) == 54.0


def test_latitud_en_grados_se_respeta():
    assert _coerce_latlon_deg(40.47) == 40.47


def test_longitud_pequena_no_se_infla():
    """Regresión: una longitud española como -0.47 no debe multiplicarse.

    El heurístico antiguo la confundía con radianes y la grababa como
    -27.08 (×57,3), disparando la distancia del vuelo.
    """
    assert round(_coerce_latlon_deg(-0.4727), 4) == -0.4727


def test_squawk_en_bcd_se_lee_como_numero():
    assert _coerce_squawk(0x7000) == "7000"
    assert _coerce_squawk(0x1200) == "1200"


def test_valores_no_numericos_no_rompen():
    assert _coerce_angle_deg("no es un número") is None
    assert _coerce_vs_fpm(None) is None
    assert _coerce_squawk(None) == ""
    assert _coerce_angle_deg(float("nan")) is None


# -- poll --------------------------------------------------------------


def test_poll_devuelve_un_estado_completo():
    connector = _connector(
        {
            "PLANE_LATITUDE": 40.47,
            "PLANE_LONGITUDE": -3.56,
            "PLANE_ALTITUDE": 4000.0,
            "PLANE_ALT_ABOVE_GROUND": 3000.0,
            "PLANE_HEADING_DEGREES_TRUE": math.radians(180),
            "GROUND_VELOCITY": 110.0,
            "AIRSPEED_INDICATED": 105.0,
            "VERTICAL_SPEED": 500.0,
            "SIM_ON_GROUND": 0,
            "FUEL_TOTAL_QUANTITY_WEIGHT": 220.0,
            "TRANSPONDER_CODE:1": 0x7000,
            "SIMULATION_RATE": 1.0,
            "PLANE_BANK_DEGREES": math.radians(15),
            "LIGHT_BEACON": 1,
        }
    )

    state = connector.poll()

    assert round(state.lat, 2) == 40.47
    assert round(state.lon, 2) == -3.56
    assert state.gs_kt == 110.0
    assert round(state.vs_fpm) == 500
    assert round(state.hdg_deg) == 180
    assert round(state.bank_deg, 1) == 15.0
    assert state.squawk == "7000"
    assert state.beacon_light is True
    assert not state.on_ground
    # El combustible se convierte de libras a kilos.
    assert round(state.fuel_kg) == 100


def test_poll_guarda_los_valores_sin_convertir():
    """El panel de diagnóstico los usa para verificar unidades en vuelo."""
    connector = _connector({"PLANE_BANK_DEGREES": 0.2618})

    state = connector.poll()

    assert state.raw["bank_deg"] == 0.2618


def test_qnh_en_inhg_se_respeta():
    connector = _connector({"KOHLSMAN_SETTING_HG": 29.921})

    state = connector.poll()

    assert state.qnh_inhg == 29.921
    assert state.raw["qnh_inhg"] == 29.921


def test_avisos_del_simulador_y_piloto_automatico():
    connector = _connector(
        {
            "STALL_WARNING": 1,
            "OVERSPEED_WARNING": 0,
            "AUTOPILOT_MASTER": 1,
            "GEAR_HANDLE_POSITION": 1,
        }
    )

    state = connector.poll()

    assert state.stall_warning is True
    assert state.overspeed_warning is False
    assert state.autopilot_engaged is True
    assert state.gear_down is True


def test_qnh_ausente_o_invalido_no_rompe():
    connector = _connector({"KOHLSMAN_SETTING_HG": None})

    state = connector.poll()

    assert state.qnh_inhg is None
    assert state.stall_warning is None


class TestTextoDelSimulador:
    """MSFS devuelve el modelo envuelto en una clave de traducción."""

    def test_saca_el_tipo_icao_de_la_clave_de_traduccion(self):
        from avcars.connectors.simconnect_client import _coerce_texto

        assert _coerce_texto(b"TT:ATCCOM.AC_MODEL_C172.0.text") == "C172"
        assert _coerce_texto(b"TT:ATCCOM.ATC_NAME_C25C.0.text") == "C25C"

    def test_un_texto_normal_se_deja_como_esta(self):
        from avcars.connectors.simconnect_client import _coerce_texto

        assert _coerce_texto(b"C172") == "C172"
        assert _coerce_texto(b"Cessna 172 Skyhawk") == "Cessna 172 Skyhawk"

    def test_vacio_es_none_y_no_cadena_vacia(self):
        """Un dato ausente tiene que distinguirse de uno vacío."""
        from avcars.connectors.simconnect_client import _coerce_texto

        assert _coerce_texto(b"") is None
        assert _coerce_texto(None) is None
        assert _coerce_texto(b"  \x00 ") is None
