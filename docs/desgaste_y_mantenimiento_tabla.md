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

## Decisión de diseño: flota con matrícula, pero sin exclusiva

Los aviones de la aerolínea tienen matrícula y el piloto elige uno. **Si dos o
tres eligen el mismo a la vez, vuelan todos**: no se reserva en exclusiva y
nadie se queda en tierra esperando.

Que sea físicamente imposible da igual — nadie ve el avión de nadie. Y lo que
se evita es lo primero que hace abandonar una aerolínea virtual: *«quería volar
el sábado y no pude»*.

**El desgaste de los vuelos simultáneos se suma sobre la misma célula.** Tres
pilotos volando una hora el mismo avión le acumulan tres horas. Eso tiene una
propiedad buena: el desgaste sigue al **uso que le da el club**, no al reloj de
pared, así que los aviones populares se gastan antes. Es lo que pasa de verdad,
aunque el mecanismo sea otro.

Se conserva lo único que aporta una flota común: **las consecuencias se
comparten**. Si alguien machaca el C172, la salud de esa célula baja para
todos, y eso hace que a cada uno le importe cómo vuela el resto.

### La flota: ocho células, una por tipo

Matrícula e indicativo son cosas distintas y hoy están confundidas:

| | Qué es | Dónde vive |
|---|---|---|
| `EVA18L` | Indicativo de radio, el «número de vuelo» | vPilot, al conectar a VATSIM |
| `EC-xxx` | Matrícula, lo que va pintado en el avión | Campo *tail number* de MSFS |

No compiten: el piloto vuela como `EVA18L` en la red **y** lleva `EC-EVA`
pintado, igual que en la realidad. El problema actual es que el campo de
matrícula del simulador tiene el indicativo, así que EvA lee uno creyendo leer
el otro.

La flota, decidida el 2026-08-28. Serie `EC-EV·`, con la última letra siguiendo
**el orden de la escalera de habilitaciones**: la A es el avión de entrada y la
H es el reactor. Así la matrícula sola ya te dice dónde está ese avión en la
progresión, y un piloto P1 sabe de un vistazo que la EC-EVE no es para él.

| Matrícula | Tipo | Avión | Nivel |
|---|---|---|---|
| **EC-EVA** | C172 | Cessna 172 Skyhawk | P0 |
| **EC-EVB** | DA62 | Diamond DA62 | P1 |
| **EC-EVC** | BE58 | Beechcraft Baron G58 | P1 |
| **EC-EVD** | C208 | Cessna 208 Caravan | P2 |
| **EC-EVE** | TBM9 | Daher TBM 930 | P2 |
| **EC-EVF** | B350 | Beechcraft King Air 350i | P3 |
| **EC-EVG** | DHC6 | DHC-6 Twin Otter | P3 |
| **EC-EVH** | C25C | Cessna Citation CJ4 | P4 |

`EC-` es el prefijo español y `EV` ata la serie a EvA. Al añadir una segunda
célula de un tipo, seguir por la I: `EC-EVI` sería el segundo C172, y su ficha
dice de qué tipo es.

**Sin comprobar contra el registro real de AESA.** Combinaciones como EC-EVA
son plausibles y podrían pertenecer a un avión que existe de verdad. Para una
aerolínea virtual no tiene consecuencias, pero si algún día se publican en la
web conviene mirarlo antes.

### La matrícula la pone EvA, no el simulador

MSFS reporta lo que el piloto tenga escrito en el campo de matrícula de su
avión. En los 15 vuelos de prueba del 2026-08 decía `EVA18L`, que es el
indicativo del piloto, no una matrícula de flota.

Así que **el avión sale de lo que el piloto eligió en la web** al preparar el
vuelo, y el campo del simulador se ignora. Como mucho, avisar si no coinciden
—igual que el aviso de aeródromo de salida de `client/avcars/ubicacion.py`—,
pero nunca usarlo como fuente.

### Cuántas células

Sin exclusiva, el número ya no decide quién puede volar: **decide el ritmo del
mantenimiento**. Pocas células concentran horas y las revisiones llegan; muchas
las reparten y el desgaste se queda de adorno.

Con una sola célula por tipo y el número de pilotos activos:

| Pilotos activos | Horas/semana | Revisión de 100 h cada… |
|---:|---:|---|
| 2 | ~5 | 5 meses |
| 5 | ~12 | 2 meses |
| 10 | ~24 | 1 mes |
| 20 | ~48 | 2 semanas |

**Empezar con una célula por tipo: ocho aviones.** Con 2 cuentas activas, más
células harían que el mantenimiento no llegara a ocurrir nunca. Añadir una
segunda es una fila; quitarla cuando ya hay pilotos con historial en ella, no.

**Regla para crecer:** segunda célula de un tipo cuando su revisión de 100 h
empiece a caer más a menudo de cada 6 semanas. Pasará primero con el C172,
porque todo el mundo entra por ahí.

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

## Nada inmoviliza, y por eso no hace falta botón de reparar

Con una sola célula por tipo, inmovilizar el C172 dos horas deja **a todo el
club** sin C172. Va contra la decisión de que nadie se quede en tierra, así que
la columna de horas de inmovilización de las tablas originales queda como dato
informativo y no gobierna nada.

El ciclo, sin ningún estado que bloquee:

1. **Cada hora volada aporta su provisión**, cobrada en el vuelo. Automática:
   no hay forma de "no mantener" el avión.
2. **Al llegar a las 100 h**, la revisión se da por pasada —ya está pagada— y
   el desgaste acumulado vuelve a cero.
3. **Un evento de daño lo paga quien lo causa, en el momento**, y ese pago *es*
   la reparación. No queda nada pendiente para nadie.

Así no hay botón de reparar, y sobre todo **no hay gorrones**: si arreglar
beneficiara a todos y lo pagara uno, nadie lo pagaría nunca. Es el problema
clásico de lo común, y habría hundido el sistema en un mes.

La salud de la célula queda entonces como un diente de sierra: baja con las
horas y con los eventos, y sube con cada revisión. Sirve para **verse** —y para
que a cada uno le importe cómo vuela el resto—, no para apagar aviones.

---

## Preguntas abiertas

1. **¿El alquiler ya incluía el mantenimiento?** Las tarifas de 60/140/250/400/900 €/h
   se calibraron como coste total del avión. Si además se cobra la provisión,
   hay que bajarlas un poco o se cobra dos veces. Recomendado bajarlas y dejar
   la provisión visible aparte: si el mantenimiento va escondido en el
   alquiler, el piloto no lo mira y deja de cuidar el avión, que es justo lo
   contrario de lo que se busca.
2. **¿Se avisa si el simulador reporta otra matrícula?** Igual que el aviso de
   aeródromo de salida: avisar sin bloquear, y mirar en un mes cuántas veces
   salta antes de decidir si endurecerlo. Al principio saltará siempre, porque
   hoy todo el mundo lleva su indicativo en ese campo.
3. **¿Se pide al piloto que ponga la matrícula en el simulador?** Es un campo
   que se edita una vez por avión y se queda guardado, así que el coste es
   bajo y a cambio el avión lleva pintado lo que le corresponde. Pero es
   fricción, y hay que decidir si compensa.
