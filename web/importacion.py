"""Control de qué vuelos entran en la cartilla y de quién son.

Tres reglas:

1. **Un vuelo no se importa dos veces.** Ni renombrando el fichero.
   (2026-08-17)
2. **Un vuelo no lo importa otro piloto.** El vuelo dice de quién es.
   (2026-08-17)
3. **Solo entran vuelos completos**: que aterrizaron cerca del aeródromo de
   destino declarado en el plan. (2026-08-23, a raíz de bajar el umbral de
   grabación automática al rodaje: sin esto, cualquier rodaje grabado para
   verificar luces —sin despegar siquiera— contaría igual que un vuelo de
   verdad). Un vuelo incompleto no se sube ni a la cartilla ni a
   estadísticas: no deja ni rastro, se puede reintentar sin más. Entre los
   completos, además, solo los aprobados cuentan para estadísticas — los
   suspensos sí quedan en la cartilla (ver `_resumir_para_estadisticas` en
   `app.py`).

Cómo se reconoce un vuelo
-------------------------
Por su **huella**, no por el nombre del fichero, que cualquiera cambia:

- `.avlog.json`: el `integrity.track_hash` que el grabador ya escribe. Cubre
  solo la traza, que es el dato bruto y no vuelve a tocarse; sobrevive a que
  el fichero se reescriba o se le añada la evaluación. Si el fichero no lo
  trae, se recalcula sobre su traza.
- `.csv`: la telemetría de fstelemetry no lleva ni piloto ni hash, así que se
  usa el SHA-256 del contenido. Detecta el mismo fichero subido dos veces,
  pero no el mismo vuelo reexportado.

Hasta dónde protege
-------------------
Contra equivocaciones y contra subir el vuelo de otro por descuido: sí. Contra
alguien decidido, **no**. `avcars/integrity.py` ya lo dice de su hash: no es
una firma, y quien tenga el cliente delante puede recalcularlo sobre una traza
retocada, o cambiar el `license_id` del fichero antes de subirlo. Cerrar eso
es la decisión SEC-03 de `docs/especificacion_funcional.md`, todavía abierta.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

#: Junto a `usuarios.json`, que es el otro dato compartido de la cartilla.
REGISTRO_PATH = Path(__file__).resolve().parent / "data" / "importados.json"

#: Nombres de fichero aceptables. Se comprueba el nombre ya despojado de
#: carpetas: sin esto, un `..\..\algo.avlog.json` escribiría fuera de sitio.
NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9 ._-]+$")


class ImportacionRechazada(Exception):
    """El vuelo no puede entrar, con el motivo ya redactado para el piloto."""

    def __init__(self, mensaje: str, codigo: int = 409) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


# -- nombre del fichero -------------------------------------------------


def nombre_seguro(nombre: str) -> str:
    """Se queda con el nombre a secas, sin carpetas ni sorpresas.

    Se rechaza en vez de limpiarse a la fuerza: un nombre raro es señal de
    que algo va mal, y renombrarlo en silencio esconde el problema.
    """
    limpio = Path(str(nombre or "")).name.strip()
    if not limpio or not NOMBRE_VALIDO.match(limpio):
        raise ImportacionRechazada(
            "El nombre del fichero tiene caracteres que no se admiten.", 400
        )
    return limpio


# -- huella del vuelo ---------------------------------------------------


def huella_de_avlog(contenido: bytes) -> tuple[str, Optional[str]]:
    """Devuelve (huella, license_id) de un `.avlog.json`.

    El `license_id` es None si el vuelo no dice de quién es: los vuelos
    grabados antes de que EvA lo guardara no tienen dueño declarado.

    🔐 FASE 1: Confía en integrity.track_hash que escribió el cliente.
    Si no lo trae, recalcula. No rechaza por discrepancia (compatibilidad).
    """
    try:
        datos = json.loads(contenido.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ImportacionRechazada(
            "El fichero no es un vuelo de EvA legible.", 400
        ) from exc

    if not isinstance(datos, dict):
        raise ImportacionRechazada("El fichero no es un vuelo de EvA.", 400)

    piloto = datos.get("pilot") or {}
    license_id = (piloto.get("license_id") or "").strip() or None

    integridad = datos.get("integrity") or {}
    huella = (integridad.get("track_hash") or "").strip()
    if huella:
        # El cliente escribió el hash: confiar en él
        return huella, license_id

    # Sin hash guardado: se calcula sobre la traza, igual que el grabador.
    from avcars.integrity import track_hash  # import tardío: web sin cliente
    from avcars.schema import TrackPoint

    try:
        traza = [TrackPoint.model_validate(p) for p in datos.get("track") or []]
    except Exception as exc:
        raise ImportacionRechazada(
            "El vuelo no trae una traza que se pueda comprobar.", 400
        ) from exc
    return track_hash(traza), license_id


def huella_de_csv(contenido: bytes) -> str:
    """Huella de un CSV de fstelemetry: el propio contenido."""
    return hashlib.sha256(contenido).hexdigest()


# -- registro de lo ya importado ---------------------------------------


def _leer_registro() -> dict:
    try:
        datos = json.loads(REGISTRO_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _guardar_registro(registro: dict) -> None:
    REGISTRO_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporal = REGISTRO_PATH.with_suffix(".tmp")
    temporal.write_text(
        json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporal.replace(REGISTRO_PATH)


def ya_importado(huella: str) -> Optional[dict]:
    """Datos de la importación anterior de ese vuelo, o None si es nuevo."""
    entrada = _leer_registro().get(huella)
    return entrada if isinstance(entrada, dict) else None


def anotar(huella: str, piloto: str, fichero: str) -> None:
    """Deja constancia de que ese vuelo ya está en la cartilla."""
    registro = _leer_registro()
    registro[huella] = {
        "piloto": piloto,
        "fichero": fichero,
        "importado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _guardar_registro(registro)


def huella_de_fichero(nombre: str) -> Optional[str]:
    """La huella con la que se importó ese fichero, o None si no consta.

    Es la búsqueda inversa de `anotar`: dado el nombre que ve el piloto,
    encuentra la huella para poder olvidar el vuelo (gestión, admin).
    """
    for huella, entrada in _leer_registro().items():
        if isinstance(entrada, dict) and entrada.get("fichero") == nombre:
            return huella
    return None


def olvidar(huella: str) -> None:
    """Quita el vuelo del registro: puede volver a importarse.

    No borra el fichero ni las estadísticas — eso lo decide quien llama,
    con la vista completa de qué más depende de esa huella.
    """
    registro = _leer_registro()
    if huella in registro:
        del registro[huella]
        _guardar_registro(registro)


# -- log de auditoría append-only (FASE 1) --------------------------------


TRUSTED_LOG_PATH = Path(__file__).resolve().parent / "data" / "trusted_log.json"


def auditar_importacion(
    huella: str,
    piloto: str,
    nombre_fichero: str,
    ip_cliente: str,
    resultado: str = "éxito",
) -> None:
    """Registra en trusted_log.json (append-only) quién subió qué y cuándo.

    🔐 FASE 1: Log immutable de servidor con timestamp UTC e IP del cliente.
    Solo para lectura/auditoría. No se usa para validar nada en tiempo real.
    """
    try:
        registro = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "ip_cliente": ip_cliente,
            "piloto": piloto,
            "fichero": nombre_fichero,
            "huella": huella,
            "resultado": resultado,
        }

        # Leer el log actual
        if TRUSTED_LOG_PATH.exists():
            try:
                entries = json.loads(TRUSTED_LOG_PATH.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                entries = []
        else:
            entries = []

        if not isinstance(entries, list):
            entries = []

        # Append: nunca reescribir lo anterior
        entries.append(registro)

        # Guardar con transacción (escribir a .tmp, luego renombrar)
        TRUSTED_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporal = TRUSTED_LOG_PATH.with_suffix(".tmp")
        temporal.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temporal.replace(TRUSTED_LOG_PATH)
    except Exception:
        # Never break the upload if auditing fails
        pass


# -- vuelo completo (llegó al destino declarado) ------------------------

#: Margen alrededor del aeródromo de destino: un aeródromo real tiene
#: pistas y plataformas separadas varios km del punto de referencia que
#: se guarda en `airports.json`/`aerodromos_es`, así que exigir coincidencia
#: exacta rechazaría vuelos que sí llegaron. 10 NM (~18,5 km) es de sobra
#: para eso sin aceptar un desvío a un aeródromo distinto.
DESTINO_RADIO_NM = 10.0


def _distancia_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia aproximada en millas náuticas entre dos puntos.

    Aproximación plana con corrección de latitud: sobra de precisión a la
    escala de "¿aterrizó cerca del aeródromo?" y evita depender de una
    librería geodésica solo para esto.
    """
    import math

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    mean_lat = math.radians((lat1 + lat2) / 2.0)
    x = dlon * math.cos(mean_lat)
    return math.hypot(dlat, x) * 60.0  # 1° de latitud ~= 60 NM


def vuelo_llego_a_destino(datos: dict, aeropuertos: dict) -> bool:
    """¿El vuelo terminó cerca del aeródromo de destino declarado?

    Se mira dónde acaba la traza, no un evento concreto: da igual el motivo
    por el que no llegara —nunca despegó, se desvió, se cortó a medias—,
    en todos esos casos el último punto queda lejos del destino. No hace
    falta encontrar el touchdown, basta con dónde terminó de verdad, y en
    tierra (sobrevolar cerca sin aterrizar no cuenta).

    `aeropuertos` es el `icao -> {"lat", "lon", ...}` de la web
    (`AIRPORTS`); sin coordenadas del destino no se puede afirmar que
    llegó, así que se rechaza.
    """
    plan = datos.get("flight_plan") or {}
    destino = str(plan.get("arrival_icao") or "").strip().upper()
    aeropuerto = aeropuertos.get(destino)
    if not aeropuerto:
        return False

    track = datos.get("track") or []
    if not track:
        return False
    ultimo = track[-1]
    if not ultimo.get("on_ground"):
        return False
    lat, lon = ultimo.get("lat"), ultimo.get("lon")
    if lat is None or lon is None:
        return False

    distancia = _distancia_nm(lat, lon, aeropuerto["lat"], aeropuerto["lon"])
    return distancia <= DESTINO_RADIO_NM


# -- la comprobación completa ------------------------------------------


def _mismo_piloto(uno: str, otro: str) -> bool:
    """Compara indicativos sin distinguir mayúsculas ni espacios.

    El grabador escribe el indicativo tal como lo teclea el piloto, así que
    el mismo piloto aparece como `EVA18L` o `EvA18L` según el día. Comparar
    exacto le impedía importar sus propios vuelos, con un mensaje que además
    decía "este vuelo es de otro piloto" señalándole a él mismo. Las cuentas
    ya comparaban así (`cuentas._ficha`, con `COLLATE NOCASE`).
    """
    return (uno or "").strip().casefold() == (otro or "").strip().casefold()


def revisar(
    contenido: bytes,
    nombre: str,
    piloto_sesion: str,
    aeropuertos: Optional[dict] = None,
) -> tuple[str, str]:
    """Decide si el vuelo puede entrar. Devuelve (nombre_seguro, huella).

    Lanza `ImportacionRechazada` con el motivo si no puede. `aeropuertos`
    habilita la comprobación de vuelo completo (regla 3 arriba); si no se
    pasa, se omite — así los tests que no le dan importancia a esto no
    tienen que fabricar coordenadas.
    """
    nombre = nombre_seguro(nombre)

    if nombre.endswith(".avlog.json"):
        huella, dueno = huella_de_avlog(contenido)
        # Un vuelo sin dueño declarado (grabado antes de que EvA lo guardara)
        # se lo queda quien lo sube: no hay nada que contradiga.
        if dueno is not None and not _mismo_piloto(dueno, piloto_sesion):
            raise ImportacionRechazada(
                f"Este vuelo es del piloto {dueno}, no tuyo. "
                "Cada piloto importa solo sus vuelos.",
                403,
            )
        if aeropuertos is not None:
            try:
                datos = json.loads(contenido.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                datos = {}
            if not vuelo_llego_a_destino(datos, aeropuertos):
                destino = str(
                    (datos.get("flight_plan") or {}).get("arrival_icao") or "???"
                ).upper()
                raise ImportacionRechazada(
                    f"Este vuelo no llegó a {destino}, el destino declarado "
                    "en el plan. Solo se suben vuelos completos: un rodaje, "
                    "un despegue abortado o un desvío no entran en la "
                    "cartilla.",
                    400,
                )
    elif nombre.endswith(".csv"):
        huella = huella_de_csv(contenido)
    else:
        raise ImportacionRechazada(
            "Formato no válido. Se admiten .avlog.json y .csv.", 400
        )

    anterior = ya_importado(huella)
    if anterior is not None:
        cuando = str(anterior.get("importado_utc", "")).replace("T", " ")
        de_quien = anterior.get("piloto", "")
        if de_quien and not _mismo_piloto(de_quien, piloto_sesion):
            raise ImportacionRechazada(
                "Este vuelo ya está en la cartilla de otro piloto.", 403
            )
        raise ImportacionRechazada(
            f"Este vuelo ya lo importaste el {cuando} UTC "
            f"como «{anterior.get('fichero', '')}».",
            409,
        )

    return nombre, huella
