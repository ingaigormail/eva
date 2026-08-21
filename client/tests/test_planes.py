"""Planes de vuelo guardados: son del piloto que los guardó, y de nadie más."""
import pytest

from avcars import cuentas, planes

PLAN = {
    "callsign": "EVA321",
    "departure": "LEMD",
    "arrival": "LEIB",
    "alternate": "LEPA",
    "aircraft": "C172",
    "cruise_alt_ft": 8000,
    "route": "DCT TERSA DCT",
    "rules": "V",
    "remarks": "prueba",
}


@pytest.fixture
def almacen_tmp(tmp_path):
    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    cuentas.crear_cuenta("EvA18L", "clave", "uno@ejemplo.com")
    cuentas.crear_cuenta("EVA999", "clave", "otro@ejemplo.com")
    yield
    cuentas.configurar_almacen(original)


def test_se_guarda_y_se_lista_con_lo_justo_para_reconocerlo(almacen_tmp):
    ident = planes.guardar("EvA18L", PLAN)

    lista = planes.listar("EvA18L")
    assert len(lista) == 1
    fila = lista[0]
    assert fila["id"] == ident
    assert fila["origen"] == "LEMD"
    assert fila["destino"] == "LEIB"
    assert fila["aeronave"] == "C172"
    assert fila["creado"]


def test_al_abrirlo_vuelve_el_plan_entero(almacen_tmp):
    ident = planes.guardar("EvA18L", PLAN)
    plan = planes.obtener(ident, "EvA18L")

    # Tal cual se guardó: el planificador tiene que poder rehacerlo igual.
    assert plan["datos"] == PLAN


def test_un_piloto_no_ve_ni_abre_ni_borra_los_planes_de_otro(almacen_tmp):
    ajeno = planes.guardar("EVA999", PLAN)

    assert planes.listar("EvA18L") == []
    assert planes.obtener(ajeno, "EvA18L") is None
    assert planes.borrar(ajeno, "EvA18L") is False
    # Y el dueño lo sigue teniendo.
    assert planes.obtener(ajeno, "EVA999") is not None


def test_tampoco_lo_pisa_al_actualizar(almacen_tmp):
    ajeno = planes.guardar("EVA999", PLAN)

    with pytest.raises(ValueError):
        planes.guardar("EvA18L", {**PLAN, "arrival": "LEZL"}, plan_id=ajeno)

    assert planes.obtener(ajeno, "EVA999")["datos"]["arrival"] == "LEIB"


def test_el_indicativo_no_distingue_mayusculas(almacen_tmp):
    planes.guardar("EvA18L", PLAN)
    assert len(planes.listar("eva18l")) == 1
    assert planes.cuantos("EVA18L") == 1


def test_actualizar_no_crea_una_copia(almacen_tmp):
    ident = planes.guardar("EvA18L", PLAN)
    planes.guardar("EvA18L", {**PLAN, "arrival": "LEZL"}, plan_id=ident)

    assert planes.cuantos("EvA18L") == 1
    assert planes.obtener(ident, "EvA18L")["destino"] == "LEZL"


def test_un_plan_sin_origen_ni_destino_no_se_guarda(almacen_tmp):
    with pytest.raises(ValueError):
        planes.guardar("EvA18L", {"callsign": "EVA321"})
    with pytest.raises(ValueError):
        planes.guardar("EvA18L", {})
    assert planes.cuantos("EvA18L") == 0


def test_borrar_quita_solo_ese(almacen_tmp):
    uno = planes.guardar("EvA18L", PLAN)
    planes.guardar("EvA18L", {**PLAN, "arrival": "LEZL"})

    assert planes.borrar(uno, "EvA18L") is True
    assert planes.cuantos("EvA18L") == 1
    assert planes.obtener(uno, "EvA18L") is None
