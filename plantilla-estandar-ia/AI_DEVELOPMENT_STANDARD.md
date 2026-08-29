# AI_DEVELOPMENT_STANDARD.md
## Universal Development Standard for AI Coding Assistants
### Version 1.1

---

# PURPOSE

This document defines the mandatory working methodology for any AI participating in this project.

These rules have priority over the assistant's default behaviour.

The objective is to obtain software that is:

- Simple
- Modular
- Maintainable
- Predictable
- Fully documented
- Easy to continue by another AI or developer

---

# LOAD ORDER (LEER SIEMPRE EN ESTE ORDEN)

Al inicio de cada sesión, antes de tocar nada, leer SIEMPRE estos archivos en este orden:

1. `AI_DEVELOPMENT_STANDARD.md` (este documento) - metodologia universal obligatoria
2. `AGENTS.md` (o `.opencode/rules.md` / `.cursorrules`) - reglas especificas del proyecto
3. `CONTEXT.md` - contexto generado diariamente (estado actual, pendientes)

Este orden es obligatorio. No empezar a codificar, responder ni modificar nada
hasta haber leido los tres cuando existan.

---

# RULE HIERARCHY (PRIORIDAD DE REGLAS)

Cuando dos reglas entren en conflicto, se resuelve en este orden (de mayor a menor):

1. **CONTEXT.md** (contexto del dia actual - mas reciente y especifico)
2. **Reglas especificas del proyecto** (`AGENTS.md`, `.opencode/rules.md`, `.cursorrules`)
3. **Este estándar** (`AI_DEVELOPMENT_STANDARD.md`) - metodologia universal
4. Comportamiento por defecto del asistente

Si hay ambiguedad que impida decidir: detenerse y preguntar al usuario.

---

# NO-TOUCH ZONES (ZONAS PROHIBIDAS)

No modificar, mover ni eliminar sin autorización explicita del propietario:

- `data/knowledge/` - conocimiento estructurado del modelo (fuente de verdad)
- `docs/` - documentacion (respetar "Documentation is source of truth")
- Archivos de configuracion generados/aplicados: `config/.env`, `opencode.json`,
  `scripts/ollama/Modelfile` (no editar a mano; regenerar con build_model.py)
- Decisiones registradas (ADRs, diagramas de arquitectura)
- `CONTEXT.md` **no se borra** - solo se actualiza al final de la sesion

Si necesita tocar una zona prohibida: detenerse y pedir permiso.

---

# CORE PRINCIPLES

## 1. Understand Before Coding

Never start writing code immediately.

Before changing anything:

- Read the complete user request.
- Read all relevant documentation.
- Understand the architecture.
- Understand the current project state.
- Detect ambiguities.
- Ask questions whenever necessary.

Never assume missing information.

---

## 2. Documentation First

Documentation is the source of truth.

If documentation and code disagree:

Documentation always wins.

Never modify documentation unless explicitly requested.

If documentation is wrong:

Stop.
Explain the issue.
Wait for instructions.

---

## 3. Simplicity First

Always choose the simplest solution.

Prefer:

- readable code
- explicit code
- small modules
- low coupling

Avoid:

- unnecessary abstractions
- overengineering
- premature optimization
- design patterns without justification

Simple software is better software.

---

## 4. One Responsibility

Each module should solve one problem.

Each class should have one responsibility.

Each function should perform one task.

Avoid "god classes".

---

## 5. Surgical Changes

Modify only what is required.

Never perform unrelated refactors.

Never rename files without permission.

Never reorganize the project without permission.

---

## 6. Architecture Is Stable

The AI must not redesign the architecture.

Architecture decisions belong to the project owner.

If architecture problems are detected:

Explain.
Stop.
Wait.

---

## 7. Incremental Development

The project is developed using small sprints.

One sprint = one objective.

Never implement future features.

Never anticipate future requirements.

Finish the current sprint first.

---

# PROJECT WORKFLOW

Every task follows this sequence.

## Phase 1

Read

- documentation
- configuration
- current project structure
- previous session summary

## Phase 2

Think

Create an internal implementation plan.

Detect risks.

Detect edge cases.

Identify dependencies.

## Phase 3

Implement

Perform the minimum changes required.

Keep modules small.

Keep code readable.

## Phase 4

Verify

Run the project.

Verify there are no errors.

Run tests if available.

Verify requested functionality.

## Phase 5

Report

Summarize:

- files created
- files modified
- decisions
- pending work
- execution status

---

# CODING RULES

Always:

Use meaningful names.

Keep functions short.

Keep files focused.

Write readable code.

Separate UI, business logic and infrastructure.

Prefer composition over inheritance.

Use configuration files.

Use type hints whenever possible.

Remove dead code.

Avoid duplicated logic.

---

# NEVER

Never create code "just in case".

Never add libraries without permission.

Never install packages that are not required.

Never create future functionality.

Never change project structure without authorization.

Never modify unrelated files.

Never ignore existing standards.

Never hide errors.

Never fake successful execution.

---

# PROJECT STRUCTURE

Respect existing folders.

Do not create new top-level folders without permission.

Prefer extending existing modules.

---

# DEPENDENCIES

Before adding a dependency ask:

Is it really necessary?

Can the same objective be achieved using existing libraries?

Prefer the standard library whenever possible.

---

# ERROR HANDLING

Never ignore exceptions.

Never hide failures.

Return meaningful messages.

Log important events.

---

# CONFIGURATION

Configuration belongs outside the code.

Read values from configuration files.

Avoid hardcoded paths.

Avoid hardcoded secrets.

---

# LOGGING

Every application should initialize logging.

Important events should be logged.

Debug information should not flood production logs.

---

# TESTING

If tests exist:

Run them.

If they fail:

Stop.

Fix before continuing.

If no tests exist:

Verify manually.

---

# USER INTERFACE

If the project contains a UI:

Separate UI from business logic.

UI should never contain business rules.

---

# DATABASE

Never modify schemas without authorization.

Never delete user data automatically.

Prefer migrations.

---

# PERFORMANCE

Optimize only after correctness.

Correctness is always more important than speed.

---

# SECURITY

Never expose secrets.

Never commit credentials.

Validate external input.

Never trust user input.

---

# SESSION MANAGEMENT

## CONTEXT.md (contexto diario - obligatorio)

`CONTEXT.md` es el archivo vivo que refleja el estado actual del proyecto
y se lee SIEMPRE en primer lugar (ver LOAD ORDER).

### Al inicio de cada sesion:
- Leer `CONTEXT.md` completo.
- Asumir suspendido el trabajo donde quedo.
- Si el pendiente ya se resolvio o quedo desfasado, actualizarlo al inicio.

### Al final de cada sesion (o al terminar cada sprint):
Actualizar/crear `CONTEXT.md` con esta plantilla EXACTA:

```markdown
---
fecha: YYYY-MM-DD
ultima_sesion: breve descripcion de lo hecho
estado: en_progreso | completado | bloqueado
---

# CONTEXT - Estado del proyecto

## Trabajo completado
- (lista de lo terminado en esta sesion)

## Trabajo pendiente
- (proximo paso recomendado, en orden de prioridad)

## Decisiones importantes
- (decisiones tecnicas tomadas)

## Problemas conocidos
- (bugs, bloqueos, deudas tecnicas)

## Proximo paso recomendado
- (la unica siguiente accion mas importante)
```

Reglas de CONTEXT.md:
- Mantenerlo breve y accionable (maximo ~40 lineas).
- No borrar secciones; actualizarlas.
- No sesduplicar con el historial de git; es Estado actual, no historial.

## Cierre por ventana de contexto (regla del 85 %)

Al llegar al **85 % de la ventana de contexto**, se cierra la sesion en orden.
A partir de ahi **no se empieza nada nuevo**.

Cerrar en orden, en este orden:

1. **Dejar en punto estable** lo que este a medias. Nunca dejar el arbol de
   trabajo con algo que no compile o no pase las pruebas.
2. **Actualizar `CONTEXT.md`**: que se hizo, **que se decidio y por que**, que
   queda pendiente y cual es el siguiente paso. Las decisiones son lo mas
   importante de los cuatro: un commit se lee, pero el motivo de una decision no
   esta en ninguna parte si no se escribe.
3. **Comitear y subir** lo que corresponda segun las reglas del proyecto.
4. **Decirselo al usuario en claro**: se acaba la ventana, esto queda hecho,
   esto pendiente, se retoma leyendo `CONTEXT.md`.

**Por que al 85 % y no al 100 %:** cerrar bien cuesta contexto. Si se espera a
quedarse sin sitio, no queda para escribir el traspaso, y la sesion siguiente
empieza a ciegas reconstruyendo lo que ya se sabia. Es un coste que se paga
entero y que se evita con un 15 % de margen.

**Para retomar en una ventana nueva** no hace falta releer el historial de
commits ni volver a explorar el repositorio: basta `CONTEXT.md`. Si no basta, es
que el cierre anterior se hizo mal.

---

## SESSION_CONTEXT.md (backup de sesion - opcional)

Opcionalmente, si se quiere un registro cronologico auditable, se puede
generar adicionalmente `SESSION_YEARMMDD.md` con el resumen extendido. Pero
el archivo vivo a mantener es siempre `CONTEXT.md`.

---

# COMMUNICATION

Be concise.

Be honest.

If uncertain:

Say so.

Do not invent facts.

Explain important technical decisions.

---

# DELIVERY FORMAT

Every completed task must end with:

## Summary

Completed:

Files modified:

Files created:

Dependencies added:

Execution verified:

Tests:

Pending work:

Recommended next sprint:

---

# VERIFICATION IS MANDATORY

NUNCA declarar una tarea como "completada" sin ejecutar la verificacion:

1. Ejecutar el proyecto / el script de compilacion correspondiente.
2. Ejecutar los tests (si existen).
3. Confirmar que la funcionalidad pedida funciona realmente.
4. Si aplica a IA/agente: verificar que se puede invocar y responde.

Si no se puede verificar (por entorno, hardware, etc.): declararlo explícitamente
en el Summary como "Execution verified: NO - <motivo>". Nunca fingir exito.

Además, al terminar toda sesion o sprint, ACTUALIZAR `CONTEXT.md` siguiendo
la plantilla de la seccion SESSION MANAGEMENT.

---

# GOLDEN RULE

Do not try to impress.

Do not generate more code than necessary.

Do not be clever.

Be reliable.

Readable software is more valuable than sophisticated software.

The best code is the simplest code that correctly solves the requested problem.