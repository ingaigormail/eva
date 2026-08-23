# Documentación técnica de EvA

Este directorio es la documentación de **EvA** (`D:\proyectos\eva`), organizada
con el mismo criterio que `D:\proyectos\airhispania\docs`: un documento por
preocupación, afirmaciones marcadas por origen, y el código como fuente de
verdad.

La documentación de Airhispania se ha usado **solo como modelo de estructura y
estilo**. No describe este repositorio. Donde Airhispania documenta un
componente que EvA no tiene, se indica explícitamente. Donde EvA tiene algo
que Airhispania no documenta (p. ej. Vuelta a España, módulo `airliner/`),
hay secciones nuevas.

## Convención de marcado

| Marca | Significado |
|---|---|
| `[CONF]` | Confirmado en código, configuración o tests de este repositorio |
| `[INF]` | Inferido de comentarios o nombres, sin otra prueba de ejecución |
| `[PEND]` | No se ha podido determinar a partir del proyecto |
| `[N/A]` | Existe en el modelo Airhispania; **no hay equivalente** en EvA |

## Índice (equivalente Airhispania → EvA)

| Airhispania | EvA | Notas |
|---|---|---|
| *(inicio)* | [`resumen_inicio.md`](resumen_inicio.md) | **Empezar aquí:** qué es EvA Airliner, flujo y URLs |
| `manual_piloto.md` | [`manual_piloto.md`](manual_piloto.md) | Uso del grabador y la cartilla |
| `arquitectura_eva.md` | [`arquitectura_eva.md`](arquitectura_eva.md) | Componentes y flujos |
| `especificacion_funcional.md` | [`especificacion_funcional.md`](especificacion_funcional.md) | Qué hace el producto, con marcas |
| `motor_evaluacion_v2.md` | [`motor_evaluacion_v2.md`](motor_evaluacion_v2.md) | Motor `evaluate_flight` |
| `criterios_vfr.md` | [`criterios_vfr.md`](criterios_vfr.md) | Criterios y umbrales |
| `formato_log_vuelo.md` | [`formato_log_vuelo.md`](formato_log_vuelo.md) | Esquema `FlightLog` |
| `esquema_pantallas.md` | [`esquema_pantallas.md`](esquema_pantallas.md) | Escritorio + web |
| `mapa_navegacion.yaml` | [`mapa_navegacion.yaml`](mapa_navegacion.yaml) | Rutas Flask reales |
| `MAPA_WEB_PARA_ENVIAR.md` | [`MAPA_WEB_PARA_ENVIAR.md`](MAPA_WEB_PARA_ENVIAR.md) | Mapa web para terceros |
| `traspaso_ui_web.md` | [`traspaso_ui_web.md`](traspaso_ui_web.md) | Tokens CSS y plantillas |
| `prueba_e2e_flujo_completo.md` | [`prueba_e2e_flujo_completo.md`](prueba_e2e_flujo_completo.md) | Tests existentes, no un E2E inventado |
| `auditoria_datos_home_cartilla.md` | [`auditoria_datos_home_cartilla.md`](auditoria_datos_home_cartilla.md) | De dónde salen los datos de cartilla |
| `espec_oc05_aerodromos_vfr.md` | [`espec_oc05_aerodromos_vfr.md`](espec_oc05_aerodromos_vfr.md) | Aeródromos ES + pistas de gestión |
| `bitacora_bugs.md` | [`bitacora_bugs.md`](bitacora_bugs.md) | No hay bitácora previa; deriva del código |
| `analisis_ahs_bender.md` | `[N/A]` | No hay análisis AHS-Bender en este repo |
| `auditoria_director_2026-08-16.md` | `[N/A]` | Acta de sesión de otro proyecto |
| `sesion_2026_08_16_resumen.md` | `[N/A]` | Idem |
| `handoff_oc05_opencode.md` | `[N/A]` | Idem |

## Ya existía en EvA (no sustituye a lo anterior)

| Fichero | Qué es |
|---|---|
| [`matriz_reglas.md`](matriz_reglas.md) / `.csv` | Trazabilidad de reglas (puede **desfasarse** respecto a `scoring.py`; ver motor) |
| [`limites_vne_vmo_mmo.csv`](limites_vne_vmo_mmo.csv) | Límites estructurales tabulados |
| [`limites_community_msfs.csv`](limites_community_msfs.csv) | Límites community MSFS |
| [`RENDER_SETUP_EMAIL.md`](RENDER_SETUP_EMAIL.md) | Correo en Render (SMTP bloqueado; Mailjet API) |
| `../DOCUMENTACION_PROYECTO.md` | Informe largo en la raíz. **No usarlo como fuente**: mezcla nombres y rutas que el código actual no coincide. Esta carpeta `docs/` manda. |

## Cómo leer esto para mantener el código

1. Esquema del log → `formato_log_vuelo.md` y `client/avcars/schema.py`.
2. Umbrales → `client/config/profiles.yaml` (nunca hardcodeados en el motor).
3. Veredicto → `client/avcars/evaluation/scoring.py` (`evaluate_flight`).
4. Cuentas y SQLite → `client/avcars/cuentas.py`.
5. HTTP → `web/app.py`.

Paquete Python del cliente: **`avcars`** (`client/avcars/`). `[CONF]`
