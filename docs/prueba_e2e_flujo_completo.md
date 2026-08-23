# Pruebas y flujo completo — EvA

> Equivalente de `prueba_e2e_flujo_completo.md`. **No** se ha inventado un
> E2E Selenium que el repo no tenga. Esto lista lo que **sí** hay en pytest
> y el flujo manual que el código permite.

## 1. Flujo funcional de extremo a extremo `[CONF]` (diseño)

```
1. Alta: /solicitar-alta → admin /gestion/usuarios
2. Login: /login  (o dashboard.py)
3. Plan: /plan → POST /api/plan/guardar
4. (opcional) POST /api/plan/vatsim-url  → el piloto envía en VATSIM
5. Grabar: gui.py → .avlog.json
6. Subir: POST /api/registro/upload
7. Ver: /vuelo/<nombre>  (mismo evaluate_flight)
8. Flota: /aerolinea
```

Paso 5 en X-Plane **no** está cerrado (`poll` no implementado). `[CONF]`

No hay en el árbol un script que ejecute 1–8 contra un simulador real de
forma automática. `[CONF]` por ausencia. Sí hay
`client/tests/test_regresion_vuelo_real.py` con **fixtures** de vuelo.

## 2. Tests automáticos presentes `[CONF]`

### Cliente `client/tests/`

`test_scoring.py`, `test_planes.py`, `test_correo.py`, `test_xplane_udp.py`,
`test_vpilot.py`, `test_timing.py`, `test_solicitudes.py`,
`test_simconnect_hybrid.py`, `test_simconnect_client.py`,
`test_sim_poller.py`, `test_settings.py`, `test_restablecer.py`,
`test_requisitos.py`, `test_regresion_vuelo_real.py`,
`test_recuperacion.py`, `test_prefile.py`, `test_paths.py`,
`test_lanzar_grabador.py`, `test_integridad.py`, `test_importacion.py`,
`test_incidencias.py`, `test_flight_plan.py`,
`test_flight_state_machine.py`, `test_estadisticas.py`,
`test_flight_log_writer.py`, `test_debuglog.py`, `test_data_quality.py`,
`test_cuentas.py`.

### Web `web/test_*.py`

`test_app.py`, `test_vuelta_espana.py`, `test_lanzar_vuelo.py`,
`test_descargar.py`, `test_planes_web.py`, `test_gestion_vuelos.py`,
`test_gestion_usuarios.py`, `test_estadisticas_web.py`,
`test_cuentas_web.py`, `test_borrar_vuelo_propio.py`,
`test_fase1_seguridad.py`, `test_despacho_pesos.py`.

Cómo correrlos: no hay un único `Makefile` visto en esta pasada. `[PEND]`
comando canónico de CI. Típico: `pytest` desde `client/` y `web/` con
`PYTHONPATH` incluyendo `client/`. `[INF]`

## 3. Checklist manual (operación)

- [ ] Login `pruebas` solo en entorno de desarrollo.
- [ ] Subir un `.avlog.json` propio → 200; repetir → rechazo duplicado.
- [ ] Subir log de otro `license_id` → rechazo.
- [ ] Nombre de fichero con `../` → 400.
- [ ] `/api/vuelo/lanzar` en servidor público no debe abrir procesos ajenos
      (`puede_lanzar_vuelo` / loopback).
- [ ] CSRF: POST sin token debe fallar.
- [ ] Perfil easy/normal/hard cambia umbral de aprobado.

## 4. Lo que Airhispania documentaba y aquí no aplica `[N/A]`

Acta E2E de una fecha concreta de Airhispania, capturas de su UI, y
criterios de su motor v2 distinto.
