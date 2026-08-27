"""Tests de la comprobación de aeródromo de salida.

Lo que importa aquí no es tanto que la distancia salga bien — eso es una
fórmula conocida — como que la comprobación **nunca bloquee por un hueco en
los datos**. Un ICAO que no está en la lista, un aeropuerto sin coordenadas o
un simulador que aún no da posición tienen que dejar grabar: son fallos de
datos, no de pilotaje.
"""
import math

from avcars import ubicacion


AEROPUERTOS = {
    "LEMD": {"name": "Adolfo Suarez Madrid-Barajas", "lat": 40.47223, "lon": -3.56094},
    "LETO": {"name": "Madrid-Torrejon", "lat": 40.48681, "lon": -3.45831},
    "LEBL": {"name": "Barcelona", "lat": 41.29706, "lon": 2.07846},
    "SINCOORD": {"name": "Sin coordenadas"},
}


# -- la fórmula -------------------------------------------------------

def test_distancia_entre_el_mismo_punto_es_cero():
    assert ubicacion.distancia_nm(40.0, -3.0, 40.0, -3.0) == 0.0


def test_distancia_madrid_barcelona():
    # ~261 NM en línea recta. Se admite un 1% porque el modelo es esférico.
    d = ubicacion.distancia_nm(40.47223, -3.56094, 41.29706, 2.07846)
    assert math.isclose(d, 261.0, rel_tol=0.01)


def test_distancia_es_simetrica():
    ida = ubicacion.distancia_nm(40.47223, -3.56094, 41.29706, 2.07846)
    vuelta = ubicacion.distancia_nm(41.29706, 2.07846, 40.47223, -3.56094)
    assert math.isclose(ida, vuelta)


# -- el caso que la regla existe para cazar ---------------------------

def test_avion_en_barcelona_con_plan_desde_madrid_no_es_conforme():
    r = ubicacion.comprobar_salida(41.29706, 2.07846, "LEMD", AEROPUERTOS)
    assert not r.conforme
    assert r.comprobada
    assert r.distancia_nm > 250
    assert "LEMD" in r.motivo


def test_avion_en_su_aerodromo_es_conforme():
    r = ubicacion.comprobar_salida(40.47223, -3.56094, "LEMD", AEROPUERTOS)
    assert r.conforme
    assert r.comprobada
    assert r.distancia_nm < 0.1


def test_aerodromos_vecinos_se_distinguen():
    # Barajas y Torrejón están a ~5 NM: dentro de la tolerancia por defecto
    # son el mismo sitio, y con una tolerancia apretada dejan de serlo. Es el
    # motivo de que el umbral sea configurable.
    holgada = ubicacion.comprobar_salida(40.48681, -3.45831, "LEMD", AEROPUERTOS)
    apretada = ubicacion.comprobar_salida(
        40.48681, -3.45831, "LEMD", AEROPUERTOS, tolerancia_nm=2.0
    )
    assert holgada.conforme
    assert not apretada.conforme


def test_la_tolerancia_es_inclusiva():
    # Justo en el borde se considera conforme: la duda beneficia al piloto.
    r = ubicacion.comprobar_salida(40.47223, -3.56094, "LEMD", AEROPUERTOS)
    en_el_borde = ubicacion.comprobar_salida(
        40.47223, -3.56094, "LEMD", AEROPUERTOS, tolerancia_nm=r.distancia_nm
    )
    assert en_el_borde.conforme


# -- lo que nunca debe bloquear ---------------------------------------

def test_sin_origen_en_el_plan_deja_pasar():
    r = ubicacion.comprobar_salida(41.29706, 2.07846, "", AEROPUERTOS)
    assert r.conforme
    assert not r.comprobada


def test_icao_desconocido_deja_pasar():
    r = ubicacion.comprobar_salida(41.29706, 2.07846, "XXXX", AEROPUERTOS)
    assert r.conforme
    assert not r.comprobada
    assert "XXXX" in r.motivo


def test_aeropuerto_sin_coordenadas_deja_pasar():
    r = ubicacion.comprobar_salida(41.29706, 2.07846, "SINCOORD", AEROPUERTOS)
    assert r.conforme
    assert not r.comprobada


def test_sin_posicion_del_simulador_deja_pasar():
    r = ubicacion.comprobar_salida(None, None, "LEMD", AEROPUERTOS)
    assert r.conforme
    assert not r.comprobada


def test_lista_de_aeropuertos_vacia_deja_pasar():
    r = ubicacion.comprobar_salida(41.29706, 2.07846, "LEMD", {})
    assert r.conforme
    assert not r.comprobada


def test_simulador_en_el_menu_se_distingue_de_estar_lejos():
    # Coordenadas 0,0 están a ~2.400 NM de Madrid, pero el mensaje correcto
    # no es "estás lejos" sino "no has cargado el vuelo".
    r = ubicacion.comprobar_salida(0.0, 0.0, "LEMD", AEROPUERTOS)
    assert r.conforme
    assert not r.comprobada
    assert "menú" in r.motivo


# -- entrada sucia ----------------------------------------------------

def test_el_icao_se_normaliza():
    r = ubicacion.comprobar_salida(40.47223, -3.56094, "  lemd ", AEROPUERTOS)
    assert r.conforme
    assert r.comprobada
