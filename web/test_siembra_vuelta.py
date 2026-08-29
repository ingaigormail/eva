"""Las etapas de la Vuelta se siembran solas si faltan.

Producción estuvo con la página de Eventos vacía porque el importador nunca
se ejecutó allí: `rutas_vfr` no existía y la vista se traga el error. Esto
fija que no vuelva a pasar en un servidor nuevo, y —más importante— que la
siembra automática NO borre lo que los pilotos llevan hecho.
"""
import sqlite3
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

import importar_vuelta_espana as vuelta


def test_en_una_base_vacia_se_importan_las_etapas(tmp_path):
    db = tmp_path / "eva.db"

    assert vuelta.asegurar_importadas(db) is True

    con = sqlite3.connect(db)
    n = con.execute("SELECT COUNT(*) FROM rutas_vfr").fetchone()[0]
    con.close()
    assert n == len(vuelta.ETAPAS)


def test_si_ya_estan_no_se_vuelven_a_importar(tmp_path):
    db = tmp_path / "eva.db"
    vuelta.asegurar_importadas(db)

    assert vuelta.asegurar_importadas(db) is False


def test_la_siembra_no_borra_el_progreso_de_los_pilotos(tmp_path):
    """Lo que de verdad importa: `importar()` sí borra el progreso, así que
    llamarlo en cada arranque habría machacado las etapas completadas."""
    db = tmp_path / "eva.db"
    vuelta.asegurar_importadas(db)

    con = sqlite3.connect(db)
    ruta_id = con.execute("SELECT id FROM rutas_vfr LIMIT 1").fetchone()[0]
    con.execute(
        "INSERT INTO progreso_rutas (license_id, ruta_id, estado) VALUES (?, ?, ?)",
        ("EVA18L", ruta_id, "completada"),
    )
    con.commit()
    con.close()

    vuelta.asegurar_importadas(db)  # segundo arranque

    con = sqlite3.connect(db)
    hechas = con.execute(
        "SELECT COUNT(*) FROM progreso_rutas WHERE estado = 'completada'"
    ).fetchone()[0]
    con.close()
    assert hechas == 1, "la siembra se ha llevado por delante el progreso"
