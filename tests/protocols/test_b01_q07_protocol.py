"""Tests for the B01 protocol message encoding and decoding."""

import base64
import json
import pathlib
import zlib
from collections.abc import Generator

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from freezegun import freeze_time
from syrupy import SnapshotAssertion

from roborock.exceptions import RoborockException
from roborock.protocol import Utils
from roborock.protocols.b01_q7_protocol import (
    Q7RequestMessage,
    decode_map_response_payload,
    decode_rpc_response,
    encode_mqtt_payload,
)
from roborock.roborock_message import RoborockMessage, RoborockMessageProtocol

TESTDATA_PATH = pathlib.Path("tests/protocols/testdata/b01_q7_protocol")
TESTDATA_FILES = list(TESTDATA_PATH.glob("*.json"))
TESTDATA_IDS = [x.stem for x in TESTDATA_FILES]


@pytest.fixture(autouse=True)
def fixed_time_fixture() -> Generator[None, None, None]:
    """Fixture to freeze time for predictable request IDs."""
    with freeze_time("2025-01-20T12:00:00"):
        yield


@pytest.mark.parametrize("filename", TESTDATA_FILES, ids=TESTDATA_IDS)
def test_decode_rpc_payload(filename: str, snapshot: SnapshotAssertion) -> None:
    """Test decoding a B01 RPC response protocol message."""
    with open(filename, "rb") as f:
        payload = f.read()

    message = RoborockMessage(
        protocol=RoborockMessageProtocol.RPC_RESPONSE,
        payload=payload,
        seq=12750,
        version=b"B01",
        random=97431,
        timestamp=1652547161,
    )

    decoded_message = decode_rpc_response(message)
    assert json.dumps(decoded_message, indent=2) == snapshot


@pytest.mark.parametrize(
    ("dps", "command", "params", "msg_id"),
    [
        (
            10000,
            "prop.get",
            {"property": ["status", "fault"]},
            123456789,
        ),
    ],
)
def test_encode_mqtt_payload(dps: int, command: str, params: dict[str, list[str]], msg_id: int) -> None:
    """Test encoding of MQTT payload for B01 commands."""

    message = encode_mqtt_payload(Q7RequestMessage(dps, command, params, msg_id))
    assert isinstance(message, RoborockMessage)
    assert message.protocol == RoborockMessageProtocol.RPC_REQUEST
    assert message.version == b"B01"
    assert message.payload is not None
    unpadded = unpad(message.payload, AES.block_size)
    decoded_json = json.loads(unpadded.decode("utf-8"))

    assert decoded_json["dps"][str(dps)]["method"] == command
    assert decoded_json["dps"][str(dps)]["msgId"] == str(msg_id)
    assert decoded_json["dps"][str(dps)]["params"] == params


def _encode_map_response_payload(payload: bytes, *, serial: str, model: str) -> bytes:
    map_key = Utils.derive_b01_map_key(serial, model)
    encrypted = AES.new(map_key, AES.MODE_ECB).encrypt(pad(payload.hex().encode(), AES.block_size))
    return base64.b64encode(encrypted)


def test_decode_map_response_payload_decompresses_by_default() -> None:
    serial = "testsn012345"
    model = "roborock.vacuum.sc05"
    scmap_payload = b"raw-scmap-payload"
    raw_payload = _encode_map_response_payload(zlib.compress(scmap_payload), serial=serial, model=model)

    assert decode_map_response_payload(raw_payload, serial=serial, model=model) == scmap_payload


def test_decode_map_response_payload_supports_explicit_uncompressed_payloads() -> None:
    serial = "testsn012345"
    model = "roborock.vacuum.sc05"
    scmap_payload = b"raw-scmap-payload"
    raw_payload = _encode_map_response_payload(scmap_payload, serial=serial, model=model)

    assert decode_map_response_payload(raw_payload, serial=serial, model=model, compressed=False) == scmap_payload


def test_decode_map_response_payload_rejects_invalid_base64() -> None:
    with pytest.raises(RoborockException, match="Failed to decode B01 map payload"):
        decode_map_response_payload(b"not valid base64!", serial="testsn012345", model="roborock.vacuum.sc05")
