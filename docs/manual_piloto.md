# EvA — Manual del piloto

EvA graba tu vuelo mientras vuelas y produce un fichero que después subes a
tu cartilla para que se evalúe.

Este texto describe el **producto EvA** (`D:\proyectos\eva`), según el cliente
de escritorio y la web del mismo repositorio. `[CONF]`

---

## Qué necesitas

- **Windows** para el grabador de escritorio (el paquete declara
  `SimConnect` solo en `win32`). `[CONF]` `client/pyproject.toml`
- Un simulador con el que el cliente sepa hablar:
  - **MSFS 2020 / 2024 o Prepar3D**, vía SimConnect. `[CONF]`
    `client/avcars/connectors/simconnect_client.py`
  - **X-Plane**: el transporte UDP de paquetes DATA está implementado;
    **el mapeo a estado de vuelo (`poll`) no está cerrado** y lanza
    `NotImplementedError`. `[CONF]` `xplane_udp.py`
- Nada obliga a instalar Python si usas el ejecutable empaquetado
  (`client/tools/build_exe.py`, `Crear_instalador.bat`). `[CONF]`

### Sobre SimConnect

EvA lee el simulador con la librería **Python-SimConnect**, sin plugin
dentro del simulador. `[CONF]`

Si el indicador no pasa de desconectado con el simulador abierto, falta el
cliente SimConnect del propio simulador (SDK / componentes de cliente). El
repositorio no instala SimConnect por ti. `[INF]` comentarios del conector.

---

## Instalación del cliente

El flujo documentado en código/scripts:

1. Empaquetado PyInstaller: `client/tools/build_exe.py`. `[CONF]`
2. Instalador: `client/tools/installer.py` y `client/Crear_instalador.bat`. `[CONF]`

La carpeta de grabaciones la resuelve `client/avcars/paths.py`
(`recordings_dir`). `[CONF]` El valor concreto en un PC instalado **no está
fijado en este repositorio** más allá de esa lógica. `[PEND]` ruta por
defecto del instalador en una máquina real.

---

## Cómo se usa (piloto)

El procedimiento publicado en la web (`/descargar`) es el de operación.
Los nombres de botones son los de **PLAN** y del grabador. `[CONF]`

1. Instalar EvA Airliner (Windows). Se crea la carpeta de vuelos.
2. En **PLAN** (`/plan`): crear el plan y usar **GENERAR PLAN ICAO** o
   **ABRIR EN VATSIM**. Sin una de las dos, **el vuelo no se evalúa**.
   **GUARDAR PLAN SIN VATSIM** solo guarda el plan en local.
3. Abrir **primero el simulador**, luego EvA Airliner.
4. Grabar: **GRABAR** (manual) o automático al **empezar a rodar**.
   Al terminar, **FINALIZAR VUELO**.
5. Fichero en **Grabaciones** (carpeta de instalación).
6. Subirlo en **REGISTRO** (`/registro`).

### Qué hace el grabador por debajo `[CONF]`

Ventana: `client/avcars/gui.py` (`EvaApp`).

Modos (`settings.py`: `MODO_AUTOMATICO`, `MODO_MANUAL`):

- **Automático**: al rodar (~**2,7 kt**, `TAXI_MOVEMENT_THRESHOLD_KT`) pasa a
  `TAXIING` y **empieza a grabar**. A **50 kt** GS (`SPEED_THRESHOLD_KT`) entra
  en carrera de despegue. Cierra al confirmar toma y parada.
- **Manual**: el piloto pulsa **GRABAR** / **FINALIZAR VUELO**.

Tiempos de confirmación (`timing.py`): `[CONF]`

| Qué | Valor |
|---|---|
| Consulta al simulador | 1,0 s |
| Refresco de ventana | 0,25 s |
| Datos congelados | 4 lecturas iguales |
| Despegue confirmado | 3,0 s sin contacto y ≥ 50 ft AGL |
| Aterrizaje confirmado | 5,0 s de contacto |
| Vuelo cerrado (parado) | 10,0 s bajo umbral |
| Muestreo cerca del suelo | 1 s (&lt; 1500 ft AGL) |
| Muestreo en crucero | 10 s |

Si abres EvA con el avión ya volando, la máquina arranca en
`WAITING_SIMULATOR` / tierra y **no inventa** un despegue a mitad de vuelo:
hay que usar el modo manual para grabar un vuelo ya empezado. `[INF]`
transiciones de `flight_state_machine.py`

El escritorio también incluye un **lanzador** (`dashboard.py`) con login
frente a las mismas cuentas que la web y luces de vPilot / VATSIM (CID leído
de `vPilotConfig.xml` cuando existe). `[CONF]`

**EvA no sube el fichero sola.** El docstring de `gui.py` apunta a la
cartilla local `http://127.0.0.1:5000/registro`; el piloto elige qué
importar. `[CONF]`

---

## Dónde quedan los vuelos

El escritor (`recorder/flight_log_writer.py`) genera JSON con sufijo
**`.avlog.json`**. `[CONF]` `LOG_SUFFIX`

Hay volcado parcial (`PARTIAL_SUFFIX`, prefijo `en_curso_`) para no perder
el vuelo si se cierra el proceso. `[CONF]`

El nombre incluye marca de tiempo (`FILENAME_TIMESTAMP`). `[CONF]`

Ese fichero es el que se sube en **REGISTRO** (`/registro`). También se
acepta CSV de telemetría (`web/csv_reader.py`); el CSV **no lleva dueño ni
hash de traza** y se identifica por SHA-256 del contenido. `[CONF]`
`web/importacion.py`

---

## Cartilla web

Arranque local documentado en `web/app.py`: `python web/app.py` →
`http://127.0.0.1:5000`. `[CONF]`

Semilla de cuentas: usuario **`pruebas` / `pruebas`**, rol administrador.
`[CONF]` `cuentas.py`, `auth.py`. En un servidor público esa cuenta es un
riesgo: el README de despliegue de este repo lo menciona en espíritu
equivalente. `[INF]`

### Qué ves (navegación real de `web/templates/base.html`) `[CONF]`

| Entrada | Ruta Flask | Para qué |
|---|---|---|
| AEROLÍNEA | `/aerolinea` | KPIs agregados |
| PLAN | `/plan` | Planificador / prefile |
| VUELO | lanza grabador en local, o `/descargar` en servidor | |
| VUELOS | `/vuelos` | Lista de grabaciones |
| PLANES DE VUELO | `/planes-de-vuelo` | Planes guardados |
| VUELTA A ESPAÑA | `/vuelta-espana` | 21 etapas VFR |
| REGISTRO | `/registro` | Subir `.avlog.json` / CSV |
| (admin) USUARIOS | `/gestion/usuarios` | Altas y bloqueos |
| (admin) TODOS LOS VUELOS | `/gestion/vuelos` | Flota |
| (admin) PISTAS | `/gestion/pistas` | Pistas de referencia |
| (admin) REGLAS | `/gestion/reglas` | Catálogo de reglas |

Detalle de un vuelo evaluado: `/vuelo/<nombre>`. `[CONF]`

---

## Preguntas frecuentes

**¿Puedo minimizar el grabador?**  
La ventana está pensada para una esquina; el muestreo corre en hilo aparte
en el escritor. `[INF]` diseño de `gui.py` / `FlightRecorder`

**¿Y si pauso el simulador?**  
Se intenta distinguir pausa de datos congelados (`SIM_PAUSED` si existe;
si no, lecturas idénticas). Las pausas se guardan como eventos `pause` con
`duration_s` y el motor las puntúa. `[CONF]`

**¿Y si acelero el tiempo?**  
`max_sim_rate_observed` > 1 es **fallo duro** (`time_compression`). `[CONF]`

**¿Se me ha cerrado el simulador?**  
Datos inválidos o pérdida de conexión devuelven la máquina a espera; el
parcial en disco permite recuperar. `[CONF]` `find_interrupted` /
`recover`

**¿EvA envía el vuelo sola a internet?**  
El grabador escribe en local. La cartilla es otro proceso (Flask). Correo
(Gmail API / Mailjet / SMTP) solo para altas y contraseñas, no para el log.
`[CONF]`

**¿X-Plane?**  
Hasta que `XPlaneUDPConnector.poll()` esté verificado, **no hay grabación
X-Plane de extremo a extremo**. `[CONF]`
