"""Tests de la escritura de carga al simulador.

No hace falta MSFS: se le pone al conector un `_requests` de mentira y se mira
qué escribe y qué contesta. Lo que se protege aquí es que **no vuelva a decir
que aplicó la carga cuando no la aplicó**: la versión anterior devolvía `True`
aunque fallaran las dos escrituras, así que la hoja de vuelo decía «aplicado»
y el avión salía vacío.
"""
import pytest

from avcars.config import load_aircraft, load_economia
from avcars.connectors.simconnect_client import SimConnectConnector

LB_A_KG = 0.45359237


class RequestsFalso:
    """Anota lo que se le escribe. `falla_en` hace saltar esas variables."""

    def __init__(self, falla_en=()):
        self.escrito = {}
        self.falla_en = set(falla_en)

    def set(self, nombre, valor):
        if nombre in self.falla_en:
            raise RuntimeError("variable de solo lectura")
        self.escrito[nombre] = valor


def _conector(falla_en=()) -> SimConnectConnector:
    c = SimConnectConnector()
    c._requests = RequestsFalso(falla_en)
    return c


# -- lo que se escribe -------------------------------------------------


def test_la_carga_se_escribe_en_libras():
    c = _conector()

    r = c.set_payload(passengers=4, cargo_kg=100)

    esperado_kg = 4 * SimConnectConnector.KG_POR_PASAJERO + 100
    assert r["carga"] is True
    assert r["carga_kg"] == esperado_kg
    assert c._requests.escrito["PAYLOAD STATION WEIGHT:0"] == pytest.approx(
        esperado_kg / LB_A_KG
    )


def test_el_pasajero_pesa_lo_mismo_que_en_la_economia():
    """Si no coincidieran, el avión volaría con un peso y se cobraría otro."""
    economia = load_economia()

    # `economia.yaml` documenta los 85 kg en el comentario de tarifa_kg_nm;
    # el valor vivo es el del conector, y ambos tienen que ser el mismo.
    assert SimConnectConnector.KG_POR_PASAJERO == 85
    assert economia["ingresos"]["tarifa_pasajero_nm"] > 0


def test_el_combustible_usa_la_capacidad_real_del_avion():
    """Antes se aplicaba el porcentaje sobre 200 lb fijas, que no es de nadie."""
    c = _conector()
    util = load_aircraft()["C172"]["despacho"]["combustible_util_kg"]

    r = c.set_payload(fuel_pct=50, combustible_util_kg=util)

    assert r["combustible_kg"] == pytest.approx(util * 0.5, abs=0.1)
    assert c._requests.escrito["FUEL_TOTAL_QUANTITY_WEIGHT"] == pytest.approx(
        util * 0.5 / LB_A_KG, rel=1e-3
    )


def test_sin_capacidad_no_se_toca_el_combustible():
    c = _conector()

    r = c.set_payload(passengers=2, fuel_pct=75)

    assert r["combustible"] is None
    assert "FUEL_TOTAL_QUANTITY_WEIGHT" not in c._requests.escrito


def test_el_porcentaje_de_combustible_se_recorta_al_rango():
    c = _conector()

    assert c.set_payload(fuel_pct=500, combustible_util_kg=100)["combustible_kg"] == 100
    assert c.set_payload(fuel_pct=-20, combustible_util_kg=100)["combustible_kg"] == 0


# -- lo que NO se promete ----------------------------------------------


def test_sin_conexion_no_dice_que_aplico_nada():
    c = SimConnectConnector()  # sin `_requests`

    r = c.set_payload(passengers=4)

    assert r["carga"] is False
    assert "simulador" in r["motivo"]


def test_si_falla_la_carga_lo_dice():
    c = _conector(falla_en={"PAYLOAD STATION WEIGHT:0"})

    r = c.set_payload(passengers=4)

    assert r["carga"] is False
    assert r["motivo"]


def test_que_el_combustible_falle_no_invalida_la_carga():
    """En MSFS el combustible suele ser de solo lectura; la carga sí entra."""
    c = _conector(falla_en={"FUEL_TOTAL_QUANTITY_WEIGHT"})

    r = c.set_payload(passengers=4, fuel_pct=50, combustible_util_kg=144)

    assert r["carga"] is True
    assert r["combustible"] is False
    assert r["motivo"]
