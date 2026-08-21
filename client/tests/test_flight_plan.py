"""Tests del lector de plan de vuelo.

Se prueban con ficheros .PLN reales de MSFS (formato XML) escritos en un
directorio temporal, y con un objeto que imita a `AircraftRequests`.
"""
from avcars.connectors.flight_plan import (
    FlightPlanData,
    _clean_icao,
    parse_plan_file,
    read_from_simconnect,
)

PLN_MSFS = """<?xml version="1.0" encoding="UTF-8"?>
<SimBase.Document Type="AceXML" version="1,0">
    <FlightPlan.FlightPlan>
        <Title>LEMD to LEBL</Title>
        <FPType>VFR</FPType>
        <CruisingAlt>8500</CruisingAlt>
        <DepartureID>LEMD</DepartureID>
        <DepartureLLA>N40 28' 20\",W3 33' 39\",+002000.00</DepartureLLA>
        <DestinationID>LEBL</DestinationID>
        <DestinationLLA>N41 17' 49\",E2 4' 42\",+000012.00</DestinationLLA>
        <Descr>LEMD, LEBL</Descr>
        <ATCWaypoint id="LEMD">
            <ATCWaypointType>Airport</ATCWaypointType>
        </ATCWaypoint>
    </FlightPlan.FlightPlan>
</SimBase.Document>
"""


class FakeRequests:
    """Imita a AircraftRequests devolviendo un diccionario fijo."""

    def __init__(self, values: dict) -> None:
        self.values = values

    def get(self, name: str):
        if name not in self.values:
            raise KeyError(name)
        return self.values[name]


def test_lee_salida_y_llegada_de_un_pln(tmp_path):
    path = tmp_path / "CustomFlight.PLN"
    path.write_text(PLN_MSFS, encoding="utf-8")

    plan = parse_plan_file(path)

    assert plan.departure_icao == "LEMD"
    assert plan.arrival_icao == "LEBL"
    assert plan.cruise_altitude_ft == 8500
    assert plan.has_route


def test_un_fichero_corrupto_no_rompe(tmp_path):
    path = tmp_path / "CustomFlight.PLN"
    path.write_text("esto no es xml <<<", encoding="utf-8")

    plan = parse_plan_file(path)

    assert plan.departure_icao is None
    assert not plan.has_route


def test_lee_matricula_y_modelo_de_simconnect():
    requests = FakeRequests(
        {
            "GPS_APPROACH_AIRPORT_ID": "LEBL",
            "ATC_ID": "EC-ABC",
            "ATC_FLIGHT_NUMBER": "101",
            "ATC_MODEL": "C172",
        }
    )

    plan = read_from_simconnect(requests)

    assert plan.arrival_icao == "LEBL"
    assert plan.registration == "EC-ABC"
    assert plan.flight_number == "101"
    assert plan.aircraft_type == "C172"


def test_simconnect_sin_datos_no_inventa():
    plan = read_from_simconnect(FakeRequests({}))

    assert plan.arrival_icao is None
    assert plan.registration is None
    assert not plan.has_route


def test_valores_en_bytes_se_decodifican():
    requests = FakeRequests({"ATC_ID": b"EC-XYZ"})
    plan = read_from_simconnect(requests)

    assert plan.registration == "EC-XYZ"


def test_limpieza_de_icao():
    assert _clean_icao("  lemd ") == "LEMD"
    assert _clean_icao("LEBL") == "LEBL"
    assert _clean_icao("") is None
    assert _clean_icao(None) is None
    assert _clean_icao("no-es-un-icao") is None


def test_flight_plan_vacio_no_tiene_ruta():
    assert not FlightPlanData().has_route
