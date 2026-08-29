"""El CID de VATSIM se puede poner y quitar en una cuenta ya creada.

Hasta el 2026-08-29 solo se podía indicar al solicitar el alta, así que los
pilotos que ya tenían cuenta no podían rellenarlo nunca — y sin CID no
aparecen con su indicativo de EvA en el mapa de vuelos en vivo, solo con su
número de VATSIM.
"""
import pytest

from avcars import cuentas


@pytest.fixture
def almacen_tmp(tmp_path):
    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    cuentas.crear_cuenta("EVA001", "clave", "eva001@ejemplo.test")
    cuentas.crear_cuenta("EVA002", "clave", "eva002@ejemplo.test")
    yield
    cuentas.configurar_almacen(original)


def _cid_de(license_id: str) -> str:
    return next(
        u["vatsim_cid"] for u in cuentas.listar_usuarios()
        if u["license_id"] == license_id
    )


# -- normalización -----------------------------------------------------

def test_se_queda_solo_con_los_digitos():
    """La gente lo copia con espacios o escribe «CID 1234567»."""
    assert cuentas.normalizar_cid(" CID 1234567 ") == "1234567"
    assert cuentas.normalizar_cid("1234567") == "1234567"


def test_sin_digitos_queda_vacio():
    assert cuentas.normalizar_cid("no tengo") == ""
    assert cuentas.normalizar_cid("") == ""
    assert cuentas.normalizar_cid(None) == ""


# -- guardar -----------------------------------------------------------

def test_un_piloto_ya_dado_de_alta_puede_recibir_su_cid(almacen_tmp):
    assert _cid_de("EVA001") == ""

    cuentas.cambiar_vatsim_cid("EVA001", "1234567")

    assert _cid_de("EVA001") == "1234567"


def test_vacio_lo_borra(almacen_tmp):
    """Un piloto puede querer dejar de salir en el mapa."""
    cuentas.cambiar_vatsim_cid("EVA001", "1234567")

    cuentas.cambiar_vatsim_cid("EVA001", "")

    assert _cid_de("EVA001") == ""


def test_se_guarda_normalizado(almacen_tmp):
    cuentas.cambiar_vatsim_cid("EVA001", "CID 1234567")

    assert _cid_de("EVA001") == "1234567"


# -- unicidad ----------------------------------------------------------

def test_dos_pilotos_no_pueden_tener_el_mismo_cid(almacen_tmp):
    """Rompería el mapa en silencio: el feed trae un CID y habría dos dueños."""
    cuentas.cambiar_vatsim_cid("EVA001", "1234567")

    with pytest.raises(ValueError, match="ya lo tiene otro piloto"):
        cuentas.cambiar_vatsim_cid("EVA002", "1234567")

    assert _cid_de("EVA002") == ""


def test_guardar_el_mismo_cid_en_el_mismo_piloto_no_molesta(almacen_tmp):
    """Pulsar «Guardar» sin cambiar nada no puede dar error."""
    cuentas.cambiar_vatsim_cid("EVA001", "1234567")

    cuentas.cambiar_vatsim_cid("EVA001", "1234567")

    assert _cid_de("EVA001") == "1234567"


def test_varios_pilotos_pueden_estar_sin_cid(almacen_tmp):
    """Vacío no ocupa: puede haber muchos que aún no lo hayan dado."""
    cuentas.cambiar_vatsim_cid("EVA001", "")
    cuentas.cambiar_vatsim_cid("EVA002", "")

    assert cuentas.cid_libre("")


def test_cid_libre_no_se_confunde_con_el_dueno_actual(almacen_tmp):
    cuentas.cambiar_vatsim_cid("EVA001", "1234567")

    assert cuentas.cid_libre("1234567", excepto="EVA001")
    assert not cuentas.cid_libre("1234567", excepto="EVA002")
