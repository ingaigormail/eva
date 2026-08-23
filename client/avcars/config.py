"""Carga de configuración estática: perfiles de dificultad, flota y aeropuertos.

Los umbrales y penalizaciones nunca van hardcodeados en el motor de
evaluación: se leen siempre de aquí. Ver ../docs/criterios_vfr.md para el
significado de cada valor.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
DEFAULT_PROFILES_PATH = CONFIG_DIR / "profiles.yaml"
DEFAULT_AIRCRAFT_PATH = CONFIG_DIR / "aircraft.yaml"
DEFAULT_AIRPORTS_PATH = CONFIG_DIR / "airports.json"


def load_profiles(path: Path = DEFAULT_PROFILES_PATH) -> dict:
    """Lee el fichero de perfiles y devuelve el dict completo (easy/normal/hard)."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def get_profile(name: str, profiles: dict) -> dict:
    """Devuelve el perfil solicitado o lanza ValueError si no existe."""
    if name not in profiles:
        disponibles = ", ".join(profiles.keys())
        raise ValueError(f"Perfil desconocido: '{name}'. Disponibles: {disponibles}")
    return profiles[name]


def load_aircraft(path: Path = DEFAULT_AIRCRAFT_PATH) -> dict:
    """Lee `aircraft.yaml`: designador OACI -> límites, pesos y referencias.

    Muchos campos siguen a `null` porque siguen pendientes de fuente (ver
    docs/especificacion_funcional.md, sección de datos de aeronave). No se
    rellenan aquí con valores supuestos.
    """
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def limite_efectivo(aeronave: dict, campo: str) -> tuple[object, str | None]:
    """El límite que manda para `campo` (p.ej. "vne", "vmo"): POH real
    primero, referencia de simulador solo si no hay POH.

    Devuelve `(valor, fuente)`. `fuente` es `"poh"`, `"sim"` o `None` si
    ningún sitio tiene el dato — nunca se inventa un valor a medias.
    `valor` puede ser el string `"no_aplica"` (el POH dice explícitamente
    que ese límite no rige para este avión, p.ej. VNE en un jet que usa
    VMO): eso sigue viniendo de fuente `"poh"`, no cae al simulador.

    Ver la cabecera de `aircraft.yaml` (DOS FUENTES) para por qué el orden
    importa: mezclarlas sería un error grave.
    """
    poh = aeronave.get("limites_poh") or {}
    valor = poh.get(campo)
    if valor is not None:
        return valor, "poh"
    sim = aeronave.get("referencia_sim") or {}
    valor_sim = sim.get(campo)
    if valor_sim is not None:
        return valor_sim, "sim"
    return None, None


def load_airports(path: Path = DEFAULT_AIRPORTS_PATH) -> dict:
    """Lee `airports.json`: designador OACI -> nombre y coordenadas.

    Extraído de `vatspy-data-project` (VATSIM, licencia CC-BY-SA), que es la
    lista de aeropuertos que la propia red da por válidos. No incluye pistas
    (ver DAT-02 en la especificación funcional).
    """
    return json.loads(path.read_text(encoding="utf-8"))
