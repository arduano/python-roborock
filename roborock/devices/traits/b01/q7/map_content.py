"""Map content trait for B01/Q7 devices."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from roborock.data import RoborockBase
from roborock.devices.rpc.b01_q7_channel import send_decoded_command, send_map_command
from roborock.devices.traits import Trait
from roborock.devices.transport.mqtt_channel import MqttChannel
from roborock.exceptions import RoborockException
from roborock.map.b01_map_parser import B01MapData, parse_scmap_payload, render_map_png
from roborock.protocols.b01_map_protocol import decode_b01_map_payload
from roborock.protocols.b01_q7_protocol import Q7RequestMessage
from roborock.roborock_typing import RoborockB01Q7Methods

_Q7_DPS = 10000


@dataclass
class B01MapContent(RoborockBase):
    """B01 map content wrapper."""

    image_content: bytes | None = None
    """Rendered map image as PNG bytes."""

    map_data: B01MapData | None = None
    """Decoded SCMap map data object."""

    raw_api_response: bytes | None = None
    """Raw map payload bytes returned by the device."""

    rooms: dict[int, str] | None = None
    """Segment id to segment name mapping from map metadata."""

    map_list: list[dict[str, Any]] | None = None
    """Latest map list response (cached for callers that need map metadata)."""

    current_map_id: int | None = None
    """Map id selected for the latest refresh operation."""


def _extract_current_map_id(map_list_response: dict[str, Any] | None) -> int | None:
    if not isinstance(map_list_response, dict):
        return None
    map_list = map_list_response.get("map_list")
    if not isinstance(map_list, list) or not map_list:
        return None

    for entry in map_list:
        if isinstance(entry, dict) and entry.get("cur") and isinstance(entry.get("id"), int):
            return entry["id"]

    first = map_list[0]
    if isinstance(first, dict) and isinstance(first.get("id"), int):
        return first["id"]
    return None


class Q7MapContentTrait(B01MapContent, Trait):
    """Fetch and parse map content from B01/Q7 devices."""

    def __init__(self, channel: MqttChannel, *, local_key: str, serial: str, model: str) -> None:
        super().__init__()
        self._channel = channel
        self._local_key = local_key
        self._serial = serial
        self._model = model
        self._map_command_lock = asyncio.Lock()

    async def refresh(self) -> B01MapContent:
        map_list_response = await send_decoded_command(
            self._channel,
            Q7RequestMessage(dps=_Q7_DPS, command=RoborockB01Q7Methods.GET_MAP_LIST, params={}),
        )
        self.map_list = map_list_response.get("map_list") if isinstance(map_list_response, dict) else None

        map_id = _extract_current_map_id(map_list_response)
        if map_id is None:
            raise RoborockException(f"Unable to determine map_id from map list response: {map_list_response!r}")

        self.current_map_id = map_id
        async with self._map_command_lock:
            raw_payload = await send_map_command(
                self._channel,
                Q7RequestMessage(
                    dps=_Q7_DPS,
                    command=RoborockB01Q7Methods.UPLOAD_BY_MAPID,
                    params={"map_id": map_id},
                ),
            )

        inflated = decode_b01_map_payload(
            raw_payload,
            local_key=self._local_key,
            serial=self._serial,
            model=self._model,
        )
        parsed = parse_scmap_payload(inflated)

        self.raw_api_response = raw_payload
        self.map_data = parsed
        self.rooms = parsed.rooms
        self.image_content = render_map_png(parsed)
        return self
