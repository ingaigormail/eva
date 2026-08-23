# EvA Airliner — resumen de inicio

Documento para dirección o para quien entra al proyecto: **qué es**, **cómo
funciona** y **dónde se entra**. Los detalles técnicos siguen en el resto de
`docs/`. Afirmaciones de producto contrastadas con el código (`[CONF]`).

---

## Qué hacemos

**EvA** (Evaluación de Vuelos / cartilla) es la plataforma de una aerolínea
virtual de simulador:

1. El piloto **planifica** el vuelo en la web y lo **presenta en VATSIM**.
2. **EvA Airliner** (programa de Windows) **graba** el vuelo desde el simulador.
3. El piloto **sube** el fichero a la **cartilla**.
4. Un **motor único** puntúa el vuelo (mismos criterios en el PC y en el servidor).

No es un cliente VATSIM (eso es vPilot). No envía el plan a VATSIM por API:
abre o genera el formulario y **el piloto pulsa enviar**. `[CONF]` `prefile.py`,
`plan.html`

---

## Piezas

| Pieza | Qué es | Dónde |
|---|---|---|
| **Cartilla web** | Flask: cuentas, plan, registro, evaluación, flota | `web/` |
| **EvA Airliner** | Grabador Windows (SimConnect → MSFS 2020/2024, Prepar3D) | `client/avcars/` |
| **Motor** | `evaluate_flight` (nota 0–100, fallos duros, VFR) | `client/avcars/evaluation/scoring.py` |
| **Instalador** | `setup.exe` en GitHub Releases (~53 MB) | ver URL abajo |

X-Plane: el UDP existe; **grabar un vuelo evaluable no está cerrado**. `[CONF]`

---

## Cómo funciona un vuelo (operación)

Este es el procedimiento publicado en `/descargar` y el que debe seguir el
piloto:

1. **Instalar** EvA Airliner (Windows 10/11).
2. En **PLAN** (`/plan`): rellenar el plan y usar **una** de estas dos opciones
   (botones reales de esa página):
   - **GENERAR PLAN ICAO** — texto para «Import ICAO FPL» en VATSIM.
   - **ABRIR EN VATSIM** — formulario VATSIM relleno; el piloto lo envía.
   **Si no se usa ninguna, el vuelo no se evalúa** (regla de producto en
   `/descargar`). `[CONF]` `descargar.html`, `plan.html`
3. **Abrir primero el simulador**, luego EvA Airliner.
4. Grabar:
   - **Manual:** botón **GRABAR**.
   - **Automático:** empieza al **rodar** (~2,7 kt / 5 km/h). Los **50 kt**
     marcan la carrera de despegue, no el inicio de la grabación. `[CONF]`
     `flight_state_machine.py`
   - Al terminar: **FINALIZAR VUELO**. `[CONF]` `gui.py`
5. El fichero queda en la carpeta **Grabaciones** de la instalación
   (`.avlog.json`).
6. Subirlo en **REGISTRO** (`/registro`).

**GUARDAR PLAN SIN VATSIM** solo archiva el plan en «Planes de vuelo»; **no**
sustituye a **GENERAR PLAN ICAO** ni a **ABRIR EN VATSIM**. `[CONF]` `plan.html`

---

## Direcciones de acceso

### Producción (VPS Clouding) `[CONF]` `despliegue/README.md`

| Qué | Dirección |
|---|---|
| **Web pública** | https://7c0cdce9-a46a-4339-9df6-50a26f00f11c.clouding.host |
| Login | `…/login` |
| Solicitar alta | `…/solicitar-alta` |
| Plan | `…/plan` |
| Descargar Airliner | `…/descargar` (sesión iniciada) |
| Registro (subir vuelo) | `…/registro` |
| Cartilla / vuelos | `…/` y `…/vuelos` |
| Aerolínea (KPIs) | `…/aerolinea` |
| Vuelta a España | `…/vuelta-espana` |
| SSH (solo clave) | `ssh eva@7c0cdce9-a46a-4339-9df6-50a26f00f11c.clouding.host` |

Si el dominio o el host cambian en el VPS, esta tabla puede quedar vieja;
la fuente en repo es `despliegue/README.md`. `[PEND]` comprobar en vivo.

### Instalador EvA Airliner `[CONF]` `web/app.py` `DESCARGA_URL`

https://github.com/ingaigormail/eva/releases/latest/download/setup.exe

(Variable `EVA_DESCARGA_URL` si se mueve.)

Código: https://github.com/ingaigormail/eva

### Desarrollo local `[CONF]` `web/app.py`

```
python web/app.py
```

http://127.0.0.1:5000 — puerto `PORT` si se define. Nginx de producción
apunta a **8000** (`despliegue/nginx_eva.conf`): no mezclar con el 5000 local.

Semilla de desarrollo: usuario **`pruebas` / `pruebas`** (admin). En
producción debe estar bloqueada. `[CONF]` `cuentas.py`, aviso en
`despliegue/README.md`

### Alta de piloto

No hay auto-registro libre: se **solicita alta** y un administrador
aprueba. `[CONF]` `/solicitar-alta`, `/gestion/usuarios`

---

## Qué ve el piloto en el menú web `[CONF]` `base.html`

| Menú | Ruta | Uso |
|---|---|---|
| AEROLÍNEA | `/aerolinea` | Estadísticas de flota |
| PLAN | `/plan` | Despacho y prefile VATSIM |
| VUELO | local: abre Airliner; servidor: `/descargar` | Grabar |
| VUELOS | `/vuelos` | Lista de grabaciones |
| PLANES DE VUELO | `/planes-de-vuelo` | Planes guardados |
| VUELTA A ESPAÑA | `/vuelta-espana` | 21 etapas |
| REGISTRO | `/registro` | Subir `.avlog.json` |
| USUARIOS / TODOS LOS VUELOS / PISTAS / REGLAS | `/gestion/…` | Solo admin |

---

## Evaluación (una frase)

Parte de 100, resta penalizaciones, **suspende** con fallos duros (p. ej.
compresión de tiempo, stall, toma muy dura) o si los datos no son
evaluables. Perfiles `easy` / `normal` / `hard`. Umbral típico de aprobado
en `normal`: **70**. Detalle: `criterios_vfr.md`, `motor_evaluacion_v2.md`.

---

## Lo que no hacemos (límites actuales)

- No grabamos X-Plane de punta a punta.
- No firmamos criptográficamente el log (hay hash de traza, no firma).
- No confirmamos que VATSIM recibiera el plan.
- No evaluamos desviación de ruta ni geometría de pista (faltan datos).
- El módulo `airliner/` del repo es **otro** prototipo; el producto de
  grabación es **`client/avcars`** (EvA Airliner). `[CONF]`

---

## Documentación siguiente

| Si necesitas… | Abre |
|---|---|
| Usar el grabador | `manual_piloto.md` |
| Arquitectura | `arquitectura_eva.md` |
| Requisitos con marcas | `especificacion_funcional.md` |
| Mapa de URLs | `MAPA_WEB_PARA_ENVIAR.md` |
| Servidor | `../despliegue/README.md` |
