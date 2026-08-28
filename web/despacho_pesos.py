"""Cálculo de peso de despacho para `/plan` (D2).

**Los datos de la flota NO viven aquí.** Salen de `client/config/aircraft.yaml`,
bloque `despacho` de cada avión, que es el único sitio donde se guarda lo que
describe a una aeronave: pesos, velocidades, combustible y plazas.

Hasta el 2026-08-28 este módulo llevaba su propia tabla `ESTIMACION` escrita
en Python, y pasó lo que tenía que pasar con dos copias del mismo dato: se
desincronizaron sin que nadie se enterara. El C172 figuraba con 620 kg de
peso en vacío cuando el simulador modela 767, y el Baron con 1750 cuando el
simulador dice 1432. Aquí solo queda el **cálculo**, no los datos.

Combustible = tiempo del plan (EET + 30 min VFR, o la autonomía si el
piloto la rellena) × consumo horario, tope el combustible útil.
TOW = OEW + piloto + pasajeros + carga + combustible, frente al MTOW.
"""
from __future__ import annotations

from typing import Optional

PESO_PERSONA_KG = 85  # DAT-09: masa estándar del planificador
RESERVA_VFR_MIN = 30  # reserva diurna SERA, no dato de avión
MARGEN_JUSTO_FRACCION = 0.02  # ≤ 2 % del MTOW restante = "va justo"

#: Lo que un avión necesita tener en `aircraft.yaml` para poder despacharse.
#: Sin uno solo de estos campos no hay peso que calcular.
CAMPOS_DESPACHO = (
    "mtow_kg",
    "vacio_kg",
    "combustible_util_kg",
    "consumo_kg_h",
    "plazas",
)


def mtow_kg(ficha: dict) -> Optional[float]:
    """El MTOW del avión, por orden de autoridad.

    1. `despacho`: lo que modela el simulador. Manda, porque es la única
       cifra contra la que el piloto puede comprobar lo que ve en cabina.
    2. `pesos`: cifras del manual del avión.
    3. `referencia_atc` / `referencia_sim`: fichas de referencia.

    Que discrepen no es un error, y conviene no "arreglarlo": EUROCONTROL da
    1050 kg para el C172 (un 172N/P) y el simulador modela un 172S de
    1160 kg. Son aviones distintos, y para juzgar un vuelo manda el que se
    vuela de verdad.
    """
    for bloque in ("despacho", "pesos", "referencia_atc", "referencia_sim"):
        datos = ficha.get(bloque) or {}
        if isinstance(datos, dict) and datos.get("mtow_kg"):
            return float(datos["mtow_kg"])
    return None


def datos_de_despacho(ficha: dict) -> Optional[dict]:
    """El bloque `despacho` de un avión, solo si está completo.

    None si falta cualquier campo: media ficha da un total que parece bueno
    y no lo es, y es peor enseñar un peso equivocado que no enseñar ninguno.
    """
    datos = ficha.get("despacho")
    if not isinstance(datos, dict):
        return None
    if any(datos.get(campo) is None for campo in CAMPOS_DESPACHO):
        return None
    return datos


def datos_para_plantilla(flota: dict) -> dict[str, dict]:
    """Lo que necesita la tabla de pesos de `/plan`, avión por avión.

    Todo sale de `aircraft.yaml`. Un avión con la ficha incompleta se queda
    fuera y `/plan` lo dice, en vez de enseñar un peso a medias.

    `oew_kg` se llama así por historia en la plantilla; en el yaml el campo
    es `vacio_kg`. Se traduce aquí y no allí para no tocar la interfaz.
    """
    salida: dict[str, dict] = {}
    for icao, ficha in flota.items():
        if not isinstance(ficha, dict):
            continue
        datos = datos_de_despacho(ficha)
        if datos is None:
            continue
        salida[icao] = {
            "mtow_kg": float(datos["mtow_kg"]),
            "oew_kg": datos["vacio_kg"],
            "combustible_util_kg": datos["combustible_util_kg"],
            "consumo_kg_h": datos["consumo_kg_h"],
            "plazas": datos["plazas"],
            # Para que la interfaz pueda distinguir un dato leído del
            # simulador de uno de catálogo sin verificar (hoy, el DHC-6).
            "verificado": bool(datos.get("verificado")),
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
