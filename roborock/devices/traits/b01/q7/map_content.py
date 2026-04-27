"""Trait for fetching parsed map content from B01/Q7 devices.

This intentionally mirrors the v1 `MapContentTrait` contract:
- `refresh()` performs I/O and populates cached fields
- `parse_map_content()` reparses cached raw bytes without I/O
- fields `image_content`, `map_data`, and `raw_api_response` are then readable

For B01/Q7 devices, the underlying raw map payload is retrieved via `MapTrait`.
"""

import asyncio
from dataclasses import dataclass

from vacuum_map_parser_base.map_data import MapData, Point

from roborock.data import CombinedMapInfo, NamedRoomMapping, RoborockBase
from roborock.devices.rpc.b01_q7_channel import MapRpcChannel
from roborock.devices.traits import Trait
from roborock.exceptions import RoborockException
from roborock.map.b01_map_parser import B01MapParser, B01MapParserConfig
from roborock.protocols.b01_q7_protocol import B01_Q7_DPS, Q7RequestMessage
from roborock.roborock_typing import RoborockB01Q7Methods

from .map import MapTrait

_TRUNCATE_LENGTH = 20
Q7_CURRENT_MAP_NAME = "Current map"


@dataclass
class MapContent(RoborockBase):
    """Dataclass representing map content."""

    image_content: bytes | None = None
    """The rendered image of the map in PNG format."""

    map_data: MapData | None = None
    """Parsed map data (metadata for points on the map)."""

    raw_api_response: bytes | None = None
    """Raw bytes of the map payload from the device.

    This should be treated as an opaque blob used only internally by this
    library to re-parse the map data when needed.
    """

    def __repr__(self) -> str:
        img = self.image_content
        if img and len(img) > _TRUNCATE_LENGTH:
            img = img[: _TRUNCATE_LENGTH - 3] + b"..."
        return f"MapContent(image_content={img!r}, map_data={self.map_data!r})"

    @property
    def map_flag(self) -> int | None:
        """Return the current map flag if map data is available."""
        if self.map_data is None:
            return None
        return int(getattr(self.map_data, "map_flag", 0))

    @property
    def room_names(self) -> dict[int, str]:
        """Return current-map room names indexed by room id."""
        additional_parameters = getattr(self.map_data, "additional_parameters", None)
        if not isinstance(additional_parameters, dict):
            return {}

        room_names = additional_parameters.get("room_names")
        if not isinstance(room_names, dict):
            return {}

        return {
            int(room_id): str(room_name)
            for room_id, room_name in sorted(room_names.items(), key=lambda item: int(item[0]))
        }

    @property
    def rooms(self) -> list[NamedRoomMapping]:
        """Return current-map rooms as named room mappings."""
        return [
            NamedRoomMapping(segment_id=room_id, iot_id=str(room_id), raw_name=room_name)
            for room_id, room_name in self.room_names.items()
        ]

    @property
    def current_map_name(self) -> str:
        """Return the synthetic name used for the active Q7 map."""
        return Q7_CURRENT_MAP_NAME

    @property
    def current_map_info(self) -> CombinedMapInfo | None:
        """Return the active map info in the same high-level shape used by v1."""
        if (map_flag := self.map_flag) is None:
            return None
        return CombinedMapInfo(map_flag=map_flag, name=self.current_map_name, rooms=self.rooms)

    @property
    def vacuum_position(self) -> Point | None:
        """Return the current vacuum position from cached map data."""
        if self.map_data is None:
            return None
        return self.map_data.vacuum_position


class MapContentTrait(MapContent, Trait):
    """Trait for fetching parsed map content for Q7 devices."""

    def __init__(
        self,
        map_rpc_channel: MapRpcChannel,
        map_trait: MapTrait,
        *,
        map_parser_config: B01MapParserConfig | None = None,
    ) -> None:
        super().__init__()
        self._map_rpc_channel = map_rpc_channel
        self._map_trait = map_trait
        self._map_parser = B01MapParser(map_parser_config)
        # Map uploads are serialized per-device to avoid response cross-wiring.
        self._map_command_lock = asyncio.Lock()

    async def refresh(self) -> None:
        """Fetch, decode, and parse the current map payload.

        This uses the Map Trait metadata to determine the current map_id and
        will refresh that metadata first if needed.
        """
        if (map_id := self._map_trait.current_map_id) is None:
            await self._map_trait.refresh()
            map_id = self._map_trait.current_map_id
        if map_id is None:
            raise RoborockException("Unable to determine current map ID")

        request = Q7RequestMessage(
            dps=B01_Q7_DPS,
            command=RoborockB01Q7Methods.UPLOAD_BY_MAPID,
            params={"map_id": map_id},
        )
        async with self._map_command_lock:
            raw_payload = await self._map_rpc_channel.send_map_command(request)

        try:
            parsed_data = self._map_parser.parse(raw_payload)
        except RoborockException:
            raise
        except Exception as ex:
            raise RoborockException("Failed to parse B01 map data") from ex

        if parsed_data.image_content is None:
            raise RoborockException("Failed to render B01 map image")

        self.image_content = parsed_data.image_content
        self.map_data = parsed_data.map_data
        self.raw_api_response = raw_payload
