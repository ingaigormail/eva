r"""Importa E:\descargas\VFR españa.xlsx a eva.db → tabla rutas_vfr.

Especificación OC-05 §3.3/§3.4: la Vuelta a España 2026 (21 etapas, circuito
cerrado LEAX → … → GEML → LEAX). Crea `rutas_vfr` y `progreso_rutas` si no
existen; vuelve a populares sin duplicar. `distance_nm` se deja NULL (no se
inventa).
"""
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

EXCEL = Path(r"E:\descargas\VFR españa.xlsx")
# La base real está en web/data/eva.db (avcars/cuentas.py: `parents[2] / web / data`).
EVA_DB = Path(__file__).resolve().parent / "data" / "eva.db"

PATRON_ETAPA = re.compile(r"Etapa Nº (\d+) \(([A-Z]{4})\s*-\s*([A-Z]{4})\)")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS rutas_vfr (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id TEXT NOT NULL,
    stage_number INTEGER NOT NULL,
    stage_name TEXT,
    origin_icao TEXT NOT NULL,
    destination_icao TEXT NOT NULL,
    distance_nm REAL,
    difficulty TEXT DEFAULT 'normal',
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS progreso_rutas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_id TEXT NOT NULL,
    ruta_id INTEGER NOT NULL REFERENCES rutas_vfr(id),
    estado TEXT NOT NULL DEFAULT 'pendiente',
    vuelo_huella TEXT,
    completada_en TEXT,
    intentos INTEGER DEFAULT 0,
    UNIQUE(license_id, ruta_id)
);
CREATE INDEX IF NOT EXISTS idx_progreso_piloto ON progreso_rutas(license_id);
CREATE INDEX IF NOT EXISTS idx_progreso_estado ON progreso_rutas(estado);
CREATE INDEX IF NOT EXISTS idx_rutas_vfr_route ON rutas_vfr(route_id);
"""


def importar(dst: Path | None = None, excel: Path | None = None) -> None:
    """Importa las etapas desde el Excel a `dst` (por defecto, eva.db de la web).

    `dst`/`excel` se pueden redirigir desde los tests para aislar el trabajo.
    """
    destino = Path(dst) if dst is not None else EVA_DB
    hoja = Path(excel) if excel is not None else EXCEL

    df = pd.read_excel(hoja)
    conn = sqlite3.connect(destino)
    cur = conn.cursor()

    # El esquema de las tablas nuevas se asegura antes de tocar nada.
    cur.executescript(_ESQUEMA)

    # Limpiar edición anterior
    cur.execute(
        "DELETE FROM progreso_rutas WHERE ruta_id IN "
        "(SELECT id FROM rutas_vfr WHERE route_id = 'vae-2026')"
    )
    cur.execute("DELETE FROM rutas_vfr WHERE route_id = 'vae-2026'")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total = 0

    for _, row in df.iterrows():
        vuelos = str(row["Vuelos"])
        match = PATRON_ETAPA.match(vuelos)
        if not match:
            continue
        etapa, origen, destino_icao = match.groups()
        cur.execute(
            """INSERT INTO rutas_vfr (route_id, stage_number, stage_name,
               origin_icao, destination_icao, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("vae-2026", int(etapa), vuelos.strip(), origen, destino_icao, now),
        )
        total += 1

    conn.commit()
    conn.close()
    print(f"[OK] {total} etapas importadas a rutas_vfr (route_id='vae-2026')")


if __name__ == "__main__":
    importar()