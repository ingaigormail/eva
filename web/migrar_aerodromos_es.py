"""Migra aerodromos_es.db → eva.db (tablas con sufijo _es).

Especificación OC-05 §2.3. Segunda fuente de aeropuertos: complementa
`airports.json`, que no se toca. Solo añade tablas satélite; las existentes
(`vuelos_resumen`, `usuarios`, …) no se modifican.
"""
import sqlite3
from pathlib import Path

SRC = Path(r"D:\proyectos\31_07_2026\data_aerodromos\aerodromos_es.db")
# La base real está en web/data/eva.db (avcars/cuentas.py: `parents[2] / web / data`).
DST = Path(__file__).resolve().parent / "data" / "eva.db"

TABLAS = [
    "aerodromos",
    "pistas",
    "radios",
    "espacios_aereos",
    "zonas_restringidas",
    "puntos_vfr",
]


def migrar(dst: Path | None = None) -> None:
    """Copia tablas `_es` de la fuente a `dst` (por defecto, eva.db de la web).

    `dst` se puede redirigir desde los tests para aislar el trabajo en un
    temporal sin tocar la base real.
    """
    destino = Path(dst) if dst is not None else DST
    src = sqlite3.connect(SRC)
    dst_con = sqlite3.connect(destino)
    cur = dst_con.cursor()

    for tabla in TABLAS:
        # Leer schema de la fuente
        row = src.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
        ).fetchone()
        if not row:
            continue
        schema = row[0].replace(f"CREATE TABLE {tabla}", f"CREATE TABLE {tabla}_es")

        cur.execute(f"DROP TABLE IF EXISTS {tabla}_es")
        cur.execute(schema)

        # Copiar datos
        cur_src = src.execute(f"SELECT * FROM {tabla}")
        rows = cur_src.fetchall()
        if rows:
            cols = [d[0] for d in cur_src.description]
            placeholders = ",".join("?" * len(cols))
            cur.executemany(
                f"INSERT INTO {tabla}_es ({','.join(cols)}) VALUES ({placeholders})",
                rows,
            )
        print(f"  {tabla}_es: {len(rows)} filas")

    dst_con.commit()
    dst_con.close()
    src.close()
    print("[OK] Migración completada")


if __name__ == "__main__":
    migrar()