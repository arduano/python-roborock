"""Tests for B01 map protocol decode helpers."""

from __future__ import annotations

import base64
import zlib
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from roborock.protocols.b01_map_protocol import decode_b01_map_payload, derive_map_key

FIXTURE = Path(__file__).resolve().parents[1] / "map" / "testdata" / "raw-mqtt-map301.bin.inflated.bin"


def test_decode_b01_map_payload_round_trip() -> None:
    local_key = "abcdefghijklmnop"
    serial = "testsn012345"
    model = "roborock.vacuum.sc05"
    inflated = FIXTURE.read_bytes()

    compressed = zlib.compress(inflated)
    map_key = derive_map_key(serial, model)
    encrypted = AES.new(map_key, AES.MODE_ECB).encrypt(pad(compressed.hex().encode(), 16))
    payload = base64.b64encode(base64.b64encode(encrypted))

    decoded = decode_b01_map_payload(payload, local_key=local_key, serial=serial, model=model)
    assert decoded == inflated
