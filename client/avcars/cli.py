"""Interfaz de línea de comandos de AVCARS."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import click

from avcars.config import DEFAULT_PROFILES_PATH, get_profile, load_profiles
from avcars.evaluation.scoring import RULES_VERSION, Verdict, evaluate_flight
from avcars.schema import EvaluationInfo, FlightLog, Incident


def _to_evaluation_info(verdict: Verdict, profile_name: str) -> EvaluationInfo:
    """Convierte el veredicto en lo que se guarda junto al vuelo."""
    return EvaluationInfo(
        score=verdict.score,
        passed=verdict.passed,
        failed_hard=list(verdict.failed_hard),
        incidents=[
            Incident(
                rule=item.rule,
                passed=item.passed,
                points=item.points,
                detail=item.detail,
                utc=item.utc,
                lat=item.lat,
                lon=item.lon,
            )
            for item in verdict.items
        ],
        not_evaluated=list(verdict.not_evaluated),
        not_applicable=list(verdict.not_applicable),
        profile=profile_name,
        rules_version=RULES_VERSION,
        evaluated_at_utc=datetime.now(timezone.utc),
    )


def _hhmmss(item_utc: datetime, start: datetime | None) -> str:
    """Tiempo transcurrido desde el inicio del vuelo, en hh:mm:ss."""
    if start is None:
        return item_utc.strftime("%H:%M:%S")
    total = int((item_utc - start).total_seconds())
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


@click.group()
def cli() -> None:
    """AVCARS - cliente de grabación y evaluación de vuelos VFR."""


@cli.command()
@click.argument("log_path", type=click.Path(exists=True, path_type=Path))
@click.option("--profile", default="normal", show_default=True, help="Perfil: easy, normal o hard.")
@click.option(
    "--profiles-file",
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_PROFILES_PATH,
    show_default=True,
)
@click.option(
    "--save/--no-save",
    default=True,
    show_default=True,
    help="Guarda el resultado dentro del propio fichero de vuelo.",
)
def evaluate(log_path: Path, profile: str, profiles_file: Path, save: bool) -> None:
    """Evalúa un fichero de log de vuelo (.avlog.json) y muestra el veredicto."""
    data = json.loads(log_path.read_text(encoding="utf-8"))
    flight = FlightLog.model_validate(data)

    profiles = load_profiles(profiles_file)
    selected_profile = get_profile(profile, profiles)

    verdict = evaluate_flight(flight, selected_profile)

    click.echo(
        f"Vuelo: {flight.pilot.callsign} "
        f"({flight.flight_plan.departure_icao} -> {flight.flight_plan.arrival_icao})"
    )
    click.echo(f"Perfil: {profile} (reglas v{RULES_VERSION})")
    click.echo(f"Puntuación: {verdict.score}/100")
    click.echo(f"Resultado: {'APROBADO' if verdict.passed else 'SUSPENDIDO'}")
    if verdict.failed_hard:
        click.echo(f"Fallos automáticos: {', '.join(verdict.failed_hard)}")

    # El relato del vuelo: qué salió mal y cuándo. Es lo primero que quiere
    # ver el piloto, así que va antes que el desglose completo.
    timeline = verdict.timeline
    if timeline:
        start = flight.timing.block_off_utc if flight.timing else None
        click.echo("\nIncidencias:")
        for item in timeline:
            # Un FAIL lleva 0 puntos porque su consecuencia es el suspenso, no
            # la resta. Mostrarlo como "-0" haría pensar que no pasó nada.
            coste = f"-{item.points}" if item.points else "FALLO"
            click.echo(
                f"  {_hhmmss(item.utc, start)}  {coste:>6}  "
                f"{item.rule}: {item.detail}"
            )

    click.echo("\nDesglose:")
    for item in verdict.items:
        mark = "OK" if item.passed else "FALLO"
        click.echo(f"  [{mark}] {item.rule}: {item.detail} (-{item.points} pts)")

    if verdict.not_evaluated:
        click.echo("\nNo evaluado todavía (pendiente, ver docs/criterios_vfr.md):")
        for rule in verdict.not_evaluated:
            click.echo(f"  - {rule}")

    if verdict.not_applicable:
        click.echo(f"\nNo aplica a un vuelo {flight.flight_plan.rules}:")
        for rule in verdict.not_applicable:
            click.echo(f"  - {rule}")

    if save:
        flight.evaluation = _to_evaluation_info(verdict, profile)
        log_path.write_text(
            flight.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
        )
        click.echo(f"\nResultado guardado en {log_path.name}")


@cli.command()
def record() -> None:
    """Graba un vuelo en vivo conectando con el simulador."""
    raise click.ClickException(
        "Todavía no implementado: requiere los conectores SimConnect/X-Plane "
        "(ver avcars/connectors/). Sprint siguiente."
    )


if __name__ == "__main__":
    cli()
