# EvA — Análisis y arquitectura

Documento de arquitectura del repositorio `D:\proyectos\eva`, alineado en
forma con `arquitectura_eva.md` de Airhispania (secciones: punto de partida,
tecnología, componentes, flujos, persistencia, límites). El contenido es
solo de EvA. `[CONF]` salvo marca en contrario.

---

## 1. Punto de partida

EvA es una **cartilla de vuelos de simulación** más un **grabador de
escritorio**. El motor de evaluación **no se duplica**: web y CLI importan
`avcars.evaluation.scoring.evaluate_flight`. `[CONF]` `web/app.py`,
`client/avcars/cli.py`

Tres árboles de primer nivel:

| Árbol | Rol |
|---|---|
| `client/` | Paquete `avcars`: esquema, conectores, grabador, GUI, evaluación, cuentas |
| `web/` | Flask: cartilla, importación, gestión, planificador |
| `despliegue/` | Nginx, scripts de VPS, userdata Clouding |
| `airliner/` | Aplicación **aparte** (README: grabación MSFS/sync “roadmap”; no es el cliente `avcars`) `[CONF]` |

---

## 2. Tecnología `[CONF]`

| Pieza | Elección en el repo |
|---|---|
| Lenguaje | Python 3.10+ (`requires-python` del cliente) |
| Escritorio | tkinter (`gui.py`, `dashboard.py`) |
| Simulador MSFS/P3D | `SimConnect` / Python-SimConnect, solo Windows |
| Simulador X-Plane | UDP DATA; `poll()` no implementado |
| Web | Flask 3, Flask-WTF (CSRF), Gunicorn (requirements + wsgi) |
| Modelos | Pydantic v2 (`schema.py`) |
| Config | YAML (`profiles.yaml`, `aircraft.yaml`) + `airports.json` |
| Cuentas | SQLite `web/data/eva.db` (WAL), PBKDF2-SHA256 260 000 iteraciones |
| Empaquetado | PyInstaller |

No hay base PostgreSQL ni Redis en este árbol. `[CONF]` por ausencia.

---

## 3. Diagrama de componentes

```
                    ┌─────────────────────────────────────┐
                    │           Simulador                  │
                    │  MSFS/P3D SimConnect  │  X-Plane UDP │
                    └──────────┬────────────┴──────┬───────┘
                               │ poll()            │ receive_raw()
                               ▼                   ▼
                    ┌─────────────────────────────────────┐
                    │ client/avcars/connectors             │
                    │  SimPoller 1 Hz → SimState           │
                    └──────────────────┬──────────────────┘
                                       ▼
                    ┌─────────────────────────────────────┐
                    │ FlightStateMachine + FlightRecorder  │
                    │  → .avlog.json (+ .parcial)          │
                    └──────────────────┬──────────────────┘
                                       │ el piloto sube
                                       ▼
 ┌──────────────┐   evaluate_flight    ┌──────────────────────────────┐
 │ CLI avcars   │◄────────────────────►│ web/app.py (Flask)            │
 │ evaluate     │   mismo scoring.py   │ importacion + plantillas      │
 └──────────────┘                      └──────────────┬───────────────┘
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │ web/data/eva.db              │
                                       │ usuarios, solicitudes,       │
                                       │ planes, vuelos_resumen       │
                                       │ + ficheros de vuelo          │
                                       │ + importados.json            │
                                       └──────────────────────────────┘
```

---

## 4. Cliente (`avcars`) — qué es cada módulo `[CONF]`

| Módulo | Para qué | Entradas | Salidas |
|---|---|---|---|
| `schema.py` | Contrato del log | JSON | `FlightLog` |
| `config.py` | Perfiles, flota, aeropuertos | YAML/JSON | dicts |
| `connectors/base.py` | `SimState` / `SimConnector` | — | modelo común |
| `simconnect_client.py` | Lectura SimConnect | sim | `SimState` (+ `raw`) |
| `xplane_udp.py` | UDP X-Plane | datagramas | índices crudos; **no** `SimState` vía `poll` |
| `sim_poller.py` | Cadencia 1 Hz, congelado | conector | `Reading` |
| `flight_plan.py` | Plan MSFS en disco / SimConnect | `.pln` / sim | `FlightPlanData` |
| `flight_state_machine.py` | Auto start/stop | `SimState` | acciones grabar/guardar |
| `flight_log_writer.py` | Muestreo adaptativo + eventos | estados | `.avlog.json` |
| `evaluation/scoring.py` | Puntuación | `FlightLog` + perfil | `Verdict` |
| `evaluation/data_quality.py` | ¿Hay vuelo de verdad? | `FlightLog` | `QualityReport` |
| `evaluation/reglas_info.py` | Textos del panel admin | — | catálogo (puede desfasarse del motor) |
| `gui.py` | Grabador en vuelo | usuario + sim | fichero |
| `dashboard.py` | Lanzador D1 | login | abre web / vPilot / GUI |
| `cli.py` | `avcars evaluate` | path + perfil | veredicto (+ escribe evaluation en el JSON) |
| `cuentas.py` | Identidad compartida con la web | SQLite | auth |
| `planes.py` | CRUD planes del piloto | SQLite `planes` | filas |
| `prefile.py` | URL IVAO/VATSIM + FPL ICAO | plan | URL / texto; **no envía** el plan |
| `correo.py` | Gmail API / SMTP / Mailjet | config | email |
| `integrity.py` | SHA-256 de la traza | track | `track_hash` |
| `vpilot.py` | Detectar vPilot y CID | proceso / XML | bool / CID |
| `timing.py` | Todos los segundos del sistema | — | constantes + assert de coherencia |
| `paths.py` | Rutas con/sin PyInstaller | — | directorios |

Dependencia: `src/common` de flight-sim-cockpit **no aplica**. EvA no usa
esa capa. `[N/A]`

---

## 5. Servidor web `[CONF]`

`web/app.py` es el único punto de rutas HTTP del producto cartilla.

| Pieza | Función |
|---|---|
| `auth.py` | Decoradores sesión / permiso; reexporta `cuentas` |
| `importacion.py` | Huella, dueño, duplicados, `importados.json` |
| `avlog_reader.py` / `csv_reader.py` | Parseo de ficheros subidos |
| `despacho_pesos.py` | Semáforo de pesos en `/plan` (**no** entra en el motor) |
| `security.py` | CSP nonce, HSTS, X-Frame-Options, bleach |
| `importar_vuelta_espana.py` | 21 etapas en SQLite `rutas_vfr` |
| `wsgi.py` | `gunicorn ... wsgi:app`; inserta `client/` en `sys.path` |

Puerto **documentado en `app.py`**: 5000. **Nginx** (`nginx_eva.conf`)
hace proxy a `127.0.0.1:8000`. **wsgi.py** comenta `5000`. Hay que alinear
servicio systemd (no hay `eva.service` en `despliegue/` en este árbol) con
el proxy. `[CONF]` discrepancia de puertos en ficheros; `[PEND]` unidad
systemd real en el VPS.

---

## 6. Persistencia `[CONF]`

### SQLite `web/data/eva.db` (`cuentas.py`)

Tablas: `usuarios`, `solicitudes`, `testigos`, `planes`, `vuelos_resumen`.

Migración única: `usuarios.json` → SQLite, luego `usuarios.json.migrado`.

### Ficheros junto a la DB

| Fichero | Uso |
|---|---|
| `web/data/importados.json` | Huella → piloto/fichero (anti-duplicado) |
| `web/data/trusted_log.json` | Auditoría append-only (si el flujo de app lo escribe) |
| `web/data/sesion_activa.json` | Puente desktop ↔ web (`sesion_web.py`) |
| `web/data/secret_key.txt` | Cookie Flask (`secreto.py`) |
| `web/data/correo.json` | Credenciales correo (no commitear secretos) |

La ruta de **almacenamiento de `.avlog.json` en servidor** la decide
`app.py` al importar (directorio de búsqueda de vuelos). `[PEND]` valor
exacto de producción sin leer el arranque del VPS; en código hay helpers
`find_flights` / copia a carpeta de grabaciones.

---

## 7. Flujo principal de ejecución

1. Simulador expone variables.
2. `SimPoller` llama `poll()` cada `POLL_INTERVAL_S`.
3. `FlightStateMachine.update` decide empezar/parar.
4. `FlightRecorder` escribe track (1 s bajo 1500 AGL, 10 s en crucero) y
   eventos.
5. Hash de traza en `integrity`.
6. Piloto sube en `/api/registro/upload` (nombre de ruta real en `app.py`:
   comprobar `upload_telemetry` / registro).
7. `importacion` valida nombre, huella, dueño.
8. `evaluate_flight` + `check` de calidad.
9. Resumen en `vuelos_resumen`; detalle en `/vuelo/<nombre>`.

---

## 8. Integraciones externas `[CONF]`

| Sistema | Cómo |
|---|---|
| VATSIM prefile | URL de formulario; EvA **no** hace POST del plan (`prefile.py`) |
| IVAO prefile | JSON en Base64 en query |
| VATSIM status | dashboard consulta red (timeouts en código); no es telemetría de evaluación |
| Gmail | OAuth API en `correo.py` |
| Mailjet | API HTTPS (motivo: Render bloquea SMTP) `docs/RENDER_SETUP_EMAIL.md` |
| OpenStreetMap / Leaflet | mapa en plantillas (`web/static/vendor/leaflet`) |
| eva-dispatcher (otro repo) | **No hay import** en este árbol. `[N/A]` cable X4 |

---

## 9. Seguridad (hechos de código) `[CONF]`

- Contraseñas: PBKDF2-SHA256, 260 000 iteraciones (`cuentas.py`).
- CSRF: Flask-WTF.
- Cookies: HttpOnly, SameSite=Lax; `EVA_COOKIE_SECURE=1` para Secure.
- Cabeceras en `security.py` (CSP con nonce, HSTS siempre enviado — en HTTP
  local HSTS puede estorbar; está en código).
- Nombres de fichero: regex `^[A-Za-z0-9 ._-]+$`.
- Hash de traza: **no es firma**. `importacion.py` lo declara (SEC abierto).

---

## 10. Tests `[CONF]`

Hay baterías pytest en `client/tests/` y `web/test_*.py` (scoring, GUI
paths, importación, cuentas, planes, seguridad, Vuelta a España, etc.).
No hay en este repo un informe E2E de vuelo real obligatorio; hay
`test_regresion_vuelo_real.py` con fixtures.

---

## 11. Lo que este documento no afirma

- Que X-Plane grabe vuelos evaluables hoy.
- Que el plan se “envíe” a VATSIM.
- Que `airliner/` sea el cliente de producción (el README propio lo deja
  en roadmap).
- Cifras de usuarios o URL canónica de producción: `despliegue/README.md`
  habla de un host Clouding; **verificar en el VPS** antes de citarla como
  vigente. `[PEND]`
