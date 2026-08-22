# AVCARS Client

Cliente de escritorio (V1) de la aerolínea virtual: graba el vuelo conectando
con el simulador y evalúa el log resultante contra los criterios VFR.

La documentación de referencia (fuente de verdad) vive en `../docs/`:

- `../docs/criterios_vfr.md` - reglas de evaluación y modelo de puntuación.
- `../docs/formato_log_vuelo.md` - esquema del fichero de log de vuelo.

## Estado actual (sprint 1: arquitectura + motor de evaluación)

Implementado y verificado:

- `avcars/schema.py` - modelos del fichero de log (`FlightLog` y afines).
- `avcars/config.py` - carga de perfiles de dificultad (`config/profiles.yaml`).
- `avcars/evaluation/scoring.py` - motor de evaluación (100 puntos, penalizaciones,
  fallos automáticos).
- `avcars/cli.py` - comando `avcars evaluate <fichero.json>`.

## Estado del conector X-Plane (sprint 2)

- `avcars/connectors/xplane_udp.py` - la capa de transporte (decodificar el
  paquete UDP "DATA" de X-Plane) está implementada y probada, incluida una
  prueba con un socket real en loopback (`tests/test_xplane_udp.py`).
- El mapeo semántico (qué grupo UDP es velocidad/actitud/posición) usa la
  convención más citada por la comunidad, pero **no se ha podido verificar
  contra un X-Plane real** en este entorno (no hay simulador disponible
  aquí). Por eso `poll()` lanza `NotImplementedError` a propósito: falta
  confirmarlo con Igor delante de X-Plane antes de darlo por bueno.

Pendiente para el próximo sprint (no implementado todavía, ver `CONTEXT.md`):

- Verificar el mapeo de grupos UDP de X-Plane contra el simulador real y
  completar `XPlaneUDPConnector.poll()`.
- `avcars/connectors/simconnect_client.py` - conexión real a MSFS 2024/P3D
  (necesita comprobarse aparte: hay dudas sin resolver en la comunidad sobre
  si la librería `Python-SimConnect` funciona en MSFS 2024).
- `avcars/recorder/flight_log_writer.py` - grabación en vivo del log
  (muestreo adaptativo + detección de eventos), depende de los conectores.
- Reglas de `criterios_vfr.md` que necesitan ampliar el esquema del log:
  desviación de ruta, altitud semicircular, velocidad <10.000 ft, squawk
  asignado, pista planificada, excursión de pista, overspeed estructural.
- Overlay en pantalla con feedback instantáneo al touchdown (idea tomada de
  herramientas de flightsim.to como Arc/Rate My Landing/Landing Toast).
- Verificación automática de red (VATSIM/IVAO) cruzando el vuelo contra sus
  feeds públicos, en vez de un checkbox manual del piloto (V2, necesita backend).

## Uso

```bash
pip install -e ".[dev]"

# Evaluar un log de vuelo ya grabado
avcars evaluate tests/fixtures/sample_flight_pass.json --profile normal

# Tests
pytest
```
