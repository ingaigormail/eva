# Guía práctica de las reglas de puntuación (EvA)

Esta guía explica, en lenguaje cotidiano, **qué mira cada regla** y **cuándo se cumple o no**. Los números y criterios salen del perfil **normal** (`client/config/profiles.yaml`), que es el que usa la cartilla al guardar la nota. No se inventan umbrales: si el código no define aprobado o suspenso para una regla, se dice aquí con claridad.

Fuente: motor `client/avcars/evaluation/scoring.py`, umbrales `client/config/profiles.yaml`, fichas `client/avcars/evaluation/reglas_info.py`, calidad de datos `client/avcars/evaluation/data_quality.py`.

---

## Cómo se puntúa un vuelo (visión general)

El vuelo **empieza con 100 puntos**. Cada regla que no se cumple **resta** una cantidad fija (salvo las que solo marcan suspenso directo y restan 0).

El vuelo **aprueba** solo si se cumplen **las tres** condiciones a la vez:

1. La nota final es **70 o más**.
2. No hay ningún **fallo grave** (lista más abajo).
3. Los datos del fichero **sirven para evaluar** (no es un log vacío o “congelado”).

Si falta cualquiera de las tres, el vuelo **no aprueba**, aunque la nota numérica sea alta.

**Fallos graves** (el vuelo entero queda suspenso, da igual la nota):

- Toma muy dura (`landing_vs` en banda *very_hard*).
- Se aceleró el tiempo del simulador por encima de velocidad real.
- Alabeo por encima del límite duro.
- Aviso de pérdida (stall) del simulador.
- Aviso de sobrevelocidad del simulador.
- Velocidad por encima del límite del avión (VMO o VNE del manual).

**No es lo mismo “esta regla no se cumplió” que “el vuelo está suspenso”.** Muchas reglas solo quitan puntos. El vuelo puede seguir aprobado si la nota queda en 70 o más y no hay fallo grave.

**Si falta el dato** de una regla (por ejemplo no se grabó el despegue), esa regla **no resta puntos** y queda como *no evaluada*. Eso no equivale a haberla aprobado: simplemente no hay pruebas.

Hay otros dos perfiles (**fácil** y **difícil**) con otros números. Solo cambian la relectura de un vuelo ya subido; **la nota que se guarda en la cartilla usa el perfil normal**. Un administrador puede apagar una regla: entonces no cuenta ni para la nota ni para el suspenso.

**Calidad de los datos:** hace falta, como mínimo, 10 puntos de trayectoria y 5 posiciones distintas. Si el fichero no llega, el vuelo **no es evaluable** y **no aprueba**.

Los números de esta guía son los del perfil **normal**.

---

## Índice de reglas

**Se evalúan hoy**

1. [Alineación de pista al despegar](#1-alineación-de-pista-al-despegar)
2. [Alineación de pista al aterrizar](#2-alineación-de-pista-al-aterrizar)
3. [Punto de toma](#3-punto-de-toma)
4. [Velocidad de descenso al aterrizar](#4-velocidad-de-descenso-al-aterrizar)
5. [Aproximación estabilizada a 500 ft](#5-aproximación-estabilizada-a-500-ft)
6. [Reserva de combustible al final](#6-reserva-de-combustible-al-final)
7. [Duración de las pausas](#7-duración-de-las-pausas)
8. [Compresión de tiempo](#8-compresión-de-tiempo)
9. [Ángulo de alabeo (bank)](#9-ángulo-de-alabeo-bank)
10. [Luces de aterrizaje al despegar](#10-luces-de-aterrizaje-al-despegar)
11. [Luces de aterrizaje al aterrizar](#11-luces-de-aterrizaje-al-aterrizar)
12. [Luz anticolisión (beacon) en vuelo](#12-luz-anticolisión-beacon-en-vuelo)
13. [Luces de navegación en vuelo](#13-luces-de-navegación-en-vuelo)
14. [Luz de rodaje al rodar](#14-luz-de-rodaje-al-rodar)
15. [Luz estroboscópica apagada al rodar](#15-luz-estroboscópica-apagada-al-rodar)
16. [Sin aviso de pérdida](#16-sin-aviso-de-pérdida)
17. [Sin aviso de sobrevelocidad del simulador](#17-sin-aviso-de-sobrevelocidad-del-simulador)
18. [QNH dentro de rango](#18-qnh-dentro-de-rango)
19. [Tren extendido al tomar contacto](#19-tren-extendido-al-tomar-contacto)
20. [Sobrevelocidad estructural (VNE/VMO)](#20-sobrevelocidad-estructural-vnevmo)

**Aún no se evalúan** (no hay aprobado ni suspenso)

21. [Desviación de la ruta planificada](#21-desviación-de-la-ruta-planificada)
22. [Altitud de crucero según regla semicircular](#22-altitud-de-crucero-según-regla-semicircular)
23. [Velocidad limitada por debajo de 10 000 ft](#23-velocidad-limitada-por-debajo-de-10-000-ft)
24. [Squawk asignado por ATC](#24-squawk-asignado-por-atc)
25. [Pista usada coincide con la planificada](#25-pista-usada-coincide-con-la-planificada)
26. [Excursión de pista](#26-excursión-de-pista)

---

## 1. Alineación de pista al despegar

**Qué se mira.** Si, al empezar la carrera de despegue, el avión iba razonablemente paralelo al eje de la pista.

**Cuándo se cumple.** El desvío respecto a la pista es **10 grados o menos** (se usa el valor absoluto: da igual izquierda o derecha).

**Cuándo no se cumple.** El desvío es **mayor de 10 grados**. Se restan **10 puntos**. No es fallo grave: el vuelo no queda suspenso solo por esto.

**Niveles.** No hay bandas. O está dentro del límite, o resta esos 10 puntos.

**Ejemplo.** 8° de desvío → se cumple. 12° → no se cumple (−10).

**Si falta el dato.** No hay evento de despegue o no viene el ángulo → la regla no se puntúa (queda como no evaluada).

---

## 2. Alineación de pista al aterrizar

**Qué se mira.** Lo mismo, pero en el momento en que las ruedas tocan el suelo.

**Cuándo se cumple.** Desvío de **10 grados o menos**.

**Cuándo no se cumple.** Más de 10 grados. Se restan **15 puntos**. No es fallo grave.

**Niveles.** No hay bandas.

**Ejemplo.** 5° → se cumple. 11° → no se cumple (−15).

**Si falta el dato.** No hay toma de contacto grabada → no se puntúa esta regla (ni las otras de la toma). Si hay toma pero no viene el ángulo, el motor **no resta** y **tampoco** la marca explícitamente como no evaluada.

---

## 3. Punto de toma

**Qué se mira.** A qué distancia del umbral de pista (el “comienzo” de la pista) tocan las ruedas.

**Cuándo se cumple.** Esa distancia es **600 metros o menos**.

**Cuándo no se cumple.** Más de 600 m. Se restan **10 puntos**. No es fallo grave.

**Niveles.** No hay bandas.

**Ejemplo.** Toma a 320 m del umbral → se cumple. A 650 m → no se cumple (−10).

**Si falta el dato.** Igual que la regla 2: sin toma, no se evalúa. Con toma pero sin esta distancia, no resta y no queda listada como no evaluada.

---

## 4. Velocidad de descenso al aterrizar

**Qué se mira.** Lo “dura” que fue la toma, según la velocidad vertical en el contacto (pies por minuto). Se usa el **valor absoluto**: un −250 cuenta como 250.

**Cuándo se cumple (esta regla).** La toma **no** entra en la banda más dura (*very_hard*). Las demás bandas **sí** cuentan como que la regla “pasa”, aunque algunas resten puntos.

**Cuándo el vuelo entero queda suspenso.** Velocidad vertical **por encima de 600** pies por minuto (en valor absoluto). Eso es *very_hard*: **fallo grave**. No se restan puntos extra por esta banda; el suspenso viene del fallo grave.

**Niveles** (perfil normal):

| Banda | Hasta (valor absoluto) | Puntos que resta | ¿La regla “pasa”? |
|--------|------------------------|------------------|-------------------|
| butter (muy suave) | 60 | 0 | Sí |
| smooth (suave) | 180 | 0 | Sí |
| normal | 300 | 10 | Sí |
| hard (dura) | 600 | 25 | Sí |
| very_hard | más de 600 | 0 | No: **fallo grave** |

**Ejemplo.** −250 fpm → banda *normal*, −10 puntos, la regla pasa. −720 fpm → *very_hard*, el vuelo **no aprueba**.

**Si falta el dato.** Sin toma, o sin esta velocidad en la toma → no se puntúa.

---

## 5. Aproximación estabilizada a 500 ft

**Qué se mira.** En el último tramo cerca de **500 pies sobre el suelo**, si el avión bajaba de forma razonable (ni en picado fuerte ni subiendo).

**Cuándo se cumple.** Hay un punto en el aire a **500 pies ± 100 pies** sobre el suelo, y en ese punto la velocidad vertical está entre **−1000 y 0** pies por minuto (bajando como mucho a 1000, y no subiendo).

**Cuándo no se cumple.** Ese punto existe, pero la velocidad vertical **está fuera** de ese rango. Se restan **20 puntos**. No es fallo grave.

**Niveles.** No hay bandas. El perfil indica que **no se mira la velocidad indicada** del avión en esta regla (queda pendiente).

**Ejemplo.** A 510 pies, bajando a 600 fpm → se cumple. A 480 pies, bajando a 1200 fpm → no se cumple (−20).

**Si falta el dato.** No hay ningún punto en esa ventana de altura (por ejemplo una aproximación que no pasa por ahí, o una traza muy pobre) → no se puntúa.

---

## 6. Reserva de combustible al final

**Qué se mira.** Cuánto combustible queda al terminar, según el resumen del vuelo.

**Cuándo se cumple.** Quedan **20 kg o más**.

**Cuándo no se cumple.** Menos de 20 kg. Se restan **20 puntos**. No es fallo grave.

**Niveles.** No hay bandas.

**Ejemplo.** 45 kg al calar → se cumple. 18 kg → no se cumple (−20).

**Si falta el dato.** No hay resumen o no viene el combustible restante → no se puntúa.

---

## 7. Duración de las pausas

**Qué se mira.** Si se pausó el simulador, y durante cuánto tiempo **cada** pausa.

**Cuándo se cumple.** Cada pausa grabada dura **120 segundos o menos**.

**Cuándo no se cumple.** Una pausa dura **más de 120 segundos**. Esa pausa resta **10 puntos**. Si hay varias pausas largas, **cada una** resta (pueden acumularse). No es fallo grave.

**Niveles.** No hay bandas.

**Ejemplo.** Una pausa de 90 s → se cumple. Una de 3 minutos → no se cumple (−10). Dos pausas de 3 minutos → −20.

**Si no hay pausas.** El motor no resta nada. Tampoco marca esta regla como “no evaluada”: simplemente no hay pausas que juzgar.

---

## 8. Compresión de tiempo

**Qué se mira.** Si en algún momento el simulador corrió **más rápido que la vida real** (x2, x4, etc.).

**Cuándo se cumple.** La tasa máxima observada es **1,0 o menos** (tiempo real).

**Cuándo no se cumple.** La tasa máxima es **mayor que 1,0**. Es **fallo grave**: el vuelo **no aprueba**. No se restan puntos por esta regla.

**Niveles.** No hay bandas: o es tiempo real, o es suspenso directo.

**Ejemplo.** Todo el vuelo a x1 → se cumple. Un tramo a x2 → el vuelo no aprueba.

**Si falta el dato.** No se grabó esa tasa → no se puntúa.

---

## 9. Ángulo de alabeo (bank)

**Qué se mira.** Cuánto se inclinó el avión de lado (las “alas ladeadas”).

Hay **dos comprobaciones** distintas:

1. **Límite duro.** Si en algún momento el alabeo (en valor absoluto) es **mayor de 60 grados** → **fallo grave**. El vuelo no aprueba. No se restan puntos extra.
2. **Aviso sostenido.** Si no se pasó de 60°, pero el alabeo se mantuvo **por encima de 30 grados** durante **3 muestras seguidas** → la regla no se cumple y se restan **15 puntos**. No es fallo grave.

**Cuándo se cumple.** El máximo es 60° o menos **y** no hubo esas 3 muestras seguidas por encima de 30°.

**Niveles.** Dos umbrales (aviso 30° / fallo 60°) más un recuento de muestras (3), no una escala de notas.

**Ejemplo.** Máximo 25° → se cumple. Máximo 45° durante un instante y luego se endereza (sin 3 muestras seguidas encima de 30°) → se cumple. 45° durante 3 muestras seguidas → −15. 65° en un instante → fallo grave, vuelo suspenso.

**Si falta el dato.** No hay muestras de alabeo (o falta la configuración) → no se puntúa.

---

## 10. Luces de aterrizaje al despegar

**Qué se mira.** Si, cerca del momento del despegue, las luces de aterrizaje estaban **encendidas**.

**Cuándo se cumple.** En el punto de la trayectoria más cercano al despegue, **dentro de 30 segundos**, esas luces están encendidas.

**Cuándo no se cumple.** En ese punto están apagadas. Se restan **10 puntos**. No es fallo grave.

**Niveles.** No hay bandas: encendidas o apagadas.

**Ejemplo.** Luces de aterrizaje puestas al iniciar carrera → se cumple. Apagadas en ese momento → −10.

**Si falta el dato.** No hay despegue, o no hay un punto de trayectoria a menos de 30 s, o no se grabó el estado de esa luz → esta regla concreta no se añade. Si **ninguna** regla de luces pudo evaluarse, el grupo de luces queda como no evaluado.

---

## 11. Luces de aterrizaje al aterrizar

**Qué se mira.** Igual que la anterior, en el **contacto con la pista**.

**Cuándo se cumple.** Luces de aterrizaje encendidas en el punto más cercano a la toma, **dentro de 30 segundos**.

**Cuándo no se cumple.** Apagadas. Se restan **10 puntos**. No es fallo grave.

**Niveles.** Encendidas o apagadas.

**Si falta el dato.** Igual que la regla 10, pero con el evento de toma.

---

## 12. Luz anticolisión (beacon) en vuelo

**Qué se mira.** Con el avión **en el aire**, si la luz anticolisión (beacon) estuvo encendida **en todos** los puntos donde se grabó ese dato.

**Cuándo se cumple.** En todos esos puntos en el aire, beacon **encendido**.

**Cuándo no se cumple.** En **algún** punto en el aire estaba apagado. Se restan **10 puntos**. **No** es fallo grave (aunque alguna ficha antigua hablara de “FAIL”: el motor resta puntos, no suspende el vuelo solo por esto).

**Niveles.** No hay bandas.

**Ejemplo.** Beacon todo el vuelo → se cumple. Un tramo en el aire con beacon apagado → −10.

**Si falta el dato.** No hay puntos en el aire con ese dato → esta regla no se añade (salvo que el grupo entero de luces quede sin evaluar).

---

## 13. Luces de navegación en vuelo

**Qué se mira.** Igual que el beacon, con las luces de navegación (las de punta de ala, en rojo y verde).

**Cuándo se cumple.** Encendidas en **todos** los puntos en el aire donde se grabó el dato.

**Cuándo no se cumple.** Apagadas en algún punto en el aire. Se restan **10 puntos**. No es fallo grave.

**Niveles.** No hay bandas.

---

## 14. Luz de rodaje al rodar

**Qué se mira.** Con el avión **en tierra** y moviéndose a **más de 2 nudos**, si la luz de rodaje (taxi) estaba encendida.

**Cuándo se cumple.** Encendida en **todos** esos puntos de rodaje donde se grabó el dato.

**Cuándo no se cumple.** Apagada en algún momento rodando. Se restan **5 puntos**. No es fallo grave.

**Niveles.** No hay bandas.

**Ejemplo.** Taxi light puesta al salir del parking → se cumple. Rodar de noche (o de día, da igual: el motor no distingue) con esa luz apagada → −5.

---

## 15. Luz estroboscópica apagada al rodar

**Qué se mira.** Lo contrario de las demás luces: **mientras se rueda** (en tierra, más de 2 nudos), las estroboscópicas deben estar **apagadas**. Se reservan para la pista en uso.

**Cuándo se cumple.** En todos esos puntos de rodaje, strobe **apagado**.

**Cuándo no se cumple.** Strobe **encendido** en algún momento rodando. Se restan **5 puntos**. No es fallo grave.

**Niveles.** No hay bandas.

**Ejemplo.** Strobe solo al entrar en pista, apagado en taxiways → se cumple. Strobe puesto ya en el rodaje → −5.

---

## 16. Sin aviso de pérdida

**Qué se mira.** Si el **simulador** activó el aviso de entrada en pérdida (stall warning) en algún momento.

**Cuándo se cumple.** En todos los puntos donde se grabó ese aviso, está **inactivo**.

**Cuándo no se cumple.** El aviso se activó **alguna vez**. Es **fallo grave**: el vuelo **no aprueba**. En el perfil normal no hay puntos extra que restar por esta regla (la penalización configurada es 0).

**Niveles.** No hay bandas: o no saltó el aviso, o el vuelo queda suspenso.

**Si falta el dato.** Ningún punto trae este campo (log antiguo o simulador sin esa variable) → no se puntúa.

---

## 17. Sin aviso de sobrevelocidad del simulador

**Qué se mira.** Si el **propio simulador** encendió su aviso de ir demasiado rápido. **No** se compara aquí con el número del manual del avión (eso es la regla 20).

**Cuándo se cumple.** El aviso no se activó en ningún punto grabado.

**Cuándo no se cumple.** El aviso se activó alguna vez. Es **fallo grave**. No se restan puntos (van a 0).

**Niveles.** No hay bandas.

**Si falta el dato.** No hay muestras de ese aviso → no se puntúa.

---

## 18. QNH dentro de rango

**Qué se mira.** Si la presión que tenía puesta el altímetro (QNH, en pulgadas de mercurio) es un valor **físicamente razonable**, no un número absurdo.

**Cuándo se cumple.** En **todos** los puntos con QNH grabado, el valor está entre **28,5 y 31,2** (incluidos).

**Cuándo no se cumple.** **Algún** punto está fuera de ese rango. Se restan **10 puntos**. No es fallo grave. El detalle que se muestra usa el **último** QNH grabado, aunque el fallo se sitúa en el **primer** punto fuera de rango.

**Niveles.** Solo un rango mínimo–máximo, no una escala de calidad.

**Ejemplo.** 29,92 en todo el vuelo → se cumple. Un tramo a 27,0 → no se cumple (−10).

**Si falta el dato.** No hay muestras de QNH → no se puntúa.

---

## 19. Tren extendido al tomar contacto

**Qué se mira.** En el momento de la toma (punto de trayectoria a **5 segundos** o menos de ese instante), si el tren de aterrizaje estaba **abajo**.

**Cuándo se cumple.** En ese instante el tren está abajo.

**Cuándo no se cumple.** El tren está arriba. Se restan **15 puntos**. No es fallo grave.

**Cuándo no se aplica.** Si **todas** las muestras del vuelo tienen el tren abajo, el motor entiende que es un avión de **tren fijo** y **no evalúa** esta regla (no resta, queda como no evaluada). La ficha descriptiva habla del tren fijo en la ficha del avión; **lo que hace el motor hoy** es esta comprobación sobre la grabación, no leer esa ficha.

**Niveles.** No hay bandas: abajo, arriba, o no aplica.

**Ejemplo.** Tren bajado en final y en la toma → se cumple. Toma con tren arriba (avión de tren retráctil) → −15. Cessna de tren fijo con el tren “abajo” todo el rato → no se evalúa.

**Si falta el dato.** No hay toma, o no hay un punto a menos de 5 s, o no se grabó el estado del tren → no se puntúa.

---

## 20. Sobrevelocidad estructural (VNE/VMO)

**Qué se mira.** Si la velocidad indicada (IAS) superó el **límite certificado del avión**: primero se busca **VMO**; si no hay un número usable, se usa **VNE**. El número sale de la ficha del avión (manual / POH, o referencia del simulador solo si no hay POH). Es **independiente** del aviso del simulador (regla 17). **No** se comprueba MMO (número Mach): el log no lo guarda y no se inventa.

**Cuándo se cumple.** Hay un límite numérico, hay muestras de IAS, y **ninguna** supera ese límite.

**Cuándo no se cumple.** Alguna muestra de IAS es **mayor** que el límite. Es **fallo grave**. No se restan puntos.

**Niveles.** No hay bandas: dentro o fuera del límite.

**Ejemplo.** Límite 163 kt, máximo observado 150 → se cumple. Máximo 170 → el vuelo no aprueba.

**Si falta el dato.** No se pasó la ficha del avión, o no hay VMO ni VNE usable, o no hay IAS → no se puntúa.

---

## 21. Desviación de la ruta planificada

**Qué se miraía.** Si la trayectoria se alejó demasiado de la ruta escrita en el plan.

**Aprobado / suspenso.** **No se puede determinar.** Esta regla **no está implementada**. Siempre queda como no evaluada. El plan guarda la ruta como **texto libre** (por ejemplo `DCT TERSA DCT`) y hoy no se convierte en puntos con coordenadas para medir distancias.

**Qué faltaría** (según la ficha del sistema): un analizador de esa ruta hacia waypoints con latitud y longitud.

---

## 22. Altitud de crucero según regla semicircular

**Qué se miraía.** En VFR, si la altitud de crucero encaja con la regla semicircular según el rumbo (altitudes pares/impares más 500 pies).

**Aprobado / suspenso.** **No se puede determinar.** No está implementada. No hay una altitud de crucero fiable con la que comparar (la del plan puede no coincidir con una fase real estable del vuelo).

---

## 23. Velocidad limitada por debajo de 10 000 ft

**Qué se miraía.** Si, por debajo de 10 000 pies, la velocidad indicada superó el límite del avión (o uno genérico).

**Aprobado / suspenso.** **No se puede determinar.** No está implementada. La ficha indica que los límites VNO/VNE del POH no están verificados en varios aviones, y **inventar un límite se considera peor que no evaluar**.

---

## 24. Squawk asignado por ATC

**Qué se miraía.** Si el transpondedor llevaba el código que asignó ATC, no uno cualquiera.

**Aprobado / suspenso.** **No se puede determinar.** No está implementada. Solo se graba el código **puesto** en el transpondedor, no el que **asignó** ATC. Compararlo consigo mismo no serviría.

---

## 25. Pista usada coincide con la planificada

**Qué se miraía.** Si la pista real de despegue o aterrizaje es la que se pensaba usar al planificar.

**Aprobado / suspenso.** **No se puede determinar.** No está implementada. El plan guarda el **aeródromo**, no la **pista** prevista.

---

## 26. Excursión de pista

**Qué se miraía.** Si el avión se salió de los bordes de la pista mientras rodaba por ella.

**Aprobado / suspenso.** **No se puede determinar.** No está implementada. Se conoce un punto del aeródromo, no el dibujo (ancho, orientación, extremos) de cada pista.

---

## Recuerdo rápido

| Pregunta | Respuesta (perfil normal) |
|----------|---------------------------|
| ¿Con cuántos puntos empiezo? | 100 |
| ¿Nota mínima para aprobar? | 70, **y** sin fallos graves, **y** datos evaluables |
| ¿Una regla que resta puntos suspende el vuelo? | No, salvo que la nota baje de 70 o haya un fallo grave |
| ¿Qué es un fallo grave? | Toma *very_hard*, tiempo acelerado, alabeo > 60°, stall, overspeed del sim, IAS sobre VMO/VNE |
| ¿Las 6 últimas reglas pueden suspenderme? | No: hoy no se puntúan |
