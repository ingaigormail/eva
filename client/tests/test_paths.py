"""Tests de las rutas de la aplicación.

La regla que se prueba aquí: **nunca perder una grabación por no poder
escribir donde tocaba**. Si la carpeta preferida no sirve, hay que caer a
otra en vez de fallar.
"""
from pathlib import Path

from avcars import paths


def test_carpeta_escribible_se_detecta(tmp_path):
    assert paths.is_writable(tmp_path)


def test_carpeta_no_escribible_se_detecta(tmp_path, monkeypatch):
    def falla(*args, **kwargs):
        raise OSError("sin permisos")

    monkeypatch.setattr("pathlib.Path.touch", falla)

    assert not paths.is_writable(tmp_path)


def test_se_usa_la_carpeta_preferida_si_sirve(tmp_path):
    preferida = tmp_path / "mis_vuelos"

    resultado = paths.recordings_dir(str(preferida))

    assert resultado == preferida
    assert resultado.exists()


def test_se_cae_a_la_del_ejecutable_si_la_preferida_no_sirve(tmp_path, monkeypatch):
    """Si la carpeta elegida no admite escritura, no se pierde el vuelo."""
    junto_al_exe = tmp_path / "instalacion"
    monkeypatch.setattr(paths, "base_dir", lambda: junto_al_exe)

    real_is_writable = paths.is_writable

    def solo_falla_la_preferida(directory: Path) -> bool:
        if "no_sirve" in str(directory):
            return False
        return real_is_writable(directory)

    monkeypatch.setattr(paths, "is_writable", solo_falla_la_preferida)

    resultado = paths.recordings_dir("/carpeta/no_sirve")

    assert resultado == junto_al_exe / paths.RECORDINGS_DIRNAME


def test_la_carpeta_se_crea_si_no_existe(tmp_path):
    destino = tmp_path / "nueva" / "grabaciones"
    assert not destino.exists()

    paths.recordings_dir(str(destino))

    assert destino.exists()


def test_espacio_libre_devuelve_un_numero(tmp_path):
    libre = paths.free_space_mb(tmp_path)

    assert libre is not None
    assert libre > 0


def test_espacio_libre_de_ruta_invalida_devuelve_none():
    assert paths.free_space_mb(Path("/esta/ruta/no/existe/en/ningun/sitio")) is None


def test_nombres_en_minuscula():
    """La especificación pide eva.exe y grabaciones/ en minúscula."""
    assert paths.RECORDINGS_DIRNAME == "grabaciones"
    assert paths.SETTINGS_FILENAME == "eva.config.json"
