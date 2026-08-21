"""Modelos del fichero de log de vuelo.

Reflejan el esquema descrito en ../docs/formato_log_vuelo.md. Si el esquema
cambia, ese documento es la fuente de verdad y este módulo debe actualizarse
para seguirlo (nunca al revés).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ClientInfo(BaseModel):
    name: str
    version: str
    simulator: str


class PilotInfo(BaseModel):
    license_id: str
    callsign: str


class FlightPlanInfo(BaseModel):
    rules: str  # "VFR" | "IFR"
    departure_icao: str
    arrival_icao: str
    alternate_icao: Optional[str] = None
    route: Optional[str] = None
    planned_cruise_alt_ft: Optional[int] = None
    aircraft_icao_type: Optional[str] = None
    aircraft_registration: Optional[str] = None
    network: str  # "VATSIM" | "IVAO" | "OFFLINE"
    atc_controlled: bool


class TimingInfo(BaseModel):
    block_off_utc: Optional[datetime] = None
    takeoff_utc: Optional[datetime] = None
    touchdown_utc: Optional[datetime] = None
    block_on_utc: Optional[datetime] = None
    max_sim_rate_observed: Optional[float] = None


class Event(BaseModel):
    """Evento discreto del vuelo (despegue, touchdown, tren, flaps, pausa...).

    Se usa un único modelo con campos opcionales en vez de una jerarquía por
    tipo de evento para mantenerlo simple (ver AI_DEVELOPMENT_STANDARD.md,
    "Simplicity First"). `type` indica qué evento es; el resto de campos solo
    aplican a algunos tipos.
    """

    type: str
    utc: Optional[datetime] = None
    airport_icao: Optional[str] = None
    runway: Optional[str] = None
    heading_deg: Optional[float] = None
    runway_alignment_deg: Optional[float] = None
    ias_kt: Optional[float] = None
    vs_fpm: Optional[float] = None
    distance_from_threshold_m: Optional[float] = None
    position_pct: Optional[float] = None
    duration_s: Optional[float] = None
    rate: Optional[float] = None


class TrackPoint(BaseModel):
    t: float
    lat: float
    lon: float
    alt_msl_ft: float
    alt_agl_ft: float
    hdg_deg: float
    gs_kt: float
    ias_kt: float
    vs_fpm: float
    on_ground: bool
    bank_deg: Optional[float] = None
    pitch_deg: Optional[float] = None
    gear_down: Optional[bool] = None
    flaps_pct: Optional[float] = None
    qnh_inhg: Optional[float] = None
    stall_warning: Optional[bool] = None
    overspeed_warning: Optional[bool] = None
    autopilot_engaged: Optional[bool] = None
    fuel_kg: Optional[float] = None
    # Peso total del avión. Varias velocidades (VR, V2, VREF, pérdida) no son
    # un número fijo del avión sino función del peso: en el TBM 930 la VR va
    # de ~75 a ~90 kt según la carga. Sin este dato no se pueden evaluar, y
    # con un valor único uno se equivoca hasta en 7 kt. También permite
    # contrastar la carga declarada en el plan con la que se llevaba de
    # verdad. None si el simulador no lo expone.
    total_weight_kg: Optional[float] = None
    squawk: Optional[str] = None
    # 0 off, 1 standby, 2 test, 3 on, 4 alt (modo C). Permite evaluar si el
    # piloto llevaba el transpondedor transmitiendo altitud.
    transponder_state: Optional[int] = None
    landing_light: Optional[bool] = None
    beacon_light: Optional[bool] = None
    nav_light: Optional[bool] = None
    taxi_light: Optional[bool] = None
    strobe_light: Optional[bool] = None


class SummaryInfo(BaseModel):
    total_distance_nm: Optional[float] = None
    fuel_used_kg: Optional[float] = None
    fuel_remaining_kg: Optional[float] = None
    flight_time_min: Optional[float] = None


class IntegrityInfo(BaseModel):
    hash_algorithm: str
    track_hash: str


class DiagnosticsInfo(BaseModel):
    """Salud de la captura durante el vuelo.

    Sin esto, un vuelo que sale mal obliga a adivinar qué pasó. Con esto se
    sabe si el simulador dejó de actualizar, si la conexión iba lenta o si
    hubo errores procesando muestras.
    """

    samples_total: Optional[int] = None
    samples_repeated: Optional[int] = None
    process_errors: Optional[int] = None
    longest_repeated_streak: Optional[int] = None


class Incident(BaseModel):
    """Una infracción concreta, situada en el tiempo y en el espacio.

    Se calcula una sola vez, al evaluar, y la consumen tanto la puntuación
    como la interfaz de análisis. Si cada parte del sistema recalculase los
    errores por su cuenta, acabarían discrepando.

    `utc`, `lat` y `lon` son lo que permite pintar el error en un mapa y
    ordenarlo en una línea de tiempo. Sin ellos una incidencia solo se puede
    listar, no situar.
    """

    rule: str
    passed: bool
    points: int
    detail: str
    utc: Optional[datetime] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class EvaluationInfo(BaseModel):
    """Resultado de la evaluación, guardado junto al vuelo.

    Sin `profile` una nota no significa nada: un 72 no es lo mismo sacado en
    `easy` que en `hard`. Y sin `rules_version`, comparar dos vuelos
    evaluados con criterios distintos induce a error.
    """

    score: int
    passed: bool
    failed_hard: list[str] = Field(default_factory=list)
    incidents: list[Incident] = Field(default_factory=list)
    not_evaluated: list[str] = Field(default_factory=list)
    #: Reglas que no aplican a este tipo de vuelo (p. ej. reglas IFR en un
    #: vuelo VFR). Distinto de `not_evaluated`, que es "falta el dato".
    not_applicable: list[str] = Field(default_factory=list)
    profile: str
    rules_version: str
    evaluated_at_utc: Optional[datetime] = None


class FlightLog(BaseModel):
    schema_version: str
    client: ClientInfo
    pilot: PilotInfo
    flight_plan: FlightPlanInfo
    timing: Optional[TimingInfo] = None
    events: list[Event] = Field(default_factory=list)
    track: list[TrackPoint] = Field(default_factory=list)
    summary: Optional[SummaryInfo] = None
    diagnostics: Optional[DiagnosticsInfo] = None
    integrity: Optional[IntegrityInfo] = None
    #: Se rellena al evaluar, no al grabar. No afecta a `integrity.track_hash`,
    #: que solo cubre la traza.
    evaluation: Optional[EvaluationInfo] = None
