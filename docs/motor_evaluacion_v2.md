# Motor de evaluación — EvA

> Equivalente estructural de `motor_evaluacion_v2.md` de Airhispania.
> Describe **solo** `client/avcars/evaluation/` de este repositorio.

Fuente ejecutable: `scoring.py` función `evaluate_flight`. Versión
`RULES_VERSION = "1.0"`. `[CONF]`

---

## 1. Por qué existe una capa previa a la nota

Un log vacío o congelado sacaría ~100 puntos si solo se restara lo
comprobado. Por eso **antes** se ejecuta `data_quality.check`
(`Quality.OK` / `DUDOSA` / `NO_EVALUABLE`). `[CONF]`

Si `quality.evaluable` es falso, `Verdict.passed` es **False** aunque la
resta de puntos sea pequeña. `[CONF]` final de `evaluate_flight`

Umbrales de calidad `[CONF]` `data_quality.py`:

| Criterio | Valor |
|---|---|
| Puntos de track mínimos | 10 |
| Posiciones distintas mínimas | 5 |
| Ratio de muestras repetidas | > 0,9 → no evaluable |

---

## 2. Arquitectura en capas (la que hay, no la propuesta)

```
SimConnect / (X-Plane UDP incompleto)
    → SimPoller 1 Hz
    → FlightRecorder  (.avlog.json)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
evaluate_flight(flight, profile, aircraft=None)
    → data_quality.check
    → reglas que tengan dato (VerdictItem)
    → failed_hard[]
    → not_evaluated[] / not_applicable[]
    → score = max(0, 100 − penalizaciones)
    → passed = score ≥ pass_score ∧ ¬failed_hard ∧ evaluable
```

No hay motor “v2” separado ni subnotas Taxi/Aero/Regio. `[N/A]` respecto al
diseño AHS-Bender de Airhispania. EvA usa **una nota 0–100** y fallos duros.
`[CONF]`

---

## 3. Situar vs juzgar `[CONF]`

`LOCATION_TOLERANCE_S = 60` sitúa el alfiler en el mapa.

Para el tren en toma se usa una ventana **corta** (~5 s) al buscar el
`TrackPoint` más cercano al evento. Mezclar las dos ventanas cambiaría el
veredicto. Comentarios en `scoring.py`.

---

## 4. Contrato de salida

```text
Verdict
  score: int
  passed: bool
  failed_hard: list[str]
  items: list[VerdictItem]   # rule, passed, points, detail, utc, lat, lon
  not_evaluated: list[str]
  not_applicable: list[str]
  quality: QualityReport | None
```

`timeline` (propiedad): incidencias **fallidas** con `utc`, ordenadas.
`[CONF]`

Al persistir en el log, `cli.py` copia esto a `EvaluationInfo` (campos
`score`, `passed`, `failed_hard`, `incidents`, `not_evaluated`,
`not_applicable`, `profile`, `rules_version`, `evaluated_at_utc`). `[CONF]`
Los nombres Pydantic en `schema.py` son esos; no usar los de un informe
antiguo (`passed` vs `passed`, etc.).

---

## 5. Ámbito VFR/IFR `[CONF]`

`RULE_SCOPE` declara `"VFR" | "IFR" | "ambas"`. Hoy casi todo es `"ambas"`;
`cruise_altitude_semicircular` es `"VFR"`. `rule_applies()` filtra items y
listas. **No cambia resultados** mientras solo se evalúe VFR.

---

## 6. Reglas que el motor ejecuta `[CONF]`

Nombres **tal como están en `RULE_SCOPE` / `evaluate_flight`**. El fichero
`reglas_info.py` y `docs/matriz_reglas.md` usan a veces **otros identificadores**
(p. ej. catálogo vs motor). Si discrepan, **gana `scoring.py`**.

### 6.1 Con evento `takeoff` / `touchdown`

| `rule` | Dato | Efecto (perfil `normal`) |
|---|---|---|
| `runway_alignment_takeoff` | `Event.runway_alignment_deg` | resta `penalties.runway_alignment_takeoff` (10) si \|deg\| > `runway_alignment_deg_max` (10°) |
| `runway_alignment_landing` | idem en touchdown | resta 15 |
| `touchdown_zone` | `distance_from_threshold_m` | resta 10 si > 600 m |
| `landing_vs` | `vs_fpm` | bandas butter/smooth/normal/hard; **very_hard** → `failed_hard` `landing_vs_very_hard` |

Si no hay takeoff con alineación: `not_evaluated` += takeoff alignment.
Si no hay touchdown: landing alignment, zona y VS pasan a `not_evaluated`.

### 6.2 Trayectoria y resumen

| `rule` | Lógica |
|---|---|
| `stabilized_500ft` | Último punto aéreo con \|AGL−500\| ≤ tolerancia; VS en [vs_fpm_min, vs_fpm_max] |
| `fuel_reserve` | `summary.fuel_remaining_kg` ≥ mínimo |
| `pause_duration` | cada evento `pause` con `duration_s` |
| `time_compression` | `timing.max_sim_rate_observed` ≤ 1; si no, `failed_hard` `time_compression_used` |
| `bank_angle` | max > fail_deg → FAIL `excessive_bank_angle`; sostenido > warn_deg N muestras → penalización |

### 6.3 Luces y transpondedor

De las luces, **la única que puntúa es `strobe_airborne`**: los estrobos
deben ir **encendidos en el aire**. Antes existía `strobe_taxi`, que
penalizaba justo lo contrario (llevarlos encendidos rodando); se sustituyó
por decisión de la aerolínea el 2026-08-25.

El motor sigue sabiendo evaluar `landing_light_takeoff` / `_landing`,
`beacon_airborne`, `nav_light_airborne` y `taxi_light` (GS > 2 kt en
tierra), pero están **inactivas de serie**
(`reglas_config.REGLAS_INACTIVAS_POR_DEFECTO`). Se pueden volver a encender
desde `/gestion/reglas`: lo que diga el administrador manda sobre el valor
de serie.

`transponder_airborne` penaliza volar con el transpondedor apagado o en
espera; valen tanto ON como ALT (ver `SimState.mode_charlie`).

Si no hay ningún dato de luces, `not_evaluated` incluye `"lights"`.

### 6.4 Avisos y configuración

| `rule` | Efecto |
|---|---|
| `stall_warning` | cualquier True en track → FAIL `stall_warning_triggered` |
| `overspeed_warning` | idem → FAIL `overspeed_warning_triggered` |
| `structural_overspeed` | IAS > límite `limite_efectivo(aircraft, vmo\|vne)`; FAIL `structural_overspeed`. Sin `aircraft` o sin límite → `not_evaluated`. **No evalúa MMO** (el log no guarda Mach). |
| `qnh` | `qnh_inhg` fuera de [min, max] del perfil |
| `gear_on_touchdown` | tren arriba en toma; se omite si todas las muestras tienen tren abajo (tren fijo) |

---

## 7. Reglas declaradas pero no evaluadas `[CONF]`

Se meten al inicio en `not_evaluated`:

- `route_deviation`
- `cruise_altitude_semicircular`
- `speed_below_10000ft`
- `assigned_squawk`
- `planned_runway_match`
- `runway_excursion`

Falta dato de plan/geometría/POH, no es un “pass” silencioso.

---

## 8. Perfiles `[CONF]` `config/profiles.yaml`

Claves de perfil: **`easy`**, **`normal`**, **`hard`**.

El motor **no** incrusta umbrales: llama `profile["pass_score"]`,
`profile["runway_alignment_deg_max"]`, etc.

`normal.pass_score`: 70. `easy`: 60. `hard`: 80.

---

## 9. Errores y casos especiales `[CONF]`

- Sin eventos: muchas reglas a `not_evaluated`; calidad puede tumbar el aprobado.
- Tren fijo: no se puntúa `gear_on_touchdown`.
- `aircraft=None`: no hay overspeed estructural por POH.
- `null` en `aircraft.yaml` / `limites_poh`: no se inventa VNE; no se evalúa esa regla.
- IFR: el campo `flight_plan.rules` existe; el conjunto de reglas sigue siendo el VFR actual más `not_applicable` por `RULE_SCOPE`.

---

## 10. Relación con el resto

- CLI y web llaman la misma función.
- `/gestion/reglas` lee `reglas_info` (prosa). Contraste obligatorio con este documento y `scoring.py`.
- `despacho_pesos.py` **no** alimenta `evaluate_flight`.
