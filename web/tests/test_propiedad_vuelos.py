"""Ningún piloto puede ver ni tocar el vuelo de otro.

Estas pruebas existen por el fallo del 2026-08-27: `/vuelo/<nombre>/json` se
quedó sin la comprobación de propiedad que sí tenían todas las demás rutas y
devolvía el `.avlog.json` entero de cualquiera —traza a 1 Hz, matrícula, plan—
a cualquiera con sesión abierta. Estuvo así días porque **no había ni una sola
prueba de las rutas web**.

Lo importante de este fichero no es el caso concreto, que ya está arreglado,
sino `test_ninguna_ruta_de_vuelo_se_le_escapa_a_un_intruso`: recorre las rutas
por sí mismo, así que una ruta nueva que se olvide de comprobar propiedad falla
aquí sin que nadie tenga que acordarse de añadir un test.
"""
from __future__ import annotations


def test_el_dueno_ve_su_vuelo_en_json(entorno):
    piloto = entorno["piloto"]
    entorno["como"](piloto)
    vuelo = entorno["ficheros"][piloto]

    r = entorno["cliente"].get(f"/vuelo/{vuelo}/json")

    assert r.status_code == 200
    assert r.get_json()["pilot"]["license_id"] == piloto


def test_otro_piloto_no_ve_ese_json(entorno):
    entorno["como"](entorno["otro"])
    ajeno = entorno["ficheros"][entorno["piloto"]]

    r = entorno["cliente"].get(f"/vuelo/{ajeno}/json")

    # 404 y no 403: a un piloto no se le confirma qué vuelos tienen los demás.
    assert r.status_code == 404


def test_otro_piloto_no_ve_la_ficha_del_vuelo(entorno):
    entorno["como"](entorno["otro"])
    ajeno = entorno["ficheros"][entorno["piloto"]]

    r = entorno["cliente"].get(f"/vuelo/{ajeno}")

    assert r.status_code == 404


def test_sin_sesion_no_se_llega_al_vuelo(entorno):
    """Sin sesión no hay 200 ni por asomo: redirige al login."""
    vuelo = entorno["ficheros"][entorno["piloto"]]

    r = entorno["cliente"].get(f"/vuelo/{vuelo}/json")

    assert r.status_code in (301, 302, 401, 403)


def test_la_comparacion_no_distingue_mayusculas(entorno):
    """El grabador escribe el indicativo como lo teclea el piloto.

    Un vuelo de `EVA001` es del titular de la cuenta `eva001`. Sin esto, un
    piloto no veía sus propios vuelos y no había forma de saber por qué.
    """
    piloto = entorno["piloto"]
    entorno["como"](piloto.lower())
    vuelo = entorno["ficheros"][piloto]

    r = entorno["cliente"].get(f"/vuelo/{vuelo}/json")

    assert r.status_code == 200


def test_la_cartilla_solo_lista_los_vuelos_propios(entorno):
    entorno["como"](entorno["piloto"])
    mio = entorno["ficheros"][entorno["piloto"]]
    ajeno = entorno["ficheros"][entorno["otro"]]

    r = entorno["cliente"].get("/vuelos")

    assert r.status_code == 200
    cuerpo = r.get_data(as_text=True)
    assert mio in cuerpo
    assert ajeno not in cuerpo


def test_un_vuelo_sin_dueno_no_se_le_ensena_a_nadie(entorno):
    """Es preferible que falte un vuelo antiguo a que lo vea quien no debe."""
    piloto = entorno["piloto"]
    grabaciones = entorno["grabaciones"]
    huerfano = "2026-08-27_11-00-00_HUERFANO.avlog.json"

    contenido = (grabaciones / entorno["ficheros"][piloto]).read_text(
        encoding="utf-8"
    )
    (grabaciones / huerfano).write_text(
        contenido.replace(f'"license_id": "{piloto}"', '"license_id": ""'),
        encoding="utf-8",
    )

    for quien in (piloto, entorno["otro"]):
        entorno["como"](quien)
        r = entorno["cliente"].get(f"/vuelo/{huerfano}/json")
        assert r.status_code == 404, f"{quien} ha visto un vuelo sin dueño"


def _rutas_de_un_vuelo(app):
    """Las rutas GET bajo `/vuelo/` que reciben el nombre de un vuelo.

    No hace falta excluir `/gestion/` porque no cuelga de `/vuelo/`: esas
    rutas llevan `@permiso_requerido` y **deben** ver los vuelos de todos.
    Solo se miran las de lectura; una prueba con POST tendría que lidiar con
    el CSRF y estaría midiendo otra cosa.
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


def test_hay_rutas_de_vuelo_que_revisar(entorno):
    """Red de seguridad de la red de seguridad.

    Si un refactor cambiara el prefijo de las rutas, el test de abajo pasaría
    sin comprobar nada y nadie se enteraría. Este falla en ese caso.
    """
    assert _rutas_de_un_vuelo(entorno["app"].app), (
        "no se ha encontrado ninguna ruta /vuelo/<...>: revisar el filtro"
    )


def test_ninguna_ruta_de_vuelo_se_le_escapa_a_un_intruso(entorno):
    """La prueba que importa: se descubre sola las rutas.

    Recorre el mapa de URLs de Flask en vez de llevar una lista escrita a
    mano. Una ruta nueva bajo `/vuelo/` que se olvide de comprobar propiedad
    falla aquí el día que se escriba, sin que nadie tenga que acordarse de
    añadirla a ningún sitio.

    Comprobado el 2026-08-27 quitando el arreglo del IDOR: esta prueba falla
    y nombra la ruta culpable.
    """
    entorno["como"](entorno["otro"])
    ajeno = entorno["ficheros"][entorno["piloto"]]

    filtradas = []
    for ruta, argumento in _rutas_de_un_vuelo(entorno["app"].app):
        url = ruta.replace(f"<{argumento}>", ajeno)
        # Los conversores con tipo (`<int:id>`) no se sustituyen con el
        # patrón de arriba; si queda algún `<`, la ruta no es de esta clase.
        if "<" in url:
            continue
        if entorno["cliente"].get(url).status_code == 200:
            filtradas.append(f"{url} -> 200")

    assert not filtradas, (
        "estas rutas devuelven el vuelo de otro piloto:\n  "
        + "\n  ".join(filtradas)
    )
