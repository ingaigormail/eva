# 📊 Estudio Comparativo: Criterios de Costes y Ganancias de Vuelo en EvA

Este documento analiza la viabilidad, realismo y equilibrio del sistema económico de **EvA** en comparación con los modelos estándar utilizados por otras aerolíneas virtuales (VAs) y simuladores de carrera en el ámbito de la simulación de vuelo.

---

## 1. Contexto y Modelos de Referencia en Simulación

Para evaluar si los criterios de EvA son aceptables y competitivos, los comparamos frente a las tres corrientes principales de economía en la simulación aérea:

1. **Modelo Cosmético (phpVMS / vAMSYS / Iberia Virtual):**
   - El piloto recibe un "salario virtual" por hora (ej. 50 € por hora de simulación), pero es puramente estético. No hay costes, no hay compras reales, ni riesgo de quiebra. El foco es la acumulación de horas.
2. **Modelo de Gestión de Negocio / Sandbox (FSEconomy / OnAir Company):**
   - Economía persistente y cerrada. Los ingresos dependen de la oferta/demanda de pasajeros y carga real. Hay costes de combustible variables, tasas de aterrizaje y tarifas de alquiler ("wet" o "dry") por hora.
3. **Modelo de Carrera Individual (A Pilot's Life / flyLAT):**
   - El piloto firma contratos con aerolíneas virtuales, gana un salario, paga licencias y compra/alquila aviones personales.

---

## 2. Tabla Comparativa de Criterios Económicos

| Criterio / Parámetro | phpVMS / vAMSYS (Típico) | FSEconomy / OnAir | **EvA (Modelo Actual)** |
| :--- | :--- | :--- | :--- |
| **Ingresos** | Salario fijo por hora de vuelo. | Pasajero-milla y carga-milla dinámicos. | **Pasajero-milla (2 €vAs/NM) + kilo-milla (0,01 €vAs/kg-NM) + Base (1 €vAs/NM)**, con mínimo facturable de 20 NM. |
| **Costes de Combustible** | Ninguno para el piloto. | Precio real por galón/kilo consumido. | **2,00 €vAs por kilo gastado** (real según simulación). |
| **Coste de Alquiler** | Ninguno. | Tarifa horaria o porcentaje de ingresos. | **Tarifa fija por hora de vuelo por modelo (de 200 a 2200 €vAs)**, solo mientras el avión sea alquilado. |
| **Compra de aeronaves** | No existe. | Compra libre si hay dinero. | **Se compran dentro de la categoría ya habilitada** (21.000 a 132.000 €vAs); el propietario pasa a pagar mantenimiento (25% del alquiler). |
| **Tasas de Aeródromo** | Ninguno. | Tasas fijas por aterrizaje (landing fees). | **Tasas según tamaño del aeródromo (25 a 120 €vAs) + Handling fijo (30 €vAs)**. |
| **Impacto de la Calidad** | Ninguno (o se rechaza el vuelo). | Ninguno (solo penaliza el accidente total). | **APTO (100% cobro), NO APTO (30% cobro), FAIL y no evaluable (0% cobro)**. |
| **Bonificaciones** | Ninguna. | Ninguna. | **VATSIM +10%, ATC real +5%, perfil difícil +5%**, con tope del +20%. |
| **Penalización por Aterrizaje Duro** | Ninguna (o amonestación manual). | Coste de reparación proporcional. | **Inspección fija (taller) + tarifa lineal por cada pie/minuto que exceda los 300 fpm**. |
| **Progresión** | Horas acumuladas. | Compra/Alquiler libre si hay dinero. | **Por examen escolar + número de vuelos APTOS** (el dinero compra aviones, nunca rangos). |

---

## 3. Análisis de Criterios Específicos de EvA

### A. Ingresos: Pasajero-Milla y Kilo-Milla (Aceptable y Realista)
* **Evaluación:** **Muy Aceptable.** Es el sistema que mejor premia el tamaño de la aeronave de forma natural. En lugar de usar multiplicadores artificiales de ingresos para aviones grandes, un Cessna 208 Caravan gana más que un DA62 simplemente porque tiene más asientos (10 vs 7) y más peso útil de carga.
* **Ventaja respecto a FSEconomy:** EvA añade un ingreso base por milla (`base_nm: 1.0`), lo que permite que los vuelos de traslado de flota o en solitario sigan siendo económicamente viables (no se vuela gratis), algo que suele ser un dolor de cabeza en plataformas de economía abierta.

### B. Impacto de la Calidad (Excelente / Factor Diferenciador)
* **Evaluación:** **Excelente.** La mayoría de las aerolíneas virtuales tradicionales ignoran la economía de pilotaje (solo miran si despegaste y aterrizaste). En sistemas de carrera como FSEconomy, si aterrizas a 590 fpm (un impacto durísimo) cobras exactamente lo mismo por el pasaje. 
* **El factor EvA:** Vincular el motor de evaluación al cobro (**NO APTO reduce los ingresos al 30%**) y cobrar reparaciones de taller por tomas superiores a **300 fpm** añade la tensión necesaria para simular la responsabilidad de un piloto real. Un piloto que vuela mal con un avión caro entrará en quiebra rápidamente.

### C. Alquiler Fijo por Hora vs Porcentaje
* **Evaluación:** **Aceptable pero exigente.** EvA cobra tarifas de alquiler por hora muy marcadas (ej. 900 €vAs/h para Caravan, 2200 €vAs/h para el Citation CJ4). 
* **Tensión en Jets:** Esto provoca que los aviones grandes tengan márgenes de ganancia muy finos. Si vuelas el Citation CJ4 de forma impecable (APTO), obtendrás grandes ganancias brutas. Pero un solo vuelo calificado como NO APTO (que reduce los ingresos al 30%) resultará en una pérdida neta devastadora de miles de €vAs debido a la alta tarifa horaria y consumo de combustible. Esto equilibra la flota y evita que los pilotos abandonen las avionetas ligeras de inmediato.

### D. Compra de aeronaves (Salida al superávit)
* **Evaluación:** **Necesaria y bien acotada.** Sin ella, el dinero acumulado no tenía ningún destino salvo pagar averías, y un piloto veterano llegaba a un superávit que no significaba nada.
* **Por qué no rompe la progresión:** solo se compran aviones que el piloto **ya tiene habilitados** por examen. El dinero acelera la posesión, nunca el rango: un P0 con 200.000 €vAs sigue sin poder tocar un Caravan.
* **Por qué el C172 no se vende:** es el avión de entrada. Si se pudiera comprar, el P0 gastaría en el avión que está a punto de dejar atrás justo el dinero que necesita para el siguiente escalón.
* **Amortización:** el precio son 60 horas de alquiler y el propietario paga el 25%, así que la compra se recupera en unas 80 horas de vuelo. Es lento a propósito: comprar debe ser una decisión, no un trámite.

---

## 4. Conclusiones del Estudio

1. **EvA combina lo mejor de ambos mundos:** Toma la sencillez de una aerolínea de club (donde la progresión y los exámenes son gestionados por humanos) y le añade la tensión económica de un simulador de carrera (combustible, alquileres y daños por pilotaje).
2. **Criterios Aceptables y Coherentes:** Los valores de las tarifas de pasajeros (2 €vAs/NM), combustible (2 €vAs/kg) y alquileres están bien calculados para que la Cessna 172 actúe como un "salvavidas" financiero, mientras que los jets grandes actúan como un reto avanzado que exige un pilotaje perfecto.

   *Contraste con números:* un vuelo APTO de 1,5 h y 120 NM en C172 desde y hacia aeródromos pequeños ingresa 840 €vAs con 3 pasajeros y gasta 446 (66 de combustible, 50 de tasas, 30 de handling, 300 de alquiler): **margen del 47%**, que sube al 59% con el avión lleno. Es un colchón cómodo, aunque no tan holgado como sugiere una lectura rápida de las tarifas.
3. **El taller es el gran acierto:** Cobrar una tasa de inspección fija más un variable lineal por fpm por encima de los 300 fpm emula perfectamente el coste de mantenimiento correctivo de la aviación real.
4. **La compra de aviones cierra el circuito:** el dinero deja de ser un marcador sin destino sin llegar a comprar progresión, que sigue en manos de la escuela.

### Recomendaciones a futuro:
- **Calibración:** Mantener bajo observación los vuelos del escalón intermedio (Cessna Caravan / TBM 930) para asegurar que el coste de alquiler (900 y 1100 €vAs respectivamente) no ahogue el margen de beneficio en vuelos con meteorología adversa o desvíos largos.
- **Vigilar la amortización real:** el 25% de mantenimiento y las 60 horas de precio salen de una estimación de 20 h de vuelo al mes. Si el ritmo real de la escuela resulta ser la mitad, comprar un Caravan pasa de tres meses a seis y conviene revisar `compra_aviones` en `economia.yaml`.
- **Salidas al superávit una vez comprada la flota:** un piloto que ya tiene todos los aviones de su categoría vuelve a acumular sin destino. Ahí sí encajarían logros o distintivos comprables.
