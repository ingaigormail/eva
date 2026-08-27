# Análisis del cliente de FlyAnt (Ant Tracker v2)

Analizado el 2026-08-27 sobre la instalación local en
`%LOCALAPPDATA%\Programs\flyant-tracker`. La app es Electron y su `app.asar`
incluye el **código TypeScript sin ofuscar** del motor, en el paquete propio
`fsim-api`.

Se ha leído para entender el planteamiento, no para trasplantar código. Las
ideas de diseño son de dominio común; su implementación es suya.

---

## Arquitectura

Tres capas dentro de `fsim-api`:

- `simulators/` — un adaptador por simulador (`fsx.ts` cubre FSX/P3D/MSFS vía
  FSUIPC, `xpl.ts` cubre X-Plane vía datarefs UDP).
- `datapoints/` — cada variable declara *las dos formas* de leerse.
- `phases/` — cada regla es un módulo con `execute(data, oldData)` que devuelve
  una lista de eventos.

Un datapoint típico:

```ts
export const vs: IDataPoint = {
  name: "vs",
  dataref: "sim/flightmodel/position/vh_ind_fpm",   // X-Plane
  offset: { name: "vs", hex: 0x2c8, type: 3 },       // FSUIPC
  convertFsx(data) { return Math.floor((data * 60 * 3.28084) / 256); }
};
```

**Usan FSUIPC, no SimConnect.** Un solo código para MSFS 2020/2024, FSX, P3D y
X-Plane, a cambio de que el piloto instale FSUIPC7 por su cuenta. EvA va directa
a SimConnect: menos fricción para el piloto, más trabajo por simulador.

### Dos ritmos distintos

- **30 Hz** (`setInterval(..., 33)`) para detectar eventos.
- **~1,2 Hz** para emitir posición (solo cada 25 muestras, `dataCounter > 24`).

Separan el flujo de eventos del flujo de traza. EvA captura a 1 Hz y escribe a
1 Hz cerca del suelo / 0,1 Hz en crucero: el mismo ritmo para las dos cosas.

---

## Lo que merece copiarse

### 1. La configuración de reglas la sirve el servidor

En código antiguo que dejaron comentado en `dist/events.js`:

```js
axios.post(`${baseUri}/api/aircraft/config`, body, {headers})
     .then((config) => client.connect(sim, config.data, departureCoords, departure, language))
```

El cliente pide al servidor la configuración de *ese* avión antes de conectar.
**Pueden cambiar umbrales y puntos sin publicar versión nueva del cliente.**

**Corregido el 2026-08-27:** EvA ya resuelve esto por otra vía, mejor. La
puntuación **no corre en el cliente sino en el servidor** (`web/app.py:53`
importa `evaluate_flight` y puntúa al importar el vuelo), y las reglas se
ajustan en caliente con `reglas_config.cargar_overrides()` desde
`/gestion/reglas`, sin desplegar. Ventaja añadida: el piloto nunca tiene el
baremo, así que no puede manipularlo.

Lo que sí queda empaquetado en el cliente:

- **La lista de la flota** (`client/config/aircraft.yaml`). Si se añade un avión,
  los pilotos con el cliente viejo no lo ven hasta reinstalar. Es la única
  molestia real.
- **Los parámetros del grabador** (ritmos de muestreo, ventanas de confirmación),
  entre `timing.py` y el `eva.config.json` local de cada piloto. No se pueden
  cambiar centralmente, pero se tocan muy de tarde en tarde.

Solución si se quiere: un `GET /api/config-cliente` sobre la tubería que ya
existe (`plan_web.py` ya lee el plan de la web con clave de solo lectura), con
caché y **respaldo obligatorio a lo empaquetado** si el servidor no responde —
un fallo de red no puede dejar a un piloto sin poder grabar. Media tarde de
trabajo. Recomendado hacerlo solo para la flota.

### 2. Tres candados antes de permitir grabar

En `fsim-api/src/index.ts:114-146`, al conectar:

| Comprobación | Mensaje |
|---|---|
| `gs > 0` | "Can't load the cargo if you are moving!" |
| `lat/lon ≈ 0,0` | "You can't connect while in the game menu" |
| Distancia haversine al aeropuerto de salida **> 15 km** | "Are you sure you are at the right airport?" |

El tercero es antifraude barato y eficaz, y EvA no lo tiene. Revela además la
arquitectura: `connect` recibe `booking: { departureCoords, departure }`, o sea
**no se puede grabar un vuelo que no se haya reservado antes**. Encaja con la
idea de rutas preestablecidas. Escape: si el ICAO es `ZZZZ` se salta la
comprobación.

### 3. Los puntos viven en la configuración

Plantilla en `fsim-api/src/_config.json`:

```json
"landingRateThresholds": [
  { "msg": "Too soft", "val": 50,    "points": -5  },
  { "msg": "Perfect",  "val": 150,   "points": 25  },
  { "msg": "Hard",     "val": 250,   "points": -5  },
  { "msg": "...",      "val": 99999, "points": -50 }
]
```

Se recorre hasta el primer umbral que supera al valor absoluto de la VS. EvA ya
está a la par con `profiles.yaml`; lo que falta es que lo sirva el servidor.

Las infracciones de luces valen -5 cada una.

### 4. Rebote y antirrepetición

- Un evento no se repite si han pasado < 5 s (salvo los marcados `stackable`).
- Un aterrizaje dentro de los 2 s siguientes a otro se ignora.
- Un aterrizaje entre 2 s y 10 s después de otro se marca **`bounced`**.

EvA no detecta rebotes, y es de lo que más delata un mal aterrizaje.

### 5. Luces con histéresis

Luz de aterrizaje: penaliza encendida por encima de **11.000 ft** y apagada por
debajo de **9.000 ft**. La banda de 2.000 ft evita castigar a quien la conmuta un
poco antes o después. Detalle pequeño que evita muchas reclamaciones.

---

## Lo que NO hay que copiar

### El cálculo del régimen de toma es un apaño

`fsim-api/src/phases/landing.ts:26`:

```ts
const vs = heights[last] == heights[last-1]
  ? data.vs
  : ((heights[last] - heights[last-1]) / 66) * (60000 * 0.8);
```

Derivan la VS de la diferencia de altura entre dos muestras en vez de leer la
del simulador, y la multiplican por **0,8**. Ese factor es empírico y sin
justificar: **el régimen de toma que publican es un 20% más suave que el que
sale de la cuenta**. Quien toca a 500 fpm reales aparece con 400.

### `vs > 0` en el contacto se marca como accidente

Si el avión toca con velocidad vertical positiva (rebote, o terreno subiendo
bajo el avión) reportan `crashed` con valor 99999. Demasiado brusco.

### El `.env` cifrado con dotenvx dentro del asar

Es ofuscación, no seguridad: la clave tiene que estar al alcance de la app para
que arranque. No montar secretos del servidor sobre ese patrón.

### Detalle menor

La plantilla `_config.json` lleva una cadena de broma sin quitar
(`"Sa matao paco"` como mensaje del peor umbral de aterrizaje). Va dentro del
paquete distribuido.

---

## Corrección a un análisis anterior

El `SESSION_CONTEXT.md` del otro equipo apuntaba que Ant Tracker guarda el token
de sesión en claro en logs y `config.json`. **En la v2 ya no**: el logger declara
`privateKeys: [StoreKeys.Token, StoreKeys.LoginToken]` y los redacta. Ese
hallazgo era de la alpha y está corregido.

---

## El hueco que esto destapa en EvA

EvA captura a 1 Hz; ellos a 30 Hz. Para casi todo da igual, **pero no para medir
el régimen de toma**. El instante del contacto dura milisegundos: con una muestra
por segundo puedes coger el avión 300 ms antes de tocar, cuando la VS ya no es la
del impacto. Su método es feo, pero el problema que intentan resolver lo tiene
EvA igual.

No hace falta subir todo a 30 Hz. Lo razonable es **desacoplar los dos ritmos**:
muestreo rápido solo para fijar el instante de eventos concretos (toma, rebote,
pérdida) y el ritmo actual para la traza que se guarda.

Decisión tomada el 2026-08-27: **el muestreo de la traza se deja como está**
(1 Hz por debajo de 1.500 ft AGL, 1/10 s por encima). Lo del ritmo doble queda
como mejora pendiente, no como bloqueante.

---

## Pendientes que salen de aquí

1. **Candado de distancia al aeropuerto de salida** al empezar a grabar.
2. **Detección de rebote** (segundo contacto dentro de una ventana corta).
3. **Histéresis en las reglas de luces**, si no la tienen ya.
4. **Servir la lista de la flota desde el servidor**, para que añadir un avión no
   obligue a los pilotos a reinstalar. Comodidad, no arquitectura: la evaluación
   ya vive en el servidor.
5. **Muestreo rápido en el instante de la toma**, para medir la VS de contacto
   con precisión. Aparcado por decisión del 2026-08-27.
