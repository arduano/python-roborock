import base64
import gzip
import zlib
from pathlib import Path

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from roborock.exceptions import RoborockException
from roborock.protocols.b01_map_protocol import decode_map_response, derive_map_key

FIXTURE = Path(__file__).resolve().parent.parent / "map" / "testdata" / "raw-mqtt-map301.bin.inflated.bin.gz"


def _build_payload(inflated: bytes, *, serial: str, model: str) -> bytes:
    compressed_hex = zlib.compress(inflated).hex().encode()
    map_key = derive_map_key(serial, model)
    encrypted = AES.new(map_key, AES.MODE_ECB).encrypt(pad(compressed_hex, AES.block_size))
    return base64.b64encode(encrypted)


def test_decode_map_response_decodes_fixture_payload() -> None:
    serial = "testsn012345"
    model = "roborock.vacuum.sc05"
    inflated = gzip.decompress(FIXTURE.read_bytes())

    payload = _build_payload(inflated, serial=serial, model=model)

    assert decode_map_response(payload, serial=serial, model=model) == inflated


def test_decode_map_response_rejects_invalid_payload() -> None:
    with pytest.raises(RoborockException, match="Failed to decode B01 map payload"):
        decode_map_response(b"not a map", serial="testsn012345", model="roborock.vacuum.sc05")
