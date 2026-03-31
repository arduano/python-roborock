import base64
import gzip
import hashlib
import zlib
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from roborock.devices.traits.b01.q7 import Q7PropertiesApi
from roborock.devices.transport.mqtt_channel import MqttChannel
from roborock.exceptions import RoborockException
from roborock.roborock_message import RoborockMessage, RoborockMessageProtocol
from tests.fixtures.channel_fixtures import FakeChannel

from . import B01MessageBuilder

FIXTURE = Path(__file__).resolve().parents[4] / "map" / "testdata" / "raw-mqtt-map301.bin.inflated.bin.gz"


def _build_encrypted_map_payload(serial: str, model: str) -> bytes:
    inflated = gzip.decompress(FIXTURE.read_bytes())
    compressed = zlib.compress(inflated)

    model_suffix = model.split(".")[-1]
    model_key = (model_suffix + "0" * 16)[:16].encode()
    material = f"{serial}+{model_suffix}+{serial}".encode()
    encrypted = AES.new(model_key, AES.MODE_ECB).encrypt(pad(material, AES.block_size))
    md5 = hashlib.md5(base64.b64encode(encrypted), usedforsecurity=False).hexdigest()
    map_key = md5[8:24].encode()

    encoded = AES.new(map_key, AES.MODE_ECB).encrypt(pad(compressed.hex().encode(), AES.block_size))
    return base64.b64encode(encoded)


async def test_q7_map_content_refresh_populates_cached_values(
    q7_api: Q7PropertiesApi,
    fake_channel: FakeChannel,
    message_builder: B01MessageBuilder,
):
    payload = _build_encrypted_map_payload(serial="testsn012345", model="roborock.vacuum.sc05")

    fake_channel.response_queue.append(message_builder.build({"map_list": [{"id": 1772093512, "cur": True}]}))
    fake_channel.response_queue.append(
        RoborockMessage(
            protocol=RoborockMessageProtocol.MAP_RESPONSE,
            payload=payload,
            version=b"B01",
            seq=message_builder.seq + 1,
        )
    )

    await q7_api.map_content.refresh()

    assert q7_api.map_content.raw_api_response == payload
    assert q7_api.map_content.image_content is not None
    assert q7_api.map_content.image_content.startswith(b"\x89PNG\r\n\x1a\n")
    assert q7_api.map_content.map_data is not None
    assert q7_api.map_content.map_data.additional_parameters["room_names"] == {
        10: "room1",
        11: "room2",
        12: "room3",
        13: "room4",
        14: "room5",
        15: "room6",
        16: "room7",
        17: "room8",
        18: "room9",
        19: "room10",
    }


def test_q7_map_content_parse_errors_cleanly(q7_api: Q7PropertiesApi):
    with patch("roborock.devices.traits.b01.q7.map_content.B01MapParser.parse", side_effect=ValueError("boom")):
        with pytest.raises(RoborockException, match="Failed to parse B01 map data"):
            q7_api.map_content.parse_map_content(b"raw")


def test_q7_map_content_preserves_specific_roborock_errors(q7_api: Q7PropertiesApi):
    with patch(
        "roborock.devices.traits.b01.q7.map_content.B01MapParser.parse",
        side_effect=RoborockException("Specific decoder failure"),
    ):
        with pytest.raises(RoborockException, match="Specific decoder failure"):
            q7_api.map_content.parse_map_content(b"raw")


def test_q7_map_content_requires_metadata_at_init(fake_channel: FakeChannel):
    from roborock.data import HomeDataDevice, HomeDataProduct, RoborockCategory

    with pytest.raises(ValueError, match="requires device serial number and product model metadata"):
        Q7PropertiesApi(
            cast(MqttChannel, fake_channel),
            device=HomeDataDevice(
                duid="abc123",
                name="Q7",
                local_key="key123key123key1",
                product_id="product-id-q7",
                sn=None,
            ),
            product=HomeDataProduct(
                id="product-id-q7",
                name="Roborock Q7",
                model="roborock.vacuum.sc05",
                category=RoborockCategory.VACUUM,
            ),
        )
