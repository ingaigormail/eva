# AGENTS.md — reglas de EvA

## ⚠️ LOAD ORDER — leer siempre primero (obligatorio)

Antes de tocar nada, en este orden:

1. **`plantilla-estandar-ia/AI_DEVELOPMENT_STANDARD.md`** — metodología
   universal. Ahí está, entre otras cosas, la **regla del 85 %**: al llegar al
   85 % de la ventana de contexto se cierra la sesión en orden y no se empieza
   nada nuevo.
2. **`AGENTS.md`** (este fichero) — lo específico de EvA.
3. **`CONTEXT.md`** — el estado de hoy: qué se hizo, qué está decidido, qué
   queda. Es el parte que comparten todos los agentes.

Si necesitas orientarte en la arquitectura: `DOCUMENTACION_PROYECTO.md`.

El estándar no está copiado a la raíz **a propósito**: dos copias del mismo
documento en un repositorio acaban divergiendo, y este proyecto ya ha pagado ese
precio dos veces (los datos de flota, y `airhispania` frente a `eva`). Hay una
sola copia y se lee desde donde está.

> Nota pendiente: `plantilla-estandar-ia/` es universal, no de EvA. Su sitio
> natural es `D:\proyectos\`, para que lo compartan todos los proyectos en vez
> de tener una copia dentro de cada uno.

---

## Qué es EvA

Aerolínea virtual sobre **VATSIM**. Los pilotos graban sus vuelos con un cliente
de escritorio (`client/`, «EvA Airliner»), se evalúan contra criterios VFR y el
resultado va a una cartilla web (`web/`).

**Principio que no se toca:** el motor de evaluación no se duplica. Cliente y
servidor importan el mismo `avcars.evaluation.scoring`, para que evaluar en
local y en la web dé exactamente el mismo resultado.

---

## Dos agentes, un solo árbol de ficheros

Aquí trabaja más de una IA sobre **el mismo directorio**. No son ramas
distintas, así que git no protege de nada. Lo que protege es repartirse el
terreno.

| Zona | Quién | Ficheros |
|---|---|---|
| Código y pruebas | Claude Code | `client/`, `web/**.py`, plantillas, migraciones |
| Documentos, planes, auditorías | OpenCode | `docs/`, `thoughts/`, `CONTEXT.md` |

**Antes de tocar código**, reclamar el dominio:

    python D:\proyectos\coord.py claim eva --who "quien seas"
    python D:\proyectos\coord.py release

Para documentos no hace falta candado: basta respetar el reparto.

**Solo Claude Code comitea.** Los demás dejan sus cambios en el árbol para que
el usuario los revise. Si el usuario pide que se suban, se comitean **marcando
de quién es el trabajo**: no se firma como propio lo que ha hecho otro.

---

## Comprobar antes de afirmar

La regla que más disgustos ha evitado y la que más veces se ha saltado.

- **Leer un decorador no es probar una ruta.** Una auditoría de agosto de 2026
  declaró tres APIs «sin autenticación» leyendo el código. Probadas, devuelven
  302: las cubría un `before_request` que el auditor no miró. Dos de sus cinco
  acciones urgentes no procedían.
- **Que no exista una carpeta `tests/` no significa que no haya pruebas.** Las
  de la web están sueltas en `web/test_*.py`. Son 206.
- Si otro agente afirma algo, **verifícalo**. Se equivocan igual que tú.

---

## Nunca inventar un valor aeronáutico

Está en la cabecera de `client/config/aircraft.yaml` y vale para todo el
proyecto:

> Una V-speed inventada no produce un aviso: produce una penalización a un
> piloto que volaba bien. Es peor que no evaluar.

`null` significa «sin verificar», y el motor debe tratarlo como «esta regla no
se evalúa» — nunca como cero ni como «sin límite». Lo mismo con pesos, consumos
y límites de zona: **si no se puede afirmar, no se acusa.**

Cuando entre un dato, anotar de dónde salió (`fuente`, `fecha_consulta`,
`verificado`). Un número sin procedencia no se puede revisar dentro de tres
meses.

---

## Un solo sitio por dato

| Dato | Dónde |
|---|---|
| Flota: pesos, velocidades, combustible, plazas | `client/config/aircraft.yaml` |
| Valores típicos de operación (**no** límites) | `client/config/performance_atc.yaml` |
| Reglas de puntuación | `client/config/profiles.yaml` + ajustes en `/gestion/reglas` |
| Espacio aéreo | `web/data/aeronautica.db` (lo genera `web/tools/descargar_enaire.py`; no va en git) |

Hubo una segunda copia de los datos de flota escrita a mano en
`web/despacho_pesos.py` y se desincronizó sin que nadie se enterara: el C172
figuraba con 620 kg de peso en vacío cuando el simulador modela 767.

---

## Trampas de este equipo

- **`gh` no está instalado**: no se pueden crear PR desde la línea de órdenes.
- **`D:\proyectos\airhispania` está muerto** desde el renombre del 20-08-2026.
  No escribir ahí. El proyecto vivo es `D:\proyectos\eva`.
- **6 pruebas fallan desde antes**, en `test_scoring`, `test_data_quality` y
  `test_regresion_vuelo_real`, más `test_simconnect_hybrid.py`, que ni se
  recoge. No son tuyas: no digas que las has roto ni que las has arreglado.
- **El TLS puede fallar** con antivirus (`CERTIFICATE_VERIFY_FAILED`). Se
  resuelve con `truststore`, ya instalado.
- **Probar antes de desplegar**: `bash despliegue/probar_pre.sh` levanta un clon
  limpio de GitHub en `D:\proyectos\eva-pre`. Existe porque dos veces se coló un
  paquete que estaba en el disco pero no en git: funcionaba en local y reventaba
  en el servidor.
