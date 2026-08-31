"""Tests de la generación de enlaces de presentación de plan de vuelo.

El contrato que se fija aquí: el enlace lleva lo que el piloto puso, no lo
que EvA supone. Un campo vacío se omite; nunca se rellena a ojo.
"""
import base64
import json
from datetime import time
from urllib.parse import parse_qs, urlparse

import pytest

from avcars.prefile import (
    IVAO_PREFILE_URL,
    PrefileExtras,
    icao_fpl,
    ivao_flight_plan,
    ivao_prefile_url,
    prefile_url,
    vatsim_prefile_url,
)
from avcars.schema import FlightPlanInfo, PilotInfo

PILOTO = PilotInfo(license_id="123456", callsign="EVA101")


def _plan(**kwargs) -> FlightPlanInfo:
    base = dict(
        rules="VFR",
        departure_icao="LEVC",
        arrival_icao="LEAL",
        network="IVAO",
        atc_controlled=False,
        aircraft_icao_type="C172",
    )
    base.update(kwargs)
    return FlightPlanInfo(**base)


def _decodifica(url: str) -> dict:
    """Saca el plan del parámetro base64 de una URL de IVAO."""
    crudo = parse_qs(urlparse(url).query)["flightPlan"][0]
    return json.loads(base64.b64decode(crudo))


# --- IVAO ---------------------------------------------------------------


def test_ivao_devuelve_un_plan_decodificable():
    url = ivao_prefile_url(_plan(), PILOTO)
    assert url.startswith(IVAO_PREFILE_URL + "?")

    plan = _decodifica(url)
    assert plan["callsign"] == "EVA101"
    assert plan["departureId"] == "LEVC"
    assert plan["arrivalId"] == "LEAL"
    assert plan["aircraftId"] == "C172"


def test_en_vfr_el_nivel_va_como_tipo_vfr_y_sin_altitud():
    """Mandar una altitud numérica con tipo VFR es contradictorio."""
    plan = ivao_flight_plan(_plan(rules="VFR", planned_cruise_alt_ft=4500), PILOTO)
    assert plan["altitudeType"] == "VFR"
    assert "altitude" not in plan


def test_en_ifr_la_altitud_va_en_niveles_de_vuelo():
    plan = ivao_flight_plan(
        _plan(rules="IFR", planned_cruise_alt_ft=34000), PILOTO
    )
    assert plan["altitudeType"] == "F"
    assert plan["altitude"] == 340


def test_las_reglas_de_vuelo_se_traducen_a_la_letra_de_ivao():
    assert ivao_flight_plan(_plan(rules="VFR"), PILOTO)["flightRules"] == "V"
    assert ivao_flight_plan(_plan(rules="IFR"), PILOTO)["flightRules"] == "I"


def test_las_horas_y_duraciones_van_en_segundos():
    extras = PrefileExtras(
        departure_utc=time(13, 25), eet_minutes=145, endurance_minutes=300
    )
    plan = ivao_flight_plan(_plan(), PILOTO, extras)

    assert plan["departureTime"] == 13 * 3600 + 25 * 60
    assert plan["eet"] == 145 * 60
    assert plan["endurance"] == 300 * 60


def test_los_campos_vacios_no_se_mandan():
    """Mandar vacío puede pisar un valor que el formulario habría deducido."""
    plan = ivao_flight_plan(_plan(), PILOTO)
    for ausente in ("alternativeId", "route", "remarks", "pob", "cruisingSpeed"):
        assert ausente not in plan


def test_no_se_manda_tipo_de_velocidad_sin_velocidad():
    """El tipo sin el valor no dice nada y ensucia el formulario."""
    plan = ivao_flight_plan(_plan(), PILOTO, PrefileExtras())
    assert "cruisingSpeedType" not in plan

    con = ivao_flight_plan(_plan(), PILOTO, PrefileExtras(cruise_speed=110))
    assert con["cruisingSpeedType"] == "N"
    assert con["cruisingSpeed"] == 110


def test_los_pasajeros_del_manifiesto_llegan_al_plan():
    plan = ivao_flight_plan(_plan(), PILOTO, PrefileExtras(persons_on_board=2))
    assert plan["pob"] == 2


def test_un_plan_a_medias_sigue_generando_enlace():
    """IVAO admite planes parciales: mejor abrir el formulario a medias que nada."""
    minimo = FlightPlanInfo(
        rules="VFR", departure_icao="LEVC", arrival_icao="LEAL",
        network="IVAO", atc_controlled=False,
    )
    plan = _decodifica(ivao_prefile_url(minimo, PILOTO))
    assert plan["departureId"] == "LEVC"
    assert "aircraftId" not in plan


# --- VATSIM -------------------------------------------------------------


def test_vatsim_usa_el_parametro_raw_con_el_fpl_en_una_linea():
    """Es el único formato verificado contra el formulario real (el de
    eva-dispatcher). Los parámetros sueltos no están documentados."""
    url = vatsim_prefile_url(
        _plan(network="VATSIM", route="DCT BICORP"), PILOTO,
        PrefileExtras(departure_utc=time(10, 0), cruise_speed=93),
    )
    q = parse_qs(urlparse(url).query)

    raw = q["raw"][0]
    assert raw.startswith("(FPL-EVA101-VG")
    assert "\n" not in raw, "el formulario espera el plan en una sola línea"
    assert "-LEVC1000" in raw
    assert "DCT BICORP" in raw


def test_vatsim_manda_fuel_time_si_hay_autonomia():
    url = vatsim_prefile_url(
        _plan(network="VATSIM"), PILOTO, PrefileExtras(endurance_minutes=96)
    )
    q = parse_qs(urlparse(url).query)
    assert q["fuel_time"] == ["0136"]

    sin = vatsim_prefile_url(_plan(network="VATSIM"), PILOTO)
    assert "fuel_time" not in parse_qs(urlparse(sin).query)


# --- Formato ICAO (botón «Import ICAO FPL» de VATSIM) -------------------


def test_el_plan_icao_tiene_la_estructura_de_casillas():
    extras = PrefileExtras(
        departure_utc=time(10, 30), cruise_speed=110, eet_minutes=55,
        endurance_minutes=240, persons_on_board=2,
    )
    texto = icao_fpl(
        _plan(network="VATSIM", route="DCT XERTA DCT", alternate_icao="LERI"),
        PILOTO, extras,
    )
    lineas = texto.splitlines()

    assert lineas[0] == "(FPL-EVA101-VG"      # casilla 7
    assert lineas[1] == "-C172/L-S/C"         # casillas 9 y 10
    assert lineas[2] == "-LEVC1030"           # casilla 13
    assert lineas[3] == "-N0110VFR DCT XERTA DCT"   # casilla 15
    assert lineas[4] == "-LEAL0055 LERI"      # casilla 16
    assert lineas[-1] == "-E/0400 P/2"        # casilla 19


def test_en_vfr_con_altitud_conocida_la_casilla_15_lleva_el_nivel():
    """El convenio ICAO real admite «VFR» literal aquí, pero el formulario
    beta de VATSIM lo rechaza (Error parsing line 4) y exige un nivel
    numérico aunque el vuelo sea VFR — la regla V/I ya va en la casilla 7."""
    texto = icao_fpl(
        _plan(rules="VFR", planned_cruise_alt_ft=4500), PILOTO,
        PrefileExtras(cruise_speed=110),
    )
    assert "N0110F045" in texto


def test_en_vfr_sin_altitud_la_casilla_15_lleva_vfr():
    texto = icao_fpl(
        _plan(rules="VFR", planned_cruise_alt_ft=None), PILOTO,
        PrefileExtras(cruise_speed=110),
    )
    assert "N0110VFR" in texto


def test_en_ifr_la_casilla_15_lleva_el_nivel_de_vuelo():
    texto = icao_fpl(
        _plan(rules="IFR", planned_cruise_alt_ft=8000), PILOTO,
        PrefileExtras(cruise_speed=110),
    )
    assert "N0110F080" in texto


def test_la_velocidad_va_a_cuatro_cifras():
    """N0110, no N110: el formato exige cuatro dígitos."""
    texto = icao_fpl(_plan(), PILOTO, PrefileExtras(cruise_speed=95))
    assert "N0095" in texto


def test_las_duraciones_van_en_hhmm():
    texto = icao_fpl(
        _plan(), PILOTO, PrefileExtras(eet_minutes=145, endurance_minutes=305)
    )
    assert "0225" in texto      # 2 h 25 min de ruta
    assert "-E/0505" in texto   # 5 h 05 min de autonomía


def test_los_dos_alternativos_caben_en_la_casilla_16():
    texto = icao_fpl(
        _plan(alternate_icao="LERI"), PILOTO,
        PrefileExtras(second_alternate_icao="LEAM"),
    )
    assert "LERI LEAM" in texto


def test_el_plan_icao_cierra_el_parentesis():
    """Sin el paréntesis de cierre, el importador no lo reconoce."""
    texto = icao_fpl(_plan(), PILOTO)
    assert ")" in texto
    assert texto.startswith("(FPL-")


def test_la_fecha_va_como_dof_en_la_casilla_18():
    from datetime import date
    texto = icao_fpl(_plan(), PILOTO, PrefileExtras(flight_date=date(2026, 8, 16)))
    assert "DOF/260816" in texto


def test_la_capacidad_de_voz_va_como_com_en_la_casilla_18():
    texto = icao_fpl(_plan(), PILOTO, PrefileExtras(voice_capability="V"))
    assert "COM/V" in texto


def test_dof_com_y_remarks_conviven_en_la_misma_casilla():
    from datetime import date
    texto = icao_fpl(
        _plan(), PILOTO,
        PrefileExtras(flight_date=date(2026, 8, 16), voice_capability="T", remarks="PBN/A1"),
    )
    linea = [l for l in texto.splitlines() if l.startswith("-DOF") or "DOF/" in l][0]
    assert "DOF/260816" in linea and "COM/T" in linea and "PBN/A1" in linea
    assert linea.endswith(")")


def test_observaciones_sin_etiqueta_se_marcan_como_rmk():
    """Reportado en vivo 2026-08-31: texto libre en "Observaciones" se veía
    en VATSIM dentro de COM/, porque sin una palabra clave propia (RMK/,
    PBN/, ...) que lo delimite, se pega al dato anterior. Debe quedar
    marcado como RMK/ para que aparezca en su propio campo."""
    texto = icao_fpl(
        _plan(), PILOTO,
        PrefileExtras(voice_capability="V", remarks="vuelo de entrenamiento, sin incidencias"),
    )
    linea = [l for l in texto.splitlines() if "COM/" in l][0]
    assert "COM/V RMK/vuelo de entrenamiento, sin incidencias" in linea


def test_observaciones_ya_etiquetadas_no_se_tocan():
    """Si el piloto ya puso RMK/ (o PBN/, etc.) él mismo, no se duplica."""
    texto = icao_fpl(_plan(), PILOTO, PrefileExtras(remarks="RMK/ver NOTAM"))
    assert "RMK/RMK/" not in texto
    assert "RMK/ver NOTAM" in texto


def test_la_estela_sale_del_perfil_de_aeronave_si_se_pasa():
    texto = icao_fpl(_plan(), PILOTO, PrefileExtras(wake_turbulence="M"))
    assert "-C172/M-" in texto


# --- Selección de red ---------------------------------------------------


def test_se_elige_la_red_segun_el_plan():
    assert prefile_url(_plan(network="IVAO"), PILOTO).startswith(IVAO_PREFILE_URL)
    assert "vatsim" in prefile_url(_plan(network="VATSIM"), PILOTO)


def test_un_vuelo_offline_no_genera_enlace_a_ninguna_parte():
    """Mejor un error claro que una URL que no lleva a nada."""
    with pytest.raises(ValueError, match="OFFLINE"):
        prefile_url(_plan(network="OFFLINE"), PILOTO)


def test_la_ruta_con_espacios_viaja_intacta():
    """Una ruta real lleva espacios y barras; deben sobrevivir al codificado."""
    ruta = "DCT DKR N872 SVD/N0446F360 DCT"
    plan = _decodifica(ivao_prefile_url(_plan(route=ruta), PILOTO))
    assert plan["route"] == ruta
