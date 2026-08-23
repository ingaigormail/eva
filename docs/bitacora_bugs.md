# Bitácora de defectos conocidos — EvA

> Equivalente de `bitacora_bugs.md`. **No había** bitácora en
> `D:\proyectos\eva\docs` antes de este documento. Lo siguiente sale de
> código y comentarios, no de un tracker. `[CONF]`

No hay Issues de GitHub volcados aquí. `[PEND]` lista de tickets remotos.

## Abiertos (evidencia en código)

| ID local | Qué | Dónde |
|---|---|---|
| XP-01 | `XPlaneUDPConnector.poll` → `NotImplementedError`; solo `receive_raw` verificado | `connectors/xplane_udp.py` |
| SEC-01 | Hash de traza no es firma; se puede recalcular tras editar | `importacion.py`, `integrity.py` |
| SEC-02 | Cuenta semilla `pruebas`/`pruebas` admin | `cuentas.py` |
| OPS-01 | Puerto 5000 (`app.py`/`wsgi.py`) vs 8000 (`nginx_eva.conf`) | despliegue |
| OPS-02 | No hay `eva.service` en `despliegue/` | árbol git |
| DOC-01 | `reglas_info.py` / `matriz_reglas.md` pueden usar **ids distintos** a `RULE_SCOPE` | evaluación vs docs antiguas |
| DOC-02 | `DOCUMENTACION_PROYECTO.md` desactualizado | raíz |
| DAT-01 | V-speeds `null` en `aircraft.yaml` → no se evalúa estructural | `config.py` / scoring |
| DAT-02 | Sin polígono de pista → no hay `runway_excursion` | airports.json |
| INT-01 | Prefile no confirma Submit en red | `prefile.py` |
| INT-02 | Sin cable a eva-dispatcher | ausencia de imports |
| UI-01 | HSTS siempre en `security.py` (molesto en HTTP local) | `security.py` |
| MOD-01 | `airliner/` es otro producto, roadmap no hecho | `airliner/README.md` |
| CSV-01 | CSV sin dueño ni evaluation completa | `importacion.py`, comentarios `vuelos_resumen` |

## Cerrado / mitigado en código (no reabrir sin leer)

- Tiempos incoherentes grabador: centralizados en `timing.py` con asserts.
- JSON de usuarios concurrente: migrado a SQLite WAL.
- SMTP en Render: documentado Mailjet (`RENDER_SETUP_EMAIL.md`).
- Nombres de fichero con `/`: sanitizado en writer y `nombre_seguro`.

## Cómo añadir una fila

Solo con fallo reproducible o comentario `TODO`/`FIXME` en el repo. No
pegar bugs de Airhispania.
