"""Tests de `evaluation/reglas_config.py`: el estado editable en vivo de
las reglas (activo/inactivo, umbrales pisados sobre el perfil versionado)."""
from avcars.evaluation import reglas_config


def test_sin_fichero_todo_esta_activo_por_defecto(tmp_path):
    path = tmp_path / "no_existe.json"
    overrides = reglas_config.cargar_overrides(path)
    assert overrides == {"activo": {}, "umbral": {}}
    assert reglas_config.regla_activa("cualquiera", overrides) is True


def test_guardar_activo_persiste_y_se_relee(tmp_path):
    path = tmp_path / "reglas_config.json"
    reglas_config.guardar_activo("qnh", False, path)

    overrides = reglas_config.cargar_overrides(path)
    assert reglas_config.regla_activa("qnh", overrides) is False
    # Las demás siguen activas por defecto: desactivar una no apaga las otras.
    assert reglas_config.regla_activa("bank_angle", overrides) is True


def test_reactivar_una_regla(tmp_path):
    path = tmp_path / "reglas_config.json"
    reglas_config.guardar_activo("qnh", False, path)
    reglas_config.guardar_activo("qnh", True, path)

    overrides = reglas_config.cargar_overrides(path)
    assert reglas_config.regla_activa("qnh", overrides) is True


def test_valor_efectivo_sin_override_devuelve_el_del_perfil():
    perfil = {"runway_alignment_deg_max": 10, "bank_angle": {"fail_deg": 60}}
    overrides = {"activo": {}, "umbral": {}}

    assert reglas_config.valor_efectivo(perfil, "runway_alignment_deg_max", overrides) == 10
    assert reglas_config.valor_efectivo(perfil, "bank_angle.fail_deg", overrides) == 60


def test_guardar_umbral_pisa_el_valor_sin_tocar_el_perfil_base(tmp_path):
    path = tmp_path / "reglas_config.json"
    perfil_base = {"runway_alignment_deg_max": 10}

    reglas_config.guardar_umbral("runway_alignment_deg_max", 15, path)
    overrides = reglas_config.cargar_overrides(path)

    assert reglas_config.valor_efectivo(perfil_base, "runway_alignment_deg_max", overrides) == 15
    # El perfil base (lo que trae `profiles.yaml`) no se ha mutado.
    assert perfil_base["runway_alignment_deg_max"] == 10


def test_perfil_efectivo_aplica_overrides_sin_mutar_el_original(tmp_path):
    path = tmp_path / "reglas_config.json"
    perfil_base = {
        "runway_alignment_deg_max": 10,
        "bank_angle": {"warn_deg": 30, "fail_deg": 60},
    }
    reglas_config.guardar_umbral("bank_angle.fail_deg", 55, path)
    overrides = reglas_config.cargar_overrides(path)

    efectivo = reglas_config.perfil_efectivo(perfil_base, overrides)

    assert efectivo["bank_angle"]["fail_deg"] == 55
    assert efectivo["bank_angle"]["warn_deg"] == 30  # lo no tocado se conserva
    # El original, intacto: es el mismo dict que puede estar cacheado en
    # memoria (PROFILES en web/app.py) y se reutiliza en cada petición.
    assert perfil_base["bank_angle"]["fail_deg"] == 60


def test_quitar_override_umbral_vuelve_al_valor_original(tmp_path):
    path = tmp_path / "reglas_config.json"
    perfil_base = {"fuel_reserve_kg_min": 20}

    reglas_config.guardar_umbral("fuel_reserve_kg_min", 30, path)
    reglas_config.quitar_override_umbral("fuel_reserve_kg_min", path)

    overrides = reglas_config.cargar_overrides(path)
    assert reglas_config.valor_efectivo(perfil_base, "fuel_reserve_kg_min", overrides) == 20


def test_reglas_activas_dict_para_el_motor(tmp_path):
    path = tmp_path / "reglas_config.json"
    reglas_config.guardar_activo("stall_warning", False, path)
    overrides = reglas_config.cargar_overrides(path)

    activas = reglas_config.reglas_activas_dict(overrides)
    assert activas == {"stall_warning": False}
