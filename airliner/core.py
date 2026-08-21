"""Núcleo del Airliner: conexión a simuladores y grabación de vuelos."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class CajaNegra:
    """Gestiona el almacén local de vuelos (caja negra)."""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            base_dir = Path.home() / "eva-airliner"

        self.base_dir = Path(base_dir)
        self.caja_negra = self.base_dir / "caja-negra"

        # Crear carpetas si no existen
        self.caja_negra.mkdir(parents=True, exist_ok=True)
        self.log_dir = self.base_dir / "logs"
        self.log_dir.mkdir(exist_ok=True)

    def guardar_vuelo(self, data: dict, callsign: str = "UNKNOWN") -> Path:
        """Guarda un vuelo en la caja negra."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{callsign}_{timestamp}.json"
        filepath = self.caja_negra / filename

        # Añadir metadata
        data["_guardado_en"] = datetime.now().isoformat()
        data["_callsign"] = callsign

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

        return filepath

    def listar_vuelos(self) -> list[Path]:
        """Lista todos los vuelos en la caja negra."""
        return sorted(self.caja_negra.glob("*.json"))

    def leer_vuelo(self, filepath: Path) -> dict:
        """Lee un vuelo de la caja negra."""
        with open(filepath) as f:
            return json.load(f)


class ConectorMSFS:
    """Conecta a Microsoft Flight Simulator 2024 via SimConnect."""

    def __init__(self):
        try:
            from SimConnect import SimConnect
            self.sim = SimConnect()
            self.conectado = True
        except Exception as e:
            print(f"No se pudo conectar a MSFS: {e}")
            self.sim = None
            self.conectado = False

    def leer_telemetria(self) -> dict:
        """Lee datos básicos de MSFS."""
        if not self.conectado:
            return {}

        try:
            # Leer variables básicas (simplificado)
            data = {
                "timestamp": datetime.now().isoformat(),
                "conectado": True,
            }
            return data
        except Exception as e:
            print(f"Error leyendo telemetría: {e}")
            return {"error": str(e)}

    def desconectar(self):
        """Desconecta de MSFS."""
        if self.sim:
            self.sim.close()
            self.conectado = False
