"""Estadísticas públicas de VATSIM por CID.

Dos endpoints del Core API de VATSIM, verificados en vivo el 2026-08-24:
NO hacen falta credenciales ni clave de API, a pesar de que la
documentación (vatsim.dev) da a entender que el Core API en general sí las
pide — esa restricción es solo para los datos de roster de una división,
no para estos dos endpoints concretos, comprobado con una petición real
antes de escribir este módulo (ver memoria del proyecto).

    GET https://api.vatsim.net/v2/members/{cid}/stats
    GET https://api.vatsim.net/v2/members/{cid}/flightplans   (últimos 50)

No confundir con la "Slurper API" que ya usa `dashboard.py`
(`check_vatsim_connection`): esa dice si el piloto está conectado AHORA
MISMO; esto da su histórico (horas totales, planes presentados).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional

BASE_URL = "https://api.vatsim.net/v2/members/{cid}"

#: Corto a propósito: esto se llama desde una pantalla de administración
#: que no puede quedarse colgada porque VATSIM vaya lento. Un piloto sin
#: dato disponible se enseña como "—", nunca rompe la página.
TIMEOUT_S = 4.0


def _get_json(url: str) -> Optional[object]:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def horas_piloto(cid: str) -> Optional[float]:
    """Horas totales acumuladas como piloto en VATSIM, o None si no se
    pudo consultar (CID vacío, VATSIM no responde, CID no existe)."""
    cid = (cid or "").strip()
    if not cid.isdigit():
        return None
    datos = _get_json(BASE_URL.format(cid=cid) + "/stats")
    if not isinstance(datos, dict):
        return None
    valor = datos.get("pilot")
    return float(valor) if isinstance(valor, (int, float)) else None


def vuelos_recientes(cid: str, dias: int = 30) -> Optional[int]:
    """Cuántos planes de vuelo presentó en los últimos `dias` días.

    Es "planes presentados" (`filed`), no "vuelos realizados": VATSIM no
    da lo segundo por API pública. Se cuenta sobre los últimos 50 que
    devuelve el endpoint — de sobra para una ventana de 30 días salvo un
    piloto extremadamente activo, y no se inventa un número si el CID no
    es válido o VATSIM no responde.
    """
    cid = (cid or "").strip()
    if not cid.isdigit():
        return None
    planes = _get_json(BASE_URL.format(cid=cid) + "/flightplans")
    if not isinstance(planes, list):
        return None
    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    contador = 0
    for plan in planes:
        if not isinstance(plan, dict):
            continue
        filed = plan.get("filed")
        if not filed:
            continue
        try:
            fecha = datetime.fromisoformat(str(filed).replace("Z", "+00:00"))
        except ValueError:
            continue
        if fecha >= limite:
            contador += 1
    return contador


def actividad_de_varios(cids: list[str]) -> dict[str, dict]:
    """`horas_piloto` + `vuelos_recientes` para varios CID a la vez.

    En paralelo (hilos, no procesos: es solo esperar a la red) para no
    sumar la latencia de VATSIM una vez por cada piloto — con 20 pilotos,
    uno detrás de otro serían varios segundos de carga en
    `/gestion/usuarios` solo por esto.
    """
    cids_validos = sorted({c.strip() for c in cids if (c or "").strip()})
    resultado: dict[str, dict] = {}
    if not cids_validos:
        return resultado

    def _uno(cid: str) -> tuple[str, dict]:
        return cid, {
            "horas_pv": horas_piloto(cid),
            "vuelos_vatsim_30d": vuelos_recientes(cid),
        }

    with ThreadPoolExecutor(max_workers=min(8, len(cids_validos))) as pool:
        futuros = [pool.submit(_uno, cid) for cid in cids_validos]
        for futuro in as_completed(futuros):
            cid, datos = futuro.result()
            resultado[cid] = datos
    return resultado
