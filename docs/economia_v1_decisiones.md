# Economía EvA V1 — decisiones y cabos sueltos

Estado a 2026-08-25. Documento de trabajo: recoge lo decidido en la sesión de
diseño y lo que queda por cerrar. No hay nada implementado todavía.

Punto de partida: `E:\descargas\aerolinea_virtual_consolidado.md` (documento
consolidado del usuario) más el análisis de esta sesión.

---

## 1. Naturaleza del sistema (importante)

Con las decisiones tomadas, **el dinero tiene un solo trabajo: pagar
reparaciones**. No compra aviones (el desbloqueo va por examen), no alimenta a
ninguna caja (no hay tesorería) y el alquiler propuesto es marginal.

Esto no es una economía cerrada, es un **marcador de cuánto cuida el piloto los
aviones**. Es una V1 legítima y simple, pero conviene tenerlo presente:

- El piloto que vuela limpio acumula saldo sin límite y su cifra no significa nada.
- El piloto que rompe cosas se desangra.
- El objetivo original «gastar los puntos dentro del ecosistema» queda sin cubrir.

Si más adelante se quiere una economía de verdad, hace falta al menos un
sumidero real (alquiler fijo, cuota, o compra de aeronave).

---

## 2. Decisiones cerradas

| Tema | Decisión |
|---|---|
| Caja de la aerolínea | **No existe.** El ingreso se crea por vuelo y va entero al piloto. |
| Factor de calidad | Sale del motor que ya existe (`client/avcars/evaluation/scoring.py`, 26 reglas). El landing rate solo modula dentro de él. NO se construye una tabla de calidad paralela. |
| Desbloqueo de aeronaves | Por examen humano en la escuela + mínimo de vuelos. El dinero no desbloquea nada. |
| Quién examina | La escuela, fuera del sistema. Aprobar sube de categoría (P0→P1…). |
| Mecánica de categorías | Ya existe: `cambiar_categoria()` en `client/avcars/cuentas.py:618`. No hay que construir nada nuevo. |
| Flota | De la aerolínea, compartida (V1). |
| Rutas | Definidas por la aerolínea. |
| Vuelos sin datos suficientes | No mueven economía (ni ingreso ni coste). |
| Vuelos FAIL | 0 ingresos, sin gastos punitivos añadidos. |

---

## 3. Propuestas sobre la mesa (pendientes de aprobación)

### 3.1 Mínimo de vuelos gatea el examen, no el desbloqueo

Recomendación: el sistema marca «listo para examen» cuando se cumple el mínimo;
la escuela examina; aprobar es lo que sube de categoría. Así el sistema nunca
contradice a un humano que ya ha aprobado a alguien.

**Vuelo válido para el contador** (blindaje antifarmeo): solo APTO, ≥30 min,
≥25 NM, origen ≠ destino. Sin esto, veinte circuitos en el aeródromo de casa
cumplen el requisito.

### 3.2 Mapeo de categorías a flota — DECIDIDO 2026-08-27

El usuario delegó la cifra. Queda así:

| Nivel | Desbloquea | Vuelos APTO para poder examinarse |
|---|---|---:|
| P0 | C172 | — (entrada) |
| P1 | DA62, Baron G58 | 4 |
| P2 | C208 Caravan, TBM 930 | 5 |
| P3 | King Air 350i, DHC-6 | 6 |
| P4 | Citation CJ4 | 8 |

**23 vuelos en total**, no los 55 que se habían propuesto antes. Dos razones:

1. **Los exámenes ya aportan el tiempo de calendario.** Cuadrar cuatro
   exámenes con la escuela no es instantáneo. Si además los vuelos consumen
   cuatro meses por sí solos, el total real se va cerca del año. La fricción
   la ponen los exámenes; los vuelos solo garantizan que se llega con oficio.
2. **Solo cuentan los APTO.** 23 válidos no son 23 volados: quien vuela mal
   repite. A 2 vuelos/semana con un 80% de APTO salen ~3 meses de vuelo más
   lo que tarden los exámenes, que encaja con el objetivo inicial de 2-3
   meses sin forzar la cuenta.

El reparto crece porque los saltos no son iguales: a bimotor son 4 vuelos, al
reactor son 8. El escalón mayor pide el bloque mayor.

### 3.3 Alquiler y tarifa — DECIDIDO 2026-08-27

Interpretación: alquiler = 2% × (ingresos − combustible).

| Vuelo | Ingresos | Combustible | Margen | Alquiler 2% | Por hora |
|---|---:|---:|---:|---:|---:|
| C172, 60 NM, 0,6 h | 290 | 42 | 248 | 4,96 | ~8 €/h |
| Caravan, 260 NM, 1,6 h | 1.075 | 510 | 565 | 11,30 | ~7 €/h |
| CJ4, 400 NM, 1,0 h | 1.880 | 1.200 | 680 | 13,60 | ~14 €/h |

Tres problemas:

1. **Demasiado pequeño**: 11€ frente a 140 de tasas y 95 de mantenimiento base
   (3% de los costes del vuelo). No frena nada.
2. **No distingue aviones**: CJ4 14 €/h vs C172 8 €/h. En la realidad la
   diferencia es de 15 a 1. Volar el avión caro no conlleva responsabilidad extra.
3. **Baja cuando el vuelo sale mal**: si el piloto gana poco, paga menos alquiler.
   El coste debería ser independiente del resultado.

**Alternativa recomendada — alquiler fijo por hora y clase:**

| Clase | Aviones | €/hora |
|---|---|---:|
| Ligera pistón | C172 | 60 |
| Bimotor pistón | DA62, Baron G58 | 140 |
| Turbohélice mono | C208, TBM 930 | 250 |
| Turbohélice bimotor | King Air 350i, DHC-6 | 400 |
| Reactor | Citation CJ4 | 900 |

El 2% queda descartado como sumidero. Guardarlo para cuando exista caja de la
aerolínea: como *comisión* sí funciona.

#### Dos cambios que arrastra el alquiler fijo

Con el alquiler fijo, la Caravan del ejemplo pasaba de +330 a **−70** con la
tarifa de 2,0 €/NM del documento consolidado. Así que:

**1. La tarifa sube a 6 €/NM, igual para todas las clases.** La tarifa única
es deliberada: si el avión grande cobra más por milla *y además* recorre más
millas por hora, se le está pagando dos veces lo mismo. La diferencia entre
aeronaves la hacen los costes (combustible, tasas, alquiler), no el ingreso.

**2. Desaparece la base fija por ruta (`B`).** Con una base plana, un salto de
20 NM cobraba la misma base que uno de 300 y farmear vuelos cortos salía a
cuenta. La fórmula queda:

    ingreso = 6 €/NM × distancia_nm × (1 + 0,6·P + 0,8·C) × calidad

#### Comprobación

| Vuelo | Ingreso | Costes | Neto | €/hora | Margen |
|---|---:|---:|---:|---:|---:|
| C172, 60 NM, 0,6 h | 580 | 166 | +414 | 690 | 71% |
| Caravan, 260 NM, 1,6 h | 2.122 | 1.145 | +977 | 611 | 46% |
| CJ4, 400 NM, 0,9 h | 3.360 | 2.390 | +970 | 1.078 | 29% |

La diferencia por hora entre la avioneta y el reactor baja de **9:1 a 1,6:1**:
volar un C172 vuelve a tener sentido, que era el objetivo.

Y sale una propiedad buena que no se buscaba: **el avión pequeño tiene margen
gordo y cifra pequeña; el jet, margen fino y cifra grande.** Ese 29% del CJ4
significa que un NO APTO (que reduce el ingreso a la mitad) lo deja en números
rojos. Es justo el incentivo que se quería para que se cuiden los aviones caros.

El salto de 20 NM sigue siendo rentable pero flojo (~370 €/h con handling fijo),
por debajo de un vuelo en condiciones. No hace falta prohibirlo: no compensa.

**Todos estos números son de partida, no definitivos.** Hay que recalibrarlos
tras 30-50 vuelos reales.

---

### 3.4 Saldo negativo y visibilidad — DECIDIDO 2026-08-27

**Un piloto en números rojos sigue volando.** No se le bloquea. Se avisa al
responsable.

**Cada piloto ve su saldo.**

Derivadas, resueltas con el criterio más razonable:

- **El aviso se manda al cruzar a negativo, una vez**, y otro al recuperarse.
  Avisar en cada vuelo con saldo negativo haría que el responsable dejara de
  leer los avisos en una semana. Además, marca visible en `/gestion/usuarios`
  para que no dependa de que llegue un correo.
- **Cada piloto ve solo el suyo**; el responsable, todos. Sin tabla pública de
  saldos: sigue la línea de `dueno_del_vuelo()` / `es_de()` que ya usa el resto
  del sitio.

**Estar en rojo ya tiene consecuencia sin regla nueva.** Como el dinero solo
sirve para pagar el taller, un piloto en negativo no puede reparar: su avión se
degrada y la degradación sí afecta a la puntuación. No hace falta prohibirle
volar.

---

## 4. Abierto

Nada bloqueante. Con la sección 3 cerrada se puede escribir la tabla completa de
costes por avión (consumo por tipo, tasas por categoría de aeródromo,
mantenimiento base) y empezar a implementar.

Lo que queda es calibración, y no se puede hacer sin datos: los números de 3.3
son de partida y hay que revisarlos tras 30-50 vuelos reales.

---

## 5. Fallos detectados en el documento consolidado (para no repetirlos)

- El alquiler figuraba como decisión cerrada pero **no aparecía en ninguna
  fórmula** de costes.
- Quién paga el taller estaba «abierto» y a la vez decidido al 100% al piloto
  por la fórmula `beneficio_neto = ingresos − costes − reparación`.
- `pago_piloto = beneficio_neto × f_calidad` implica que la aerolínea no acumula
  nada → resuelto: no hay caja.
- El aterrizaje duro se castigaba dos veces (resta de reparación + multiplicador)
  sobre un margen fino: en rutas ajustadas el factor de calidad deja de distinguir.
- La calidad dependía solo del landing rate → un piloto podía entrar en pérdida,
  pasarse de velocidad y usar compresión de tiempo, y cobrar el 100% posando
  a −150 fpm. **Resuelto: la calidad sale del motor.**
- La tabla de landing rate premiaba más −50/−99 fpm (1,05) que −100/−149 (1,03):
  incentiva flotar. Y los factores >1,00 crean dinero de la nada.
- Unidades: el documento usa galones a 6/galón; EvA graba `fuel_used_kg`.
- Flota incompleta: parámetros de mantenimiento solo para 5 aviones. Faltan
  TBM 930, DHC-6 y CJ4 — justo los que fijan el techo de la progresión.
- Las referencias `[cite:NNN]` no llevan a ninguna bibliografía.

## 6. Huecos que siguen sin cubrir

- **Dónde está cada avión** (flota común + rutas fijas). Para V1 vale decir «el
  avión aparece donde haga falta», pero hay que decirlo.
- **Dos pilotos, una matrícula**: ¿reserva de avión? ¿desgaste sumado?
- **Vuelos que se cortan a medias** (caída del simulador en crucero).
- **Saldo inicial** y si se permite negativo.
- **El payload no es una decisión real**: siempre conviene ir al máximo. Hace
  falta demanda por ruta, pista corta o penalización por ir al límite de peso.
- **Indicadores de control**: dinero generado vs gastado, saldo medio, beneficio
  por vuelo, concentración por ruta. No hay ninguno definido.
- **Conexión con lo que ya existe**: `eva.db`, `registrar_avlog`
  (`client/avcars/estadisticas.py:63`), `vuelos_resumen` idempotente. El diseño
  está escrito como si el proyecto empezara de cero.
