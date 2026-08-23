# Traspaso UI web — EvA

> Equivalente de `traspaso_ui_web.md`. Para quien toque HTML/CSS **sin**
> reescribir el motor. Si este texto y el código divergen, manda el código.

## 0. Qué es EvA en tres frases `[CONF]`

Cartilla de aerolínea virtual: el piloto planifica, graba con el cliente y
sube un `.avlog.json`. El mismo `evaluate_flight` puntúa en local y en el
servidor. La web **presenta** veredictos; no reimplementa reglas.

## 1. Sistema de diseño `[CONF]` `web/static/eva.css`

```css
--bg: #eef1f6;
--panel: #ffffff;
--panel-alto: #f4f6fa;
--borde: #e2e6ee;
--texto: #1e293b;
--tenue: #7c8698;
--azul: #2563eb;
--azul-claro: #eaf1ff;
--azul-oscuro: #1e3a8a;
--verde: #16a34a;
--rojo: #dc2626;
--ambar: #d97706;
--marca-cyan: #16a3e0;
--sombra: 0 1px 2px rgba(30,41,59,.04), 0 8px 24px -12px rgba(30,41,59,.10);
```

Tipografía: la de `eva.css` / `base.html` (sistema). Códigos ICAO: clase
mono en `plan.html` si existe.

**No añadir** SALDO, TIENDA ni barra de “salud avión”: no hay backend.

Logo: estáticos bajo `web/static/` (`eva_logo.svg` / PNG según plantilla).

Plantilla de layout: `base.html` (`nav.lateral`, cabecera, `csrf_token()`).
Referencia de formulario: `plan.html`.

## 2. CSRF `[CONF]`

- Meta: `<meta name="csrf-token" content="{{ csrf_token() }}">` en `base.html`.
- Formularios: hidden `csrf_token`.
- `fetch` POST: header `X-CSRFToken` (ver `plan.html`, `registro.html`).

Sin ese header los POST JSON fallan.

## 3. Inventario de plantillas `[CONF]` `web/templates/`

| Plantilla | Ruta |
|---|---|
| `base.html` | layout |
| `login.html` | `/login` |
| `solicitar_alta.html` | `/solicitar-alta` |
| `recuperar.html` `restablecer.html` | recupero |
| `index.html` | `/` |
| `plan.html` | `/plan` |
| `planes_de_vuelo.html` | `/planes-de-vuelo` |
| `vuelo.html` | `/vuelo/<nombre>` |
| `vuelos.html` | `/vuelos` |
| `registro.html` | `/registro` |
| `detalle_registro.html` | `/registro/<nombre>` |
| `aerolinea.html` | `/aerolinea` |
| `descargar.html` | `/descargar` |
| `vuelta_espana.html` | `/vuelta-espana` |
| `gestion_*.html` | admin |
| `error.html` | errores |

## 4. Qué no tocar desde UI

- `scoring.py`, `profiles.yaml` (umbrales).
- Hash / dueño en `importacion.py`.
- Semilla `pruebas`/`pruebas` (sí: no documentarla en pantallas públicas).

## 5. Leaflet `[CONF]`

Vendor en `web/static/vendor/leaflet/`. Mapas de vuelo/aerolínea: leer el
JS embebido en la plantilla correspondiente; no hay SPA aparte.
