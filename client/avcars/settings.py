"""Preferencias de la aplicación EvA.

Se guardan en `eva.config.json`, junto al ejecutable, para que el piloto
pueda verlas y editarlas si quiere. No hay que confundirlas con
`config/profiles.yaml`, que son los umbrales del motor de evaluación: eso es
cosa de la aerolínea, esto es cosa del piloto.

Principio de diseño: **un fichero de configuración roto nunca debe impedir
que EvA arranque**. Si falta un campo, tiene un tipo raro o el JSON entero
está corrupto, se usa el valor por defecto de cada campo y se sigue adelante.
Perder las preferencias es molesto; no poder grabar un vuelo es grave.

La velocidad de inicio del modo automático (50 kt) **no** está aquí: es una
constante de la máquina de estados, por decisión explícita del proyecto.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Optional

MODO_AUTOMATICO = "automatico"
MODO_MANUAL = "manual"
MODOS_VALIDOS = (MODO_AUTOMATICO, MODO_MANUAL)


@dataclass
class Settings:
    """Preferencias del piloto, con sus valores por defecto."""

    modo: str = MODO_AUTOMATICO
    indicativo: str = ""
    salida: str = ""
    llegada: str = ""
    license_id: str = ""  # ID de piloto EvA (usado en login y grabaciones)

    # CID de VATSIM del piloto. No es una credencial: es el número público
    # de miembro, y solo se usa para preguntar a la Slurper API si está
    # conectado (el LED del panel de inicio). EvA no guarda contraseñas.
    #
    # Normalmente no hace falta escribirlo: se lee solo de la configuración
    # de vPilot (`NetworkLogin` en vPilotConfig.xml), que ya lo tiene porque
    # es lo que usa para entrar en la red. Este campo es el respaldo manual
    # para cuando ese fichero no está o no se encuentra.
    cid: str = ""

    # Ruta al ejecutable de vPilot, solo si no está en ninguna de las rutas
    # habituales y el piloto la ha indicado a mano. Vacío significa "buscar
    # en las rutas por defecto".
    vpilot_path: str = ""

    # Tiempos de confirmación de la máquina de estados. Se exponen aquí
    # porque puede hacer falta ajustarlos para aviones concretos, pero no se
    # muestran en la interfaz: no son cosa del uso diario.
    segundos_confirmacion_despegue: float = 3.0
    segundos_confirmacion_aterrizaje: float = 5.0
    segundos_confirmacion_parada: float = 10.0
    altura_despegue_ft: float = 50.0

    # Cada cuánto se vuelca lo grabado a disco, para no perder el vuelo si
    # EvA se cierra de golpe.
    intervalo_autoguardado_s: float = 30.0

    # None significa "la carpeta grabaciones junto al ejecutable".
    carpeta_grabaciones: Optional[str] = None

    # -- validación ----------------------------------------------------

    def normalizar(self) -> None:
        """Corrige en el sitio cualquier valor fuera de rango."""
        if self.modo not in MODOS_VALIDOS:
            self.modo = MODO_AUTOMATICO

        self.indicativo = str(self.indicativo or "").strip().upper()[:16]
        # Solo dígitos: un CID es un número de socio, no un texto libre.
        self.cid = "".join(c for c in str(self.cid or "") if c.isdigit())[:9]
        self.salida = str(self.salida or "").strip().upper()[:4]
        self.llegada = str(self.llegada or "").strip().upper()[:4]

        # Los tiempos de confirmación tienen que ser positivos y razonables:
        # un valor de 0 haría la detección tan nerviosa como no tenerla, y
        # uno enorme dejaría el vuelo sin cerrar.
        self.segundos_confirmacion_despegue = _clamp(
            self.segundos_confirmacion_despegue, 1.0, 30.0, 3.0
        )
        self.segundos_confirmacion_aterrizaje = _clamp(
            self.segundos_confirmacion_aterrizaje, 1.0, 60.0, 5.0
        )
        self.segundos_confirmacion_parada = _clamp(
            self.segundos_confirmacion_parada, 1.0, 300.0, 10.0
        )
        self.altura_despegue_ft = _clamp(self.altura_despegue_ft, 10.0, 500.0, 50.0)
        self.intervalo_autoguardado_s = _clamp(
            self.intervalo_autoguardado_s, 5.0, 600.0, 30.0
        )

        if self.carpeta_grabaciones is not None:
            carpeta = str(self.carpeta_grabaciones).strip()
            self.carpeta_grabaciones = carpeta or None


def _clamp(value: Any, minimum: float, maximum: float, default: float) -> float:
    """Devuelve el valor dentro del rango, o el valor por defecto si no vale."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return max(minimum, min(maximum, number))


# -- lectura y escritura -----------------------------------------------


def load(path: Path) -> Settings:
    """Lee las preferencias. Nunca lanza excepción: ante la duda, defaults."""
    settings = Settings()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings  # no existe, no se puede leer o no es JSON válido

    if not isinstance(raw, dict):
        return settings

    known = {field.name for field in fields(Settings)}
    for key, value in raw.items():
        if key in known and value is not None:
            setattr(settings, key, value)

    settings.normalizar()
    return settings


def save(settings: Settings, path: Path) -> bool:
    """Guarda las preferencias. Devuelve False si no se ha podido.

    No poder guardar las preferencias no es motivo para interrumpir nada, así
    que el fallo se comunica con un booleano en vez de con una excepción.
    """
    settings.normalizar()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Escritura en dos pasos: si algo falla a mitad, el fichero anterior
        # sigue intacto en vez de quedarse truncado.
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(settings), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(path)
        return True
    except OSError:
        return False
