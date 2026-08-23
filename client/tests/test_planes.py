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


# -- via: con cuál de los tres botones se guardó -------------------------


def test_via_se_guarda_y_se_lista(almacen_tmp):
    ident = planes.guardar("EvA18L", PLAN, via="vatsim")

    assert planes.obtener(ident, "EvA18L")["via"] == "vatsim"
    assert planes.listar("EvA18L")[0]["via"] == "vatsim"


def test_via_no_reconocida_se_guarda_vacia(almacen_tmp):
    ident = planes.guardar("EvA18L", PLAN, via="lo-que-sea")
    assert planes.obtener(ident, "EvA18L")["via"] == ""


def test_via_por_defecto_es_vacia(almacen_tmp):
    ident = planes.guardar("EvA18L", PLAN)
    assert planes.obtener(ident, "EvA18L")["via"] == ""


def test_actualizar_sin_via_mantiene_la_que_ya_tenia(almacen_tmp):
    ident = planes.guardar("EvA18L", PLAN, via="icao")
    planes.guardar("EvA18L", {**PLAN, "arrival": "LEZL"}, plan_id=ident)

    assert planes.obtener(ident, "EvA18L")["via"] == "icao"


def test_actualizar_con_via_nueva_la_cambia(almacen_tmp):
    ident = planes.guardar("EvA18L", PLAN, via="icao")
    planes.guardar("EvA18L", PLAN, plan_id=ident, via="vatsim")

    assert planes.obtener(ident, "EvA18L")["via"] == "vatsim"


def test_una_base_de_datos_de_antes_de_via_se_migra_sola(tmp_path):
    """`CREATE TABLE IF NOT EXISTS` no añade columnas a una tabla que ya
    existe: sin `_migrar_esquema()`, una base real con planes guardados
    antes de esta columna se quedaría sin poder guardar `via`.
    """
    import sqlite3

    original = cuentas.DB_PATH
    cuentas.configurar_almacen(tmp_path)
    try:
        # Fabrica una base "de antes": la tabla planes tal como era, sin `via`.
        con = sqlite3.connect(cuentas.DB_PATH)
        con.execute(
            """CREATE TABLE planes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_id TEXT NOT NULL, callsign TEXT NOT NULL DEFAULT '',
                origen TEXT NOT NULL DEFAULT '', destino TEXT NOT NULL DEFAULT '',
                alterno TEXT NOT NULL DEFAULT '', aeronave TEXT NOT NULL DEFAULT '',
                nivel TEXT NOT NULL DEFAULT '', ruta TEXT NOT NULL DEFAULT '',
                datos TEXT NOT NULL, creado TEXT NOT NULL, actualizado TEXT NOT NULL
            )"""
        )
        con.execute(
            "INSERT INTO planes (license_id, origen, destino, datos, creado, actualizado) "
            "VALUES ('EvA18L', 'LEMD', 'LEIB', '{}', 'x', 'x')"
        )
        con.commit()
        con.close()

        cuentas.crear_cuenta("EvA18L", "clave", "uno@ejemplo.com")

        # Cualquier acceso normal dispara la migración sin que nadie la pida.
        antiguos = planes.listar("EvA18L")
        assert len(antiguos) == 1
        assert antiguos[0]["via"] == ""  # el plan de antes no lo tenía

        nuevo = planes.guardar("EvA18L", PLAN, via="sin_vatsim")
        assert planes.obtener(nuevo, "EvA18L")["via"] == "sin_vatsim"
    finally:
        cuentas.configurar_almacen(original)
