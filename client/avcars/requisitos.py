"""Comprobación de los requisitos para ejecutar EvA.

Se usa en el instalador para avisar al piloto de lo que falta **sin impedirle
instalar**: alguien puede preparar el equipo antes de tener el simulador
puesto, o instalar EvA en un portátil para copiarlo luego. Bloquear la
instalación por eso sería peor que avisar.

Cada comprobación devuelve un `Resultado` con un mensaje ya redactado para
mostrar, incluyendo qué hacer si falla.
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

MIN_FREE_SPACE_MB = 200.0


class Nivel(Enum):
    """Gravedad del resultado de una comprobación."""

    OK = "ok"
    AVISO = "aviso"      # se puede instalar, pero algo no está listo
    PROBLEMA = "problema"  # impedirá usar EvA hasta resolverlo


@dataclass
class Resultado:
    nombre: str
    nivel: Nivel
    detalle: str
    solucion: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.nivel is Nivel.OK


# -- comprobaciones individuales ---------------------------------------


def comprobar_sistema() -> Resultado:
    """EvA está pensada para Windows, que es donde corren los simuladores."""
    if sys.platform != "win32":
        return Resultado(
            nombre="Sistema operativo",
            nivel=Nivel.AVISO,
            detalle=f"Este sistema no es Windows ({sys.platform}).",
            solucion="EvA necesita Windows 10 u 11 para hablar con el simulador.",
        )
    return Resultado("Sistema operativo", Nivel.OK, "Windows")


SIMULADORES = {
    "MSFS 2024": (
        r"Packages\Microsoft.Limitless_8wekyb3d8bbwe",
        "Microsoft Flight Simulator 2024",
    ),
    "MSFS 2020": (
        r"Packages\Microsoft.FlightSimulator_8wekyb3d8bbwe",
        "Microsoft Flight Simulator",
    ),
}


def _carpetas_de_busqueda() -> list[Path]:
    local = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    return [Path(p) for p in (local, appdata) if p]


def detectar_simuladores() -> list[str]:
    """Devuelve los simuladores que parecen instalados."""
    encontrados: list[str] = []
    bases = _carpetas_de_busqueda()

    for nombre, (ruta_store, ruta_steam) in SIMULADORES.items():
        for base in bases:
            if (base / ruta_store).exists() or (base / ruta_steam).exists():
                encontrados.append(nombre)
                break

    # Prepar3D se instala en Archivos de programa, no en el perfil.
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        raiz = os.environ.get(variable)
        if raiz and list(Path(raiz).glob("Lockheed Martin/Prepar3D*")):
            encontrados.append("Prepar3D")
            break

    return encontrados


def comprobar_simulador() -> Resultado:
    encontrados = detectar_simuladores()
    if encontrados:
        return Resultado("Simulador", Nivel.OK, ", ".join(encontrados))

    return Resultado(
        nombre="Simulador",
        nivel=Nivel.AVISO,
        detalle="No se ha encontrado ningún simulador compatible.",
        solucion=(
            "EvA funciona con MSFS 2020, MSFS 2024 y Prepar3D. Puedes "
            "instalar EvA ahora y el simulador después."
        ),
    )


def comprobar_simconnect() -> Resultado:
    """SimConnect viene con el simulador; se busca su DLL.

    No se intenta importar la librería de Python porque el instalador puede
    ejecutarse en un equipo sin Python: se busca el fichero del sistema.
    """
    if sys.platform != "win32":
        return Resultado(
            "SimConnect", Nivel.AVISO, "No comprobable fuera de Windows"
        )

    nombres = ("SimConnect.dll",)
    rutas = []

    for variable in ("ProgramFiles", "ProgramFiles(x86)", "WINDIR"):
        raiz = os.environ.get(variable)
        if raiz:
            rutas.append(Path(raiz))

    for ruta in rutas:
        for nombre in nombres:
            try:
                if any(ruta.rglob(nombre)):
                    return Resultado("SimConnect", Nivel.OK, "Disponible")
            except OSError:
                continue

    return Resultado(
        nombre="SimConnect",
        nivel=Nivel.AVISO,
        detalle="No se ha localizado SimConnect.",
        solucion=(
            "SimConnect se instala con el simulador. En MSFS actívalo en "
            "Opciones → General → Desarrolladores → Modo desarrollador y "
            "luego Herramientas → SDK Installer. En Prepar3D, vuelve a "
            "ejecutar su instalador y marca «Client Components»."
        ),
    )


def comprobar_espacio(destino: Path) -> Resultado:
    """Espacio libre en la unidad donde se va a instalar."""
    try:
        # La carpeta puede no existir aún: se mira la primera que sí exista.
        referencia = destino
        while not referencia.exists() and referencia != referencia.parent:
            referencia = referencia.parent
        libre_mb = shutil.disk_usage(referencia).free / (1024 * 1024)
    except OSError:
        return Resultado(
            "Espacio en disco", Nivel.AVISO, "No se ha podido comprobar"
        )

    if libre_mb < MIN_FREE_SPACE_MB:
        return Resultado(
            nombre="Espacio en disco",
            nivel=Nivel.AVISO,
            detalle=f"Quedan {libre_mb:.0f} MB libres.",
            solucion=(
                f"Se recomiendan al menos {MIN_FREE_SPACE_MB:.0f} MB para el "
                "programa y las grabaciones."
            ),
        )

    return Resultado("Espacio en disco", Nivel.OK, f"{libre_mb / 1024:.1f} GB libres")


def comprobar_escritura(destino: Path) -> Resultado:
    """Si no se puede escribir, no hay instalación posible en esa carpeta."""
    try:
        destino.mkdir(parents=True, exist_ok=True)
        prueba = destino / ".eva_prueba"
        prueba.touch()
        prueba.unlink()
        return Resultado("Permisos de escritura", Nivel.OK, str(destino))
    except OSError:
        return Resultado(
            nombre="Permisos de escritura",
            nivel=Nivel.PROBLEMA,
            detalle=f"No se puede escribir en {destino}.",
            solucion="Elige otra carpeta, por ejemplo dentro de tu carpeta de usuario.",
        )


# -- comprobación completa ---------------------------------------------


def comprobar_todo(destino: Path) -> list[Resultado]:
    """Ejecuta todas las comprobaciones en el orden en que se muestran."""
    return [
        comprobar_sistema(),
        comprobar_simulador(),
        comprobar_simconnect(),
        comprobar_espacio(destino),
        comprobar_escritura(destino),
    ]


def hay_problemas(resultados: list[Resultado]) -> bool:
    """True si algo impide instalar (no si solo hay avisos)."""
    return any(r.nivel is Nivel.PROBLEMA for r in resultados)


def resumen(resultados: list[Resultado]) -> str:
    """Texto corto para la cabecera del instalador."""
    problemas = sum(1 for r in resultados if r.nivel is Nivel.PROBLEMA)
    avisos = sum(1 for r in resultados if r.nivel is Nivel.AVISO)

    if problemas:
        return f"{problemas} problema(s) que resolver"
    if avisos:
        return f"Se puede instalar, con {avisos} aviso(s)"
    return "Todo listo"
