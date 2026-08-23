# Mapa web EvA — para enviar

**Fecha:** 2026-08-23  
**Fuente de rutas:** `web/app.py` y `web/templates/base.html`.  
**Plantilla visual:** `web/templates/plan.html` + `web/static/eva.css`.

Solo páginas **web**. D1 y D4 son escritorio (`dashboard.py`, `gui.py`).

---

## 1. Plantilla de estilo

Copiar de `plan.html` / `eva.css`, no reinventar.

| Pieza | Valor `[CONF]` |
|---|---|
| Fondo | `--bg: #eef1f6` |
| Panel | `--panel: #ffffff` |
| Acento | `--azul: #2563eb` |
| Marca | `--azul-oscuro: #1e3a8a` / `--marca-cyan: #16a3e0` |
| Lateral | `nav.lateral` en `base.html` |
| Logo | `web/static/eva_logo.svg` (y PNG en cabecera según plantilla) |

No copiar SALDO / SHOP / MIS OBJ de referencias ajenas. `[CONF]` no existen
en `base.html`.

---

## 2. Qué es web y qué no

```
ESCRITORIO
  D1  dashboard.py
  D4  gui.py
  D5  no hay producto aparte (LED mini en gui)

WEB  (Flask; app.py documenta :5000)
  login / alta / recupero
  /                cartilla
  /plan            despacho
  /planes-de-vuelo biblioteca
  /vuelo/<nombre>  veredicto + mapa
  /vuelos          lista
  /registro        subida
  /aerolinea       KPIs
  /vuelta-espana   21 etapas
  /descargar       cliente
  /gestion/*       admin
```

---

## 3. Flujo del piloto

```
/login → / (cartilla)
          → /plan → guardar → /planes-de-vuelo
          → VUELO → (local) lanzar gui  |  (servidor) /descargar
          → volar → .avlog.json
          → /registro → upload → /vuelos → /vuelo/<nombre>
          → /aerolinea  (flota)
          → /vuelta-espana
```

---

## 4. Estado

| Página | Estado |
|---|---|
| Login / alta / recupero | hecho |
| Cartilla `/` | hecho |
| Plan `/plan` | hecho |
| Planes guardados | hecho |
| Evaluación `/vuelo/<nombre>` | hecho |
| Subida | hecho |
| Aerolínea | hecho |
| Vuelta a España | hecho |
| Gestión usuarios/vuelos/pistas/reglas | hecho |
| W2 `/datos` | **no existe** |
| Dispatcher X4 | **no cableado** |

Prefile VATSIM/IVAO: abre formulario; EvA no sabe si se envió. `[CONF]`
