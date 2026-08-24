"""Estado editable en vivo de las reglas: activo/inactivo y umbrales.

Separado de `reglas_info.py` (la ficha descriptiva, estática) y de
`scoring.py` (la lógica de las reglas). Este módulo es el único sitio que
sabe leer y escribir la configuración *efectiva* que usa el motor: activar
o desactivar una regla, o pisar uno de sus umbrales sin tocar el perfil de
dificultad versionado (`config/profiles.yaml`).

Por qué en fichero aparte y no escribiendo `profiles.yaml` directamente:
`profiles.yaml` va en el repositorio y se despliega con el código —
escribir ahí en producción dejaría un fichero versionado modificado a mano
en el servidor, mezclando "lo que trae el código" con "lo que ha tocado un
administrador en vivo" (el mismo problema que ya se evitó con
`eva.db`/`importados.json`, que tampoco van en git). Aquí solo se guardan
las DIFERENCIAS respecto al perfil base: qué reglas se han activado o
desactivado a mano, y qué umbrales se han pisado. Sin diferencias, el motor
se comporta exactamente igual que con el `profiles.yaml` de siempre.

Todas las lecturas son en vivo (sin caché): guardar un cambio y volver a
leer en la misma petición ya ve el cambio, que es justo la garantía que
pide `docs/README.md` de que esta pieza no pueda desincronizarse en
silencio con lo que evalúa el motor.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

# client/avcars/evaluation/reglas_config.py -> avcars -> client -> raíz -> web/data/
_DIRECTORIO_POR_DEFECTO = Path(__file__).resolve().parents[3] / "web" / "data"
RUNTIME_CONFIG_PATH = _DIRECTORIO_POR_DEFECTO / "reglas_config.json"


def _leer(path: Path) -> dict:
    try:
        datos = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = {}
    if not isinstance(datos, dict):
        datos = {}
    datos.setdefault("activo", {})
    datos.setdefault("umbral", {})
    return datos


def _guardar(path: Path, datos: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(".tmp")
    temporal.write_text(
        json.dumps(datos, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporal.replace(path)


def cargar_overrides(path: Path = RUNTIME_CONFIG_PATH) -> dict:
    """`{"activo": {regla_id: bool}, "umbral": {"ruta.punteada": valor}}`."""
    return _leer(path)


def regla_activa(regla_id: str, overrides: dict) -> bool:
    """Activa por defecto: una regla nueva participa hasta que alguien la apague."""
    return bool(overrides.get("activo", {}).get(regla_id, True))


def _navegar(d: dict, ruta: str) -> Optional[Any]:
    nodo: Any = d
    for parte in ruta.split("."):
        if not isinstance(nodo, dict) or parte not in nodo:
            return None
        nodo = nodo[parte]
    return nodo


def _escribir(d: dict, ruta: str, valor: Any) -> None:
    partes = ruta.split(".")
    nodo = d
    for parte in partes[:-1]:
        nodo = nodo.setdefault(parte, {})
    nodo[partes[-1]] = valor


def valor_efectivo(perfil_base: dict, ruta: str, overrides: dict) -> Optional[Any]:
    """El valor que de verdad usa el motor para `ruta`: override si existe, si no el del perfil."""
    umbral = overrides.get("umbral", {})
    if ruta in umbral:
        return umbral[ruta]
    return _navegar(perfil_base, ruta)


def perfil_efectivo(perfil_base: dict, overrides: dict) -> dict:
    """El perfil que de verdad usa el motor: perfil_base + overrides guardados.

    Nunca muta `perfil_base` — puede ser el dict cargado una vez en memoria
    (`PROFILES` en `web/app.py`) y reutilizado en cada petición.
    """
    resultado = copy.deepcopy(perfil_base)
    for ruta, valor in overrides.get("umbral", {}).items():
        _escribir(resultado, ruta, valor)
    return resultado


def reglas_activas_dict(overrides: dict) -> dict:
    """El `{regla_id: bool}` que espera `scoring.evaluate_flight(reglas_activas=...)`."""
    return dict(overrides.get("activo", {}))


def guardar_activo(regla_id: str, activo: bool, path: Path = RUNTIME_CONFIG_PATH) -> dict:
    datos = _leer(path)
    datos["activo"][regla_id] = bool(activo)
    _guardar(path, datos)
    return datos


def guardar_umbral(ruta: str, valor: Any, path: Path = RUNTIME_CONFIG_PATH) -> dict:
    datos = _leer(path)
    datos["umbral"][ruta] = valor
    _guardar(path, datos)
    return datos


def quitar_override_umbral(ruta: str, path: Path = RUNTIME_CONFIG_PATH) -> dict:
    """Vuelve al valor del perfil versionado para esa ruta (deja de pisarlo)."""
    datos = _leer(path)
    datos["umbral"].pop(ruta, None)
    _guardar(path, datos)
    return datos
