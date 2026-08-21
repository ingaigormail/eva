"""Tests del conector UDP de X-Plane (avcars/connectors/xplane_udp.py).

Cubren la parte verificable sin simulador: la decodificación del paquete
binario, incluyendo una prueba con un socket UDP real en loopback.
"""
import socket
import struct

import pytest

from avcars.connectors.xplane_udp import (
    BLOCK_SIZE,
    HEADER,
    XPlaneUDPConnector,
    parse_data_packet,
)


GROUP_INDEX_FOR_TEST = 3


def _build_packet(blocks: dict[int, tuple[float, ...]]) -> bytes:
    """Construye un paquete "DATA" válido a partir de {índice: (f0..f7)}."""
    payload = HEADER + b"\x00"
    for index, floats in blocks.items():
        assert len(floats) == 8
        payload += struct.pack("<i", index) + struct.pack("<8f", *floats)
    return payload


def test_parse_single_block():
    floats = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0)
    packet = _build_packet({20: floats})

    groups = parse_data_packet(packet)

    assert set(groups.keys()) == {20}
    assert groups[20] == pytest.approx(floats)


def test_parse_multiple_blocks():
    blocks = {
        3: (120.0, 0, 0, 0, 0, 0, 0, 0),
        17: (0.5, -0.2, 90.0, 88.0, 0, 0, 0, 0),
        20: (40.4, -3.7, 1500.0, 500.0, 0, 0, 0, 0),
    }
    packet = _build_packet(blocks)

    groups = parse_data_packet(packet)

    assert set(groups.keys()) == {3, 17, 20}
    for index, floats in blocks.items():
        assert groups[index] == pytest.approx(floats)


def test_rejects_wrong_header():
    with pytest.raises(ValueError):
        parse_data_packet(b"XXXX\x00" + b"\x00" * BLOCK_SIZE)


def test_rejects_malformed_length():
    with pytest.raises(ValueError):
        parse_data_packet(HEADER + b"\x00" + b"\x00" * (BLOCK_SIZE - 1))


def test_connector_receives_real_udp_packet():
    """Prueba de extremo a extremo con un socket UDP real en loopback.

    No usa X-Plane: simula el envío enviando nosotros mismos un paquete bien
    formado al puerto en el que escucha el conector.
    """
    connector = XPlaneUDPConnector(listen_port=0, timeout_s=2.0)
    connector.connect()
    try:
        floats = (150.0, 0, 0, 0, 0, 0, 0, 0)
        packet = _build_packet({GROUP_INDEX_FOR_TEST: floats})

        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender.sendto(packet, ("127.0.0.1", connector.bound_port))
        sender.close()

        groups = connector.receive_raw()
        assert groups[GROUP_INDEX_FOR_TEST] == pytest.approx(floats)
    finally:
        connector.disconnect()


def test_poll_not_implemented_yet():
    connector = XPlaneUDPConnector(listen_port=0)
    connector.connect()
    try:
        with pytest.raises(NotImplementedError):
            connector.poll()
    finally:
        connector.disconnect()
