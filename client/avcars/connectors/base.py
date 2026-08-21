"""Interfaz común que debe implementar cada conector de simulador.

Cada simulador (MSFS/P3D vía SimConnect, X-Plane vía UDP) expone sus datos de
forma distinta; este módulo define el contrato común (`SimState`) para que el
resto del cliente (muestreo, detección de eventos, escritura del log) no
tenga que saber de qué simulador vienen los datos.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

# Valores del estado del transpondedor en SimConnect.
TRANSPONDER_OFF = 0
TRANSPONDER_STANDBY = 1
TRANSPONDER_TEST = 2
TRANSPONDER_ON = 3
TRANSPONDER_ALT = 4  # modo C: transmite altitud

TRANSPONDER_LABELS = {
    TRANSPONDER_OFF: "OFF",
    TRANSPONDER_STANDBY: "STBY",
    TRANSPONDER_TEST: "TEST",
    TRANSPONDER_ON: "ON",
    TRANSPONDER_ALT: "ALT/C",
}


@dataclass
class SimState:
    """Estado instantáneo del avión, normalizado entre simuladores.

    Los campos opcionales son los que no todos los simuladores exponen (o que
    aún no hemos verificado en todos). Cuando un conector no puede leerlos
    deja `None`, y el grabador simplemente no los escribe: así el motor de
    evaluación los marca como "not_evaluated" en vez de asumir un valor.
    """

    lat: float
    lon: float
    alt_msl_ft: float
    alt_agl_ft: float
    hdg_deg: float
    gs_kt: float
    ias_kt: float
    vs_fpm: float
    on_ground: bool
    fuel_kg: float
    squawk: str
    sim_rate: float

    # Peso total del avión. Del peso dependen VR, V2, VREF y la velocidad de
    # pérdida, así que sin él esas reglas no se pueden evaluar. Opcional
    # porque no todos los simuladores lo exponen.
    total_weight_kg: Optional[float] = None

    # Actitud
    bank_deg: Optional[float] = None
    pitch_deg: Optional[float] = None

    # True si el simulador dice estar en pausa. None si no lo expone: en ese
    # caso la pausa hay que inferirla, porque una pausa y una conexión rota
    # se parecen mucho (en ambas los datos dejan de cambiar).
    paused: Optional[bool] = None

    # Estado del transpondedor tal cual lo da el simulador:
    # 0 apagado, 1 standby, 2 test, 3 on, 4 alt (modo C).
    transponder_state: Optional[int] = None

    @property
    def mode_charlie(self) -> Optional[bool]:
        """True si el transpondedor está en modo C (transmitiendo altitud).

        En VFR sin control, el transpondedor debe ir en ALT con 7000 (Europa)
        o 1200 (EEUU) para que el resto del tráfico vea la altitud.
        """
        if self.transponder_state is None:
            return None
        return self.transponder_state == TRANSPONDER_ALT

    # Configuración
    gear_down: Optional[bool] = None
    flaps_pct: Optional[float] = None

    # Calado del altímetro (QNH). Bender lo consume y EvA aún no lo grababa.
    # Se guarda en pulgadas de mercurio (inHg), la unidad del simulador; el
    # motor de evaluación puede convertirlo si prefiere hectopascales.
    qnh_inhg: Optional[float] = None

    # Avisos del simulador. Bender los penaliza por tiempo; para ello hace
    # falta grabarlos como parte del estado, no solo como eventos.
    stall_warning: Optional[bool] = None
    overspeed_warning: Optional[bool] = None

    # Piloto automático encendido (Bender penaliza el PA no permitido).
    autopilot_engaged: Optional[bool] = None

    # Luces
    landing_light: Optional[bool] = None
    beacon_light: Optional[bool] = None
    nav_light: Optional[bool] = None
    taxi_light: Optional[bool] = None
    strobe_light: Optional[bool] = None

    # Diagnóstico: valores crudos tal cual los devuelve el simulador, sin
    # convertir. Sirve para verificar unidades desde la interfaz sin tener
    # que mirar la consola.
    raw: dict = field(default_factory=dict)


class SimConnector(ABC):
    """Contrato que implementa cada conector de simulador."""

    @abstractmethod
    def connect(self) -> None:
        """Establece la conexión con el simulador."""

    @abstractmethod
    def disconnect(self) -> None:
        """Cierra la conexión con el simulador."""

    @abstractmethod
    def poll(self) -> SimState:
        """Lee el estado actual del avión. Solo válido tras `connect()`."""

    def set_payload(
        self, passengers: int = 0, cargo_kg: int = 0, fuel_pct: int = 100
    ) -> bool:
        """Intenta escribir carga, pasajeros y combustible en el simulador.

        Args:
            passengers: Número de pasajeros (default 0)
            cargo_kg: Carga en kilogramos (default 0)
            fuel_pct: Porcentaje de combustible (0-100, default 100)

        Returns:
            True si la operación fue exitosa, False si no está soportada o falló.

        Nota: Solo `SimConnectConnector` lo implementa; otros conectores devuelven False.
        """
        return False
