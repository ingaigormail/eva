"""Lo que un vuelo deja en el bolsillo del piloto.

Un sitio y solo uno donde se calcula el dinero. Las tarifas viven en
`config/economia.yaml` y se pueden pisar en vivo desde `/gestion/reglas`; aquí
está la aritmética que las usa.

QUE SE COBRA Y QUE NO
---------------------
Se cobra por pasajero-milla y por kilo-milla, pero **el grabador todavía no
registra ni pasajeros ni carga** (ver el comentario de `vuelos_resumen` en
`cuentas.py`). Así que hoy todos los vuelos facturan solo la base por milla.
No se estima un pasaje que nadie ha contado: un ingreso inventado descuadraría
la clasificación mensual, que es lo único que los pilotos miran de verdad.

El día que el grabador guarde esos dos números, `pasajeros` y `carga_kg` dejan
de ser cero y esta función ya sabe qué hacer con ellos: no hay nada más que
tocar.

ALQUILADO O PROPIO
------------------
La hora de avión es el coste gordo. Quien ha comprado el avión paga solo
`mantenimiento_pct` de esa hora; quien no, la paga entera. Es toda la ventaja
de comprar, y por eso la compra tarda en amortizarse.
"""
from __future__ import annotations

from typing import Optional

#: Un vuelo que no se ha podido juzgar no mueve dinero, ni a favor ni en
#: contra: no es una trampa, es un problema técnico.
SIN_MOVIMIENTO = "no_evaluable"


def _num(valor, por_defecto: float = 0.0) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return por_defecto


def tarifa_hora(
    designador: str, economia: dict, *, es_propio: bool
) -> float:
    """Lo que cuesta una hora de ese avión, según sea propio o alquilado."""
    horas = (economia.get("costes") or {}).get("hora_avion") or {}
    alquiler = _num(horas.get((designador or "").upper()))
    if not es_propio:
        return alquiler
    pct = _num((economia.get("compra_aviones") or {}).get("mantenimiento_pct"), 0.25)
    return round(alquiler * pct, 2)


def _combustible_kg(
    vuelo: dict, aviones: dict, economia: dict, horas: float
) -> tuple[float, bool]:
    """Kilos gastados. Devuelve también si hubo que estimarlos."""
    real = vuelo.get("combustible_usado_kg")
    if real is not None:
        return _num(real), False

    costes = economia.get("costes") or {}
    if not costes.get("estimar_combustible_si_falta", True):
        return 0.0, False

    # Un CSV de fstelemetry no trae el consumo. Cobrar cero premiaría al que
    # graba con la herramienta pobre, así que se estima con el consumo de
    # despacho del avión.
    ficha = aviones.get((vuelo.get("aeronave") or "").upper()) or {}
    por_hora = _num((ficha.get("despacho") or {}).get("consumo_kg_h"))
    return round(por_hora * horas, 1), True


def _tasas(vuelo: dict, economia: dict, tamano_aerodromo) -> float:
    """Tasas de salida y llegada, según el tamaño de cada aeródromo."""
    tabla = ((economia.get("costes") or {}).get("tasas")) or {}
    desconocido = _num(tabla.get("desconocido"), 40.0)

    total = 0.0
    for icao in (vuelo.get("origen"), vuelo.get("destino")):
        if not icao:
            total += desconocido
            continue
        tamano = tamano_aerodromo(icao) if tamano_aerodromo else None
        total += _num(tabla.get(tamano), desconocido) if tamano else desconocido
    return total


def _multiplicador_calidad(calidad: Optional[str], economia: dict) -> float:
    tabla = economia.get("calidad") or {}
    if not calidad:
        # Un .csv no pasa por el motor: no hay veredicto que aplicar.
        return _num(tabla.get(SIN_MOVIMIENTO), 0.0)
    return _num(tabla.get(calidad), 0.0)


def _bonificacion(vuelo: dict, economia: dict) -> float:
    """Suma de extras sobre el ingreso, con el tope del fichero."""
    bonus = economia.get("bonus") or {}
    total = 0.0
    if (vuelo.get("red") or "").upper() in ("VATSIM", "IVAO"):
        total += _num(bonus.get("vatsim"))
    if vuelo.get("control_atc"):
        total += _num(bonus.get("atc_controlado"))
    if (vuelo.get("perfil_evaluacion") or "").lower() == "hard":
        total += _num(bonus.get("perfil_dificil"))
    return min(total, _num(bonus.get("tope"), total))


def calcular(
    vuelo: dict,
    economia: dict,
    *,
    aviones: Optional[dict] = None,
    es_propio: bool = False,
    tamano_aerodromo=None,
) -> dict:
    """Desglose económico de un vuelo. Nunca lanza: un vuelo raro vale cero.

    `vuelo` es una fila de `vuelos_resumen` (o cualquier dict con esas claves).
    `tamano_aerodromo` es una función `icao -> 'large'|'medium'|'small'|None`;
    sin ella, todo aeródromo paga la tasa de «desconocido».
    """
    aviones = aviones or {}
    ingresos_cfg = economia.get("ingresos") or {}

    distancia = max(
        _num(vuelo.get("distancia_nm")),
        _num(ingresos_cfg.get("distancia_minima_nm"), 0.0),
    )
    horas = _num(vuelo.get("duracion_min")) / 60.0

    # -- ingresos ------------------------------------------------------
    # `pasajeros` y `carga_kg` son cero mientras el grabador no los registre.
    pasajeros = _num(vuelo.get("pasajeros"))
    carga_kg = _num(vuelo.get("carga_kg"))
    bruto = (
        pasajeros * _num(ingresos_cfg.get("tarifa_pasajero_nm")) * distancia
        + carga_kg * _num(ingresos_cfg.get("tarifa_kg_nm")) * distancia
        + _num(ingresos_cfg.get("base_nm")) * distancia
    )

    calidad = vuelo.get("calidad")
    multiplicador = _multiplicador_calidad(calidad, economia)
    bonificacion = _bonificacion(vuelo, economia)
    ingreso = round(bruto * multiplicador * (1 + bonificacion), 2)

    # -- costes --------------------------------------------------------
    # Un vuelo no evaluable no mueve dinero en ningún sentido: cobrarle los
    # costes castigaría al piloto por un fallo del grabador.
    if multiplicador == 0 and calidad in (None, SIN_MOVIMIENTO):
        return {
            "ingreso": 0.0, "coste": 0.0, "neto": 0.0,
            "bruto": round(bruto, 2), "multiplicador_calidad": multiplicador,
            "bonificacion": bonificacion, "sin_movimiento": True,
            "desglose_costes": {}, "combustible_estimado": False,
        }

    costes_cfg = economia.get("costes") or {}
    kg, estimado = _combustible_kg(vuelo, aviones, economia, horas)
    combustible = round(kg * _num(costes_cfg.get("precio_combustible_kg")), 2)
    tasas = _tasas(vuelo, economia, tamano_aerodromo)
    handling = _num(costes_cfg.get("handling"))
    hora = round(
        tarifa_hora(vuelo.get("aeronave") or "", economia, es_propio=es_propio)
        * horas,
        2,
    )

    desglose = {
        "combustible": combustible,
        "tasas": tasas,
        "handling": handling,
        "hora_avion": hora,
    }
    coste = round(sum(desglose.values()), 2)

    return {
        "ingreso": ingreso,
        "coste": coste,
        "neto": round(ingreso - coste, 2),
        "bruto": round(bruto, 2),
        "multiplicador_calidad": multiplicador,
        "bonificacion": bonificacion,
        "sin_movimiento": False,
        "desglose_costes": desglose,
        "combustible_estimado": estimado,
    }
