"""Cálculo de peso de despacho para `/plan` (D2).

No es POH y **no lo usa el motor de evaluación**. `aircraft.yaml` sigue
sin OEW ni consumo verificados (DAT-11). Hasta que existan, el semáforo
usa estas estimaciones de despacho, etiquetadas como tal en la UI.

Combustible = tiempo del plan (EET + 30 min VFR, o la autonomía si el
piloto la rellena) × consumo horario, tope el combustible útil.
TOW = OEW + piloto + pasajeros + carga + combustible, frente al MTOW.
"""
from __future__ import annotations

from typing import Optional

PESO_PERSONA_KG = 85  # DAT-09: masa estándar del planificador
RESERVA_VFR_MIN = 30  # reserva diurna SERA, no dato de avión
MARGEN_JUSTO_FRACCION = 0.02  # ≤ 2 % del MTOW restante = "va justo"

# Estimación de despacho. No copiar a aircraft.yaml ni al motor.
# Claves: oew_kg, combustible_util_kg, consumo_kg_h, plazas (incluye piloto).
ESTIMACION: dict[str, dict] = {
    "C172": {
        "oew_kg": 620,
        "combustible_util_kg": 100,
        "consumo_kg_h": 22,
        "plazas": 4,
    },
    "C208": {
        "oew_kg": 2100,
        "combustible_util_kg": 1000,
        "consumo_kg_h": 180,
        "plazas": 10,
    },
    "BE58": {
        "oew_kg": 1750,
        "combustible_util_kg": 370,
        "consumo_kg_h": 70,
        "plazas": 6,
    },
    # Anadido el 2026-08-28: era el unico avion de la flota que no aparecia
    # en la tabla de pesos de /plan. Cifras de la ficha tecnica oficial de
    # Diamond (diamondaircraft.com, DA62 > Technical Specifications):
    #   vacio sin opcionales 1598 kg | util max 702 kg | MTOM 2300 kg
    #   combustible utilizable: principal 151 kg + auxiliar 110 kg = 261 kg
    #   consumo al 60% a 12.000 ft: 44,7 l/h -> ~36 kg/h (Jet-A, 0,80 kg/l)
    "DA62": {
        # 1650 y no los 1598 de catalogo: esa cifra es "sin opcionales" y
        # cualquier avion equipado pesa mas. Cargar el mas ligero posible
        # haria que el semaforo avisara tarde, que es el error que no
        # interesa cometer en un calculo de peso.
        "oew_kg": 1650,
        "combustible_util_kg": 261,
        "consumo_kg_h": 36,
        "plazas": 7,
    },
    "TBM9": {
        "oew_kg": 2100,
        "combustible_util_kg": 1100,
        "consumo_kg_h": 230,
        "plazas": 6,
    },
    "B350": {
        "oew_kg": 4400,
        "combustible_util_kg": 1600,
        "consumo_kg_h": 360,
        "plazas": 11,
    },
    "DHC6": {
        "oew_kg": 3400,
        "combustible_util_kg": 1400,
        "consumo_kg_h": 280,
        "plazas": 19,
    },
    "C25C": {
        "oew_kg": 4660,
        "combustible_util_kg": 2090,
        "consumo_kg_h": 410,
        "plazas": 10,
    },
}


def mtow_kg(ficha: dict) -> Optional[float]:
    """El MTOW del avión, mirando en los tres sitios donde puede estar.

    `aircraft.yaml` no guarda el MTOW en un único sitio: la mayoría de los
    aviones lo tienen en `referencia_atc`, pero el TBM 930 lo tiene en un
    bloque `pesos` con las cifras del manual (MTOW, máximo en rampa, máximo
    al aterrizar, máximo sin combustible). Mirar solo en `referencia_atc`
    dejaba al TBM sin MTOW, y sin MTOW la tabla de pesos de `/plan` se
    quedaba entera en "—": el piloto tocaba pasajeros y carga y no cambiaba
    nada. Arreglado el 2026-08-28.

    `pesos` va primero porque son datos de manual, que mandan sobre la ficha
    de referencia para ATC. Hoy solo el TBM lo tiene, así que el orden no
    cambia el valor de ningún otro avión.
    """
    for bloque, clave in (
        ("pesos", "mtow_kg"),
        ("referencia_atc", "mtow_kg"),
        ("referencia_sim", "mtow_kg"),
    ):
        datos = ficha.get(bloque) or {}
        if isinstance(datos, dict) and datos.get(clave):
            return float(datos[clave])
    return None


def datos_para_plantilla(flota: dict) -> dict[str, dict]:
    """MTOW real del yaml + estimación de despacho, solo si hay ambos."""
    salida: dict[str, dict] = {}
    for icao, ficha in flota.items():
        mtow = mtow_kg(ficha) if isinstance(ficha, dict) else None
        estimacion = ESTIMACION.get(icao)
        if mtow is None or estimacion is None:
            continue
        salida[icao] = {
            "mtow_kg": mtow,
            **estimacion,
        }
    return salida


def minutos_de_combustible(
    eet_min: Optional[int],
    autonomia_min: Optional[int],
) -> Optional[int]:
    """Autonomía del plan si está; si no, EET + reserva VFR 30 min."""
    if autonomia_min is not None and autonomia_min > 0:
        return autonomia_min
    if eet_min is not None and eet_min > 0:
        return eet_min + RESERVA_VFR_MIN
    return None


def combustible_kg(
    minutos: int,
    consumo_kg_h: float,
    combustible_util_kg: float,
) -> float:
    kg = (minutos / 60.0) * consumo_kg_h
    return min(kg, combustible_util_kg)


def clasificar_peso(tow_kg: float, mtow_kg: float) -> str:
    """sobrepeso | justo | ok."""
    if tow_kg > mtow_kg:
        return "sobrepeso"
    margen = mtow_kg - tow_kg
    umbral_justo = max(15.0, MARGEN_JUSTO_FRACCION * mtow_kg)
    if margen <= umbral_justo:
        return "justo"
    return "ok"
