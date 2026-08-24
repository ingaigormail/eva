---
fecha: 2026-08-24
ultima_sesion: Guía de reglas, auditoría web (sin parche), skill code-review, mapa VATSIM en working tree; lanzador aviación fuera de este repo
estado: en_progreso
---

# CONTEXT - EvA Airliner

## Trabajo completado
- Guía práctica de las 26 reglas: `docs/guia_practica_reglas_puntuacion.md` (perfil **normal**; 20 evaluadas + 6 no implementadas sin inventar criterios). Enlace en `docs/README.md`.
- Auditoría de `web/` con code-review-excellence: CSRF/sesión/PBKDF2 bien; **IDOR** en `GET /vuelo/<nombre>/json` (no comprueba `es_de`); no se parcheó.
- Skill `code-review-excellence` instalada en `.agents/skills/` (`npx skills add …`; TLS npm necesitó `--use-system-ca`).
- En el árbol (posible otro chat): `/vatsim` + `/api/vatsim-data` en `web/app.py` y `web/templates/vatsim_live.html` (público, sin login).
- Fuera de este git (`D:\proyectos`): panel `lanzador_aviacion.pyw` + `lanzador_aviacion.bat`; `todos.bat` abre el panel (no arranca todo a la vez).

## Trabajo pendiente
- Parchear IDOR de `/vuelo/<nombre>/json` + test de dos pilotos (recomendado antes de tratar la web pública).
- Confirmar en Clouding: arranque por `wsgi:app` (no `python web/app.py` con debug), cuenta `pruebas` bloqueada.
- Decidir si desplegar `/vatsim` o dejarlo solo local.
- X-Plane `poll()` sigue sin cerrar.
- Comprobar URL Clouding si el host cambia.
- Monitor VPS (opcional): Netdata en localhost + túnel SSH; OpenCode no sustituye gráficos.

## Decisiones importantes
- Números de la guía = perfil `normal` (`profiles.yaml`); easy/hard solo relectura.
- Beacon/nav/taxi/strobe **restan puntos**; no son fallo grave (el motor manda, no fichas antiguas).
- Little, EvA cartilla y Airhispania comparten puerto **5000**: no arrancar más de una.
- `/vatsim` y `/api/vatsim-data` están en la lista pública de `exigir_sesion` (sin login).

## Problemas conocidos
- IDOR JSON de vuelo entre usuarios autenticados.
- `/registro/<nombre>` no usa `_find_by_name` (posible ruta absoluta en Windows).
- Hash de traza Fase 1: se confía en el del cliente.
- CSP vs Leaflet/OSM en `vuelo.html` (unpkg + tiles); `aerolinea.html` ya usa vendor local.

## Proximo paso recomendado
- Parchear `crudo()` en `web/app.py` (`/vuelo/<nombre>/json`) con la misma comprobación de dueño que `detalle()`.
