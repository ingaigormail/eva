"""Pruebas de Fase 1 de Seguridad: auditoría append-only.

Fase 1 confía en el hash que escribió el cliente, no lo valida en servidor.
La seguridad está en la auditoría: quién subió qué, cuándo y desde dónde.
"""
import json
from pathlib import Path

import pytest

from avcars.integrity import track_hash
from avcars.schema import TrackPoint
import importacion


def crear_avlog(license_id=None, track_points=None, incluir_hash=True):
    """Helper: crea un AVLOG JSON válido."""
    if track_points is None:
        track_points = [
            {
                "t": 0.0,
                "lat": 40.0,
                "lon": -3.0,
                "alt_agl_ft": 1000,
                "alt_msl_ft": 2000,
                "hdg_deg": 180.0,
                "gs_kt": 100.0,
                "ias_kt": 95.0,
                "vs_fpm": 0.0,
                "on_ground": False,
            }
        ]

    # Calcular el hash real
    try:
        traza = [TrackPoint.model_validate(p) for p in track_points]
        hash_calculado = track_hash(traza)
    except Exception:
        hash_calculado = "HASH_ERROR"

    datos = {
        "pilot": {"license_id": license_id, "callsign": "TST1"} if license_id else {},
        "track": track_points,
    }

    if incluir_hash:
        datos["integrity"] = {"track_hash": hash_calculado}

    return json.dumps(datos).encode("utf-8")


class TestFase1Seguridad:
    """Tests de Fase 1: Auditoría de importación en append-only log."""

    def test_avlog_con_hash_valido_pasa(self):
        """Un AVLOG con integrity.track_hash se acepta (confía en el cliente)."""
        contenido = crear_avlog(license_id="PILOTO1", incluir_hash=True)
        nombre, huella = importacion.revisar(contenido, "test.avlog.json", "PILOTO1")
        assert nombre == "test.avlog.json"
        assert len(huella) == 64

    def test_avlog_sin_hash_calcula_uno(self):
        """Un AVLOG sin integrity.track_hash se calcula uno en servidor."""
        contenido = crear_avlog(license_id="PILOTO1", incluir_hash=False)
        nombre, huella = importacion.revisar(contenido, "test.avlog.json", "PILOTO1")
        assert nombre == "test.avlog.json"
        assert len(huella) == 64

    def test_avlog_con_hash_falso_sigue_pasando(self):
        """Un AVLOG con hash falso sigue pasando (confía en el cliente)."""
        datos = json.dumps(
            {
                "pilot": {"license_id": "PILOTO1"},
                "track": [
                    {
                        "t": 0.0,
                        "lat": 40.0,
                        "lon": -3.0,
                        "alt_agl_ft": 1000,
                        "alt_msl_ft": 2000,
                        "hdg_deg": 180.0,
                        "gs_kt": 100.0,
                        "ias_kt": 95.0,
                        "vs_fpm": 0.0,
                        "on_ground": False,
                    }
                ],
                "integrity": {"track_hash": "HASH_FALSO_INVENTADO"},
            }
        ).encode("utf-8")

        nombre, huella = importacion.revisar(datos, "test.avlog.json", "PILOTO1")
        assert huella == "HASH_FALSO_INVENTADO"
        assert nombre == "test.avlog.json"

    def test_ownership_se_rechaza_igual(self):
        """Fallo de ownership sigue rechazándose con 403."""
        datos = json.dumps(
            {
                "pilot": {"license_id": "OTRO99"},
                "track": [],
                "integrity": {"track_hash": "algo"},
            }
        ).encode("utf-8")

        with pytest.raises(importacion.ImportacionRechazada) as exc_info:
            importacion.revisar(datos, "test.avlog.json", "PILOTO1")

        assert exc_info.value.codigo == 403

class TestVueloCompleto:
    """Regla 3 de `importacion.revisar`: solo entran vuelos que llegaron al
    destino declarado en el plan (2026-08-23, a raíz de bajar el umbral de
    grabación automática al rodaje — ver `flight_state_machine.RODANDO`)."""

    AEROPUERTOS = {
        "LEMD": {"lat": 40.4719, "lon": -3.5626, "name": "Madrid-Barajas"},
        "LEBL": {"lat": 41.2971, "lon": 2.0785, "name": "Barcelona-El Prat"},
    }

    def _avlog(self, destino, ultimo_punto):
        track_points = [
            {
                "t": 0.0, "lat": 40.0, "lon": -3.0, "alt_agl_ft": 1000,
                "alt_msl_ft": 2000, "hdg_deg": 180.0, "gs_kt": 100.0,
                "ias_kt": 95.0, "vs_fpm": 0.0, "on_ground": False,
            },
            ultimo_punto,
        ]
        datos = {
            "pilot": {"license_id": "PILOTO1", "callsign": "TST1"},
            "flight_plan": {"arrival_icao": destino},
            "track": track_points,
            "integrity": {"track_hash": "h-completo"},
        }
        return json.dumps(datos).encode("utf-8")

    def test_llega_cerca_del_destino_se_acepta(self):
        ultimo = {
            "t": 3600.0, "lat": 41.2971, "lon": 2.0785, "alt_agl_ft": 0,
            "alt_msl_ft": 10, "hdg_deg": 90.0, "gs_kt": 5.0, "ias_kt": 5.0,
            "vs_fpm": 0.0, "on_ground": True,
        }
        nombre, _ = importacion.revisar(
            self._avlog("LEBL", ultimo), "test.avlog.json", "PILOTO1",
            aeropuertos=self.AEROPUERTOS,
        )
        assert nombre == "test.avlog.json"

    def test_se_queda_a_medio_camino_se_rechaza(self):
        ultimo = {
            "t": 1800.0, "lat": 40.8, "lon": -1.0, "alt_agl_ft": 5000,
            "alt_msl_ft": 6000, "hdg_deg": 90.0, "gs_kt": 200.0, "ias_kt": 190.0,
            "vs_fpm": 0.0, "on_ground": False,
        }
        with pytest.raises(importacion.ImportacionRechazada) as exc_info:
            importacion.revisar(
                self._avlog("LEBL", ultimo), "test.avlog.json", "PILOTO1",
                aeropuertos=self.AEROPUERTOS,
            )
        assert exc_info.value.codigo == 400
        assert "LEBL" in exc_info.value.mensaje

    def test_solo_rodo_sin_despegar_se_rechaza(self):
        """El caso que motivó la regla: grabar solo el rodaje para ver luces."""
        ultimo = {
            "t": 120.0, "lat": 40.472, "lon": -3.561, "alt_agl_ft": 0,
            "alt_msl_ft": 2000, "hdg_deg": 90.0, "gs_kt": 8.0, "ias_kt": 8.0,
            "vs_fpm": 0.0, "on_ground": True,
        }
        with pytest.raises(importacion.ImportacionRechazada):
            importacion.revisar(
                self._avlog("LEBL", ultimo), "test.avlog.json", "PILOTO1",
                aeropuertos=self.AEROPUERTOS,
            )

    def test_sin_aeropuertos_se_omite_la_comprobacion(self):
        """Sin pasar `aeropuertos` (compatibilidad), la regla 3 no se aplica."""
        ultimo = {
            "t": 120.0, "lat": 40.472, "lon": -3.561, "alt_agl_ft": 0,
            "alt_msl_ft": 2000, "hdg_deg": 90.0, "gs_kt": 8.0, "ias_kt": 8.0,
            "vs_fpm": 0.0, "on_ground": True,
        }
        nombre, _ = importacion.revisar(
            self._avlog("LEBL", ultimo), "test.avlog.json", "PILOTO1"
        )
        assert nombre == "test.avlog.json"


class TestAuditarImportacion:
    def test_auditar_importacion_escribe_log(self, tmp_path):
        """auditar_importacion() escribe en trusted_log.json."""
        import importacion

        old_path = importacion.TRUSTED_LOG_PATH
        try:
            importacion.TRUSTED_LOG_PATH = tmp_path / "trusted_log.json"

            importacion.auditar_importacion(
                huella="abc123def456",
                piloto="PILOTO1",
                nombre_fichero="test.avlog.json",
                ip_cliente="192.168.1.100",
            )

            assert importacion.TRUSTED_LOG_PATH.exists()
            contenido = json.loads(importacion.TRUSTED_LOG_PATH.read_text())
            assert isinstance(contenido, list)
            assert len(contenido) == 1
            assert contenido[0]["piloto"] == "PILOTO1"
            assert contenido[0]["ip_cliente"] == "192.168.1.100"
            assert "timestamp_utc" in contenido[0]
        finally:
            importacion.TRUSTED_LOG_PATH = old_path

    def test_auditar_importacion_append_only(self, tmp_path):
        """auditar_importacion() nunca sobrescribe, solo append."""
        import importacion

        old_path = importacion.TRUSTED_LOG_PATH
        try:
            importacion.TRUSTED_LOG_PATH = tmp_path / "trusted_log.json"

            importacion.auditar_importacion(
                huella="huella1",
                piloto="PILOTO1",
                nombre_fichero="vuelo1.avlog.json",
                ip_cliente="10.0.0.1",
            )

            importacion.auditar_importacion(
                huella="huella2",
                piloto="PILOTO2",
                nombre_fichero="vuelo2.avlog.json",
                ip_cliente="10.0.0.2",
            )

            contenido = json.loads(importacion.TRUSTED_LOG_PATH.read_text())
            assert len(contenido) == 2
            assert contenido[0]["huella"] == "huella1"
            assert contenido[1]["huella"] == "huella2"
        finally:
            importacion.TRUSTED_LOG_PATH = old_path

    def test_auditar_importacion_nunca_rompe_subida(self, tmp_path):
        """Si auditar falla, no debe romper la subida (fail-safe)."""
        import importacion

        old_path = importacion.TRUSTED_LOG_PATH
        try:
            importacion.TRUSTED_LOG_PATH = Path("/dev/null/imposible/trusted_log.json")

            importacion.auditar_importacion(
                huella="abc123",
                piloto="PILOTO1",
                nombre_fichero="test.avlog.json",
                ip_cliente="1.1.1.1",
            )
        finally:
            importacion.TRUSTED_LOG_PATH = old_path
