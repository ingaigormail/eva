"""La validación empieza en la web; el escritorio se entera por aquí.

Decisión del usuario (2026-08-18): el piloto ya no se valida en una ventana
del escritorio, sino en la web, y EVA Dispatcher arranca con esa identidad.

El problema a resolver es que la sesión de la web vive en una cookie del
navegador, a la que el proceso de escritorio no tiene acceso. Como los dos
corren en la misma máquina y ya comparten `web/data/usuarios.json`, el
traspaso se hace con otro fichero en esa misma carpeta: la web lo escribe al
validar y el escritorio lo lee.

**No es un mecanismo de seguridad.** Cualquiera que pueda escribir en esa
carpeta puede poner ahí el ID que quiera; igual que ya podía editar
`usuarios.json`. Sirve para llevar la identidad de una ventana a otra en el
equipo del piloto, nada más. Si algún día EvA deja de ser una aplicación
local, esto hay que sustituirlo por un testigo firmado (SEC-03).

La sesión **caduca**: un fichero olvidado de hace días no debe colar como
validación de hoy.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import cuentas

#: Junto a `eva.db`, que es el otro dato compartido web/escritorio.
SESION_PATH = cuentas.directorio_datos() / "sesion_activa.json"

#: Cuánto vale una validación. Lo bastante para abrir el Dispatcher tras
#: entrar en la web, no tanto como para que valga la de anteayer.
VALIDEZ = timedelta(hours=12)


def abrir(license_id: str, callsign: str = "") -> bool:
    """La web anota quién acaba de validarse. False si no se pudo escribir."""
    if not license_id:
        return False
    try:
        SESION_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporal = SESION_PATH.with_suffix(".tmp")
        temporal.write_text(
            json.dumps(
                {
                    "license_id": license_id,
                    "callsign": callsign,
                    "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporal.replace(SESION_PATH)
        return True
    except OSError:
        return False


def leer() -> Optional[dict]:
    """Sesión válida en curso, o None.

    Nunca lanza: si el fichero no está, no se lee o está caducado, es None.
    Sin sesión el escritorio manda al piloto a la web, que es lo correcto.
    """
    try:
        datos = json.loads(SESION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(datos, dict) or not datos.get("license_id"):
        return None

    try:
        marca = datetime.fromisoformat(str(datos.get("utc", "")))
    except ValueError:
        return None
    if marca.tzinfo is None:
        marca = marca.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - marca > VALIDEZ:
        return None

    return datos


def cerrar() -> None:
    """Borra la sesión. Se llama al salir de la web."""
    try:
        SESION_PATH.unlink()
    except OSError:
        pass
