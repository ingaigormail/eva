# Llevarse EvA a otra máquina

Escrito el 2026-08-29, con producción en la versión `7d897f6`.

**El código no hay que copiarlo**: está entero en GitHub y todo lo de esta
sesión está subido (`git log origin/main` lo confirma). En la máquina nueva:

```bash
git clone https://github.com/ingaigormail/eva.git D:\proyectos\eva
```

Lo que sí hay que llevarse es **lo que nunca entra al repositorio**, porque
son datos o secretos. Es esta lista y nada más.

---

## 1. Los datos de la web — `web/data/`

Es la carpeta importante. Va entera **menos** `aeronautica.db`.

| Fichero | Qué es | Se puede perder? |
|---|---|---|
| `eva.db` | Cuentas, vuelos, aviones comprados, etapas de la Vuelta | **NO** |
| `secret_key.txt` | Clave de sesión; si cambia, se caen todas las sesiones | **NO** |
| `correo.json` | Credenciales del correo (API de Gmail) | **NO** |
| `importados.json` | Qué vuelos ya se importaron; evita duplicados | **NO** |
| `trusted_log.json` | Auditoría append-only | **NO** |
| `reglas_config.json` | Reglas y economía pisadas en vivo desde `/gestion/reglas` | **NO** (hoy no existe: nadie ha pisado nada) |
| `aeronautica.db` | Espacio aéreo de ENAIRE, 7,7 MB | Sí: se rehace con `web/tools/descargar_enaire.py` |

> **Ojo:** este `eva.db` es el de **desarrollo**. El de verdad, con los pilotos
> reales, vive en el servidor (`/home/eva/eva/web/data/eva.db`) y **no se toca
> desde aquí**. Si en la máquina nueva quieres partir de los datos reales,
> baja la última copia de `D:\eva-backups-servidor` en vez de copiar este.

## 2. Los vuelos grabados — `C:\Users\<usuario>\EvA\`

19 ficheros hoy. Dentro va `grabaciones\` (los `.avlog.json`), y también
`eva.config.json` con la configuración del cliente. La cartilla local los lee
de ahí; sin ellos aparece vacía.

## 3. Mi memoria — `C:\Users\<usuario>\.claude\projects\D--proyectos\memory\`

**Esta es la que se olvida y la que más se nota.** Son 76 ficheros con todo lo
aprendido del proyecto entre sesiones: decisiones, trampas de Windows, por qué
EvA se fue de Render, el incidente del historial de git… Sin ella arranco en
frío y vuelvo a preguntar cosas ya resueltas.

Cópiala a la misma ruta relativa en la máquina nueva. Si allí el proyecto
cuelga de otra carpeta, el nombre `D--proyectos` cambia: es la ruta con los
separadores convertidos en guiones.

## 4. Las copias del servidor — `D:\eva-backups-servidor`

Las copias diarias que se bajan del VPS. Van con una **tarea programada de
Windows a las 06:00** que hay que **volver a crear en la máquina nueva**: las
instrucciones están dentro de `despliegue\sync_backups_local.ps1`. Si no se
monta, el servidor se queda sin copias fuera de sí mismo, que es justo lo que
se arregló el 2026-08-24.

## 5. Acceso al servidor — `C:\Users\<usuario>\.ssh\`

La clave SSH de `eva@7c0cdce9-...clouding.host`. Sin ella no se puede
desplegar, y **no se puede volver a entrar por contraseña**: el acceso por
contraseña y el de root están cerrados, y el `sudo` de `eva` está restringido.
Recuperarlo exigiría la consola de emergencia del panel de Clouding.io.

---

## En la máquina nueva, después de copiar

```bash
python -m venv .venv
.venv\Scripts\pip install -e ./client -r ./web/requirements.txt
python -m pytest client/tests web -q
```

Tienen que salir **688 pasan, 2 se saltan**. Las 2 que se saltan piden MSFS.

Para arrancar la web: `python web/app.py` (puerto 5000).

---

## Dónde se quedó el trabajo

Producción va por `7d897f6` y está al día con `origin/main`.

**Hecho en esta sesión:**

- Compra de aviones: los pilotos compran los de su categoría (21.000 a 132.000
  €vAs) y pasan a pagar el 25% de la hora en vez del alquiler entero. El C172
  no se vende: es el avión de entrada.
- Economía real por vuelo (`client/avcars/economia_vuelo.py`): ingreso por
  calidad y bonos menos combustible, tasas, handling y hora de avión.
- Suite en verde: de 7 tests rojos a 0. Al arreglarlos salió un fallo real en
  producción (`detalle_registro.html` llamaba al endpoint `vuelta_espana`, que
  ya no existe: la ficha de un vuelo de la Vuelta daba error 500).
- Las 21 etapas de la Vuelta no estaban en producción; se importaron y ahora
  se siembran solas al arrancar si faltan.
- `set_payload` dejaba de mentir: devolvía «aplicado» aunque no escribiera
  nada, y calculaba el combustible sobre 200 lb fijas que no son de ningún
  avión de la flota.

**Lo que queda pendiente, por orden:**

1. **Cargar el peso en MSFS al pulsar «aplicar al simulador».** Hoy
   `/api/plan/apply-payload` devuelve un 503 honesto: el servidor web no tiene
   forma de hablar con el SimConnect del cliente. El camino existe
   (`se_puede_lanzar_en_local` en `web/app.py`), pero hay que construirlo.
   **Necesita MSFS delante para probarlo**: escribir esto a ciegas es lo que
   dejó `set_payload` como estaba.
2. **Comprobar que el avión lleva de verdad el peso del plan.** Exige que el
   grabador capture el peso en vuelo.
3. **Cobrar por pasajero.** Depende del punto 2: hoy `pasajeros` y `carga_kg`
   valen cero y solo se factura la base por milla, porque el grabador no los
   registra. No se factura un pasaje que nadie ha contado.
4. Borrar `web/templates/vuelta_espana.html`, que quedó huérfana.
