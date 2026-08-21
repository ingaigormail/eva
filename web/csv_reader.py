"""Lector de telemetría desde CSV generados por fstelemetry.

fstelemetry genera archivos CSV con 50+ variables de MSFS 2020.
Este módulo lee esos archivos y los convierte en estructuras
que usa EvA para mostrar en D3 (Registro y Evaluación).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class TelemetryPoint:
    """Un punto de telemetría (una fila del CSV)."""

    timestamp: float  # Segundos desde inicio del vuelo
    lat: float
    lon: float
    alt_msl_ft: float
    alt_agl_ft: float
    hdg_deg: float
    gs_kt: float
    ias_kt: float
    vs_fpm: float
    total_weight_lb: float
    fuel_qty_lb: float
    on_ground: bool


@dataclass
class TelemetrySummary:
    """Resumen estadístico de un vuelo."""

    flight_time_min: float
    distance_nm: float
    alt_max_ft: float
    gs_max_kt: float
    vs_min_fpm: float
    vs_max_fpm: float
    weight_avg_lb: float
    fuel_used_lb: float
    points_recorded: int


class FStelemetryCSVReader:
    """Lee y procesa CSV de fstelemetry."""

    # Mapeo de nombres de columnas fstelemetry → nuestros campos
    COLUMN_MAP = {
        "PLANE_LATITUDE": "lat",
        "PLANE_LONGITUDE": "lon",
        "PLANE_ALTITUDE": "alt_msl_ft",
        "PLANE_ALT_ABOVE_GROUND": "alt_agl_ft",
        "PLANE_HEADING_DEGREES_TRUE": "hdg_deg",
        "GROUND_VELOCITY": "gs_kt",
        "AIRSPEED_INDICATED": "ias_kt",
        "VERTICAL_SPEED": "vs_fpm",
        "TOTAL_WEIGHT": "total_weight_lb",
        "FUEL_TOTAL_QUANTITY_WEIGHT": "fuel_qty_lb",
        "SIM_ON_GROUND": "on_ground",
    }

    @staticmethod
    def read_csv(csv_path: Path) -> tuple[list[TelemetryPoint], TelemetrySummary]:
        """Lee un CSV de fstelemetry y devuelve puntos + resumen.

        Args:
            csv_path: Ruta al archivo CSV

        Returns:
            (lista de puntos telemetría, resumen estadístico)
        """
        points = []

        if not csv_path.exists():
            return [], TelemetrySummary(
                flight_time_min=0,
                distance_nm=0,
                alt_max_ft=0,
                gs_max_kt=0,
                vs_min_fpm=0,
                vs_max_fpm=0,
                weight_avg_lb=0,
                fuel_used_lb=0,
                points_recorded=0,
            )

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader):
                    try:
                        # Convertir valores
                        point = TelemetryPoint(
                            timestamp=row_idx * 1.0,  # 1 seg por fila
                            lat=float(row.get("PLANE_LATITUDE", 0)),
                            lon=float(row.get("PLANE_LONGITUDE", 0)),
                            alt_msl_ft=float(row.get("PLANE_ALTITUDE", 0)),
                            alt_agl_ft=float(row.get("PLANE_ALT_ABOVE_GROUND", 0)),
                            hdg_deg=float(row.get("PLANE_HEADING_DEGREES_TRUE", 0)),
                            gs_kt=float(row.get("GROUND_VELOCITY", 0)),
                            ias_kt=float(row.get("AIRSPEED_INDICATED", 0)),
                            vs_fpm=float(row.get("VERTICAL_SPEED", 0)),
                            total_weight_lb=float(
                                row.get("TOTAL_WEIGHT", 0)
                            ),
                            fuel_qty_lb=float(
                                row.get("FUEL_TOTAL_QUANTITY_WEIGHT", 0)
                            ),
                            on_ground=bool(
                                int(row.get("SIM_ON_GROUND", 0))
                            ),
                        )
                        points.append(point)
                    except (ValueError, TypeError):
                        # Fila con datos inválidos, saltar
                        continue
        except Exception as e:
            print(f"Error leyendo CSV {csv_path}: {e}")
            return [], TelemetrySummary(
                flight_time_min=0,
                distance_nm=0,
                alt_max_ft=0,
                gs_max_kt=0,
                vs_min_fpm=0,
                vs_max_fpm=0,
                weight_avg_lb=0,
                fuel_used_lb=0,
                points_recorded=0,
            )

        # Calcular resumen
        if not points:
            return [], TelemetrySummary(
                flight_time_min=0,
                distance_nm=0,
                alt_max_ft=0,
                gs_max_kt=0,
                vs_min_fpm=0,
                vs_max_fpm=0,
                weight_avg_lb=0,
                fuel_used_lb=0,
                points_recorded=0,
            )

        altitudes = [p.alt_msl_ft for p in points]
        velocidades = [p.gs_kt for p in points]
        vs_values = [p.vs_fpm for p in points]
        weights = [p.total_weight_lb for p in points]

        # Distancia aproximada (suma de velocidades / 60 en millas náuticas)
        distance_nm = sum(p.gs_kt / 60 for p in points)

        summary = TelemetrySummary(
            flight_time_min=len(points) / 60.0,  # 1 punto/segundo
            distance_nm=distance_nm,
            alt_max_ft=max(altitudes) if altitudes else 0,
            gs_max_kt=max(velocidades) if velocidades else 0,
            vs_min_fpm=min(vs_values) if vs_values else 0,
            vs_max_fpm=max(vs_values) if vs_values else 0,
            weight_avg_lb=np.mean(weights) if weights else 0,
            fuel_used_lb=0,  # TODO: Calcular diferencia inicial-final
            points_recorded=len(points),
        )

        return points, summary

    @staticmethod
    def find_csv_files(directory: Path) -> list[Path]:
        """Encuentra todos los CSV de fstelemetry en un directorio.

        Formato: YYYYMMDDHHMMSS.csv (generado por fstelemetry)
        """
        if not directory.exists():
            return []

        csvs = []
        for csv_file in directory.glob("*.csv"):
            # Verificar que el nombre es válido (14 dígitos)
            if len(csv_file.stem) == 14 and csv_file.stem.isdigit():
                csvs.append(csv_file)

        # Ordenar por fecha (más recientes primero)
        return sorted(csvs, reverse=True)
