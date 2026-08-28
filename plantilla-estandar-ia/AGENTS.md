# AGENTS.md - Plantilla de reglas por proyecto

> Copiar este archivo a la RAIZ de cada proyecto y completar las secciones
> entre [[LLENAR]] marcando los datos especificos del proyecto.

## ⚠️ LOAD ORDER - LEER SIEMPRE PRIMERO (obligatorio)

Lee estos archivos, en este orden, antes de cualquier tarea:

1. `AI_DEVELOPMENT_STANDARD.md` - metodologia universal obligatoria
2. `AGENTS.md` (este archivo) - reglas especificas del proyecto
3. `CONTEXT.md` - contexto del dia (estado actual, pendientes, proximo paso)

No empieces a codificar ni respondas hasta haber leido los tres. Si `CONTEXT.md`
no existe, crealo con la plantilla de AI_DEVELOPMENT_STANDARD.md (SESSION MANAGEMENT).
Al terminar cada tarea, actualiza `CONTEXT.md`.

## Que estamos construyendo
[[LLENAR: descripcion en 2-3 lineas del proyecto]]

## Arquitectura / Stack
[[LLENAR: tecnologias, lenguaje, estructura de carpetas clave]]

## Convenciones de codigo
[[LLENAR: estilo, nombrado, linters, formatters, versiones]]

## Comandos de trabajo (build / test / lint)
[[LLENAR: los comandos EXACTOS para compilar, probar y formatear]]

## NO-TOUCH ZONES (personalizar)
- `data/` (datos generados/estructurados)
- `docs/` (documentacion - fuente de verdad)
- `config/*.env` (secretos y configuracion)
- Cualquier archivo generado por scripts (no editar a mano si se regenera)

## Dependencias
[[LLENAR: librerias permitidas, reglas de nuevas dependencias]]
