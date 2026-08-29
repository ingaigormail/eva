"""Extrae los limites de las FIR de Iberia para pintarlas en el mapa en vivo.

Por que hace falta
------------------
El feed de VATSIM no dice donde esta un controlador: solo su indicativo y su
frecuencia. Para los de torre o rodadura basta con situarlos en su aeropuerto,
pero un `LECM_CTR` no es un punto sino un AREA -- la FIR de Madrid entera -- y
sin sus limites no se puede pintar.

Esos limites los publica VATSIM en el `vatspy-data-project`, que es la misma
fuente de la que ya sale `client/config/airports.json` y la que usa VATSIM
Radar por dentro. Licencia CC-BY-SA: hay que citar la fuente.

Se queda solo con las FIR de Espana y Portugal (LE, GC, GE, LP), que son 9 y
ocupan 16 KB. El fichero entero son 1,9 MB y 1.102 regiones: mandar el mundo
al navegador para pintar nueve zonas no tiene sentido.

Uso
---
    python web/tools/extraer_fir_iberia.py

Escribe `web/static/fir_iberia.geojson`. A diferencia del espacio aereo de
ENAIRE, este SI va en git: son 16 KB que cambian una vez al ano, y asi no hace
falta un paso extra al desplegar.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover - depende de la maquina
    pass

FUENTE = (
    "https://raw.githubusercontent.com/vatsimnetwork/"
    "vatspy-data-project/master/Boundaries.geojson"
)

#: Prefijos OACI de las FIR que interesan: Espana peninsular y Baleares,
#: Canarias, y Portugal con Azores.
PREFIJOS = ("LE", "GC", "GE", "LP")

DESTINO = Path(__file__).resolve().parents[1] / "static" / "fir_iberia.geojson"


def extraer(datos: dict) -> dict:
    """Las FIR base de Iberia, sin subsectores.

    Se descartan los subsectores (`LECM-BDP`, `LECB-TMA`…) porque lo que se
    pinta es la zona del controlador que esta conectado, y en el feed aparece
    como `LECM_CTR`: la FIR entera. Pintar ademas sus divisiones internas
    llenaria el mapa de lineas que no significan nada para el piloto.
    """
    salida = []
    for region in datos.get("features", []):
        ident = str((region.get("properties") or {}).get("id") or "")
        if not ident.startswith(PREFIJOS) or "-" in ident:
            continue
        propiedades = region.get("properties") or {}
        salida.append(
            {
                "type": "Feature",
                "properties": {
                    "id": ident,
                    "label_lat": propiedades.get("label_lat"),
                    "label_lon": propiedades.get("label_lon"),
                },
                "geometry": region.get("geometry"),
            }
        )
    return {"type": "FeatureCollection", "features": salida}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--salida", type=Path, default=DESTINO)
    args = parser.parse_args(argv)

    print(f"descargando {FUENTE}")
    try:
        with urllib.request.urlopen(FUENTE, timeout=90) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - herramienta de consola
        print(f"no se pudo descargar: {exc}")
        return 1

    recorte = extraer(datos)
    if not recorte["features"]:
        print("no se encontro ninguna FIR de Iberia: revisar los prefijos")
        return 1

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(
        json.dumps(recorte, separators=(",", ":")), encoding="utf-8"
    )
    tamano = args.salida.stat().st_size / 1024
    print(f"{len(recorte['features'])} FIR -> {args.salida} ({tamano:.1f} KB)")
    print("  " + ", ".join(f["properties"]["id"] for f in recorte["features"]))
    print("\nDatos de vatspy-data-project (VATSIM), licencia CC-BY-SA.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
