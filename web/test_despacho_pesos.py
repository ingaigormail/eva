"""Peso de despacho D2: combustible del plan, luego pasajeros y carga."""
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

sys.path.insert(0, str(WEB_DIR.parent / "client"))

from avcars.config import load_aircraft  # noqa: E402
from despacho_pesos import (  # noqa: E402
    PESO_PERSONA_KG,
    combustible_kg,
    clasificar_peso,
    datos_para_plantilla,
    minutos_de_combustible,
    mtow_kg,
)

#: Los datos de la flota salen de aircraft.yaml, que es el unico sitio donde
#: viven. Antes estos tests usaban la tabla ESTIMACION del modulo, que era
#: una segunda copia: si se desincronizaba del yaml, los tests seguian en
#: verde contra la copia equivocada. Ahora prueban lo que se usa de verdad.
FLOTA = datos_para_plantilla(load_aircraft())
C172 = FLOTA["C172"]
MTOW_C172 = C172["mtow_kg"]


def test_c172_vacio_en_lem_d_leib_no_es_sobrepeso():
    """LEMD–LEIB ~247 NM a 93 kt: el 172 vacío no puede salir en rojo."""
    eet_min = round((247 / 93) * 60)
    minutos = minutos_de_combustible(eet_min, None)
    c172 = C172
    fuel = combustible_kg(
        minutos, c172["consumo_kg_h"], c172["combustible_util_kg"]
    )
    tow = c172["oew_kg"] + PESO_PERSONA_KG + fuel
    assert clasificar_peso(tow, MTOW_C172) == "ok"
    assert fuel < 1100
    assert tow < MTOW_C172


def test_c172_lleno_de_pasajeros_si_puede_sobrepeso():
    c172 = C172
    eet_min = round((247 / 93) * 60)
    minutos = minutos_de_combustible(eet_min, None)
    fuel = combustible_kg(
        minutos, c172["consumo_kg_h"], c172["combustible_util_kg"]
    )
    # 1 piloto + 4 pasajeros (más plazas de las que hay) + combustible
    tow = c172["oew_kg"] + PESO_PERSONA_KG + 4 * PESO_PERSONA_KG + fuel
    assert clasificar_peso(tow, MTOW_C172) == "sobrepeso"


def test_autonomia_manda_sobre_el_eet():
    assert minutos_de_combustible(60, 180) == 180
    assert minutos_de_combustible(60, None) == 90
    assert minutos_de_combustible(None, None) is None


def test_justo_cuando_el_margen_es_minimo():
    assert clasificar_peso(1040, 1050) == "justo"
    assert clasificar_peso(1050, 1050) == "justo"
    assert clasificar_peso(1051, 1050) == "sobrepeso"
    assert clasificar_peso(900, 1050) == "ok"


def test_la_ficha_sale_entera_del_bloque_despacho():
    """Todo viene del yaml: aquí no se completa nada desde ninguna tabla.

    Antes esta prueba daba un avión con solo el MTOW y esperaba que el resto
    (peso en vacío, combustible…) lo rellenara la tabla `ESTIMACION` del
    módulo. Esa tabla era una segunda copia de los datos de la flota y ya no
    existe: `aircraft.yaml` es el único sitio.
    """
    flota = {
        "XXXX": {
            "despacho": {
                "mtow_kg": 2000,
                "vacio_kg": 1200,
                "combustible_util_kg": 300,
                "consumo_kg_h": 50,
                "plazas": 4,
                "verificado": True,
            }
        }
    }
    datos = datos_para_plantilla(flota)

    assert datos["XXXX"]["mtow_kg"] == 2000
    assert datos["XXXX"]["oew_kg"] == 1200   # `vacio_kg` en el yaml
    assert datos["XXXX"]["verificado"] is True


def test_un_avion_con_la_ficha_a_medias_se_queda_fuera():
    """Peor un peso equivocado que ninguno: si falta un sumando, no hay total."""
    flota = {
        "SOLO_MTOW": {"despacho": {"mtow_kg": 2000}},
        "SIN_NADA": {"referencia_atc": {"disponible": False}},
        "SIN_CONSUMO": {
            "despacho": {
                "mtow_kg": 2000,
                "vacio_kg": 1200,
                "combustible_util_kg": 300,
                "plazas": 4,
            }
        },
    }

    assert datos_para_plantilla(flota) == {}


def test_el_mtow_del_simulador_manda_sobre_el_de_eurocontrol():
    """No es un conflicto que arreglar: son aviones distintos.

    EUROCONTROL da 1050 kg para el C172 (un 172N/P) y el simulador modela un
    172S de 1160 kg. Para juzgar un vuelo manda el que se vuela.
    """
    ficha = {
        "despacho": {"mtow_kg": 1160},
        "referencia_atc": {"mtow_kg": 1050},
    }
    assert mtow_kg(ficha) == 1160


def test_mtow_tbm_sale_de_referencia_sim():
    assert mtow_kg({"referencia_sim": {"mtow_kg": 3354}}) == 3354


# -- que ningun avion de la flota se quede sin calculo ------------------

def test_todos_los_aviones_de_la_flota_calculan_su_peso():
    """El fallo del 2026-08-28, y la red para que no vuelva.

    Un avión que está en el desplegable de `/plan` pero no en `DESPACHO`
    deja la tabla de pesos entera en "—": el piloto toca pasajeros y carga y
    no cambia nada, sin ninguna explicación de por qué. Pasó con dos de los
    ocho aviones a la vez y por motivos distintos:

    - el TBM 930 tenía su MTOW en el bloque `pesos` del yaml, donde
      `mtow_kg()` no miraba;
    - el DA62 no tenía MTOW en ninguna parte del yaml.

    Esta prueba no comprueba un avión concreto: recorre la flota real. Si
    mañana se añade uno y se olvida su ficha de despacho, falla aquí en vez
    de descubrirse volando.
    """
    sys.path.insert(0, str(WEB_DIR.parent / "client"))
    from avcars.config import load_aircraft

    flota = load_aircraft()
    datos = datos_para_plantilla(flota)

    sin_datos = sorted(set(flota) - set(datos))
    assert not sin_datos, (
        "estos aviones se pueden elegir en /plan pero no calculan peso: "
        f"{sin_datos}. Falta o esta incompleto su bloque `despacho` en aircraft.yaml."
    )


def test_el_mtow_tambien_se_busca_en_el_bloque_pesos():
    """El TBM 930 lo tiene ahí, con las cifras del manual."""
    assert mtow_kg({"pesos": {"mtow_kg": 3354}}) == 3354


def test_el_bloque_pesos_manda_sobre_la_referencia_para_atc():
    """Son datos de manual: pesan más que una ficha de referencia."""
    ficha = {"pesos": {"mtow_kg": 3354}, "referencia_atc": {"mtow_kg": 9999}}
    assert mtow_kg(ficha) == 3354


def test_sin_mtow_en_ningun_sitio_no_hay_ficha():
    """Mejor sin ficha que con un MTOW inventado: el semáforo avisaría mal."""
    assert mtow_kg({"referencia_atc": {"disponible": False}}) is None
