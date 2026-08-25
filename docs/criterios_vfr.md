# Criterios de evaluación VFR — EvA

> Equivalente de `criterios_vfr.md`. Los números de esta tabla salen de
> `client/config/profiles.yaml` perfil **`normal`** y de `scoring.py`.
> `[CONF]` Los perfiles `easy` / `hard` cambian umbrales y penalizaciones;
> no se copian aquí enteros (ver el YAML).

El log **no** es un POH. Varias reglas de velocidad estructural dependen de
`aircraft.yaml` y hoy pueden quedar en `not_evaluated`. `[CONF]`

## Modelo de puntuación `[CONF]`

- Partida: **100**.
- Cada infracción resta `VerdictItem.points` (puede ser 0 en FAIL duro).
- **Aprobado** si `score ≥ pass_score` **y** `failed_hard` vacío **y** datos evaluables.
- `pass_score` normal = **70**.

## Tabla de criterios implementados (normal)

| Categoría | `rule` (id en `RULE_SCOPE`) | Umbral / condición | Penalización o FAIL |
|---|---|---|---|
| Salida | `runway_alignment_takeoff` | \|alineación\| ≤ 10° | −10 |
| Llegada | `runway_alignment_landing` | \|alineación\| ≤ 10° | −15 |
| Llegada | `touchdown_zone` | ≤ 600 m desde umbral | −10 |
| Llegada | `landing_vs` | \|VS\| ≤ 60 / 180 / 300 / 600 fpm | 0 / 0 / −10 / −25; **> 600 FAIL** `landing_vs_very_hard` |
| Aprox. | `stabilized_500ft` | 500 ft AGL ±100; VS en [−1000, 0] fpm | −20 |
| Combustible | `fuel_reserve` | ≥ 20 kg al final | −20 |
| Sim | `pause_duration` | pausa ≤ 120 s | −10 por exceso |
| Sim | `time_compression` | sim rate ≤ 1 | **FAIL** `time_compression_used` |
| Actitud | `bank_angle` | warn 30° sostenido 3 muestras; fail 60° | −15 sostenida; **FAIL** (id en código: ver `failed_hard` de `_evaluate_bank_angle`) |
| Luces | `strobe_airborne` | ON todo el aire | −5 (`penalties.strobe_wrong_state`) |
| Luces | `landing_light_takeoff` / `landing_light_landing` | ON ± `lights.check_tolerance_s` (30 s) | **inactiva de serie** |
| Luces | `beacon_airborne` | ON todo el aire | **inactiva de serie** |
| Luces | `nav_light_airborne` | ON todo el aire | **inactiva de serie** |
| Luces | `taxi_light` | ON si `on_ground` y GS > 2 kt | **inactiva de serie** |
| Radio | `transponder_airborne` | ON o ALT todo el aire | −5 (`penalties.transponder_off_airborne`) |
| Seguridad | `stall_warning` | ningún True | **FAIL** `stall_warning_triggered` |
| Seguridad | `overspeed_warning` | ningún True | **FAIL** `overspeed_warning_triggered` |
| Seguridad | `structural_overspeed` | IAS ≤ VMO/VNE efectivo | **FAIL** `structural_overspeed` si hay límite |
| Instrumentos | `qnh` | 28.5–31.2 inHg (`qnh.min_inhg` / `max_inhg`) | −10 |
| Config | `gear_on_touchdown` | tren abajo (si no es fijo) | −15 |

## No evaluadas (faltan datos) `[CONF]`

Desviación de ruta, semicircular VFR, 250 kt bajo 10 000 ft, squawk
asignado, pista planificada, excursión de pista. Ver motor §7.

## Metadatos que no puntúan `[CONF]`

Red (`VATSIM` / `IVAO` / `OFFLINE` en el comentario de `FlightPlanInfo.network`)
y `atc_controlled`. No hay regla que los convierta en puntos.

## Lo que no está en EvA `[N/A]` vs algunos borradores Airhispania

- Calificación letra A–F.
- Cartilla por tipo de vuelo Taxi/Aero/Regio.
- Penalización proporcional a segundos fuera de margen (modelo AHS).
- Overlay de touchdown en el simulador.
