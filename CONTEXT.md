---
fecha: 2026-08-28
ultima_sesion: IDOR parcheado 55eece5 re-verificado + plan economía V1 15 secciones en thoughts/plans/2026-08-28 + reparto entre agentes
estado: en_progreso
---

# CONTEXT - EvA Airliner

## Reparto entre agentes (acordado 2026-08-28)

Dos agentes trabajan sobre **el mismo árbol de ficheros**. No son dos máquinas
con ramas distintas: es un único directorio, así que las ramas de git no
protegen de nada. Lo que protege es repartirse el terreno y avisarse.

| Zona | Quién | Ficheros |
|---|---|---|
| Código y pruebas | Claude Code | `client/`, `web/**.py`, `web/tests/`, plantillas, migraciones |
| Documentos, planes y auditorías | OpenCode | `docs/`, `thoughts/`, `CONTEXT.md`, `AGENTS.md` |
| Commits | Claude Code | Norma del usuario: los demás dejan los cambios sin comitear para que él los revise |

**Antes de tocar código**, reclamar el dominio (añadido el 2026-08-28, antes no
existía y por eso nadie lo usaba):

    python D:\proyectos\coord.py claim eva --who "quien seas"
    python D:\proyectos\coord.py release

Para documentos no hace falta lock: basta con respetar el reparto.

**Este fichero es el parte de traspaso.** Leerlo al empezar la sesión y
actualizarlo al terminar. Es lo que evita que cada uno redescubra por su cuenta
lo que el otro ya hizo.

**Cuidado con `D:\proyectos\airhispania`**: es la copia anterior al renombre del
2026-08-20 y está muerta (ver `LEEME_ESTO_ESTA_MUERTO.md` allí). El 2026-08-28
se anotaron tareas en su `TAREAS.md` por error; ese fichero no lo lee nadie.

## Trabajo completado
- Guía práctica de las 26 reglas: `docs/guia_practica_reglas_puntuacion.md` (perfil **normal**; 20 evaluadas + 6 no implementadas sin inventar criterios). Enlace en `docs/README.md`.
- Auditoría de `web/` con code-review-excellence: CSRF/sesión/PBKDF2 bien; **IDOR** en `GET /vuelo/<nombre>/json` parcheado en 55eece5 (`web/app.py:1362` `es_de`) y re-verificado 2026-08-28; `web/tests/test_propiedad_vuelos.py:1` cubre.
- Skill `code-review-excellence` instalada en `.agents/skills/` (`npx skills add …`; TLS npm necesitó `--use-system-ca`).
- En el árbol (posible otro chat): `/vatsim` + `/api/vatsim-data` en `web/app.py` y `web/templates/vatsim_live.html` (público, sin login).
- Fuera de este git (`D:\proyectos`): panel `lanzador_aviacion.pyw` + `lanzador_aviacion.bat`; `todos.bat` abre el panel (no arranca todo a la vez).
- Plan economía V1 15 secciones: `thoughts/plans/2026-08-28-economia-v1-15-secciones.md:1` reconcilia `docs/plan_economia_mantenimiento.md` (infra) con `docs/economia_v1_decisiones.md` (6€/NM + alquiler 60/140/250/400/900, P0-P4 4/5/6/8); anotado en `D:/proyectos/airhispania/TAREAS.md` (⚠️ repo muerto, reanotar aquí) y `ARQUITECTURA.md:441`.

### Sesión de código del 2026-08-28 (Claude Code, 6 commits en `main`, **sin subir**)
- `55eece5` **IDOR** de `/vuelo/<nombre>/json` parcheado. Repasadas las demás rutas: las de `/gestion/` sin comprobación llevan `@permiso_requerido` y deben ver todo.
- `b770910` **Aviso de aeródromo de salida** (`client/avcars/ubicacion.py`): si el avión no está donde dice el plan, avisa. No bloquea, y nunca por falta de datos. Idea tomada del cliente de FlyAnt.
- `7e25bf2` **Espacio aéreo oficial de ENAIRE** (`web/tools/descargar_enaire.py`): 11 capas, 1.576 elementos → `web/data/aeronautica.db` (ignorado en git, se regenera). Atribución obligatoria puesta en `base.html`.
- `2e07bd9` Documentos: `docs/economia_v1_decisiones.md`, `docs/analisis_ant_tracker_v2.md`, `docs/datos_espacio_aereo_enaire.md`.
- `96d886e` Pruebas de rutas de vuelo. **Corregido después**: dije que «no había ni una sola prueba de rutas web» y era falso — hay **209 en `web/test_*.py`**, en ficheros sueltos y no en una carpeta `tests/`, que es por lo que no las vi. El IDOR no se coló por falta de pruebas sino porque estaban escritas ruta por ruta: `test_app.py` cubría la propiedad de `/vuelo/<nombre>` pero nadie escribió la de su hermana `/vuelo/<nombre>/json`. Lo aportado de verdad está en `web/test_rutas_de_vuelo.py`: `test_ninguna_ruta_de_vuelo_se_le_escapa_a_un_intruso` recorre el mapa de URLs de Flask, así que una ruta nueva bajo `/vuelo/` que se olvide de comprobar propiedad falla sola. Verificado quitando el parche del IDOR.
- `7c55ffe` **Regla de espacio aéreo** `airspace_zones`: invasión de zonas P/R/D y prohibición VFR. Penaliza, no suspende. Aparece sola en `/gestion/reglas` con 5 valores configurables.

Decisiones de diseño de esa sesión, por si hay que discutirlas:
- La regla de zonas **no acusa si no puede afirmarlo**: hacen falta margen al borde, permanencia mínima y ≥2 muestras. 8 de 238 zonas no traen referencia vertical entendible y se dejan fuera.
- El muestreo de la traza **se queda como está** (1 Hz bajo 1.500 ft AGL, 1/10 s en crucero). Consecuencia asumida: la validación de zonas es indicio, no prueba.
- La economía **no tiene caja de aerolínea**: el dinero solo paga el taller. Con eso, la V1 es un marcador de cuánto cuida el piloto los aviones, no una economía cerrada.

## Trabajo pendiente
- Confirmar en Clouding: arranque por `wsgi:app` (no `python web/app.py` con debug), cuenta `pruebas` bloqueada.
- Decidir si desplegar `/vatsim` o dejarlo solo local.
- X-Plane `poll()` sigue sin cerrar.
- Comprobar URL Clouding si el host cambia.
- Monitor VPS (opcional): Netdata en localhost + túnel SSH; OpenCode no sustituye gráficos.
- Economía V1 F1 pendiente de visto humano (no programar hasta aprobar `thoughts/plans/2026-08-28-economia-v1-15-secciones.md`).

## Decisiones importantes
- Números de la guía = perfil `normal` (`profiles.yaml`); easy/hard solo relectura.
- Beacon/nav/taxi/strobe **restan puntos**; no son fallo grave (el motor manda, no fichas antiguas).
- Little, EvA cartilla y Airhispania comparten puerto **5000**: no arrancar más de una.
- `/vatsim` y `/api/vatsim-data` están en la lista pública de `exigir_sesion` (sin login).

## Problemas conocidos
- `/registro/<nombre>` no usa `_find_by_name`: construye `directory / nombre` con lo que llega en la URL. **Comprobado el 2026-08-28: NO es explotable** — `..\..\Windows\win.ini`, `..\data\eva.db` y `C:\Windows\win.ini` dan los tres 404, porque `es_de()` devuelve falso para un fichero que no es un vuelo. Pero se salva por accidente, no por diseño: si alguien reordena el código o relaja `es_de`, se abre. Arreglo: usar `_find_by_name`, que compara nombres y nunca construye rutas (por eso lo hace así `detalle()`).
- Hash de traza Fase 1: se confía en el del cliente.
- CSP vs Leaflet/OSM en `vuelo.html` (unpkg + tiles); `aerolinea.html` ya usa vendor local.

## Cierre del 2026-08-28: TODO SUBIDO a origin/main (`dce134b`)

Ya no queda nada sin comitear ni sin subir. `main` local y `origin/main` están
alineados. Existe además la rama `flota-y-mantenimiento` con los mismos
commits, por si se quiere abrir el PR (no se pudo: **`gh` no está instalado**
en este equipo).

Lo que entró después del bloque anterior:

- `09f261b` **El peso de `/plan` ya se recalcula con los ocho aviones.** Eran
  dos fallos: el TBM 930 tenía su MTOW en un bloque del yaml donde el lector no
  miraba, el DA62 no lo tenía en ninguna parte, y los kilos de carga se
  descartaban en silencio con el tipo en «Ninguno».
- `6e18db4` **Un único sitio para los datos de flota: `aircraft.yaml`.** Había
  una segunda copia escrita a mano en `web/despacho_pesos.py` y se habían
  desincronizado (C172 con 620 kg de vacío cuando el simulador modela 767).
  Nuevo `client/tools/leer_flight_model.py`, que lee de MSFS y **no escribe
  nada**: imprime para copiar a mano con su fuente.
- `ef789de` + `1253ad5` + `c6f9fc3` **Diseño de desgaste y mantenimiento**
  (`docs/desgaste_y_mantenimiento_tabla.md`). Sin implementar.
- `0eaeff3` + `7092ff9` + `dce134b` Trabajo de **OpenCode** que estaba en el
  árbol: Leaflet servido en local (arregla H-07 de la auditoría sin abrir la
  CSP a un CDN), VATSIM Live en el menú, tres documentos y la plantilla de
  estándar. Comiteado a petición del usuario; la autoría no es de Claude Code.

**Decisiones de economía cerradas** (todo en `docs/economia_v1_decisiones.md` y
`docs/desgaste_y_mantenimiento_tabla.md`):

- Progresión P0→P4: **4/5/6/8 vuelos APTO**, 23 en total.
- **6 €/NM igual para todas las clases** y sin base fija por ruta.
- Alquiler fijo por hora: 60/140/250/400/900.
- Saldo negativo: **el piloto sigue volando**, se avisa al responsable.
- Flota: **ocho células con matrícula, `EC-EVA` a `EC-EVH`, sin exclusiva.** Si
  dos eligen el mismo avión, vuelan los dos y el desgaste se suma.
- **Nada inmoviliza.** La provisión por hora se cobra en cada vuelo y el daño
  lo paga quien lo causa en el momento: ese pago *es* la reparación, así que no
  hay botón de reparar ni problema de gorrones.

## Pendientes de la sesión de código (2026-08-28)
- **7 pruebas rotas de antes**: 6 fallos en `test_scoring`, `test_data_quality`, `test_regresion_vuelo_real`, más `test_simconnect_hybrid.py`, que ni se recoge (importa `HAS_FSTELEMETRY`, que ya no existe). Idénticos en `eva` y en `eva-pre`, así que no son cosa del entorno. Una suite con fallos crónicos deja de avisar cuando se rompe algo de verdad, y además **cortan `probar_pre.sh`** antes de que dé el visto bueno (`set -o pipefail`): mientras sigan ahí, ese script nunca dirá que se puede desplegar.
- **Las pruebas de web viven sueltas en `web/test_*.py`, no en `web/tests/`.** 13 ficheros, 206 pruebas. Conviene saberlo antes de concluir que algo no está probado.
- **Techo VFR** con la capa `SECTORES_VFR` (`VFRMAXALT` relleno en el 90% de sus filas). Es la continuación natural de `airspace_zones`.
- **Desviación de ruta**: bloqueada hasta que existan rutas definidas por la aerolínea. Con ruta de texto libre escrita por el piloto es circular y no se puede puntuar.
- **Relanzar `web/tools/descargar_enaire.py` cada ciclo AIRAC** (28 días). Hoy es manual.
- **Consolidar `SESSION_CONTEXT.md`** que el usuario bajó de otra máquina a `E:\descargas`: allí se construyó medio EvA en paralelo sin saber que este repo existía.
- **Implementar la economía y el desgaste.** El diseño está cerrado y no queda
  nada bloqueante; falta la tabla de costes por avión y el código.
- **Falta la columna `toma_fpm` en `vuelos_resumen`.** Hoy `incidencias` guarda
  solo nombres de reglas falladas, no valores, y sin el régimen de toma no se
  puede cobrar el daño del aterrizaje.
- **Un tercio de los vuelos de prueba no traen tipo de avión**, o lo traen
  corrupto (`ATCCOM.ATC_NAME CESSNA.0.text`, una clave de traducción de MSFS
  que se cuela en vez del designador). Sin tipo no hay límites POH, ni
  desgaste, ni tarifa.
- **De la auditoría de Gemini** (`~/.gemini/antigravity/.../auditoria_eva.md`),
  verificada una por una: el bug de la distancia CSV ×60 (`csv_reader.py:158`)
  sigue abierto y es el más urgente, porque corrompe cartillas hoy. También
  reales: path traversal latente en `/registro/<nombre>`, CORS `*` en el proxy
  VATSIM, `app.py` con 2.500 líneas. **Falsos:** las tres APIs «sin
  autenticar» (probado: 302 sin sesión, las cubre `exigir_sesion`) y la cuenta
  `pruebas` «activa» (está bloqueada y es rol piloto).
- De FlyAnt (ver `docs/analisis_ant_tracker_v2.md`): detección de rebote, histéresis en luces, servir la lista de la flota desde el servidor.
- Al mes de rodaje del aviso de aeródromo de salida: mirar `debuglog` y decidir si se convierte en bloqueo.

## Proximo paso recomendado
- Esperar visto humano del plan `thoughts/plans/2026-08-28-economia-v1-15-secciones.md:1` antes de F1 (BD + `web/economia.py` + hook `estadisticas.py:63`).
