"""¿Se puede evaluar este vuelo?

Antes de puntuar hay que decidir si el fichero contiene un vuelo de verdad.
Un log con un solo punto y sin eventos sacaba 90/100 y salía APROBADO,
simplemente porque casi ningún criterio era comprobable y no se restaba nada.
Aprobar por falta de pruebas es peor que no evaluar.

Los umbrales son deliberadamente generosos: la idea no es exigir un vuelo
bonito, sino distinguir un vuelo grabado de un fichero roto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ..schema import FlightLog

#: Puntos mínimos para que el track describa algo. Por debajo de esto no hay
#: trayectoria, hay una foto.
MIN_TRACK_POINTS = 10

#: Proporción máxima de muestras repetidas. Por encima, el simulador estaba
#: devolviendo siempre lo mismo y el vuelo no refleja lo que ocurrió.
MAX_REPEATED_RATIO = 0.9

#: Posiciones distintas mínimas. Un avión que se mueve las genera solo.
MIN_DISTINCT_POSITIONS = 5


class Quality(Enum):
    OK = "ok"
    DUDOSA = "dudosa"          # se puede evaluar, pero con reservas
    NO_EVALUABLE = "no_evaluable"


@dataclass
class QualityReport:
    quality: Quality
    problemas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    # Cifras que explican el veredicto, para poder enseñarlas.
    track_points: int = 0
    distinct_positions: int = 0
    repeated_ratio: Optional[float] = None

    @property
    def evaluable(self) -> bool:
        return self.quality is not Quality.NO_EVALUABLE

    @property
    def resumen(self) -> str:
        if self.quality is Quality.OK:
            return "Datos correctos"
        if self.quality is Quality.DUDOSA:
            return "Datos con reservas"
        return "Datos insuficientes para evaluar"


def check(flight: FlightLog) -> QualityReport:
    """Analiza si el vuelo tiene datos suficientes para ser evaluado."""
    track = flight.track
    problemas: list[str] = []
    avisos: list[str] = []

    posiciones = {(p.lat, p.lon, p.alt_msl_ft) for p in track}

    report = QualityReport(
        quality=Quality.OK,
        track_points=len(track),
        distinct_positions=len(posiciones),
    )

    if not track:
        problemas.append("El vuelo no tiene ningún punto de trayectoria.")
    elif len(track) < MIN_TRACK_POINTS:
        problemas.append(
            f"Solo hay {len(track)} puntos de trayectoria; "
            f"hacen falta al menos {MIN_TRACK_POINTS}."
        )

    if track and len(posiciones) < MIN_DISTINCT_POSITIONS:
        problemas.append(
            f"El avión aparece en {len(posiciones)} posición(es) distinta(s): "
            "el simulador no estaba actualizando los datos."
        )

    # Diagnóstico que graba el propio cliente, si está disponible.
    diagnostics = flight.diagnostics
    if diagnostics and diagnostics.samples_total:
        repetidas = diagnostics.samples_repeated or 0
        ratio = repetidas / diagnostics.samples_total
        report.repeated_ratio = ratio

        if ratio > MAX_REPEATED_RATIO:
            problemas.append(
                f"El {ratio:.0%} de las lecturas fueron idénticas a la "
                "anterior: la conexión con el simulador no funcionaba bien."
            )
        elif ratio > 0.5:
            avisos.append(
                f"El {ratio:.0%} de las lecturas fueron repetidas."
            )

        if diagnostics.process_errors:
            avisos.append(
                f"{diagnostics.process_errors} error(es) al procesar muestras."
            )

    # Un vuelo que duró y no recorrió distancia es sospechoso, pero puede ser
    # legítimo (prácticas de rodaje, circuitos muy cerrados): solo aviso.
    summary = flight.summary
    if summary and summary.flight_time_min and summary.total_distance_nm is not None:
        if summary.flight_time_min > 5 and summary.total_distance_nm < 0.5:
            avisos.append(
                f"{summary.flight_time_min:.0f} minutos de vuelo con "
                f"{summary.total_distance_nm:.1f} NM recorridas."
            )

    if not flight.events:
        avisos.append("No se registró ningún evento (despegue, toma, etc.).")

    report.problemas = problemas
    report.avisos = avisos

    if problemas:
        report.quality = Quality.NO_EVALUABLE
    elif avisos:
        report.quality = Quality.DUDOSA

    return report
