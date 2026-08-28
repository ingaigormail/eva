"""Detecta si un vuelo se metió en una zona en la que no debía estar.

Qué hace falta para acusar a alguien
------------------------------------
Decir "invadiste la P de Torrejón" es una acusación, y una acusación falsa
destruye la confianza en todo el sistema de puntuación mucho más de lo que la
falta de la regla la construye. Así que una invasión solo cuenta si se cumplen
las tres a la vez:

1. El avión está **dentro** del polígono.
2. Está a más de un **margen** del borde. Los límites publicados y los que
   dibuja el simulador no coinciden al metro, y rozar una esquina no es entrar.
3. Se mantiene así de forma **continuada** un tiempo mínimo. Cruzar un pico
   durante dos segundos no es lo mismo que atravesar la zona.

Y si no se puede saber, no se acusa: una zona cuya referencia vertical no se
entiende se deja fuera y se dice, en vez de suponer.

Ojo con el muestreo
-------------------
La traza guarda 1 punto/s por debajo de 1.500 ft AGL pero **1 cada 10 s en
crucero** (ver `recorder/flight_log_writer.py`). Justo donde ocurren las
invasiones es donde menos resolución hay: a 120 kt son 330 m entre muestras.
Por eso esto detecta travesías, no roces, y por eso el resultado es indicio y
no prueba.

Todo lo de aquí es cálculo puro salvo `cargar_zonas()`, que es la única que
toca disco.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

#: Capas de `aeronautica.db` en las que un vuelo VFR no debería entrar. No
#: están las CTR ni las ATZ: entrar ahí es normal y legal con autorización,
#: y el motor no sabe si la hubo. Ver docs/datos_espacio_aereo_enaire.md
CAPAS_PROHIBIDAS = ("D_P_R", "PROHIBIDO_VFR", "NO_SOBREVUELO")

#: Un grado de latitud son 60 NM. Para longitud hay que multiplicar por el
#: coseno de la latitud, cosa que se hace donde toca.
NM_POR_GRADO = 60.0

#: Referencias verticales de ENAIRE y contra qué altitud se comparan.
#: STD es nivel de vuelo: por encima de la altitud de transición coincide con
#: la presión estándar, y en España esa transición está lo bastante alta como
#: para que un VFR rara vez la cruce. Se compara contra la altitud sobre el
#: mar, que es la aproximación honesta; para zonas bajas da igual.
REFERENCIA_MSL = ("HEIS", "ALT", "STD")
REFERENCIA_AGL = ("HEIG", "HEI")


@dataclass(frozen=True)
class Zona:
    """Una zona con su geometría y sus límites verticales ya resueltos."""

    ident: str
    nombre: str
    capa: str
    #: Lista de polígonos; cada polígono es una lista de anillos; el primer
    #: anillo es el contorno y los demás son huecos.
    poligonos: tuple
    #: Caja envolvente (lat_min, lon_min, lat_max, lon_max), para descartar
    #: rápido sin recorrer los vértices.
    caja: tuple
    suelo_ft: Optional[float]
    techo_ft: Optional[float]
    #: Contra qué se comparan: "msl", "agl" o None si no se ha entendido.
    referencia: Optional[str]

    @property
    def etiqueta(self) -> str:
        nombre = (self.nombre or "").strip()
        ident = (self.ident or "").strip()
        if nombre and ident and nombre != ident:
            return f"{ident} ({nombre})"
        return nombre or ident or self.capa


@dataclass
class Invasion:
    """Un tramo continuado dentro de una zona."""

    zona: Zona
    t_entrada: float
    t_salida: float
    muestras: int
    #: Lo más adentro que llegó, en millas desde el borde.
    profundidad_nm: float
    #: Altitud a la que iba en el punto más profundo.
    altitud_ft: float

    @property
    def duracion_s(self) -> float:
        return self.t_salida - self.t_entrada


# -- geometría --------------------------------------------------------


def _dentro_del_anillo(lat: float, lon: float, anillo: Sequence) -> bool:
    """Lanzamiento de rayo. `anillo` son pares (lon, lat), como en GeoJSON.

    Sin dependencias: meter shapely obligaría a empaquetarla en el ejecutable
    del cliente para una función de veinte líneas.
    """
    dentro = False
    n = len(anillo)
    j = n - 1
    for i in range(n):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if (yi > lat) != (yj > lat):
            corte = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < corte:
                dentro = not dentro
        j = i
    return dentro


def _dentro_del_poligono(lat: float, lon: float, poligono: Sequence) -> bool:
    """Dentro del contorno y fuera de todos los huecos."""
    if not poligono or not _dentro_del_anillo(lat, lon, poligono[0]):
        return False
    return not any(
        _dentro_del_anillo(lat, lon, hueco) for hueco in poligono[1:]
    )


def _distancia_a_segmento_nm(
    lat: float, lon: float, a: Sequence, b: Sequence
) -> float:
    """Distancia de un punto a un segmento, en millas náuticas.

    Se trabaja en grados proyectados a millas: la longitud se encoge por el
    coseno de la latitud. A la escala de una zona (decenas de millas) el error
    de no usar geodésicas es despreciable, y aquí solo se compara contra un
    margen de una milla escasa.
    """
    escala = math.cos(math.radians(lat))
    px, py = lon * escala, lat
    ax, ay = a[0] * escala, a[1]
    bx, by = b[0] * escala, b[1]

    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        proyectado_x, proyectado_y = ax, ay
    else:
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        proyectado_x, proyectado_y = ax + t * dx, ay + t * dy

    return math.hypot(px - proyectado_x, py - proyectado_y) * NM_POR_GRADO


def distancia_al_borde_nm(lat: float, lon: float, zona: Zona) -> float:
    """Lo más cerca que está el punto de cualquier borde de la zona."""
    minima = float("inf")
    for poligono in zona.poligonos:
        for anillo in poligono:
            for i in range(len(anillo)):
                d = _distancia_a_segmento_nm(
                    lat, lon, anillo[i - 1], anillo[i]
                )
                if d < minima:
                    minima = d
    return minima


def dentro_lateralmente(lat: float, lon: float, zona: Zona) -> bool:
    lat_min, lon_min, lat_max, lon_max = zona.caja
    if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
        return False
    return any(_dentro_del_poligono(lat, lon, p) for p in zona.poligonos)


def dentro_verticalmente(
    alt_msl_ft: float, alt_agl_ft: Optional[float], zona: Zona
) -> Optional[bool]:
    """¿Está entre el suelo y el techo? None si no se puede afirmar.

    Devolver None y no False es deliberado: son casos distintos. False es
    "iba por encima de la zona"; None es "no lo sé", y de un no lo sé no sale
    una acusación.
    """
    if zona.referencia is None:
        return None
    if zona.referencia == "agl" and alt_agl_ft is None:
        return None

    altura = alt_agl_ft if zona.referencia == "agl" else alt_msl_ft
    if zona.suelo_ft is not None and altura < zona.suelo_ft:
        return False
    if zona.techo_ft is not None and altura > zona.techo_ft:
        return False
    return True


# -- detección --------------------------------------------------------


def invasiones(
    track: Iterable,
    zonas: Sequence[Zona],
    margen_nm: float = 0.5,
    permanencia_s: float = 20.0,
    muestras_minimas: int = 2,
) -> list[Invasion]:
    """Los tramos en los que el vuelo estuvo dentro de una zona, de verdad.

    `muestras_minimas` va aparte de `permanencia_s` porque un solo punto nunca
    puede demostrar permanencia, por muy separado que esté del siguiente: en
    crucero dos muestras ya son 10 segundos, y con una sola no se sabe si
    entró y salió o si se quedó.
    """
    puntos = list(track)
    encontradas: list[Invasion] = []

    for zona in zonas:
        abierta: list = []

        for punto in puntos:
            dentro = False
            profundidad = 0.0
            if dentro_lateralmente(punto.lat, punto.lon, zona):
                vertical = dentro_verticalmente(
                    punto.alt_msl_ft, getattr(punto, "alt_agl_ft", None), zona
                )
                if vertical:
                    profundidad = distancia_al_borde_nm(
                        punto.lat, punto.lon, zona
                    )
                    dentro = profundidad >= margen_nm

            if dentro:
                abierta.append((punto, profundidad))
                continue
            if abierta:
                invasion = _cerrar(zona, abierta, permanencia_s, muestras_minimas)
                if invasion is not None:
                    encontradas.append(invasion)
                abierta = []

        if abierta:
            invasion = _cerrar(zona, abierta, permanencia_s, muestras_minimas)
            if invasion is not None:
                encontradas.append(invasion)

    encontradas.sort(key=lambda i: i.t_entrada)
    return encontradas


def _cerrar(
    zona: Zona,
    tramo: list,
    permanencia_s: float,
    muestras_minimas: int,
) -> Optional[Invasion]:
    """Convierte un tramo abierto en invasión, si da la talla."""
    if len(tramo) < muestras_minimas:
        return None
    entrada = tramo[0][0].t
    salida = tramo[-1][0].t
    if salida - entrada < permanencia_s:
        return None

    punto, profundidad = max(tramo, key=lambda par: par[1])
    return Invasion(
        zona=zona,
        t_entrada=entrada,
        t_salida=salida,
        muestras=len(tramo),
        profundidad_nm=profundidad,
        altitud_ft=punto.alt_msl_ft,
    )


# -- carga ------------------------------------------------------------


def _referencia(codigo: Optional[str]) -> Optional[str]:
    codigo = (codigo or "").strip().upper()
    if codigo in REFERENCIA_MSL:
        return "msl"
    if codigo in REFERENCIA_AGL:
        return "agl"
    # HEISG mezcla las dos y OTHER no dice nada. Sin referencia no se juzga.
    return None


def _anillos(geometria: dict) -> tuple:
    """Normaliza GeoJSON a una tupla de polígonos, cada uno con sus anillos."""
    tipo = (geometria or {}).get("type")
    coords = (geometria or {}).get("coordinates") or []
    if tipo == "Polygon":
        return (tuple(tuple(tuple(p) for p in anillo) for anillo in coords),)
    if tipo == "MultiPolygon":
        return tuple(
            tuple(tuple(tuple(p) for p in anillo) for anillo in poligono)
            for poligono in coords
        )
    return ()


def _caja(poligonos: tuple) -> tuple:
    lats, lons = [], []
    for poligono in poligonos:
        for anillo in poligono:
            for lon, lat in ((p[0], p[1]) for p in anillo):
                lons.append(lon)
                lats.append(lat)
    if not lats:
        return (0.0, 0.0, -1.0, -1.0)  # caja imposible: nunca contiene nada
    return (min(lats), min(lons), max(lats), max(lons))


def cargar_zonas(
    db_path: Path, capas: Sequence[str] = CAPAS_PROHIBIDAS
) -> list[Zona]:
    """Lee las zonas de `aeronautica.db`. Lista vacía si no está la base.

    Devolver vacío y no reventar es a propósito: sin la base, la regla queda
    en `not_evaluated` y el vuelo se evalúa igual con las demás. Que falte un
    fichero de datos no puede tumbar la evaluación entera.
    """
    if not Path(db_path).exists():
        return []

    zonas: list[Zona] = []
    marcadores = ",".join("?" for _ in capas)
    with sqlite3.connect(db_path) as con:
        filas = con.execute(
            "SELECT capa, ident, nombre, lower_val, lower_code, upper_val, "
            f"upper_code, geom FROM elementos WHERE capa IN ({marcadores})",
            tuple(capas),
        ).fetchall()

    for capa, ident, nombre, suelo, suelo_cod, techo, techo_cod, geom in filas:
        poligonos = _anillos(json.loads(geom) if geom else {})
        if not poligonos:
            continue
        # El techo manda para la referencia: es el límite que un VFR roza. Si
        # no lo trae, se prueba con el del suelo.
        zonas.append(
            Zona(
                ident=ident or "",
                nombre=nombre or "",
                capa=capa,
                poligonos=poligonos,
                caja=_caja(poligonos),
                suelo_ft=suelo,
                techo_ft=techo,
                referencia=_referencia(techo_cod) or _referencia(suelo_cod),
            )
        )
    return zonas
