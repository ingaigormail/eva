"""Testigos de contraseña: un solo uso, con caducidad y sin filtrar nada."""
import pytest

from avcars import cuentas, restablecer


@pytest.fixture
def almacen_tmp(tmp_path):
    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    cuentas.crear_cuenta("EVA18L", "vieja", "eva18l@ejemplo.com")
    yield tmp_path
    cuentas.configurar_almacen(original)


def test_el_testigo_cambia_la_contraseña_y_la_anterior_deja_de_valer(almacen_tmp):
    testigo = restablecer.crear("EVA18L")
    assert restablecer.consumir(testigo, "nueva") == "EVA18L"

    assert cuentas.autenticar("EVA18L", "nueva")
    assert not cuentas.autenticar("EVA18L", "vieja")


def test_un_testigo_solo_sirve_una_vez(almacen_tmp):
    testigo = restablecer.crear("EVA18L")
    restablecer.consumir(testigo, "nueva")

    assert restablecer.piloto_de(testigo) is None
    assert restablecer.consumir(testigo, "otra") is None
    assert cuentas.autenticar("EVA18L", "nueva")


def test_un_testigo_caducado_no_vale(almacen_tmp):
    testigo = restablecer.crear("EVA18L", minutos=-1)
    assert restablecer.piloto_de(testigo) is None
    assert restablecer.consumir(testigo, "nueva") is None
    assert cuentas.autenticar("EVA18L", "vieja")


def test_pedir_otro_testigo_invalida_el_anterior(almacen_tmp):
    primero = restablecer.crear("EVA18L")
    segundo = restablecer.crear("EVA18L")

    assert restablecer.piloto_de(primero) is None
    assert restablecer.piloto_de(segundo) == "EVA18L"


def test_en_la_base_no_queda_el_testigo_en_claro(almacen_tmp):
    testigo = restablecer.crear("EVA18L")

    with cuentas.conexion() as con:
        filas = con.execute("SELECT * FROM testigos").fetchall()

    assert len(filas) == 1
    assert filas[0]["license_id"] == "EVA18L"
    assert testigo not in dict(filas[0]).values()
    # Y tampoco está en el fichero, mirado en crudo.
    crudo = (almacen_tmp / "eva.db").read_bytes()
    assert testigo.encode() not in crudo


def test_no_se_emiten_testigos_para_quien_no_existe(almacen_tmp):
    with pytest.raises(ValueError):
        restablecer.crear("NADIE")
