"""Trae el espacio aéreo oficial de ENAIRE a una base local.

Por qué existe
--------------
Las tablas de espacio aéreo que hay hoy en `eva.db` (`espacios_aereos_es`,
`puntos_vfr_es`) vienen de OpenAIP, que es comunitario: no lleva ciclo AIRAC,
así que se queda obsoleto sin avisar y nadie se entera. Para pintar un mapa
vale; para suspenderle un vuelo a un piloto, no.

ENAIRE publica lo mismo pero oficial, en los servicios que hay detrás de
Insignia VFR (https://insigniavfr.enaire.es). Son ArcGIS REST públicos, sin
autenticación, y devuelven GeoJSON con los límites verticales **en número**
(`LOWER_VAL`/`UPPER_VAL` + unidad aparte) en vez del texto ambiguo de OpenAIP.

Condiciones de uso
------------------
ENAIRE permite usar estos servicios siempre que se indique expresamente que
ENAIRE es el titular de los derechos, y que el uso **nunca sea operacional**.
Un simulador es no operacional por definición, pero la atribución hay que
ponerla por escrito en la web. Dudas: ais@enaire.es

Uso
---
    python web/tools/descargar_enaire.py
    python web/tools/descargar_enaire.py --servicio airac   # el ciclo que viene
    python web/tools/descargar_enaire.py --capas CTR TMA_CTA

Se relanza en cada ciclo AIRAC (28 días).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

# En este equipo (y en cualquiera con antivirus que intercepte TLS) la
# verificación de certificados falla contra cualquier host porque el proxy
# inyecta su propia CA raíz. `truststore` usa el almacén de certificados del
# sistema, que sí la conoce. Si no está instalado se sigue adelante: en un
# servidor limpio no hace falta.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover - depende de la máquina
    pass


BASE = "https://servais.enaire.es/insigniads/rest/services/INSIGNIA_SRV"

#: `VIGOR` es lo que está en vigor ahora mismo, que es contra lo que hay que
#: juzgar un vuelo ya volado. `AIRAC` es lo publicado pero aún sin entrar en
#: vigor, útil para preparar el cambio antes de que llegue.
SERVICIOS = {
    "vigor": f"{BASE}/Aero_SRV_VIGOR_data_V4/FeatureServer",
    "airac": f"{BASE}/Aero_SRV_AIRAC_data_V3/FeatureServer",
}

#: Qué capas nos interesan, con el id que tienen en el servicio. El servicio
#: publica unas cincuenta; aquí solo están las que hacen falta para juzgar un
#: vuelo VFR. Añadir una es poner una línea, no tocar el esquema.
CAPAS = {
    "CTR": 131,
    "ATZ_FIZ": 129,
    "TMA_CTA": 110,
    "SECTORES_VFR": 111,
    "D_P_R": 126,
    "PROHIBIDO_VFR": 113,
    "NO_SOBREVUELO": 114,
    "RMZ": 2,
    "TMZ": 122,
    "PUNTO_VFR": 147,
    "RUTAS_VFR": 29,
}

#: El servicio no devuelve más de esto por consulta, así que hay que pedir
#: por tandas. Lo dice él mismo en `maxRecordCount`.
POR_TANDA = 1000

ESQUEMA = """
CREATE TABLE capas (
    capa           TEXT PRIMARY KEY,
    id_servicio    INTEGER NOT NULL,
    servicio       TEXT NOT NULL,
    descargado_utc TEXT NOT NULL,
    filas          INTEGER NOT NULL
);

-- Una sola tabla para todas las capas: cada una trae campos distintos y
-- hacer una tabla por capa obligaría a tocar el esquema cada vez que se
-- añade una. Lo común sale a columnas (que es por lo que se filtra) y el
-- resto se guarda entero en `props` por si algún día hace falta.
CREATE TABLE elementos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    capa       TEXT NOT NULL,
    ident      TEXT,
    nombre     TEXT,
    tipo       TEXT,
    clase      TEXT,
    -- Límites verticales. El valor va en número y la unidad en su columna,
    -- y `*_code` dice respecto a qué se mide (HEIS = sobre el nivel del mar,
    -- HEIG = sobre el terreno, STD = nivel de vuelo). Esa referencia es
    -- justo lo que faltaba en OpenAIP, donde "2000 ft" podía ser cualquiera
    -- de las tres.
    lower_val  REAL,
    lower_uom  TEXT,
    lower_code TEXT,
    upper_val  REAL,
    upper_uom  TEXT,
    upper_code TEXT,
    -- Altitud máxima VFR publicada. Va como texto porque ENAIRE la da ya
    -- redactada ("4500ft AMSL"), con la referencia dentro: convertirla a
    -- número aquí perdería la mitad del dato.
    vfrmaxalt  TEXT,
    geom       TEXT NOT NULL,
    props      TEXT NOT NULL
);

CREATE INDEX elementos_capa  ON elementos (capa);
CREATE INDEX elementos_ident ON elementos (capa, ident);
"""


def _pedir(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def _tandas(servicio: str, id_capa: int) -> Iterator[dict]:
    """Va pidiendo la capa por tandas hasta que se acaba.

    `exceededTransferLimit` es lo que dice ArcGIS cuando ha devuelto un trozo
    y queda más. Fiarse solo de "me han venido menos de los que pedí" falla
    cuando el total es múltiplo exacto del tamaño de tanda.
    """
    desplazamiento = 0
    while True:
        parametros = urllib.parse.urlencode(
            {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                # Sin esto la geometría llega en Web Mercator, que es lo que
                # usa el visor. Nosotros comparamos contra latitud y longitud
                # del simulador, así que se pide en WGS84 directamente.
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": desplazamiento,
                "resultRecordCount": POR_TANDA,
            }
        )
        datos = _pedir(f"{servicio}/{id_capa}/query?{parametros}")

        for elemento in datos.get("features", []):
            yield elemento

        if not datos.get("exceededTransferLimit"):
            return
        desplazamiento += POR_TANDA


def _numero(valor: object) -> Optional[float]:
    """El valor como número, o None. ENAIRE mezcla nulos con cadenas vacías."""
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _fila(capa: str, elemento: dict) -> tuple:
    p = dict(elemento.get("properties") or {})
    return (
        capa,
        p.get("IDENT_TXT"),
        p.get("NAME_TXT"),
        p.get("TYPE_CODE"),
        p.get("CLASS"),
        _numero(p.get("LOWER_VAL")),
        p.get("DISTVERTLOWER_UOM"),
        p.get("DISTVERTLOWER_CODE"),
        _numero(p.get("UPPER_VAL")),
        p.get("DISTVERTUPPER_UOM"),
        p.get("DISTVERTUPPER_CODE"),
        p.get("VFRMAXALT") or None,
        json.dumps(elemento.get("geometry"), separators=(",", ":")),
        json.dumps(p, separators=(",", ":"), ensure_ascii=False),
    )


def descargar(destino: Path, nombre_servicio: str, capas: dict) -> int:
    """Descarga las capas y deja la base en `destino`. Devuelve filas totales.

    Se escribe en un fichero aparte y solo al final se pone en su sitio. Una
    descarga a medias que dejara media España sin espacio aéreo sería peor
    que no tener nada: las reglas darían por bueno un vuelo que atravesó una
    zona prohibida que resulta que no se llegó a descargar.
    """
    servicio = SERVICIOS[nombre_servicio]
    temporal = destino.with_suffix(destino.suffix + ".nuevo")
    temporal.unlink(missing_ok=True)
    destino.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    con = sqlite3.connect(temporal)
    try:
        con.executescript(ESQUEMA)
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")

        for capa, id_capa in capas.items():
            print(f"  {capa} (capa {id_capa}) ... ", end="", flush=True)
            filas = [_fila(capa, e) for e in _tandas(servicio, id_capa)]
            con.executemany(
                "INSERT INTO elementos (capa, ident, nombre, tipo, clase, "
                "lower_val, lower_uom, lower_code, upper_val, upper_uom, "
                "upper_code, vfrmaxalt, geom, props) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                filas,
            )
            con.execute(
                "INSERT INTO capas (capa, id_servicio, servicio, "
                "descargado_utc, filas) VALUES (?,?,?,?,?)",
                (capa, id_capa, nombre_servicio, ahora, len(filas)),
            )
            total += len(filas)
            print(f"{len(filas)} elementos")

        con.commit()
    except BaseException:
        con.close()
        temporal.unlink(missing_ok=True)
        raise
    con.close()

    temporal.replace(destino)
    return total


def main(argv: Optional[list[str]] = None) -> int:
    raiz = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--servicio",
        choices=sorted(SERVICIOS),
        default="vigor",
        help="vigor = lo que está en vigor; airac = el ciclo que viene",
    )
    parser.add_argument(
        "--capas",
        nargs="+",
        choices=sorted(CAPAS),
        help="por defecto, todas",
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=raiz / "web" / "data" / "aeronautica.db",
        help="base de salida (se reemplaza entera)",
    )
    args = parser.parse_args(argv)

    elegidas = (
        {c: CAPAS[c] for c in args.capas} if args.capas else dict(CAPAS)
    )

    print(f"ENAIRE {args.servicio.upper()} -> {args.salida}")
    try:
        total = descargar(args.salida, args.servicio, elegidas)
    except Exception as exc:  # noqa: BLE001 — es una herramienta de consola
        print(f"\nFalló la descarga, no se ha tocado la base: {exc}")
        return 1

    print(f"\n{total} elementos en {len(elegidas)} capas.")
    print("Datos de ENAIRE. Uso no operacional; citar a ENAIRE como titular.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
