# Qué se evalúa en cada vuelo y con cuántos puntos se aprueba

> **Perfil que guarda la cartilla: normal.** Fácil/difícil solo para relectura.

## Cómo se aprueba

Empiezas con **100 puntos**. Cada fallo resta puntos. Apruebas si se cumplen **las 3 a la vez**:

1. **Nota ≥ 70**
2. **Sin fallo grave** (FAIL directo)
3. **Datos suficientes** (≥10 puntos de trayectoria y ≥5 posiciones distintas; si no, NO EVALUABLE y no aprueba)

Si hay FAIL, suspendes aunque la nota sea 85.

Fuentes: `client/config/profiles.yaml:9` y `client/avcars/evaluation/scoring.py:33`

---

## Lo que sí te puede quitar puntos o suspender (20 reglas)

| # | Qué se mira | Límite normal | ¿Resta? | ¿FAIL? |
|---|---|---|---|---|
| 1 | Alineación al despegar | ≤10° | **-10** | no |
| 2 | Alineación al aterrizar | ≤10° | **-15** | no |
| 3 | Punto de toma (dist. umbral) | ≤600 m | **-10** | no |
| 4 | Dureza de toma (vs vertical) | ver bandas | **-10 / -25** | **sí si >600 fpm** (`very_hard`) |
| 5 | Aproximación estable a 500 ft AGL | vs -1000..0 fpm en 500±100 ft | **-20** | no |
| 6 | Combustible al final | ≥20 kg | **-20** | no |
| 7 | Pausa (cada pausa) | ≤120 s | **-10 por pausa** | no |
| 8 | Tiempo acelerado (sim rate) | ≤1.0x | 0 | **sí si >1.0** |
| 9 | Alabeo (bank) | aviso 30° ×3 muestras / duro 60° | **-15** (sostenido) | **sí si >60°** |
| 10 | Luces aterrizaje al despegar | ON ±30 s despegue | **-10** | no |
| 11 | Luces aterrizaje al aterrizar | ON ±30 s toma | **-10** | no |
| 12 | Beacon en vuelo | ON todo el vuelo | **-10** | no |
| 13 | Nav en vuelo | ON todo el vuelo | **-10** | no |
| 14 | Taxi al rodar (>2 kt en tierra) | ON | **-5** | no |
| 15 | Strobe al rodar | OFF en rodaje | **-5** | no |
| 16 | Aviso pérdida (stall) simulador | nunca activo | 0 | **sí** |
| 17 | Aviso sobrevelocidad simulador | nunca activo | 0 | **sí** |
| 18 | QNH | 28.5–31.2 inHg | **-10** | no |
| 19 | Tren abajo en la toma | abajo (si retráctil) | **-15** | no |
| 20 | VNE/VMO (límite del avión) | IAS ≤ VMO/VNE POH | 0 | **sí** |

**Luces 10-15:** si no hay dato de luces en todo el vuelo, no restan (quedan “no evaluadas”).

**Tren 19:** aviones de tren fijo (todo el vuelo con tren abajo) no se evalúan.

**Bandas toma regla 4 (normal):** butter ≤60 fpm 0pt / smooth ≤180 0pt / normal ≤300 **-10** / hard ≤600 **-25** / very_hard >600 **FAIL**.

Penalizaciones en `client/config/profiles.yaml:37`

---

## Lo que NO te puede suspender hoy (6 reglas aún no implementadas)

21 desviación de ruta · 22 altitud semicircular · 23 velocidad <10.000 ft · 24 squawk ATC · 25 pista planificada · 26 excursión de pista. Siempre salen como “no evaluadas”.

---

## Fácil vs normal vs difícil

| Perfil | Nota para aprobar | Alineación | Toma | Reserva fuel | Bank aviso/duro |
|---|---|---|---|---|---|
| **Fácil** | 60 | 15° / 750 m | bandas más anchas | 15 kg | 35°×4 / 70° |
| **Normal** | **70** | **10° / 600 m** | **ver arriba** | **20 kg** | **30°×3 / 60°** |
| **Difícil** | 80 | 6° / 450 m | bandas más estrechas | 25 kg | 25°×2 / 50° |

La cartilla siempre guarda la nota **normal**.

---

## Ejemplos rápidos

- Aterrizas a 250 fpm (-10), beacon OFF un momento (-10), QNH OK → 100-20 = **80 apruebas**.
- Aterrizas a 420 fpm (-25), alineación aterrizaje 12° (-15), pausa 3 min (-10) → 100-50 = **50 suspendes por nota**.
- Todo perfecto pero pones ×2 de tiempo → **FAIL, suspendes directo**.
- Toma a 720 fpm → **FAIL very_hard**, da igual el resto.

---

Guía completa con explicación regla por regla: `docs/guia_practica_reglas_puntuacion.md:1`
Matriz campo-a-campo: `docs/matriz_reglas.md:1`
