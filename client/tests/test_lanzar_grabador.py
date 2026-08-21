"""El botón de VUELO lanza EVA Airliner, y solo uno.

No se abre ninguna ventana: se prueba el método suelto, con un `Popen` de
mentira. Lo que importa es que dos pulsaciones no dejen dos grabadores
escribiendo el mismo vuelo.
"""
import sys
from pathlib import Path

import pytest

from avcars import dashboard


class PopenFalso:
    """Se comporta como el proceso del grabador: vivo hasta que muere."""

    def __init__(self, cmd, cwd=None):
        self.cmd = cmd
        self.cwd = cwd
        self.vivo = True

    def poll(self):
        return None if self.vivo else 0


class PanelDePruebas:
    """Lo mínimo de DashboardApp para poder llamar al método real."""

    def __init__(self):
        self.root = None
        self._grabador = None
        self.avisos = []

    _start_recording = dashboard.DashboardApp._start_recording


@pytest.fixture
def panel(monkeypatch):
    p = PanelDePruebas()
    monkeypatch.setattr(
        dashboard.messagebox, "showinfo", lambda *a, **k: p.avisos.append(a)
    )
    monkeypatch.setattr(
        dashboard.messagebox, "showerror", lambda *a, **k: p.avisos.append(a)
    )
    return p


def test_lanza_el_grabador_con_el_python_actual(panel, monkeypatch):
    lanzados = []

    def falso_popen(cmd, cwd=None):
        lanzados.append((cmd, cwd))
        return PopenFalso(cmd, cwd)

    monkeypatch.setattr(dashboard.subprocess, "Popen", falso_popen)
    panel._start_recording()

    assert len(lanzados) == 1
    cmd, cwd = lanzados[0]
    assert cmd == [sys.executable, "-m", "client.avcars.gui"]
    # Se lanza desde la raíz del repo, que es donde ese módulo resuelve.
    assert (Path(cwd) / "client" / "avcars" / "gui.py").exists()


def test_pulsar_dos_veces_no_abre_dos_grabadores(panel, monkeypatch):
    lanzados = []
    monkeypatch.setattr(
        dashboard.subprocess,
        "Popen",
        lambda cmd, cwd=None: (lanzados.append(cmd), PopenFalso(cmd, cwd))[1],
    )

    panel._start_recording()
    panel._start_recording()

    assert len(lanzados) == 1
    assert panel.avisos, "hay que avisar de que ya está abierto, no callarse"


def test_si_el_grabador_se_cerro_se_puede_volver_a_lanzar(panel, monkeypatch):
    lanzados = []
    monkeypatch.setattr(
        dashboard.subprocess,
        "Popen",
        lambda cmd, cwd=None: (lanzados.append(cmd), PopenFalso(cmd, cwd))[1],
    )

    panel._start_recording()
    panel._grabador.vivo = False  # el piloto lo cerró
    panel._start_recording()

    assert len(lanzados) == 2


def test_si_no_arranca_se_dice_no_se_traga_el_fallo(panel, monkeypatch):
    def revienta(cmd, cwd=None):
        raise OSError("no se encuentra Python")

    monkeypatch.setattr(dashboard.subprocess, "Popen", revienta)
    panel._start_recording()

    assert panel.avisos, "un fallo al lanzar tiene que verse"
    assert panel._grabador is None
