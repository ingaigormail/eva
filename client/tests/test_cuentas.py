"""El almacén de cuentas es el mismo para D1 y para la web."""
import json

import pytest

from avcars import cuentas


@pytest.fixture
def almacen_tmp(tmp_path):
    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    yield
    cuentas.configurar_almacen(original)


def test_importar_el_modulo_no_toca_la_base_real(tmp_path, monkeypatch):
    """Regresión 2026-08-18: la inicialización debe ser perezosa.

    Antes, `cuentas.py` inicializaba el almacén al importarse, contra
    `DB_PATH` por defecto — que en cualquier proceso (un test incluido) es la
    base real. Un `pytest` que solo pretendía usar un directorio temporal
    dejó una tabla con esquema equivocado en `web/data/eva.db` de verdad.

    Aquí se simula justo ese escenario: recargar el módulo con `DB_PATH`
    apuntando a un sitio temporal y comprobar que, con solo importarlo (sin
    llamar a ninguna función), no se ha escrito nada en disco.
    """
    import importlib

    destino = tmp_path / "no_debe_tocarse"
    monkeypatch.setattr(cuentas, "DB_PATH", destino / "eva.db")
    monkeypatch.setattr(cuentas, "_inicializado", False)

    importlib.reload(cuentas)  # vuelve a ejecutar el módulo, cuerpo incluido

    assert not destino.exists(), (
        "importar el módulo ha inicializado el almacén: "
        "la inicialización perezosa se ha roto"
    )

    importlib.reload(cuentas)  # deja el módulo como estaba para el resto de tests


def test_restaurar_el_almacen_original_tampoco_lo_toca(tmp_path, monkeypatch):
    """El fallo real del 2026-08-18, más sutil que el anterior.

    El patrón de fixture de todo el proyecto es: apuntar a un directorio
    temporal al empezar, y `configurar_almacen(original)` al terminar para
    dejarlo «como estaba». `original` casi siempre es la ruta de producción.
    Si `configurar_almacen` inicializara de inmediato, **cada test** dejaría,
    al terminar, una escritura real contra `web/data/eva.db` — con la semilla
    de administrador incluida. Aquí se reproduce exactamente ese patrón.
    """
    produccion_falsa = tmp_path / "produccion"
    otro = tmp_path / "otro"
    monkeypatch.setattr(cuentas, "DB_PATH", produccion_falsa / "eva.db")
    monkeypatch.setattr(cuentas, "USUARIOS_PATH", produccion_falsa / "usuarios.json")
    monkeypatch.setattr(cuentas, "_inicializado", False)
    original = cuentas.USUARIOS_PATH  # tal como lo captura cada fixture real

    cuentas.configurar_almacen(otro / "usuarios.json")
    cuentas.configurar_almacen(original)  # el teardown de cualquier fixture

    assert not produccion_falsa.exists(), (
        "restaurar el almacén original ha inicializado esa ruta: "
        "un test dejaría escritura real en producción al terminar"
    )


def test_pruebas_entra_con_la_contraseña_semilla(almacen_tmp):
    assert cuentas.existe_usuario("pruebas")
    assert cuentas.autenticar("pruebas", "pruebas")
    assert not cuentas.autenticar("pruebas", "otra")


def test_desconocido_no_entra_ni_se_registra_solo(almacen_tmp):
    assert not cuentas.existe_usuario("NUEVO99")
    assert not cuentas.autenticar("NUEVO99", "secreto")
    assert not cuentas.existe_usuario("NUEVO99")


# -- Modelo de usuario: correo, estado y rol ------------------------------


def test_pruebas_es_admin_por_rol_no_por_nombre(almacen_tmp):
    assert cuentas.rol_de("pruebas") == cuentas.ROL_ADMIN
    assert cuentas.es_admin("pruebas")

    # Y el rol se puede mover: otro piloto puede ser admin sin tocar código.
    cuentas.crear_cuenta("EVA18L", "clave", "eva18l@ejemplo.com")
    assert not cuentas.es_admin("EVA18L")
    cuentas.cambiar_rol("EVA18L", cuentas.ROL_ADMIN)
    assert cuentas.es_admin("EVA18L")
    assert cuentas.tiene_permiso("EVA18L", cuentas.PERM_GESTIONAR_USUARIOS)


def test_cuenta_bloqueada_no_entra_aunque_acierte(almacen_tmp):
    cuentas.crear_cuenta("EVA001", "clave", "eva001@ejemplo.com")
    assert cuentas.autenticar("EVA001", "clave")

    cuentas.bloquear("EVA001")
    assert not cuentas.autenticar("EVA001", "clave")
    assert cuentas.autenticar_detallado("EVA001", "clave") == cuentas.AUTH_BLOQUEADA
    assert cuentas.permisos_de("EVA001") == frozenset()

    cuentas.desbloquear("EVA001")
    assert cuentas.autenticar("EVA001", "clave")


def test_el_estado_no_se_revela_a_quien_falla_la_contraseña(almacen_tmp):
    cuentas.crear_cuenta("EVA002", "clave", "eva002@ejemplo.com")
    cuentas.bloquear("EVA002")
    # Contraseña mala: la respuesta es la misma que para cualquier otra cuenta.
    assert cuentas.autenticar_detallado("EVA002", "mala") == cuentas.AUTH_PASSWORD
    assert cuentas.autenticar_detallado("NADIE", "mala") == cuentas.AUTH_DESCONOCIDO


def test_el_alta_exige_correo_valido_y_sin_repetir(almacen_tmp):
    with pytest.raises(ValueError):
        cuentas.crear_cuenta("EVA003", "clave", "esto-no-es-un-correo")

    cuentas.crear_cuenta("EVA003", "clave", "Piloto@Ejemplo.COM")
    assert cuentas.correo_de("EVA003") == "piloto@ejemplo.com"
    assert cuentas.buscar_por_correo("PILOTO@ejemplo.com") == "EVA003"

    with pytest.raises(ValueError):
        cuentas.crear_cuenta("EVA004", "clave", "piloto@ejemplo.com")
    with pytest.raises(ValueError):
        cuentas.crear_cuenta("EVA003", "otra", "distinto@ejemplo.com")


def test_pruebas_deja_de_ser_admin_cuando_hay_otro_de_verdad(almacen_tmp):
    """Y el arranque no vuelve a ascenderlo: si no, no habría forma de quitarlo."""
    cuentas.crear_cuenta(
        "EvA18L", "clave", "jefe@ejemplo.com", rol=cuentas.ROL_ADMIN
    )
    cuentas.cambiar_rol("pruebas", cuentas.ROL_PILOTO)

    cuentas._asegurar_semilla()  # lo que ocurre en cada arranque

    assert cuentas.rol_de("pruebas") == cuentas.ROL_PILOTO
    assert cuentas.es_admin("EvA18L")


def test_sin_ningun_admin_pruebas_recupera_el_mando(almacen_tmp):
    """Red de seguridad: nunca quedarse sin poder administrar nada."""
    cuentas.cambiar_rol("pruebas", cuentas.ROL_PILOTO)
    assert cuentas.cuantos_admins() == 0

    cuentas._asegurar_semilla()

    assert cuentas.rol_de("pruebas") == cuentas.ROL_ADMIN


def test_el_indicativo_no_distingue_mayusculas(almacen_tmp):
    """Nadie recuerda con qué caja se dio de alta su callsign."""
    cuentas.crear_cuenta("EvA18L", "clave", "eva18l@ejemplo.com")

    for tecleado in ("EvA18L", "eva18l", "EVA18L", "  Eva18l  "):
        assert cuentas.existe_usuario(tecleado), tecleado
        assert cuentas.autenticar(tecleado, "clave"), tecleado
        # Pero por dentro sigue siendo uno solo, con su forma original.
        assert cuentas.id_canonico(tecleado) == "EvA18L"

    assert len(cuentas.listar_usuarios()) == 2  # pruebas + EvA18L


def test_no_se_cuelan_dos_cuentas_que_solo_cambian_de_caja(almacen_tmp):
    cuentas.crear_cuenta("EvA18L", "clave", "eva18l@ejemplo.com")
    with pytest.raises(ValueError):
        cuentas.crear_cuenta("eva18l", "otra", "otro@ejemplo.com")


def test_bloquear_y_cambiar_rol_tampoco_distinguen_caja(almacen_tmp):
    cuentas.crear_cuenta("EvA18L", "clave", "eva18l@ejemplo.com")

    cuentas.bloquear("EVA18L")
    assert cuentas.estado_de("eva18l") == cuentas.ESTADO_BLOQUEADA
    cuentas.desbloquear("eva18l")
    cuentas.cambiar_rol("EVA18L", cuentas.ROL_ADMIN)
    assert cuentas.es_admin("EvA18L")


def test_listar_usuarios_no_saca_el_hash(almacen_tmp):
    cuentas.crear_cuenta("EVA005", "clave", "eva005@ejemplo.com")
    fichas = cuentas.listar_usuarios()
    assert {f["license_id"] for f in fichas} == {"pruebas", "EVA005"}
    assert all("password" not in f for f in fichas)


def _hash_de(license_id: str) -> str:
    with cuentas.conexion() as con:
        return con.execute(
            "SELECT password FROM usuarios WHERE license_id = ?", (license_id,)
        ).fetchone()["password"]


def test_el_usuarios_json_de_antes_se_importa_a_la_base(tmp_path):
    """Nadie pierde su cuenta al pasar de JSON a SQLite.

    El formato original era `{id: hash}` a secas; el intermedio, la ficha
    entera. Los dos tienen que entrar.
    """
    original = cuentas.USUARIOS_PATH
    viejo = tmp_path / "usuarios.json"
    cuentas.configurar_almacen(viejo)
    try:
        # Un hash real con el que luego comprobar que la contraseña sigue valiendo.
        cuentas.registrar_usuario("MOLDE", "clave")
        hash_real = _hash_de("MOLDE")

        # Se tira la base y se deja solo el JSON, como en un equipo que
        # actualiza el código sin haber abierto nunca la versión nueva.
        (tmp_path / "eva.db").unlink()
        viejo.write_text(
            json.dumps(
                {
                    "ANTIGUO": hash_real,  # formato original
                    "FICHA": {  # formato intermedio
                        "password": hash_real,
                        "correo": "ficha@ejemplo.com",
                        "estado": "bloqueada",
                        "rol": "admin",
                    },
                }
            ),
            encoding="utf-8",
        )
        cuentas.configurar_almacen(viejo)

        assert cuentas.autenticar("ANTIGUO", "clave")
        assert cuentas.estado_de("ANTIGUO") == cuentas.ESTADO_ACTIVA
        assert cuentas.rol_de("ANTIGUO") == cuentas.ROL_PILOTO
        assert cuentas.correo_de("ANTIGUO") == ""

        assert cuentas.correo_de("FICHA") == "ficha@ejemplo.com"
        assert cuentas.estado_de("FICHA") == cuentas.ESTADO_BLOQUEADA
        assert cuentas.rol_de("FICHA") == cuentas.ROL_ADMIN

        # El fichero se conserva apartado, no se borra.
        assert not viejo.exists()
        assert (tmp_path / "usuarios.json.migrado").exists()
    finally:
        cuentas.configurar_almacen(original)


def test_la_importacion_no_repisa_una_base_que_ya_tiene_cuentas(tmp_path):
    """El JSON es historia en cuanto la base tiene datos."""
    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    try:
        cuentas.crear_cuenta("EVA010", "buena", "eva010@ejemplo.com")
        (tmp_path / "usuarios.json").write_text(
            json.dumps({"EVA010": "pbkdf2_sha256$1$00$00"}), encoding="utf-8"
        )
        cuentas.configurar_almacen(tmp_path / "usuarios.json")

        assert cuentas.autenticar("EVA010", "buena")
    finally:
        cuentas.configurar_almacen(original)
