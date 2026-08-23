# Matriz de Trazabilidad — 26 Reglas EvA: de dónde sale cada dato

**Fuentes** (2026-08-23, `RULES_VERSION="1.0"` en `client/avcars/evaluation/scoring.py:33`)
- Log: `client/avcars/schema.py:176` (`FlightLog`, `TrackPoint:70`, `Event:47`, `TimingInfo:39`, `FlightPlanInfo:26`)
- POH / performance: `client/config/aircraft.yaml:1` (`limites_poh` = límites certificados, `referencia_atc` = típicos EUROCONTROL — nunca límite)
- Aeródromos: `client/config/airports.json:1` (`{icao:{lat,lon,name}}` solo coords) + `web/data/eva.db` (`aerodromos_es:817`, `pistas_es:217`, `puntos_vfr_es:1104`)
- Umbrales: `client/config/profiles.yaml:1` (`normal/easy/hard` + `penalties`)
- Motor: `client/avcars/evaluation/scoring.py:46` (`RULE_SCOPE`), `scoring.py:460` (`evaluate_flight`), `scoring.py:226`/`268`/`369` helpers

> `null` en `aircraft.yaml` = no verificado = **NO se evalúa** (peor inventar que no evaluar). `no_aplica` = no existe en ese avión (ej. `vle` tren fijo).

## Resumen evaluabilidad

- **20 evaluables hoy** (tienen dato en log + umbral en `profiles.yaml`/`aircraft.yaml`): alineaciones, toma, estabilizada, combustible, pausas, time compression, bank, 5 luces, stall/overspeed/qnh, tren, `structural_overspeed` (VNE/VMO real del POH para los 8 aviones desde 2026-08-23).
- **6 no evaluables** (`Verdict.not_evaluated` en `scoring.py:465`): `route_deviation`, `cruise_altitude_semicircular`, `speed_below_10000ft`, `assigned_squawk`, `planned_runway_match`, `runway_excursion`.

## Matriz campo por campo

| # | Regla | `RULE_SCOPE` | Log (`schema.py`) | `aircraft.yaml` | `airports.json` / `eva.db` | `profiles.yaml` | Lógica `scoring.py` | Estado |
|---|---|---|---|---|---|---|---|---|
| 1 | `runway_alignment_takeoff` | `ambas` | `events[type=takeoff].runway_alignment_deg` (`Event:61`), `events[].utc` (`Event:57`) | — | — | `runway_alignment_deg_max=10` (`normal:11`), `penalties.runway_alignment_takeoff=10` (`normal:38`) | `scoring.py:476` `abs(deg) <= max` -> `score -= pts`, `_at_utc(..., takeoff.utc)` | ✅ Evaluable si evento existe, si no -> `not_evaluated` |
| 2 | `runway_alignment_landing` | `ambas` | `events[touchdown].runway_alignment_deg` | — | — | idem `penalties.runway_alignment_landing=15` (`normal:39`) | `scoring.py:493` | ✅ |
| 3 | `touchdown_zone` | `ambas` | `events[touchdown].distance_from_threshold_m` (`Event:64`) | — | — | `touchdown_zone_m_max=600` (`normal:12`) | `scoring.py:507` | ✅ |
| 4 | `landing_vs` | `ambas` | `events[touchdown].vs_fpm` (`Event:63`) | — | — | `landing_vs_bands` butter 60/0, smooth 180/0, normal 300/10, hard 600/25, >hard=FAIL (`normal:20-25`) | `scoring.py:520` bandas + `failed_hard.append("landing_vs_very_hard")` | ✅ FAIL si very_hard |
| 5 | `stabilized_500ft` | `ambas` | `track[].alt_agl_ft` (`TrackPoint:75`), `track[].vs_fpm` (`TrackPoint:79`), `track[].on_ground` | — | — | `stabilization {alt_agl_ft:500, tolerance:100, vs_min:-1000, vs_max:0}` (`normal:15-19`) | `scoring.py:545` busca `abs(agl-500)<=tol` y comprueba `vs` | ✅ |
| 6 | `fuel_reserve` | `ambas` | `summary.fuel_remaining_kg` (`SummaryInfo:111`), `track[].fuel_kg` (`TrackPoint:89`), situado en `track[-1]` | — | — | `fuel_reserve_kg_min=20` (`normal:26`) | `scoring.py:566` | ✅ |
| 7 | `pause_duration` | `ambas` | `events[pause].duration_s` (`Event:66`) | — | — | `pause_duration_s_max=120` (`normal:27`), `penalties.pause_exceeded=10` | `scoring.py:583` itera `pause` | ✅ |
| 8 | `time_compression` | `ambas` | `timing.max_sim_rate_observed` (`TimingInfo:44`) | — | — | FAIL si >1.0 | `scoring.py:597` `failed_hard+=time_compression_used` | ✅ |
| 9 | `bank_angle` | `ambas` | `track[].bank_deg` (`TrackPoint:81`) | — | — | `bank_angle {warn_deg:30, fail_deg:60, sustained_samples:3}` (`normal:31-34`) | `scoring.py:226` max>fail=FAIL, si no sostenida >warn durante N muestras = penaliza `sustained_bank_angle=15` | ✅ |
| 10 | `landing_light_takeoff` | `ambas` | `events[takeoff].utc` + `_nearest_track_point` `track.landing_light` (`TrackPoint:101`) | — | — | `lights.check_tolerance_s=30` (`normal:36`), `penalties.landing_light_off=10` | `scoring.py:380` busca punto ±tolerance, `ok=landing_light==True` | ✅ |
| 11 | `landing_light_landing` | `ambas` | idem con `touchdown` | — | — | idem | `scoring.py:380` | ✅ |
| 12 | `beacon_airborne` | `ambas` | `track[airborne=!on_ground].beacon_light` (`TrackPoint:102`) | — | — | `penalties.beacon_off_airborne=10` | `scoring.py:397` `all(beacon)` else FAIL | ✅ |
| 13 | `nav_light_airborne` | `ambas` | `track[airborne].nav_light` (`TrackPoint:103`) | — | — | `penalties.nav_light_off_airborne=10` | `scoring.py:413` | ✅ |
| 14 | `taxi_light` | `ambas` | `track[on_ground && gs_kt>2].taxi_light` (`TrackPoint:104`, `TrackPoint:77`) | — | — | `penalties.taxi_light_off=5` | `scoring.py:427` | ✅ |
| 15 | `strobe_taxi` | `ambas` | `track[taxiing].strobe_light` debe estar OFF (`TrackPoint:105`) | — | — | `penalties.strobe_wrong_state=5` | `scoring.py:443` `all(not strobe)` | ✅ |
| 16 | `stall_warning` | `ambas` | `track[].stall_warning` (`TrackPoint:86`) | — | — | FAIL duro ( `penalties.stall_warning` 0) | `scoring.py:284` `failed_hard+=stall_warning_triggered` | ✅ si `stall_warning!=None`, si no -> `not_evaluated` |
| 17 | `overspeed_warning` | `ambas` | `track[].overspeed_warning` (`TrackPoint:87`) — **aviso del sim, no VNE calculado** | `limites_poh.vmo/mmo/vne` **no usado** hoy (solo DHC6 `vmo:166`, C25C `vmo:305/mmo:0.77` tienen valor; resto `null`) | — | FAIL duro | `scoring.py:301` | ✅ si hay dato |
| 18 | `qnh` | `ambas` | `track[].qnh_inhg` (`TrackPoint:85`) | — | — | `qnh {min:28.5, max:31.2}` (`normal:28-30`), `penalties.qnh_out_of_range=10` | `scoring.py:318` `cfg["min"] <= qnh <= max` | ✅ |
| 19 | `gear_on_touchdown` | `ambas` | `events[touchdown].utc` + `_nearest_track_point(tol 5s)` `track.gear_down` (`TrackPoint:83`), `track.on_ground` | `configuracion.tren: fijo/retractil` (`aircraft.yaml:58`) detecta `all(gear_down==True)` => tren fijo => skip | — | `penalties.gear_up_touchdown=15` | `scoring.py:338` | ✅ (no evalúa si tren fijo) |
| 20 | `route_deviation` | `ambas` | `flight_plan.route` (`FlightPlanInfo:31` string sin parsear), `track[].lat/lon` (`TrackPoint:72-73`) | — | `puntos_vfr_es` (`lat/lon` por `ctr_icao`) + `airports.json` coords origen/destino | — | `scoring.py:466` en `not_evaluated` inicial | ❌ No evaluable: falta ruta parseada + waypoints con coords |
| 21 | `cruise_altitude_semicircular` | `VFR` | `flight_plan.planned_cruise_alt_ft` (`FlightPlanInfo:32`), `track[].alt_msl_ft` (`TrackPoint:74`), `flight_plan.rules` | — | — | — | `scoring.py:467` | ❌ Falta altitud fiable + regla semicircular |
| 22 | `speed_below_10000ft` | `ambas` | `track[].ias_kt` (`TrackPoint:78`), `track[].alt_msl_ft`, `track[].alt_agl_ft` | `limites_poh.vno/vne` `null` en 6/8 aviones (solo DHC6/C25C parcial) | — | — | `scoring.py:468` | ❌ Requiere alt transición + IAS real + V límites |
| 23 | `assigned_squawk` | `ambas` | `track[].squawk` (`TrackPoint:97`), `track[].transponder_state` (`TrackPoint:100`), `flight_plan` sin squawk asignado | — | — | — | `scoring.py:469` | ❌ Falta squawk asignado ATC en plan/eventos |
| 24 | `planned_runway_match` | `ambas` | `events[].runway` (`Event:59`), `flight_plan.departure_icao/arrival_icao` | — | `pistas_es` `{designator, le_ident/he_ident, le_heading/he_heading}` (`eva.db`) + `aerodromos_es.default_runway` | — | `scoring.py:470` | ❌ Falta pista planificada en FPL |
| 25 | `runway_excursion` | `ambas` | `track[].lat/lon`, `track[].on_ground`, `events[].position_pct` | — | `airports.json` solo punto (sin polígono), `pistas_es` sin `wkt` geometría | — | `scoring.py:471` | ❌ Requiere geometría pista |
| 26 | `structural_overspeed` (VNE/VMO) | `ambas` | `track[].ias_kt` | `limites_poh.vne/vmo` (POH real, los 8 aviones; `referencia_sim` solo si no hay POH) vía `limite_efectivo()` | — | — | `scoring.py:472` | ✅ Evaluable; no comprueba MMO (sin dato de Mach en el log) ni variación de VMO con altitud |

## Diagrama de flujo de datos por bloque

```
Log track.*          ─┐
Log events.*         ─┼─> scoring.py:evaluate_flight() ─> Verdict {items, failed_hard, not_evaluated}
Log timing.*         ─┘              │
Log flight_plan.*    ────────────────┘              usa profiles.yaml umbrales
Log summary.*        ────────────────────────────────

aircraft.yaml:limites_poh ──> vne/vmo reales (8/8 aviones) ──> limite_efectivo() ──> structural_overspeed
aircraft.yaml:referencia_atc ──> NO es límite, no penaliza (solo contexto Eurocontrol)
airports.json / aerodromos_es / puntos_vfr_es ──> solo coords, no geometría => runway_excursion/route_deviation bloqueadas
```

## CSV adjunto

Se genera también `docs/matriz_reglas.csv` con las mismas columnas para filtrar en Excel/Sheets (separador `;`).

## Notas de implementación

- `scoring.py:166` `_at()` y `scoring.py:196` `_at_utc()` sitúan cada `VerdictItem` con `utc/lat/lon` del `TrackPoint` más cercano (`LOCATION_TOLERANCE_S=60` para pintar, 5s para juzgar tren).
- `scoring.py:635` `rule_applies(rule, flight_rules)` filtra `not_applicable` vs `not_evaluated` (VFR/IFR). Hoy todo es `ambas` salvo `cruise_altitude_semicircular=VFR`.
- Para desbloquear las 6 no evaluables que quedan hay que: parsear `route` a waypoints (`puntos_vfr_es` lat/lon), añadir `squawk_asignado` y `pista_planificada` a `flight_plan`, geometría de pista, y programar la regla semicircular.
