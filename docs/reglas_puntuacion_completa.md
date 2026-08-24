# Reglas de puntuación — EvA — Guía completa

> **Fuente de verdad:** `client/avcars/evaluation/scoring.py:1` + `client/config/profiles.yaml:1` + `docs/criterios_vfr.md:1` + `client/avcars/schema.py:1` + `client/config/aircraft.yaml:1`.
> Esta guía detalla por cada regla **qué significa → qué debe hacer el piloto para infringirla → cómo se detecta → cuántos puntos pierde → ejemplos → casos límite**.
> No inventa umbrales: todos los números salen de `profiles.yaml` perfil `normal` (easy/hard varían, ver § Perfiles).

## 1. Modelo de puntuación

- Partida `100` (`scoring.py:545`). Cada infracción resta `VerdictItem.points` (`scoring.py:562`).
- `score = max(0, score)` (`scoring.py:751`).
- **Aprobado** si `score ≥ pass_score` **y** `failed_hard` vacío **y** `quality.evaluable` (`scoring.py:757`).
  - `pass_score` normal `70`, easy `60`, hard `80` (`profiles.yaml:10/54/96`).
- `failed_hard` = suspenso directo aunque la nota numérica sea alta (`scoring.py:515`): `landing_vs_very_hard`, `time_compression_used`, `excessive_bank_angle`, `stall_warning_triggered`, `overspeed_warning_triggered`, `structural_overspeed`.
- `not_evaluated` = aplica pero falta el dato (evento/track ausente) → no resta, no aprueba por falta de pruebas. Distinto de `not_applicable` (no aplica a VFR/IFR) y `not_active` (apagada a mano por admin, `scoring.py:732`).
- `RULES_VERSION = "1.0"` (`scoring.py:34`) y `profile` se guardan con el vuelo (`schema.py:155`): sin ellos dos 72 no son comparables.
- **Un piloto no puede modificar su propia puntuación:** la evaluación es server-side (`scoring.py:525 evaluate_flight`), el log lleva `integrity.track_hash` (`schema.py:115`) y `diagnostics` (`schema.py:120`); `quality.evaluable=False` suspende por falta de pruebas aunque la nota sea alta. No hay endpoint de escritura de `evaluation` desde el cliente.

## 2. Flujo evaluación → puntuación → ingreso → progresión

Mencionado en la especificación funcional: cada vuelo evaluado produce `EvaluationInfo` (`schema.py:155`) con `score/passed`; ese score alimenta el cálculo de ingresos y progresión (rango/horas). Detalle de ingresos/progresión fuera de `scoring.py` — aquí solo se documenta que `score` es la entrada.

## 3. Perfiles (umbrales que cambian por dificultad)

| Concepto | normal | easy | hard |
|---|---|---|---|
| `runway_alignment_deg_max` | 10° | 15° | 6° |
| `touchdown_zone_m_max` | 600 m | 750 m | 450 m |
| `stabilized_500ft` | 500±100 ft, VS −1000..0 | 500±150, −1200..0 | 500±75, −800..0 |
| `landing_vs_bands` | 60/180/300/600 fpm → 0/0/10/25, >600 FAIL | 60/200/350/700 → 0/0/5/15 | 60/160/260/500 → 0/0/15/35 |
| `fuel_reserve_kg_min` | 20 kg | 15 kg | 25 kg |
| `pause_duration_s_max` | 120 s | 180 s | 90 s |
| `qnh` | 28.5–31.2 inHg | 28.0–31.5 | 28.8–30.9 |
| `bank_angle warn/fail/sustained` | 30°/60°/3 muestras | 35°/70°/4 | 25°/50°/2 |
| `lights.check_tolerance_s` | 30 s | 45 s | 20 s |
| Penalizaciones | ver `profiles.yaml:37` | :79 | :121 |

## 4. Reglas implementadas (19) — fichas

### 4.1 `runway_alignment_takeoff` — Salida — ambas
- **Qué significa:** alineación con el eje de pista en el despegue.
- **Infringir:** despegar con `|runway_alignment_deg| > max_deg`.
- **Detecta:** `events[type=takeoff].runway_alignment_deg` (`schema.py:47`), `profile.runway_alignment_deg_max` (`scoring.py:559`). `score -= penalties.runway_alignment_takeoff` (normal −10).
- **Ejemplo:** 12° con max 10° → `12° (máx 10°)`, −10. 8° → OK.
- **Límite:** sin evento `takeoff` o sin `runway_alignment_deg` → `not_evaluated` (`scoring.py:571`). No es FAIL, solo `-10`.

### 4.2 `runway_alignment_landing` — Llegada — ambas
- **Qué significa:** alineación en la toma.
- **Infringir:** `|runway_alignment_deg| > 10°` en `touchdown`.
- **Detecta:** `events[touchdown].runway_alignment_deg` (`scoring.py:575`), misma penalización landing −15 (normal).
- **Ejemplo:** 11° → −15. 5° → OK.
- **Límite:** sin `touchdown` → `not_evaluated` junto a `touchdown_zone` y `landing_vs` (`scoring.py:624`).

### 4.3 `touchdown_zone` — Llegada — ambas
- **Qué significa:** tomar dentro de la zona (distancia desde umbral).
- **Infringir:** `distance_from_threshold_m > 600 m` (normal).
- **Detecta:** `events[touchdown].distance_from_threshold_m` (`scoring.py:588`), penal −10.
- **Ejemplo:** 650 m → −10. 320 m → OK.
- **Límite:** sin `touchdown` o sin ese campo → `not_evaluated`.

### 4.4 `landing_vs` — Llegada — ambas — con FAIL duro
- **Qué significa:** suavidad de la toma (VS vertical en fpm).
- **Infringir (resta):** `|vs_fpm|` en bandas `profiles.yaml:20`: ≤60 butter 0, ≤180 smooth 0, ≤300 normal −10, ≤600 hard −25.
- **FAIL:** `|vs| > 600` → `failed_hard landing_vs_very_hard` (`scoring.py:614`), `points=0` pero suspende directo.
- **Detecta:** `events[touchdown].vs_fpm` (`scoring.py:601`).
- **Ejemplo:** −250 fpm → `normal` −10. −720 fpm → `very_hard` FAIL.
- **Límite:** VS es negativo en descenso; se usa `abs`. Sin `touchdown` → `not_evaluated`.

### 4.5 `stabilized_500ft` — Aproximación — ambas
- **Qué significa:** estabilizado a 500 ft AGL.
- **Infringir:** a 500±100 ft AGL, `vs_fpm` fuera de [−1000, 0].
- **Detecta:** busca el último `track` con `!on_ground` y `|alt_agl_ft-500| ≤ 100` (`scoring.py:627`), comprueba `vs_fpm` (`scoring.py:634`), −20 si no estabilizado.
- **Ejemplo:** a 480 ft con VS −1200 → −20. A 510 ft con −600 → OK.
- **Límite:** sin candidato (aprox. directa sin pasar por 500 o traza pobre) → `not_evaluated`. Solo mira VS, no IAS (pendiente, ver nota `profiles.yaml:13`).

### 4.6 `fuel_reserve` — Combustible — ambas
- **Qué significa:** reserva al calar.
- **Infringir:** `summary.fuel_remaining_kg < 20 kg` (normal) (`scoring.py:648`).
- **Detecta:** `summary.fuel_remaining_kg` vs `fuel_reserve_kg_min`, sitúa incidencia en último `track` (`scoring.py:659`), −20.
- **Ejemplo:** 18 kg → −20. 45 kg → OK.
- **Límite:** sin `summary` o sin ese campo → `not_evaluated`. No distingue si es VFR/IFR.

### 4.7 `pause_duration` — Sim — ambas
- **Qué significa:** pausas largas.
- **Infringir:** cualquier `events[type=pause].duration_s > 120 s` (normal) (`scoring.py:666`).
- **Detecta:** itera todos los `pause`, −10 por cada exceso (`scoring.py:668`).
- **Ejemplo:** pausa 180 s → −10. 90 s → OK.
- **Límite:** una pausa larga no es FAIL, solo resta.

### 4.8 `time_compression` — Sim — ambas — FAIL duro
- **Qué significa:** vuelo sin aceleración temporal.
- **Infringir:** `timing.max_sim_rate_observed > 1` (`scoring.py:679`).
- **Detecta:** `timing.max_sim_rate_observed` (`schema.py:39`), FAIL `time_compression_used` (`scoring.py:681`), `points=0` pero suspende.
- **Ejemplo:** 2x → FAIL. 1x → OK.
- **Límite:** sin `max_sim_rate_observed` → `not_evaluated` (fixture antiguo).

### 4.9 `bank_angle` — Actitud — ambas — FAIL o resta
- **Qué significa:** escora excesiva o sostenida.
- **FAIL:** `|bank_deg| > fail_deg` (60° normal) en cualquier `track` → `failed_hard excessive_bank_angle` (`scoring.py:243`).
- **Resta:** si no hay FAIL pero `|bank| > warn_deg` (30°) durante `sustained_samples` (3) consecutivas → −15 `sustained_bank_angle` (`scoring.py:265`).
- **Detecta:** `track[].bank_deg` (`schema.py:81`), ancle en punto de máxima escora o inicio sostenido (`scoring.py:250`).
- **Ejemplo:** pico 65° → FAIL. 35° durante 4 s a 1 Hz → −15. 28° → OK.
- **Límite:** sin `bank_deg` o sin `profile.bank_angle` → `not_evaluated` (`scoring.py:240`).

### 4.10 `landing_light_takeoff` / `landing_light_landing` — Luces — ambas
- **Qué significa:** landing light encendida en despegue y aterrizaje.
- **Infringir:** OFF en el instante del evento (±30 s normal).
- **Detecta:** busca `track` más cercano a `takeoff.utc`/`touchdown.utc` dentro de `lights.check_tolerance_s` (`scoring.py:434`), lee `landing_light` (`schema.py:101`), −10 `landing_light_off` si apagada.
- **Ejemplo:** despegue con landing OFF dentro de 30 s → −10.
- **Límite:** sin evento o sin `landing_light` en traza → no evalúa esa subregla (no va a `not_evaluated` global de luces a menos que ninguna luz se haya podido evaluar, `scoring.py:702`).

### 4.11 `beacon_airborne` — Luces — ambas
- **Qué significa:** beacon siempre ON en el aire.
- **Infringir:** cualquier `track` con `!on_ground` y `beacon_light==False` (`scoring.py:450`).
- **Detecta:** `track[].beacon_light` en vuelo, −10 `beacon_off_airborne`, sitúa en primer punto con beacon OFF.
- **Ejemplo:** beacon OFF a FL100 → −10 aunque luego lo encienda.

### 4.12 `nav_light_airborne` — Luces — ambas
- Igual que beacon pero con `nav_light`, −10 `nav_light_off_airborne` (`scoring.py:466`).

### 4.13 `taxi_light` — Luces — ambas
- **Qué significa:** luz de rodaje ON mientras rueda.
- **Infringir:** `on_ground && gs_kt > 2 && taxi_light==False` (`scoring.py:477`), −5.
- **Detecta:** filtra `taxiing`, exige `all(taxi_light)` en ese tramo.

### 4.14 `strobe_taxi` — Luces — ambas
- **Qué significa:** strobes OFF en rodaje.
- **Infringir:** `strobe_light==True` mientras `on_ground && gs>2` (`scoring.py:495`), −5 `strobe_wrong_state`.
- **Lógica inversa:** OK = todos OFF.

### 4.15 `stall_warning` — Seguridad — ambas — FAIL
- **Qué significa:** nunca entrar en aviso de pérdida.
- **FAIL:** cualquier `track.stall_warning==True` → `failed_hard stall_warning_triggered` (`scoring.py:296`), `points` de `penalties.stall_warning`.
- **Detecta:** `track[].stall_warning` (`schema.py:86`), sitúa en primer True.
- **Límite:** sin `stall_warning` en traza → `not_evaluated` (sim sin esa variable).

### 4.16 `overspeed_warning` — Seguridad — ambas — FAIL
- Igual que stall pero con `overspeed_warning` (`schema.py:87`), FAIL `overspeed_warning_triggered` (`scoring.py:313`), `points=0`.

### 4.17 `structural_overspeed` — Seguridad — ambas — FAIL (requiere `aircraft`)
- **Qué significa:** no exceder el límite estructural real (VNE/VMO) del avión.
- **FAIL:** `ias_kt > limite` donde `limite = limite_efectivo(aircraft, "vmo")` si existe, si no `"vne"` (`scoring.py:333`), `limite` sale de `aircraft.yaml limites_poh` si verificado, si no `referencia_sim` (`avcars/config.py:limite_efectivo`). Si `limite` es `None/"no_aplica"` en ambas fuentes → `not_evaluated` (`scoring.py:364`). **No comprueba MMO** (el log no guarda Mach, `scoring.py:330`).
- **Ejemplo:** C172 VNE 163, IAS 170 → `170 kt IAS > limite 163 kt (fuente: limites_poh)` FAIL. VMO 175 en C208, IAS 174 → OK.
- **Límite:** sin `aircraft` pasado a `evaluate_flight` → `not_evaluated`. Con tren fijo y `vmo=no_aplica` cae a `vne`.

### 4.18 `qnh` — Instrumentos — ambas
- **Qué significa:** QNH plausible.
- **Infringir:** cualquier `track.qnh_inhg` fuera de [28.5, 31.2] (normal) (`scoring.py:371`), −10 `qnh_out_of_range`, sitúa en primer fuera de rango.
- **Límite:** sin `qnh_inhg` o sin `profile.qnh` → `not_evaluated`.

### 4.19 `gear_on_touchdown` — Config — ambas
- **Qué significa:** tren abajo en la toma (si el avión tiene tren retráctil).
- **Infringir:** `gear_down==False` en punto más cercano a `touchdown.utc` (5 s, `scoring.py:390`), −15 `gear_up_touchdown`.
- **Detecta:** si `all(gear_down==True)` en toda la traza → asume tren fijo (C172) y pasa a `not_evaluated` (`scoring.py:399`), no penaliza.
- **Límite:** sin `gear_down` en traza o sin `touchdown` → `not_evaluated`.

## 5. Reglas no evaluadas (7) — ver `scoring.py:548`

Todas entran en `not_evaluated` por falta de dato en `FlightLog` actual. No restan ni hacen FAIL, pero impiden el aprobado encubierto: el informe las lista como pendientes.

| Regla | Alcance | Qué sería infringir | Por qué no se evalúa hoy |
|---|---|---|---|
| `route_deviation` | ambas | desviarse de `flight_plan.route` | falta `eva.db` de rutas/puntos y traza vs plan |
| `cruise_altitude_semicircular` | VFR | crucero que no cumple semicircular VFR | falta `planned_cruise_alt_ft` vs alt real + regla hemisferio |
| `speed_below_10000ft` | ambas | >250 kt IAS <10.000 ft | falta chequeo `ias_kt` + `alt_msl_ft` <10k con tolerancia |
| `assigned_squawk` | ambas | no llevar squawk ATC asignado | falta `track[].squawk` vs squawk asignado (no en log) |
| `planned_runway_match` | ambas | despegar/aterrizar en pista distinta a la planificada | falta `flight_plan` con pista planificada vs `events.runway` real |
| `runway_excursion` | ambas | salirse de pista (posición lateral) | falta geometría de pista (`eva.db pistas_es`) y posición vs bordes |
| `structural_overspeed` (si sin `aircraft`) | ambas | ver §4.17 | sin `aircraft` no hay límite contra el que comparar |

*Nota:* `structural_overspeed` sí se evalúa cuando `evaluate_flight(..., aircraft=...)` recibe el bloque de `aircraft.yaml`; si no, queda aquí.

## 6. Casos límite y notas operativas

- **Sin eventos:** despegue/aterrizaje sin `runway_alignment_deg`/`distance_from_threshold_m`/`vs_fpm` → `not_evaluated`, no penaliza pero el vuelo es poco evaluable; `data_quality` puede marcar `evaluable=False` si la traza es pobre.
- **Tolerancias de localización:** `LOCATION_TOLERANCE_S=60 s` (`scoring.py:200`) solo para pintar en mapa; el juicio de `gear` usa 5 s y luces 30 s — ventana mayor no cambia la nota, solo desplaza el alfiler.
- **`VNE` vs `VMO`:** el motor respeta la terminología del POH (`C208/C350 usan VMO, C172/BE58 VNE`, `aircraft.yaml:1`). No reclasifica.
- **`no_aplica` vs `null`:** `no_aplica`=esa velocidad no existe (tren fijo → VLE, monomotor → VMCA); `null`=aún no verificado → en `not_evaluated` no se reclama.
- **Modo `VFR`/`IFR`:** `RULE_SCOPE` (`scoring.py:47`) filtra `not_evaluated`/`items` por `flight_plan.rules` (`scoring.py:716`), pero hoy casi todo es `ambas`.
- **Reglas apagadas:** `reglas_activas=false` devuelve puntos y limpia `failed_hard` de esa regla (`scoring.py:739`).

## 7. Referencias cruzadas

- Matriz campo por campo (log/aircraft.yaml/eva.db/profiles/scoring): `docs/matriz_reglas.md:1`, `docs/matriz_reglas.csv:1`
- Límites VNE/VMO/MMO verificados y CSV MSFS: `docs/limites_vne_vmo_mmo.csv:1`, `docs/limites_community_msfs.csv:1`
- Esquema del log: `docs/formato_log_vuelo.md`, `client/avcars/schema.py:176`
