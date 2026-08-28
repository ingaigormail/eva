"""Tests de la detección de invasión de zona.

Lo que se comprueba sobre todo es lo que **no** debe acusar: rozar una
esquina, pasar por encima, cruzar un instante, o una zona cuya referencia
vertical no se entiende. Una acusación falsa destruye la confianza en el
sistema entero mucho más de lo que la falta de la regla la construye.
"""
from dataclasses import dataclass
from typing import Optional

from avcars.evaluation import espacio_aereo as ea


@dataclass
class Punto:
    """Lo mínimo que mira el módulo de un TrackPoint."""

    t: float
    lat: float
    lon: float
    alt_msl_ft: float
    alt_agl_ft: Optional[float] = 1000.0


def zona(
    suelo=0.0,
    techo=5000.0,
    referencia="msl",
    lat0=40.0,
    lon0=-3.0,
    lado=1.0,
) -> ea.Zona:
    """Un cuadrado de `lado` grados con la esquina inferior en (lat0, lon0)."""
    anillo = (
        (lon0, lat0),
        (lon0 + lado, lat0),
        (lon0 + lado, lat0 + lado),
        (lon0, lat0 + lado),
        (lon0, lat0),
    )
    poligonos = ((anillo,),)
    return ea.Zona(
        ident="LED123",
        nombre="ZONA DE PRUEBA",
        capa="D_P_R",
        poligonos=poligonos,
        caja=ea._caja(poligonos),
        suelo_ft=suelo,
        techo_ft=techo,
        referencia=referencia,
    )


def travesia(n=10, lat=40.5, lon=-2.5, alt=2000.0, paso=10.0):
    """`n` puntos quietos en el mismo sitio, separados `paso` segundos."""
    return [Punto(t=i * paso, lat=lat, lon=lon, alt_msl_ft=alt) for i in range(n)]


# -- geometría ---------------------------------------------------------

def test_el_centro_esta_dentro():
    assert ea.dentro_lateralmente(40.5, -2.5, zona())


def test_fuera_es_fuera():
    assert not ea.dentro_lateralmente(45.0, -2.5, zona())


def test_la_caja_descarta_sin_mirar_vertices():
    z = zona()
    assert not ea.dentro_lateralmente(0.0, 0.0, z)


def test_un_hueco_no_cuenta_como_dentro():
    contorno = ((-3.0, 40.0), (-2.0, 40.0), (-2.0, 41.0), (-3.0, 41.0), (-3.0, 40.0))
    hueco = ((-2.6, 40.4), (-2.4, 40.4), (-2.4, 40.6), (-2.6, 40.6), (-2.6, 40.4))
    poligonos = ((contorno, hueco),)
    z = ea.Zona("X", "X", "D_P_R", poligonos, ea._caja(poligonos), 0.0, 5000.0, "msl")

    assert ea.dentro_lateralmente(40.1, -2.9, z)   # dentro del contorno
    assert not ea.dentro_lateralmente(40.5, -2.5, z)  # dentro del hueco


def test_la_distancia_al_borde_crece_hacia_el_centro():
    z = zona()
    en_el_borde = ea.distancia_al_borde_nm(40.001, -2.999, z)
    en_el_centro = ea.distancia_al_borde_nm(40.5, -2.5, z)
    assert en_el_borde < 1.0
    assert en_el_centro > 20.0


# -- límites verticales ------------------------------------------------

def test_por_encima_del_techo_no_esta_dentro():
    assert ea.dentro_verticalmente(9000.0, 1000.0, zona(techo=5000.0)) is False


def test_por_debajo_del_suelo_no_esta_dentro():
    assert ea.dentro_verticalmente(500.0, 400.0, zona(suelo=3000.0)) is False


def test_entre_suelo_y_techo_esta_dentro():
    assert ea.dentro_verticalmente(4000.0, 3000.0, zona()) is True


def test_una_zona_en_agl_se_compara_con_la_altura_sobre_el_terreno():
    z = zona(suelo=0.0, techo=1000.0, referencia="agl")
    # A 8.000 ft sobre el mar pero 500 sobre el terreno: dentro.
    assert ea.dentro_verticalmente(8000.0, 500.0, z) is True
    assert ea.dentro_verticalmente(8000.0, 3000.0, z) is False


def test_sin_referencia_no_se_puede_afirmar_nada():
    assert ea.dentro_verticalmente(3000.0, 1000.0, zona(referencia=None)) is None


def test_una_zona_en_agl_sin_dato_de_terreno_no_se_juzga():
    z = zona(referencia="agl")
    assert ea.dentro_verticalmente(3000.0, None, z) is None


# -- detección ---------------------------------------------------------

def test_una_travesia_larga_se_detecta():
    inv = ea.invasiones(travesia(), [zona()])

    assert len(inv) == 1
    assert inv[0].zona.ident == "LED123"
    assert inv[0].duracion_s == 90.0
    assert inv[0].muestras == 10


def test_pasar_por_encima_no_es_invasion():
    alto = travesia(alt=12000.0)
    assert ea.invasiones(alto, [zona(techo=5000.0)]) == []


def test_un_roce_corto_no_es_invasion():
    """Dos muestras seguidas a 1 s no llegan a la permanencia mínima."""
    corto = [
        Punto(t=0.0, lat=40.5, lon=-2.5, alt_msl_ft=2000.0),
        Punto(t=1.0, lat=40.5, lon=-2.5, alt_msl_ft=2000.0),
    ]
    assert ea.invasiones(corto, [zona()]) == []


def test_un_solo_punto_nunca_acusa():
    """Aunque el siguiente esté a 10 minutos y la permanencia salga enorme.

    Con una sola muestra no se sabe si entró y salió o si se quedó dentro.
    """
    uno = [
        Punto(t=0.0, lat=40.5, lon=-2.5, alt_msl_ft=2000.0),
        Punto(t=600.0, lat=50.0, lon=-2.5, alt_msl_ft=2000.0),
    ]
    assert ea.invasiones(uno, [zona()]) == []


def test_rozar_el_borde_no_es_invasion():
    """Dentro del polígono pero a menos del margen: no cuenta."""
    z = zona()
    borde = [
        Punto(t=i * 10.0, lat=40.0001, lon=-2.5, alt_msl_ft=2000.0)
        for i in range(10)
    ]
    assert ea.dentro_lateralmente(40.0001, -2.5, z)  # sí está dentro
    assert ea.invasiones(borde, [z], margen_nm=0.5) == []


def test_una_zona_sin_referencia_vertical_no_acusa():
    assert ea.invasiones(travesia(), [zona(referencia=None)]) == []


def test_entrar_salir_y_volver_son_dos_invasiones():
    dentro_1 = [Punto(t=i * 10.0, lat=40.5, lon=-2.5, alt_msl_ft=2000.0) for i in range(5)]
    fuera = [Punto(t=50.0 + i * 10.0, lat=45.0, lon=-2.5, alt_msl_ft=2000.0) for i in range(3)]
    dentro_2 = [Punto(t=80.0 + i * 10.0, lat=40.5, lon=-2.5, alt_msl_ft=2000.0) for i in range(5)]

    inv = ea.invasiones(dentro_1 + fuera + dentro_2, [zona()])

    assert len(inv) == 2
    assert inv[0].t_entrada == 0.0
    assert inv[1].t_entrada == 80.0


def test_se_informa_de_lo_mas_adentro_que_llego():
    recorrido = [
        Punto(t=0.0, lat=40.05, lon=-2.95, alt_msl_ft=2000.0),
        Punto(t=10.0, lat=40.3, lon=-2.7, alt_msl_ft=2000.0),
        Punto(t=20.0, lat=40.5, lon=-2.5, alt_msl_ft=2500.0),
        Punto(t=30.0, lat=40.3, lon=-2.7, alt_msl_ft=2000.0),
    ]
    inv = ea.invasiones(recorrido, [zona()])

    assert len(inv) == 1
    # El punto más profundo es el centro, y con él va su altitud.
    assert inv[0].altitud_ft == 2500.0
    assert inv[0].profundidad_nm > 20.0


def test_sin_zonas_no_hay_nada_que_detectar():
    assert ea.invasiones(travesia(), []) == []


# -- carga -------------------------------------------------------------

def test_sin_base_de_datos_devuelve_lista_vacia(tmp_path):
    """Que falte el fichero deja la regla sin evaluar, no tumba el motor."""
    assert ea.cargar_zonas(tmp_path / "no-existe.db") == []


def test_referencias_verticales_reconocidas():
    assert ea._referencia("HEIS") == "msl"
    assert ea._referencia("ALT") == "msl"
    assert ea._referencia("STD") == "msl"
    assert ea._referencia("HEIG") == "agl"
    assert ea._referencia("HEI") == "agl"
    # HEISG mezcla las dos y OTHER no dice nada: sin referencia no se juzga.
    assert ea._referencia("HEISG") is None
    assert ea._referencia("OTHER") is None
    assert ea._referencia(None) is None


def test_multipolygon_se_normaliza():
    geo = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[-3.0, 40.0], [-2.0, 40.0], [-2.0, 41.0], [-3.0, 40.0]]],
            [[[0.0, 45.0], [1.0, 45.0], [1.0, 46.0], [0.0, 45.0]]],
        ],
    }
    assert len(ea._anillos(geo)) == 2


def test_geometria_desconocida_no_produce_zona():
    assert ea._anillos({"type": "Point", "coordinates": [0, 0]}) == ()


# -- integración con el motor de evaluación ---------------------------

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from avcars.config import load_profiles  # noqa: E402
from avcars.evaluation.scoring import evaluate_flight  # noqa: E402
from avcars.schema import FlightLog  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
PERFIL = load_profiles()["normal"]


def _vuelo_de_prueba() -> FlightLog:
    datos = json.loads(
        (FIXTURES / "sample_flight_pass.json").read_text(encoding="utf-8")
    )
    return FlightLog.model_validate(datos)


def _zona_sobre(vuelo: FlightLog) -> ea.Zona:
    """Una zona centrada justo donde vuela el avión de la fixture."""
    p = vuelo.track[len(vuelo.track) // 2]
    return zona(lat0=p.lat - 0.5, lon0=p.lon - 0.5, lado=1.0, techo=99999.0)


def test_sin_zonas_la_regla_queda_sin_evaluar():
    """Es el caso del cliente: tiene el motor pero no la base de ENAIRE."""
    veredicto = evaluate_flight(_vuelo_de_prueba(), PERFIL)

    assert "airspace_zones" in veredicto.not_evaluated


def test_con_zonas_y_sin_invasion_la_regla_pasa():
    vuelo = _vuelo_de_prueba()
    lejos = zona(lat0=10.0, lon0=10.0)

    veredicto = evaluate_flight(vuelo, PERFIL, zonas=[lejos])

    assert "airspace_zones" not in veredicto.not_evaluated
    item = next(i for i in veredicto.items if i.rule == "airspace_zones")
    assert item.passed
    assert item.points == 0


def test_una_invasion_resta_puntos_y_se_situa_en_el_mapa():
    vuelo = _vuelo_de_prueba()
    limpio = evaluate_flight(vuelo, PERFIL, zonas=[])

    veredicto = evaluate_flight(vuelo, PERFIL, zonas=[_zona_sobre(vuelo)])
    item = next(i for i in veredicto.items if i.rule == "airspace_zones")

    assert not item.passed
    assert item.points == PERFIL["penalties"]["airspace_intrusion"]
    assert veredicto.score == limpio.score - item.points
    # Sin sitio en el mapa la incidencia solo se puede listar, no revisar.
    assert item.lat is not None and item.utc is not None


def test_una_invasion_no_suspende_el_vuelo_por_si_sola():
    """Penaliza, no es fallo duro.

    La traza en crucero guarda un punto cada 10 s: esto detecta travesías,
    no roces, así que de momento no puede invalidar un vuelo. Cuando lleve
    meses sin falsos positivos, subirlo a fallo duro es cambiar una línea.
    """
    vuelo = _vuelo_de_prueba()

    veredicto = evaluate_flight(vuelo, PERFIL, zonas=[_zona_sobre(vuelo)])

    assert "airspace_intrusion" not in veredicto.failed_hard


def test_la_penalizacion_tiene_tope():
    """Diez zonas invadidas no pueden dejar el vuelo a cero por sí solas."""
    vuelo = _vuelo_de_prueba()
    muchas = [_zona_sobre(vuelo) for _ in range(10)]

    veredicto = evaluate_flight(vuelo, PERFIL, zonas=muchas)
    item = next(i for i in veredicto.items if i.rule == "airspace_zones")

    assert item.points == PERFIL["airspace"]["penalizacion_maxima"]
