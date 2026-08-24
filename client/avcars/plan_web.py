"""El plan de vuelo que el piloto preparó en la web de EvA.

Sin esto, EvA Airliner solo sabía de dónde a dónde vuela mirando el `.PLN`
cargado en MSFS o lo que el piloto hubiera escrito a mano en las
preferencias: el plan hecho en la web (origen, destino, aeronave, nivel)
no llegaba al grabador de ninguna manera, y decía «Sin plan de vuelo
declarado» aunque acabara de prepararlo y mandarlo a VATSIM.

Se identifica con la **clave del grabador**, que el piloto genera en
`/descargar` y pega una vez en las preferencias. No es su contraseña: es de
solo lectura, solo abre este dato y se puede anular desde la web (ver
`cuentas.generar_clave_grabador`).

Nada de aquí interrumpe nunca al grabador: si no hay clave, no hay red, el
servidor tarda o responde cualquier cosa rara, se devuelve `None` y el
grabador sigue con el `.PLN` o las preferencias, como antes.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

#: Corto a propósito: esto se consulta al abrir el grabador y al refrescar
#: la cabecera. El piloto está a punto de volar; no puede quedarse mirando
#: una ventana congelada porque el servidor vaya lento.
TIMEOUT_S = 4.0


@dataclass
class PlanWeb:
    """Lo que hace falta para la cabecera y el vuelo grabado."""

    origen: str = ""
    destino: str = ""
    alterno: str = ""
    aeronave: str = ""
    callsign: str = ""
    ruta: str = ""
    reglas: str = ""
    nivel_ft: Optional[int] = None
    actualizado: str = ""

    @property
    def completo(self) -> bool:
        return bool(self.origen and self.destino)


def _entero(valor: object) -> Optional[int]:
    try:
        return int(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _icao(valor: object) -> str:
    return str(valor or "").strip().upper()[:4]


def obtener_clave(eva_url: str, license_id: str, password: str) -> tuple[str, str]:
    """Cambia las credenciales del piloto por su clave del grabador.

    Devuelve `(clave, mensaje_de_error)`: con la clave puesta, el error va
    vacío, y al revés. **La contraseña no se guarda en ninguna parte** — se
    usa solo para esta petición y se olvida; lo único que el grabador
    escribe en disco es la clave que sale de aquí.
    """
    eva_url = (eva_url or "").strip().rstrip("/")
    if not eva_url:
        return "", "Falta la dirección del servidor de EvA."
    if not license_id or not password:
        return "", "Hacen falta el ID de piloto y la contraseña."

    cuerpo = json.dumps(
        {"license_id": license_id, "password": password}
    ).encode("utf-8")
    peticion = urllib.request.Request(
        f"{eva_url}/api/grabador/login",
        data=cuerpo,
        headers={"Content-Type": "application/json", "User-Agent": "EvA-Airliner"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_S) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return "", "ID de piloto o contraseña incorrectos."
        if exc.code == 429:
            return "", "Demasiados intentos. Espera un rato y vuelve a probar."
        return "", f"El servidor respondió {exc.code}."
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return "", "No se pudo contactar con el servidor de EvA."

    clave = str((datos or {}).get("clave") or "")
    if not clave:
        return "", "El servidor no devolvió ninguna clave."
    return clave, ""


def ultimo_plan(eva_url: str, clave: str) -> Optional[PlanWeb]:
    """El último plan guardado por ese piloto, o None si no se pudo saber.

    `None` cubre a propósito todos los casos en los que no hay un dato
    fiable — sin clave, sin red, clave anulada, el piloto no ha guardado
    ningún plan todavía — porque el grabador reacciona igual a todos: tirar
    de las otras fuentes y no inventarse una ruta.
    """
    eva_url = (eva_url or "").strip().rstrip("/")
    clave = (clave or "").strip()
    if not eva_url or not clave:
        return None

    peticion = urllib.request.Request(
        f"{eva_url}/api/grabador/plan",
        headers={"X-EvA-Clave": clave, "User-Agent": "EvA-Airliner"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_S) as respuesta:
            if respuesta.status != 200:
                return None
            cuerpo = json.loads(respuesta.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None

    if not isinstance(cuerpo, dict):
        return None
    plan = cuerpo.get("plan")
    if not isinstance(plan, dict):
        return None   # `plan: null` = el piloto aún no ha guardado ninguno

    return PlanWeb(
        origen=_icao(plan.get("origen")),
        destino=_icao(plan.get("destino")),
        alterno=_icao(plan.get("alterno")),
        aeronave=str(plan.get("aeronave") or "").strip(),
        callsign=str(plan.get("callsign") or "").strip().upper(),
        ruta=str(plan.get("ruta") or "").strip(),
        reglas=str(plan.get("reglas") or "").strip().upper(),
        nivel_ft=_entero(plan.get("nivel")),
        actualizado=str(plan.get("actualizado") or ""),
    )
