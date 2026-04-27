import json

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from roborock.devices.traits.b01.q7 import Q7PropertiesApi
from tests.fixtures.channel_fixtures import FakeChannel

from . import B01MessageBuilder


async def test_q7_vacuum_clean_segments_normalizes_home_assistant_ids(
    q7_api: Q7PropertiesApi,
    fake_channel: FakeChannel,
    message_builder: B01MessageBuilder,
):
    """Q7 room cleaning accepts HA-style segment ids in the library layer."""
    fake_channel.response_queue.append(message_builder.build("ok"))

    await q7_api.clean_segments([10, "1_11"])

    assert len(fake_channel.published_messages) == 1
    message = fake_channel.published_messages[0]
    payload_data = json.loads(unpad(message.payload, AES.block_size))
    assert payload_data["dps"]["10000"]["method"] == "service.set_room_clean"
    assert payload_data["dps"]["10000"]["params"] == {
        "clean_type": 1,
        "ctrl_value": 1,
        "room_ids": [10, 11],
    }


async def test_q7_vacuum_send_command_intercepts_app_segment_clean(
    q7_api: Q7PropertiesApi,
    fake_channel: FakeChannel,
    message_builder: B01MessageBuilder,
):
    """Legacy APP_SEGMENT_CLEAN normalization now lives in the library layer."""
    fake_channel.response_queue.append(message_builder.build("ok"))

    await q7_api.vacuum.send_command("app_segment_clean", [{"segments": [10, "1_11"]}])

    assert len(fake_channel.published_messages) == 1
    message = fake_channel.published_messages[0]
    payload_data = json.loads(unpad(message.payload, AES.block_size))
    assert payload_data["dps"]["10000"]["method"] == "service.set_room_clean"
    assert payload_data["dps"]["10000"]["params"] == {
        "clean_type": 1,
        "ctrl_value": 1,
        "room_ids": [10, 11],
    }


async def test_q7_vacuum_send_command_passthrough_with_extra_payload(
    q7_api: Q7PropertiesApi,
    fake_channel: FakeChannel,
    message_builder: B01MessageBuilder,
):
    """Non-canonical APP_SEGMENT_CLEAN payloads are passed through unchanged."""
    fake_channel.response_queue.append(message_builder.build("ok"))

    await q7_api.vacuum.send_command("app_segment_clean", [{"segments": [10], "repeat": 2}])

    assert len(fake_channel.published_messages) == 1
    message = fake_channel.published_messages[0]
    payload_data = json.loads(unpad(message.payload, AES.block_size))
    assert payload_data["dps"]["10000"]["method"] == "app_segment_clean"
    assert payload_data["dps"]["10000"]["params"] == [{"segments": [10], "repeat": 2}]
