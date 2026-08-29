# AGENTS.md — reglas para cualquier IA que trabaje en EvA

Este fichero es la puerta de entrada. Lo lee cualquier agente (Claude Code,
OpenCode, Gemini/Antigravity, Cursor…) antes de tocar nada.

---

## 1. Qué leer, y en este orden

1. **`AGENTS.md`** (este fichero) — las reglas.
2. **`CONTEXT.md`** — el estado de hoy: qué se hizo, qué está decidido, qué
   queda. Es el parte que comparten todos los agentes.
3. **`DOCUMENTACION_PROYECTO.md`** — arquitectura y componentes, si te hace
   falta orientarte.

No hace falta más para empezar. Los tres se mantienen al día; si algo de lo que
lees ahí no cuadra con el código, **gana el código** y corrige el documento.

---

## 2. La regla del 85 % de contexto

**Al llegar al 85 % de la ventana de contexto, se cierra la ventana en orden.**
No se empieza nada nuevo a partir de ahí.

Cerrar en orden significa, en este orden:

1. **Terminar o dejar en punto estable** lo que esté a medias. Nunca dejar el
   árbol de trabajo con algo a medio hacer que no compile o no pase pruebas.
2. **Actualizar `CONTEXT.md`**: qué se hizo, **qué se decidió y por qué**, qué
   queda pendiente y cuál es el siguiente paso. Las decisiones son lo más
   importante: un commit se lee, pero el motivo de una decisión se pierde.
3. **Comitear y subir** (ver la regla 4 sobre quién comitea).
4. **Decírselo al usuario en claro**: «se acaba la ventana, esto queda hecho,
   esto queda pendiente, retoma leyendo `CONTEXT.md`».

Por qué al 85 % y no al 100 %: cerrar bien cuesta contexto. Si esperas a
quedarte sin sitio, no te queda para escribir el traspaso, y la sesión siguiente
empieza a ciegas reconstruyendo lo que ya se sabía. Se ha pagado ese precio más
de una vez.

**Para retomar en una ventana nueva:** leer `CONTEXT.md` entero. Ahí está el
estado, las decisiones cerradas y los pendientes ordenados. No hace falta releer
el historial de commits ni volver a explorar el repositorio.

---

## 3. Dos agentes, un solo árbol de ficheros

Aquí trabaja más de una IA sobre **el mismo directorio**. No son ramas
distintas: es un único árbol, así que git no protege de nada. Lo que protege es
repartirse el terreno.

| Zona | Quién | Ficheros |
|---|---|---|
| Código y pruebas | Claude Code | `client/`, `web/**.py`, plantillas, migraciones |
| Documentos, planes, auditorías | OpenCode | `docs/`, `thoughts/`, `CONTEXT.md`, `AGENTS.md` |

**Antes de tocar código**, reclamar el dominio:

    python D:\proyectos\coord.py claim eva --who "quien seas"
    python D:\proyectos\coord.py release

Para documentos no hace falta candado: basta con respetar el reparto.

---

## 4. Quién comitea

**Solo Claude Code comitea.** Los demás agentes dejan sus cambios en el árbol
sin comitear, para que el usuario los revise. Si el usuario pide explícitamente
que se suban, se comitean **marcando en el mensaje de quién es el trabajo** —
no se firma como propio lo que ha hecho otro.

---

## 5. Comprobar antes de afirmar

Esta es la regla que más disgustos ha evitado y la que más veces se ha saltado.

- **Leer un decorador no es probar una ruta.** Una auditoría de agosto de 2026
  declaró tres APIs «sin autenticación» leyendo el código. Probadas, devuelven
  302: las cubría un `before_request` que el auditor no miró. Dos de sus cinco
  acciones urgentes no procedían.
- **Que no exista una carpeta `tests/` no significa que no haya pruebas.** Las
  de la web están sueltas en `web/test_*.py`. Son 206.
- Si otro agente afirma algo, **verifícalo**. Se equivocan igual que tú.

---

## 6. Nunca inventar un valor aeronáutico

Está escrito en la cabecera de `client/config/aircraft.yaml` y vale para todo el
proyecto:

> Una V-speed inventada no produce un aviso: produce una penalización a un
> piloto que volaba bien. Es peor que no evaluar.

`null` significa «sin verificar» y el motor debe tratarlo como «esta regla no se
evalúa» — nunca como cero ni como «sin límite». Lo mismo con pesos, consumos y
límites de zona: si no se puede afirmar, no se acusa.

Cuando un dato entre, **anotar de dónde salió** (`fuente`, `fecha_consulta`,
`verificado`). Un número sin procedencia no se puede revisar dentro de tres
meses.

---

## 7. Un solo sitio por dato

- **Datos de flota** (pesos, velocidades, combustible, plazas):
  `client/config/aircraft.yaml`. Nada más. Hubo una segunda copia escrita a mano
  en `web/despacho_pesos.py` y se desincronizó sin que nadie se enterara.
- **Valores típicos de operación** (no límites): `client/config/performance_atc.yaml`,
  separado a propósito. No mezclar con los límites.
- **Reglas de puntuación**: `client/config/profiles.yaml` más los ajustes en
  caliente de `/gestion/reglas`.
- **Espacio aéreo**: `web/data/aeronautica.db`, generado por
  `web/tools/descargar_enaire.py`. No va en git; se rehace cada ciclo AIRAC.

---

## 8. Trampas conocidas de este equipo

- **`gh` no está instalado**: no se pueden crear PR desde la línea de órdenes.
- **`D:\proyectos\airhispania` está muerto** desde el renombre del 20-08-2026.
  No escribir ahí. El proyecto vivo es `D:\proyectos\eva`.
- **6 pruebas fallan desde antes**, en `test_scoring`, `test_data_quality` y
  `test_regresion_vuelo_real`, más `test_simconnect_hybrid.py` que ni se
  recoge. No son tuyas: no digas que las has roto ni que las has arreglado.
- **El TLS puede fallar** en máquinas con antivirus (`CERTIFICATE_VERIFY_FAILED`).
  Se resuelve con `truststore`, ya instalado.
- **Probar antes de desplegar**: `bash despliegue/probar_pre.sh` levanta un clon
  limpio de GitHub en `D:\proyectos\eva-pre`. Existe porque dos veces se coló un
  paquete que estaba en el disco pero no en git: funcionaba en local y reventaba
  en el servidor.

---

## 9. Al terminar cualquier tarea

Actualizar `CONTEXT.md`. Siempre. Aunque la tarea haya sido pequeña, aunque no
se haya comiteado nada, y aunque quede ventana de sobra.
