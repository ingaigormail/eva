# Formato del log de vuelo — EvA

> Equivalente de `formato_log_vuelo.md`. Fuente de código:
> `client/avcars/schema.py` (`FlightLog` y modelos anidados). `[CONF]`
>
> El propio `schema.py` dice que la prosa en `docs` manda sobre el módulo.
> Este fichero **reconstruye** el esquema desde Pydantic, porque
> `formato_log_vuelo.md` **no existía** en el árbol hasta esta documentación.
> Si alguien cambia el modelo, hay que actualizar ambos.

## Decisiones de diseño `[CONF]`

| Decisión | En código |
|---|---|
| JSON versionado | `schema_version` en `FlightLog` |
| Extensión de grabación | `.avlog.json` (`LOG_SUFFIX` del writer) |
| Muestreo adaptativo | 1 s &lt; 1500 ft AGL; 10 s en crucero (`timing.py`) |
| Eventos discretos | lista `events` (`Event.type`) |
| Integridad | `IntegrityInfo.hash_algorithm` + `track_hash` (SHA-256 de la traza). **No es firma.** |
| Evaluación opcional | `evaluation: EvaluationInfo` no entra en el hash de traza |

Cliente grabador: `CLIENT_NAME = "EvA"`, `CLIENT_VERSION = "0.1.0"`,
`SCHEMA_VERSION = "1.0"` en el writer. `[CONF]`

## Estructura (`FlightLog`) `[CONF]`

```json
{
  "schema_version": "1.0",
  "client": { "name": "EvA", "version": "0.1.0", "simulator": "MSFS2024" },
  "pilot": { "license_id": "EVA18L", "callsign": "EVA18L" },
  "flight_plan": {
    "rules": "VFR",
    "departure_icao": "LEMD",
    "arrival_icao": "LEBL",
    "alternate_icao": null,
    "route": "DCT",
    "planned_cruise_alt_ft": 5500,
    "aircraft_icao_type": "C172",
    "aircraft_registration": "EC-ABC",
    "network": "VATSIM",
    "atc_controlled": true
  },
  "timing": {
    "block_off_utc": "2026-08-14T18:02:11Z",
    "takeoff_utc": "2026-08-14T18:09:40Z",
    "touchdown_utc": "2026-08-14T19:14:02Z",
    "block_on_utc": "2026-08-14T19:20:15Z",
    "max_sim_rate_observed": 1.0
  },
  "events": [
    {
      "type": "takeoff",
      "utc": "2026-08-14T18:09:40Z",
      "airport_icao": "LEMD",
      "runway": "18L",
      "heading_deg": 182,
      "runway_alignment_deg": 1.4,
      "ias_kt": 62
    },
    {
      "type": "touchdown",
      "utc": "2026-08-14T19:14:02Z",
      "vs_fpm": -140,
      "distance_from_threshold_m": 320,
      "runway_alignment_deg": 0.8
    },
    { "type": "pause", "utc": "2026-08-14T18:40:00Z", "duration_s": 95 }
  ],
  "track": [
    {
      "t": 0,
      "lat": 40.4719,
      "lon": -3.5626,
      "alt_msl_ft": 1998,
      "alt_agl_ft": 0,
      "hdg_deg": 182,
      "gs_kt": 0,
      "ias_kt": 0,
      "vs_fpm": 0,
      "on_ground": true,
      "bank_deg": 0,
      "pitch_deg": 0.5,
      "gear_down": true,
      "flaps_pct": 0,
      "qnh_inhg": 29.92,
      "stall_warning": false,
      "overspeed_warning": false,
      "autopilot_engaged": false,
      "fuel_kg": 145.2,
      "total_weight_kg": null,
      "squawk": "7000",
      "transponder_state": 4,
      "landing_light": false,
      "beacon_light": true,
      "nav_light": true,
      "taxi_light": true,
      "strobe_light": false
    }
  ],
  "summary": {
    "total_distance_nm": 258,
    "fuel_used_kg": 62.4,
    "fuel_remaining_kg": 82.8,
    "flight_time_min": 64
  },
  "diagnostics": {
    "samples_total": 3600,
    "samples_repeated": 0,
    "process_errors": 0,
    "longest_repeated_streak": 0
  },
  "integrity": {
    "hash_algorithm": "SHA-256",
    "track_hash": "…"
  },
  "payload": {
    "requested_passengers": 4,
    "requested_cargo_kg": 100,
    "requested_fuel_pct": 0,
    "aircraft_icao_type": "C172",
    "cargo_written_ok": true,
    "applied_cargo_kg": 440,
    "fuel_written_ok": null,
    "applied_fuel_kg": null,
    "applied_at_utc": "2026-08-30T18:05:11Z",
    "note": null
  },
  "evaluation": null
}
```

`payload` es `null` en casi todos los vuelos: solo se rellena si el piloto
usó "Aplicar al simulador" en `/plan` durante este vuelo. No confundir con
un intento fallido — ahí el bloque existe, pero `cargo_written_ok` es
`false` y `note` trae el motivo (p. ej. `"sin conexión con el simulador"`).
`requested_*` es lo que el piloto pidió; `applied_*` es lo que `set_payload()`
confirmó que entró de verdad, que puede no coincidir si algo falló a medias.

`fuel_written_ok`/`applied_fuel_kg` quedan siempre en `null` por ahora:
`/plan` no tiene todavía un selector de combustible real, y aplicar un
`requested_fuel_pct=0` de fábrica vaciaría el depósito sin que nadie lo
pidiera. Se activa el día que exista ese control. `[CONF]`

Los tipos de `Event.type` los escribe el grabador (takeoff, touchdown, gear,
flaps, pause, aceleración de tiempo, etc.). Cualquier string es válido en
Pydantic; el motor solo busca los que conoce. `[CONF]`

## `network` `[CONF]`

Comentario del modelo: `"VATSIM" | "IVAO" | "OFFLINE"`. No hay enum
Pydantic que lo imponga en runtime.

## Mapeo a criterios `[CONF]`

| Criterio | Campo |
|---|---|
| Alineación despegue/toma | `events[].runway_alignment_deg` |
| VS de toma | `events[type=touchdown].vs_fpm` |
| Zona de toma | `events[].distance_from_threshold_m` |
| Estabilización 500 ft | `track[].alt_agl_ft`, `vs_fpm`, `on_ground` |
| Combustible | `summary.fuel_remaining_kg` |
| Compresión | `timing.max_sim_rate_observed` |
| Pausas | `events[type=pause].duration_s` |
| Bank / luces / stall / overspeed / QNH / tren | `track[]` |
| Peso para V-speeds | `track[].total_weight_kg` (a menudo `null`) |

## Entradas / salidas del writer `[CONF]`

- **Entrada:** `SimState` del conector + plan/piloto.
- **Procesos:** muestreo adaptativo, detección de eventos, autosave 30 s,
  espacio libre mínimo 50 MB.
- **Salida:** `.avlog.json` atómico; `.parcial` si se interrumpe.

## CSV `[CONF]`

`web/csv_reader.py` importa telemetría tabular (fstelemetry / pandas).
**No** es el esquema Pydantic; no trae `pilot.license_id` ni `track_hash`.
La huella es SHA-256 del fichero. No se le inventa veredicto de calidad de
avioneta si el motor no puede construir un `FlightLog` completo: el flujo
web decide qué hacer con CSV (resumen en `vuelos_resumen.calidad` puede
quedar NULL según comentarios de `cuentas.py`).
