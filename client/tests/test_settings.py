"""Tests de las preferencias de la aplicación.

Lo importante aquí no es que guarde y lea bien (que también), sino que
**ningún fichero de configuración roto impida arrancar EvA**.
"""
import json

from avcars.settings import MODO_AUTOMATICO, MODO_MANUAL, Settings, load, save


def test_fichero_inexistente_da_valores_por_defecto(tmp_path):
    settings = load(tmp_path / "no_existe.json")

    assert settings.modo == MODO_AUTOMATICO
    assert settings.segundos_confirmacion_aterrizaje == 5.0


def test_json_corrupto_no_rompe(tmp_path):
    path = tmp_path / "eva.config.json"
    path.write_text("{esto no es json", encoding="utf-8")

    settings = load(path)

    assert settings.modo == MODO_AUTOMATICO


def test_json_que_no_es_un_objeto_no_rompe(tmp_path):
    path = tmp_path / "eva.config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    assert load(path).modo == MODO_AUTOMATICO


def test_campos_desconocidos_se_ignoran(tmp_path):
    path = tmp_path / "eva.config.json"
    path.write_text(
        json.dumps({"modo": "manual", "campo_inventado": 42}), encoding="utf-8"
    )

    settings = load(path)

    assert settings.modo == MODO_MANUAL
    assert not hasattr(settings, "campo_inventado")


def test_modo_invalido_cae_a_automatico(tmp_path):
    path = tmp_path / "eva.config.json"
    path.write_text(json.dumps({"modo": "telepatico"}), encoding="utf-8")

    assert load(path).modo == MODO_AUTOMATICO


def test_valores_fuera_de_rango_se_corrigen(tmp_path):
    path = tmp_path / "eva.config.json"
    path.write_text(
        json.dumps(
            {
                "segundos_confirmacion_aterrizaje": -5,
                "segundos_confirmacion_parada": 99999,
                "intervalo_autoguardado_s": "no es un número",
            }
        ),
        encoding="utf-8",
    )

    settings = load(path)

    assert settings.segundos_confirmacion_aterrizaje == 1.0   # mínimo
    assert settings.segundos_confirmacion_parada == 300.0     # máximo
    assert settings.intervalo_autoguardado_s == 30.0          # por defecto


def test_ida_y_vuelta(tmp_path):
    path = tmp_path / "eva.config.json"
    original = Settings(modo=MODO_MANUAL, indicativo="avh100", salida="lemd")

    assert save(original, path)
    recuperado = load(path)

    assert recuperado.modo == MODO_MANUAL
    assert recuperado.indicativo == "AVH100"  # normalizado a mayúsculas
    assert recuperado.salida == "LEMD"


def test_guardar_no_deja_el_fichero_a_medias(tmp_path):
    path = tmp_path / "eva.config.json"
    save(Settings(indicativo="PRIMERO"), path)
    save(Settings(indicativo="SEGUNDO"), path)

    # El fichero tiene que ser JSON válido tras varias escrituras.
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["indicativo"] == "SEGUNDO"
    assert not list(tmp_path.glob("*.tmp"))  # sin restos temporales


def test_guardar_en_carpeta_sin_permisos_devuelve_false(tmp_path, monkeypatch):
    def falla(*args, **kwargs):
        raise OSError("sin permisos")

    monkeypatch.setattr("pathlib.Path.write_text", falla)

    assert save(Settings(), tmp_path / "eva.config.json") is False


def test_indicativo_se_recorta_y_normaliza(tmp_path):
    settings = Settings(indicativo="  avh100xxxxxxxxxxxxxxxxxxxx  ")
    settings.normalizar()

    assert settings.indicativo == "AVH100XXXXXXXXXX"
    assert len(settings.indicativo) <= 16
