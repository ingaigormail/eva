# 🧠 Plantilla de Estándar IA para Proyectos

Conjunto de archivos para que **cualquier asistente IA** (OpenCode, Claude Code,
Cursor, etc.) trabaje con una metodologia uniforme y lea SIEMPRE el contexto
del proyecto antes de codificar.

## 📦 Contenido

| Archivo | Descripcion |
|---------|-------------|
| `AI_DEVELOPMENT_STANDARD.md` | Estandar universal de metodologia (simplicidad, cambios quirurgicos, verificacion obligatoria, gestion de sesion). |
| `AGENTS.md` | Reglas por proyecto con bloque LOAD ORDER. **Se lee automaticamente** al abrir el proyecto en la mayoria de asistentes. |
| `CONTEXT.md` | Contexto diario vivo (estado actual, pendientes, proximo paso). Plantilla para cada sesion. |
| `opencode.json.example` | Configuracion de ejemplo para OpenCode (proveedor Ollama local). |

## 🚀 Como usar en un proyecto NUEVO

1. Copia los 4 archivos a la **raiz** de tu proyecto:

   ```sh
   cp -r plantilla-estandar-ia/* /ruta/del/proyecto/
   ```

2. Rellena las secciones `[[LLENAR]]` de `AGENTS.md` con los datos reales
   (descripcion, stack, convenciones, comandos, no-touch zones).

3. Rellena `CONTEXT.md` con el estado inicial del proyecto.

4. (Opcional) Copia `opencode.json.example` a `opencode.json` y ajusta el
   proveedor/modelo al que uses.

## 🔁 Flujo de trabajo diario

- **Al empezar**: el asistente lee LOAD ORDER -> AGENTS.md -> CONTEXT.md.
- **Durante**: sigue las convenciones y NO-TOUCH ZONES.
- **Al terminar**: actualiza `CONTEXT.md` y entrega el resumen (DELIVERY FORMAT).

## 🔧 Configurar `CONTEXT.md` diario automatico

El archivo `CONTEXT.md` se actualiza **al final de cada sesion/sprint** de forma
manual (o por el asistente) gestionando el estado vivo del proyecto.

---

**Personalizacion:** ajusta el `AI_DEVELOPMENT_STANDARD.md` si tu organizacion
requiere matices, pero se recomienda mantenerlo como fuente de verdad comun.
