"""Conector para X-Plane vía UDP Data Output (nativo, sin plugins).

El piloto activa en X-Plane: Settings > Data Output > marca las filas de
datos que nos interesan (velocidades, actitud, posición...) y activa la
columna "Network via UDP" con la IP/puerto de este cliente.

Formato del paquete (documentado y estable desde X-Plane 8, ver
https://www.nuclearprojects.com/xplane/xplaneref.html):

  - Cabecera de 5 bytes: b"DATA" + 1 byte de índice interno de X-Plane
    (se ignora al enviar, no forma parte de los datos).
  - Después, N bloques de 36 bytes cada uno: int32 índice de fila + 8 x
    float32 con los valores de esa fila.

El índice de cada bloque depende de qué filas active el piloto en la
pantalla de Data Output — no hay un índice global fijo por la app. Este
módulo separa dos cosas:

1. `parse_data_packet` / `receive_raw`: decodifican la estructura binaria
   del paquete. Esto SÍ está verificado (tests con paquetes construidos a
   mano + prueba de socket real en loopback).
2. `poll` (traducir los grupos en bruto a `SimState`): usa la convención más
   citada por la comunidad para las filas estándar (velocidades=3,
   actitud=17, posición=20), pero **no se ha podido verificar contra un
   X-Plane real en este entorno** (no hay simulador disponible aquí). Por
   eso `poll` está deliberadamente sin implementar todavía — ver
   CONTEXT.md. No tiene sentido fingir un mapeo que no se ha comprobado.
"""
from __future__ import annotations

import socket
import struct

from avcars.connectors.base import SimConnector, SimState

HEADER = b"DATA"
BLOCK_SIZE = 4 + 8 * 4  # int32 índice + 8 x float32

# Convención habitual de filas de "Data Output" en X-Plane (ver docstring).
# PENDIENTE DE VERIFICAR contra un X-Plane real antes de usarse en poll().
GROUP_SPEEDS = 3
GROUP_ATTITUDE = 17
GROUP_POSITION = 20


def parse_data_packet(payload: bytes) -> dict[int, tuple[float, ...]]:
    """Decodifica un paquete UDP "DATA" de X-Plane en {índice: (f0..f7)}.

    Solo interpreta la estructura binaria (documentada y estable); no
    interpreta el significado de cada índice.
    """
    if not payload.startswith(HEADER):
        raise ValueError(f"Paquete no reconocido, no empieza por {HEADER!r}")

    body = payload[5:]  # 4 bytes de label + 1 byte de índice interno
    if len(body) == 0 or len(body) % BLOCK_SIZE != 0:
        raise ValueError(
            f"Tamaño de paquete inesperado: {len(body)} bytes "
            f"no es múltiplo de {BLOCK_SIZE}"
        )

    groups: dict[int, tuple[float, ...]] = {}
    for offset in range(0, len(body), BLOCK_SIZE):
        block = body[offset : offset + BLOCK_SIZE]
        index = struct.unpack_from("<i", block, 0)[0]
        floats = struct.unpack_from("<8f", block, 4)
        groups[index] = floats
    return groups


class XPlaneUDPConnector(SimConnector):
    """Conector UDP para X-Plane.

    `connect`/`disconnect`/`receive_raw` están implementados y probados
    (incluye una prueba con un socket real en loopback). `poll` está
    pendiente: necesita verificar el mapeo de grupos contra un X-Plane real
    (ver docstring del módulo y CONTEXT.md).
    """

    def __init__(self, listen_port: int, timeout_s: float = 5.0) -> None:
        self._requested_port = listen_port
        self._timeout_s = timeout_s
        self._sock: socket.socket | None = None

    @property
    def bound_port(self) -> int:
        """Puerto real en el que está escuchando (útil si se pidió el puerto 0)."""
        if self._sock is None:
            raise RuntimeError("Conector no conectado; llama a connect() primero.")
        return self._sock.getsockname()[1]

    def connect(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("0.0.0.0", self._requested_port))
        self._sock.settimeout(self._timeout_s)

    def disconnect(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def receive_raw(self) -> dict[int, tuple[float, ...]]:
        """Recibe un paquete y lo decodifica en {índice: (f0..f7)}.

        No traduce a `SimState` (ver `poll`). Es la parte de este conector
        que sí está verificada.
        """
        if self._sock is None:
            raise RuntimeError("Conector no conectado; llama a connect() primero.")
        payload, _addr = self._sock.recvfrom(4096)
        return parse_data_packet(payload)

    def poll(self) -> SimState:
        raise NotImplementedError(
            "receive_raw() está implementado y probado, pero el mapeo de "
            "grupos UDP a SimState (GROUP_SPEEDS/GROUP_ATTITUDE/GROUP_POSITION) "
            "no se ha verificado todavía contra un X-Plane real. Pendiente, "
            "ver CONTEXT.md."
        )
