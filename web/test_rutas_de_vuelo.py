"""Ninguna ruta de `/vuelo/` le enseña a un piloto lo que no es suyo.

Se ejecutan con:

    python -m pytest web/test_rutas_de_vuelo.py

Por qué hace falta esto además de `test_app.py`
------------------------------------------------
El IDOR del 2026-08-27 (`/vuelo/<nombre>/json` devolvía el vuelo de
cualquiera) se coló **teniendo 209 tests de web**. La causa no fue la falta
de pruebas: fue que estaban escritas ruta por ruta. `test_app.py` comprobaba
la propiedad de `/vuelo/<nombre>` pero nadie escribió la de su hermana
`/vuelo/<nombre>/json`, y una prueba que no existe no falla.

Por eso la prueba que importa aquí no nombra ninguna ruta: recorre el mapa
de URLs de Flask. Una ruta nueva bajo `/vuelo/` que se olvide de comprobar
propiedad falla el día que se escriba, sin que nadie tenga que acordarse de
añadirla a ningún sitio.
"""
import sys
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

from app import app  # noqa: E402

FIXTURES = WEB_DIR.parent / "client" / "tests" / "fixtures"

#: El fixture `vuelo_eva18l.json` declara `pilot.license_id = EVA18L`.
DUENO = "EVA18L"
INTRUSO = "otro-piloto"
VUELO = "vuelo_eva18l.json"


@pytest.fixture(autouse=True)
def _altas_aisladas(tmp_path):
    """Las cuentas de los tests, a un temporal: `web/data/eva.db` no se toca."""
    from avcars import cuentas

    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "altas" / "usuarios.json")
    for piloto in (DUENO, INTRUSO):
        cuentas.crear_cuenta(piloto, "clave", f"{piloto.lower()}@ejemplo.test")
    yield
    cuentas.configurar_almacen(original)


@pytest.fixture(autouse=True)
def _solo_los_vuelos_de_fixtures(monkeypatch):
    """Que la app no vea las grabaciones reales de quien ejecute pytest."""
    import app as app_module

    monkeypatch.setattr(app_module, "SEARCH_DIRS", [FIXTURES])


@pytest.fixture
def cliente():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app.test_client()


def _como(cliente, piloto):
    with cliente.session_transaction() as sesion:
        sesion["user_id"] = piloto


def _rutas_de_un_vuelo():
    """Las rutas GET bajo `/vuelo/` que reciben el nombre de un vuelo.

    No hace falta excluir `/gestion/`: no cuelga de `/vuelo/`. Esas rutas
    llevan `@permiso_requerido` y **deben** ver los vuelos de todos.
    """
    encontradas = []
    for regla in app.url_map.iter_rules():
        ruta = str(regla)
        if not ruta.startswith("/vuelo/"):
            continue
        if "GET" not in (regla.methods or set()):
            continue
        if len(regla.arguments) != 1:
            continue
        encontradas.append((ruta, next(iter(regla.arguments))))
    return encontradas


def test_hay_rutas_de_vuelo_que_revisar():
    """Red de seguridad de la red de seguridad.

    Si un refactor cambiara el prefijo de las rutas, el test de abajo pasaría
    sin comprobar nada y nadie se enteraría. Este falla en ese caso.
    """
    assert _rutas_de_un_vuelo(), (
        "no se ha encontrado ninguna ruta /vuelo/<...>: revisar el filtro"
    )


def test_ninguna_ruta_de_vuelo_se_le_escapa_a_un_intruso(cliente):
    """La prueba que importa: se descubre sola las rutas.

    Comprobado el 2026-08-27 quitando el arreglo del IDOR: falla y nombra la
    ruta culpable.
    """
    _como(cliente, INTRUSO)

    filtradas = []
    for ruta, argumento in _rutas_de_un_vuelo():
        url = ruta.replace(f"<{argumento}>", VUELO)
        # Los conversores con tipo (`<int:id>`) no se sustituyen con el
        # patrón de arriba; si queda algún `<`, la ruta no es de esta clase.
        if "<" in url:
            continue
        if cliente.get(url).status_code == 200:
            filtradas.append(f"{url} -> 200")

    assert not filtradas, (
        "estas rutas devuelven el vuelo de otro piloto:\n  "
        + "\n  ".join(filtradas)
    )


def test_el_dueno_si_ve_su_vuelo_en_json(cliente):
    """La otra mitad: que la comprobación no se pase de celosa."""
    _como(cliente, DUENO)

    respuesta = cliente.get(f"/vuelo/{VUELO}/json")

    assert respuesta.status_code == 200
    assert respuesta.get_json()["pilot"]["license_id"] == DUENO


def test_otro_piloto_no_ve_el_json(cliente):
    """El fallo concreto del 2026-08-27, por si la genérica cambia de forma."""
    _como(cliente, INTRUSO)

    # 404 y no 403: a un piloto no se le confirma qué vuelos tienen los demás.
    assert cliente.get(f"/vuelo/{VUELO}/json").status_code == 404


def test_sin_sesion_tampoco(cliente):
    assert cliente.get(f"/vuelo/{VUELO}/json").status_code in (301, 302, 401, 403)


def test_la_comparacion_no_distingue_mayusculas(cliente):
    """El grabador escribe el indicativo como lo teclea el piloto.

    Un vuelo de `EVA18L` es del titular de la cuenta `eva18l`. Sin esto, un
    piloto no veía sus propios vuelos y no había forma de saber por qué.
    """
    _como(cliente, DUENO.lower())

    assert cliente.get(f"/vuelo/{VUELO}/json").status_code == 200
