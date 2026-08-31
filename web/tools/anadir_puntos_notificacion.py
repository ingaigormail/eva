"""Añade puntos de notificación VFR verificados a `puntos_vfr_es`.

Por qué existe
---------------
`puntos_vfr_es` viene de OpenAIP (ver `migrar_aerodromos_es.py`), que es
comunitario y no tiene por qué llevar todos los aeródromos pequeños. Este
script guarda los puntos que se han verificado a mano, contrastando la carta
VAC oficial del aeródromo contra la capa `PUNTO_VFR` de ENAIRE
(`web/tools/descargar_enaire.py`) — cuando las coordenadas de ambas fuentes
coinciden, se da el punto por bueno.

Es aditivo e idempotente: si el aeródromo ya tiene puntos en `puntos_vfr_es`,
no hace nada (evita duplicar si se ejecuta dos veces). No toca ningún otro
dato.

Uso
---
    python web/tools/anadir_puntos_notificacion.py
    python web/tools/anadir_puntos_notificacion.py --dst /ruta/a/eva.db
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DST_POR_DEFECTO = Path(__file__).resolve().parent.parent / "data" / "eva.db"

#: Verificado el 2026-08-31 contra LEMU.VAC.3 (carta VAC de Mutxamel,
#: MAR 2025, sección "PUNTOS NOTIFICACIÓN") y la capa PUNTO_VFR de ENAIRE:
#: coordenadas idénticas en ambas fuentes. Todos "compulsory" porque la VAC
#: los llama puntos de notificación obligatoria, no opcionales.
PUNTOS: dict[str, list[dict]] = {
    "LEMU": [
        {"letter": "N", "name": "BALSA", "lat": 38.466667, "lon": -0.452778},
        {"letter": "E", "name": "NUDO AUTOPISTA", "lat": 38.419444, "lon": -0.425000},
        {"letter": "S", "name": "INVERNADEROS", "lat": 38.425000, "lon": -0.516667},
        {"letter": "E1", "name": "NAVE INDUSTRIAL", "lat": 38.430556, "lon": -0.450000},
    ],
    # Verificado el 2026-08-31: coordenadas pasadas por el piloto desde la
    # VAC de Requena - El Rebollar, coinciden exactamente con PUNTO_VFR de
    # ENAIRE (mismo criterio que LEMU).
    "LERE": [
        {"letter": "N", "name": "CHERA", "lat": 39.597317, "lon": -0.965556},
        {"letter": "E", "name": "SIETE AGUAS", "lat": 39.472653, "lon": -0.916389},
        {"letter": "S", "name": "LA PORTERA", "lat": 39.403333, "lon": -1.086944},
        {"letter": "W", "name": "SAN ANTONIO", "lat": 39.524417, "lon": -1.136389},
    ],
}


def anadir(dst: Path | None = None) -> None:
    destino = Path(dst) if dst is not None else DST_POR_DEFECTO
    con = sqlite3.connect(destino)
    try:
        for icao, puntos in PUNTOS.items():
            ya = con.execute(
                "SELECT COUNT(*) FROM puntos_vfr_es WHERE ctr_icao = ?", (icao,)
            ).fetchone()[0]
            if ya:
                print(f"  {icao}: ya tiene {ya} puntos, no se toca")
                continue
            for p in puntos:
                con.execute(
                    "INSERT INTO puntos_vfr_es "
                    "(name, letter, ctr_icao, ctr_name, lat, lon, roles, "
                    "rule, source, compulsory) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        p["name"], p["letter"], icao, icao,
                        p["lat"], p["lon"], "entry,exit",
                        "Punto de notificación (VAC + ENAIRE, verificado)",
                        "vac+enaire", 1,
                    ),
                )
            print(f"  {icao}: {len(puntos)} puntos añadidos")
        con.commit()
    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dst", type=Path, default=None)
    args = parser.parse_args()
    anadir(args.dst)
    print("[OK]")
