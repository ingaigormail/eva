# Espacio aéreo oficial de ENAIRE

Verificado el 2026-08-27. Sustituye a los datos de OpenAIP para todo lo que
sea juzgar un vuelo.

---

## Dónde vive cada cosa

Esto se preguntó y conviene dejarlo escrito, porque no es obvio:

| Fichero | Qué es | ¿En git? | ¿En el servidor? |
|---|---|---|---|
| `web/data/eva.db` | La base de verdad: usuarios, vuelos, planes, y las tablas aeronáuticas `*_es` importadas de OpenAIP | No (ignorado) | **Sí, es la de producción** |
| `data/databases/aerodromos_es.db` | Fichero de trabajo local del que se importó lo anterior | No (`/data/` ignorado) | No |
| `web/data/aeronautica.db` | **Nuevo**: espacio aéreo oficial de ENAIRE | No (ignorado) | Se genera ahí con el script |

Es decir: `data/` nunca viaja. Lo que hay en el servidor son las tablas dentro
de `eva.db`, y ahora además `aeronautica.db` al lado.

**Por qué en una base aparte y no dentro de `eva.db`:** `eva.db` lleva cuentas
y vuelos, y se copia todos los días. El espacio aéreo son 7 MB que se rehacen
enteros cada 28 días y se pueden volver a descargar en un minuto: meterlos ahí
hincharía cada copia de seguridad con algo que no hay que salvar. Además, una
importación que salga mal no puede tocar las cuentas si vive en otro fichero.

---

## El servicio

Detrás de [Insignia VFR](https://insigniavfr.enaire.es) hay servicios ArcGIS
REST **públicos y sin autenticación**:

```
https://servais.enaire.es/insigniads/rest/services/INSIGNIA_SRV/Aero_SRV_VIGOR_data_V4/FeatureServer
https://servais.enaire.es/insigniads/rest/services/INSIGNIA_SRV/Aero_SRV_AIRAC_data_V3/FeatureServer
```

`VIGOR` es lo que está en vigor ahora — contra lo que hay que juzgar un vuelo
ya volado. `AIRAC` es lo publicado pero aún sin entrar en vigor.

Devuelven GeoJSON (`f=geojson`), admiten `outSR=4326` para que la geometría
llegue en latitud/longitud, y topan en 10.000 registros por consulta. También
exportan a `shapefile, csv, filegdb, sqlite`.

### Condiciones de uso

Del documento de servicios AIS de ENAIRE:

> Puede acceder y utilizar los servicios de datos AIS [...] siempre que se
> indique expresamente que ENAIRE es el titular de los derechos de propiedad
> intelectual e industrial [...] y que su utilización **nunca sea para uso
> operacional**.

Dos obligaciones. EvA cumple las dos: es un simulador (no operacional), y hay
que **poner la atribución a ENAIRE por escrito en la web**. Eso último está
pendiente. Dudas: `ais@enaire.es`.

---

## Qué se descarga

`python web/tools/descargar_enaire.py` deja 11 capas, 1.576 elementos, 7,3 MB:

| Capa | Filas | Para qué |
|---|---:|---|
| CTR | 48 | Zonas de control |
| ATZ_FIZ | 56 | Tránsito de aeródromo |
| TMA_CTA | 66 | **La capa de TMA que faltaba** |
| SECTORES_VFR | 187 | **El techo VFR** (ver abajo) |
| D_P_R | 225 | Peligrosas, prohibidas, restringidas |
| PROHIBIDO_VFR | 5 | Donde el VFR está prohibido |
| NO_SOBREVUELO | 8 | Prohibido sobrevolar |
| RMZ | 28 | Radio obligatoria |
| TMZ | 20 | Transpondedor obligatorio |
| PUNTO_VFR | 390 | Puntos de notificación oficiales |
| RUTAS_VFR | 543 | Rutas VFR publicadas |

Se relanza en cada ciclo AIRAC. La descarga se escribe en un fichero aparte y
solo se pone en su sitio al terminar: una descarga a medias que dejara media
España sin espacio aéreo sería peor que no tener nada, porque las reglas darían
por bueno un vuelo que cruzó una zona que resulta que no se descargó.

---

## Lo que resuelve frente a OpenAIP

**Los límites verticales vienen en número, y con su referencia.** Donde OpenAIP
daba `"2000 ft"` sin decir si era sobre el mar o sobre el terreno, aquí hay tres
columnas: valor, unidad y código de referencia. Los códigos que aparecen:

| Código | Filas | Significado |
|---|---:|---|
| STD | 368 | Nivel de vuelo |
| HEIS | 176 | Sobre el nivel del mar |
| HEIG | 169 | Sobre el terreno |
| ALT | 83 | Altitud |
| HEI | 33 | Altura |
| HEISG | 19 | Mixto |
| OTHER | 5 | Otro |

**Lleva ciclo AIRAC.** `LASTMOD_AMDT` trae la enmienda (`"AIRAC - 04/20"`) y
`LASTMOD_DATE` la fecha. Se puede decir con qué versión se juzgó un vuelo, que
es lo que convierte una regla en defendible.

**Es fuente oficial.** No es un detalle legal: es la diferencia entre poder
decirle a un piloto "entraste en la P de Torrejón" y que la respuesta correcta
no sea "según quién".

---

## Trampas encontradas

**`VFRMAXALT` es texto, no número.** Viene como `"4500ft AMSL"`, con la
referencia dentro. Convertirlo a número al importar pierde la mitad del dato,
y además hace que parezca vacío. Se guarda tal cual.

**Solo la capa SECTORES_VFR trae `VFRMAXALT`**, y en 168 de sus 187 filas
(90%). Ninguna otra capa lo tiene. O sea: **el techo VFR sale de los sectores**,
como ya se sabía, y con buena cobertura.

**Los sectores VFR no tienen nombre útil.** `IDENT_TXT` y `NAME_TXT` valen
literalmente `" (SECTOR VFR)"` en todos. Sirven para el cálculo (geometría y
límites están bien) pero no para decirle al piloto en qué sector estaba. Si
hace falta nombrarlo, habrá que cruzarlo con `TMA_CTA` por geometría.

**Los puntos VFR no traen altitud.** Los 390 tienen `LOWER_VAL`/`UPPER_VAL`
a nulo. La altitud máxima por punto de notificación no está aquí — mismo hueco
que en OpenAIP, donde solo la tenía el 9%.

**Hay menos puntos VFR que en OpenAIP**: 390 oficiales frente a 1.104. OpenAIP
incluye puntos que no están publicados en el AIP. Para juzgar, los buenos son
los 390.

**El TLS puede fallar en máquinas con antivirus.** Da
`CERTIFICATE_VERIFY_FAILED` porque el antivirus inyecta su propia CA. El script
usa `truststore` si está disponible, que lee el almacén del sistema. En un
servidor limpio no hace falta.

---

## Siguiente paso

Con esto, el orden que tenía sentido antes ya no depende de conseguir datos:

1. **Regla de zonas** (D_P_R + PROHIBIDO_VFR + NO_SOBREVUELO) con permanencia
   mínima y margen horizontal, para no dar falsos positivos por deriva.
2. **Techo VFR** con SECTORES_VFR.
3. **Desviación de ruta**, cuando existan las rutas definidas por la aerolínea
   (ver `docs/economia_v1_decisiones.md`): RUTAS_VFR y PUNTO_VFR dan el
   esqueleto oficial.

Recordar la limitación de muestreo: en crucero la traza guarda un punto cada
10 s, así que la validación de zonas es orientativa, no probatoria. Decisión
tomada el 2026-08-27 de dejarlo así (ver `docs/analisis_ant_tracker_v2.md`).
