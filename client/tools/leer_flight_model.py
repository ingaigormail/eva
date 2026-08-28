"""Lee los pesos y el combustible de la flota del propio simulador.

Por que el simulador y no un catalogo
--------------------------------------
El piloto vuela lo que MSFS modela, y el grabador mide lo que MSFS reporta.
Si el catalogo del fabricante dice una cosa y el simulador otra, para juzgar
un vuelo manda el simulador: es la unica cifra contra la que el piloto puede
comprobar lo que le sale en la cabina.

Ademas resuelve la duda de las variantes sin adivinar. `aircraft.yaml` traia
el MTOW de un Cessna 172N/P (1050 kg), pero el paquete que MSFS instala es
`asobo-aircraft-c172sp-as1000`: un 172S de 1160 kg. Son 110 kg de diferencia
en un avion cuyo margen de carga util son 390 kg.

Uso
---
    python client/tools/leer_flight_model.py

No escribe nada: imprime lo que encuentra para que se copie a
`aircraft.yaml` a mano, con su `fuente` y su `fecha_consulta`. Se hace asi a
proposito — estos numeros afectan a la puntuacion y a la economia, y merecen
pasar por un `git diff` que alguien lea, no por una escritura automatica.
"""
from __future__ import annotations

import argparse
import configparser
import glob
import os
import re
import sys
from pathlib import Path

LB_A_KG = 0.45359237

#: Densidad por tipo de combustible, en kg por galon US. El `fuel_type` del
#: cfg: 1 = 100 octanos (AVGAS), 2 = Jet-A. AVGAS pesa 6,0 lb/gal y el Jet-A
#: 6,7 lb/gal, que es de donde salen estos numeros.
KG_POR_GALON = {1: 6.0 * LB_A_KG, 2: 6.7 * LB_A_KG}

#: Que paquete de MSFS corresponde a cada avion de la flota. Es la parte que
#: hay que mantener a mano: si manana entra otro avion, se anade aqui.
PAQUETES = {
    "C172": "asobo-aircraft-c172sp-as1000",
    "C208": "asobo-aircraft-208b-grand-caravan-ex",
    "DA62": "asobo-aircraft-da62",
    "BE58": "asobo-aircraft-baron-g58",
    "TBM9": "asobo-aircraft-tbm930",
    "B350": "asobo-aircraft-kingair350",
    "C25C": "asobo-aircraft-cj4",
    # El Twin Otter no viene con MSFS; si se instala un anadido, poner aqui
    # su carpeta. Mientras tanto sus cifras salen del manual, no del sim.
    "DHC6": None,
}

USER_CFG = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Packages"
    / "Microsoft.FlightSimulator_8wekyb3d8bbwe"
    / "LocalCache"
    / "UserCfg.opt"
)


def raiz_de_paquetes() -> Path | None:
    """Donde instalo MSFS los paquetes, segun su propia configuracion.

    No se codifica una ruta: cada instalacion la pone donde quiere, y aqui
    esta en G:. `UserCfg.opt` lo dice, asi que se le pregunta a el.
    """
    try:
        texto = USER_CFG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r'InstalledPackagesPath\s+"([^"]+)"', texto)
    return Path(m.group(1)) if m else None


def _valor(texto: str, clave: str) -> float | None:
    m = re.search(rf"^\s*{clave}\s*=\s*([-\d.]+)", texto, re.M | re.I)
    return float(m.group(1)) if m else None


def _combustible_kg(texto: str) -> float | None:
    """Suma la capacidad utilizable de todos los depositos.

    Cada linea del bloque [FUEL] es: z, x, y, capacidad_total, no_utilizable
    (en galones). Lo que interesa para despachar es la diferencia: el
    combustible que el avion puede gastar de verdad.
    """
    inicio = texto.lower().find("[fuel]")
    if inicio == -1:
        return None
    bloque = texto[inicio : inicio + 2000]
    tipo = int(_valor(bloque, "fuel_type") or 1)
    kg_gal = KG_POR_GALON.get(tipo, KG_POR_GALON[1])

    galones = 0.0
    for linea in bloque.splitlines()[1:]:
        if "=" not in linea or linea.strip().startswith(("fuel_type", "[")):
            continue
        partes = linea.split("=", 1)[1].split(";")[0].split(",")
        if len(partes) < 5:
            continue
        try:
            total, no_utilizable = float(partes[3]), float(partes[4])
        except ValueError:
            continue
        galones += max(0.0, total - no_utilizable)
    return galones * kg_gal if galones else None


def leer(raiz: Path, paquete: str) -> dict | None:
    patron = str(raiz / "Official" / "**" / paquete / "**" / "flight_model.cfg")
    encontrados = glob.glob(patron, recursive=True)
    if not encontrados:
        return None
    texto = Path(encontrados[0]).read_text(encoding="utf-8", errors="replace")
    mtow_lb = _valor(texto, "max_gross_weight")
    vacio_lb = _valor(texto, "empty_weight")
    return {
        "paquete": paquete,
        "mtow_kg": round(mtow_lb * LB_A_KG) if mtow_lb else None,
        "vacio_kg": round(vacio_lb * LB_A_KG) if vacio_lb else None,
        "combustible_util_kg": (
            round(_combustible_kg(texto)) if _combustible_kg(texto) else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raiz", type=Path, default=None, help="ruta de MSFS")
    args = parser.parse_args(argv)

    raiz = args.raiz or raiz_de_paquetes()
    if raiz is None or not raiz.exists():
        print("No se encontro la instalacion de MSFS.")
        print(f"Se busco en {USER_CFG}. Usa --raiz para indicarla a mano.")
        return 1

    print(f"MSFS en: {raiz}\n")
    print(f"{'avion':6} {'MTOW':>8} {'vacio':>8} {'comb.util':>10}  paquete")
    faltan = []
    for icao, paquete in PAQUETES.items():
        if paquete is None:
            faltan.append(f"{icao} (sin paquete declarado)")
            continue
        datos = leer(raiz, paquete)
        if datos is None:
            faltan.append(f"{icao} ({paquete} no instalado)")
            continue
        print(
            f"{icao:6} {datos['mtow_kg']!s:>8} {datos['vacio_kg']!s:>8} "
            f"{datos['combustible_util_kg']!s:>10}  {paquete}"
        )

    if faltan:
        print("\nSin datos del simulador (sus cifras salen del manual):")
        for f in faltan:
            print(f"  - {f}")
    print("\nTodo en kg. Copiar a client/config/aircraft.yaml, bloque `despacho`,")
    print("anotando fuente y fecha_consulta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
