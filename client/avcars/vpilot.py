"""Todo lo que EvA necesita saber de vPilot, sin tocar su instalación.

Dos preguntas distintas, con dos mecanismos distintos:

1. **¿Está vPilot arrancado?** Se comprueba mirando los procesos en marcha.
   Arrancado no es lo mismo que conectado: vPilot puede llevar un rato
   abierto sin haberse unido a la red todavía, porque **no se conecta hasta
   que detecta un simulador de vuelo abierto**. Por eso es una luz aparte de
   la de VATSIM, no la misma.

2. **¿Cuál es el CID del piloto?** Se lee de su propia configuración
   (`vPilotConfig.xml`, elemento `NetworkLogin`), en vez de pedírselo. Ya lo
   tiene ahí porque es lo que usa para entrar en la red; que EvA lo
   redactee sería un dato de más que pedir.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

VPILOT_PROCESS_NAME = "vPilot.exe"

#: Rutas donde suele estar instalado vPilot.
VPILOT_CANDIDATES = (
    os.path.expandvars(r"%LOCALAPPDATA%\vPilot\vPilot.exe"),
    r"C:\Program Files (x86)\vPilot\vPilot.exe",
    r"C:\Program Files\vPilot\vPilot.exe",
)

#: Dónde guarda vPilot su configuración. Es el mismo sitio en todas las
#: instalaciones porque vPilot no deja elegirlo.
VPILOT_CONFIG_PATH = Path(os.path.expandvars(r"%LOCALAPPDATA%\vPilot\vPilotConfig.xml"))

_CID_PATTERN = re.compile(r"<NetworkLogin>(\d+)</NetworkLogin>")


def find_vpilot_executable(custom_path: str = "") -> Optional[str]:
    """Busca el ejecutable de vPilot.

    Primero la ruta que el piloto haya indicado a mano (si la hay y sigue
    existiendo), luego las rutas habituales. None si no aparece en ninguna
    parte: entonces hace falta preguntar.
    """
    if custom_path and os.path.isfile(custom_path):
        return custom_path
    for candidate in VPILOT_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return None


def is_vpilot_running() -> bool:
    """True si hay un proceso `vPilot.exe` en marcha.

    Arrancado, no necesariamente conectado a la red: para eso está
    `avcars.dashboard.check_vatsim_connection`, que consulta la red, no el
    proceso local.
    """
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {VPILOT_PROCESS_NAME}", "/NH"],
            capture_output=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False

    # Sin `text=True` a propósito: `tasklist` escribe sus cabeceras en la
    # codificación de la consola (en Windows en español lleva acentos), y si
    # Python no acierta con ella la decodificación falla y `stdout` se queda
    # en None. Los nombres de proceso son ASCII, así que se compara en bytes.
    salida = result.stdout or b""
    return VPILOT_PROCESS_NAME.lower().encode("ascii") in salida.lower()


def read_vpilot_cid(config_path: Path = VPILOT_CONFIG_PATH) -> Optional[str]:
    """Lee el CID de la configuración de vPilot, si existe.

    No se abre como XML con un parser completo: es un fichero pequeño y de
    formato estable, y una expresión regular sobre el texto es más tolerante
    a variaciones menores de versión que exigir un XML perfectamente válido.
    None si el fichero no está, no se puede leer, o no contiene el campo.
    """
    try:
        contenido = config_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _CID_PATTERN.search(contenido)
    return match.group(1) if match else None
