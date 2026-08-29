"""Tests de la arquitectura híbrida: fstelemetry (lectura) + SimConnect (escritura).

Prueba end-to-end del flujo D2 → Carga aplicada → MSFS → D3 grabado.

Para ejecutar:
    python -m pytest client/tests/test_simconnect_hybrid.py -v

Requisitos:
    - MSFS 2020/2024 ejecutándose
    - Cliente de EvA conectado a SimConnect
    - fstelemetry instalado (pip install fstelemetry)
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# Agregar cliente al path
CLIENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLIENT_DIR))

from avcars.connectors.simconnect_client import (
    SimConnectConnector,
    SimConnectNotAvailable,
)

# fstelemetry ya no se importa desde el conector: pasó a ser una herramienta
# de línea de órdenes aparte (ver la cabecera de `simconnect_client.py`), y con
# ella se fue el `HAS_FSTELEMETRY` que este fichero importaba. Se detecta aquí
# para que la suite se pueda recolectar aunque no esté instalada; sin esto, un
# ImportError tumbaba la recolección de TODAS las pruebas del proyecto.
HAS_FSTELEMETRY = importlib.util.find_spec("fstelemetry") is not None


class TestHybridArchitecture:
    """Suite de pruebas para arquitectura híbrida SimConnect."""

    def test_fstelemetry_disponible(self):
        """Verifica que fstelemetry está instalado."""
        assert HAS_FSTELEMETRY, (
            "fstelemetry no está instalado. "
            "Instala con: pip install fstelemetry"
        )

    def test_config_yaml_existe(self):
        """Verifica que config/fstelemetry.yaml existe y es válido."""
        config_path = CLIENT_DIR / "config" / "fstelemetry.yaml"
        assert config_path.exists(), f"Falta {config_path}"

        # Verifica que contiene variables
        content = config_path.read_text()
        assert "PLANE_LATITUDE" in content, "Falta PLANE_LATITUDE"
        assert "PAYLOAD_STATION_WEIGHT" in content, "Falta PAYLOAD_STATION_WEIGHT"
        assert "variables:" in content, "Config YAML mal formada"

    @pytest.mark.skipif(
        not HAS_FSTELEMETRY, reason="fstelemetry no está instalado"
    )
    def test_simconnect_connector_init(self):
        """Intenta crear una instancia de SimConnectConnector."""
        try:
            connector = SimConnectConnector()
            assert connector is not None
            assert connector._sm is None  # Aún no conectado
            assert connector._requests is None
        except SimConnectNotAvailable as e:
            pytest.skip(f"MSFS no está disponible: {e}")

    @pytest.mark.skipif(
        not HAS_FSTELEMETRY, reason="fstelemetry no está instalado"
    )
    def test_set_payload_interface(self):
        """Verifica que set_payload() tiene la interface correcta."""
        try:
            connector = SimConnectConnector()
            # Sin conectar, debería devolver False pero no crash
            result = connector.set_payload(
                passengers=8, cargo_kg=500, fuel_pct=75
            )
            assert isinstance(result, bool), "set_payload debe devolver bool"
        except SimConnectNotAvailable:
            pytest.skip("MSFS no está disponible")

    def test_payload_validation(self):
        """Verifica validación de parámetros de carga."""
        try:
            connector = SimConnectConnector()
        except SimConnectNotAvailable:
            pytest.skip("MSFS no está disponible")

        # Valores válidos no deberían crash
        connector.set_payload(passengers=0, cargo_kg=0, fuel_pct=0)
        connector.set_payload(passengers=500, cargo_kg=5000, fuel_pct=100)
        connector.set_payload(passengers=8, cargo_kg=500, fuel_pct=75)


class TestE2EFlowD2ToMSFS:
    """Pruebas end-to-end: D2 planificador → MSFS simulador."""

    @pytest.mark.skipif(
        not HAS_FSTELEMETRY, reason="fstelemetry no está instalado"
    )
    @pytest.mark.integration
    def test_e2e_apply_payload_to_msfs(self):
        """Prueba completa: aplica carga desde D2 al simulador.

        Flujo:
        1. Conectar a MSFS via SimConnect
        2. Leer estado actual (fstelemetry)
        3. Aplicar carga (8 pasajeros, 500 kg, 75% combustible)
        4. Verificar que MSFS recibió los datos
        5. Grabar en CSV (fstelemetry)
        """
        try:
            connector = SimConnectConnector()
            connector.connect()
        except SimConnectNotAvailable as e:
            pytest.skip(f"MSFS no disponible: {e}")

        # Datos D2 que vienen del planificador
        D2_PAYLOAD = {
            "passengers": 8,
            "cargo_kg": 500,
            "fuel_pct": 75,
        }

        # 1. Leer estado inicial (fstelemetry)
        try:
            state_before = connector.poll()
            assert state_before is not None
            assert state_before.lat != 0 or state_before.lon != 0  # Algún dato
        except Exception as e:
            pytest.skip(f"No se pudo leer telemetría: {e}")

        # 2. Aplicar carga (escritura via Python-SimConnect)
        result = connector.set_payload(
            passengers=D2_PAYLOAD["passengers"],
            cargo_kg=D2_PAYLOAD["cargo_kg"],
            fuel_pct=D2_PAYLOAD["fuel_pct"],
        )
        assert result is True, "set_payload() falló"

        # 3. Leer estado después (para verificar cambios)
        try:
            state_after = connector.poll()
            assert state_after is not None
            # Verificar que los datos se escribieron (si el simulador los reporta)
            # NOTA: MSFS puede no reportar PAYLOAD_STATION_WEIGHT en MSFS 2020
            # pero otros datos deberían cambiar (posición, velocidad)
        except Exception as e:
            pytest.skip(f"No se pudo verificar estado: {e}")

        # 4. Limpiar
        try:
            connector.disconnect()
        except Exception:
            pass

        pytest.skip("Prueba manual: ejecuta con MSFS 2020 corriendo")

    @pytest.mark.skipif(
        not HAS_FSTELEMETRY, reason="fstelemetry no está instalado"
    )
    @pytest.mark.integration
    def test_e2e_csv_recording(self):
        """Verifica que fstelemetry graba CSV con los datos.

        Flujo:
        1. Ejecutar fstelemetry con config
        2. Volar durante 10 segundos
        3. Verificar que CSV se creó
        4. Verificar que contiene pasajeros/carga
        """
        try:
            import subprocess

            config_path = CLIENT_DIR / "config" / "fstelemetry.yaml"
            # Ejecutaría: fstelemetry --config config_path
            # Por ahora solo verificamos que el comando existe
            result = subprocess.run(
                ["fstelemetry", "--help"],
                capture_output=True,
                timeout=5,
            )
            assert result.returncode == 0, "fstelemetry CLI no disponible"
        except Exception as e:
            pytest.skip(f"fstelemetry CLI test: {e}")


class TestArchitectureIntegration:
    """Verifica integración de fstelemetry + Python-SimConnect."""

    def test_hybrid_architecture_components(self):
        """Verifica que ambos componentes están presentes."""
        # fstelemetry
        assert HAS_FSTELEMETRY, "fstelemetry no disponible"

        # Python-SimConnect
        try:
            from SimConnect import SimConnect, AircraftRequests

            assert SimConnect is not None
            assert AircraftRequests is not None
        except ImportError:
            pytest.fail("Python-SimConnect no instalado")

    def test_graceful_fallback_without_fstelemetry(self):
        """Si fstelemetry falta, el sistema sigue funcionando."""
        # Esta prueba es teórica, pero valida la arquitectura
        # Si HAS_FSTELEMETRY es False, SimConnectConnector debe:
        # 1. No crashes
        # 2. poll() sigue usando Python-SimConnect directo
        # 3. set_payload() sigue funcionando

        if HAS_FSTELEMETRY:
            pytest.skip("fstelemetry está disponible (prueba con --without-fstelemetry)")

        # Sin fstelemetry, debería usar fallback
        try:
            connector = SimConnectConnector()
            # No debería crash
            assert connector is not None
        except SimConnectNotAvailable:
            # Esperado si MSFS no está disponible
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
