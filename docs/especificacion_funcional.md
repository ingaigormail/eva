# Especificación funcional — EvA

> Equivalente de `especificacion_funcional.md` de Airhispania: producto
> descrito contra **código de `D:\proyectos\eva`**, con marcas de origen.
>
> **Convención:** `[CONF]` implementado y visto en código · `[INF]` se deduce
> de comentarios · `[PEND]` no consta en el repo · `[N/A]` existe en el
> modelo Airhispania y no en EvA.
>
> Donde no hay dato, queda `[PEND]`. No se rellena a ojo.

---

## 0. Alcance

EvA es cartilla + grabador para vuelos de simulador, con evaluación VFR
automática compartida entre escritorio y web. `[CONF]`

**No es** el despachador EVA de `eva-dispatcher` ni el cockpit
`flight-sim-cockpit`. `[N/A]` esos repos.

---

## 1. Actores `[CONF]`

| Actor | Cómo entra |
|---|---|
| Piloto | Cuenta `usuarios.license_id` + contraseña; rol `piloto` |
| Administrador | Mismo modelo; rol `admin` → `PERM_GESTIONAR_USUARIOS` |
| Anónimo | Solo login, solicitar alta, recuperar / restablecer |

No hay OAuth VATSIM en EvA. El CID de vPilot se usa en el lanzador para
luces de red, no para autenticar la cartilla. `[CONF]` `dashboard.py`,
`auth.py`

---

## 2. Identidad y altas `[CONF]`

- Alta **no es auto-registro**: `POST /solicitar-alta` crea fila en
  `solicitudes`; un admin aprueba (`/gestion/solicitudes/<id>`).
- Contraseñas: PBKDF2-SHA256, 260 000 iteraciones.
- Recuperación: `testigos` de un uso (`restablecer.py`); correo vía
  `correo.py`.
- Semilla: `pruebas` / `pruebas` administrador. **Debe bloquearse en
  producción.** `[INF]` riesgo operativo obvio; el repo no automatiza el
  bloqueo en el VPS (`[PEND]` procedimiento real del servidor).

---

## 3. Grabación `[CONF]`

| Req. | Estado |
|---|---|
| Grabación manual | Hecho (`gui.py` + `MODO_MANUAL`) |
| Grabación automática | Hecho (`FlightStateMachine`, 50 kt) |
| SimConnect MSFS/P3D | Hecho (unidades con heurística `_coerce_*`) |
| X-Plane `poll()` | **No** (`NotImplementedError`) |
| Muestreo adaptativo | Hecho (1 s / 10 s, 1500 ft AGL) |
| Parcial / recuperación | Hecho (`en_curso_`, `recover`) |
| Subida automática a la web | **No** (el piloto sube el fichero) |
| Firma criptográfica del log | **No** (hash de traza solamente) |

---

## 4. Plan de vuelo `[CONF]`

- UI: `GET /plan`, persistencia `POST /api/plan/guardar` → tabla `planes`.
- Listado: `/planes-de-vuelo`.
- FPL ICAO: `POST /api/plan/fpl` → `prefile.icao_fpl`.
- VATSIM/IVAO: URLs de formulario (`vatsim_prefile_url`, IVAO base64).
  **EvA no confirma** que el piloto pulsara Submit. `[CONF]` docstring de
  `prefile.py`
- `POST /api/plan/apply-payload`: existe; el significado exacto de
  `success: true` en todos los casos **no se ha auditado línea a línea**
  en esta pasada. `[PEND]`
- Pesos: `despacho_pesos.py` estimaciones etiquetadas; **no** son POH ni
  entran en `evaluate_flight`. `[CONF]`

---

## 5. Evaluación `[CONF]`

Ver `motor_evaluacion_v2.md` y `criterios_vfr.md`.

- Tres perfiles: `easy`, `normal`, `hard`.
- Solo VFR de producto; `RULE_SCOPE` ya etiqueta IFR futuro.
- Selector de perfil en `/vuelo/<nombre>`: `[PEND]` si la query `?perfil=`
  está cableada (la plantilla y `app.py` deben mirarse al cambiar UI).
  `evaluate_flight` sí recibe un perfil; la web carga perfiles con
  `load_profiles`. `[CONF]` import en `app.py`

---

## 6. Cartilla e importación `[CONF]`

- Subida: `POST /api/registro/upload`.
- Anti-duplicado: huella (`integrity.track_hash` o SHA-256 CSV).
- Anti-usurpación: `pilot.license_id` ≠ sesión → rechazo (código HTTP en
  `ImportacionRechazada`).
- CSV: sin dueño declarado; huella de contenido.
- Borrado propio: `POST /vuelos/<nombre>/borrar`.
- Admin: `/gestion/vuelos` subir/borrar cualquiera.

Hasta dónde protege la huella: **no** contra quien edita el JSON y
recalcula el hash. Documentado en `importacion.py`. `[CONF]`

---

## 7. Aerolínea y Vuelta a España `[CONF]`

- `/aerolinea`: KPIs de `estadisticas.py` sobre `vuelos_resumen`.
- `/vuelta-espana`: 21 etapas fijas en `importar_vuelta_espana.py`
  (`ROUTE_ID = "vae-2026"`), tabla `rutas_vfr`. No lee Excel.

---

## 8. Seguridad web `[CONF]`

CSRF Flask-WTF, CSP con nonce, HSTS, SameSite=Lax, `EVA_COOKIE_SECURE`,
bleach en `sanitize_input`, SQL parametrizado.

HSTS se envía siempre (`security.py`). En HTTP puro local puede ser
incómodo. `[CONF]` comportamiento; `[PEND]` si producción termina HTTPS
terminado en nginx.

---

## 9. Correo `[CONF]`

`correo.py`: Gmail API, SMTP, Mailjet API. Render bloquea SMTP
(`docs/RENDER_SETUP_EMAIL.md`). Config: `web/data/correo.json` /
variables de entorno (ver módulo). Secretos **no** deben ir a git.

---

## 10. Despliegue `[CONF]`

Scripts en `despliegue/`: `desplegar.sh` (backup, git pull, pip, import
check, restart, health), `nginx_eva.conf` (proxy 8000, body 20M,
`X-Forwarded-Proto`), `copia_seguridad.sh`, `userdata_clouding.yaml`.

No hay unit file systemd en el árbol. Puerto 5000 vs 8000 **discrepante**
entre `app.py`/`wsgi.py` y nginx. `[CONF]`

Host citado en README de despliegue: verificar antes de publicarlo como
URL canónica. `[PEND]`

---

## 11. `airliner/` `[CONF]`

README propio: app descargable distinta, grabación real y sync **en
roadmap**. No sustituye a `client/avcars`.

---

## 12. Requisitos que Airhispania documenta y EvA no tiene `[N/A]`

- Login VATSIM OAuth / captura de contraseña de red.
- Envío del plan por API de escritura VATSIM (no existe API pública de
  escritura; EvA usa prefile URL, igual que la corrección C-01 del
  documento Airhispania, pero **implementado a su manera** en `prefile.py`).
- Cliente vPilot como fuente de telemetría (EvA usa SimConnect).
- eva-dispatcher cableado al evaluador.
- Compacto D5 como ventana de producto documentada aparte: hay un LED
  mini en `gui.py` (`_led_window`) `[CONF]` pero no hay ruta Flask D5.
- Ficha piloto `/datos` (W2).
- Overlay in-sim de touchdown.

---

## 13. Datos de aeronave `[CONF]`

`aircraft.yaml`: regla de no inventar V-speeds; `null` = no evaluar.
`limite_efectivo()` prioriza POH sobre referencia sim.

Flota con bloques en el YAML (al menos C172 y otras claves ICAO en el
fichero). Cobertura POH incompleta a propósito.

---

## 14. Pendientes explícitos del código

| Ítem | Dónde |
|---|---|
| `XPlaneUDPConnector.poll` | `xplane_udp.py` |
| Firma del log | comentarios SEC `importacion.py` |
| Geometría de pista / ruta parseada | `not_evaluated` en scoring |
| Cable dispatcher | ausencia de imports |
| Alinear `reglas_info.py` con `RULE_SCOPE` | ids distintos en prosa vs motor |
