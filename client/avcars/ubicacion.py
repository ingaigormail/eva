"""Comprobar que el avión está donde el plan dice que sale.

Un piloto puede declarar un plan LEMD-LEBL y aparecer cargado en las afueras
de Barcelona: el plan dice una cosa y el avión estaba en otra, y hasta ahora
nadie lo miraba. No hace falta mala fe — pasa igual cuando alguien carga mal
el escenario o se deja puesto el plan del vuelo anterior — pero el vuelo entra
torcido en la cartilla y luego cuesta mucho más deshacerlo que evitarlo.

Es de las pocas comprobaciones que se pueden hacer *antes* de grabar en vez
de deducirlas después analizando la traza.

Todo lo de aquí es cálculo puro: se le pasan las coordenadas y el diccionario
de aeropuertos, y devuelve un veredicto. Sin red, sin ficheros y sin ventanas,
para que se pueda probar sin simulador.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

#: Radio medio de la Tierra en millas náuticas. La comprobación es de "estás
#: en este aeródromo o no", con tolerancias de varias millas, así que un
#: modelo esférico sobra: el error del esferoide es de milésimas.
RADIO_TIERRA_NM = 3440.065

#: A partir de cuántas millas del aeródromo de salida se considera que el
#: avión no está ahí. FlyAnt usa 15 km (~8 NM) en su cliente; se recoge ese
#: orden de magnitud porque cubre un aeropuerto grande entero con margen,
#: sin llegar al siguiente. Es configurable: en aeródromos pequeños puede
#: interesar apretarlo.
TOLERANCIA_POR_DEFECTO_NM = 8.0


@dataclass(frozen=True)
class Comprobacion:
    """El resultado de mirar si el avión está en su aeródromo de salida.

    `conforme` en False es la única situación que merece avisar al piloto.
    Cuando no se puede comprobar (no hay ICAO, o no está en la lista de
    aeropuertos) se devuelve conforme=True a propósito: un hueco en los datos
    no puede impedirle volar a nadie.
    """

    conforme: bool
    #: Distancia al aeródromo declarado, o None si no se pudo calcular.
    distancia_nm: Optional[float]
    #: Por qué salió así, en una línea, para el aviso y para el registro.
    motivo: str

    @property
    def comprobada(self) -> bool:
        """Si de verdad se llegó a medir algo."""
        return self.distancia_nm is not None


def distancia_nm(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Distancia en millas náuticas entre dos puntos, por la fórmula del semiverseno."""
    fi1 = math.radians(lat1)
    fi2 = math.radians(lat2)
    dfi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dfi / 2) ** 2
        + math.cos(fi1) * math.cos(fi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * RADIO_TIERRA_NM * math.asin(min(1.0, math.sqrt(a)))


def comprobar_salida(
    lat: Optional[float],
    lon: Optional[float],
    icao: str,
    aeropuertos: dict,
    tolerancia_nm: float = TOLERANCIA_POR_DEFECTO_NM,
) -> Comprobacion:
    """¿Está el avión en el aeródromo `icao`?

    `aeropuertos` es el diccionario de `config.load_airports()`: designador
    OACI -> {name, lat, lon, iata}. Trae 17.800 aeropuertos de todo el mundo,
    así que la comprobación no se queda solo en España.

    Devuelve conforme=True siempre que no se pueda afirmar lo contrario. Los
    cuatro casos en los que no se puede afirmar nada:

    - el plan no trae origen;
    - el origen no está en la lista de aeropuertos;
    - la entrada del aeropuerto no tiene coordenadas;
    - el simulador todavía no da posición.

    El caso de posición 0,0 se trata aparte: no es que falte el dato, es que
    el simulador está en el menú y aún no ha cargado el vuelo. Tampoco se
    bloquea, pero se dice, porque el mensaje útil ahí es otro.
    """
    if not icao:
        return Comprobacion(True, None, "el plan no trae aeródromo de salida")

    icao = icao.strip().upper()
    ficha = aeropuertos.get(icao)
    if not ficha:
        return Comprobacion(
            True, None, f"{icao} no está en la lista de aeropuertos"
        )

    destino_lat = ficha.get("lat")
    destino_lon = ficha.get("lon")
    if destino_lat is None or destino_lon is None:
        return Comprobacion(True, None, f"{icao} no tiene coordenadas")

    if lat is None or lon is None:
        return Comprobacion(True, None, "el simulador no da posición todavía")

    # Coordenadas 0,0 es el golfo de Guinea, y ningún vuelo de EvA sale de
    # ahí: el simulador las devuelve mientras está en el menú, antes de
    # cargar. Distinguirlo evita decirle a alguien que está a 3.000 millas
    # de Madrid cuando lo que pasa es que no ha entrado al vuelo.
    if round(lat, 2) == 0.0 and round(lon, 2) == 0.0:
        return Comprobacion(
            True, None, "el simulador está en el menú, sin vuelo cargado"
        )

    distancia = distancia_nm(lat, lon, destino_lat, destino_lon)
    if distancia <= tolerancia_nm:
        return Comprobacion(True, distancia, f"a {distancia:.1f} NM de {icao}")

    return Comprobacion(
        False,
        distancia,
        f"a {distancia:.0f} NM de {icao}, que es el origen del plan",
    )
