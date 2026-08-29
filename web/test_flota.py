"""Cada piloto solo puede elegir los aviones de su categoría.

Filtrar en vez de rechazar: el piloto ve lo suyo en lugar de elegir un avión
y recibir un error después.
"""
import sys
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))
sys.path.insert(0, str(WEB_DIR.parent / "client"))

import flota as flota_eva  # noqa: E402
from avcars.config import load_aircraft, load_economia  # noqa: E402

FLOTA = load_aircraft()
ECONOMIA = load_economia()


def _icaos(categoria):
    return [a["icao"] for a in flota_eva.aviones_de(categoria, FLOTA)]


# -- filtrado por categoría --------------------------------------------

def test_un_p0_solo_ve_el_c172():
    """Es correcto que sea uno solo: es el único avión de su categoría."""
    assert _icaos("P0") == ["C172"]


def test_un_p1_ve_el_suyo_y_lo_de_abajo():
    """La escalera es acumulativa: subir no te quita el avión anterior."""
    icaos = _icaos("P1")

    assert "C172" in icaos
    assert {"DA62", "BE58", "C208"} <= set(icaos)
    assert "C25C" not in icaos


def test_sin_categoria_no_se_ofrece_ningun_avion():
    """Prudencia: mejor no ofrecer nada que ofrecer un reactor por un dato
    que falta o viene corrupto."""
    assert _icaos("") == []
    assert _icaos("categoria-inventada") == []


def test_todos_los_aviones_de_la_flota_tienen_matricula_y_categoria():
    """Uno sin declarar no se le ofrece a nadie y desaparecería en silencio."""
    sin_declarar = [
        icao for icao, f in FLOTA.items()
        if not (f.get("flota") or {}).get("matricula")
        or not (f.get("flota") or {}).get("categoria_minima")
    ]

    assert not sin_declarar, f"sin bloque `flota` en aircraft.yaml: {sin_declarar}"


def test_las_matriculas_no_se_repiten():
    matriculas = [
        (f.get("flota") or {}).get("matricula") for f in FLOTA.values()
    ]

    assert len(matriculas) == len(set(matriculas))


def test_un_avion_sin_categoria_declarada_no_se_ofrece():
    inventado = {"XXXX": {"nombre": "Sin declarar", "flota": {"matricula": "EC-XXX"}}}

    assert flota_eva.aviones_de("P4", inventado) == []


# -- salud de la célula ------------------------------------------------

def test_una_celula_a_estrenar_esta_al_cien():
    salud = flota_eva.salud("C172", ECONOMIA)

    assert salud["salud_pct"] == 100
    assert salud["estado"] == "buena"
    assert salud["horas_para_revision"] == 100


def test_la_salud_baja_con_las_horas(monkeypatch):
    """A 0,2 % por hora, la célula llega a la revisión con un 80 %."""
    monkeypatch.setattr(flota_eva, "horas_voladas", lambda _icao: 50.0)

    salud = flota_eva.salud("C172", ECONOMIA)

    assert salud["salud_pct"] == 90
    assert salud["horas_para_revision"] == 50


def test_la_revision_devuelve_la_salud(monkeypatch):
    """Es un diente de sierra: a las 100 h se revisa y vuelve a empezar."""
    monkeypatch.setattr(flota_eva, "horas_voladas", lambda _icao: 100.0)

    assert flota_eva.salud("C172", ECONOMIA)["salud_pct"] == 100


def test_la_salud_nunca_baja_de_cero(monkeypatch):
    """Con un desgaste por hora exagerado, el porcentaje no se va a negativo."""
    monkeypatch.setattr(flota_eva, "horas_voladas", lambda _icao: 99.0)
    economia = {"desgaste": {"horas_entre_revisiones": 100, "por_hora_pct": 5}}

    assert flota_eva.salud("C172", economia)["salud_pct"] == 0


def test_la_ficha_trae_matricula_y_salud():
    ficha = flota_eva.ficha_de("C172", FLOTA, ECONOMIA)

    assert ficha["matricula"] == "EC-EVA"
    assert ficha["salud_pct"] == 100


def test_un_tipo_que_no_existe_no_tiene_ficha():
    assert flota_eva.ficha_de("XXXX", FLOTA, ECONOMIA) is None


# -- controladores del mapa en vivo ------------------------------------

def test_solo_salen_los_controladores_de_la_peninsula_iberica():
    """El feed trae más de cien de todo el mundo; el mapa es de aquí.

    Portugal entra: para volar VFR desde España es la misma zona, y la Vuelta
    a España ya tiene etapas portuguesas.
    """
    import app as app_module

    entrada = [
        {"callsign": "LEBL_TWR", "frequency": "118.325", "name": "Barcelona"},
        {"callsign": "LPPT_TWR", "frequency": "118.100", "name": "Lisboa"},
        {"callsign": "GCLP_APP", "frequency": "120.300", "name": "Las Palmas"},
        {"callsign": "LFPG_TWR", "frequency": "119.250", "name": "París"},
        {"callsign": "KJFK_TWR", "frequency": "119.100", "name": "Nueva York"},
    ]

    salida = {c["callsign"] for c in app_module._controladores_situados(entrada)}

    assert salida == {"LEBL_TWR", "LPPT_TWR", "GCLP_APP"}


def test_los_observadores_no_son_controladores():
    """199.998 es la frecuencia de "no atiendo": no sirve para llamar."""
    import app as app_module

    entrada = [{"callsign": "LEMD_OBS", "frequency": "199.998", "name": "Obs"}]

    assert app_module._controladores_situados(entrada) == []


def test_un_sector_de_ruta_se_pinta_como_region_y_no_como_punto():
    """LECM no es un aeropuerto sino un área: se pinta con su polígono de FIR.

    Antes se descartaba por no encontrarlo en `airports.json`. Desde que hay
    límites de FIR (`web/static/fir_iberia.geojson`) sale como región, sin
    coordenadas: inventarle un punto sería peor que no pintarlo.
    """
    import app as app_module

    c = app_module._controladores_situados(
        [{"callsign": "LECM_CTR", "frequency": "132.400", "name": "Madrid"}]
    )[0]

    assert c["fir"] == "LECM"
    assert c["latitude"] is None and c["longitude"] is None
    assert c["tipo"] == "Control de área"


def test_cada_posicion_dice_de_que_tipo_es():
    """Es lo que el piloto necesita para saber a quién llama."""
    import app as app_module

    entrada = [
        {"callsign": "LEBL_TWR", "frequency": "118.325", "name": "x"},
        {"callsign": "LEMD_APP", "frequency": "119.800", "name": "x"},
        {"callsign": "LEBL_GND", "frequency": "121.650", "name": "x"},
        {"callsign": "LECM_CTR", "frequency": "132.400", "name": "x"},
    ]

    tipos = {c["callsign"]: c["tipo"] for c in app_module._controladores_situados(entrada)}

    assert tipos["LEBL_TWR"] == "Torre"
    assert tipos["LEMD_APP"] == "Aproximación"
    assert tipos["LEBL_GND"] == "Rodadura"
    assert tipos["LECM_CTR"] == "Control de área"


def test_el_tipo_sale_del_ultimo_trozo_del_indicativo():
    """Hay indicativos con parte intermedia: LEMH_A_TWR, EGLL_1_GND."""
    import app as app_module

    c = app_module._controladores_situados(
        [{"callsign": "LEMH_A_TWR", "frequency": "119.655", "name": "x"}]
    )[0]

    assert c["tipo"] == "Torre"


def test_las_torres_van_delante_de_las_areas():
    """Si no, una torre queda tapada por el polígono de su control de área."""
    import app as app_module

    entrada = [
        {"callsign": "LECM_CTR", "frequency": "132.400", "name": "x"},
        {"callsign": "LEBL_TWR", "frequency": "118.325", "name": "x"},
    ]

    orden = [c["callsign"] for c in app_module._controladores_situados(entrada)]

    assert orden == ["LEBL_TWR", "LECM_CTR"]


def test_el_controlador_lleva_lo_que_hace_falta_para_llamarle():
    import app as app_module

    c = app_module._controladores_situados(
        [{"callsign": "LEBL_TWR", "frequency": "118.325", "name": "Ana"}]
    )[0]

    assert c["frequency"] == "118.325"
    assert c["latitude"] is not None and c["longitude"] is not None
    assert "Barcelona" in c["aeropuerto"]
