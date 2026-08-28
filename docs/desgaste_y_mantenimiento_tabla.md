# Desgaste y mantenimiento: tabla propuesta

Estado: **propuesta para revisar**, nada implementado. 2026-08-28.

Parte de las cuatro tablas que aportó el usuario
(`maintenance_parameters_5_aircraft.csv`, `operational_checks_damage_table_5_aircraft.*`,
`aircraft_list.csv`) con tres correcciones y una decisión de diseño.

---

## Qué se ha corregido de las tablas originales

### 1. La columna de sistemas afectados estaba generada, no mapeada

En el original, «Hard landing inspection» del C172 afectaba a **lights**, y el
resto de aviones a **tires**. Un aterrizaje duro daña tren, ruedas, frenos y
estructura; nunca las luces. Mirando las cinco filas de cada avión se ve que la
columna rota por una lista de sistemas en vez de describir nada:

    C172   oil → tires → brakes → lights → prop
    C208   prop → engine → brakes → tires → landing gear
    DA62   engines → propellers → brakes → tires → electrics

Si eso se conecta, EvA le dice a un piloto *«tu aterrizaje duro ha dañado las
luces»*, y pierde la credibilidad del sistema entero en un mensaje. Rehecha a
mano abajo.

### 2. Faltaban tres de los ocho aviones

Las tablas cubren C172, C208, DA62, Baron 58 y King Air 350. Faltaban el
**TBM 930, el Twin Otter y el CJ4** — que son los tres más caros, y el CJ4 es
la cima de la progresión P0→P4. Añadidos por extrapolación y **marcados como no
verificados**.

Además `aircraft_list.csv` incluía un C152 y un PA-28 que no están en la flota.

### 3. Había dos modelos de coste que no se hablaban

Coexistían una tabla de eventos con coste fijo y una fórmula continua de daño.
Para un C172 tocando a −600 fpm daban tres cifras distintas: 220 (tabla), 45
(lineal) y 360 (cuadrática). Se elige **uno solo**, abajo.

---

## Decisión de diseño: provisión por hora, no factura de golpe

Las revisiones de 50 h y 100 h son un coste por **horas acumuladas del avión**,
no por vuelo. Con una flota compartida y sin caja de aerolínea, la pregunta era
quién paga los 700 € de la revisión del King Air.

**Cada hora volada aparta su parte:**

    provision_por_hora = coste_100h / 100 + 2 × coste_50h / 100

El piloto la paga en cada vuelo, proporcional a lo que voló. Cuando la revisión
toca, ya está pagada.

Es exactamente justo (pagas tus horas y solo las tuyas), no hace falta saber
quién voló las 99 anteriores, y no necesita caja: el dinero desaparece, que es
lo que se decidió para la economía V1.

**Entonces el contador de horas por matrícula sirve para lo que importa de
verdad: saber cuándo inmovilizar el avión**, no para repartir la factura.

La provisión sale entre el 3 % y el 9 % del alquiler por hora. Se nota sin
dominar el coste del vuelo.

---

## Tabla 1 — Mantenimiento programado

| Avión | 100 h | 50 h | **Provisión €/h** | Inmovilización 100 h | Verificado |
|---|---:|---:|---:|---:|:--:|
| C172 | 320 | 120 | **5,60** | 2,0 h | sí |
| DA62 | 430 | 160 | **7,50** | 2,5 h | sí |
| BE58 | 480 | 190 | **8,60** | 2,5 h | sí |
| C208 | 520 | 180 | **8,80** | 3,0 h | sí |
| TBM9 | 600 | 210 | **10,20** | 3,0 h | **no** |
| DHC6 | 650 | 240 | **11,30** | 3,0 h | **no** |
| B350 | 700 | 260 | **12,20** | 3,0 h | sí |
| C25C | 900 | 320 | **15,40** | 4,0 h | **no** |

Los tres «no» son extrapolación, no fuente. El criterio: un turbohélice
monomotor presurizado (TBM) va por encima del Caravan; un bimotor turbohélice
rústico (Twin Otter) por debajo del King Air; y un reactor por encima de todo.
Marcar y no disimular, igual que se hizo con los pesos del DHC-6.

---

## Tabla 2 — Daño por evento

Sistemas rehechos. Un evento cuesta **la inspección fija más el daño lineal**.

| Evento | Sistemas que toca de verdad | ¿Puede EvA detectarlo hoy? |
|---|---|---|
| Aterrizaje duro | Tren, ruedas, frenos, estructura | **Sí** — `landing_vs` del motor |
| Sobrevelocidad estructural | Estructura, mandos | **Sí** — `structural_overspeed` |
| Entrada en pérdida | Motor, célula | **Sí** — `stall_warning` |
| Golpe de hélice | Hélice, eje, reductora | **No** |
| Exceso de motor | Motor, turbina | **No** |

Las dos últimas quedan fuera de la V1: no se puede cobrar por algo que no se
mide.

| Avión | Inspección aterrizaje duro | Daño lineal €/fpm sobre 300 |
|---|---:|---:|
| C172 | 220 | 0,15 |
| DA62 | 280 | 0,35 |
| BE58 | 320 | 0,45 |
| C208 | 320 | 0,30 |
| TBM9 | 350 | 0,40 |
| DHC6 | 380 | 0,50 |
| B350 | 420 | 0,60 |
| C25C | 500 | 0,75 |

### Por qué lineal y no cuadrática

    coste = inspeccion_fija + max(0, |fpm| − 300) × factor_lineal

La cuadrática daba 360 € a un C172 por una toma a −600 fpm: más que la propia
inspección (220) y casi el beneficio entero del vuelo (414). Demasiado para una
primera vez.

Con la lineal, esa misma toma cuesta **220 + 45 = 265 €**, un 64 % del
beneficio del vuelo. Duele y se recuerda, pero no arruina.

Y la crítica obvia a la lineal —que se aplana en lo extremo— aquí no aplica:
**por encima de 600 fpm el motor ya declara FAIL y el ingreso del vuelo es
cero**. El castigo del extremo lo pone la puntuación, no el taller. Los dos
sistemas se reparten el trabajo en vez de duplicarlo.

### El umbral coincide con lo que ya hay

Los 300 fpm de las tablas del usuario son exactamente el techo de la banda
`normal` de `profiles.yaml` (`butter` 60, `smooth` 180, `normal` 300, `hard`
600). El daño empieza justo donde el motor ya dice «hard». Dos diseños hechos
por separado que coinciden: no tocar.

---

## Coste por vuelo, independiente de las horas

| Avión | Preflight/turnaround |
|---|---:|
| C172 | 35 |
| DA62 | 50 |
| C208 | 55 |
| BE58 | 60 |
| TBM9 | 75 |
| DHC6 | 80 |
| B350 | 90 |
| C25C | 120 |

---

## Lo que falta en la base de datos

`vuelos_resumen` ya tiene `matricula` y `duracion_min`, así que **las horas por
avión se pueden llevar hoy mismo**.

Lo que **no** está: el régimen de toma en fpm. La columna `incidencias` guarda
solo los nombres de las reglas falladas, no sus valores, así que para cobrar el
daño hay que añadir una columna (`toma_fpm`) o releer el fichero del vuelo. Lo
primero es mejor: al importar ya se tiene el veredicto delante.

---

## Preguntas abiertas

1. **¿El alquiler ya incluía el mantenimiento?** Las tarifas de 60/140/250/400/900 €/h
   se calibraron como coste total del avión. Si además se cobra la provisión,
   hay que bajarlas un poco o se cobra dos veces. Recomendado bajarlas y dejar
   la provisión visible aparte: si el mantenimiento va escondido en el
   alquiler, el piloto no lo mira y deja de cuidar el avión, que es justo lo
   contrario de lo que se busca.
2. **¿Quién pasa la revisión cuando toca?** ¿Un botón que alguien pulsa, o el
   avión vuelve solo al servicio cuando pasan las horas de inmovilización?
3. **¿Qué pasa si nadie repara un avión?** Se queda en tierra indefinidamente,
   y con flota compartida eso afecta a todos.
