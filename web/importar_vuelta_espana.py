"""Carga las 21 etapas de la Vuelta a España 2026 en `rutas_vfr`.

Circuito cerrado: Gibraltar → costa mediterránea → Cantábrico → Galicia →
Portugal → Gibraltar. 1.900 NM en total. Los datos son los de la hoja de
ruta oficial (fecha, origen, destino y distancia); no se calculan ni se
inventan.

No lee ningún Excel a propósito: la especificación original (OC-05, 19 de
agosto) sí lo hacía, contra `E:\\descargas\\VFR españa.xlsx`, pero esa era
una ruta distinta (LEAX→…→GEML→LEAX, sin distancias) que esta sustituye.
Con los 21 tramos ya fijos y verificados, un fichero externo solo añade un
punto más en el que algo puede no estar donde se espera — en el propio
equipo, y más aún en el servidor.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# La base real está en web/data/eva.db (avcars/cuentas.py: `parents[2] / web / data`).
EVA_DB = Path(__file__).resolve().parent / "data" / "eva.db"

ROUTE_ID = "vae-2026"

#: (etapa, origen, destino, distancia_nm)
ETAPAS = [
    (1, "LXGB", "LEMG", 57),
    (2, "LEMG", "LEAM", 109),
    (3, "LEAM", "LEMI", 95),
    (4, "LEMI", "LEAL", 52),
    (5, "LEAL", "LEVC", 111),
    (6, "LEVC", "LECN", 49),
    (7, "LECN", "LERS", 91),
    (8, "LERS", "LEGE", 95),
    (9, "LEGE", "LESU", 72),
    (10, "LESU", "LEPP", 141),
    (11, "LEPP", "LESO", 44),
    (12, "LESO", "LEXJ", 94),
    (13, "LEXJ", "LEAS", 98),
    (14, "LEAS", "LECO", 118),
    (15, "LECO", "LEVX", 107),
    (16, "LEVX", "LPMR", 145),
    (17, "LPMR", "LPCS", 74),
    (18, "LPCS", "LPSI", 75),
    (19, "LPSI", "LPFR", 97),
    (20, "LPFR", "LERT", 102),
    (21, "LERT", "LXGB", 74),
]

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


def importar(dst: Path | None = None) -> None:
    """Carga las 21 etapas en `dst` (por defecto, eva.db de la web).

    Vuelve a poblar sin duplicar: borra la edición anterior de esta misma
    ruta (`route_id`) antes de insertar, así que se puede ejecutar más de
    una vez sin ir dejando copias.
    """
    destino = Path(dst) if dst is not None else EVA_DB

    conn = sqlite3.connect(destino)
    cur = conn.cursor()

    cur.executescript(_ESQUEMA)

    cur.execute(
        "DELETE FROM progreso_rutas WHERE ruta_id IN "
        "(SELECT id FROM rutas_vfr WHERE route_id = ?)",
        (ROUTE_ID,),
    )
    cur.execute("DELETE FROM rutas_vfr WHERE route_id = ?", (ROUTE_ID,))

    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for etapa, origen, destino_icao, distancia in ETAPAS:
        cur.execute(
            """INSERT INTO rutas_vfr (route_id, stage_number, stage_name,
               origin_icao, destination_icao, distance_nm, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                ROUTE_ID,
                etapa,
                f"Etapa {etapa}: {origen} → {destino_icao}",
                origen,
                destino_icao,
                distancia,
                ahora,
            ),
        )

    conn.commit()
    conn.close()
    print(f"[OK] {len(ETAPAS)} etapas importadas a rutas_vfr (route_id='{ROUTE_ID}')")


if __name__ == "__main__":
    importar()
