# Esquema de pantallas — EvA

> Equivalente de `esquema_pantallas.md`. Códigos D1–D7 / W* se reutilizan
> **solo como mapa mental** del modelo Airhispania. La verdad son las
> rutas Flask y los módulos tkinter de este repo. `[CONF]`

**Estilo web:** `web/static/eva.css` y plantillas que extienden
`base.html`. Referencia visual de despacho: `plan.html`.

---

## Mapa general (construido)

```
  [dashboard.py D1]
       │ login cuentas SQLite
       ├─► abre navegador cartilla
       ├─► vPilot (externo)
       └─► gui.py D4 (± LED mini)
                │ .avlog.json
                ▼
  /login ──► /  (cartilla)
               ├ /plan                 D2
               ├ /planes-de-vuelo      D3
               ├ /vuelo/<nombre>       D6+W1
               ├ /vuelos  /registro    D7
               ├ /aerolinea            (no es W2)
               ├ /vuelta-espana
               └ /gestion/*            admin
```

---

## Escritorio

### D1 — Lanzador `[CONF]` `dashboard.py`

Login `license_id` + contraseña contra `cuentas` (mismo SQLite que la web).
Luces: MSFS en marcha, vPilot proceso, VATSIM (consulta de red + CID de
`vPilotConfig.xml`). Abre el grabador y URLs locales de la cartilla.

No custodia USER/PASS de VATSIM. `[CONF]`

### D4 — Grabación `[CONF]` `gui.py`

Always-on-top, LED de conexión, tiempo grabado, transpondedor, modo
auto/manual, botón grabar. Indicativo sale de settings, no se pide el
plan en la ventana (docstring: lo rellena el sim).

### D5 — Compacto

No hay ejecutable ni ruta propia. Hay `_led_window` / modo minimizado en
`gui.py`. `[CONF]` existencia de atributos; `[PEND]` si se considera
producto D5 o solo detalle de UI.

---

## Web (Flask)

| Código modelo | Ruta real `[CONF]` | Plantilla |
|---|---|---|
| Login | `/login` `/logout` | `login.html` |
| Alta | `/solicitar-alta` | `solicitar_alta.html` |
| Recupero | `/recuperar` `/restablecer/<testigo>` | `recuperar.html` `restablecer.html` |
| D7 cartilla | `/` | `index.html` |
| D2 | `/plan` | `plan.html` |
| D3 | `/planes-de-vuelo` | `planes_de_vuelo.html` |
| D6+W1 | `/vuelo/<nombre>` | `vuelo.html` |
| JSON crudo | `/vuelo/<nombre>/json` | — |
| D7 lista | `/vuelos` | `vuelos.html` |
| Subida | `/registro` | `registro.html` |
| Detalle registro | `/registro/<nombre>` | `detalle_registro.html` |
| Aerolínea | `/aerolinea` | `aerolinea.html` |
| Descarga cliente | `/descargar` | `descargar.html` |
| Vuelta ES | `/vuelta-espana` | `vuelta_espana.html` |
| Admin usuarios | `/gestion/usuarios` | `gestion_usuarios.html` |
| Admin vuelos | `/gestion/vuelos` | `gestion_vuelos.html` |
| Admin pistas | `/gestion/pistas` | `gestion_pistas.html` |
| Admin reglas | `/gestion/reglas` `/gestion/reglas/<id>` | `gestion_reglas.html` `gestion_regla_detalle.html` |

### APIs `[CONF]`

| Ruta | Uso |
|---|---|
| `POST /api/registro/upload` | Importar log/CSV |
| `POST /api/vuelo/lanzar` | Abrir grabador **solo local** |
| `POST /api/plan/guardar` | Guardar plan |
| `POST /api/plan/fpl` | Texto FPL |
| `POST /api/plan/vatsim-url` | URL prefile |
| `POST /api/plan/apply-payload` | Aplicar payload al planificador |
| `GET /api/aeropuerto/<icao>` | Coords para mapa |
| `POST /vuelos/<nombre>/borrar` | Borrar propio |
| `POST /planes-de-vuelo/<id>/borrar` | Borrar plan |

### W2 ficha piloto

**No existe** `/datos`. `[N/A]`

### D4 desde la web

Botón VUELO: si `puede_lanzar_vuelo`, `POST /api/vuelo/lanzar`; si no,
enlace a `/descargar`. `[CONF]` `base.html`

---

## Navegación lateral `[CONF]` `base.html`

AEROLÍNEA · PLAN · VUELO · VUELOS · PLANES DE VUELO · VUELTA A ESPAÑA ·
REGISTRO · (admin) USUARIOS · TODOS LOS VUELOS · PISTAS · REGLAS.

Píldora «VATSIM» en cabecera: elemento visual; **no** está documentado en
plantilla como feed vivo en todos los modos. `[PEND]` si el LED de cabecera
web se alimenta de verdad o es estático.

---

## Relación con el modelo Airhispania (solo correspondencia)

| Modelo | EvA |
|---|---|
| X1 VATSIM login | `[N/A]` cuenta EvA |
| X2 vPilot | Lanzado desde D1; no es telemetría |
| X3 Sim | SimConnect |
| X4 dispatcher | `[N/A]` sin cable |
| X5 almacén | `.avlog.json` + SQLite + `importados.json` |
