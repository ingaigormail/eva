"""Lee el plan de vuelo cargado en el simulador.

Objetivo: que el piloto no tenga que teclear la salida y la llegada si ya las
ha metido en el simulador.

SimConnect **no** expone el aeropuerto de salida como variable. Lo que sí hay
es el fichero del plan de vuelo activo, que MSFS guarda en disco en formato
XML y contiene tanto la salida como el destino. Por eso se combinan dos
fuentes:

1. El fichero `.PLN` del plan activo (salida y llegada fiables).
2. SimConnect, para el destino de la aproximación cargada, la matrícula y el
   tipo de avión, que sí son variables.

Si ninguna de las dos da resultado, se devuelve lo que se haya podido
averiguar y el piloto rellena el resto a mano: no se inventa nada.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# Nombres con los que MSFS guarda el plan de vuelo activo.
PLAN_FILENAMES = (
    "CustomFlight.PLN",
    "LastFlight.PLN",
    "CustomFlight.FLT",
)


@dataclass
class FlightPlanData:
    """Lo que se ha podido averiguar del plan de vuelo cargado."""

    departure_icao: Optional[str] = None
    arrival_icao: Optional[str] = None
    aircraft_type: Optional[str] = None
    registration: Optional[str] = None
    flight_number: Optional[str] = None
    cruise_altitude_ft: Optional[int] = None
    source: str = "ninguna"

    @property
    def has_route(self) -> bool:
        return bool(self.departure_icao or self.arrival_icao)


def _msfs_data_dirs() -> list[Path]:
    """Carpetas donde MSFS 2020 y 2024 guardan el plan de vuelo activo.

    Cambian según si el simulador viene de Microsoft Store o de Steam, así
    que se prueban todas las conocidas y se descartan las que no existen.
    """
    local = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")

    candidates = [
        # MSFS 2024
        Path(local) / "Packages" / "Microsoft.Limitless_8wekyb3d8bbwe" / "LocalCache",
        Path(appdata) / "Microsoft Flight Simulator 2024",
        # MSFS 2020
        Path(local)
        / "Packages"
        / "Microsoft.FlightSimulator_8wekyb3d8bbwe"
        / "LocalCache",
        Path(appdata) / "Microsoft Flight Simulator",
    ]
    return [path for path in candidates if path.exists()]


def _find_plan_file() -> Optional[Path]:
    """Busca el fichero de plan de vuelo más reciente."""
    found: list[Path] = []
    for directory in _msfs_data_dirs():
        for name in PLAN_FILENAMES:
            candidate = directory / name
            if candidate.exists():
                found.append(candidate)

    if not found:
        return None
    return max(found, key=lambda p: p.stat().st_mtime)


def _clean_icao(value: Optional[str]) -> Optional[str]:
    """Normaliza un identificador de aeropuerto."""
    if not value:
        return None
    code = value.strip().upper()
    # Los ficheros de MSFS a veces traen el ICAO con prefijos internos.
    if len(code) > 4 and code[0] in "AKW":
        code = code[-4:]
    return code if 3 <= len(code) <= 4 and code.isalnum() else None


def parse_plan_file(path: Path) -> FlightPlanData:
    """Extrae los datos de un fichero de plan de vuelo de MSFS."""
    data = FlightPlanData(source=path.name)
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError):
        return data

    root = tree.getroot()

    def _text(tag: str) -> Optional[str]:
        node = root.find(f".//{tag}")
        return node.text if node is not None and node.text else None

    data.departure_icao = _clean_icao(_text("DepartureID"))
    data.arrival_icao = _clean_icao(_text("DestinationID"))

    altitude = _text("CruisingAlt")
    if altitude:
        try:
            data.cruise_altitude_ft = int(float(altitude))
        except ValueError:
            pass

    return data


def read_from_simconnect(requests: Any) -> FlightPlanData:
    """Lee del simulador lo que sí está disponible como variable.

    `requests` es un `AircraftRequests` de Python-SimConnect. Se pasa como
    parámetro (en vez de crear uno aquí) para reutilizar la conexión que ya
    tiene abierta el conector.
    """
    data = FlightPlanData(source="simconnect")

    def _get(name: str) -> Optional[str]:
        try:
            value = requests.get(name)
        except Exception:
            return None
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="ignore")
        text = str(value).strip()
        return text or None

    # El destino de la aproximación cargada en el GPS.
    data.arrival_icao = _clean_icao(_get("GPS_APPROACH_AIRPORT_ID"))
    data.registration = _get("ATC_ID")
    data.flight_number = _get("ATC_FLIGHT_NUMBER")
    data.aircraft_type = _get("ATC_MODEL") or _get("TITLE")

    return data


def read_flight_plan(requests: Any = None) -> FlightPlanData:
    """Combina las dos fuentes, dando prioridad al fichero del plan.

    El fichero es más fiable porque contiene la salida, que SimConnect no
    expone. SimConnect completa lo que falte.
    """
    result = FlightPlanData()

    plan_file = _find_plan_file()
    if plan_file is not None:
        result = parse_plan_file(plan_file)

    if requests is not None:
        from_sim = read_from_simconnect(requests)
        result.arrival_icao = result.arrival_icao or from_sim.arrival_icao
        result.registration = result.registration or from_sim.registration
        result.flight_number = result.flight_number or from_sim.flight_number
        result.aircraft_type = result.aircraft_type or from_sim.aircraft_type
        if result.source == "ninguna":
            result.source = from_sim.source
        elif from_sim.has_route or from_sim.registration:
            result.source = f"{result.source} + simconnect"

    return result
