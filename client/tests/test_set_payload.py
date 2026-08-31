"""Tests de la escritura de carga al simulador.

No hace falta MSFS: se le pone al conector un `_requests` de mentira y se mira
qué escribe y qué contesta. Lo que se protege aquí es que **no vuelva a decir
que aplicó la carga cuando no la aplicó**: la versión anterior devolvía `True`
aunque fallaran las dos escrituras, así que la hoja de vuelo decía «aplicado»
y el avión salía vacío.

También se protege que la carga vaya a una estación real de equipaje/carga
y no a un índice fijo: la versión anterior escribía siempre en
`PAYLOAD STATION WEIGHT:0`, que ni siquiera existe (el SDK de MSFS indexa
las estaciones desde 1, "PAYLOAD STATION COUNT" documenta "1 to 15") y que
en el C172 de base habría sustituido el peso del piloto por el de la carga
si hubiera existido.

Y, descubierto el 2026-08-31 leyendo el código fuente de Python-SimConnect
en vivo: la clave que acepta esta librería lleva guion bajo
(`PAYLOAD_STATION_COUNT`, `PAYLOAD_STATION_WEIGHT:n`), no espacios -- con
espacios `AircraftRequests.find()` no la encuentra y `.get()`/`.set()`
devuelven `None`/`False` en silencio, sin lanzar nada. `RequestsFalso` usa
esas claves con guion bajo a propósito, para que un test que use la clave
equivocada (con espacios) falle aquí en vez de fallar en vivo con MSFS
abierto de verdad.
"""
import pytest

from avcars.config import load_aircraft, load_economia
from avcars.connectors.simconnect_client import SimConnectConnector

LB_A_KG = 0.45359237


class RequestsFalso:
    """Anota lo que se le escribe.

    `falla_en` hace que esas variables *lancen* al escribirlas (un fallo de
    verdad, de conexión). `no_reconocidas` simula lo que hace de verdad
    Python-SimConnect con una variable que no reconoce: `.set()` devuelve
    `False` *sin* lanzar nada -- justo el caso que costó encontrar hoy.
    """

    def __init__(self, falla_en=(), no_reconocidas=(), total_estaciones=2):
        self.escrito = {}
        self.falla_en = set(falla_en)
        self.no_reconocidas = set(no_reconocidas)
        self.total_estaciones = total_estaciones

    def set(self, nombre, valor):
        if nombre in self.falla_en:
            raise RuntimeError("variable de solo lectura")
        if nombre in self.no_reconocidas:
            return False
        self.escrito[nombre] = valor
        return True

    def get(self, nombre):
        if nombre == "PAYLOAD_STATION_COUNT":
            return self.total_estaciones
        return None


def _conector(
    falla_en=(), no_reconocidas=(), estaciones=("Pilot", "Baggage"), monkeypatch=None
) -> SimConnectConnector:
    """Conector con `_requests` de mentira y los nombres de estación fijados.

    `PAYLOAD_STATION_NAME:n` no se puede simular vía `_requests` (el código
    real lo lee por debajo con un objeto `Request` de la librería, no con
    `self._requests.get(...)` -- ver el comentario en
    `SimConnectConnector._leer_nombre_estacion`), así que aquí se sustituye
    directamente ese método por uno que devuelve `estaciones[indice - 1]`,
    estación 1 primero (como el SDK real). Por defecto trae un "Pilot" en
    la 1 y un "Baggage" en la 2: es justo el caso que antes se rompía
    (escribir en la 0/1 sin mirar el nombre habría tocado al piloto, no al
    equipaje).
    """
    c = SimConnectConnector()
    c._requests = RequestsFalso(
        falla_en, no_reconocidas, total_estaciones=len(estaciones)
    )

    def _nombre_falso(indice: int) -> str:
        if 1 <= indice <= len(estaciones):
            return estaciones[indice - 1]
        return ""

    if monkeypatch is not None:
        monkeypatch.setattr(c, "_leer_nombre_estacion", _nombre_falso)
    else:
        c._leer_nombre_estacion = _nombre_falso  # type: ignore[method-assign]
    return c


# -- lo que se escribe -------------------------------------------------


def test_la_carga_se_escribe_en_libras():
    c = _conector()

    r = c.set_payload(passengers=4, cargo_kg=100)

    esperado_kg = 4 * SimConnectConnector.KG_POR_PASAJERO + 100
    assert r["carga"] is True
    assert r["carga_kg"] == esperado_kg
    # Estación 2 con el fixture por defecto ("Pilot", "Baggage"): es la que
    # se llama "Baggage", no la primera que hay.
    assert c._requests.escrito["PAYLOAD_STATION_WEIGHT:2"] == pytest.approx(
        esperado_kg / LB_A_KG
    )


def test_el_pasajero_pesa_lo_mismo_que_en_la_economia():
    """Si no coincidieran, el avión volaría con un peso y se cobraría otro."""
    economia = load_economia()

    # `economia.yaml` documenta los 85 kg en el comentario de tarifa_kg_nm;
    # el valor vivo es el del conector, y ambos tienen que ser el mismo.
    assert SimConnectConnector.KG_POR_PASAJERO == 85
    assert economia["ingresos"]["tarifa_pasajero_nm"] > 0


def test_el_combustible_usa_la_capacidad_real_del_avion():
    """Antes se aplicaba el porcentaje sobre 200 lb fijas, que no es de nadie."""
    c = _conector()
    util = load_aircraft()["C172"]["despacho"]["combustible_util_kg"]

    r = c.set_payload(fuel_pct=50, combustible_util_kg=util)

    assert r["combustible_kg"] == pytest.approx(util * 0.5, abs=0.1)
    assert c._requests.escrito["FUEL_TOTAL_QUANTITY_WEIGHT"] == pytest.approx(
        util * 0.5 / LB_A_KG, rel=1e-3
    )


def test_sin_capacidad_no_se_toca_el_combustible():
    c = _conector()

    r = c.set_payload(passengers=2, fuel_pct=75)

    assert r["combustible"] is None
    assert "FUEL_TOTAL_QUANTITY_WEIGHT" not in c._requests.escrito


def test_el_porcentaje_de_combustible_se_recorta_al_rango():
    c = _conector()

    assert c.set_payload(fuel_pct=500, combustible_util_kg=100)["combustible_kg"] == 100
    assert c.set_payload(fuel_pct=-20, combustible_util_kg=100)["combustible_kg"] == 0


# -- lo que NO se promete ----------------------------------------------


def test_sin_conexion_no_dice_que_aplico_nada():
    c = SimConnectConnector()  # sin `_requests`

    r = c.set_payload(passengers=4)

    assert r["carga"] is False
    assert "simulador" in r["motivo"]


def test_si_falla_la_carga_lo_dice():
    c = _conector(falla_en={"PAYLOAD_STATION_WEIGHT:2"})

    r = c.set_payload(passengers=4)

    assert r["carga"] is False
    assert r["motivo"]


def test_si_la_libreria_no_reconoce_la_variable_lo_dice():
    """`.set()` puede devolver `False` sin lanzar nada -- no basta con
    fijarse en si ha habido una excepción (ver el docstring del módulo)."""
    c = _conector(no_reconocidas={"PAYLOAD_STATION_WEIGHT:2"})

    r = c.set_payload(passengers=4)

    assert r["carga"] is False
    assert r["motivo"]


def test_que_el_combustible_falle_no_invalida_la_carga():
    """En MSFS el combustible suele ser de solo lectura; la carga sí entra."""
    c = _conector(falla_en={"FUEL_TOTAL_QUANTITY_WEIGHT"})

    r = c.set_payload(passengers=4, fuel_pct=50, combustible_util_kg=144)

    assert r["carga"] is True
    assert r["combustible"] is False
    assert r["motivo"]


# -- qué estación se usa -------------------------------------------------


def test_busca_la_estacion_de_equipaje_y_no_la_primera_que_encuentra():
    """Avión con varios asientos antes del maletero: no debe tocar ninguno."""
    c = _conector(estaciones=("Pilot", "Co-Pilot", "Row 2 Passenger", "Baggage"))

    r = c.set_payload(passengers=2, cargo_kg=20)

    assert r["carga"] is True
    assert "PAYLOAD_STATION_WEIGHT:4" in c._requests.escrito
    assert "PAYLOAD_STATION_WEIGHT:1" not in c._requests.escrito
    assert "PAYLOAD_STATION_WEIGHT:2" not in c._requests.escrito
    assert "PAYLOAD_STATION_WEIGHT:3" not in c._requests.escrito


def test_reconoce_cargo_ademas_de_baggage():
    """Un avión de carga no llama "Baggage" a su bodega, sino "Cargo"."""
    c = _conector(estaciones=("Pilot", "Cargo Bay 1"))

    r = c.set_payload(cargo_kg=200)

    assert r["carga"] is True
    assert "PAYLOAD_STATION_WEIGHT:2" in c._requests.escrito


def test_la_busqueda_de_nombre_no_distingue_mayusculas():
    c = _conector(estaciones=("Pilot", "BAGGAGE"))

    r = c.set_payload(cargo_kg=50)

    assert r["carga"] is True
    assert "PAYLOAD_STATION_WEIGHT:2" in c._requests.escrito


def test_sin_estacion_de_carga_reconocible_no_escribe_en_ningun_asiento():
    """Sin un "Baggage"/"Cargo" claro, mejor no aplicar nada que sentar la
    carga encima del piloto o de un pasajero."""
    c = _conector(estaciones=("Pilot", "Co-Pilot"))

    r = c.set_payload(passengers=2, cargo_kg=20)

    assert r["carga"] is False
    assert "equipaje" in r["motivo"] or "carga" in r["motivo"]
    assert not any(k.startswith("PAYLOAD_STATION_WEIGHT") for k in c._requests.escrito)


def test_reconoce_los_nombres_en_espanol_del_c172_real():
    """Nombres vistos en vivo el 2026-08-31 en el C172 de EvA: MSFS los
    devolvió en español, no en inglés como se había supuesto al principio.
    "Cola 1"/"Cola 2" son las dos zonas de equipaje traseras."""
    c = _conector(estaciones=(
        "Piloto", "Copiloto", "Pasajero izquierda", "Pasajero derecha",
        "Cola 1", "Cola 2",
    ))

    r = c.set_payload(passengers=2, cargo_kg=30)

    assert r["carga"] is True
    # La primera estación de carga real es "Cola 1", índice 5.
    assert "PAYLOAD_STATION_WEIGHT:5" in c._requests.escrito


def test_el_motivo_lista_las_estaciones_vistas_para_poder_depurar():
    c = _conector(estaciones=("Pilot", "Co-Pilot"))

    r = c.set_payload(cargo_kg=20)

    assert "Pilot" in r["motivo"]
    assert "Co-Pilot" in r["motivo"]
