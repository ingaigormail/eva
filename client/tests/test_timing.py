"""Tests de la coordinación de tiempos.

No comprueban valores concretos (esos pueden cambiar), sino las **relaciones**
entre ellos, que son las que hacen que el sistema se comporte bien. Si alguien
ajusta un tiempo y rompe una de estas relaciones, salta aquí y no en un vuelo.
"""
import importlib

import pytest

from avcars import timing


def test_los_tiempos_son_coherentes_al_importar():
    """El módulo se valida a sí mismo al cargarse."""
    importlib.reload(timing)  # no debe lanzar


def test_detectar_datos_malos_es_mas_rapido_que_decidir_con_ellos():
    """La incoherencia que motivó centralizar los tiempos.

    Antes, los datos congelados se detectaban a los 8 s y un aterrizaje se
    confirmaba a los 5: la máquina decidía con datos que ya sabíamos malos.
    """
    detectar_congelado_s = timing.FROZEN_READS * timing.POLL_INTERVAL_S

    assert detectar_congelado_s <= timing.CONFIRM_LANDING_S
    assert detectar_congelado_s <= timing.CONFIRM_STOPPED_S


def test_las_confirmaciones_van_de_menos_a_mas_comprometido():
    """Cuanto más irreversible es la decisión, más tarda en tomarse."""
    assert timing.CONFIRM_LIFTOFF_S < timing.CONFIRM_LANDING_S
    assert timing.CONFIRM_LANDING_S < timing.CONFIRM_STOPPED_S


def test_el_umbral_de_pausa_deja_margen_sobre_la_cadencia():
    """Con el margen justo, la lentitud normal se contaría como pausa.

    Fue lo que pasó en la primera prueba real: consultas de 3,1 s con un
    umbral de 3 s produjeron 27 pausas inventadas.
    """
    assert timing.PAUSE_GAP_S >= 4 * timing.POLL_INTERVAL_S


def test_la_ventana_se_refresca_mas_rapido_que_el_muestreo():
    """Si no, el contador de tiempo avanzaría a saltos."""
    assert timing.UI_REFRESH_S < timing.POLL_INTERVAL_S


def test_en_crucero_se_guardan_menos_puntos_que_cerca_del_suelo():
    assert timing.SAMPLE_CRUISE_S > timing.SAMPLE_NEAR_GROUND_S


def test_no_se_muestrea_mas_rapido_de_lo_que_se_consulta():
    """Guardar más a menudo de lo que llegan datos solo duplicaría puntos."""
    assert timing.SAMPLE_NEAR_GROUND_S >= timing.POLL_INTERVAL_S


def test_el_volcado_no_pierde_medio_vuelo():
    assert timing.POLL_INTERVAL_S < timing.AUTOSAVE_INTERVAL_S <= 120.0


def test_una_pausa_sospechosa_dura_mas_que_una_normal():
    assert timing.PAUSE_SUSPICIOUS_S > timing.PAUSE_GAP_S


def test_la_validacion_detecta_una_combinacion_incoherente(monkeypatch):
    """La comprobación no es decorativa: falla de verdad."""
    monkeypatch.setattr(timing, "FROZEN_READS", 60)

    with pytest.raises(AssertionError, match="congelados"):
        timing._check_coherence()


def test_el_resumen_enumera_toda_la_cadena():
    texto = timing.resumen()

    for etiqueta in ("consulta al simulador", "confirmar aterrizaje", "umbral de pausa"):
        assert etiqueta in texto


# -- que los módulos usen los tiempos centralizados ---------------------


def test_la_maquina_de_estados_usa_los_tiempos_centralizados():
    from avcars.recorder import flight_state_machine as fsm

    assert fsm.DEFAULT_CONFIRMATION_LIFTOFF_S == timing.CONFIRM_LIFTOFF_S
    assert fsm.DEFAULT_CONFIRMATION_LANDING_S == timing.CONFIRM_LANDING_S
    assert fsm.DEFAULT_CONFIRMATION_STOPPED_S == timing.CONFIRM_STOPPED_S


def test_el_grabador_usa_los_tiempos_centralizados():
    from avcars.recorder import flight_log_writer as writer

    assert writer.PAUSE_GAP_S == timing.PAUSE_GAP_S
    assert writer.POLL_INTERVAL_S == timing.POLL_INTERVAL_S
    assert writer.SAMPLE_INTERVAL_CRUISE_S == timing.SAMPLE_CRUISE_S


def test_el_poller_usa_los_tiempos_centralizados():
    from avcars.connectors import sim_poller

    assert sim_poller.DEFAULT_INTERVAL_S == timing.POLL_INTERVAL_S
    assert sim_poller.FROZEN_THRESHOLD == timing.FROZEN_READS
