"""El Home de la aerolínea: agregados reales sobre `vuelos_resumen`.

No se reconstruye `FlightLog` completo para cada prueba: `registrar_avlog`
solo toca un puñado de campos, así que se prueban con dobles mínimos
(`SimpleNamespace`) en vez de acoplar el test a todo el esquema.
"""
from types import SimpleNamespace

import pytest

from avcars import cuentas, estadisticas


@pytest.fixture
def almacen_tmp(tmp_path):
    original = cuentas.USUARIOS_PATH
    cuentas.configurar_almacen(tmp_path / "usuarios.json")
    yield
    cuentas.configurar_almacen(original)


def _vuelo(license_id="EVA321", origen="LEMD", destino="LEIB", aeronave="C172",
           distancia_nm=180, duracion_min=95):
    return SimpleNamespace(
        pilot=SimpleNamespace(license_id=license_id, callsign=license_id),
        flight_plan=SimpleNamespace(
            departure_icao=origen, arrival_icao=destino, aircraft_icao_type=aeronave,
            aircraft_registration="EC-ABC", rules="VFR", network="VATSIM",
            atc_controlled=True,
        ),
        summary=SimpleNamespace(
            total_distance_nm=distancia_nm, flight_time_min=duracion_min,
            fuel_used_kg=12.5, fuel_remaining_kg=40.0,
        ),
    )


def _verdict(passed=True, evaluable=True, reglas_falladas=None, score=85):
    reglas_falladas = reglas_falladas or []
    items = [SimpleNamespace(rule=r, passed=False) for r in reglas_falladas]
    return SimpleNamespace(passed=passed, evaluable=evaluable, items=items, score=score)


# -- registrar_avlog -------------------------------------------------------


def test_registra_un_vuelo_apto(almacen_tmp):
    estadisticas.registrar_avlog("h1", _vuelo(), _verdict(passed=True), fecha="2026-08-01")

    kpis = estadisticas.kpis_globales()
    assert kpis["total_vuelos"] == 1
    assert kpis["pct_apto"] == 100.0
    assert kpis["pct_no_evaluable"] == 0.0


def test_un_vuelo_no_evaluable_no_cuenta_como_apto_ni_como_no_apto(almacen_tmp):
    estadisticas.registrar_avlog(
        "h1", _vuelo(), _verdict(passed=False, evaluable=False), fecha="2026-08-01"
    )
    kpis = estadisticas.kpis_globales()
    assert kpis["pct_no_evaluable"] == 100.0
    assert kpis["pct_apto"] == 0.0


def test_el_mismo_vuelo_no_se_cuenta_dos_veces(almacen_tmp):
    """La huella es la clave: reimportar el mismo vuelo no duplica la fila."""
    estadisticas.registrar_avlog("h1", _vuelo(), _verdict(), fecha="2026-08-01")
    estadisticas.registrar_avlog("h1", _vuelo(), _verdict(), fecha="2026-08-01")

    assert estadisticas.kpis_globales()["total_vuelos"] == 1


def test_las_incidencias_falladas_quedan_guardadas(almacen_tmp):
    estadisticas.registrar_avlog(
        "h1", _vuelo(), _verdict(passed=False, reglas_falladas=["descenso_brusco"]),
        fecha="2026-08-01",
    )
    incidencias = estadisticas.incidencia_mas_frecuente()
    assert incidencias == [{"regla": "descenso_brusco", "vuelos": 1, "pct": 100.0}]


# -- registrar_csv -----------------------------------------------------


def test_un_csv_no_tiene_calidad_pero_cuenta_en_los_totales(almacen_tmp):
    estadisticas.registrar_csv(
        "h-csv", "EVA321", distancia_nm=50, duracion_min=30, fecha="2026-08-01"
    )
    kpis = estadisticas.kpis_globales()
    assert kpis["total_vuelos"] == 1
    # Sin evaluar: no entra en el % de aptos ni de no evaluables.
    assert kpis["vuelos_evaluados"] == 0
    assert kpis["pct_apto"] is None


# -- rankings ------------------------------------------------------------


def test_top_pilotos_por_actividad(almacen_tmp):
    for i in range(3):
        estadisticas.registrar_avlog(f"a{i}", _vuelo("EVA111"), _verdict(), fecha="2026-08-01")
    estadisticas.registrar_avlog("b0", _vuelo("EVA222"), _verdict(), fecha="2026-08-01")

    top = estadisticas.top_pilotos_actividad()
    assert top[0]["license_id"] == "EVA111"
    assert top[0]["vuelos"] == 3
    assert top[1]["license_id"] == "EVA222"


def test_top_pilotos_por_calidad_exige_un_minimo_de_vuelos(almacen_tmp):
    # Un piloto con un solo vuelo perfecto: no debe ganar por eso.
    estadisticas.registrar_avlog("solo1", _vuelo("SUERTUDO"), _verdict(passed=True), fecha="2026-08-01")

    # Otro con más vuelos, algo peor de media, pero por encima del mínimo.
    for i in range(5):
        estadisticas.registrar_avlog(
            f"m{i}", _vuelo("CONSTANTE"), _verdict(passed=(i < 4)), fecha="2026-08-01"
        )

    top = estadisticas.top_pilotos_calidad(minimo_vuelos=5)
    assert [p["license_id"] for p in top] == ["CONSTANTE"]
    assert top[0]["pct_apto"] == 80.0


def test_top_rutas_y_top_aeropuertos(almacen_tmp):
    estadisticas.registrar_avlog("r1", _vuelo(origen="LEMD", destino="LEIB"), _verdict(), fecha="2026-08-01")
    estadisticas.registrar_avlog("r2", _vuelo(origen="LEMD", destino="LEIB"), _verdict(), fecha="2026-08-02")
    estadisticas.registrar_avlog("r3", _vuelo(origen="LEIB", destino="LEBL"), _verdict(), fecha="2026-08-03")

    rutas = estadisticas.top_rutas()
    assert rutas[0]["origen"] == "LEMD" and rutas[0]["destino"] == "LEIB"
    assert rutas[0]["vuelos"] == 2

    aeropuertos = {a["icao"]: a for a in estadisticas.top_aeropuertos()}
    assert aeropuertos["LEIB"]["operaciones"] == 3  # 2 llegadas + 1 salida
    assert aeropuertos["LEMD"]["salidas"] == 2


def test_actividad_mensual_agrupa_y_ordena_por_fecha(almacen_tmp):
    estadisticas.registrar_avlog("e1", _vuelo(), _verdict(), fecha="2026-07-15")
    estadisticas.registrar_avlog("e2", _vuelo(), _verdict(), fecha="2026-08-01")
    estadisticas.registrar_avlog("e3", _vuelo(), _verdict(), fecha="2026-08-15")

    meses = estadisticas.actividad_mensual()
    assert [m["mes"] for m in meses] == ["2026-07", "2026-08"]
    assert meses[1]["vuelos"] == 2


def test_se_guardan_los_datos_que_ya_grababa_el_cliente_y_se_tiraban(almacen_tmp):
    """Combustible, matrícula, red, reglas, control ATC y puntuación real."""
    estadisticas.registrar_avlog(
        "h1", _vuelo(), _verdict(passed=True, score=91), perfil="normal", fecha="2026-08-01"
    )
    with cuentas.conexion() as con:
        fila = dict(con.execute("SELECT * FROM vuelos_resumen WHERE huella = 'h1'").fetchone())

    assert fila["matricula"] == "EC-ABC"
    assert fila["reglas"] == "VFR"
    assert fila["red"] == "VATSIM"
    assert fila["control_atc"] == 1
    assert fila["combustible_usado_kg"] == 12.5
    assert fila["combustible_restante_kg"] == 40.0
    assert fila["puntuacion"] == 91
    assert fila["perfil_evaluacion"] == "normal"


def test_un_vuelo_no_evaluable_no_guarda_puntuacion(almacen_tmp):
    """Un score sin significado (NO EVALUABLE) no se guarda como si valiera."""
    estadisticas.registrar_avlog(
        "h1", _vuelo(), _verdict(evaluable=False, score=0), fecha="2026-08-01"
    )
    with cuentas.conexion() as con:
        fila = dict(con.execute("SELECT * FROM vuelos_resumen WHERE huella = 'h1'").fetchone())
    assert fila["puntuacion"] is None


def test_sin_ningun_vuelo_los_agregados_no_revientan(almacen_tmp):
    assert estadisticas.kpis_globales()["total_vuelos"] == 0
    assert estadisticas.top_pilotos_actividad() == []
    assert estadisticas.top_pilotos_calidad() == []
    assert estadisticas.top_rutas() == []
    assert estadisticas.top_aeropuertos() == []
    assert estadisticas.actividad_mensual() == []
    assert estadisticas.incidencia_mas_frecuente() == []
