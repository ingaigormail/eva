"""¿Está el simulador arrancado?

Pregunta distinta de "¿puedo hablar con el simulador?". Aquí solo se mira si
el proceso existe, que es barato y no depende de que SimConnect llegue a
enganchar. La conexión de verdad la hace `connectors.simconnect_client`.

Se comprueba por **nombre exacto de proceso**, no por subcadena: en un
equipo con MSFS instalado suelen convivir procesos como
`MSFS_AddonsLinker_2024.exe` o `pilot_core_msfs.exe`, que contienen "msfs"
pero no son el simulador. Buscar "msfs" daría verde con el simulador cerrado.

Nombres verificados en el equipo del piloto (2026-08-17): MSFS 2024 arranca
como `FlightSimulator2024.exe`.
"""
from __future__ import annotations

import subprocess

try:
    import psutil
except ImportError:  # psutil no está: se tira de tasklist
    psutil = None

#: Nombres de proceso del simulador, en minúsculas. MSFS 2020 y 2024 usan
#: ejecutables distintos y pueden estar instalados a la vez.
MSFS_PROCESS_NAMES = (
    "flightsimulator2024.exe",  # MSFS 2024
    "flightsimulator.exe",      # MSFS 2020
)


def is_msfs_running() -> bool:
    """True si hay un proceso de MSFS en marcha.

    Nunca lanza excepción: si no se puede comprobar, se responde False. Un
    indicador apagado por no poder mirarlo es preferible a que se caiga la
    ventana en cada refresco.
    """
    if psutil is not None:
        try:
            for proceso in psutil.process_iter(["name"]):
                nombre = (proceso.info.get("name") or "").lower()
                if nombre in MSFS_PROCESS_NAMES:
                    return True
            return False
        except Exception:
            pass  # se intenta con tasklist

    return _is_running_tasklist()


def _is_running_tasklist() -> bool:
    """Respaldo sin psutil, con el mismo `tasklist` que se usa para vPilot."""
    for nombre in MSFS_PROCESS_NAMES:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {nombre}", "/NH"],
                capture_output=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            continue
        # En bytes, no en texto: las cabeceras de `tasklist` van en la
        # codificación de la consola y decodificarlas mal deja `stdout` en
        # None. Los nombres de proceso son ASCII y se comparan tal cual.
        if nombre.encode("ascii") in (result.stdout or b"").lower():
            return True
    return False
