# Auditoría de datos: home y cartilla — EvA

> Equivalente de `auditoria_datos_home_cartilla.md`. De dónde sale cada
> cifra que ve el piloto. `[CONF]` salvo `[PEND]`.

## 1. Home aerolínea `/aerolinea`

Vista: `aerolinea.html`. Agregados: `client/avcars/estadisticas.py`
leyendo `vuelos_resumen` en `web/data/eva.db`. `[CONF]` `app.py` ruta
`aerolinea`.

Campos de la tabla (esquema en `cuentas.py`) `[CONF]`:

| Columna | Origen al integrar |
|---|---|
| `huella` | hash de traza o SHA-256 CSV |
| `license_id` | dueño |
| `callsign` `origen` `destino` `aeronave` `matricula` | log / plan |
| `reglas` | VFR/IFR del plan |
| `red` | VATSIM / IVAO / OFFLINE |
| `atc_controlled` | bool/NULL |
| `distancia_nm` `duracion_min` | summary / track |
| `combustible_usado_kg` `combustible_restante_kg` | summary; NULL si no viene |
| `calidad` | apto / no_apto / no_evaluable / NULL (CSV) |
| `puntuacion` | `Verdict.score` o NULL |
| `perfil_evaluacion` | easy/normal/hard |
| `incidencias` | JSON de reglas falladas |
| `fecha` | fecha del vuelo |
| `creado` | integración |

KPIs (`kpis_globales`, tops, `actividad_mensual`,
`incidencia_mas_frecuente`): **solo filas ya integradas**. Un `.avlog.json`
en disco no subido no cuenta. `[CONF]`

Mapa de rutas: `app.py` `_geo_para_mapa` usa `airports.json` / API
aeropuerto. Si falta ICAO, ese punto no geocodifica. `[INF]` helper en
`app.py`.

## 2. Cartilla `/` (index)

Lista de vuelos **del piloto de sesión**, no de toda la flota. `[CONF]`
decorador de login + filtro por `license_id`.

Detalle `/vuelo/<nombre>`: relee el fichero, vuelve a llamar
`evaluate_flight` (o muestra evaluation guardada — `[PEND]` si cachea el
JSON `evaluation` o recalcula siempre; `app.py` `detalle` hace ambas cosas
en la práctica: load + scoring). Comprobar la función `detalle` al
cambiar: no afirmar caché si recalcula.

`/vuelos` vs `/`: una es lista de ficheros/grabaciones con acciones; la
otra es cartilla/evaluación. No unificar en la UI sin leer ambas
plantillas. `[CONF]` rutas distintas.

## 3. Lo que no aparece `[CONF]`

- Pasajeros, payload, coste de fuel: comentarios en `cuentas.py` (2026-08-18)
  dejan claro que **no se capturan**; no hay columnas inventadas.
- Confirmación de prefile VATSIM.
- Nota del dispatcher.

## 4. Ficheros de control (no SQL) `[CONF]`

`importados.json` (huellas), `trusted_log.json` (auditoría; confirmar
escrituras en `app.py`/`importacion.py` antes de tratarlo como SIEM),
`sesion_activa.json` (puente desktop).

## 5. Discrepancia con `DOCUMENTACION_PROYECTO.md`

Ese informe de raíz usa nombres de tablas/rutas que **no coinciden** con
`cuentas.py` + `app.py` actuales. Ignorarlo. `[CONF]` esta auditoría.
