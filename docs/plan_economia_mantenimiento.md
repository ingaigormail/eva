# Plan — Sistema económico y de mantenimiento EvA Airliner

> **Estado:** PLAN (no programar aún). Documento de diseño para revisión humana.
> **Versión:** 2026-08-25 borrador v1 · perfil **normal** como referencia.
> **Dependencias leídas:** `client/config/aircraft.yaml:1`, `client/config/profiles.yaml:1`, `client/avcars/evaluation/scoring.py:33`, `client/avcars/schema.py:1`, `client/avcars/cuentas.py:102`, `client/avcars/estadisticas.py:63`, `web/app.py:112`, `web/data/eva.db` (14 tablas), `CONTEXT.md:1`, `docs/guia_practica_reglas_puntuacion.md`, `docs/reglas_puntuacion_completa.md`, `D:/proyectos/airhispania/ARQUITECTURA.md:1`.

---

## 0. Resumen ejecutivo

EvA ya evalúa **cómo** vuelas (scoring 0-100 + FAIL). Este plan añade **consecuencias** de volar: dinero y desgaste. Sin cambiar el motor ni la grabación, cada vuelo integrado genera:

1. **Asiento económico** (+ingreso / -costes) en la cuenta del piloto.
2. **Delta de desgaste** por componente de la aeronave usada.
3. Si el desgaste exige taller, **coste de mantenimiento** que sale de la misma cuenta.

Filosofía: **simple, determinista, auditable**. Cada euro y cada % de desgaste debe poder explicarse en una línea ("aterrizaje hard 320 fpm → tren -8% → 340 EVA€"). Nada de economía oculta ni de fallos aleatorios.

---

## 1. Sistema económico

### 1.1 Moneda y titular

- **Moneda:** `EVA€` (entero, sin decimales). Ficticia, no convertible.
- **Titular:** **piloto** (`usuarios.license_id`). La aerolínea no tiene caja central en F1-F3; el ranking de aerolínea suma saldos si hace falta, pero no hay tesorería común. Razón: evita contabilidad inter-pilotos y es compatible con el modelo actual (todo filtrado por `license_id` como en `planes` y `vuelos_resumen`).
- **Saldo inicial:** `5000 EVA€` al crear cuenta (o al migrar cuentas existentes: `UPDATE usuarios SET saldo=5000 WHERE saldo IS NULL`). Suficiente para 3-4 vuelos + un mantenimiento ligero, insuficiente para ignorar la economía.
- **Saldo puede ser 0, nunca negativo.** Si un vuelo dejaría el saldo <0, se registra igualmente pero el piloto queda **en descubierto técnico**: puede seguir volando (no se bloquea la cartilla), pero no puede comprar/estrenar aeronave hasta reponer (ver §1.6).

### 1.2 Ingresos por vuelo (crédito)

Se calculan **después** de `evaluate_flight()` y solo si `verdict.evaluable == True`. Un vuelo `NO EVALUABLE` no genera ingreso (no se premia la falta de pruebas) pero sí genera costes (combustible gastado es real).

```
ingreso_base = tarifa_por_nm[clase_aeronave] * distancia_nm
```

| Clase (por `mtow_kg` en `aircraft.yaml`) | Tarifa base (EVA€/NM) | Ejemplo |
|---|---|---|
| Ligera <1500 kg (C172, DA62, BE58) | 8 | C172 LEMD-LETO 150 NM → 1200€ |
| Turbohélice 1500-7000 (C208, TBM9, B350, DHC6) | 12 | B350 150 NM → 1800€ |
| Jet (C25C) | 18 | CJ4 150 NM → 2700€ |

**Multiplicador de calidad** (sobre ingreso_base):

| Veredicto | Coeficiente | Efecto |
|---|---|---|
| APTO `score >=70` | 1.0 | cobra completo |
| NO APTO `score <70` sin FAIL | 0.5 | media paga |
| FAIL duro (`landing_vs_very_hard`, `stall_warning`, `structural_overspeed`, `excessive_bank`, `time_compression`) | 0.0 | sin paga (vuelo no válido) |
| NO EVALUABLE | 0.0 | sin paga |

**Bonificaciones (aditivas, sobre ingreso_base):**

- `+10%` si `flight_plan.network == "VATSIM"` (exige CID válido y vuelo registrado en VATSIM; se cruza con `vatsim_api` si existe, no se inventa).
- `+5%` si `control_atc == 1` (despegue o llegada con ATC según `flight_plan.atc_controlled`).
- `+5%` si `perfil_evaluacion == "hard"` (incentiva dificultad).

Tope: bonificaciones suman máximo `+20%` para no desvirtuar la tarifa.

**Ejemplo completo:** B350 150 NM APTO con VATSIM+ATC en perfil normal → `1800 *1.0 + 1800*0.15 = 2070€`

### 1.3 Costes por vuelo (débito)

Siempre se descuentan, incluso si FAIL/NO EVALUABLE:

- **Combustible:** `fuel_used_kg * precio_kg`. `precio_kg = 2 EVA€/kg` (AVGAS/JET unificado en F1; diferenciar en F4). Si `fuel_used_kg IS NULL` (CSV o log sin fuel), se estima `0.15 * mtow_kg * (distancia_nm / 500)` para no dejar coste 0.
- **Tasas de aeródromo:** por `origen` y `destino` según `aerodromos_es.type`:
  - `large_airport` 120€, `medium` 60€, `small`/`heliport` 25€. Si ICAO no está en `aerodromos_es`, 40€.
- **Handling fijo:** `30€` por vuelo (tramitación).

No se cobra por pasajero/carga en F1 (dato no existe aún en `schema.py`/`vuelos_resumen` — ver `ARQUITECTURA.md §3c`).

### 1.4 Balance del vuelo

```
neto = ingreso - (combustible + tasas + handling)
```

Se persiste como **una fila** en `economia_movimientos` (ver §6) con `concepto = "vuelo"` y desglose JSON. El saldo del piloto es `SUM(neto)` o columna cacheada `usuarios.saldo` (elegir una; ver §6.1).

### 1.5 Otros movimientos (no-vuelo)

| Concepto | Signo | Cuándo |
|---|---|---|
| Mantenimiento | - | al pagar taller (ver §3) |
| Compra aeronave | - | F4 |
| Venta / leasing | + | F4-F5 |
| Ajuste admin | ± | `PERM_GESTIONAR_USUARIOS` |
| Bono bienvenida | + | al crear cuenta (5000€) |

Todos pasan por la misma tabla de movimientos; no hay tablas separadas por concepto.

### 1.6 Reglas de saldo

- Saldo nunca negativo en BD (CHECK). Si un vuelo daría negativo, se aplica igual pero el **siguiente vuelo** exige saldo >=0 para generar ingreso? No: se permite descubierto hasta `-500€` con aviso en UI, pero se bloquea **compra de aeronave** y **mantenimiento preventivo opcional** hasta reponer. El vuelo en sí nunca se impide (principio del proyecto: la cartilla no se cierra por dinero).
- Admin puede ajustar saldo con motivo obligatorio (auditoría).

### 1.7 Antiexploits económicos

- **Reimportación idempotente:** `huella` ya existe en `vuelos_resumen` → no se genera segundo asiento económico (misma guarda que `estadisticas.ya_registrado()`).
- **Distancia mínima facturable:** `max(distancia_nm, 20)` para evitar vuelos de 2 NM con tasas negativas.
- **Sin farming de toques y despegues:** solo un ingreso por `huella`; los circuitos en el mismo log son un solo vuelo.
- **Validación de combustible:** si `fuel_used_kg > mtow_kg`, se capa a `0.3*mtow_kg` y se marca `incidencia: fuel_anomalo`.

---

## 2. Sistema de desgaste

### 2.1 Principio

Desgaste **determinista y trazable**: cada vuelo suma `%` a componentes según lo que pasó, no según RNG. Un piloto puede anticipar el coste de volar mal.

No se simulan fallos en vuelo en F1-F3 (no se apaga motor en MSFS). El desgaste solo condiciona **disponibilidad y coste** en tierra.

### 2.2 Componentes (por aeronave)

Seis componentes comunes; si no aplica (tren fijo → tren no degrada por `gear_on_touchdown`), su desgaste es siempre 0 y no se muestra.

| # | Componente | Qué lo degrada | Fuente en log/scoring |
|---|---|---|---|
| 1 | **Motor(es)** | `stall_warning`, `overspeed_warning`, `structural_overspeed`, tiempo a alta potencia (proxy: `overspeed` sostenido) | `track.stall_warning`, `track.overspeed_warning`, `aircraft.limites_poh.vmo/vne`, `track.ias_kt` |
| 2 | **Tren** | `gear_on_touchdown` (arriba), `landing_vs` hard/very_hard, `touchdown_zone` largo + frenada | `events.touchdown.vs_fpm`, `events.touchdown.distance_from_threshold`, `track.gear_down` |
| 3 | **Flaps** | `vfe` excedido (cuando exista chequeo), `structural_overspeed` con flaps | `limites_poh.vfe_por_flap` (futuro), hoy proxy por `overspeed` |
| 4 | **Estructura** | `bank_angle` fail/sostenida, `excessive_bank`, `stall`, `overspeed` | `track.bank_deg`, `bank_angle.fail_deg` |
| 5 | **Frenos** | `touchdown_zone` excedido, `runway_excursion` (futuro) | `distance_from_threshold_m` |
| 6 | **Hélice** (solo hélice/turbohélice) | `overspeed`, `landing_vs` very_hard (golpe) | idem motor |

Cada componente: `salud 0-100%` (100 = nuevo). Se persiste por aeronave y piloto.

### 2.3 Cálculo de deltas por vuelo

Base por horas + eventos:

```
desgaste_base = 0.4% por hora de vuelo (0.0067% por minuto) → todos los componentes
```

Eventos (aditivos, por vuelo):

| Evento | Componentes | Delta |
|---|---|---|
| `landing_vs` butter/smooth (0-180 fpm) | — | +0% |
| `landing_vs` normal (180-300) | tren +0.8%, frenos +0.4% | |
| `landing_vs` hard (300-600) | tren +4%, frenos +2%, estructura +1%, hélice +1% | |
| `landing_vs` very_hard (>600, FAIL) | tren +12%, estructura +5%, motor +3%, hélice +3% | además FAIL económico |
| `gear_on_touchdown` fail (tren arriba) | tren +25%, estructura +10%, hélice +15% | vuelo NO APTO ya |
| `bank_angle` sostenida (warn 3 muestras) | estructura +2% | |
| `bank_angle` fail (>60°) | estructura +7%, motor +2% | |
| `stall_warning` | motor +6%, estructura +4% | |
| `structural_overspeed` / `overspeed_warning` | motor +8%, estructura +5%, flaps +5% | |
| `touchdown_zone` excedido (>600m) | frenos +2%, tren +1% | |
| `qnh` fuera de rango, luces, `fuel_reserve` | — | 0% (solo puntúan, no desgastan) |

Cap por vuelo: `máx +15%` a un componente (evita destruir aeronave en un solo vuelo salvo tren arriba). Suelo: nunca baja de 0%.

**Ejemplo:** C172 60 min, aterrizaje normal 250 fpm, sin otros eventos → cada componente `+0.4%` base + tren `+0.8%` = tren 1.2% total, resto 0.4%.

### 2.4 Persistencia de salud

- Salud por aeronave y piloto (no global por matrícula). Un C172 de `EvA18L` y otro de `pruebas` llevan contadores separados.
- Si el piloto aún no tiene fila para esa aeronave, se crea con `100%` en todos los componentes (aeronave nueva).
- Tras cada vuelo: `salud_nueva = max(0, salud_previa - delta)`.

### 2.5 Umbrales de estado

| Salud mínima entre componentes | Estado | Efecto |
|---|---|---|
| >=70% | Operativa | sin restricción |
| 40-69% | Mantenimiento recomendado | aviso ámbar en hangar |
| 15-39% | Mantenimiento requerido | aviso rojo; puede volar pero próximo vuelo con `FAIL` si no repara* |
| <15% | No aeronavegable | **grounded**: no genera ingreso hasta reparar (ver §3.3) |

*Política F1: nunca grounded automático salvo <15% o tren arriba sin reparar. F3 puede endurecer.

---

## 3. Sistema de mantenimiento

### 3.1 Tipos de intervención

| Tipo | Qué hace | Coste | Cuándo |
|---|---|---|---|
| **Ligero** | restaura +25% al componente más bajo | `80 + 2*%restaurado` | a demanda |
| **Completo** | todos los componentes a 100% | `400 + 1.5*%total_restaurado` | a demanda |
| **Correctivo** (tren arriba, very_hard) | obliga completo si tren <40% | idem completo | tras evento grave |

No hay checks por horas calendario en F1; solo por salud. Calendario (50h/100h) entra en F4.

Coste escala con % restaurado para que reparar 5% no cueste igual que 60%. Fórmula abierta a ajuste tras 20 vuelos reales.

### 3.2 Pago y registro

- Se descuenta de `usuarios.saldo` (o suma de movimientos) en la misma transacción que actualiza salud. Si saldo insuficiente, **se permite a crédito hasta -500€** con aviso, pero se registra deuda (ver §1.6). No se deja aeronave grounded por falta de saldo si el piloto quiere asumir deuda.
- Cada intervención deja fila en `economia_movimientos` con `concepto="mantenimiento"` y detalle `{componentes: {tren: "+25%"}, coste: 130}`.

### 3.3 Grounded y disponibilidad

- Si algún componente <15%, la aeronave aparece como **NO DISPONIBLE** en `/plan` (selector de aeronave deshabilitado con tooltip "Mantenimiento requerido"). El piloto puede reparar o elegir otra aeronave si tiene hangar múltiple (F4).
- En F1 con una sola aeronave por piloto, grounded = debe reparar antes del siguiente vuelo con ingreso. Puede seguir volando, pero el vuelo no genera ingreso hasta reparar (incentivo, no bloqueo técnico de la grabación).

### 3.4 Taller admin

- `PERM_GESTIONAR_USUARIOS` puede ver salud de cualquier piloto y forzar reparación gratuita (ajuste con motivo).

---

## 4. Relación economía ↔ desgaste ↔ mantenimiento

```
Vuelo evaluado (scoring)
  ├─→ ingresos/ costes  → saldo (economía)
  └─→ deltas desgaste   → salud por componente
                              │
                              ▼
                         ¿salud < umbral?
                              ├─ no → seguir volando
                              └─ sí → pagar mantenimiento → saldo ↓ → salud ↑ 100%
```

- **Volar bien abarata:** APTO sin eventos → solo desgaste base 0.4%/h → mantenimiento cada ~30h → coste medio ~13€/h.
- **Volar mal encarece:** hard/overspeed/stall → 5-12% por vuelo → mantenimiento cada 3-4 vuelos → coste medio ~80€/h + pérdida de ingreso (0.5x o 0x).
- **Economía financia mantenimiento:** el neto de un vuelo APTO (ej. 2070-400=1670€) cubre ~4 mantenimientos ligeros. Un piloto NO APTO crónico entra en espiral (menos ingreso, más gasto) y debe entrenar — que es el objetivo pedagógico de EvA, no punitivo.
- **Sin RNG:** la relación es predecible y explicable en el informe post-vuelo ("este aterrizaje te costó 340€ de tren").

---

## 5. Realismo vs complejidad

| Decisión | Realismo | Complejidad | Elección y por qué |
|---|---|---|---|
| Tarifa por NM por clase MTOW | Medio (tarifa real varía por ruta/aerolínea) | Baja (una tabla) | **Elegido:** suficiente para diferenciar C172 vs CJ4 sin meter contratos. |
| Precio combustible único 2€/kg | Bajo (AVGAS ≠ JET) | Baja | **F1:** un precio. **F4:** dos precios (AVGAS 2.2, JET 1.6). |
| Tasas por tipo de aeródromo | Medio | Baja (lookup `aerodromos_es.type`) | **Elegido:** usa dato que ya existe. |
| Desgaste determinista por eventos scoring | Medio (no modela fatiga real) | Baja (usa `Verdict` ya calculado) | **Elegido:** sin telemetría nueva. Alternativa realista (ciclos, vibración) exigiría ampliar `schema.py` — aplazado. |
| Sin fallos en vuelo inducidos | Bajo | Nula | **Elegido:** EvA no inyecta fallos en MSFS. El desgaste solo afecta economía/hangar. |
| Salud por piloto+aeronave, no por matrícula | Bajo (flota compartida) | Baja | **F1:** por piloto. **F4:** por matrícula de flota si se introduce pooling. |
| Mantenimiento a % restaurado | Medio | Baja | **Elegido:** lineal, auditable. Alternativa real (horas hombre + repuestos) es overkill. |
| Grounded <15% | Alto (aeronavegable) | Baja | **Elegido:** umbral único. Más granular (MEL por componente) en F5. |
| Sin mercado/seguro/leasing | — | — | **F5:** leasing, seguro, mercado de segunda mano. No F1. |

Principio transversal: **cada realismo debe poder explicarse en una frase al piloto y en una query al admin**. Si necesita manual, es demasiado complejo para EvA.

---

## 6. Integración con sistema actual

### 6.1 Base de datos (SQLite `web/data/eva.db`)

Todo en SQLite, sin servidor nuevo, mismo patrón que `cuentas.py:266` (`conexion()` con WAL, `PRAGMA foreign_keys`, `configurar_almacen` para tests).

**Migración 1 — `usuarios.saldo` (o vista):**

```sql
ALTER TABLE usuarios ADD COLUMN saldo INTEGER NOT NULL DEFAULT 5000;
-- CHECK saldo >= -500 si se quiere enforcer en BD; si no, en app.
```

Alternativa sin columna: `saldo = SUM(economia_movimientos.importe) WHERE license_id=?`. Elegir **columna cacheada + trigger** o **vista**: columna es más rápida para `/aerolinea` y `/hangar`; vista es más pura. Recomendado: **columna `saldo` + actualización transaccional** (un solo `UPDATE` por movimiento), con función `recalcular_saldo(license_id)` para reconciliar.

**Tabla nueva — `economia_movimientos`:**

```sql
CREATE TABLE economia_movimientos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  license_id TEXT NOT NULL REFERENCES usuarios(license_id),
  fecha TEXT NOT NULL,               -- ISO8601 UTC
  concepto TEXT NOT NULL,            -- 'vuelo','mantenimiento','ajuste','bono'
  importe INTEGER NOT NULL,           -- +ingreso / -coste, en EVA€
  saldo_resultante INTEGER NOT NULL,  -- saldo tras aplicar
  huella TEXT,                        -- FK lógica a vuelos_resumen.huella si concepto='vuelo'
  detalle TEXT NOT NULL DEFAULT '{}', -- JSON: {ingreso_base, bonus, combustible, tasas, ...}
  creado_por TEXT NOT NULL DEFAULT '' -- license_id del admin si ajuste
);
CREATE INDEX economia_piloto ON economia_movimientos(license_id, fecha);
CREATE UNIQUE INDEX economia_huella_unica ON economia_movimientos(huella) WHERE huella IS NOT NULL;
```

**Tabla nueva — `aeronaves_piloto`:**

```sql
CREATE TABLE aeronaves_piloto (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  license_id TEXT NOT NULL REFERENCES usuarios(license_id),
  icao TEXT NOT NULL,                -- C172, B350, ...
  matricula TEXT NOT NULL DEFAULT '',
  salud_motor REAL NOT NULL DEFAULT 100,
  salud_tren REAL NOT NULL DEFAULT 100,
  salud_flaps REAL NOT NULL DEFAULT 100,
  salud_estructura REAL NOT NULL DEFAULT 100,
  salud_frenos REAL NOT NULL DEFAULT 100,
  salud_helice REAL NOT NULL DEFAULT 100,
  horas_totales REAL NOT NULL DEFAULT 0,
  ciclos INTEGER NOT NULL DEFAULT 0, -- despegues
  estado TEXT NOT NULL DEFAULT 'operativa', -- operativa|recomendado|requerido|grounded
  actualizado TEXT NOT NULL,
  UNIQUE(license_id, icao, matricula)
);
CREATE INDEX aeronaves_piloto_piloto ON aeronaves_piloto(license_id);
```

Opcional F2: `historial_desgaste` por vuelo si se quiere auditoría fina; si no, el detalle del desgaste puede ir en `economia_movimientos.detalle` del vuelo.

**Migración y compatibilidad con `vuelos_resumen`:**

- No se altera `vuelos_resumen` salvo añadir `economia_huella` opcional si se quiere join directo. Mejor dejarla intacta y unir por `huella`.
- `estadisticas.registrar_avlog()` es el punto de inserción: tras `INSERT OR IGNORE INTO vuelos_resumen`, si es fila nueva, calcular economía+desgaste en la misma transacción. Si `ya_registrado(huella)` → no recalcular.
- `estadisticas.borrar_por_huella()` debe borrar también `economia_movimientos` de esa huella y revertir saldo (o marcar anulado).

### 6.2 Motor de evaluación — no se toca

`scoring.py:555 evaluate_flight()` y `profiles.yaml:1` siguen igual. Economía y desgaste **consumen** el `Verdict` (score, failed_hard, items, not_evaluated) y el `FlightLog` (fuel, distancia, eventos, track), no los modifican. Esto preserva la garantía de `web/app.py:7` ("el motor no se reimplementa").

### 6.3 Web (`web/app.py`)

- Nuevo módulo `web/economia.py` (cálculo puro, sin Flask) + `web/mantenimiento.py` o uno solo `web/economia_mantenimiento.py` con funciones `calcular_asiento_vuelo(flight, verdict, aeronave) -> dict` y `aplicar_desgaste(...)`.
- Hook en `POST /api/registro/upload` (o donde hoy se llama `estadisticas.registrar_avlog`): tras registrar resumen, llamar a `economia.registrar_vuelo(huella, flight, verdict, perfil)`. Si falla, **no se revierte la subida** (mismo criterio que `estadisticas` — ver `ARQUITECTURA.md §3c`).
- Nuevas rutas (todas con `exigir_sesion`, no públicas como `/vatsim`):
  - `GET /hangar` — hangar del piloto: aeronaves, salud por componente (barras), estado, saldo, últimos movimientos.
  - `POST /hangar/reparar` — paga mantenimiento (ligero/completo).
  - `GET /economia` — extracto de movimientos (paginado).
  - `GET /api/economia/saldo` — JSON para D1 si hace falta.
  - `GET /gestion/economia` — admin: ajustes y reconciliación.
- `/plan` muestra aeronave no disponible si grounded (consulta `aeronaves_piloto.estado`).
- `/aerolinea` puede mostrar saldo medio, coste medio por vuelo, aeronave más cara de mantener.

### 6.4 Cliente de escritorio (`client/avcars`)

- No se modifica `schema.py` en F1 (no se añade telemetría nueva). Si en F4 se quiere desgaste más fino (EPR, CHT), se ampliará `TrackPoint` entonces.
- `client/avcars/cuentas.py` añade `saldo` (getter/setter transaccional). `dashboard.py` (D1) puede mostrar saldo si hay API local; si no, solo web.

### 6.5 Tests

- `web/test_economia.py` y `web/test_mantenimiento.py` con `configurar_almacen(tmp)` (patrón existente). Casos: APTO genera ingreso, FAIL no, reimportación idempotente, combustible NULL estimado, grounded <15%, pago restaura salud y descuenta saldo, descubierto -500.
- `client/tests/test_economia_calculo.py` para cálculo puro sin BD (tarifas, deltas).

### 6.6 Seguridad y auditoría

- IDOR ya existente en `/vuelo/<nombre>/json` (CONTEXT.md) — antes de exponer `/hangar/<otro>` verificar `es_de` / `license_id == piloto_actual()`.
- CSRF en `POST /hangar/reparar` (ya hay `CSRFProtect` en `web/app.py:117`).
- Cada ajuste admin deja `creado_por` y motivo obligatorio.

---

## 7. Fases 1–5 (de MVP a completo)

### Fase 1 — MVP económico (2–3 días, sin desgaste)

**Objetivo:** el piloto ve dinero entrar/salir por volar.

- DB: `usuarios.saldo` + `economia_movimientos`.
- Cálculo: ingreso base por NM + multiplicador calidad + bonus VATSIM/ATC + costes (combustible, tasas, handling).
- Hook en `registrar_avlog` (idempotente por huella).
- UI: `GET /economia` (extracto), saldo en cabecera `/hangar` (aunque hangar aún sin salud), `/gestion/economia` ajuste admin.
- Tests: 8-10 casos.
- **Criterio de salida:** 5 vuelos reales (APTO, NO APTO, FAIL, NO EVALUABLE, CSV) generan asientos correctos y saldo cuadra con `SUM`.

### Fase 2 — Desgaste visible (2 días, sin cobro)

**Objetivo:** el piloto ve cómo cada vuelo degrada su aeronave, pero aún no paga.

- DB: `aeronaves_piloto` con 6 salud + horas/ciclos.
- Cálculo: `desgaste_base + deltas por evento` (tabla §2.3), cap 15%.
- Hook: mismo punto que F1, tras economía.
- UI: `/hangar` con barras por componente, estado (operativa/recomendado/requerido/grounded), historial de deltas por vuelo.
- **Sin grounded efectivo ni cobro** — solo informativo. Permite calibrar deltas con vuelos reales antes de monetizar.
- Tests: deltas por landing_vs, stall, overspeed, idempotencia.

### Fase 3 — Mantenimiento con coste (2–3 días)

**Objetivo:** cerrar el bucle economía→desgaste→mantenimiento.

- Tipos ligero/completo + fórmulas de coste (§3.1).
- `POST /hangar/reparar` descuenta saldo y restaura salud, deja movimiento `mantenimiento`.
- Grounded <15% efectivo (bloquea ingreso, no grabación).
- UI: botón Reparar con preview de coste y % a restaurar, confirmación.
- Admin: ver salud ajena, forzar reparación.
- Tests: pago, saldo insuficiente (-500), grounded, reversión al borrar vuelo.
- **Criterio de salida:** piloto puede volar 10 vuelos variados y mantenerse solvente solo si vuela bien.

### Fase 4 — Flota y realismo afinado (1–2 semanas)

- Hangar múltiple: piloto posee N aeronaves (compra con saldo, `aeronaves_piloto` ya lo soporta con `UNIQUE(license_id, icao, matricula)`; añadir `precio_compra` por tipo).
- Precios diferenciados AVGAS/JET, tasas por aeródromo con tabla real, handling variable.
- Checks por horas (50h/100h) además de por salud.
- `vfe` real por flap si se implementa chequeo de flaps en scoring (hoy no evaluado).
- `/plan` filtra aeronaves operativas; `/aerolinea` ranking de coste/mantenimiento.
- Telemetría ampliada si hace falta (`schema.py` + `gui.py` SimConnect: CHT, EPR).

### Fase 5 — Economía avanzada (cuando F1-F4 estén asentados)

- Leasing / alquiler por vuelo (no comprar).
- Seguro (prima fija + franquicia por FAIL).
- Mercado de segunda mano (vender aeronave con salud <100% a otro piloto, precio depreciado).
- Eventos de aerolínea (retos mensuales con bonus, ver `estadisticas.actividad_mensual`).
- Integración VATSIM real: horas VATSIM verificadas contra `data.vatsim.net` para bonus (no autodeclarado).
- Si se introduce caja de aerolínea central, reparto de ingresos y nómina.

**Orden recomendado:** F1 → F2 → breve calibración con vuelos reales (1 semana) → F3 → pausa de balanceo → F4 → F5 solo si F1-F3 demuestran que la economía engancha sin frustrar.

---

## 8. Decisiones abiertas (requieren humano)

| # | Pregunta | Opciones | Recomendación |
|---|---|---|---|
| 1 | ¿Saldo inicial? | 0 / 5000 / 10000 | **5000** (ver §1.1). |
| 2 | ¿Permitir saldo negativo? | No / hasta -500 / ilimitado | **Hasta -500 con bloqueo de compra** (no bloquea vuelo). |
| 3 | ¿Grounded bloquea grabación o solo ingreso? | Solo ingreso / también grabación | **Solo ingreso en F1-F3** (no se impide grabar). |
| 4 | ¿Economía por piloto o caja central de aerolínea? | Piloto / central / mixto | **Piloto en F1-F3**, central solo si F5. |
| 5 | ¿Precio combustible único o diferenciado? | Único / AVGAS vs JET | **Único en F1**, dos precios en F4. |
| 6 | ¿Desgaste RNG o determinista? | Determinista / +RNG | **Determinista** (auditable). |
| 7 | ¿Mantenimiento obligatorio o recomendado? | Obligatorio <15% / siempre opcional | **Obligatorio <15% (grounded)**. |
| 8 | ¿Reimportación genera segundo asiento? | No / sí | **No** (idempotente por huella). |

---

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Deltas de desgaste mal calibrados (demasiado punitivo o irrelevante) | F2 sin cobro para calibrar con vuelos reales; fórmulas con constantes en `config/economia.yaml` (no hardcode), admin puede ajustar sin deploy. |
| Economía genera frustración ("no puedo volar por dinero") | Saldo nunca bloquea vuelo; descubierto -500; bono bienvenida; FAIL no cobra pero tampoco multa extra. |
| Reimportación duplica dinero | Índice único por huella + `ya_registrado` guard. |
| Concurrencia SQLite con varios workers gunicorn | Mismo patrón que `cuentas.py`: `conexion()` con `timeout=10` y `WAL`; movimientos en transacción corta. |
| Saldo cacheado diverge de `SUM(movimientos)` | Función `recalcular_saldo()` y endpoint admin de reconciliación; test de invariante. |
| IDOR en `/hangar/<otro>` | Reutilizar `es_de`/`piloto_actual()` y `PERM_GESTIONAR_USUARIOS` para admin. |
| Piloto con CSV (sin scoring) se queda sin ingreso siempre | Documentado: CSV no genera ingreso (§1.2) pero sí coste; se informa en UI. |

---

## 10. Qué NO hacer en este plan

- No tocar `scoring.py`, `profiles.yaml`, `schema.py` en F1-F3 (solo consumirlos).
- No añadir dependencias nuevas (ni Redis, ni Postgres) — todo SQLite stdlib.
- No inyectar fallos en MSFS ni pedir telemetría nueva.
- No reintroducir `D0` ni duplicar pantallas (ver `ARQUITECTURA.md §2`).
- No generar `eva.exe` (ver `ARQUITECTURA.md §9`).
- No pedir contraseña VATSIM.

---

## 11. Próximo paso propuesto

1. Humano revisa este documento y resuelve las 8 decisiones de §8 (una línea por cada una basta).
2. Si se aprueba F1, implementar en este orden: migración DB → `web/economia.py` (cálculo puro + tests) → hook en `estadisticas.registrar_avlog` → `economia_movimientos` + `usuarios.saldo` → UI `/economia` y saldo en cabecera → tests E2E con 5 vuelos reales.
3. Dejar F2 sin cobro 1 semana para calibrar deltas antes de monetizar en F3.

---

*Archivo canónico de intercambio entre IAs: `D:/proyectos/airhispania/ARQUITECTURA.md`. Al cerrar sesión, añadir entrada en § Registro de sesiones.*
