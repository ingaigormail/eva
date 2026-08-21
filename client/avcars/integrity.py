"""Hash de integridad de la traza.

Sirve para detectar que alguien editó a mano el `.avlog.json` antes de
subirlo. No es una firma: cualquiera con el cliente delante puede recalcular
el hash sobre una traza retocada y sustituirlo. Quién lo verifica —y por
tanto contra qué protege de verdad— es la decisión SEC-03 de
`docs/especificacion_funcional.md`, todavía abierta.

Qué se cubre
------------
Solo el array `track`, no el documento entero. El resto del fichero cambia
legítimamente después de grabar: `evaluation` se añade al evaluar (ver
`avcars/cli.py`), y un hash del documento completo lo invalidaría cada vez.
La traza, en cambio, no vuelve a tocarse nunca: es el dato bruto.

Por qué esta serialización y no el JSON del fichero
---------------------------------------------------
El fichero se escribe con `exclude_none=True` y con el orden de campos que
declare `schema.py`. Hashear ese texto ataría el hash a dos detalles de
presentación: mañana se reordena un campo del modelo y todos los vuelos
grabados parecerían manipulados. Aquí se reconstruye una forma canónica
—claves ordenadas, sin espacios, campos ausentes como `null`— que sobrevive
a un ida y vuelta por disco.

El formato de los floats es el `repr` de Python, que es el texto más corto
que vuelve a leerse como el mismo número: estable entre plataformas y
reproducible tras releer el fichero.
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

from .schema import IntegrityInfo, TrackPoint

#: Nombre tal y como se escribe en el log (ver `docs/formato_log_vuelo.md`).
HASH_ALGORITHM = "SHA-256"


def canonical_track_bytes(track: Iterable[TrackPoint]) -> bytes:
    """Representación canónica de la traza, la que entra en el hash."""
    points = [point.model_dump(mode="json") for point in track]
    return json.dumps(
        points,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def track_hash(track: Iterable[TrackPoint]) -> str:
    """Hash hexadecimal de la traza. Una traza vacía también tiene el suyo."""
    return hashlib.sha256(canonical_track_bytes(track)).hexdigest()


def build_integrity(track: Iterable[TrackPoint]) -> IntegrityInfo:
    return IntegrityInfo(hash_algorithm=HASH_ALGORITHM, track_hash=track_hash(track))
