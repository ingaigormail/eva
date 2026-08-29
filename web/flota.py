"""La flota de EvA: qué avión puede volar cada piloto y cómo está de salud.

Un avión por tipo, con matrícula (`EC-EVA`…`EC-EVH`). **Sin exclusiva**: si
dos pilotos eligen el mismo a la vez, vuelan los dos y el desgaste de ambos
se suma sobre la misma célula. Lo primero que hace abandonar una aerolínea
virtual es no poder volar cuando quieres.

Todo lo que describe a un avión sale de `client/config/aircraft.yaml`, bloque
`flota`. Aquí solo se combina con las horas voladas.

Ver `docs/desgaste_y_mantenimiento_tabla.md`.
"""
from __future__ import annotations

from typing import Optional

from avcars import cuentas

#: Orden de la escalera de habilitaciones. Un piloto puede volar todo lo que
#: esté en su categoría o por debajo.
ORDEN_CATEGORIAS = ["P0", "P1", "P2", "P3", "P4"]


def _nivel(categoria: str) -> int:
    """La posición de una categoría en la escalera. -1 si no se reconoce.

    Un piloto sin categoría entendible se trata como si no tuviera ninguna:
    solo ve lo que no exige nada. Es preferible a enseñarle un reactor por un
    dato corrupto.
    """
    try:
        return ORDEN_CATEGORIAS.index((categoria or "").strip().upper())
    except ValueError:
        return -1


def puede_volar(categoria_piloto: str, ficha_avion: dict) -> bool:
    """Si un piloto de esa categoría tiene permiso para ese avión."""
    exigida = (ficha_avion.get("flota") or {}).get("categoria_minima")
    if not exigida:
        # Un avión sin categoría declarada no se ofrece a nadie. Es la misma
        # prudencia que en el resto del proyecto: si no se puede afirmar que
        # alguien puede volarlo, no se le ofrece.
        return False
    return _nivel(categoria_piloto) >= _nivel(exigida)


def aviones_de(categoria_piloto: str, flota: dict) -> list[dict]:
    """Los aviones que ese piloto puede elegir, en orden de escalera.

    Filtrar en vez de rechazar: el piloto ve solo lo suyo en lugar de elegir
    un avión y recibir un error después. Idea tomada del cliente de FlyAnt.
    """
    salida = []
    for icao, ficha in flota.items():
        if not isinstance(ficha, dict) or not puede_volar(categoria_piloto, ficha):
            continue
        datos = ficha.get("flota") or {}
        salida.append(
            {
                "icao": icao,
                "nombre": ficha.get("nombre", icao),
                "matricula": datos.get("matricula", ""),
                "categoria_minima": datos.get("categoria_minima", ""),
            }
        )
    salida.sort(key=lambda a: (_nivel(a["categoria_minima"]), a["matricula"]))
    return salida


def horas_voladas(icao: str) -> float:
    """Horas acumuladas sobre esa célula, de todos los pilotos.

    Se cuenta por **tipo de avión** y no por matrícula porque hay una célula
    por tipo: las horas del C172 son las horas del EC-EVA. Cuando haya dos
    células del mismo tipo habrá que separar por matrícula, y entonces hará
    falta que el vuelo la traiga (hoy el simulador reporta el indicativo del
    piloto en ese campo, no la matrícula de la flota).
    """
    try:
        with cuentas.conexion() as con:
            fila = con.execute(
                "SELECT COALESCE(SUM(duracion_min), 0) AS m FROM vuelos_resumen "
                "WHERE UPPER(aeronave) = ?",
                (icao.upper(),),
            ).fetchone()
        return round((fila["m"] or 0) / 60.0, 1)
    except Exception:  # noqa: BLE001 — sin base, la flota sale a estrenar
        return 0.0


def salud(icao: str, economia: dict) -> dict:
    """Cómo está esa célula: horas, salud en %, y cuánto falta para la revisión.

    El desgaste sube con las horas y se pone a cero en cada revisión de 100 h,
    que va pagada por la provisión que aporta cada vuelo. Es un diente de
    sierra: **no bloquea nada**, solo se ve. Con una célula por tipo, dejar el
    C172 en tierra dejaría a todo el club sin C172.

    `desgaste.por_hora_pct` en `economia.yaml` dice cuánto cuesta una hora.
    """
    horas = horas_voladas(icao)
    cada = float(
        (economia.get("desgaste") or {}).get("horas_entre_revisiones", 100)
    ) or 100.0
    por_hora = float((economia.get("desgaste") or {}).get("por_hora_pct", 0.2))

    desde_revision = horas % cada
    porcentaje = max(0, min(100, round(100 - desde_revision * por_hora)))
    return {
        "horas": horas,
        "horas_desde_revision": round(desde_revision, 1),
        "horas_para_revision": round(cada - desde_revision, 1),
        "salud_pct": porcentaje,
        "estado": _estado(porcentaje),
    }


def _estado(porcentaje: int) -> str:
    """Etiqueta para pintar el semáforo. Los cortes van con el color, no con
    ninguna consecuencia: la salud no impide volar."""
    if porcentaje >= 90:
        return "buena"
    if porcentaje >= 75:
        return "usada"
    return "gastada"


def catalogo_de_compra(categoria_piloto: str, license_id: str,
                       flota: dict, economia: dict) -> list[dict]:
    """Los aviones que ese piloto puede comprar, con precio y si ya es suyo.

    Solo salen los de su categoría (o inferior) que tengan precio. El C172 no
    lleva precio a propósito: es el avión de entrada y va siempre alquilado.
    """
    compra = economia.get("compra_aviones") or {}
    precios = compra.get("precio") or {}
    horas = economia.get("costes", {}).get("hora_avion") or {}
    pct = float(compra.get("mantenimiento_pct", 0.25))
    mios = set(cuentas.aviones_de(license_id))

    salida = []
    for icao, ficha in flota.items():
        if not isinstance(ficha, dict) or icao not in precios:
            continue
        if not puede_volar(categoria_piloto, ficha):
            continue
        alquiler = float(horas.get(icao, 0))
        datos = ficha.get("flota") or {}
        salida.append(
            {
                "icao": icao,
                "nombre": ficha.get("nombre", icao),
                "matricula": datos.get("matricula", ""),
                "categoria_minima": datos.get("categoria_minima", ""),
                "plazas": (ficha.get("despacho") or {}).get("plazas"),
                "precio": float(precios[icao]),
                "alquiler_hora": alquiler,
                "mantenimiento_hora": round(alquiler * pct, 2),
                "es_mio": icao in mios,
            }
        )
    salida.sort(key=lambda a: a["precio"])
    return salida


def precio_de_compra(icao: str, economia: dict) -> Optional[float]:
    """Lo que cuesta ese avión, o None si no está a la venta."""
    precios = (economia.get("compra_aviones") or {}).get("precio") or {}
    if icao not in precios:
        return None
    return float(precios[icao])


def ficha_de(icao: str, flota: dict, economia: dict) -> Optional[dict]:
    """Matrícula y salud de la célula de ese tipo, para enseñarla en `/plan`."""
    ficha = flota.get(icao)
    if not isinstance(ficha, dict):
        return None
    datos = ficha.get("flota") or {}
    if not datos.get("matricula"):
        return None
    return {
        "icao": icao,
        "nombre": ficha.get("nombre", icao),
        "matricula": datos["matricula"],
        **salud(icao, economia),
    }
