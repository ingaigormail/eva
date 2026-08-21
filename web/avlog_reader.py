"""Lector de logs de vuelo en formato .avlog.json (formato nativo de eva.pyw)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class TelemetryPoint:
    """Un punto de telemetría del track."""

    timestamp: float
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


class AvlogJsonReader:
    """Lee logs de vuelo en formato .avlog.json."""

    @staticmethod
    def read_avlog(avlog_path: Path) -> tuple[list[TelemetryPoint], TelemetrySummary]:
        """Lee un archivo .avlog.json y devuelve puntos + resumen.

        Args:
            avlog_path: Ruta al archivo .avlog.json

        Returns:
            (lista de puntos telemetría, resumen estadístico)
        """
        points = []

        if not avlog_path.exists():
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
            with open(avlog_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Extraer track (array de puntos de telemetría)
            track = data.get("track", [])

            for row in track:
                try:
                    # Convertir de kg a lb (1 kg = 2.20462 lb)
                    total_weight_kg = row.get("total_weight_kg", 0)
                    fuel_kg = row.get("fuel_kg", 0)

                    point = TelemetryPoint(
                        timestamp=row.get("t", 0),  # t está en segundos
                        lat=float(row.get("lat", 0)),
                        lon=float(row.get("lon", 0)),
                        alt_msl_ft=float(row.get("alt_msl_ft", 0)),
                        alt_agl_ft=float(row.get("alt_agl_ft", 0)),
                        hdg_deg=float(row.get("hdg_deg", 0)),
                        gs_kt=float(row.get("gs_kt", 0)),
                        ias_kt=float(row.get("ias_kt", 0)),
                        vs_fpm=float(row.get("vs_fpm", 0)),
                        total_weight_lb=total_weight_kg * 2.20462,
                        fuel_qty_lb=fuel_kg * 2.20462,
                        on_ground=bool(row.get("on_ground", False)),
                    )
                    points.append(point)
                except (ValueError, TypeError, KeyError):
                    continue

        except Exception as e:
            print(f"Error leyendo AVLOG {avlog_path}: {e}")
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

        # Distancia aproximada (suma de velocidades / 60)
        distance_nm = sum(p.gs_kt / 60 for p in points)

        # Tiempo de vuelo en minutos
        flight_time_min = points[-1].timestamp / 60 if points else 0

        summary = TelemetrySummary(
            flight_time_min=flight_time_min,
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
    def find_avlog_files(directory: Path) -> list[Path]:
        """Encuentra todos los .avlog.json en un directorio."""
        if not directory.exists():
            return []

        avlogs = []
        for avlog_file in directory.glob("*.avlog.json"):
            avlogs.append(avlog_file)

        # Ordenar por fecha (más recientes primero)
        return sorted(avlogs, reverse=True)
