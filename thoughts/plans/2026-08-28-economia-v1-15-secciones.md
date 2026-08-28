# Economía V1 — Plan de implementación 15 secciones

**Fecha:** 2026-08-28 · `thoughts/plans/2026-08-28-economia-v1-15-secciones.md`
**Estado:** PLAN (no programar aún, salvo parche IDOR ya restaurado)
**Base:** `docs/plan_economia_mantenimiento.md:1` + `docs/economia_v1_decisiones.md:1` (decisiones 2026-08-27 mandan sobre tarifas) + `client/config/aircraft.yaml:1` + `client/avcars/evaluation/scoring.py:33` + `client/avcars/estadisticas.py:63` + `web/app.py:112` + `D:/proyectos/airhispania/ARQUITECTURA.md:1`
**Conflicto resuelto:** tarifa por clase 8/12/18 de Plan antiguo → **6 €/NM única** + alquiler fijo por clase (60/140/250/400/900) de `docs/economia_v1_decisiones.md:102`. El plan antiguo sigue válido como infraestructura; los números de tarifa/coste se toman del documento de decisiones.

---

## 1. Resumen ejecutivo

EvA ya puntúa cómo vuelas (`scoring.py:33` → 0-100 + FAIL, 26 reglas). Economía V1 añade **consecuencia**: dinero (+ingreso/−costes) y desgaste (6 componentes) que obliga a pagar taller. Filosofía: determinista, auditable, una línea por coste (“hard 320fpm → tren −8% → 340 EVA€”).

**Qué hace el dinero en V1:** `docs/economia_v1_decisiones.md:11` — solo paga reparaciones (y alquiler fijo). No compra flota (desbloqueo por examen, `client/avcars/cuentas.py:618`), no alimenta caja central (no existe), no paga nómina. Es un marcador de cuidado, no una economía cerrada.

---

## 2. Modelo de moneda y titular

- **Moneda:** `EVA€` entero, ficticia.
- **Titular:** `usuarios.license_id` (piloto). Sin caja aerolínea (`docs/economia_v1_decisiones.md:33`). Flota compartida de aerolínea, desgaste por aeronave compartida vs por piloto queda abierto (`docs/economia_v1_decisiones.md:212` — V1: “el avión aparece donde haga falta”, desgaste sumado si se comparte matrícula).
- **Saldo inicial:** 5000 EVA€ (propuesta `docs/plan_economia_mantenimiento.md:27`) — calibrar tras 30 vuelos; `docs/economia_v1_decisiones.md:216` deja saldo inicial abierto.
- **Negativo:** permitido, con aviso único al cruzar a <0 y al recuperarse + marca en `/gestion/usuarios` (`docs/economia_v1_decisiones.md:155`). Sin bloqueo de vuelo; en negativo no puede reparar → degradación sigue afectando puntuación. Límite técnico −500 si se quiere cap (`docs/plan_economia_mantenimiento.md:96`).
- **Visibilidad:** cada piloto solo ve su saldo; responsable ve todos (`docs/economia_v1_decisiones.md:168`, sigue `es_de()` `web/app.py:284`).

---

## 3. Ingresos por vuelo

Solo si `verdict.evaluable == True`; `NO EVALUABLE` no genera ingreso (pero sí costes si los hay) — `docs/economia_v1_decisiones.md:40`. FAIL→0 ingreso.

**Fórmula V1 vigente** (`docs/economia_v1_decisiones.md:129`):

```
ingreso = 6 €/NM × distancia_nm × (1 + 0.6·P + 0.8·C) × calidad
```
- `distancia_nm` de `estadisticas.py:63` / `FlightLog`.
- `P` y `C` son flags de plan (pasajeros/carga) si existen; si no, 0. Antes era bonus VATSIM/ATC + perfil hard; queda subsumido aquí.
- `calidad` sale del **motor** (`scoring.py:33`), no de tabla paralela (`docs/economia_v1_decisiones.md:34`): APTO 1.0, NO APTO 0.5, FAIL 0.0. Landing rate solo modula dentro del motor, no duplica castigo.
- Sin base fija por ruta `B` (`docs/economia_v1_decisiones.md:125`) — evita farmear 20 NM.
- `max(distancia, 20NM)` piso antiexploit corto (`docs/plan_economia_mantenimiento.md:102`).

Tarifa única 6 €/NM corrige el 9:1 anterior (C172 vs CJ4) a 1.6:1 por hora (`docs/economia_v1_decisiones.md:139`).

---

## 4. Costes por vuelo

Siempre se descuentan (incluso FAIL/NO EVALUABLE si hay dato):

```
coste_vuelo = combustible + tasas + handling + alquiler
```
- **Combustible:** `fuel_used_kg × precio` (AVGAS/JET hoy 2 €/kg único `docs/plan_economia_mantenimiento.md:67` → F4 diferenciar 2.2/1.6). Si `NULL`, estimar `0.15×mtow×(dist/500)` o `NULL→0` si vuelo sin datos (`docs/economia_v1_decisiones.md:40`). `fuel_used_kg` viene de `schema.py:176` (kg, no galones — fix vs doc consolidado).
- **Tasas:** por `aerodromos_es.type` (`web/data/eva.db` 817 aeródromos): large 120 / medium 60 / small 25 / desconocido 40 (`docs/plan_economia_mantenimiento.md:69`).
- **Handling:** 30 €/vuelo (`docs/plan_economia_mantenimiento.md:70`) — base fija residual válida tras quitar `B`.
- **Alquiler fijo por hora y clase** (`docs/economia_v1_decisiones.md:106`): C172 60, DA62/BE58 140, C208/TBM9 250, B350/DHC6 400, C25C 900 (por horas de vuelo `FlightLog.timing`). Reemplaza el 2% marginal.

**Neto:** `ingreso − coste`. Ejemplo validado `docs/economia_v1_decisiones.md:135`: C172 60NM +414 (71% margen), Caravan 260NM +977 (46%), CJ4 400NM +970 (29%) — el jet deja margen fino que se vuelve rojo en NO APTO, incentivo buscado.

---

## 5. Desgaste

Determinista, 6 componentes comunes (`docs/plan_economia_mantenimiento.md:117`): motor, tren, flaps, estructura, frenos, hélice (solo hélice/turbohélice). Fuente = `Verdict` + `TrackPoint` (`bank_deg`, `stall_warning`, `overspeed_warning`, `landing_vs` etc.) `schema.py:176`.

- **Base:** 0.4%/h a todos (`docs/plan_economia_mantenimiento.md:136`).
- **Deltas por evento** (`docs/plan_economia_mantenimiento.md:140`): hard +4% tren, very_hard +12% tren/+5% estructura, gear_up +25% tren, bank fail +7% estructura, stall +6% motor, overspeed +8% motor/+5% estructura, etc. Cap 15%/vuelo. `qnh`/luces no desgastan.
- **Persistencia:** por aeronave (V1 flota compartida: desgaste sumado si dos pilotos usan misma matrícula — hueco `docs/economia_v1_decisiones.md:213`). Salud 0-100%.
- **Umbrales** (`docs/plan_economia_mantenimiento.md:165`): ≥70 operativa, 40-69 recomendado, 15-39 requerido, <15 grounded.

---

## 6. Mantenimiento

- **Ligero:** +25% al componente peor. **Completo:** 100%. Fórmulas coste `docs/plan_economia_mantenimiento.md:184`: ligero `80+2×%`, completo `400+1.5×%`. En negativo: permite reparar pero deja saldo más negativo (no bloquea).
- **Correctivo** si tren <40% tras tren arriba → obliga completo.
- **Grounded <15%** (`docs/plan_economia_mantenimiento.md:198`): aeronave no disponible en `/plan` (selector deshabilitado con tooltip). No bloquea grabación, solo ingreso (`docs/economia_v1_decisiones.md:158`).
- **Pago:** transacción `usuarios.saldo` + fila `economia_movimientos` concepto `mantenimiento`.

---

## 7. Progresión y desbloqueo (P0-P4)

`docs/economia_v1_decisiones.md:58` — 23 vuelos APTO en total, no 55:

- P0 C172 entrada; P1 DA62/BE58 4; P2 C208/TBM9 5; P3 B350/DHC6 6; P4 C25C 8.
- Mecánica ya existe `cuentas.py:618 cambiar_categoria()`. Flujo: sistema marca “listo para examen” al cumplir mínimo → escuela examina → aprobar sube categoría (`docs/economia_v1_decisiones.md:49`).
- **Vuelo válido para contador:** solo APTO, ≥30 min, ≥25 NM, origen≠destino (antifarmeo `docs/economia_v1_decisiones.md:53`).

Dinero no desbloquea flota; categorías tampoco dan dinero.

---

## 8. Realismo vs complejidad

Tabla de decisiones `docs/plan_economia_mantenimiento.md:230`:

- Tarifa única + alquiler fijo: realismo medio, complejidad baja (corrige doble pago por milla+velocidad).
- Combustible único V1, split F4.
- Desgaste determinista por eventos scoring (sin telemetría nueva `schema.py`).
- Sin fallos MSFS inyectados.
- Salud por matrícula compartida (simplificar: “aparece donde haga falta” V1, reserva F4).
- Sin mercado/seguro/leasing hasta F5.

Cada coste explicable en una frase y una query.

---

## 9. Integración BD (`web/data/eva.db`)

SQLite WAL, `client/avcars/cuentas.py:102` `conexion()` + `migrar_esquema()`.

```sql
ALTER TABLE usuarios ADD COLUMN saldo INTEGER NOT NULL DEFAULT 5000;

CREATE TABLE economia_movimientos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  license_id TEXT NOT NULL REFERENCES usuarios(license_id),
  fecha TEXT NOT NULL, concepto TEXT NOT NULL, importe INTEGER NOT NULL,
  saldo_resultante INTEGER NOT NULL, huella TEXT,
  detalle TEXT NOT NULL DEFAULT '{}', creado_por TEXT NOT NULL DEFAULT ''
);
CREATE INDEX economia_piloto ON economia_movimientos(license_id, fecha);
CREATE UNIQUE INDEX economia_huella_unica ON economia_movimientos(huella) WHERE huella IS NOT NULL;

CREATE TABLE aeronaves_piloto (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  license_id TEXT NOT NULL, icao TEXT NOT NULL, matricula TEXT NOT NULL DEFAULT '',
  salud_motor REAL NOT NULL DEFAULT 100, salud_tren REAL NOT NULL DEFAULT 100,
  salud_flaps REAL NOT NULL DEFAULT 100, salud_estructura REAL NOT NULL DEFAULT 100,
  salud_frenos REAL NOT NULL DEFAULT 100, salud_helice REAL NOT NULL DEFAULT 100,
  horas_totales REAL NOT NULL DEFAULT 0, ciclos INTEGER NOT NULL DEFAULT 0,
  estado TEXT NOT NULL DEFAULT 'operativa', actualizado TEXT NOT NULL,
  UNIQUE(license_id, icao, matricula)
);
```

Compat: no tocar `vuelos_resumen`; unir por `huella`. `estadisticas.borrar_por_huella()` revierte movimientos y saldo. `docs/plan_economia_mantenimiento.md:252` + `docs/economia_v1_decisiones.md:222`.

---

## 10. Integración web (`web/app.py`)

- **Módulo puro:** `web/economia.py` (y `web/mantenimiento.py`) — `calcular_asiento(huella, flight, verdict) → dict`.
- **Hook:** `POST /api/registro/upload` tras `estadisticas.registrar_avlog()` idempotente por `huella` (`estadisticas.py:63` `ya_registrado`). Si resumir falla, upload no se revierte (`ARQUITECTURA.md:173`).
- **Rutas nuevas** (con `exigir_sesion`, no públicas como `/vatsim` `web/app.py:112`): `GET /hangar` (barras salud, estado, saldo), `POST /hangar/reparar`, `GET /economia` (extracto paginado), `GET /api/economia/saldo`, `GET /gestion/economia` (admin ajustes + marca saldos negativos).
- ** `/plan`** deshabilita aeronaves grounded.
- **Seguridad:** reutilizar `es_de()`/`piloto_actual()`/`PERM_GESTIONAR_USUARIOS` (`docs/plan_economia_mantenimiento.md:339`). CSRF ya en `web/app.py:117`. IDOR `crudo()` `web/app.py:1362` ya parcheado 55eece5 (verificado 2026-08-28).

---

## 11. Antiexploits y auditoría

- Reimportación idempotente por `huella` → no segundo asiento (`docs/plan_economia_mantenimiento.md:101`).
- Distancia piso 20 NM, combustible cap `0.3×mtow` + flag `fuel_anomalo`.
- Ruta repetida >15% en 30d → −10% tarifa (optimizer 30 vuelos 111k frenado).
- Vuelo válido filtrado para P1-P4 evita farmear circuitos.
- Saldo negativo avisa 1 vez + marca en `/gestion/usuarios` (no spam por vuelo).

---

## 12. Fases 1-5

- **F1 MVP económico (2-3d):** saldo + `economia_movimientos`, fórmula 6€/NM + alquiler fijo + tasas, hook upload, UI `/economia`, admin ajustes. Criterio: 5 vuelos reales cuadran `SUM`.
- **F2 Desgaste visible (2d, sin cobro):** `aeronaves_piloto` + deltas, `/hangar` barras, sin grounded. Calibra deltas 1 semana.
- **F3 Mantenimiento con coste (2-3d):** ligero/completo, grounded <15 bloquea ingreso, `POST /hangar/reparar`. Criterio: 10 vuelos variados solo solvente si vuela bien.
- **F4 Flota/realismo (1-2 sem):** hangar múltiple, AVGAS/JET split, checks 50/100h, `vfe` por flap si scoring lo implementa, `/plan` filtra.
- **F5 Avanzado:** leasing, seguro, mercado segunda mano, eventos mensuales (`estadisticas.actividad_mensual`), VATSIM verificado para bonus.

Orden: F1→F2→calibración→F3→pausa→F4→F5 solo si engancha. `docs/plan_economia_mantenimiento.md:345`.

---

## 13. Configuración

`client/config/economia.yaml` (no hardcode) — constantes para calibrar sin deploy:

```yaml
tarifa_por_nm: 6
alquiler_hora_por_clase: { ligera: 60, bimotor_piston: 140, turboprop_mono: 250, turboprop_bi: 400, jet: 900 }
precio_combustible_kg: 2
tasas: { large: 120, medium: 60, small: 25, desconocido: 40 }
handling: 30
desgaste_base_por_h: 0.4
cap_desgaste_por_vuelo: 15
umbrales: { operativa: 70, recomendado: 40, grounded: 15 }
```

Admin `/gestion/economia` + `recalcular_saldo()` reconcilia `saldo` vs `SUM`.

---

## 14. Testing

- **Puro:** `client/tests/test_economia_calculo.py` (tarifas, deltas, cap, pisos).
- **Web:** `web/test_economia.py` con `configurar_almacen(tmp)` (`cuentas.py:102`): APTO genera ingreso, FAIL 0, NO EVALUABLE 0 con coste si hay dato, reimportación idempotente, combustible NULL estimado, grounded <15, pago restaura y descuenta, saldo negativo aviso, filtro vuelo válido P1-P4.
- **Propiedad:** `web/tests/test_propiedad_vuelos.py:132` ya cubre rutas `/vuelo/` (incluye `crudo`).
- **E2E:** 5 vuelos reales (APTO/NO APTO/FAIL/NO EVALUABLE/CSV) generan asientos y desgaste correctos.

---

## 15. Riesgos y decisiones abiertas

Riesgos `docs/plan_economia_mantenimiento.md:420`: deltas mal calibrados, frustración por saldo, duplicado por huella, concurrencia WAL, saldo cacheado diverge, IDOR hangar, CSV sin ingreso.

Decisiones cerradas 2026-08-27 (`docs/economia_v1_decisiones.md:29`): no caja, calidad del motor, desbloqueo por examen, mínimo 4/5/6/8, alquiler fijo, negativo con aviso.

Abierto (`docs/economia_v1_decisiones.md:179` + `docs/plan_economia_mantenimiento.md:403`): saldo inicial exacto, `aeronaves_piloto` por piloto vs matrícula compartida + reserva, vuelos a medias, payload ponderado (hoy siempre conviene máximo), indicadores (dinero generado vs gastado, saldo medio, beneficio/vuelo), ubicación flota V1.

---

**Próximo paso:** humano valida §3/4/7/13 números; si ok, F1 en orden `web/economia.py` → BD → hook → UI → tests. No programar hasta visto.
