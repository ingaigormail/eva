# Aeródromos, pistas y VFR — EvA

> Equivalente de `espec_oc05_aerodromos_vfr.md` de Airhispania, **solo**
> con lo que hay en este repo. No hay ticket OC-05 ni handoff OpenCode
> aquí. `[N/A]` esos artefactos.

## 1. Catálogo de aeropuertos `[CONF]`

`client/config/airports.json` — ICAO → nombre y coordenadas. Comentario en
`config.py`: extraído de vatspy-data-project (CC-BY-SA). **No incluye
geometría de pistas.** Por eso `runway_excursion` está en `not_evaluated`.

Uso: mapas, `/api/aeropuerto/<icao>`, distancia en planificador (haversine
en JS de `plan.html` si está cableado). `[CONF]` ruta API; `[PEND]` cada
campo del JSON sin abrir el fichero entero.

## 2. Gestión de pistas `[CONF]`

Rutas: `GET /gestion/pistas`, `POST /gestion/pistas/guardar`.
Plantilla: `gestion_pistas.html`.

Sirven como **referencia** para detectar pista usada (heading / designador).
No sustituyen un AIP completo ni polígonos. Persistencia concreta (tabla vs
JSON) `[PEND]` sin leer el cuerpo de `gestion_pistas_guardar`; la ruta
existe.

## 3. Datos España `[CONF]` / `[PEND]`

Existe `web/migrar_aerodromos_es.py` (reescribe `CREATE TABLE` a `*_es`).
Hay comentarios en `matriz_reglas.md` sobre `eva.db` y tablas
`aerodromos_es` / `pistas_es` / `puntos_vfr_es`. **Verificar en una DB
real** si esas tablas están pobladas: el esquema de `cuentas.py` **no** las
crea. `[PEND]` población; `[CONF]` el migrador existe.

## 4. Vuelta a España `[CONF]`

`web/importar_vuelta_espana.py`: 21 etapas hardcoded, `ROUTE_ID = "vae-2026"`,
tablas `rutas_vfr` / `progreso_rutas`. UI `/vuelta-espana`. Tests
`test_vuelta_espana.py`. **No** lee el Excel original a propósito.

## 5. Plan VFR vs evaluación `[CONF]`

El planificador guarda ruta como texto. `route_deviation` **no** se evalúa
(no hay waypoints parseados a lat/lon). Semicircular VFR tampoco.

## 6. vs Airhispania OC-05 `[N/A]`

Especificación de aeródromos VFR de Airhispania (VRP, polígonos CTR, etc.)
no está implementada como módulo en EvA. No copiar requisitos de aquel
documento como si fueran de este código.
