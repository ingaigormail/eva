"""Dónde vive EvA y dónde deja las grabaciones.

La aplicación se distribuye como un ejecutable dentro de una carpeta `EvA`,
y las grabaciones se guardan en una subcarpeta `Grabaciones` junto a él, para
que el piloto tenga todo en el mismo sitio y no tenga que buscar nada.

Durante el desarrollo (ejecutando el código con Python) no hay ejecutable, así
que se usa la carpeta del proyecto como base. Así el comportamiento es el
mismo en los dos casos sin tener que configurar nada.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Optional

RECORDINGS_DIRNAME = "grabaciones"
SETTINGS_FILENAME = "eva.config.json"


def is_frozen() -> bool:
    """True si estamos ejecutando desde el .exe empaquetado."""
    return getattr(sys, "frozen", False)


def base_dir() -> Path:
    """Carpeta de instalación de EvA.

    En el ejecutable es la carpeta que contiene al .exe. En desarrollo, la
    carpeta `client` del repositorio.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def is_writable(directory: Path) -> bool:
    """Comprueba que se puede escribir de verdad en una carpeta.

    Se hace escribiendo un fichero y borrándolo, en vez de mirar permisos:
    en Windows los permisos declarados y lo que deja hacer el sistema no
    siempre coinciden (carpetas sincronizadas, controladas por el antivirus,
    unidades de red).
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".eva_escritura"
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        return False


def recordings_dir(preferred: Optional[str] = None) -> Path:
    """Carpeta donde se guardan los vuelos, creándola si hace falta.

    `preferred` es la carpeta que el piloto haya elegido en la configuración.
    Si no se puede escribir ahí (o no se indica ninguna), se prueba la
    carpeta junto al ejecutable y, como último recurso, Documentos: es
    preferible guardar el vuelo en un sitio inesperado que perderlo.
    """
    candidates: list[Path] = []
    if preferred:
        candidates.append(Path(preferred))
    candidates.append(base_dir() / RECORDINGS_DIRNAME)
    candidates.append(Path.home() / "Documents" / "EvA" / RECORDINGS_DIRNAME)

    for candidate in candidates:
        if is_writable(candidate):
            return candidate

    # Si nada de lo anterior funciona, se devuelve la primera opción para que
    # el error se produzca donde se pueda explicar al piloto.
    return candidates[0]


def settings_file() -> Path:
    """Fichero donde se recuerdan las preferencias entre sesiones."""
    return base_dir() / SETTINGS_FILENAME


def free_space_mb(directory: Path) -> Optional[float]:
    """Espacio libre en la unidad de esa carpeta, en MB.

    Devuelve None si no se puede averiguar, para que quien llame decida qué
    hacer en vez de asumir que hay sitio.
    """
    try:
        return shutil.disk_usage(directory).free / (1024 * 1024)
    except OSError:
        return None
