"""Genera los enlaces para presentar un plan de vuelo en IVAO y en VATSIM.

Qué hace y qué NO hace
----------------------
Ninguna de las dos redes ofrece una API pública para *enviar* un plan de
vuelo. Lo que ofrecen es una URL que abre su formulario **ya relleno**, y el
piloto revisa y pulsa el botón de enviar.

Comprobado el 2026-08-16 sobre los siete ficheros OpenAPI que VATSIM publica
en github.com/vatsimnetwork/vatsim.dev: en total hay **un solo** método POST,
y es el de token de OAuth. Todo lo demás son lecturas.

Por eso este módulo devuelve una URL y nada más: al generarla, EvA no sabe
todavía si el piloto llegó a pulsar enviar.

Ahora bien, **sí se puede comprobar después**: el feed público de VATSIM
(`data.vatsim.net/v3/vatsim-data.json`, sin autenticación) publica un array
`prefiles` con los planes presentados por pilotos aún no conectados, y el
plan de cada piloto ya conectado. Buscando el indicativo ahí se confirma la
presentación. Eso no es cosa de este módulo —que solo construye enlaces—
pero conviene saber que la confirmación existe y de dónde sale.

IVAO
----
Documentado en wiki.ivao.aero/en/home/devops/api/flightplan (verificado el
2026-08-16). El plan viaja como un objeto JSON codificado en base64 dentro
del parámetro `flightPlan`. Todos los campos son opcionales, así que un plan
a medias también sirve.

VATSIM
------
Parámetros de consulta sueltos. La lista de campos la aportó el usuario; la
URL base no ha podido verificarse contra documentación oficial, así que está
aislada en `VATSIM_PREFILE_URL` para poder corregirla en un solo sitio.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import date, time
from typing import Any, Optional
from urllib.parse import urlencode

from .schema import FlightPlanInfo, PilotInfo

IVAO_PREFILE_URL = "https://fpl.ivao.aero/flight-plans/create"

#: Formulario clásico de plan de vuelo de VATSIM. Requiere haber iniciado
#: sesión. No valida el `raw=`: lo acepta tal cual, sin avisar de errores de
#: formato — por eso costó detectar la casilla 9 mal formada.
VATSIM_PREFILE_URL_CLASICO = "https://my.vatsim.net/pilots/flightplan"

#: Formulario nuevo (beta). Sí valida el `raw=` línea a línea y avisa de
#: errores de formato («Error parsing line N»); confirmado en vivo por el
#: usuario 2026-08-24 que rellena bien los campos donde el clásico no lo
#: hacía. Es el que se usa por defecto ahora.
VATSIM_PREFILE_URL_BETA = "https://my.vatsim.net/pilots/flightplan/beta"

#: Alias usado por `vatsim_prefile_url()`. Cambiar aquí si VATSIM retira
#: alguna de las dos versiones.
VATSIM_PREFILE_URL = VATSIM_PREFILE_URL_BETA

#: Reglas de vuelo tal como las nombra cada red.
IVAO_RULES = {"VFR": "V", "IFR": "I", "Y": "Y", "Z": "Z"}
VATSIM_RULES = {"VFR": "V", "IFR": "I"}


@dataclass
class PrefileExtras:
    """Datos del plan que no están en `FlightPlanInfo`.

    Todos opcionales: las dos redes admiten planes parciales y es mejor
    mandar menos que rellenar huecos a ojo. Lo que falte lo completa el
    piloto en el formulario, que es donde puede verlo.
    """

    #: Hora de salida UTC.
    departure_utc: Optional[time] = None
    #: Velocidad de crucero. La unidad va en `speed_type`.
    cruise_speed: Optional[int] = None
    #: N = nudos, M = Mach, K = km/h.
    speed_type: str = "N"
    #: Tiempo estimado en ruta, en minutos.
    eet_minutes: Optional[int] = None
    #: Autonomía, en minutos.
    endurance_minutes: Optional[int] = None
    #: Personas a bordo. Con el manifiesto de carga sale de ahí.
    persons_on_board: Optional[int] = None
    remarks: Optional[str] = None
    #: Categoría de estela: L, M, H o J. Está en config/aircraft.yaml
    #: (`referencia_atc.estela`) para los aviones que la tienen.
    wake_turbulence: Optional[str] = None
    second_alternate_icao: Optional[str] = None
    #: Casilla 10 del plan ICAO: equipo de radio y navegación a bordo.
    #: "S" es el equipo normalizado (VHF, VOR e ILS), lo corriente en
    #: aviación general. No es un dato medido del avión sino una
    #: declaración del piloto, que la revisa en el formulario.
    equipment: str = "S"
    #: Casilla 10, segunda parte: tipo de transpondedor. "C" es modo A con
    #: altitud, lo habitual en VFR.
    transponder: str = "C"
    #: S (regular), N (no regular), G (aviación general), M (militar),
    #: X (otro). Para una aerolínea virtual lo normal es S o G.
    flight_type: str = "G"
    #: Fecha del vuelo (DOF). Va en la casilla 18 como `DOF/AAMMDD`, la
    #: convención real del plan ICAO. Sin ella, ATC no sabe distinguir un
    #: plan de hoy de uno presentado por error para otro día.
    flight_date: Optional[date] = None
    #: Capacidad de comunicación del piloto: voz, solo texto, o solo
    #: recepción. No es un campo del ICAO FPL — es una nota para ATC y
    #: otros pilotos, así que se añade a las observaciones (RMK/) en vez de
    #: inventar una casilla que el formato no tiene.
    voice_capability: Optional[str] = None  # "V" | "T" | "R"


def _seconds_since_midnight(t: Optional[time]) -> Optional[int]:
    if t is None:
        return None
    return t.hour * 3600 + t.minute * 60


def _drop_empty(data: dict[str, Any]) -> dict[str, Any]:
    """Quita los campos vacíos.

    Mandar una cadena vacía no es lo mismo que no mandar el campo: lo primero
    puede sobrescribir un valor que el formulario habría deducido solo.
    """
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}


def ivao_flight_plan(
    flight_plan: FlightPlanInfo,
    pilot: PilotInfo,
    extras: Optional[PrefileExtras] = None,
) -> dict[str, Any]:
    """Construye el objeto de plan de vuelo que espera IVAO."""
    extras = extras or PrefileExtras()

    # En VFR el nivel de crucero no se manda como número: el tipo de nivel es
    # "VFR" y el valor va vacío. Mandar una altitud con tipo VFR es
    # contradictorio y el formulario lo rechazaría.
    es_vfr = flight_plan.rules.upper() == "VFR"
    if es_vfr:
        altitude_type: Optional[str] = "VFR"
        altitude: Optional[int] = None
    elif flight_plan.planned_cruise_alt_ft:
        altitude_type = "F"  # nivel de vuelo
        altitude = flight_plan.planned_cruise_alt_ft // 100
    else:
        altitude_type = None
        altitude = None

    return _drop_empty({
        "callsign": pilot.callsign,
        "flightRules": IVAO_RULES.get(flight_plan.rules.upper()),
        "flightType": extras.flight_type,
        "aircraftNumber": 1,
        "aircraftId": flight_plan.aircraft_icao_type,
        "aircraftWakeTurbulence": extras.wake_turbulence,
        "departureId": flight_plan.departure_icao,
        "departureTime": _seconds_since_midnight(extras.departure_utc),
        "cruisingSpeedType": extras.speed_type if extras.cruise_speed else None,
        "cruisingSpeed": extras.cruise_speed,
        "altitudeType": altitude_type,
        "altitude": altitude,
        "route": flight_plan.route,
        "arrivalId": flight_plan.arrival_icao,
        "eet": extras.eet_minutes * 60 if extras.eet_minutes else None,
        "alternativeId": flight_plan.alternate_icao,
        "alternative2Id": extras.second_alternate_icao,
        "remarks": extras.remarks,
        "endurance": extras.endurance_minutes * 60 if extras.endurance_minutes else None,
        "pob": extras.persons_on_board,
    })


def ivao_prefile_url(
    flight_plan: FlightPlanInfo,
    pilot: PilotInfo,
    extras: Optional[PrefileExtras] = None,
) -> str:
    """URL que abre el formulario de IVAO con el plan ya relleno."""
    payload = json.dumps(ivao_flight_plan(flight_plan, pilot, extras))
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return f"{IVAO_PREFILE_URL}?{urlencode({'flightPlan': encoded})}"


def icao_fpl(
    flight_plan: FlightPlanInfo,
    pilot: PilotInfo,
    extras: Optional[PrefileExtras] = None,
) -> str:
    """Plan de vuelo en formato ICAO, el de la casilla «Import ICAO FPL».

    Por qué esta vía y no los parámetros de la URL
    ----------------------------------------------
    El formulario de VATSIM tiene un botón para importar un plan en formato
    ICAO. Pegar ahí este texto es más robusto que construir una URL con
    parámetros:

    - El formato ICAO está normalizado y es público; el esquema de parámetros
      de `my.vatsim.net` no está documentado en ninguna parte.
    - Sobrevive a los cambios de la web. Hay una versión beta del formulario
      conviviendo con la actual, y un cambio de nombres de parámetro
      rompería la URL sin avisar. El texto ICAO seguiría valiendo.
    - Sirve igual para otras redes y para cualquier herramienta que lo
      acepte.

    Estructura (casillas del plan de vuelo ICAO)::

        (FPL-EVA101-VG
        -1/C172/L-S/C
        -LEVC1030
        -N0110VFR DCT XERTA DCT
        -LEAL0055 LEVC
        -RMK/...)
        -E/0400 P/2

    La casilla 15 lleva el nivel de crucero en números (p.ej. `F045`)
    siempre que se conoce, también en VFR: el convenio ICAO real permite
    ahí un `VFR` literal, pero el formulario beta de VATSIM no lo admite
    (ver más abajo). Sin altitud, cae a `VFR` como antes.
    """
    extras = extras or PrefileExtras()

    # Casilla 7: indicativo, reglas de vuelo y tipo de vuelo.
    reglas = VATSIM_RULES.get(flight_plan.rules.upper(), "V")
    lineas = [f"(FPL-{pilot.callsign}-{reglas}{extras.flight_type}"]

    # Casilla 9: número de aeronaves (solo si hay más de una — EvA siempre
    # presenta un único avión, así que se omite; incluir «1/» aquí es lo que
    # hacía que el formulario beta de VATSIM rechazara la línea con
    # "Error parsing line 2", verificado en vivo 2026-08-24), tipo y
    # categoría de estela.
    # Casilla 10: equipo de radio/navegación y de vigilancia. El formato los
    # exige, pero no son un dato medido del avión: son declaraciones del
    # piloto, que las revisa en el formulario antes de enviar. Por eso van
    # con un valor de partida corriente en aviación general y se pueden
    # cambiar desde `PrefileExtras`.
    tipo = flight_plan.aircraft_icao_type or "ZZZZ"
    estela = extras.wake_turbulence or "L"
    lineas.append(f"-{tipo}/{estela}-{extras.equipment}/{extras.transponder}")

    # Casilla 13: aeródromo de salida y hora prevista (HHMM).
    hora = extras.departure_utc.strftime("%H%M") if extras.departure_utc else "0000"
    lineas.append(f"-{flight_plan.departure_icao}{hora}")

    # Casilla 15: velocidad de crucero, nivel y ruta.
    # El convenio ICAO real permite «VFR» literal en el nivel cuando no hay
    # uno fijado, y así lo hacía este código — pero el formulario beta de
    # VATSIM (my.vatsim.net/pilots/flightplan/beta) no lo acepta: da
    # "Error parsing line 4" y marca velocidad/altitud/ruta como
    # obligatorias sin rellenar. Confirmado en vivo por el usuario
    # 2026-08-24. La regla de vuelo (V/I) ya va en la casilla 7, así que
    # llevar aquí un nivel numérico siempre que se conozca no es
    # ambiguo — solo cae a «VFR» si de verdad no hay altitud.
    velocidad = f"N{extras.cruise_speed:04d}" if extras.cruise_speed else "N0000"
    if flight_plan.planned_cruise_alt_ft:
        nivel = f"F{flight_plan.planned_cruise_alt_ft // 100:03d}"
    else:
        nivel = "VFR"
    lineas.append(f"-{velocidad}{nivel} {flight_plan.route or 'DCT'}")

    # Casilla 16: destino, tiempo estimado en ruta y alternativos.
    if extras.eet_minutes:
        eet = f"{extras.eet_minutes // 60:02d}{extras.eet_minutes % 60:02d}"
    else:
        eet = "0000"
    destino = f"-{flight_plan.arrival_icao}{eet}"
    for alterno in (flight_plan.alternate_icao, extras.second_alternate_icao):
        if alterno:
            destino += f" {alterno}"
    lineas.append(destino)

    # Casilla 18: otros datos. DOF/ y la capacidad de voz van primero, por
    # convención, seguidos de lo que el piloto haya escrito (PBN/, etc.).
    # Se cierra el paréntesis del plan en esta misma línea.
    otros: list[str] = []
    if extras.flight_date is not None:
        otros.append(f"DOF/{extras.flight_date.strftime('%y%m%d')}")
    if extras.voice_capability:
        otros.append(f"COM/{extras.voice_capability.upper()}")
    if extras.remarks:
        otros.append(extras.remarks)
    lineas.append(f"-{' '.join(otros) or '0'})")

    # Casilla 19: información suplementaria. Va fuera del paréntesis.
    if extras.endurance_minutes:
        aut = f"{extras.endurance_minutes // 60:02d}{extras.endurance_minutes % 60:02d}"
        suplemento = f"-E/{aut}"
        if extras.persons_on_board:
            suplemento += f" P/{extras.persons_on_board}"
        lineas.append(suplemento)

    return "\n".join(lineas)


def vatsim_prefile_url(
    flight_plan: FlightPlanInfo,
    pilot: PilotInfo,
    extras: Optional[PrefileExtras] = None,
) -> str:
    """URL que abre el formulario de VATSIM con el plan ya relleno.

    Usa el parámetro `raw=` con el plan ICAO completo en una línea, más
    `fuel_time` con la autonomía. Es el formato que emplea eva-dispatcher y
    el único **verificado funcionando** contra el formulario real
    (2026-08-16); el esquema de parámetros sueltos de `my.vatsim.net` no está
    documentado en ninguna parte, así que no se usa.
    """
    extras = extras or PrefileExtras()
    # El formulario espera el plan en una sola línea con espacios; el texto
    # multilínea de `icao_fpl` es para pegarlo a mano en «Import ICAO FPL».
    raw = " ".join(icao_fpl(flight_plan, pilot, extras).splitlines())
    params: dict[str, Any] = {}
    if extras.endurance_minutes:
        params["fuel_time"] = (
            f"{extras.endurance_minutes // 60:02d}{extras.endurance_minutes % 60:02d}"
        )
    params["raw"] = raw
    return f"{VATSIM_PREFILE_URL}?{urlencode(params)}"


def prefile_url(
    flight_plan: FlightPlanInfo,
    pilot: PilotInfo,
    extras: Optional[PrefileExtras] = None,
) -> str:
    """Enlace de presentación para la red del plan de vuelo.

    Lanza `ValueError` si la red no admite presentación por enlace, en vez de
    devolver una URL a ninguna parte.
    """
    red = (flight_plan.network or "").upper()
    if red == "IVAO":
        return ivao_prefile_url(flight_plan, pilot, extras)
    if red == "VATSIM":
        return vatsim_prefile_url(flight_plan, pilot, extras)
    raise ValueError(
        f"'{flight_plan.network}' no admite presentar plan de vuelo por enlace. "
        "Solo IVAO y VATSIM."
    )
