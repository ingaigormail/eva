"""Peso de despacho D2: combustible del plan, luego pasajeros y carga."""
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

from despacho_pesos import (  # noqa: E402
    ESTIMACION,
    PESO_PERSONA_KG,
    combustible_kg,
    clasificar_peso,
    datos_para_plantilla,
    minutos_de_combustible,
    mtow_kg,
)


def test_c172_vacio_en_lem_d_leib_no_es_sobrepeso():
    """LEMD–LEIB ~247 NM a 93 kt: el 172 vacío no puede salir en rojo."""
    eet_min = round((247 / 93) * 60)
    minutos = minutos_de_combustible(eet_min, None)
    c172 = ESTIMACION["C172"]
    fuel = combustible_kg(
        minutos, c172["consumo_kg_h"], c172["combustible_util_kg"]
    )
    tow = c172["oew_kg"] + PESO_PERSONA_KG + fuel
    assert clasificar_peso(tow, 1050) == "ok"
    assert fuel < 1100
    assert tow < 1050


def test_c172_lleno_de_pasajeros_si_puede_sobrepeso():
    c172 = ESTIMACION["C172"]
    eet_min = round((247 / 93) * 60)
    minutos = minutos_de_combustible(eet_min, None)
    fuel = combustible_kg(
        minutos, c172["consumo_kg_h"], c172["combustible_util_kg"]
    )
    # 1 piloto + 4 pasajeros (más plazas de las que hay) + combustible
    tow = c172["oew_kg"] + PESO_PERSONA_KG + 4 * PESO_PERSONA_KG + fuel
    assert clasificar_peso(tow, 1050) == "sobrepeso"


def test_autonomia_manda_sobre_el_eet():
    assert minutos_de_combustible(60, 180) == 180
    assert minutos_de_combustible(60, None) == 90
    assert minutos_de_combustible(None, None) is None


def test_justo_cuando_el_margen_es_minimo():
    assert clasificar_peso(1040, 1050) == "justo"
    assert clasificar_peso(1050, 1050) == "justo"
    assert clasificar_peso(1051, 1050) == "sobrepeso"
    assert clasificar_peso(900, 1050) == "ok"


def test_plantilla_incluye_c172_con_mtow_del_yaml():
    flota = {
        "C172": {"referencia_atc": {"mtow_kg": 1050}},
        "DA62": {"referencia_atc": {"disponible": False}},
    }
    datos = datos_para_plantilla(flota)
    assert datos["C172"]["mtow_kg"] == 1050
    assert datos["C172"]["oew_kg"] == 620
    assert "DA62" not in datos


def test_mtow_tbm_sale_de_referencia_sim():
    assert mtow_kg({"referencia_sim": {"mtow_kg": 3354}}) == 3354
