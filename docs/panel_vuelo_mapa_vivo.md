# Panel de vuelo del mapa en vivo

Especificación aprobada el 2026-08-29. **Sin implementar.**

Al pinchar un avión en `/vatsim` se abre un panel al estilo de FlightRadar24.
La regla de diseño es la de ellos: **lo importante se ve sin desplegar nada**, y
todo lo demás está escondido detrás de un desplegable.

---

## Siempre visible

```
┌──────────────────────────────────────────┐
│ EVA18L                    C172      [✕]  │
│ Escuela Virtual Aérea · EC-EVA           │
├──────────────────────────────────────────┤
│   LEMD          ✈          LEVC          │
│   Madrid                   Valencia      │
│                                          │
│   ●━━━━━━━━━━━━━━━━━○─────────           │
│   142 NM hechas        63 NM · 34 min    │
├──────────────────────────────────────────┤
│  ALTITUD        VELOCIDAD       RUMBO    │
│  4.500 ft       118 kt          134°     │
└──────────────────────────────────────────┘
```

Seis datos y una barra. La segunda línea (aerolínea y matrícula) solo aparece
si el CID está en el mapeo de EvA.

## Desplegables

**▸ Plan de vuelo** — nivel planificado, alterno, hora de salida, tiempo en
ruta, squawk asignado y la ruta completa.

**▸ El piloto en EvA** — solo si el CID está en el mapeo: categoría, vuelos
APTO del mes, puesto en la clasificación y los tres últimos vuelos con su nota.

## Fuera del panel

- **`remarks`** del plan. Un ejemplo real del feed trae 300 caracteres de
  códigos PBN y EET. No lo lee nadie.
- **QNH en dos unidades.** Una, y dentro del desplegable.
- `server`, `pilot_rating`, `military_rating`, `fuel_time`, `revision_id`.

---

## De dónde sale cada dato

El feed de VATSIM (`data.vatsim.net/v3/vatsim-data.json`, comprobado el
2026-08-29) da por piloto: `cid`, `name`, `callsign`, `latitude`, `longitude`,
`altitude`, `groundspeed`, `heading`, `transponder`, `qnh_i_hg`, `qnh_mb`,
`logon_time`, y dentro de `flight_plan`: `flight_rules`, `aircraft_short`,
`departure`, `arrival`, `alternate`, `cruise_tas`, `altitude`, `deptime`,
`enroute_time`, `route`, `assigned_transponder`.

**No da** velocidad vertical, IAS, Mach, altitud GPS ni matrícula: eso sale del
transpondedor Mode S real, que VATSIM no transmite.

### Lo que EvA puede poner y FlightRadar24 no

- **La matrícula** (`EC-EVA`…). FR24 la saca de bases externas; EvA sabe qué
  avión reservó el piloto porque se lo dio.
- **El puesto del mes.** Si pinchas el vuelo de un compañero y ves «3.º de
  septiembre», ahí está el picarse, sin ir a mirar ninguna tabla.

Eso da al piloto un motivo real para dar su CID, que hoy tienen todos vacío.

### Lo que hay que calcular

La barra de progreso y el «63 NM · 34 min» **no vienen en el feed**. Salen de
las coordenadas de origen y destino (`client/config/airports.json`, 17.800
aeropuertos, ya en el repo) y de `groundspeed`.

**Capar el tiempo restante:** si el piloto está en espera dando vueltas, la
cuenta da cifras absurdas. Por encima de 3 horas restantes, poner «—» en vez de
un número que nadie se va a creer.

---

## Detalle que se nota al usarlo

El feed se refresca cada 15 s y `_fetch_vatsim_raw` cachea 12, así que el avión
**dará saltos**, no se moverá suave como en FR24. Interpolar la posición entre
actualizaciones lo arregla, pero es trabajo aparte y no bloquea el panel.
