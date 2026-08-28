# Qué tengo que hacer desde que soy identificado como piloto hasta mi primer vuelo

Guía práctica para un piloto nuevo de EvA Airliner. Lenguaje sencillo, sin rodeos y solo con lo que el sistema hace hoy. Cuando algo no existe en el proyecto se marca como **información pendiente de confirmar**.

> Fuentes usadas: `web/app.py:594` `/solicitar-alta`, `client/avcars/solicitudes.py:28`, `client/avcars/cuentas.py:493`, `client/avcars/cuentas.py:64` categorías P0-P4, `docs/manual_piloto.md:49`, `docs/resumen_inicio.md:42`, `docs/guia_practica_reglas_puntuacion.md:9`, `client/config/profiles.yaml:9`. Si aquí y el código discrepan, manda el código.

---

## Pregunta que responde esta guía

**¿Qué tengo que hacer desde que soy identificado como piloto hasta que realizo mi primer vuelo?**

Respuesta corta: pedir el alta → que un administrador te dé de alta → poner tu contraseña → instalar el grabador → preparar el plan en la web → grabar el vuelo → subirlo. Abajo está el paso a paso.

---

## 1. Identificación o selección

**Qué significa aquí.** En EvA no hay una “selección” externa. “Ser identificado” es que tú (o alguien que te propone) pides entrar en la aerolínea virtual.

**Qué tienes que hacer.**
- Entrar en la web pública en **Solicitar alta** (`/solicitar-alta`). No hace falta tener cuenta para verla (`web/app.py:164`).
- Rellenar el formulario.

**Qué te piden en ese formulario** (`web/app.py:597`, `solicitudes.py:28`):
- **Callsign o ID de EVA** (tu indicativo, ej. `EVA18L`). Obligatorio. No puede estar ya dado de alta.
- **Nombre y apellidos**. Obligatorio.
- **Correo electrónico** donde avisarte. Obligatorio y debe ser válido. No puede estar ya usado por otro piloto (`cuentas.py:510`).
- **ID de VATSIM (CID)**. Opcional. Si vuelas en VATSIM, ponlo aquí para que tus horas de red se puedan cruzar después.

Término: **Callsign** = indicativo que te identifica en radio y en la cartilla. En EvA se guarda como `license_id` y no distingue mayúsculas (`EvA18L` = `EVA18L`).

**Quién interviene.** Tú rellenas; el sistema guarda la **solicitud** (no una cuenta todavía).

**Para pasar al siguiente paso.** Que la solicitud quede registrada. Si pides dos veces con el mismo ID y sigue pendiente, la segunda actualiza la primera, no duplica (`solicitudes.py:47`).

---

## 2. Comprobación de requisitos

**Qué se comprueba, automáticamente y luego a mano:**

1. Que el **Callsign/ID no exista ya** (`web/app.py:614` — si existe, te manda a “He olvidado mi contraseña”).
2. Que el **correo sea válido** y **no esté en uso** (`cuentas.py:100`).
3. **Información pendiente de confirmar:** el proyecto no define otros requisitos previos (horas de simulador, titulación real, edad, etc.). No se han encontrado en código ni docs. Si tu aerolínea pide algo más (por ejemplo, pertenecer a un grupo), eso está fuera de este sistema.

**Quién interviene.** El servidor valida los campos al enviar. Después, un **administrador** ve la solicitud en **Gestión > Usuarios** (`/gestion/usuarios`).

**Para pasar al siguiente paso.** Que un administrador **apruebe** la solicitud. Mientras no lo haga, no tienes cuenta y no puedes entrar.

---

## 3. Documentación y trámites

**Qué tiene que hacer el administrador** (`web/app.py:838` `gestion_solicitud`):
- Pulsar **Aprobar** (o Rechazar). Si aprueba, el sistema crea tu **cuenta** con una contraseña aleatoria que nadie conoce. Queda registrada como `activa` y categoría `P0` (*New Member*) (`cuentas.py:111`).
- El sistema te envía un **correo con un enlace** para que elijas tu contraseña. El enlace caduca en **24 horas** y solo sirve una vez (`web/app.py:762`).

**Qué tienes que hacer tú:**
- Abrir el correo (revisa spam) y pulsar el enlace (`/restablecer/<testigo>`).
- Elegir una contraseña de **al menos 6 caracteres** y repetirla (`web/app.py:744`).
- Si el correo no llegó o el enlace caducó, un administrador puede reenviártelo desde Gestión > Usuarios (“enlace”, `web/app.py:976`).

**Documentos / requisitos que necesitas:** solo el correo que pusiste. No se pide DNI, licencia real ni otro papel en el sistema actual. **Información pendiente de confirmar** si tu organización pide documentación adicional fuera de EvA.

**Para pasar al siguiente paso.** Tener la cuenta en estado **activa** y haber puesto tu contraseña. Con eso ya puedes iniciar sesión en `/login`.

---

## 4. Formación y preparación

**Qué se espera que sepas antes de volar.** EvA evalúa tu vuelo con **20 reglas** (nota 0–100, apruebas con **≥70** en perfil normal, sin fallos graves y con datos suficientes). Las 6 reglas restantes hoy no puntúan.

Lee, al menos:
- **Guía sencilla de reglas** (`docs/guia_practica_reglas_puntuacion.md:9`): alineación en pista, punto de toma, dureza de toma, aproximación estable, combustible, pausas, tiempo acelerado, alabeo, luces, QNH, tren, VNE/VMO, etc.
- **Resumen de una página** (`docs/puntuacion_resumen_vuelo.md:1`): tabla de qué resta puntos (-5 a -25) y qué suspende directo (toma muy dura >600 fpm, tiempo >1×, alabeo >60°, stall, overspeed, VNE/VMO).
- **Manual del piloto** (`docs/manual_piloto.md:49`): cómo se planifica, graba y sube.

**Formación oficial reglada:** **información pendiente de confirmar**. En el código no hay curso obligatorio, examen ni horas mínimas para pasar de `P0` a `P1`…`P4`. La progresión `P0`→`P4` existe (`cuentas.py:71` `CATEGORIAS`) pero hoy la cambia **a mano un administrador** en Gestión > Usuarios; no hay promoción automática por exámenes.

Término: **Perfil normal** = conjunto de límites (ej. alineación ≤10°, toma ≤600 m, fuel ≥20 kg) definido en `profiles.yaml:9`. Hay perfiles *fácil* (aprueba con 60) y *difícil* (80) solo para re-evaluar, la cartilla guarda el normal.

**Quién interviene.** Tú estudiando; opcionalmente un instructor/administrador si tu grupo da formación.

**Para pasar al siguiente paso.** Entender cómo se puntúa y tener el simulador y el grabador listos (siguiente fase).

---

## 5. Reconocimientos, evaluaciones o pruebas

**En el sistema EvA actual:** no hay reconocimiento médico real ni prueba teórica/práctica obligatoria antes del primer vuelo. No se ha encontrado en código ni docs.

- **Evaluación técnica previa:** **información pendiente de confirmar** (si tu aerolínea exige un vuelo de chequeo con instructor, no está en este repositorio).
- **Prueba del sistema:** tu primer vuelo subido **será evaluado** igual que todos (misma nota y mismos fallos graves). No hay vuelo “de prueba sin nota”.

**Para pasar al siguiente paso.** No se exige prueba previa en el código; puedes ir directo a autorizaciones y preparación del vuelo.

---

## 6. Autorizaciones necesarias antes de volar

**Qué debe estar en verde:**

- Cuenta **activa** (no bloqueada). Si estás bloqueado, ni la web ni el grabador te dejan entrar (`cuentas.py:445` `esta_activa`, `web/app.py:183`).
- Rol con permiso `volar` (todos los pilotos lo tienen; `cuentas.py:62`).
- **VATSIM:** si vas a volar en red VATSIM, necesitas tu **CID de VATSIM** (cuenta VATSIM propia) y el cliente **vPilot** aparte. EvA no te da esa cuenta ni te conecta a VATSIM; solo lee tu CID si lo pusiste. Si vuelas offline, no hace falta.
- **Categoría P0** vale para volar; categorías superiores no bloquean vuelos hoy.

**Quién autoriza.** El sistema (estado activa) + el administrador que te dio el alta. No hay “jefe de operaciones” que firme un despacho en el código; **información pendiente de confirmar** si tu organización añade ese visado.

**Para pasar al siguiente paso.** Poder iniciar sesión y ver el menú **PLAN** y **VUELO**.

---

## 7. Preparación del primer vuelo

Hazlo en este orden (`docs/manual_piloto.md:51`, `docs/resumen_inicio.md:42`):

1. **Instalar EvA Airliner** (solo Windows 10/11). Descarga en la web **Descargar Airliner** (`/descargar`) o `https://github.com/ingaigormail/eva/releases/latest/download/setup.exe` (`web/app.py` `DESCARGA_URL`). Se crea la carpeta de **Grabaciones** donde quedará el fichero.
2. **Requisitos del simulador:** MSFS 2020/2024 o Prepar3D con **SimConnect** instalado (el del simulador, no lo instala EvA). X-Plane aún **no graba vuelos evaluables completos** (`manual_piloto.md:20`).
3. **En la web, ve a PLAN** (`/plan`): rellena origen, destino, aeronave, nivel y ruta.
4. **Paso obligatorio para que el vuelo se evalúe:** usa **uno** de estos dos botones (sin esto el vuelo no se evalúa, `resumen_inicio.md:48`):
   - **GENERAR PLAN ICAO** → copia el texto para “Import ICAO FPL” en VATSIM.
   - **ABRIR EN VATSIM** → abre el formulario de VATSIM ya relleno; **tú pulsas Enviar** en VATSIM.
   - *GUARDAR PLAN SIN VATSIM* solo guarda el plan en “Planes de vuelo”, no sustituye a los dos anteriores.
5. **Opcional pero útil:** genera la **clave del grabador** en tu perfil si quieres que EvA Airliner lea tu plan desde el servidor sin reescribir origen/destino (`cuentas.py:648` `generar_clave_grabador`).

Términos:
- **Plan ICAO** = formulario estándar de plan de vuelo (origen, destino, ruta, nivel, etc.).
- **VATSIM** = red online donde vuelas con controladores humanos. Presentar el plan allí es “prefile”.

**Para pasar al siguiente paso.** Tener el simulador abierto y el plan presentado en VATSIM (o texto ICAO generado).

---

## 8. Realización del primer vuelo

**Orden correcto:** abre **primero el simulador**, luego **EvA Airliner** (`manual_piloto.md:52`).

**Grabar:**
- **Automático:** al empezar a **rodar** (~2,7 kt) empieza a grabar; a **50 kt** entra en carrera de despegue (`flight_state_machine.py`). Cierra solo tras tomar, salir de pista y parar ~10 s.
- **Manual:** pulsa **GRABAR** al inicio y **FINALIZAR VUELO** al parar en plataforma (`gui.py`).

Mientras vuelas, evita lo que suspende directo: tiempo acelerado >1×, alabeos >60°, avisos de pérdida/sobrevelocidad, y tomas >600 fpm. Y cuida lo que resta: alineación ≤10°, toma en los primeros 600 m, estable a 500 ft, beacon/nav ON en vuelo, taxi ON rodando y strobe OFF rodando, etc. (`puntuacion_resumen_vuelo.md:18`).

Al terminar, en **Grabaciones** queda un **`.avlog.json`** (y a veces un `.csv` que hoy no se evalúa). No se sube solo: tú eliges cuándo.

**Para pasar al siguiente paso.** Tener el `.avlog.json` cerrado (botón Finalizar vuelo pulsado o parada detectada).

---

## 9. Qué debe ocurrir después del primer vuelo

1. **Subir el vuelo:** en la web **REGISTRO** (`/registro`) sube el `.avlog.json`. Ver tus vuelos es otra pantalla: **VUELOS** (`/vuelos`) (`resumen_inicio.md:65`).
2. **Ver la evaluación:** abre **VUELO > detalle** (`/vuelo/<nombre>`, `web/app.py:1341`). Verás nota 0–100, desglose regla por regla y veredicto **APTO / NO APTO / NO EVALUABLE**. El detalle exige tu sesión; un piloto no ve vuelos ajenos (`es_de`, `web/app.py:1347`).
3. **Corregir y aprender:** si suspendes, la propia página te dice qué regla falló y cuánto restó. Vuelve a volar; cada vuelo genera una nueva entrada. Tu cartilla va sumando.
4. **Seguimiento:** tu actividad aparece en **AEROLÍNEA** (`/aerolinea`) y en **Gestión > Usuarios** para administradores. El vuelo queda también en la tabla `vuelos_resumen` (`cuentas.py:202`) con distancia, duración, combustible, calidad y puntuación.
5. **Si algo salió mal:** un administrador puede borrar/subir un vuelo en tu nombre desde **Gestión > Vuelos** (`web/app.py:997`); tú solo puedes borrar los tuyos.

**Información pendiente de confirmar** fuera del código: si tu aerolínea exige informe al instructor, briefing posterior o validación de horas VATSIM real (hoy el bonus VATSIM del plan económico aún no verifica horas contra VATSIM de forma automática).

---

## Chuleta de una página

| Fase | Tú haces | Necesitas | Quién autoriza | Para avanzar |
|---|---|---|---|---|
| 1 Identificación | Solicitar alta | Callsign, nombre, correo (+CID VATSIM opcional) | — | Solicitud registrada |
| 2 Requisitos | Esperar | Que ID y correo estén libres | Sistema + admin | Solicitud aprobada |
| 3 Trámites | Poner contraseña (24 h) | Correo con enlace | Admin crea cuenta P0 | Cuenta activa |
| 4 Formación | Leer guía de reglas | `guia_practica` + `puntuacion_resumen` | — | Sabes cómo se puntúa |
| 5 Pruebas | (hoy ninguna) | — | — | **Pendiente confirmar** |
| 6 Autorización | Iniciar sesión | Cuenta activa + VATSIM CID si vuelas en red | Sistema | Ves PLAN/VUELO |
| 7 Preparar vuelo | Instalar grabador + plan ICAO/VATSIM | Windows + MSFS/P3D + SimConnect | Tú | Plan presentado |
| 8 Volar | Grabar y finalizar | Simulador primero, luego EvA | — | `.avlog.json` cerrado |
| 9 Después | Subir y revisar | REGISTRO → VUELOS → detalle | Motor `evaluate_flight` | Nota y veredicto visibles |
