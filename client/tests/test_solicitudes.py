"""Las peticiones de alta se guardan; un correo perdido ya no pierde a nadie."""
import pytest

from avcars import cuentas, solicitudes


@pytest.fixture
def almacen_tmp(tmp_path):
    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    yield
    cuentas.configurar_almacen(original)


def test_una_solicitud_queda_guardada_con_todos_sus_datos(almacen_tmp):
    solicitudes.crear("EVA777", "Ana Pérez", "ana@ejemplo.com", discord="ana#1234")

    pendientes = solicitudes.pendientes()
    assert len(pendientes) == 1
    fila = pendientes[0]
    assert fila["license_id"] == "EVA777"
    assert fila["nombre"] == "Ana Pérez"
    assert fila["discord"] == "ana#1234"
    assert fila["correo"] == "ana@ejemplo.com"
    assert fila["creado"]
    assert fila["estado"] == solicitudes.PENDIENTE


def test_pedirlo_dos_veces_no_amontona_copias(almacen_tmp):
    primera = solicitudes.crear("EVA777", "Ana", "ana@ejemplo.com")
    segunda = solicitudes.crear("EVA777", "Ana Pérez López", "ana2@ejemplo.com")

    assert primera == segunda
    assert solicitudes.cuantas_pendientes() == 1
    # Se queda con los datos nuevos.
    assert solicitudes.pendientes()[0]["nombre"] == "Ana Pérez López"
    assert solicitudes.pendientes()[0]["correo"] == "ana2@ejemplo.com"


def test_una_solicitud_sin_datos_minimos_no_entra(almacen_tmp):
    with pytest.raises(ValueError):
        solicitudes.crear("", "Ana", "ana@ejemplo.com")
    with pytest.raises(ValueError):
        solicitudes.crear("EVA777", "", "ana@ejemplo.com")
    with pytest.raises(ValueError):
        solicitudes.crear("EVA777", "Ana", "esto-no-es-correo")
    assert solicitudes.cuantas_pendientes() == 0


def test_resolver_deja_constancia_de_quien_y_cuando(almacen_tmp):
    ident = solicitudes.crear("EVA777", "Ana", "ana@ejemplo.com")
    solicitudes.resolver(ident, solicitudes.APROBADA, por="pruebas")

    assert solicitudes.cuantas_pendientes() == 0
    guardada = solicitudes.obtener(ident)
    assert guardada["estado"] == solicitudes.APROBADA
    assert guardada["resuelta_por"] == "pruebas"
    assert guardada["resuelta_en"]


def test_una_solicitud_resuelta_no_se_resuelve_dos_veces(almacen_tmp):
    ident = solicitudes.crear("EVA777", "Ana", "ana@ejemplo.com")
    solicitudes.resolver(ident, solicitudes.RECHAZADA, por="pruebas")

    with pytest.raises(ValueError):
        solicitudes.resolver(ident, solicitudes.APROBADA, por="pruebas")


def test_las_resueltas_siguen_en_el_historial(almacen_tmp):
    ident = solicitudes.crear("EVA777", "Ana", "ana@ejemplo.com")
    solicitudes.resolver(ident, solicitudes.RECHAZADA, por="pruebas")

    # Rechazar no borra: queda quién pidió entrar y en qué quedó.
    assert [s["license_id"] for s in solicitudes.historial()] == ["EVA777"]


def test_tras_rechazar_se_puede_volver_a_pedir(almacen_tmp):
    primera = solicitudes.crear("EVA777", "Ana", "ana@ejemplo.com")
    solicitudes.resolver(primera, solicitudes.RECHAZADA, por="pruebas")

    segunda = solicitudes.crear("EVA777", "Ana", "ana@ejemplo.com")
    assert segunda != primera
    assert solicitudes.cuantas_pendientes() == 1
