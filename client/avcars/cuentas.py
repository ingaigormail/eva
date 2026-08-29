"""Altas EvA compartidas entre escritorio (D1) y web.

Los datos viven en **SQLite** (`web/data/eva.db`), no en JSON. El motivo es la
concurrencia: reescribir un fichero entero en cada cambio funciona en un
portátil con un proceso, pero en un servidor con varios *workers* dos
escrituras a la vez se pisan y una se pierde sin avisar. Con cuentas de
usuario eso significa perder un alta o resucitar a alguien bloqueado. SQLite
da transacciones y bloqueo, y sigue siendo un fichero que se copia: sin
servidor, sin credenciales y sin dependencias (viene en la biblioteca
estándar).

El `usuarios.json` de antes **se importa solo** la primera vez y se conserva
renombrado a `usuarios.json.migrado`. Nadie pierde su cuenta.

Cada cuenta tiene contraseña, correo, estado (activa/bloqueada) y rol. Los
permisos se resuelven **por rol**, nunca comprobando el nombre del usuario:
añadir otro administrador es cambiarle el rol, no tocar la lógica.

Sin Flask ni Werkzeug, para que el cliente de escritorio pueda validar igual.
No hay auto-registro: quien no esté en la base no entra. El alta se solicita
(ver `/solicitar-alta` en la web) y la concede un administrador.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# client/avcars/cuentas.py → raíz del repo → web/data/
_DIRECTORIO_POR_DEFECTO = Path(__file__).resolve().parents[2] / "web" / "data"

# El almacén de verdad.
DB_PATH = _DIRECTORIO_POR_DEFECTO / "eva.db"
# El fichero de antes: solo se lee una vez, para importarlo.
USUARIOS_PATH = _DIRECTORIO_POR_DEFECTO / "usuarios.json"

USUARIO_PRUEBAS = "pruebas"
PASSWORD_PRUEBAS = "pruebas"

# -- Estados ---------------------------------------------------------------
ESTADO_ACTIVA = "activa"
ESTADO_BLOQUEADA = "bloqueada"
ESTADOS = (ESTADO_ACTIVA, ESTADO_BLOQUEADA)

# -- Roles y permisos ------------------------------------------------------
ROL_ADMIN = "admin"
ROL_PILOTO = "piloto"
ROLES = (ROL_ADMIN, ROL_PILOTO)

PERM_VOLAR = "volar"
PERM_GESTIONAR_USUARIOS = "gestionar_usuarios"

PERMISOS_POR_ROL: dict[str, frozenset[str]] = {
    ROL_ADMIN: frozenset({PERM_VOLAR, PERM_GESTIONAR_USUARIOS}),
    ROL_PILOTO: frozenset({PERM_VOLAR}),
}

# -- Categoría de piloto (progresión P0-P4) --------------------------------
#
# No hay examen ni conteo de horas automático que la mueva: el admin la
# asigna a mano en /gestion/usuarios, igual que ya hace con el rol. Guardada
# como texto validado contra esta lista, no como columna aparte por nivel —
# añadir un P5 el día de mañana es una entrada nueva aquí, no una migración.
CATEGORIA_P0 = "P0"
CATEGORIA_P1 = "P1"
CATEGORIA_P2 = "P2"
CATEGORIA_P3 = "P3"
CATEGORIA_P4 = "P4"
CATEGORIAS = (CATEGORIA_P0, CATEGORIA_P1, CATEGORIA_P2, CATEGORIA_P3, CATEGORIA_P4)

#: Nombre y siglas para pintar la insignia, en el mismo orden que CATEGORIAS.
#: No lleva color aquí: el color/SVG de cada insignia vive en la plantilla
#: (es presentación, no un dato del piloto).
CATEGORIA_INFO: dict[str, dict[str, str]] = {
    CATEGORIA_P0: {"nombre": "New Member", "siglas": "Miembro nuevo"},
    CATEGORIA_P1: {"nombre": "Private Pilot", "siglas": "PPL"},
    CATEGORIA_P2: {"nombre": "Instrument Rating", "siglas": "IR"},
    CATEGORIA_P3: {"nombre": "Commercial Multi-Engine", "siglas": "CMEL"},
    CATEGORIA_P4: {"nombre": "Airline Transport Pilot", "siglas": "ATPL"},
}

# -- Resultados de autenticación ------------------------------------------
AUTH_OK = "ok"
AUTH_DESCONOCIDO = "desconocido"
AUTH_PASSWORD = "password"
AUTH_BLOQUEADA = "bloqueada"

_PREFIJO = "pbkdf2_sha256$"
_ITERACIONES = 260_000

# Suficiente para descartar lo que no es una dirección: un `@`, sin espacios y
# un dominio con punto. La validación de verdad es que llegue el correo.
_CORREO_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    license_id  TEXT PRIMARY KEY,
    password    TEXT NOT NULL,
    correo      TEXT NOT NULL DEFAULT '',
    estado      TEXT NOT NULL DEFAULT 'activa',
    rol         TEXT NOT NULL DEFAULT 'piloto',
    -- Progresión P0-P4 (ver CATEGORIAS). Todo piloto nuevo entra en P0; el
    -- admin lo va subiendo a mano desde /gestion/usuarios.
    categoria   TEXT NOT NULL DEFAULT 'P0',
    -- CID de VATSIM (numérico, como texto): para cruzar la actividad de
    -- VATSIM del piloto contra su cuenta de EvA. Vacío si no lo dio en la
    -- solicitud o no vuela en VATSIM.
    vatsim_cid  TEXT NOT NULL DEFAULT '',
    -- Huella (SHA-256) de la clave con la que EvA Airliner lee el plan de
    -- vuelo del piloto desde el servidor. No es una contraseña: es un valor
    -- aleatorio largo que se genera aquí y se enseña UNA vez, así que no
    -- necesita el KDF lento de `_hashear` (ese es para secretos que elige
    -- una persona, que tienen poca entropía). Vacío = sin clave.
    clave_grabador TEXT NOT NULL DEFAULT '',
    creado      TEXT NOT NULL,
    actualizado TEXT NOT NULL
);

-- El índice de `clave_grabador` NO va aquí: en una base que ya existe,
-- `CREATE TABLE IF NOT EXISTS` no añade la columna, y un `CREATE INDEX`
-- sobre una columna que aún no está revienta el arranque entero. Se crea en
-- `_migrar_esquema`, que es quien se asegura primero de que la columna
-- exista, tanto en bases nuevas como en las de siempre.

-- El correo no se repite, pero las cuentas antiguas no tienen ninguno y
-- deben poder convivir: por eso el índice deja fuera la cadena vacía.
CREATE UNIQUE INDEX IF NOT EXISTS usuarios_correo_unico
    ON usuarios (correo) WHERE correo <> '';

CREATE TABLE IF NOT EXISTS testigos (
    huella     TEXT PRIMARY KEY,
    license_id TEXT NOT NULL,
    creado     TEXT NOT NULL,
    caduca     TEXT NOT NULL
);

-- Peticiones de alta. Una solicitud NO es una cuenta: aquí no hay
-- contraseña ni la habrá. Se guardan para que perder el correo del aviso no
-- signifique perder al piloto que quería entrar.
CREATE TABLE IF NOT EXISTS solicitudes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    license_id   TEXT NOT NULL,
    nombre       TEXT NOT NULL,
    -- `discord` se deja de pedir en el formulario (sustituido por
    -- vatsim_cid); la columna se conserva sin usar para no perder el dato
    -- de solicitudes antiguas que ya lo traían.
    discord      TEXT NOT NULL DEFAULT '',
    vatsim_cid   TEXT NOT NULL DEFAULT '',
    correo       TEXT NOT NULL,
    creado       TEXT NOT NULL,
    estado       TEXT NOT NULL DEFAULT 'pendiente',
    resuelta_por TEXT NOT NULL DEFAULT '',
    resuelta_en  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS solicitudes_estado ON solicitudes (estado);

-- Planes de vuelo guardados (D3). Son del piloto que los guardó y solo él
-- los ve. El plan entero va en `datos` tal como lo arma el planificador; las
-- columnas sueltas son para poder listarlos sin abrir el JSON.
CREATE TABLE IF NOT EXISTS planes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    license_id  TEXT NOT NULL,
    callsign    TEXT NOT NULL DEFAULT '',
    origen      TEXT NOT NULL DEFAULT '',
    destino     TEXT NOT NULL DEFAULT '',
    alterno     TEXT NOT NULL DEFAULT '',
    aeronave    TEXT NOT NULL DEFAULT '',
    nivel       TEXT NOT NULL DEFAULT '',
    ruta        TEXT NOT NULL DEFAULT '',
    -- Con cuál de los tres botones se guardó: 'vatsim' | 'sin_vatsim' | 'icao'.
    -- Así el piloto (y quien puntúe) sabe cómo se declaró ese vuelo, no solo
    -- qué contenía. '' en planes de antes de que existiera esta columna.
    via         TEXT NOT NULL DEFAULT '',
    datos       TEXT NOT NULL,
    creado      TEXT NOT NULL,
    actualizado TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS planes_piloto ON planes (license_id);

-- Un resumen por cada vuelo que entra en una cartilla (Home de la aerolínea).
-- Una fila por `huella` (la misma que usa importacion.py): no se duplica
-- aunque el vuelo se reimporte con otro nombre. `calidad` es NULL para los
-- .csv, que hoy no pasan por el motor de evaluación — no se les inventa un
-- veredicto que no existe.
--
-- 2026-08-18: se ensancha con datos que YA graba el cliente pero que hasta
-- ahora se tiraban al integrar el vuelo (combustible, matrícula, red, reglas,
-- perfil de evaluación). Deliberadamente NO lleva pasajeros, carga, equipaje
-- ni coste de combustible: ese dato no existe en ningún sitio del proyecto
-- todavía (ni en el grabador ni en el esquema del vuelo). Añadir una columna
-- para un dato que no se captura sería inventarlo; el hueco se abre aquí sin
-- coste el día que el grabador empiece a guardarlo.
CREATE TABLE IF NOT EXISTS vuelos_resumen (
    huella           TEXT PRIMARY KEY,
    license_id       TEXT NOT NULL,
    callsign         TEXT NOT NULL DEFAULT '',
    origen           TEXT NOT NULL DEFAULT '',
    destino          TEXT NOT NULL DEFAULT '',
    aeronave         TEXT NOT NULL DEFAULT '',
    matricula        TEXT NOT NULL DEFAULT '',
    reglas           TEXT NOT NULL DEFAULT '',   -- 'VFR' | 'IFR'
    red              TEXT NOT NULL DEFAULT '',   -- 'VATSIM' | 'IVAO' | 'OFFLINE'
    control_atc      INTEGER,                    -- 1/0/NULL: bajo control ATC
    distancia_nm     REAL NOT NULL DEFAULT 0,
    duracion_min     REAL NOT NULL DEFAULT 0,
    combustible_usado_kg     REAL,               -- NULL si el vuelo no lo trae
    combustible_restante_kg  REAL,
    calidad          TEXT,               -- 'apto' | 'no_apto' | 'no_evaluable' | NULL
    puntuacion       INTEGER,            -- score del veredicto; NULL si no evaluable
    perfil_evaluacion TEXT NOT NULL DEFAULT '',   -- con qué perfil se evaluó (easy/normal/hard)
    incidencias      TEXT NOT NULL DEFAULT '[]',  -- JSON: nombres de reglas falladas
    fecha            TEXT NOT NULL,      -- fecha del vuelo (para "hoy" y el mensual)
    creado           TEXT NOT NULL       -- cuándo se integró a la cartilla
);

CREATE INDEX IF NOT EXISTS vuelos_resumen_piloto ON vuelos_resumen (license_id);
CREATE INDEX IF NOT EXISTS vuelos_resumen_fecha ON vuelos_resumen (fecha);
"""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def directorio_datos() -> Path:
    """Dónde viven la base y sus vecinos (correo.json, secret_key.txt…)."""
    return DB_PATH.parent


# -- Conexión --------------------------------------------------------------


#: Si ya se preparó el esquema/semilla contra el `DB_PATH` actual. Perezoso a
#: propósito: si se inicializara al importar el módulo, cualquier proceso que
#: solo *importe* `avcars.cuentas` — un test, una comprobación rápida —
#: tocaría `web/data/eva.db` de verdad antes de que nadie tuviera ocasión de
#: redirigirlo con `configurar_almacen()`. Así pasó el 2026-08-18: quedó una
#: tabla con el esquema antiguo en la base real, creada por un `pytest` que
#: solo pretendía probar contra un directorio temporal.
_inicializado = False


def _asegurar_inicializado() -> None:
    global _inicializado
    if _inicializado:
        return
    # Se marca antes de ejecutar: `_asegurar_esquema()` abre su propia
    # conexión y volvería a pasar por aquí; sin esto sería recursión infinita.
    _inicializado = True
    _asegurar_esquema()
    _migrar_esquema()
    _importar_json_si_hace_falta()
    _asegurar_semilla()


@contextmanager
def conexion():
    """Una conexión corta por operación, con la transacción cerrada al salir.

    `timeout` para que dos escrituras a la vez esperen en vez de fallar, y WAL
    para que leer no bloquee a quien escribe.
    """
    _asegurar_inicializado()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        with con:
            yield con
    finally:
        con.close()


def _asegurar_esquema() -> None:
    with conexion() as con:
        con.executescript(_ESQUEMA)


def _migrar_esquema() -> None:
    """Añade columnas nuevas a tablas que ya existían sin ellas.

    `CREATE TABLE IF NOT EXISTS` no toca una tabla que ya está creada, así
    que una base de datos real (con planes guardados de antes) se queda sin
    la columna nueva si solo se confía en `_ESQUEMA`. Esto se ejecuta
    siempre; `ALTER TABLE ADD COLUMN` es barato y solo actúa si falta.
    """
    with conexion() as con:
        columnas = {fila["name"] for fila in con.execute("PRAGMA table_info(planes)")}
        if "via" not in columnas:
            con.execute("ALTER TABLE planes ADD COLUMN via TEXT NOT NULL DEFAULT ''")

        columnas_usuarios = {
            fila["name"] for fila in con.execute("PRAGMA table_info(usuarios)")
        }
        if "categoria" not in columnas_usuarios:
            con.execute(
                "ALTER TABLE usuarios ADD COLUMN categoria TEXT NOT NULL DEFAULT 'P0'"
            )
        if "vatsim_cid" not in columnas_usuarios:
            con.execute(
                "ALTER TABLE usuarios ADD COLUMN vatsim_cid TEXT NOT NULL DEFAULT ''"
            )
        if "clave_grabador" not in columnas_usuarios:
            con.execute(
                "ALTER TABLE usuarios ADD COLUMN clave_grabador TEXT NOT NULL DEFAULT ''"
            )
        # Fuera del `if`: la columna puede existir ya (base recién creada por
        # `_ESQUEMA`) y aun así faltar el índice. Buscar al piloto por su
        # clave tiene que ser un `SELECT` directo, no recorrer la tabla.
        con.execute(
            "CREATE INDEX IF NOT EXISTS usuarios_clave_grabador "
            "ON usuarios (clave_grabador) WHERE clave_grabador <> ''"
        )

        columnas_solicitudes = {
            fila["name"] for fila in con.execute("PRAGMA table_info(solicitudes)")
        }
        if "vatsim_cid" not in columnas_solicitudes:
            con.execute(
                "ALTER TABLE solicitudes ADD COLUMN vatsim_cid TEXT NOT NULL DEFAULT ''"
            )


# -- Contraseñas -----------------------------------------------------------


def _hashear(password: str) -> str:
    salt = os.urandom(16)
    derivado = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _ITERACIONES
    )
    return f"{_PREFIJO}{_ITERACIONES}${salt.hex()}${derivado.hex()}"


def _verificar(guardado: str, password: str) -> bool:
    if guardado.startswith(_PREFIJO):
        partes = guardado.split("$")
        if len(partes) != 4:
            return False
        try:
            iteraciones = int(partes[1])
            salt = bytes.fromhex(partes[2])
            esperado = partes[3]
        except ValueError:
            return False
        derivado = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iteraciones
        )
        try:
            return hmac.compare_digest(derivado.hex(), esperado)
        except (ValueError, TypeError):
            return False

    # Hashes antiguos de Werkzeug (scrypt/pbkdf2) si Flask está instalado.
    try:
        from werkzeug.security import check_password_hash
    except ImportError:
        return False
    return bool(check_password_hash(guardado, password))


# -- Correo ----------------------------------------------------------------


def normalizar_correo(correo: str) -> str:
    return (correo or "").strip().lower()


def correo_valido(correo: str) -> bool:
    return bool(_CORREO_RE.match(normalizar_correo(correo)))


def buscar_por_correo(correo: str) -> str | None:
    """ID del piloto con ese correo, o None. Base de la recuperación."""
    buscado = normalizar_correo(correo)
    if not buscado:
        return None
    with conexion() as con:
        fila = con.execute(
            "SELECT license_id FROM usuarios WHERE correo = ?", (buscado,)
        ).fetchone()
    return fila["license_id"] if fila else None


# -- Lectura ---------------------------------------------------------------


def _ficha(license_id: str) -> dict | None:
    """Busca **sin distinguir mayúsculas**.

    Un indicativo es `EVA18L`, `EvA18L` o `eva18l` según quién lo teclee, y
    nadie recuerda con qué caja se dio de alta. La ficha guarda la forma
    original para enseñarla; para encontrarla, la caja da igual.
    """
    with conexion() as con:
        fila = con.execute(
            "SELECT * FROM usuarios WHERE license_id = ? COLLATE NOCASE",
            ((license_id or "").strip(),),
        ).fetchone()
    return dict(fila) if fila else None


def id_canonico(license_id: str) -> str | None:
    """El identificador tal como está guardado, o None si no existe.

    Se usa al iniciar sesión: en la sesión se guarda **esta** forma, no lo que
    tecleó el piloto, para que todo lo que compare identificadores después
    (los vuelos que son suyos, por ejemplo) case siempre.
    """
    ficha = _ficha(license_id)
    return ficha["license_id"] if ficha else None


def existe_usuario(license_id: str) -> bool:
    return _ficha(license_id) is not None


def correo_de(license_id: str) -> str:
    ficha = _ficha(license_id)
    return ficha["correo"] if ficha else ""


def estado_de(license_id: str) -> str:
    ficha = _ficha(license_id)
    return ficha["estado"] if ficha else ""


def rol_de(license_id: str) -> str:
    ficha = _ficha(license_id)
    return ficha["rol"] if ficha else ""


def esta_activa(license_id: str) -> bool:
    return estado_de(license_id) == ESTADO_ACTIVA


def permisos_de(license_id: str) -> frozenset[str]:
    """Una cuenta bloqueada no tiene ningún permiso mientras lo esté."""
    ficha = _ficha(license_id)
    if ficha is None or ficha["estado"] != ESTADO_ACTIVA:
        return frozenset()
    return PERMISOS_POR_ROL.get(ficha["rol"], frozenset())


def tiene_permiso(license_id: str, permiso: str) -> bool:
    return permiso in permisos_de(license_id)


def es_admin(license_id: str) -> bool:
    """Por rol, no por nombre: quien pueda gestionar usuarios es admin."""
    return tiene_permiso(license_id, PERM_GESTIONAR_USUARIOS)


def listar_usuarios() -> list[dict]:
    """Fichas para la página de gestión. Nunca sale el hash."""
    with conexion() as con:
        filas = con.execute(
            "SELECT license_id, correo, estado, rol, categoria, vatsim_cid, "
            "creado, actualizado FROM usuarios ORDER BY license_id"
        ).fetchall()
    return [dict(f) for f in filas]


def cuantos_admins() -> int:
    """Para no quedarse sin ningún administrador por accidente."""
    with conexion() as con:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM usuarios WHERE rol = ? AND estado = ?",
            (ROL_ADMIN, ESTADO_ACTIVA),
        ).fetchone()
    return int(fila["n"])


# -- Altas y cambios -------------------------------------------------------


def _correo_libre(correo: str, excepto: str = "") -> bool:
    dueno = buscar_por_correo(correo)
    return dueno is None or dueno == excepto


def crear_cuenta(
    license_id: str,
    password: str,
    correo: str,
    *,
    rol: str = ROL_PILOTO,
    estado: str = ESTADO_ACTIVA,
    vatsim_cid: str = "",
) -> None:
    """Alta con correo obligatorio y válido. Lanza ValueError si algo falla."""
    license_id = (license_id or "").strip()
    if not license_id:
        raise ValueError("El ID de piloto es obligatorio")
    if existe_usuario(license_id):
        raise ValueError(f"El piloto {license_id} ya está dado de alta")
    if not password:
        raise ValueError("La contraseña es obligatoria")
    if not correo_valido(correo):
        raise ValueError("El correo electrónico no es válido")
    if not _correo_libre(correo):
        raise ValueError("Ese correo ya está en uso por otra cuenta")
    if rol not in ROLES:
        raise ValueError(f"Rol desconocido: {rol}")
    if estado not in ESTADOS:
        raise ValueError(f"Estado desconocido: {estado}")

    momento = _ahora()
    try:
        with conexion() as con:
            con.execute(
                "INSERT INTO usuarios (license_id, password, correo, estado, "
                "rol, vatsim_cid, creado, actualizado) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    license_id,
                    _hashear(password),
                    normalizar_correo(correo),
                    estado,
                    rol,
                    (vatsim_cid or "").strip(),
                    momento,
                    momento,
                ),
            )
    except sqlite3.IntegrityError as exc:
        # La base tiene la última palabra: si dos altas llegan a la vez, una
        # de las dos rebota aquí en vez de pisar a la otra.
        raise ValueError("Ese ID o ese correo ya están en uso") from exc


def registrar_usuario(
    license_id: str,
    password: str,
    *,
    correo: str = "",
    rol: str = ROL_PILOTO,
    estado: str = ESTADO_ACTIVA,
) -> None:
    """Da de alta (o cambia la contraseña de quien ya existe) y persiste.

    Admite cuentas sin correo, que es como quedaron las de antes de este
    modelo; para las altas nuevas usa `crear_cuenta`, que lo exige.
    """
    if existe_usuario(license_id):
        establecer_password(license_id, password)
        if correo:
            cambiar_correo(license_id, correo)
        return

    if correo and not correo_valido(correo):
        raise ValueError("El correo electrónico no es válido")
    if correo and not _correo_libre(correo):
        raise ValueError("Ese correo ya está en uso por otra cuenta")

    momento = _ahora()
    with conexion() as con:
        con.execute(
            "INSERT INTO usuarios (license_id, password, correo, estado, rol, "
            "creado, actualizado) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                license_id,
                _hashear(password),
                normalizar_correo(correo),
                estado if estado in ESTADOS else ESTADO_ACTIVA,
                rol if rol in ROLES else ROL_PILOTO,
                momento,
                momento,
            ),
        )


def _actualizar(license_id: str, campo: str, valor: str) -> None:
    with conexion() as con:
        cambiadas = con.execute(
            f"UPDATE usuarios SET {campo} = ?, actualizado = ? "
            "WHERE license_id = ? COLLATE NOCASE",
            (valor, _ahora(), (license_id or "").strip()),
        ).rowcount
    if not cambiadas:
        raise ValueError(f"El piloto {license_id} no está dado de alta")


def establecer_password(license_id: str, password: str) -> None:
    """Cambia la contraseña; la anterior deja de valer. No se muestra nunca."""
    if not password:
        raise ValueError("La contraseña es obligatoria")
    _actualizar(license_id, "password", _hashear(password))


def cambiar_correo(license_id: str, correo: str) -> None:
    if not correo_valido(correo):
        raise ValueError("El correo electrónico no es válido")
    if not _correo_libre(correo, excepto=license_id):
        raise ValueError("Ese correo ya está en uso por otra cuenta")
    try:
        _actualizar(license_id, "correo", normalizar_correo(correo))
    except sqlite3.IntegrityError as exc:
        raise ValueError("Ese correo ya está en uso por otra cuenta") from exc


def cambiar_rol(license_id: str, rol: str) -> None:
    if rol not in ROLES:
        raise ValueError(f"Rol desconocido: {rol}")
    _actualizar(license_id, "rol", rol)


def cambiar_categoria(license_id: str, categoria: str) -> None:
    if categoria not in CATEGORIAS:
        raise ValueError(f"Categoría desconocida: {categoria}")
    _actualizar(license_id, "categoria", categoria)


def cambiar_estado(license_id: str, estado: str) -> None:
    if estado not in ESTADOS:
        raise ValueError(f"Estado desconocido: {estado}")
    _actualizar(license_id, "estado", estado)


def normalizar_cid(cid: str) -> str:
    """Un CID de VATSIM es un número de socio: solo dígitos.

    Se limpia en vez de rechazar porque la gente lo copia con espacios o lo
    escribe como «CID 1234567», y rechazarlo por eso sería tocar las narices
    sin motivo. Vacío significa «este piloto no ha dado su CID».
    """
    return "".join(c for c in str(cid or "") if c.isdigit())[:9]


def cid_libre(cid: str, excepto: str = "") -> bool:
    """Si ese CID no lo tiene ya otro piloto.

    Dos cuentas con el mismo CID romperían el mapa de vuelos en vivo **en
    silencio**: el feed de VATSIM trae un CID y EvA no sabría a cuál de los
    dos pilotos atribuirlo. Un CID vacío no cuenta como ocupado: puede haber
    muchos pilotos que aún no lo hayan dado.
    """
    cid = normalizar_cid(cid)
    if not cid:
        return True
    with conexion() as con:
        fila = con.execute(
            "SELECT license_id FROM usuarios WHERE vatsim_cid = ?", (cid,)
        ).fetchone()
    return fila is None or fila["license_id"] == excepto


def cambiar_vatsim_cid(license_id: str, cid: str) -> None:
    """Pone o quita el CID de VATSIM de un piloto ya dado de alta.

    Hasta el 2026-08-29 el CID solo se podía indicar al solicitar el alta, así
    que quien ya tenía cuenta no podía rellenarlo nunca. Con el mapa de vuelos
    en vivo enseñando el indicativo de EvA en lugar del número de VATSIM, eso
    dejaba a los pilotos veteranos fuera del mapa sin ninguna forma de
    arreglarlo.

    Cadena vacía lo borra: un piloto puede querer dejar de aparecer.
    """
    cid = normalizar_cid(cid)
    if not cid_libre(cid, excepto=license_id):
        raise ValueError("Ese CID de VATSIM ya lo tiene otro piloto")
    _actualizar(license_id, "vatsim_cid", cid)


# -- Clave del grabador ----------------------------------------------------
# Con ella, EvA Airliner lee del servidor el plan de vuelo que el piloto ha
# preparado en la web, sin tener que teclear origen y destino otra vez. Es de
# solo lectura y solo sirve para eso: no permite entrar en la web, ni cambiar
# nada, ni ver los planes de otro piloto.


def _huella_clave(clave: str) -> str:
    """Huella de una clave del grabador.

    SHA-256 a secas, sin sal ni KDF lento, **a propósito**: la clave la
    genera `generar_clave_grabador` con 32 bytes aleatorios, así que no hay
    nada que adivinar por fuerza bruta y sí hace falta poder buscar al
    piloto por la huella en un solo `SELECT` indexado.
    """
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()


def generar_clave_grabador(license_id: str) -> str:
    """Crea una clave nueva para ese piloto y **devuelve la única copia**.

    En la base solo queda la huella, así que esto es lo último que se puede
    leer la clave entera: si el piloto la pierde, se genera otra. Generar una
    nueva invalida la anterior — es también la forma de revocarla si se le
    escapó a alguien.
    """
    if not existe_usuario(license_id):
        raise ValueError(f"{license_id} no está dado de alta")
    clave = secrets.token_urlsafe(32)
    _actualizar(license_id, "clave_grabador", _huella_clave(clave))
    return clave


def revocar_clave_grabador(license_id: str) -> None:
    """Deja al piloto sin clave: el grabador dejará de leer su plan."""
    _actualizar(license_id, "clave_grabador", "")


def tiene_clave_grabador(license_id: str) -> bool:
    ficha = _ficha(license_id)
    return bool(ficha and ficha["clave_grabador"])


def piloto_por_clave_grabador(clave: str) -> str | None:
    """De qué piloto es esa clave, o None si no es de nadie.

    Una cuenta bloqueada no vale: si se le cierra la puerta de la web, se le
    cierra también la del grabador.
    """
    clave = (clave or "").strip()
    if not clave:
        return None
    with conexion() as con:
        fila = con.execute(
            "SELECT license_id, estado FROM usuarios WHERE clave_grabador = ?",
            (_huella_clave(clave),),
        ).fetchone()
    if fila is None or fila["estado"] != ESTADO_ACTIVA:
        return None
    return str(fila["license_id"])


def bloquear(license_id: str) -> None:
    cambiar_estado(license_id, ESTADO_BLOQUEADA)


def desbloquear(license_id: str) -> None:
    cambiar_estado(license_id, ESTADO_ACTIVA)


def eliminar_usuario(license_id: str) -> None:
    """Borra la cuenta y los testigos que tuviera pendientes."""
    with conexion() as con:
        borradas = con.execute(
            "DELETE FROM usuarios WHERE license_id = ? COLLATE NOCASE",
            (license_id,),
        ).rowcount
        con.execute(
            "DELETE FROM testigos WHERE license_id = ? COLLATE NOCASE",
            (license_id,),
        )
    if not borradas:
        raise ValueError(f"El piloto {license_id} no está dado de alta")


# -- Autenticación ---------------------------------------------------------


def autenticar_detallado(license_id: str, password: str) -> str:
    """AUTH_OK / AUTH_DESCONOCIDO / AUTH_PASSWORD / AUTH_BLOQUEADA.

    El estado solo se revela a quien acierta la contraseña: así nadie averigua
    qué cuentas existen probando IDs.
    """
    ficha = _ficha(license_id)
    if ficha is None:
        return AUTH_DESCONOCIDO
    if not _verificar(ficha["password"], password):
        return AUTH_PASSWORD
    if ficha["estado"] != ESTADO_ACTIVA:
        return AUTH_BLOQUEADA
    return AUTH_OK


def autenticar(license_id: str, password: str) -> bool:
    """Valida credenciales. Una cuenta bloqueada no entra."""
    return autenticar_detallado(license_id, password) == AUTH_OK


# -- Migración del JSON antiguo -------------------------------------------


def _ficha_desde_json(valor) -> dict | None:
    """Acepta el formato original (solo el hash) y el intermedio (ficha)."""
    if isinstance(valor, str):
        valor = {"password": valor}
    if not isinstance(valor, dict):
        return None

    password = str(valor.get("password", ""))
    if not password:
        return None

    estado = str(valor.get("estado", ESTADO_ACTIVA))
    rol = str(valor.get("rol", ROL_PILOTO))
    creado = str(valor.get("creado", "")) or _ahora()
    return {
        "password": password,
        "correo": normalizar_correo(str(valor.get("correo", ""))),
        "estado": estado if estado in ESTADOS else ESTADO_ACTIVA,
        "rol": rol if rol in ROLES else ROL_PILOTO,
        "creado": creado,
        "actualizado": str(valor.get("actualizado", "")) or creado,
    }


def _importar_json_si_hace_falta() -> None:
    """Trae las cuentas del `usuarios.json` de antes. Solo la primera vez."""
    if not USUARIOS_PATH.exists():
        return
    with conexion() as con:
        if con.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
            return  # La base ya tiene cuentas: el JSON es historia.

    try:
        datos = json.loads(USUARIOS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(datos, dict):
        return

    momento = _ahora()
    with conexion() as con:
        for license_id, valor in datos.items():
            ficha = _ficha_desde_json(valor)
            if ficha is None:
                continue
            try:
                con.execute(
                    "INSERT INTO usuarios (license_id, password, correo, "
                    "estado, rol, creado, actualizado) VALUES (?,?,?,?,?,?,?)",
                    (
                        str(license_id),
                        ficha["password"],
                        ficha["correo"],
                        ficha["estado"],
                        ficha["rol"],
                        ficha["creado"],
                        momento,
                    ),
                )
            except sqlite3.IntegrityError:
                # Correo repetido en el fichero viejo: entra sin correo, que
                # se lo ponga un administrador. Antes eso, que perder la cuenta.
                con.execute(
                    "INSERT OR IGNORE INTO usuarios (license_id, password, "
                    "correo, estado, rol, creado, actualizado) "
                    "VALUES (?,?,'',?,?,?,?)",
                    (
                        str(license_id),
                        ficha["password"],
                        ficha["estado"],
                        ficha["rol"],
                        ficha["creado"],
                        momento,
                    ),
                )

    # El fichero se conserva, apartado: si algo saliera mal, los datos siguen.
    respaldo = USUARIOS_PATH.with_suffix(USUARIOS_PATH.suffix + ".migrado")
    if not respaldo.exists():
        try:
            USUARIOS_PATH.rename(respaldo)
        except OSError:
            pass


# -- Semilla y arranque ----------------------------------------------------


def _asegurar_semilla() -> None:
    """Un usuario de pruebas, para no quedarse nunca sin poder entrar.

    Es administrador **solo mientras no haya otro**. En cuanto existe un
    administrador de verdad, `pruebas` puede degradarse o bloquearse desde la
    gestión y esto ya no vuelve a ascenderlo: si lo hiciera, degradarlo sería
    imposible y una cuenta con contraseña adivinable mandaría en la casa.
    """
    ficha = _ficha(USUARIO_PRUEBAS)
    if ficha is None or not ficha["password"].startswith(_PREFIJO):
        registrar_usuario(USUARIO_PRUEBAS, PASSWORD_PRUEBAS, rol=ROL_ADMIN)
        ficha = _ficha(USUARIO_PRUEBAS)
    if ficha and ficha["rol"] != ROL_ADMIN and cuantos_admins() == 0:
        cambiar_rol(USUARIO_PRUEBAS, ROL_ADMIN)


def configurar_almacen(path: Path) -> None:
    """Para tests: apunta el almacén a un directorio temporal.

    Acepta tanto el directorio como una ruta a `usuarios.json` dentro de él,
    que es como lo llamaban los tests cuando el almacén era el fichero.

    **Solo repunta.** No inicializa aquí mismo: cada fixture de test hace
    `configurar_almacen(tmp)` al empezar y `configurar_almacen(original)` al
    terminar, para dejarlo "como estaba". Si esta función inicializara de
    inmediato, ese `original` casi siempre es la ruta de producción — y cada
    test dejaría, al terminar, una conexión real contra `web/data/eva.db`,
    con la semilla de administrador incluida. Pasó de verdad el 2026-08-18.
    La inicialización queda pospuesta a la primera llamada real a
    `conexion()`, así que un test que solo restaura el estado y no vuelve a
    tocar `cuentas` no escribe nada.
    """
    global DB_PATH, USUARIOS_PATH, _inicializado

    path = Path(path)
    directorio = path if path.suffix == "" else path.parent
    DB_PATH = directorio / "eva.db"
    USUARIOS_PATH = directorio / "usuarios.json"
    _inicializado = False
