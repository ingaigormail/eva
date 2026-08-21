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
    creado      TEXT NOT NULL,
    actualizado TEXT NOT NULL
);

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
    discord      TEXT NOT NULL DEFAULT '',
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
            "SELECT license_id, correo, estado, rol, creado, actualizado "
            "FROM usuarios ORDER BY license_id"
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
                "rol, creado, actualizado) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    license_id,
                    _hashear(password),
                    normalizar_correo(correo),
                    estado,
                    rol,
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


def cambiar_estado(license_id: str, estado: str) -> None:
    if estado not in ESTADOS:
        raise ValueError(f"Estado desconocido: {estado}")
    _actualizar(license_id, "estado", estado)


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
