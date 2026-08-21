"""La página de gestión: quién entra, qué puede hacer y qué no le dejamos.

    python -m pytest web/test_gestion_usuarios.py
"""
import sys
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

from app import app  # noqa: E402
from avcars import correo, cuentas, restablecer, sesion_web, solicitudes  # noqa: E402


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("EVA_SMTP_MODO", "memoria")
    monkeypatch.setattr(sesion_web, "SESION_PATH", tmp_path / "sesion_activa.json")

    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")  # semilla: pruebas (admin)
    cuentas.crear_cuenta("EVA18L", "clave", "eva18l@ejemplo.com")
    correo.BANDEJA.clear()

    app.config["TESTING"] = True
    yield

    correo.BANDEJA.clear()
    cuentas.configurar_almacen(original)


def _entrar(cliente, user_id, password):
    return cliente.post(
        "/login", data={"user_id": user_id, "password": password}
    )


@pytest.fixture
def admin():
    cliente = app.test_client()
    _entrar(cliente, "pruebas", "pruebas")
    return cliente


@pytest.fixture
def piloto():
    cliente = app.test_client()
    _entrar(cliente, "EVA18L", "clave")
    return cliente


# -- Quién entra ----------------------------------------------------------


def test_un_piloto_normal_no_entra_en_la_gestion(piloto):
    assert piloto.get("/gestion/usuarios").status_code == 403
    assert piloto.post("/gestion/usuarios/alta", data={}).status_code == 403


def test_sin_sesion_te_manda_al_login():
    cliente = app.test_client()
    respuesta = cliente.get("/gestion/usuarios")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers["Location"]


def test_el_admin_ve_a_todos_con_su_correo_y_su_estado(admin):
    html = admin.get("/gestion/usuarios").get_data(as_text=True)
    assert "pruebas" in html
    assert "EVA18L" in html
    assert "eva18l@ejemplo.com" in html


def test_el_acceso_a_la_gestion_solo_sale_en_el_menu_del_admin(admin, piloto):
    assert "/gestion/usuarios" in admin.get("/").get_data(as_text=True)
    assert "/gestion/usuarios" not in piloto.get("/").get_data(as_text=True)


def test_el_rol_manda_no_el_nombre(piloto):
    """`EVA18L` no es «pruebas» y aun así entra en cuanto es admin."""
    cuentas.cambiar_rol("EVA18L", cuentas.ROL_ADMIN)
    assert piloto.get("/gestion/usuarios").status_code == 200


# -- Alta desde la gestión ------------------------------------------------


def test_el_alta_crea_la_cuenta_y_manda_el_enlace_sin_contraseña(admin):
    admin.post(
        "/gestion/usuarios/alta",
        data={"license_id": "EVA777", "correo": "nuevo@ejemplo.com", "rol": "piloto"},
    )

    assert cuentas.existe_usuario("EVA777")
    assert cuentas.rol_de("EVA777") == cuentas.ROL_PILOTO

    assert len(correo.BANDEJA) == 1
    mensaje = correo.BANDEJA[0]
    assert mensaje["para"] == "nuevo@ejemplo.com"
    assert "/restablecer/" in mensaje["cuerpo"]

    # Nadie, ni el administrador, conoce una contraseña con la que entrar.
    for intento in ("", "EVA777", "eva", "1234"):
        assert not cuentas.autenticar("EVA777", intento)


def test_el_piloto_de_alta_nueva_pone_su_contraseña_con_el_enlace(admin):
    admin.post(
        "/gestion/usuarios/alta",
        data={"license_id": "EVA777", "correo": "nuevo@ejemplo.com"},
    )
    import re

    enlace = re.search(r"/restablecer/\S+", correo.BANDEJA[0]["cuerpo"]).group(0)

    cliente = app.test_client()
    cliente.post(enlace, data={"password": "suya1234", "password2": "suya1234"})
    assert cuentas.autenticar("EVA777", "suya1234")


def test_no_se_da_de_alta_dos_veces_ni_con_correo_repetido(admin):
    r = admin.post(
        "/gestion/usuarios/alta",
        data={"license_id": "EVA18L", "correo": "otro@ejemplo.com"},
        follow_redirects=True,
    )
    assert "ya está dado de alta" in r.get_data(as_text=True)

    r = admin.post(
        "/gestion/usuarios/alta",
        data={"license_id": "OTRO", "correo": "eva18l@ejemplo.com"},
        follow_redirects=True,
    )
    assert "correo ya está en uso" in r.get_data(as_text=True)
    assert not cuentas.existe_usuario("OTRO")


# -- Bloqueo, rol y correo ------------------------------------------------


def test_bloquear_y_desbloquear_desde_la_pantalla(admin):
    admin.post("/gestion/usuarios/EVA18L", data={"accion": "bloquear"})
    assert cuentas.estado_de("EVA18L") == cuentas.ESTADO_BLOQUEADA
    assert not cuentas.autenticar("EVA18L", "clave")

    admin.post("/gestion/usuarios/EVA18L", data={"accion": "desbloquear"})
    assert cuentas.autenticar("EVA18L", "clave")


def test_un_admin_no_puede_bloquearse_a_si_mismo(admin):
    r = admin.post(
        "/gestion/usuarios/pruebas", data={"accion": "bloquear"}, follow_redirects=True
    )
    assert "a ti mismo" in r.get_data(as_text=True)
    assert cuentas.esta_activa("pruebas")


def test_no_se_puede_dejar_la_aplicacion_sin_ningun_admin(admin):
    """Ni quitándose el rol ni bloqueando al único que queda."""
    r = admin.post(
        "/gestion/usuarios/pruebas",
        data={"accion": "rol", "rol": "piloto"},
        follow_redirects=True,
    )
    assert "único administrador" in r.get_data(as_text=True)
    assert cuentas.rol_de("pruebas") == cuentas.ROL_ADMIN

    # Con un segundo administrador, ya se puede.
    cuentas.cambiar_rol("EVA18L", cuentas.ROL_ADMIN)
    admin.post("/gestion/usuarios/pruebas", data={"accion": "rol", "rol": "piloto"})
    assert cuentas.rol_de("pruebas") == cuentas.ROL_PILOTO


def test_cambiar_el_correo_de_una_cuenta_antigua(admin):
    cuentas.registrar_usuario("ANTIGUO", "clave")  # sin correo, como las viejas
    admin.post(
        "/gestion/usuarios/ANTIGUO",
        data={"accion": "correo", "correo": "Antiguo@Ejemplo.COM"},
    )
    assert cuentas.correo_de("ANTIGUO") == "antiguo@ejemplo.com"


def test_reenviar_el_enlace_a_quien_no_tiene_correo_avisa(admin):
    cuentas.registrar_usuario("ANTIGUO", "clave")
    r = admin.post(
        "/gestion/usuarios/ANTIGUO", data={"accion": "enlace"}, follow_redirects=True
    )
    assert "no tiene correo asociado" in r.get_data(as_text=True)
    assert correo.BANDEJA == []


def test_el_enlace_reenviado_cambia_la_contraseña(admin):
    admin.post("/gestion/usuarios/EVA18L", data={"accion": "enlace"})
    assert len(correo.BANDEJA) == 1

    import re

    enlace = re.search(r"/restablecer/\S+", correo.BANDEJA[0]["cuerpo"]).group(0)
    app.test_client().post(enlace, data={"password": "nueva123", "password2": "nueva123"})

    assert cuentas.autenticar("EVA18L", "nueva123")
    assert not cuentas.autenticar("EVA18L", "clave")


def test_una_accion_sobre_alguien_que_no_existe_no_revienta(admin):
    r = admin.post(
        "/gestion/usuarios/FANTASMA", data={"accion": "bloquear"}, follow_redirects=True
    )
    assert r.status_code == 200
    assert "no está dado de alta" in r.get_data(as_text=True)


# -- Bandeja de solicitudes ----------------------------------------------


@pytest.fixture
def solicitud():
    return solicitudes.crear(
        "EVA777", "Ana Pérez López", "ana@ejemplo.com", discord="ana#1234"
    )


def test_las_solicitudes_pendientes_salen_en_la_pantalla(admin, solicitud):
    html = admin.get("/gestion/usuarios").get_data(as_text=True)
    assert "EVA777" in html
    assert "Ana Pérez López" in html
    assert "ana#1234" in html
    assert "ana@ejemplo.com" in html


def test_aprobar_crea_la_cuenta_manda_el_enlace_y_cierra_la_solicitud(admin, solicitud):
    admin.post(f"/gestion/solicitudes/{solicitud}", data={"accion": "aprobar"})

    assert cuentas.existe_usuario("EVA777")
    assert cuentas.correo_de("EVA777") == "ana@ejemplo.com"
    assert cuentas.rol_de("EVA777") == cuentas.ROL_PILOTO

    assert solicitudes.cuantas_pendientes() == 0
    guardada = solicitudes.obtener(solicitud)
    assert guardada["estado"] == solicitudes.APROBADA
    assert guardada["resuelta_por"] == "pruebas"

    assert len(correo.BANDEJA) == 1
    assert correo.BANDEJA[0]["para"] == "ana@ejemplo.com"
    assert "/restablecer/" in correo.BANDEJA[0]["cuerpo"]


def test_se_puede_aprobar_directamente_como_admin(admin, solicitud):
    admin.post(
        f"/gestion/solicitudes/{solicitud}", data={"accion": "aprobar", "rol": "admin"}
    )
    assert cuentas.es_admin("EVA777")


def test_rechazar_no_crea_cuenta_ni_avisa_a_nadie(admin, solicitud):
    admin.post(f"/gestion/solicitudes/{solicitud}", data={"accion": "rechazar"})

    assert not cuentas.existe_usuario("EVA777")
    assert solicitudes.obtener(solicitud)["estado"] == solicitudes.RECHAZADA
    assert correo.BANDEJA == []


def test_una_solicitud_ya_resuelta_no_se_procesa_dos_veces(admin, solicitud):
    admin.post(f"/gestion/solicitudes/{solicitud}", data={"accion": "aprobar"})
    r = admin.post(
        f"/gestion/solicitudes/{solicitud}",
        data={"accion": "aprobar"},
        follow_redirects=True,
    )
    assert "ya no está pendiente" in r.get_data(as_text=True)


def test_si_el_alta_falla_la_solicitud_sigue_pendiente(admin):
    """Alguien pidió un ID que entretanto se dio de alta por otro camino."""
    ident = solicitudes.crear("EVA18L", "Homónimo", "otro@ejemplo.com")
    r = admin.post(
        f"/gestion/solicitudes/{ident}",
        data={"accion": "aprobar"},
        follow_redirects=True,
    )

    assert "No se ha podido dar de alta" in r.get_data(as_text=True)
    assert solicitudes.obtener(ident)["estado"] == solicitudes.PENDIENTE


def test_un_piloto_normal_no_toca_las_solicitudes(piloto, solicitud):
    assert (
        piloto.post(
            f"/gestion/solicitudes/{solicitud}", data={"accion": "aprobar"}
        ).status_code
        == 403
    )
    assert solicitudes.cuantas_pendientes() == 1


def test_el_enlace_de_alta_dura_mas_que_el_de_un_olvido(admin):
    """Un alta puede tardar en mirarse el correo; un olvido, no tanto."""
    import app as app_module

    assert app_module.HORAS_ENLACE_ALTA * 60 > restablecer.MINUTOS_VALIDEZ
