# Cómo hacer un vuelo en EvA, paso a paso

Guía rápida y visual para quien nunca ha usado el sistema: qué abrir, en qué
orden, y qué pulsar en cada sitio. Si necesitas el detalle completo de cada
paso (reglas de puntuación, requisitos de alta, etc.), está en
[`manual_piloto.md`](manual_piloto.md) y
[`proceso_piloto_primer_vuelo.md`](proceso_piloto_primer_vuelo.md) — este
documento es solo "qué toco y cuándo".

---

## Orden de un vistazo

| # | Aplicación | Qué haces |
|---|---|---|
| 1 | **Simulador** (MSFS) | Abrirlo y cargar avión + aeropuerto de salida |
| 2 | **EvA Airliner** (el grabador) | Abrirlo y esperar a que se ponga en verde |
| 3 | **vPilot** *(solo si vuelas en VATSIM)* | Abrirlo y conectar con tu CID |
| 4 | **Web de EvA** | Entrar y rellenar el plan en **PLAN** |
| 5 | **Web de EvA** | Pulsar **GENERAR PLAN ICAO** o **ABRIR EN VATSIM** |
| 6 | **VATSIM** *(si usaste ABRIR EN VATSIM)* | Revisar y pulsar Enviar |
| 7 | **Simulador** | Rodar hacia pista — el grabador arranca solo |
| 8 | **EvA Airliner** | Al terminar, comprobar que el vuelo se cerró |
| 9 | **Web de EvA** | Subir el fichero del vuelo en **REGISTRO** |

Si algo de esto no te suena (VATSIM, ICAO, grabador...), seguro que se
explica más abajo, en el paso correspondiente.

---

## Por qué este orden y no otro

**El simulador y el grabador van antes que la web, y no al revés.** Esto es
importante y es nuevo: antes se podía preparar el plan en la web sin tener
nada más abierto. Ahora, al pulsar los botones del plan, la web también le
manda el peso (pasajeros + carga) al simulador — y para que eso llegue,
**EvA Airliner tiene que estar ya abierto y conectado al simulador en ese
momento**. Si pulsas los botones del plan antes de abrir el simulador o el
grabador, verás un aviso de que no se ha podido confirmar el peso: no es un
fallo, es que todavía no hay nadie al otro lado para recogerlo.

---

## 1. Abrir el simulador

Abre MSFS (2020 o 2024) o Prepar3D y carga un vuelo: elige tu avión y el
aeropuerto de salida. Espera a que el avión esté visible y controlable
(no hace falta estar ya en pista, basta con tener el vuelo cargado).

**Listo cuando:** ves el avión en el simulador, en tierra.

---

## 2. Abrir EvA Airliner (el grabador)

Es el programa de escritorio que instalaste desde **Descargar Airliner** en
la web. Ábrelo. En su ventana verás varios indicadores (simulador, vPilot,
piloto...) que se ponen en verde según detecta cada cosa.

**Listo cuando:** el indicador del simulador está en verde — quiere decir
que EvA Airliner ya está hablando con MSFS.

> Si el indicador no se pone verde, comprueba que el simulador ya está
> abierto (paso 1) y que tienes instalado el componente SimConnect del
> propio simulador.

---

## 3. Abrir vPilot (solo si vas a volar en la red VATSIM)

Si vuelas offline, sáltate este paso. Si vuelas en VATSIM, abre vPilot y
conéctate con tu usuario. EvA no te conecta a VATSIM por ti — eso lo hace
vPilot, EvA solo lee tu CID si lo tienes puesto en tus preferencias.

**Listo cuando:** vPilot muestra que estás conectado a la red.

---

## 4. Entrar en la web de EvA y abrir PLAN

Entra en la web con tu usuario y contraseña, y ve a la sección **PLAN**.
Rellena los datos de tu vuelo:

- Origen y destino
- Aeronave
- Ruta, nivel de crucero, velocidad
- Pasajeros y carga (esto es lo que decide el peso del avión)

Al elegir pasajeros y carga verás la barra de peso: te dice en verde,
ámbar o rojo si el avión va dentro de su peso máximo o se pasa.

**Listo cuando:** todos los campos del plan están rellenos y la barra de
peso te dice si vas bien o justo de peso.

---

## 5. Pulsar uno de los tres botones del plan

Hay tres botones, y **los tres hacen dos cosas a la vez**: su acción propia,
y aplicar el peso configurado al simulador (que ya tienes abierto desde el
paso 2).

| Botón | Qué hace además de aplicar el peso |
|---|---|
| **GUARDAR PLAN SIN VATSIM** | Solo guarda el plan en «Planes de vuelo». **No** sirve para que el vuelo se evalúe. |
| **GENERAR PLAN ICAO** | Genera el texto ICAO para pegarlo en VATSIM (formulario "Import ICAO FPL"). |
| **ABRIR EN VATSIM** | Abre el formulario de VATSIM ya relleno con tus datos. |

**Importante:** para que tu vuelo se pueda evaluar al final, tienes que usar
**GENERAR PLAN ICAO** o **ABRIR EN VATSIM** — con solo GUARDAR no basta.

Después de pulsar, espera unos segundos: abajo aparece un mensaje tipo
*"Aplicado: 185 kg de carga/pasajeros"* confirmando que el peso llegó de
verdad al avión en el simulador. Si en vez de eso ves *"No se ha podido
confirmar"*, repasa los pasos 1 y 2 — seguramente el simulador o el
grabador no estaban listos.

**Listo cuando:** ves el mensaje de peso aplicado (o, si vas a volar en
VATSIM, cuando además tengas el texto ICAO o el formulario de VATSIM
abierto).

---

## 6. Enviar el plan en VATSIM (solo si usaste "ABRIR EN VATSIM")

Se abrió el formulario de VATSIM ya relleno. Revísalo y pulsa **Enviar**
tú mismo — EvA no lo manda por su cuenta, solo prepara el formulario.

**Listo cuando:** VATSIM confirma que tu plan de vuelo está presentado.

---

## 7. Empezar a volar

Vuelve al simulador y empieza a rodar hacia la pista.

- **Modo automático** (el normal): el grabador **empieza a grabar solo** en
  cuanto el avión se mueve (rueda) — no hace falta tocar nada en EvA
  Airliner.
- **Modo manual**: si lo tienes activado, pulsa **GRABAR** en EvA Airliner
  antes de empezar a rodar.

**Listo cuando:** en EvA Airliner ves que está grabando.

---

## 8. Terminar el vuelo

Aterriza, sal de la pista y para el avión.

- **Modo automático**: el grabador **cierra el vuelo solo** unos segundos
  después de pararte.
- **Modo manual**: pulsa **FINALIZAR VUELO** en EvA Airliner.

**Listo cuando:** EvA Airliner confirma que el vuelo se ha cerrado. El
fichero queda guardado en tu carpeta de **Grabaciones**.

---

## 9. Subir el vuelo para que se evalúe

En la web, ve a **REGISTRO** y sube el fichero `.avlog.json` que se generó
en el paso anterior. Después, en **VUELOS** puedes abrir el detalle y ver
tu nota y el desglose regla por regla.

**Listo cuando:** el vuelo aparece en tu lista de **VUELOS** con su nota.

---

## Resumen para pegar en la nevera

1. Simulador abierto.
2. EvA Airliner abierto y en verde.
3. (VATSIM) vPilot conectado.
4. Web → PLAN → rellenar todo.
5. Pulsar GENERAR PLAN ICAO o ABRIR EN VATSIM → esperar el "Aplicado".
6. (VATSIM) Enviar el plan.
7. Rodar → graba solo.
8. Parar → se cierra solo.
9. Web → REGISTRO → subir el vuelo.
