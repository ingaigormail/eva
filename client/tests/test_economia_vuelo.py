"""Tests del cálculo económico de un vuelo."""
import pytest

from avcars.config import load_aircraft, load_economia
from avcars.economia_vuelo import calcular, tarifa_hora

ECONOMIA = load_economia()
AVIONES = load_aircraft()


def _vuelo(**cambios) -> dict:
    """Un vuelo APTO de una hora y 120 NM en Caravan, offline."""
    base = dict(
        aeronave="C208",
        origen="LEMD",
        destino="LEBL",
        distancia_nm=120.0,
        duracion_min=60.0,
        combustible_usado_kg=180.0,
        calidad="apto",
        red="OFFLINE",
        control_atc=0,
        perfil_evaluacion="normal",
    )
    base.update(cambios)
    return base


# -- ingresos ----------------------------------------------------------


def test_un_vuelo_apto_cobra_la_base_por_milla():
    """Sin pasajeros contados, se factura la base y nada más."""
    r = calcular(_vuelo(), ECONOMIA, aviones=AVIONES)

    base_nm = ECONOMIA["ingresos"]["base_nm"]
    assert r["bruto"] == pytest.approx(120 * base_nm)
    assert r["ingreso"] == pytest.approx(r["bruto"])  # apto = x1, sin bonos


def test_un_vuelo_no_apto_cobra_la_fraccion_del_fichero():
    r = calcular(_vuelo(calidad="no_apto"), ECONOMIA, aviones=AVIONES)

    assert r["multiplicador_calidad"] == ECONOMIA["calidad"]["no_apto"]
    assert r["ingreso"] < calcular(_vuelo(), ECONOMIA, aviones=AVIONES)["ingreso"]


def test_los_vuelos_cortos_facturan_la_distancia_minima():
    """Encadenar saltos de 5 NM no puede ser rentable por acumular bases."""
    minima = ECONOMIA["ingresos"]["distancia_minima_nm"]

    corto = calcular(_vuelo(distancia_nm=5.0), ECONOMIA, aviones=AVIONES)
    justo = calcular(_vuelo(distancia_nm=float(minima)), ECONOMIA, aviones=AVIONES)

    assert corto["bruto"] == justo["bruto"]


# -- bonificaciones ----------------------------------------------------


def test_volar_en_red_bonifica():
    offline = calcular(_vuelo(), ECONOMIA, aviones=AVIONES)
    en_red = calcular(_vuelo(red="VATSIM"), ECONOMIA, aviones=AVIONES)

    assert en_red["bonificacion"] == ECONOMIA["bonus"]["vatsim"]
    assert en_red["ingreso"] > offline["ingreso"]


def test_las_bonificaciones_no_pasan_del_tope():
    r = calcular(
        _vuelo(red="VATSIM", control_atc=1, perfil_evaluacion="hard"),
        ECONOMIA,
        aviones=AVIONES,
    )

    assert r["bonificacion"] == ECONOMIA["bonus"]["tope"]


# -- costes ------------------------------------------------------------


def test_el_avion_propio_paga_mantenimiento_y_no_alquiler():
    alquilado = calcular(_vuelo(), ECONOMIA, aviones=AVIONES, es_propio=False)
    propio = calcular(_vuelo(), ECONOMIA, aviones=AVIONES, es_propio=True)

    pct = ECONOMIA["compra_aviones"]["mantenimiento_pct"]
    assert propio["desglose_costes"]["hora_avion"] == pytest.approx(
        alquilado["desglose_costes"]["hora_avion"] * pct
    )
    assert propio["neto"] > alquilado["neto"]


def test_comprar_no_toca_el_resto_de_costes():
    alquilado = calcular(_vuelo(), ECONOMIA, aviones=AVIONES, es_propio=False)
    propio = calcular(_vuelo(), ECONOMIA, aviones=AVIONES, es_propio=True)

    for concepto in ("combustible", "tasas", "handling"):
        assert alquilado["desglose_costes"][concepto] == propio["desglose_costes"][concepto]


def test_sin_consumo_registrado_se_estima_con_el_del_avion():
    """Un CSV no trae combustible; cobrar cero premiaría la herramienta pobre."""
    r = calcular(_vuelo(combustible_usado_kg=None), ECONOMIA, aviones=AVIONES)

    consumo = AVIONES["C208"]["despacho"]["consumo_kg_h"]
    precio = ECONOMIA["costes"]["precio_combustible_kg"]
    assert r["combustible_estimado"]
    assert r["desglose_costes"]["combustible"] == pytest.approx(consumo * precio)


def test_las_tasas_dependen_del_tamano_del_aerodromo():
    tabla = ECONOMIA["costes"]["tasas"]

    grandes = calcular(
        _vuelo(), ECONOMIA, aviones=AVIONES, tamano_aerodromo=lambda _i: "large"
    )
    pequenos = calcular(
        _vuelo(), ECONOMIA, aviones=AVIONES, tamano_aerodromo=lambda _i: "small"
    )

    assert grandes["desglose_costes"]["tasas"] == 2 * tabla["large"]
    assert pequenos["desglose_costes"]["tasas"] == 2 * tabla["small"]


def test_sin_saber_el_aerodromo_se_cobra_la_tasa_de_desconocido():
    r = calcular(_vuelo(), ECONOMIA, aviones=AVIONES)

    assert r["desglose_costes"]["tasas"] == 2 * ECONOMIA["costes"]["tasas"]["desconocido"]


# -- vuelos que no mueven dinero ---------------------------------------


def test_un_vuelo_no_evaluable_no_mueve_dinero():
    """Ni ingreso ni coste: es un fallo técnico, no una trampa del piloto."""
    r = calcular(_vuelo(calidad="no_evaluable"), ECONOMIA, aviones=AVIONES)

    assert r["sin_movimiento"]
    assert r["ingreso"] == 0
    assert r["coste"] == 0
    assert r["neto"] == 0


def test_un_csv_sin_veredicto_tampoco_mueve_dinero():
    r = calcular(_vuelo(calidad=None), ECONOMIA, aviones=AVIONES)

    assert r["sin_movimiento"]
    assert r["neto"] == 0


def test_un_vuelo_con_datos_rotos_vale_cero_pero_no_revienta():
    """La cartilla no se puede caer por un vuelo raro."""
    r = calcular({"aeronave": None, "distancia_nm": "x"}, ECONOMIA, aviones=AVIONES)

    assert r["neto"] == 0


# -- la tarifa por hora ------------------------------------------------


def test_la_tarifa_de_un_avion_desconocido_es_cero():
    assert tarifa_hora("XXXX", ECONOMIA, es_propio=False) == 0


def test_el_c172_cuesta_lo_mismo_aunque_se_marque_propio():
    """No está a la venta, así que nunca debería llegar como propio.

    Si alguien fuerza la ruta de compra con un C172, el peor resultado posible
    es que le cobren el 25%: no se le regala el avión de entrada.
    """
    alquilado = tarifa_hora("C172", ECONOMIA, es_propio=False)

    assert alquilado == ECONOMIA["costes"]["hora_avion"]["C172"]
    assert "C172" not in ECONOMIA["compra_aviones"]["precio"]
