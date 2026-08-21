"""Tests de la comprobación de requisitos.

La regla de negocio que se prueba: **solo la falta de permisos de escritura
impide instalar**. Todo lo demás avisa pero deja continuar, porque alguien
puede instalar EvA antes de tener el simulador.
"""
from pathlib import Path

from avcars import requisitos
from avcars.requisitos import (
    Nivel,
    Resultado,
    comprobar_escritura,
    comprobar_espacio,
    comprobar_todo,
    hay_problemas,
    resumen,
)


def test_escritura_correcta_es_ok(tmp_path):
    resultado = comprobar_escritura(tmp_path / "eva")

    assert resultado.nivel is Nivel.OK
    assert resultado.ok


def test_sin_permisos_de_escritura_es_problema(tmp_path, monkeypatch):
    def falla(*args, **kwargs):
        raise OSError("sin permisos")

    monkeypatch.setattr("pathlib.Path.touch", falla)

    resultado = comprobar_escritura(tmp_path / "eva")

    assert resultado.nivel is Nivel.PROBLEMA
    assert resultado.solucion  # se le dice al piloto qué hacer


def test_espacio_suficiente_es_ok(tmp_path):
    assert comprobar_espacio(tmp_path).nivel is Nivel.OK


def test_poco_espacio_es_aviso_no_problema(tmp_path, monkeypatch):
    class FakeUsage:
        free = 10 * 1024 * 1024  # 10 MB

    monkeypatch.setattr("shutil.disk_usage", lambda _p: FakeUsage())

    resultado = comprobar_espacio(tmp_path)

    assert resultado.nivel is Nivel.AVISO  # avisa, pero no bloquea


def test_espacio_en_carpeta_que_aun_no_existe(tmp_path):
    """Al instalar, la carpeta de destino todavía no existe."""
    resultado = comprobar_espacio(tmp_path / "no" / "existe" / "todavia")

    assert resultado.nivel in (Nivel.OK, Nivel.AVISO)


def test_sin_simulador_solo_avisa(monkeypatch):
    monkeypatch.setattr(requisitos, "detectar_simuladores", lambda: [])

    resultado = requisitos.comprobar_simulador()

    assert resultado.nivel is Nivel.AVISO
    assert "instalar EvA ahora" in (resultado.solucion or "")


def test_con_simulador_es_ok(monkeypatch):
    monkeypatch.setattr(requisitos, "detectar_simuladores", lambda: ["MSFS 2024"])

    assert requisitos.comprobar_simulador().nivel is Nivel.OK


def test_solo_los_problemas_bloquean():
    avisos = [
        Resultado("a", Nivel.OK, ""),
        Resultado("b", Nivel.AVISO, ""),
        Resultado("c", Nivel.AVISO, ""),
    ]
    assert not hay_problemas(avisos)

    con_problema = avisos + [Resultado("d", Nivel.PROBLEMA, "")]
    assert hay_problemas(con_problema)


def test_resumen_describe_la_situacion():
    todo_bien = [Resultado("a", Nivel.OK, "")]
    assert resumen(todo_bien) == "Todo listo"

    con_avisos = [Resultado("a", Nivel.AVISO, "")]
    assert "aviso" in resumen(con_avisos)

    con_problemas = [Resultado("a", Nivel.PROBLEMA, "")]
    assert "problema" in resumen(con_problemas)


def test_comprobar_todo_devuelve_todas_las_comprobaciones(tmp_path):
    resultados = comprobar_todo(tmp_path / "eva")

    nombres = {r.nombre for r in resultados}
    assert nombres == {
        "Sistema operativo",
        "Simulador",
        "SimConnect",
        "Espacio en disco",
        "Permisos de escritura",
    }


def test_ninguna_comprobacion_lanza_excepcion(tmp_path):
    """Un fallo comprobando requisitos no puede tumbar el instalador."""
    for resultado in comprobar_todo(Path("/ruta/imposible/xyz")):
        assert isinstance(resultado, Resultado)
        assert resultado.detalle
