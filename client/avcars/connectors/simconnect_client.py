"""Conector para MSFS 2024 / MSFS 2020 / Prepar3D vía SimConnect.

Arquitectura Híbrida:
- LECTURA: fstelemetry (captura automática, configurable, CSV)
- ESCRITURA: Python-SimConnect directo (payload, control total)

Usa la librería `Python-SimConnect`, que habla con el SimConnect nativo del
simulador. No requiere instalar nada dentro del simulador (ni FSUIPC ni
plugins), en línea con el requisito de huella local mínima.

Sobre las unidades
------------------
SimConnect devuelve algunas variables en unidades poco intuitivas (radianes
para posición y actitud, pies/segundo para la velocidad vertical) y distintas
versiones de la librería normalizan cosas distintas. En vez de asumir, este
conector:

1. Guarda el valor crudo de cada variable en `SimState.raw`.
2. Aplica una conversión con heurística explícita (ver `_coerce_*`).

La interfaz muestra ambos valores en su panel de diagnóstico, de forma que
las unidades se validan mirando la pantalla mientras se vuela, sin consola.

Integración de fstelemetry
--------------------------
Para máxima captura de datos, fstelemetry se ejecuta como tool separado en CLI:
    fstelemetry --config client/config/fstelemetry.yaml

Esto genera CSV automáticamente con 50+ variables de MSFS.
D3 (Registro) lee este CSV para el informe final de vuelo.

Este conector (SimConnectConnector) maneja:
- LECTURA: todas las variables via Python-SimConnect
- ESCRITURA: PAYLOAD_STATION_WEIGHT (pasajeros/carga)
- FALLBACK: funciona sin fstelemetry (CSV opcional)
"""
from __future__ import annotations

import math
from typing import Any, Optional

from .base import SimConnector, SimState

LB_TO_KG = 0.45359237

# Nombre en nuestro modelo -> nombre de la variable en Python-SimConnect.
# Se consultan en este orden; el primero que devuelva un valor gana. Varias
# entradas por campo porque los nombres no son idénticos entre versiones de
# la librería ni entre MSFS 2020/2024 y Prepar3D.
VARIABLE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "lat": ("PLANE_LATITUDE",),
    "lon": ("PLANE_LONGITUDE",),
    "alt_msl_ft": ("PLANE_ALTITUDE", "INDICATED_ALTITUDE"),
    "alt_agl_ft": ("PLANE_ALT_ABOVE_GROUND",),
    "hdg_deg": ("PLANE_HEADING_DEGREES_TRUE",),
    "gs_kt": ("GROUND_VELOCITY",),
    "ias_kt": ("AIRSPEED_INDICATED",),
    "vs_fpm": ("VERTICAL_SPEED",),
    "on_ground": ("SIM_ON_GROUND",),
    # Si el simulador expone si está pausado, es la forma fiable de
    # distinguir una pausa de verdad de un problema de conexión: con ambas
    # cosas los datos dejan de cambiar. No todos los simuladores la ofrecen,
    # así que el resto del sistema funciona igual sin ella.
    "paused": ("SIM_PAUSED", "PAUSE_FLAG"),
    "fuel_lb": ("FUEL_TOTAL_QUANTITY_WEIGHT",),
    # Peso total del avión, en libras. Si el simulador no lo expone, el campo
    # queda a None y las reglas que dependen del peso no se evalúan (nunca se
    # sustituye por un valor supuesto).
    "total_weight_lb": ("TOTAL_WEIGHT",),
    "squawk": ("TRANSPONDER_CODE:1", "TRANSPONDER_CODE"),
    # Estado del transpondedor: 0 off, 1 standby, 2 test, 3 on, 4 alt (modo C).
    "transponder_state": ("TRANSPONDER_STATE:1", "TRANSPONDER_STATE"),
    "sim_rate": ("SIMULATION_RATE",),
    "bank_deg": ("PLANE_BANK_DEGREES",),
    "pitch_deg": ("PLANE_PITCH_DEGREES",),
    "gear_down": ("GEAR_HANDLE_POSITION", "GEAR_TOTAL_PCT_EXTENDED"),
    "flaps_pct": ("FLAPS_HANDLE_PERCENT",),
    "qnh_inhg": ("KOHLSMAN_SETTING_HG",),
    "stall_warning": ("STALL_WARNING",),
    "overspeed_warning": ("OVERSPEED_WARNING",),
    "autopilot_engaged": ("AUTOPILOT_MASTER",),
    # Luces: se pide primero la variable `..._ON`, que es la que dice si la
    # luz **está encendida**; `LIGHT_LANDING` y compañía son la posición del
    # interruptor ("Light switch state" en la tabla de python-SimConnect), que
    # no es lo mismo y en algunos aviones no coincide. Lo que se enseña y se
    # puntúa es si la luz luce, así que esa es la que manda; la del
    # interruptor se deja detrás como respaldo.
    "landing_light": ("LIGHT_LANDING_ON", "LIGHT_LANDING"),
    "beacon_light": ("LIGHT_BEACON_ON", "LIGHT_BEACON"),
    "nav_light": ("LIGHT_NAV_ON", "LIGHT_NAV"),
    "taxi_light": ("LIGHT_TAXI_ON", "LIGHT_TAXI"),
    "strobe_light": ("LIGHT_STROBE_ON", "LIGHT_STROBE"),
    # `BRAKE_PARKING_INDICATOR` es booleano; `..._POSITION` es una posición
    # (0..1 o 0..32767 según el avión), así que va detrás y solo como
    # respaldo — `_coerce_bool` la da por puesta con cualquier valor > 0.
    # Qué avión es. `ATC_MODEL` va primero porque es el **modelo** (C172),
    # que es contra lo que se comparan los límites del POH en
    # `aircraft.yaml`; `ATC_TYPE` da el fabricante y en el vuelo de pruebas
    # del 2026-08-25 devolvió "CESSNA", que no sirve para nada. `TITLE` es
    # el último recurso: el nombre largo del avión.
    "aircraft_type": ("ATC_MODEL", "ATC_TYPE", "TITLE"),
    "aircraft_registration": ("ATC_ID",),
    "parking_brake": ("BRAKE_PARKING_INDICATOR", "BRAKE_PARKING_POSITION"),
    # `GENERAL ENG COMBUSTION:index` es la variable de verdad de SimConnect.
    # `ENG_COMBUSTION` (sin índice) NO existe como tal: la librería la lista,
    # pero el simulador devuelve 0, que se tomaba como "motor apagado" y
    # cortaba la grabación de un avión con el motor en marcha (visto el
    # 2026-08-25, parado antes de entrar en pista con el freno puesto).
    # Se deja al final solo por si algún simulador la sirviera.
    "engine_running": (
        "GENERAL_ENG_COMBUSTION:1", "GENERAL_ENG_COMBUSTION:2", "ENG_COMBUSTION",
    ),
}


#: Variables que el simulador sí tiene pero que la tabla de
#: python-SimConnect no lista, así que su `find()` nunca las encuentra.
#: Formato de la tabla: nombre -> [descripción, variable, unidades, settable].
_VARIABLES_EXTRA = {
    # Modo del transpondedor: 0 apagado, 1 standby, 2 test, 3 on, 4 alt
    # (modo C). Es una variable normal de SimConnect, pero la librería solo
    # trae `TRANSPONDER CODE` y `TRANSPONDER AVAILABLE`, de modo que el modo
    # no llegaba nunca y el indicador se quedaba en "---".
    "TRANSPONDER_STATE:index": [
        "Transponder state", b"TRANSPONDER STATE:index", b"Enum", "Y",
    ],
}


def _registrar_variables_que_faltan(requests: Any) -> None:
    """Mete `_VARIABLES_EXTRA` en la tabla de la librería.

    `RequestHelper.__getattr__` resuelve los nombres contra un diccionario de
    su clase, así que basta con añadirlos ahí para que `find()` los
    encuentre. Se elige la clase que ya tiene el código de transpondedor,
    para dejarlas donde les corresponde.

    Nunca lanza: si la librería cambia por dentro y esto deja de encajar, se
    pierde el dato extra —que es justo lo que pasaba antes— pero el conector
    sigue funcionando igual.
    """
    try:
        for clase in requests.list:
            tabla = getattr(clase, "list", None)
            if isinstance(tabla, dict) and "TRANSPONDER_CODE:index" in tabla:
                tabla.update(_VARIABLES_EXTRA)
                return
    except Exception:  # noqa: BLE001 — un extra nunca puede tumbar el conector
        pass


class SimConnectNotAvailable(RuntimeError):
    """La librería SimConnect no está instalada o el simulador no responde."""


# Centinela para distinguir "aún no se ha probado este campo" de "se probó y
# el simulador no lo tiene" (que se guarda como None).
_NOT_TRIED = object()


def _coerce_angle_deg(value: Any) -> Optional[float]:
    """Convierte un ángulo de actitud (escora/cabeceo) a grados.

    SimConnect devuelve estos ángulos en radianes. Un valor cuyo módulo
    supera 2*pi no puede ser radianes en un avión que vuela normalmente, así
    que en ese caso asumimos que la librería ya lo dio en grados.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v):
        return None
    return v if abs(v) > 2 * math.pi else math.degrees(v)


def _coerce_latlon_deg(value: Any) -> Optional[float]:
    """Limpia una latitud/longitud que ya viene en grados.

    Python-SimConnect declara PLANE_LATITUDE/PLANE_LONGITUDE con unidad
    `Degrees` en su RequestList (versión 0.4.26) y SimConnect devuelve el
    valor en esa unidad, así que aquí no se convierte nada. Antes este
    heurístico multiplicaba por 180/pi cualquier valor menor que pi, lo que
    inflaba las longitudes de España (siempre en ±3 grados): una longitud
    real de -0.47 se grababa como -27.08.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _coerce_vs_fpm(value: Any) -> Optional[float]:
    """Limpia una velocidad vertical que ya viene en pies/minuto.

    Python-SimConnect declara VERTICAL_SPEED con unidad `feet/minute` en su
    RequestList (versión 0.4.26) y SimConnect devuelve el valor en esa
    unidad. Antes este heurístico multiplicaba por 60 los valores menores de
    200 asumiendo pies/segundo, lo que inflaba las VS pequeñas (nivelado,
    rodaje) hasta valores absurdos.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _coerce_texto(value: Any) -> Optional[str]:
    """Texto del simulador, en limpio.

    Llega como `bytes` y, en MSFS, a veces envuelto en una clave de
    traducción del estilo `TT:ATCCOM.AC_MODEL_C172.0.text`. De ahí se saca
    la parte útil (`C172`) porque es lo que las reglas comparan contra
    `aircraft.yaml`; si no encaja con ese formato se devuelve tal cual, sin
    inventar nada.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    texto = str(value).strip().strip("\x00").strip()
    if not texto:
        return None

    # MSFS envuelve estos textos de varias formas, no siempre con el
    # prefijo `TT:`. Vistas hasta ahora:
    #   TT:ATCCOM.AC_MODEL_C172.0.text   → C172
    #   ATCCOM.ATC_NAME CESSNA.0.text    → CESSNA   (separador espacio)
    # Se busca el trozo que lleva uno de los marcadores conocidos y se coge
    # lo que va detrás, sea cual sea el separador.
    if "ATCCOM." in texto.upper():
        for parte in texto.split("."):
            arriba = parte.upper()
            for marcador in ("AC_MODEL", "ATC_MODEL", "ATC_NAME", "AC_TYPE"):
                if arriba.startswith(marcador):
                    candidato = parte[len(marcador):].lstrip("_ ").strip()
                    if candidato:
                        return candidato
        return texto
    return texto


def _coerce_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    try:
        return bool(float(value))
    except (TypeError, ValueError):
        return None


def _coerce_qnh_inhg(value: Any) -> Optional[float]:
    """Limpia el QNH del altímetro, que ya viene en pulgadas de mercurio.

    `KOHLSMAN_SETTING_HG` declara unidad `inHg` en la RequestList de
    python-SimConnect, así que aquí no se convierte nada. Un QNH plausible
    anda entre ~28 y ~31 inHg.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _coerce_squawk(value: Any) -> str:
    """El transponder viene como BCD16: 0x1200 representa el código 1200."""
    if value is None:
        return ""
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return ""
    digits = [(raw >> shift) & 0xF for shift in (12, 8, 4, 0)]
    if all(d <= 7 for d in digits):
        return "".join(str(d) for d in digits)
    return str(raw)


class SimConnectConnector(SimConnector):
    """Lee el estado del avión desde MSFS/P3D a través de SimConnect."""

    def __init__(self) -> None:
        self._sm = None
        self._requests = None
        self._missing: list[str] = []
        # Qué candidato funcionó para cada campo. Sin esto, cada ciclo vuelve
        # a probar los nombres que no existen en este simulador, y cada
        # intento fallido cuesta tiempo: en la primera prueba real un ciclo
        # completo tardaba 3,1 segundos.
        self._resolved: dict[str, Optional[str]] = {}

    # -- ciclo de vida -------------------------------------------------

    def connect(self) -> None:
        try:
            from SimConnect import AircraftRequests, SimConnect
        except ImportError as exc:
            raise SimConnectNotAvailable(
                "Falta la librería SimConnect.\n\n"
                "Si estás ejecutando EvA desde el código, instálala con:\n"
                "    pip install SimConnect\n\n"
                "Si usas EvA.exe, esto no debería pasar: avísanos."
            ) from exc

        try:
            self._sm = SimConnect()
        except OSError as exc:
            # Falta SimConnect.dll o no se puede cargar: es un problema de
            # instalación, distinto de "el simulador no está abierto".
            raise SimConnectNotAvailable(
                "No se encuentra SimConnect en este equipo.\n\n"
                "SimConnect se instala junto con el simulador. Si tienes "
                "MSFS o Prepar3D instalado y sigue fallando, instala el "
                "SDK de SimConnect del simulador."
            ) from exc
        except Exception as exc:
            raise SimConnectNotAvailable(
                "No se pudo conectar con el simulador. Comprueba que está "
                "abierto y con un vuelo cargado."
            ) from exc

        # `_time` es la antigüedad máxima (ms) que aceptamos de un dato
        # cacheado. Se ajusta al ritmo al que consultamos (1 Hz): pedir datos
        # más frescos que eso solo consigue que cada lectura espere a que el
        # simulador responda, multiplicado por las veintitantas variables.
        self._requests = AircraftRequests(self._sm, _time=900)
        _registrar_variables_que_faltan(self._requests)
        self._resolved = {}

    def disconnect(self) -> None:
        if self._sm is not None:
            try:
                self._sm.exit()
            except Exception:
                pass
        self._sm = None
        self._requests = None

    @property
    def connected(self) -> bool:
        return self._requests is not None

    @property
    def missing_variables(self) -> list[str]:
        """Variables que el simulador no ha sabido darnos en el último poll."""
        return list(self._missing)

    def read_flight_plan(self):
        """Devuelve el plan de vuelo cargado en el simulador, si lo hay."""
        from .flight_plan import read_flight_plan

        return read_flight_plan(self._requests)

    #: Lo que pesa un pasajero con su equipaje de mano. Es el mismo número que
    #: usa `economia.yaml` para facturar por pasajero-milla: si aquí fuera otro,
    #: el avión volaría con un peso distinto del que se le cobra al piloto.
    KG_POR_PASAJERO = 85

    #: Fragmentos que identifican una estación de payload como
    #: equipaje/carga, no un asiento con alguien sentado. Buscar por nombre
    #: en vez de escribir en un índice fijo: los índices de
    #: `PAYLOAD_STATION_*` son 1..N y el orden lo decide cada avión.
    #: Escribir a ciegas (como hacía la versión anterior, con la estación 0
    #: fija -- que además ni siquiera existe: el SDK indexa desde 1)
    #: sustituía el peso del piloto por el de la carga en vez de sumarlo, o
    #: no escribía en ningún sitio real.
    #:
    #: Hay términos en inglés y en español a propósito: se comprobó en vivo
    #: (2026-08-31, C172 de EvA) que `PAYLOAD_STATION_NAME` puede devolver
    #: los nombres en el idioma del simulador -- no siempre en inglés como
    #: se suponía. Ese C172 en concreto los llama "Piloto", "Copiloto",
    #: "Pasajero izquierda/derecha" y "Cola 1"/"Cola 2" (las dos zonas de
    #: equipaje traseras de un C172 real): de ahí "cola", que si no
    #: encajaría poco con "carga".
    #: https://docs.flightsimulator.com/html/Programming_Tools/SimVars/Aircraft_SimVars/Aircraft_System_Variables.htm
    _NOMBRES_ESTACION_CARGA = (
        "baggage", "cargo", "freight",
        "equipaje", "maletero", "bodega", "cola",
    )

    def _leer_nombre_estacion(self, indice: int) -> str:
        """Lee `PAYLOAD STATION NAME:n` para una estación concreta.

        Python-SimConnect (comprobado en 0.4.26) registra
        `PAYLOAD_STATION_WEIGHT:index` bien indexado, pero **no**
        `PAYLOAD_STATION_NAME:index` -- solo la versión sin índice, que no
        sirve para leer una estación en concreto (se comprobó directamente
        en el código fuente de la librería, `RequestList.py`). Por eso esto
        no puede pasar por `self._requests.get(...)` como todo lo demás:
        construye la petición de bajo nivel a mano, con el nombre real de
        la variable de MSFS (con espacios, tal como lo indexa la propia
        librería por dentro al sustituir ``:index``).
        """
        from SimConnect import Request

        peticion = Request(
            (b"PAYLOAD STATION NAME:index", b"String"), self._sm, _settable=False
        )
        peticion.setIndex(indice)
        # Llega como `bytes` (p. ej. `b'Piloto'`): con `str()` a secas se
        # queda la representación literal, `"b'Piloto'"`, y no encaja con
        # nada. `_coerce_texto` es el mismo decodificador que ya se usa
        # para el resto de texto que da MSFS (modelo, matrícula...).
        return _coerce_texto(peticion.value) or ""

    def _estacion_de_carga(self) -> tuple[Optional[int], str]:
        """Busca la estación de equipaje/carga real de este avión.

        Recorre `PAYLOAD_STATION_COUNT` estaciones (1..N) mirando el nombre
        de cada una hasta encontrar una que suene a equipaje o carga. Si no
        hay ninguna -- un avión de terceros sin estaciones bien nombradas,
        por ejemplo -- se devuelve `(None, motivo)`: nunca se escribe a
        ciegas en una estación cualquiera, porque podría ser un asiento.

        Ojo con el nombre de la variable: la clave que acepta esta librería
        lleva guion bajo (`PAYLOAD_STATION_COUNT`), no espacios
        (`PAYLOAD STATION COUNT`, que es el nombre real de MSFS pero no la
        clave por la que la busca `AircraftRequests.find()` -- con espacios
        no la encuentra y `.get()` devuelve `None` en silencio, sin avisar
        de nada). Costó una tarde entera de pruebas en vivo encontrar esto
        (2026-08-31): con la clave equivocada, `total` salía siempre 0 y
        parecía que este avión no tenía ninguna estación.
        """
        try:
            total = int(self._requests.get("PAYLOAD_STATION_COUNT") or 0)
        except Exception:
            return None, "no se pudo leer las estaciones de carga de este avión"

        nombres_vistos = []
        for indice in range(1, total + 1):
            try:
                nombre = self._leer_nombre_estacion(indice)
            except Exception:
                continue
            nombres_vistos.append(nombre or f"#{indice}")
            if any(pista in nombre.lower() for pista in self._NOMBRES_ESTACION_CARGA):
                return indice, ""

        detalle = f" (estaciones: {', '.join(nombres_vistos)})" if nombres_vistos else ""
        return None, f"este avión no tiene una estación de equipaje/carga reconocible{detalle}"

    def set_payload(
        self,
        passengers: int = 0,
        cargo_kg: int = 0,
        fuel_pct: int = 100,
        *,
        combustible_util_kg: Optional[float] = None,
    ) -> dict:
        """Escribe carga y combustible en el simulador. Devuelve qué entró.

        **No promete nada.** Cada escritura se comprueba por separado y el
        resultado dice cuál funcionó, porque el piloto tiene que saber si el
        avión lleva de verdad lo que puso en el plan. La versión anterior
        devolvía `True` aunque fallaran las dos escrituras: la hoja decía
        «aplicado» y el avión salía vacío.

        `combustible_util_kg` es la capacidad del avión, de `aircraft.yaml`
        (bloque `despacho`). Sin ella no se toca el combustible: antes se usaba
        un `max_fuel_lb = 200` fijo que no es de ningún avión de la flota —
        un C172 lleva 144 kg y un CJ4 2.613, así que el porcentaje se aplicaba
        contra una cifra inventada.

        Devuelve `{"carga": bool, "combustible": bool|None, "carga_kg": float,
        "combustible_kg": float|None, "motivo": str}`. `combustible` es None
        cuando no se ha intentado.
        """
        resultado = {
            "carga": False,
            "combustible": None,
            "carga_kg": 0.0,
            "combustible_kg": None,
            "motivo": "",
        }

        if self._requests is None:
            resultado["motivo"] = "sin conexión con el simulador"
            return resultado

        carga_total_kg = passengers * self.KG_POR_PASAJERO + cargo_kg
        resultado["carga_kg"] = float(carga_total_kg)

        estacion, motivo_estacion = self._estacion_de_carga()
        if estacion is None:
            resultado["motivo"] = motivo_estacion
        else:
            try:
                # Mismo detalle que en `_estacion_de_carga`: la clave lleva
                # guion bajo (`PAYLOAD_STATION_WEIGHT:n`), no espacios. Y
                # esta librería no siempre avisa con una excepción cuando
                # una variable no se reconoce -- `set()` puede devolver
                # `False` en silencio (variable de solo lectura, o mal
                # escrita) sin lanzar nada, así que hay que mirar lo que
                # devuelve y no solo si ha explotado.
                escrito = self._requests.set(
                    f"PAYLOAD_STATION_WEIGHT:{estacion}", carga_total_kg / LB_TO_KG
                )
                if escrito:
                    resultado["carga"] = True
                else:
                    resultado["motivo"] = (
                        "el simulador no aceptó la escritura en la estación "
                        f"de carga #{estacion}"
                    )
            except Exception as exc:  # noqa: BLE001
                resultado["motivo"] = f"no se pudo escribir la carga: {exc}"

        # El combustible solo se toca si sabemos cuánto cabe en ESTE avión.
        if combustible_util_kg:
            kg = (max(0, min(100, fuel_pct)) / 100.0) * float(combustible_util_kg)
            resultado["combustible_kg"] = round(kg, 1)
            try:
                # `.set()` devuelve `False` (sin lanzar) si la librería no
                # reconoce la variable -- p. ej. un nombre mal escrito, o
                # un cambio en una versión nueva de Python-SimConnect. Eso
                # sí lo detecta este `if`. Lo que **no** detecta es una
                # variable reconocida pero de solo lectura de verdad en
                # MSFS (que es justo el caso normal de
                # `FUEL_TOTAL_QUANTITY_WEIGHT`): ahí `AircraftRequests.set`
                # devuelve `True` igualmente, aunque por dentro no escriba
                # nada -- una limitación de la librería, no algo que se
                # pueda arreglar desde aquí sin releer el valor después
                # para comprobarlo. No toca hoy: esta llamada no se hace
                # actualmente (`gui.py` nunca pasa `combustible_util_kg`).
                escrito = self._requests.set("FUEL_TOTAL_QUANTITY_WEIGHT", kg / LB_TO_KG)
                resultado["combustible"] = bool(escrito)
                if not escrito and not resultado["motivo"]:
                    resultado["motivo"] = "el simulador no reconoció la variable de combustible"
            except Exception as exc:  # noqa: BLE001
                # En MSFS esta variable suele ser de solo lectura. No es un
                # fallo del piloto ni de EvA: se dice y se sigue.
                resultado["combustible"] = False
                if not resultado["motivo"]:
                    resultado["motivo"] = f"el simulador no dejó fijar el combustible: {exc}"

        return resultado

    # -- lectura -------------------------------------------------------

    def _read(self, field: str) -> Any:
        """Devuelve el valor del campo, recordando qué variable lo dio.

        La primera vez se prueban todos los candidatos; a partir de ahí se
        consulta directamente el que funcionó. Los campos que no existen en
        este simulador se marcan y no se vuelven a pedir.
        """
        assert self._requests is not None

        resolved = self._resolved.get(field, _NOT_TRIED)

        if resolved is None:
            # Ya sabemos que este simulador no ofrece este dato.
            self._missing.append(field)
            return None

        if resolved is not _NOT_TRIED:
            try:
                return self._requests.get(resolved)
            except Exception:
                # La variable ha dejado de responder: se vuelve a buscar.
                self._resolved.pop(field, None)

        for name in VARIABLE_CANDIDATES[field]:
            try:
                value = self._requests.get(name)
            except Exception:
                continue
            if value is not None:
                self._resolved[field] = name
                return value

        self._resolved[field] = None
        self._missing.append(field)
        return None

    def poll(self) -> SimState:
        if self._requests is None:
            raise SimConnectNotAvailable("Llama a connect() antes de poll().")

        self._missing = []
        raw = {field: self._read(field) for field in VARIABLE_CANDIDATES}

        lat = _coerce_latlon_deg(raw["lat"])
        lon = _coerce_latlon_deg(raw["lon"])
        fuel_lb = raw["fuel_lb"]

        return SimState(
            lat=lat if lat is not None else 0.0,
            lon=lon if lon is not None else 0.0,
            alt_msl_ft=_as_float(raw["alt_msl_ft"]),
            alt_agl_ft=_as_float(raw["alt_agl_ft"]),
            hdg_deg=_coerce_heading_deg(raw["hdg_deg"]),
            gs_kt=_as_float(raw["gs_kt"]),
            ias_kt=_as_float(raw["ias_kt"]),
            vs_fpm=_coerce_vs_fpm(raw["vs_fpm"]) or 0.0,
            on_ground=bool(_coerce_bool(raw["on_ground"])),
            fuel_kg=_as_float(fuel_lb) * LB_TO_KG,
            total_weight_kg=_weight_kg(raw["total_weight_lb"]),
            squawk=_coerce_squawk(raw["squawk"]),
            sim_rate=_as_float(raw["sim_rate"], default=1.0),
            bank_deg=_coerce_angle_deg(raw["bank_deg"]),
            pitch_deg=_coerce_angle_deg(raw["pitch_deg"]),
            paused=_coerce_bool(raw["paused"]),
            transponder_state=_as_optional_int(raw["transponder_state"]),
            gear_down=_coerce_bool(raw["gear_down"]),
            flaps_pct=_as_optional_float(raw["flaps_pct"]),
            qnh_inhg=_coerce_qnh_inhg(raw["qnh_inhg"]),
            stall_warning=_coerce_bool(raw["stall_warning"]),
            overspeed_warning=_coerce_bool(raw["overspeed_warning"]),
            autopilot_engaged=_coerce_bool(raw["autopilot_engaged"]),
            landing_light=_coerce_bool(raw["landing_light"]),
            aircraft_type=_coerce_texto(raw["aircraft_type"]),
            aircraft_registration=_coerce_texto(raw["aircraft_registration"]),
            parking_brake=_coerce_bool(raw["parking_brake"]),
            engine_running=_coerce_bool(raw["engine_running"]),
            beacon_light=_coerce_bool(raw["beacon_light"]),
            nav_light=_coerce_bool(raw["nav_light"]),
            taxi_light=_coerce_bool(raw["taxi_light"]),
            strobe_light=_coerce_bool(raw["strobe_light"]),
            raw=raw,
        )


def _weight_kg(value: Any) -> float | None:
    """Convierte el peso total de libras a kilos.

    Devuelve None si el simulador no da el dato o si da un valor absurdo. Un
    peso erróneo es peor que la ausencia de peso: haría que se evaluase la
    velocidad de rotación contra una VR calculada para un avión que no es.
    """
    if value is None:
        return None
    try:
        lb = float(value)
    except (TypeError, ValueError):
        return None
    if lb <= 0:
        return None
    return round(lb * LB_TO_KG, 1)


def _coerce_heading_deg(value: Any) -> float:
    """El rumbo llega en radianes; lo devolvemos en grados 0-360."""
    deg = _coerce_angle_deg(value)
    if deg is None:
        return 0.0
    return deg % 360.0


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(v) else v


def _as_optional_int(value: Any) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_optional_float(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v
