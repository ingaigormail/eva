"""La economía se lee de `economia.yaml` y se puede pisar en vivo.

Mismo trato que los umbrales de puntuación: la base va versionada en git y
las diferencias se guardan aparte, para no acabar con un fichero del
repositorio editado a mano en producción.
"""
import pytest

from avcars.config import load_economia
from avcars.evaluation import reglas_config


@pytest.fixture
def config_tmp(tmp_path):
    return tmp_path / "reglas_config.json"


def test_el_fichero_se_lee_y_trae_lo_esperado():
    e = load_economia()

    assert e["ingresos"]["tarifa_pasajero_nm"] == 2.0
    assert e["ingresos"]["tarifa_kg_nm"] == 0.01
    assert e["calidad"]["apto"] == 1.0
    assert e["progresion"]["vuelos_para_examen"]["P0_a_P1"] == 10


def test_los_ocho_aviones_tienen_hora_y_dano():
    """Un avión sin tarifa horaria no se puede cobrar, y se descubriría volando."""
    e = load_economia()
    flota = set(e["costes"]["hora_avion"])

    assert flota == set(e["dano"]["inspeccion_toma_dura"])
    assert flota == set(e["dano"]["euros_por_fpm"])
    assert len(flota) == 8


def test_se_venden_todos_los_aviones_menos_el_c172():
    """El C172 es el de entrada y va siempre alquilado; el resto se compran."""
    e = load_economia()
    precios = set(e["compra_aviones"]["precio"])

    assert precios == set(e["costes"]["hora_avion"]) - {"C172"}


def test_sin_overrides_la_economia_es_la_del_fichero():
    base = load_economia()

    assert reglas_config.economia_efectiva(base, {}) == base


def test_un_override_pisa_solo_su_valor(config_tmp):
    base = load_economia()
    reglas_config.guardar_valor_economia("calidad.no_apto", 0.5, config_tmp)

    efectiva = reglas_config.economia_efectiva(
        base, reglas_config.cargar_overrides(config_tmp)
    )

    assert efectiva["calidad"]["no_apto"] == 0.5
    assert efectiva["calidad"]["apto"] == base["calidad"]["apto"]


def test_se_puede_pisar_la_hora_de_un_solo_avion(config_tmp):
    base = load_economia()
    reglas_config.guardar_valor_economia("costes.hora_avion.C172", 150, config_tmp)

    efectiva = reglas_config.economia_efectiva(
        base, reglas_config.cargar_overrides(config_tmp)
    )

    assert efectiva["costes"]["hora_avion"]["C172"] == 150
    assert efectiva["costes"]["hora_avion"]["C208"] == base["costes"]["hora_avion"]["C208"]


def test_quitar_el_override_devuelve_el_valor_del_fichero(config_tmp):
    base = load_economia()
    reglas_config.guardar_valor_economia("calidad.no_apto", 0.9, config_tmp)
    reglas_config.quitar_valor_economia("calidad.no_apto", config_tmp)

    efectiva = reglas_config.economia_efectiva(
        base, reglas_config.cargar_overrides(config_tmp)
    )

    assert efectiva["calidad"]["no_apto"] == base["calidad"]["no_apto"]


def test_la_economia_no_pisa_los_umbrales_de_puntuacion(config_tmp):
    """Conviven en el mismo fichero: el prefijo `economia.` los separa.

    Sin él, un `calidad.no_apto` de la economía y un umbral de puntuación con
    el mismo nombre se machacarían el día que a alguien se le ocurriera.
    """
    reglas_config.guardar_valor_economia("bank_angle.fail_deg", 99, config_tmp)
    overrides = reglas_config.cargar_overrides(config_tmp)

    perfil = reglas_config.perfil_efectivo({"bank_angle": {"fail_deg": 60}}, overrides)

    assert perfil["bank_angle"]["fail_deg"] == 60


def test_no_muta_la_base(config_tmp):
    """`load_economia()` puede cargarse una vez y reutilizarse en cada petición."""
    base = load_economia()
    reglas_config.guardar_valor_economia("calidad.no_apto", 0.7, config_tmp)

    reglas_config.economia_efectiva(base, reglas_config.cargar_overrides(config_tmp))

    assert base["calidad"]["no_apto"] == load_economia()["calidad"]["no_apto"]
