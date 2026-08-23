"""Tests del servidor de la cartilla.

Se ejecutan con:

    python -m pytest web/test_app.py

Lo que importa aquí es que el veredicto que sale por la web sea el mismo que
da el motor en local (es el mismo código, y así se verifica que sigue
siéndolo) y que no se pueda pedir un fichero de fuera de las carpetas.
"""
import re
import sys
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

from app import app, find_flights, load_flight, telemetry  # noqa: E402

FIXTURES = WEB_DIR.parent / "client" / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def _sesion_de_escritorio_aislada(tmp_path, monkeypatch):
    """El login escribe la sesión que lee EVA Dispatcher; aquí, a un temporal.

    Sin esto cada `pytest` dejaba `web/data/sesion_activa.json` en el repo, y
    el escritorio se habría encontrado una validación que no hizo nadie.
    """
    from avcars import sesion_web

    monkeypatch.setattr(sesion_web, "SESION_PATH", tmp_path / "sesion_activa.json")


@pytest.fixture(autouse=True)
def _altas_aisladas(tmp_path):
    """Las cuentas de los tests, a un temporal: `web/data/usuarios.json` no se toca.

    Los pilotos de los fixtures se dan de alta de verdad porque la sesión de
    alguien que no está en el almacén ya no vale (se le echa al login).
    """
    from avcars import cuentas

    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "altas" / "usuarios.json")
    for piloto in ("AVH-1001", "otro-piloto", "EVA18L"):
        cuentas.crear_cuenta(piloto, "clave", f"{piloto.lower()}@ejemplo.test")
    yield
    cuentas.configurar_almacen(original)


@pytest.fixture(autouse=True)
def _vuelos_de_fixtures(monkeypatch):
    """Los vuelos que ve la app en los tests: solo los del fixtures/, nunca
    los del equipo que ejecuta pytest.

    `SEARCH_DIRS` ya no incluye `fixtures/` en la app real (era ruido en el
    panel de admin); aquí se restringe a propósito para que estos tests
    sigan siendo deterministas y no dependan de qué haya en las carpetas de
    grabaciones reales de quien ejecuta la prueba.
    """
    import app as app_module

    monkeypatch.setattr(app_module, "SEARCH_DIRS", [FIXTURES])


@pytest.fixture
def sin_sesion():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app.test_client()


@pytest.fixture
def cliente(sin_sesion, monkeypatch):
    """Cliente con sesión de `pruebas`, dueño de los vuelos de ejemplo.

    Los fixtures son de otros pilotos (AVH-1001, EVA18L…), y la cartilla solo
    enseña a cada piloto los suyos. Estas pruebas van del **contenido** del
    informe, no de quién es el vuelo, así que aquí se le atribuyen al piloto
    de la sesión. El filtrado por piloto se prueba aparte, en
    `test_cada_piloto_solo_ve_sus_vuelos`.
    """
    import app as app_module

    _login(sin_sesion)
    monkeypatch.setattr(
        app_module, "dueno_del_vuelo", lambda _path: "pruebas"
    )
    return sin_sesion


@pytest.fixture
def cartilla_vacia(monkeypatch, tmp_path):
    """Sin vuelos en disco: para comprobar qué ve un piloto recién dado de alta."""
    import app as app_module

    monkeypatch.setattr(app_module, "SEARCH_DIRS", [tmp_path])
    return tmp_path


def test_cada_piloto_solo_ve_sus_vuelos(sin_sesion, monkeypatch):
    """Dos pilotos, dos cartillas: ninguno ve los vuelos del otro."""
    import app as app_module

    monkeypatch.setattr(app_module, "dueno_del_vuelo", lambda _p: "AVH-1001")

    with sin_sesion.session_transaction() as s:
        s["user_id"] = "AVH-1001"
    html_dueno = sin_sesion.get("/").get_data(as_text=True)

    with sin_sesion.session_transaction() as s:
        s["user_id"] = "otro-piloto"
    html_ajeno = sin_sesion.get("/").get_data(as_text=True)

    assert "sample_flight_pass.json" in html_dueno
    assert "sample_flight_pass.json" not in html_ajeno


def test_no_se_abre_el_vuelo_de_otro_piloto(sin_sesion, monkeypatch):
    """Y da 404, no 403: no se confirma qué vuelos tienen los demás."""
    import app as app_module

    monkeypatch.setattr(app_module, "dueno_del_vuelo", lambda _p: "AVH-1001")
    with sin_sesion.session_transaction() as s:
        s["user_id"] = "otro-piloto"

    assert sin_sesion.get("/vuelo/sample_flight_pass.json").status_code == 404


def test_un_vuelo_sin_dueno_no_se_le_ensena_a_nadie(sin_sesion, monkeypatch):
    """Preferible que falte un vuelo antiguo a que se cuele en otra cartilla."""
    import app as app_module

    monkeypatch.setattr(app_module, "dueno_del_vuelo", lambda _p: None)
    with sin_sesion.session_transaction() as s:
        s["user_id"] = "pruebas"

    assert "sample_flight_pass.json" not in sin_sesion.get("/").get_data(as_text=True)


def _login(cliente, user_id="pruebas", password="pruebas"):
    """Helper: autentica un usuario dado de alta (por defecto: pruebas)."""
    cliente.post(
        "/login",
        data={"user_id": user_id, "password": password},
        follow_redirects=True,
    )


def _veredicto(html: str) -> str:
    match = re.search(r'<div class="titulo">([^<]+)</div>', html)
    return match.group(1).strip() if match else ""


# -- listado -----------------------------------------------------------


def test_la_portada_responde(cliente):
    respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert "Cartilla EvA" in respuesta.get_data(as_text=True)


def test_se_encuentran_vuelos():
    assert find_flights(), "no se ha encontrado ningún vuelo de ejemplo"


# -- veredictos --------------------------------------------------------


def test_un_vuelo_correcto_sale_apto(cliente):
    respuesta = cliente.get("/vuelo/sample_flight_pass.json")

    assert respuesta.status_code == 200
    assert _veredicto(respuesta.get_data(as_text=True)) == "APTO"


def test_el_vuelo_eva18l_sale_no_evaluable(cliente):
    """42 minutos con un punto: no se aprueba por falta de pruebas."""
    respuesta = cliente.get("/vuelo/vuelo_eva18l.json")

    html = respuesta.get_data(as_text=True)
    assert _veredicto(html) == "NO EVALUABLE"
    assert "no permiten comprobar" in html


def test_un_vuelo_con_fallos_graves_sale_no_apto(cliente):
    respuesta = cliente.get("/vuelo/sample_flight_fail.json")

    assert _veredicto(respuesta.get_data(as_text=True)) in ("NO APTO", "NO EVALUABLE")


def test_el_perfil_se_puede_cambiar(cliente):
    respuesta = cliente.get("/vuelo/sample_flight_pass.json?perfil=hard")

    assert respuesta.status_code == 200
    assert "perfil hard" in respuesta.get_data(as_text=True)


def test_un_perfil_inventado_cae_al_normal(cliente):
    respuesta = cliente.get("/vuelo/sample_flight_pass.json?perfil=imposible")

    assert respuesta.status_code == 200
    assert "perfil normal" in respuesta.get_data(as_text=True)


# -- contenido del informe ---------------------------------------------


def test_el_informe_muestra_la_telemetria(cliente):
    html = cliente.get("/vuelo/sample_flight_pass.json").get_data(as_text=True)

    for etiqueta in ("Duración", "Distancia", "Alt. máxima", "Escora máx."):
        assert etiqueta in html


def test_el_informe_desglosa_los_criterios(cliente):
    html = cliente.get("/vuelo/sample_flight_pass.json").get_data(as_text=True)

    assert "Criterios superados" in html
    assert "Criterios no superados" in html
    assert "Criterios sin comprobar" in html


def test_se_puede_descargar_el_log_original(cliente):
    respuesta = cliente.get("/vuelo/sample_flight_pass.json/json")

    assert respuesta.status_code == 200
    assert respuesta.mimetype == "application/json"


# -- errores y seguridad -----------------------------------------------


def test_un_vuelo_inexistente_da_404(cliente):
    assert cliente.get("/vuelo/no_existe.json").status_code == 404


def test_no_se_puede_salir_de_las_carpetas(cliente):
    """Un nombre con rutas relativas no debe leer ficheros del sistema."""
    for intento in (
        "..%2f..%2fetc%2fpasswd",
        "....//....//etc//passwd",
        "%2Fetc%2Fpasswd",
    ):
        assert cliente.get(f"/vuelo/{intento}").status_code in (404, 308)


# -- telemetría --------------------------------------------------------


def test_la_telemetria_resume_el_vuelo():
    ruta = FIXTURES / "sample_flight_pass.json"
    flight = load_flight(ruta)
    assert flight is not None

    datos = telemetry(flight)

    assert datos["puntos"] == len(flight.track)
    assert datos["alt_max_ft"] > 0
    assert datos["gs_max_kt"] > 0


def test_un_fichero_que_no_es_un_log_devuelve_none(tmp_path):
    malo = tmp_path / "roto.avlog.json"
    malo.write_text("{no es json", encoding="utf-8")

    assert load_flight(malo) is None


# -- D2: planificador de vuelo ------------------------------------------


def test_la_pantalla_de_plan_responde_y_lista_la_flota_real(cliente):
    respuesta = cliente.get("/plan")

    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    # Los ocho aviones de aircraft.yaml, ninguno inventado en la plantilla.
    assert "Cessna 172 Skyhawk" in html
    assert "Daher TBM 930" in html


def test_la_api_de_aeropuerto_devuelve_coordenadas_reales(cliente):
    respuesta = cliente.get("/api/aeropuerto/LEMD")

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["icao"] == "LEMD"
    assert abs(datos["lat"] - 40.47223) < 0.01
    assert abs(datos["lon"] - (-3.56094)) < 0.01


def test_la_api_de_aeropuerto_no_inventa_uno_inexistente(cliente):
    respuesta = cliente.get("/api/aeropuerto/ZZZZ")
    assert respuesta.status_code == 404


def test_generar_fpl_usa_el_mismo_codigo_que_el_cliente_de_escritorio(cliente):
    """No se reimplementa el formato ICAO en la web: se llama a
    avcars.prefile.icao_fpl, el mismo código que usaría el cliente."""
    respuesta = cliente.post(
        "/api/plan/fpl",
        json={
            "callsign": "EVA01",
            "rules": "VFR",
            "departure": "LEMD",
            "arrival": "LEIB",
            "aircraft": "C172",
        },
    )

    assert respuesta.status_code == 200
    fpl = respuesta.get_json()["fpl"]
    assert fpl.startswith("(FPL-EVA01-VG")
    assert "-LEMD" in fpl
    assert "-LEIB" in fpl
    assert fpl.rstrip().endswith(")")


def test_generar_fpl_sin_indicativo_da_error_claro(cliente):
    respuesta = cliente.post(
        "/api/plan/fpl",
        json={"departure": "LEMD", "arrival": "LEIB"},
    )
    assert respuesta.status_code == 422


def test_generar_fpl_rechaza_icao_mal_formado(cliente):
    respuesta = cliente.post(
        "/api/plan/fpl",
        json={"callsign": "EVA01", "departure": "MADRID", "arrival": "LEIB"},
    )
    assert respuesta.status_code == 422


def test_la_pantalla_de_plan_pasa_las_estelas_conocidas(cliente):
    """Solo las que aircraft.yaml tiene de verdad (hoy C208 y C25C)."""
    html = cliente.get("/plan").get_data(as_text=True)
    assert '"C208": "L"' in html or "'C208': 'L'" in html or "C208" in html
    assert "ESTELAS" in html


def test_abrir_en_vatsim_devuelve_una_url_con_el_plan_relleno(cliente):
    """El botón «Abrir en VATSIM»: usa el mismo cuerpo que generar FPL,
    reutiliza vatsim_prefile_url, y no envía nada por su cuenta — solo
    construye el enlace para que el piloto lo revise."""
    respuesta = cliente.post(
        "/api/plan/vatsim-url",
        json={
            "callsign": "EVA01",
            "rules": "VFR",
            "departure": "LEMD",
            "arrival": "LEIB",
            "aircraft": "C172",
        },
    )
    assert respuesta.status_code == 200
    url = respuesta.get_json()["url"]
    assert url.startswith("https://my.vatsim.net/pilots/flightplan?")
    assert "raw=" in url


def test_abrir_en_vatsim_exige_indicativo_igual_que_generar_fpl(cliente):
    respuesta = cliente.post(
        "/api/plan/vatsim-url",
        json={"departure": "LEMD", "arrival": "LEIB"},
    )
    assert respuesta.status_code == 422


# -- D2: carga y peso -------------------------------------------


def test_la_pantalla_de_plan_pasa_los_datos_de_peso_mtow(cliente):
    """El semáforo de peso necesita MTOW + estimación de despacho."""
    html = cliente.get("/plan").get_data(as_text=True)
    assert "C172" in html
    assert "Daher TBM 930" in html
    assert 'id="semaforo-peso"' in html
    assert "DESPACHO" in html
    assert "PESO_COMBUSTIBLE_VACIO" not in html


def test_pantalla_de_plan_tiene_selector_de_carga_y_pasajeros(cliente):
    """La sección de carga debe estar visible con los controles necesarios."""
    html = cliente.get("/plan").get_data(as_text=True)
    assert 'id="pasajeros"' in html
    assert 'id="carga-kg"' in html
    assert 'id="tipo-carga"' in html
    assert 'id="semaforo-peso"' in html
    assert "Carga y pasajeros" in html
    assert "Combustible (plan)" in html
    assert "PESO_COMBUSTIBLE_VACIO" not in html
    assert '"C172"' in html
    assert '"oew_kg"' in html


def test_aplicar_payload_rechaza_valores_negativos(cliente):
    """El endpoint /api/plan/apply-payload rechaza pasajeros/carga negativos."""
    respuesta = cliente.post(
        "/api/plan/apply-payload",
        json={"passengers": -1, "cargo_kg": 0, "fuel_pct": 100},
    )
    assert respuesta.status_code == 422


def test_aplicar_payload_rechaza_combustible_fuera_de_rango(cliente):
    """Combustible debe estar entre 0 y 100 (%)."""
    for fuel_pct in (-1, 101, 150):
        respuesta = cliente.post(
            "/api/plan/apply-payload",
            json={"passengers": 0, "cargo_kg": 0, "fuel_pct": fuel_pct},
        )
        assert respuesta.status_code == 422


def test_aplicar_payload_no_finge_exito(cliente):
    """apply-payload es honesto: sin IPC simulador no devuelve éxito falso."""
    respuesta = cliente.post(
        "/api/plan/apply-payload",
        json={"passengers": 5, "cargo_kg": 500, "fuel_pct": 75},
    )
    assert respuesta.status_code == 503
    datos = respuesta.get_json()
    assert datos.get("success") is not True
    assert "no hay conexión con el simulador" in datos["error"]


# -- D3: Registro y telemetría -----------------------------------------------


def test_la_pantalla_de_registro_responde(cliente):
    """D3: Pantalla de registro de vuelos (requiere login)."""
    _login(cliente)
    respuesta = cliente.get("/registro")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert "Registro de Vuelos" in html or "registro" in html.lower()


def test_vuelos_muestra_los_grabados(cliente, cartilla_vacia):
    """La lista de vuelos vive en /vuelos desde el 2026-08-18.

    Antes `/registro` subía y listaba a la vez, y por eso «Registro» y
    «Vuelos» se pisaban en la barra. Ahora son dos pantallas.
    """
    _login(cliente)
    respuesta = cliente.get("/vuelos")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    # Sin vuelos, se dice, y se ofrece el camino para registrar uno.
    assert "No tiene vuelos registrados." in html
    assert 'href="/registro"' in html


def test_vuelos_enlaza_cada_tipo_a_su_ficha():
    """Un `.avlog.json` va a la cartilla completa; un `.csv`, a la ficha corta.

    `/vuelo/` evalúa el vuelo (veredicto, mapa, criterios) y solo sabe leer
    AVLOG. `/registro/` es la ficha de telemetría, y es lo único que se puede
    enseñar de un CSV de fstelemetry. Enlazar todo a `/registro/` dejaba al
    piloto viendo la ficha pobre de un vuelo que sí tenía cartilla.
    """
    def fila(archivo):
        return {"archivo": archivo, "fecha": archivo, "duracion_min": 1,
                "distancia_nm": 1, "alt_max_ft": 1, "gs_max_kt": 1, "puntos": 1}

    from flask import render_template

    with app.test_request_context("/vuelos"):
        html = render_template(
            "vuelos.html",
            vuelos=[fila("un_vuelo.avlog.json"), fila("20260816143000.csv")],
            total=2,
        )

    assert 'href="/vuelo/un_vuelo.avlog.json"' in html
    assert 'href="/registro/20260816143000.csv"' in html


def test_detalle_registro_renderiza_telemetria_correctamente(cliente):
    """D3: El template detalle_registro renderiza datos de CSV o AVLOG (requiere login)."""
    _login(cliente)
    # Probar con AVLOG (datos reales de vuelo)
    respuesta = cliente.get("/registro/2026-08-16_21-59-00_WVN89%209.avlog.json")

    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)

    # Verificar que no hay código Jinja2 sin renderizar
    assert "{{" not in html
    assert "}}" not in html

    # Verificar que contiene las estadísticas
    assert "Telemetría del Vuelo" in html
    assert "puntos grabados" in html

    # La gráfica es canvas propio, sin librerías de CDN: sin red no se queda en blanco.
    assert 'id="perfil"' in html
    assert "cdn.jsdelivr.net" not in html

    # Los datos de la gráfica viajan ya serializados en la página.
    assert '"alt"' in html
    assert '"gs"' in html


# -- Upload de CSV -----------------------------------------------------------


def test_registro_es_solo_subir(cliente):
    """/registro sube el fichero; ya no lista nada."""
    _login(cliente)
    respuesta = cliente.get("/registro")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)

    assert 'id="upload-area"' in html
    assert 'id="file-input"' in html
    assert "subirArchivo" in html
    assert "Registrar un vuelo" in html
    # La tabla de vuelos ya no está aquí.
    assert "Fecha y Hora" not in html


@pytest.fixture
def cartilla_aislada(tmp_path, monkeypatch):
    """Subidas contra carpetas de usar y tirar.

    Sin esto, cada `pytest` dejaba ficheros en la carpeta de grabaciones real
    del piloto y anotaba el vuelo en el registro de importados de verdad: la
    segunda ejecución se encontraba el vuelo ya importado y fallaba.
    """
    import importacion

    hogar = tmp_path / "hogar"
    (hogar / "EvA" / "grabaciones").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: hogar))
    monkeypatch.setattr(importacion, "REGISTRO_PATH", tmp_path / "importados.json")
    return hogar / "EvA" / "grabaciones"


def test_upload_csv_endpoint(cliente, cartilla_aislada):
    """El endpoint /api/registro/upload acepta archivos CSV (requiere login)."""
    _login(cliente)
    # Crear un archivo CSV de prueba
    csv_content = b"""PLANE_LATITUDE,PLANE_LONGITUDE,PLANE_ALTITUDE
40.47,-3.56,1200
40.48,-3.55,1800
"""

    from io import BytesIO
    csv_file = (BytesIO(csv_content), "20260816143000.csv")

    respuesta = cliente.post(
        "/api/registro/upload",
        data={"file": csv_file},
        content_type="multipart/form-data"
    )

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["success"] is True
    assert "20260816143000.csv" in datos["message"]
    assert (cartilla_aislada / "20260816143000.csv").exists()


def test_upload_rechaza_el_mismo_vuelo_dos_veces(cliente, cartilla_aislada):
    """Segunda subida del mismo contenido: 409 y ni un fichero más."""
    from io import BytesIO

    contenido = b"PLANE_LATITUDE,PLANE_LONGITUDE\n40.47,-3.56\n"

    def subir():
        return cliente.post(
            "/api/registro/upload",
            data={"file": (BytesIO(contenido), "vuelo.csv")},
            content_type="multipart/form-data",
        )

    assert subir().status_code == 200
    repetida = subir()
    assert repetida.status_code == 409
    assert repetida.get_json()["success"] is False
    assert len(list(cartilla_aislada.iterdir())) == 1


def test_upload_rechaza_el_vuelo_de_otro_piloto(cliente, cartilla_aislada):
    """El `.avlog.json` dice de quién es; `pruebas` no puede subir uno ajeno."""
    import json
    from io import BytesIO

    ajeno = json.dumps(
        {
            "pilot": {"license_id": "OTRO99", "callsign": "AHI1"},
            "integrity": {"track_hash": "huella-de-otro"},
            "track": [],
        }
    ).encode("utf-8")

    respuesta = cliente.post(
        "/api/registro/upload",
        data={"file": (BytesIO(ajeno), "ajeno.avlog.json")},
        content_type="multipart/form-data",
    )

    assert respuesta.status_code == 403
    assert "OTRO99" in respuesta.get_json()["message"]
    assert not list(cartilla_aislada.iterdir())


def test_upload_no_escribe_fuera_de_las_grabaciones(cliente, cartilla_aislada):
    """Un nombre con rutas se queda en el nombre a secas."""
    import json
    from io import BytesIO

    vuelo = json.dumps(
        {"pilot": {"license_id": "pruebas"}, "integrity": {"track_hash": "h1"}, "track": []}
    ).encode("utf-8")

    respuesta = cliente.post(
        "/api/registro/upload",
        data={"file": (BytesIO(vuelo), "../../../fuera.avlog.json")},
        content_type="multipart/form-data",
    )

    assert respuesta.status_code in (200, 400)
    if respuesta.status_code == 200:
        assert (cartilla_aislada / "fuera.avlog.json").exists()
    # En ningún caso debe haber salido nada de la carpeta.
    assert not list(cartilla_aislada.parent.parent.glob("*.avlog.json"))


# -- Login / Logout / Auth ---------------------------------------------------


def test_login_muestra_formulario(sin_sesion):
    """GET /login muestra el formulario de login."""
    respuesta = sin_sesion.get("/login")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert 'name="user_id"' in html
    assert 'name="password"' in html


def test_login_rechaza_usuario_no_dado_de_alta(sin_sesion):
    """Un ID que no está en el fichero de altas no entra ni se registra solo."""
    respuesta = sin_sesion.post(
        "/login",
        data={"user_id": "NUEVO99", "password": "secreto"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert respuesta.request.path == "/login"
    html = respuesta.get_data(as_text=True)
    assert "no está dado de alta" in html
    # Y se le dice qué hacer: pedir el alta, que aprueba el responsable.
    assert "/solicitar-alta" in html


def test_login_autentica_usuario_existente(sin_sesion):
    """Usuario dado de alta: autentica con credenciales correctas."""
    respuesta = sin_sesion.post(
        "/login",
        data={"user_id": "pruebas", "password": "pruebas"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    # Desde el 2026-08-19 se aterriza en la home de la aerolínea.
    assert respuesta.request.path == "/aerolinea"


def test_login_rechaza_contraseña_incorrecta(sin_sesion):
    """Usuario dado de alta con contraseña incorrecta recibe error."""
    respuesta = sin_sesion.post(
        "/login",
        data={"user_id": "pruebas", "password": "incorrecta"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert "Contraseña incorrecta" in html


def test_logout_limpia_sesion(cliente):
    """Logout elimina la sesión y redirige a login."""
    respuesta = cliente.get("/logout", follow_redirects=True)
    assert respuesta.status_code == 200
    respuesta2 = cliente.get("/registro")
    assert respuesta2.status_code == 302
    assert "/login" in respuesta2.headers.get("Location", "")
    respuesta3 = cliente.get("/")
    assert respuesta3.status_code == 302
    assert "/login" in respuesta3.headers.get("Location", "")


def test_registro_requiere_login(sin_sesion):
    """Sin sesión, /registro redirige a /login."""
    respuesta = sin_sesion.get("/registro")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers.get("Location", "")


def test_upload_requiere_login(sin_sesion):
    """Sin sesión, /api/registro/upload redirige a /login."""
    from io import BytesIO
    csv_file = (BytesIO(b"col1,col2\n1,2\n"), "test.csv")
    respuesta = sin_sesion.post(
        "/api/registro/upload",
        data={"file": csv_file},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers.get("Location", "")


def test_portada_requiere_login(sin_sesion):
    respuesta = sin_sesion.get("/")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers.get("Location", "")


def test_plan_requiere_login(sin_sesion):
    respuesta = sin_sesion.get("/plan")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers.get("Location", "")


def test_vuelo_requiere_login(sin_sesion):
    respuesta = sin_sesion.get("/vuelo/sample_flight_pass.json")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers.get("Location", "")


def test_api_plan_requiere_login(sin_sesion):
    respuesta = sin_sesion.get("/api/aeropuerto/LEMD")
    assert respuesta.status_code == 302
    assert "/login" in respuesta.headers.get("Location", "")
    respuesta = sin_sesion.post("/api/plan/fpl", json={})
    assert respuesta.status_code == 302


# -- W1: Mapa de vuelo ---------------------------------------------------


def test_detalle_vuelo_contiene_mapa(cliente):
    """W1: La página de detalle incluye el contenedor del mapa Leaflet."""
    respuesta = cliente.get("/vuelo/sample_flight_pass.json")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert 'id="mapa-vuelo"' in html
    assert "leaflet" in html.lower()
    assert "L.map" in html


def test_mapa_tiene_datos_de_ruta(cliente):
    """W1: El mapa recibe datos de ruta con lat/lon del track."""
    respuesta = cliente.get("/vuelo/sample_flight_pass.json")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    # Los datos del mapa se inyectan como JSON en el script
    assert "mapaDatos" in html
    assert "route" in html


def test_map_data_extrae_ruta_y_bounds():
    """W1: map_data() devuelve ruta, bounds, aeropuertos e incidencias."""
    from app import map_data
    from avcars.evaluation.scoring import Verdict

    ruta = FIXTURES / "sample_flight_pass.json"
    flight = load_flight(ruta)
    assert flight is not None

    # Crear un verdict dummy para la prueba
    verdict = Verdict(
        score=85,
        passed=True,
        failed_hard=[],
        items=[],
        not_evaluated=[],
    )

    datos = map_data(flight, verdict)
    assert "route" in datos
    assert len(datos["route"]) > 0
    assert "bounds" in datos
    assert "lat_min" in datos["bounds"]
    assert "airports" in datos
    # Debe tener la estructura correcta (puede estar vacío si ICAO no conocido)
    assert isinstance(datos["airports"], dict)


# -- OC-02: Scrubbing sincronizado + ruta planificada --------------------------


def test_detalle_vuelo_tiene_scrubbing_sincronizado(cliente):
    """OC-02: El mapa y la gráfica comparten _scrubState para scrubbing bidireccional."""
    respuesta = cliente.get("/vuelo/sample_flight_pass.json")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    # El estado compartido de scrubbing debe existir
    assert "_scrubState" in html
    assert "onScrub" in html


def test_detalle_vuelo_muestra_ruta_planificada(cliente):
    """OC-02: La ruta planificada (aprox.) se renderiza como polyline discontinua naranja en el mapa."""
    respuesta = cliente.get("/vuelo/sample_flight_pass.json")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    # La ruta planificada se inyecta como JSON y se dibuja como polyline
    assert "rutaPlan" in html
    assert "f59e0b" in html  # color naranja de la ruta planificada


def test_planned_route_points_extrae_waypoints():
    """OC-02: planned_route_points() resuelve ICAO de la ruta del FPL contra airports.json."""
    from app import planned_route_points

    ruta = FIXTURES / "sample_flight_pass.json"
    flight = load_flight(ruta)
    assert flight is not None

    puntos = planned_route_points(flight)
    assert isinstance(puntos, list)
    # Al menos salida y llegada deben aparecer
    if flight.flight_plan.departure_icao:
        icaos = [p["icao"] for p in puntos]
        assert flight.flight_plan.departure_icao.upper() in icaos


def test_chart_points_incluye_lat_lon():
    """OC-02: chart_points() incluye lat/lon para sincronización con mapa."""
    from app import chart_points

    ruta = FIXTURES / "sample_flight_pass.json"
    flight = load_flight(ruta)
    assert flight is not None

    datos = chart_points(flight)
    assert "lat" in datos
    assert "lon" in datos
    assert len(datos["lat"]) == len(datos["t"])
    assert len(datos["lon"]) == len(datos["t"])
    # Si hay track, las coordenadas deben ser razonables (no todas cero)
    if datos["t"]:
        assert any(lat != 0 for lat in datos["lat"])


def test_detalle_vuelo_cursor_scrub_dibuja_crosshair(cliente):
    """OC-02: La gráfica tiene la lógica de dibujar crosshair de scrubbing sobre la serie."""
    respuesta = cliente.get("/vuelo/sample_flight_pass.json")
    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    # Sincronización gráfica ↔ mapa: _scrubState, mousemove, mouseleave
    assert "_scrubState" in html
    assert "mousemove" in html
    assert "mouseleave" in html


# -- OC-04: Barra lateral (base.html) --------------------------------------


def test_la_barra_lateral_tiene_los_destinos_del_mapa(cliente):
    """OC-04: las etiquetas de la barra.

    Actualizado el 2026-08-18: el humano renombró la carpeta a VUELOS (sus
    vuelos grabados) y pidió una entrada nueva, PLANES DE VUELO, para los
    planes que guarda el botón GUARDAR del planificador (D3, ya construido).
    """
    html = cliente.get("/").get_data(as_text=True)
    assert ">PLAN</a>" in html
    assert ">VUELO</a>" in html
    assert ">VUELOS</a>" in html
    assert ">PLANES DE VUELO</a>" in html
    assert ">REGISTRO</a>" in html


def test_planes_de_vuelo_enlaza_a_su_pantalla(cliente):
    html = cliente.get("/").get_data(as_text=True)
    assert 'href="/planes-de-vuelo"' in html


def test_plan_apunta_a_la_ruta_d2(cliente):
    """OC-04: PLAN enlaza al planificador (/plan, D2)."""
    html = cliente.get("/").get_data(as_text=True)
    assert 'href="/plan"' in html


def test_desde_el_servidor_no_se_ofrece_lanzar_el_grabador(cliente):
    """D4 es la app de escritorio: desde la web no se puede lanzar,

    salvo que el servidor esté en modo desarrollo y la petición sea local
    (ver `se_puede_lanzar_en_local` en app.py) — el fixture `cliente` no
    cumple ninguna de las dos condiciones por defecto.

    Antes, en ese caso, el icono VUELO quedaba muerto y no llevaba a ningún
    sitio. Ahora lleva a la página de descarga, que es lo que le hace falta a
    un piloto que entra desde su casa: bajarse el programa. Lo que no puede
    aparecer en ningún caso es el control de lanzar.
    """
    html = cliente.get("/").get_data(as_text=True)
    assert 'id="lanzar-vuelo"' not in html
    assert 'href="/descargar"' in html
    assert "pendiente de construir" not in html


def test_registro_apunta_a_subir_un_vuelo(cliente):
    """REGISTRO lleva a subir el fichero; la lista es VUELOS."""
    html = cliente.get("/").get_data(as_text=True)
    assert 'href="/registro"' in html
    assert 'href="/vuelos"' in html


def test_el_detalle_reapunta_registro_a_la_lista(cliente):
    """OC-04: En el detalle, REGISTRO lleva a /registro, no al índice."""
    html = cliente.get(
        "/registro/2026-08-16_21-59-00_WVN89%209.avlog.json"
    ).get_data(as_text=True)
    assert 'href="/registro"' in html


def test_el_enlace_de_usuarios_solo_lo_ve_el_admin(cliente, sin_sesion):
    """OC-04: USUARIOS sale por permiso (rol admin), no por nombre de usuario."""
    # `pruebas` es admin (semilla): sí ve el enlace.
    admin_html = cliente.get("/").get_data(as_text=True)
    assert 'href="/gestion/usuarios"' in admin_html

    # Un piloto normal (AVH-1001) no lo ve, aunque esté logado.
    _login(sin_sesion, user_id="AVH-1001", password="clave")
    piloto_html = sin_sesion.get("/").get_data(as_text=True)
    assert 'href="/gestion/usuarios"' not in piloto_html


def test_el_enlace_de_todos_los_vuelos_tambien_solo_lo_ve_el_admin(cliente, sin_sesion):
    """Igual que USUARIOS: por permiso, no por nombre."""
    admin_html = cliente.get("/").get_data(as_text=True)
    assert 'href="/gestion/vuelos"' in admin_html

    _login(sin_sesion, user_id="AVH-1001", password="clave")
    piloto_html = sin_sesion.get("/").get_data(as_text=True)
    assert 'href="/gestion/vuelos"' not in piloto_html


def test_la_seccion_activa_se_marca_por_plantilla(cliente):
    """OC-04: Cada pantalla marca 'activo' su sección con los bloques nav_*."""
    # En /plan, PLAN queda activo.
    plan = cliente.get("/plan").get_data(as_text=True)
    assert 'href="/plan" class="activo"' in plan

    # La portada es la cartilla: pertenece a VUELOS.
    for destino in ("/", "/vuelos"):
        html = cliente.get(destino).get_data(as_text=True)
        assert 'href="/vuelos" class="activo"' in html

    # Y /registro marca REGISTRO.
    registro = cliente.get("/registro").get_data(as_text=True)
    assert 'href="/registro" class="activo"' in registro

    # En la gestión, USUARIOS queda activo.
    gestion = cliente.get("/gestion/usuarios").get_data(as_text=True)
    assert 'href="/gestion/usuarios" class="activo"' in gestion


# -- OC-05: aeródromos ES + Vuelta a España VFR ---------------------------------


@pytest.fixture
def oc05_datos():
    """Siembra en la BD temporal del test las tablas _es y la Vuelta a España.

    El autouse `_altas_aisladas` ya repuntó `cuentas.DB_PATH` al temporal,
    así que la migración y la importación nunca tocan `web/data/eva.db`.
    """
    from avcars import cuentas
    import migrar_aerodromos_es
    import importar_vuelta_espana

    migrar_aerodromos_es.migrar(dst=cuentas.DB_PATH)
    importar_vuelta_espana.importar(dst=cuentas.DB_PATH)
    return cuentas.DB_PATH


def test_aerodromos_es_migrados(cliente, oc05_datos):
    """Las tablas _es existen y tienen datos en la BD temporal."""
    from avcars import cuentas

    with cuentas.conexion() as con:
        n = con.execute("SELECT COUNT(*) FROM aerodromos_es").fetchone()[0]
    assert n >= 800


def test_info_aeropuerto_prefiere_aerodromos_es(cliente, oc05_datos):
    """LEMD devuelve datos enriquecidos desde aerodromos_es (no fallback)."""
    from app import info_aeropuerto

    info = info_aeropuerto("LEMD")
    assert info.get("lat") is not None
    assert info.get("lon") is not None


def test_info_aeropuerto_fallback_global(cliente, oc05_datos):
    """Un aeropuerto no español (KJFK) cae en airports.json (fallback)."""
    from app import info_aeropuerto

    info = info_aeropuerto("KJFK")
    assert info.get("name")


def test_rutas_vfr_importadas(cliente, oc05_datos):
    """La Vuelta a España 2026 queda con 21 etapas."""
    from avcars import cuentas

    with cuentas.conexion() as con:
        n = con.execute(
            "SELECT COUNT(*) FROM rutas_vfr WHERE route_id = 'vae-2026'"
        ).fetchone()[0]
    assert n == 21


def _avlog_etapa(origen, destino, huella):
    """Vuelo AVLOG sintético LXGB→LEMG basado en el fixture real WVN89."""
    import json

    fixture = (
        Path(__file__).resolve().parent.parent
        / "client" / "tests" / "fixtures"
        / "2026-08-16_21-59-00_WVN89 9.avlog.json"
    )
    doc = json.loads(fixture.read_text(encoding="utf-8"))
    doc["pilot"] = {"license_id": "pruebas", "callsign": "OC05"}
    doc["flight_plan"]["departure_icao"] = origen
    doc["flight_plan"]["arrival_icao"] = destino
    doc["integrity"] = {"hash_algorithm": "sha256", "track_hash": huella}
    return json.dumps(doc).encode("utf-8")


def test_progreso_ruta_detectado(cliente, oc05_datos, cartilla_aislada):
    """Subir un vuelo LXGB→LEMG completa la etapa en progreso_rutas."""
    from io import BytesIO

    from avcars import cuentas

    with cuentas.conexion() as con:
        ruta = con.execute(
            "SELECT id FROM rutas_vfr WHERE origin_icao='LXGB' AND destination_icao='LEMG'"
        ).fetchone()
    assert ruta is not None

    _login(cliente)
    contenido = _avlog_etapa("LXGB", "LEMG", "h-oc05-1")
    respuesta = cliente.post(
        "/api/registro/upload",
        data={"file": (BytesIO(contenido), "etapa01.avlog.json")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 200

    with cuentas.conexion() as con:
        filas = con.execute(
            "SELECT * FROM progreso_rutas WHERE license_id='pruebas' AND ruta_id=?",
            (ruta["id"],),
        ).fetchall()
    assert len(filas) == 1
    assert filas[0]["estado"] == "completada"
    assert filas[0]["vuelo_huella"] == "h-oc05-1"


def test_progreso_ruta_no_duplica(cliente, oc05_datos, cartilla_aislada):
    """Volver a volar la misma etapa no duplica el progreso."""
    from io import BytesIO

    from avcars import cuentas

    with cuentas.conexion() as con:
        ruta = con.execute(
            "SELECT id FROM rutas_vfr WHERE origin_icao='LXGB' AND destination_icao='LEMG'"
        ).fetchone()
    assert ruta is not None

    _login(cliente)
    for huella in ("h-oc05-2", "h-oc05-3"):
        contenido = _avlog_etapa("LXGB", "LEMG", huella)
        respuesta = cliente.post(
            "/api/registro/upload",
            data={"file": (BytesIO(contenido), f"{huella}.avlog.json")},
            content_type="multipart/form-data",
        )
        assert respuesta.status_code == 200

    with cuentas.conexion() as con:
        filas = con.execute(
            "SELECT * FROM progreso_rutas WHERE license_id='pruebas' AND ruta_id=?",
            (ruta["id"],),
        ).fetchall()
    assert len(filas) == 1
    assert filas[0]["vuelo_huella"] == "h-oc05-2"
