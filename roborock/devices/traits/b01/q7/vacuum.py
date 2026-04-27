"""Vacuum command helpers for Q7 B01 devices."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from roborock.data.b01_q7.b01_q7_code_mappings import (
    CleanPathPreferenceMapping,
    CleanRepeatMapping,
    CleanTaskTypeMapping,
    CleanTypeMapping,
    SCDeviceCleanParam,
    SCWindMapping,
    WaterLevelMapping,
)
from roborock.protocols.b01_q7_protocol import CommandType, ParamsType
from roborock.roborock_message import RoborockB01Props
from roborock.roborock_typing import RoborockB01Q7Methods

if TYPE_CHECKING:
    from . import Q7PropertiesApi


class VacuumTrait:
    """Trait for sending vacuum-related commands to Q7 devices."""

    def __init__(self, api: "Q7PropertiesApi") -> None:
        """Initialize the VacuumTrait."""
        self._api = api

    async def set_fan_speed(self, fan_speed: SCWindMapping) -> None:
        """Set the fan speed (wind)."""
        await self._api.set_prop(RoborockB01Props.WIND, fan_speed.code)

    async def set_water_level(self, water_level: WaterLevelMapping) -> None:
        """Set the water level (water)."""
        await self._api.set_prop(RoborockB01Props.WATER, water_level.code)

    async def set_mode(self, mode: CleanTypeMapping) -> None:
        """Set the cleaning mode (vacuum, mop, or vacuum and mop)."""
        await self._api.set_prop(RoborockB01Props.MODE, mode.code)

    async def set_clean_path_preference(self, preference: CleanPathPreferenceMapping) -> None:
        """Set the cleaning path preference (route)."""
        await self._api.set_prop(RoborockB01Props.CLEAN_PATH_PREFERENCE, preference.code)

    async def set_repeat_state(self, repeat: CleanRepeatMapping) -> None:
        """Set the cleaning repeat state (cycles)."""
        await self._api.set_prop(RoborockB01Props.REPEAT_STATE, repeat.code)

    async def start_clean(self) -> None:
        """Start cleaning."""
        await self._api.send(
            command=RoborockB01Q7Methods.SET_ROOM_CLEAN,
            params={
                "clean_type": CleanTaskTypeMapping.ALL.code,
                "ctrl_value": SCDeviceCleanParam.START.code,
                "room_ids": [],
            },
        )

    async def clean_segments(self, segment_ids: list[int | str]) -> None:
        """Start segment cleaning for the given ids.

        Q7 devices use room ids internally. Accepting both raw integer room ids and
        Home Assistant-style string ids here keeps the compatibility shim in the
        library layer instead of every downstream integration.
        """
        room_ids = [self._normalize_segment_id(segment_id) for segment_id in segment_ids]
        await self._api.send(
            command=RoborockB01Q7Methods.SET_ROOM_CLEAN,
            params={
                "clean_type": CleanTaskTypeMapping.ROOM.code,
                "ctrl_value": SCDeviceCleanParam.START.code,
                "room_ids": room_ids,
            },
        )

    async def pause_clean(self) -> None:
        """Pause cleaning."""
        await self._api.send(
            command=RoborockB01Q7Methods.SET_ROOM_CLEAN,
            params={
                "clean_type": CleanTaskTypeMapping.ALL.code,
                "ctrl_value": SCDeviceCleanParam.PAUSE.code,
                "room_ids": [],
            },
        )

    async def stop_clean(self) -> None:
        """Stop cleaning."""
        await self._api.send(
            command=RoborockB01Q7Methods.SET_ROOM_CLEAN,
            params={
                "clean_type": CleanTaskTypeMapping.ALL.code,
                "ctrl_value": SCDeviceCleanParam.STOP.code,
                "room_ids": [],
            },
        )

    async def return_to_dock(self) -> None:
        """Return to dock."""
        await self._api.send(
            command=RoborockB01Q7Methods.START_RECHARGE,
            params={},
        )

    async def find_me(self) -> None:
        """Locate the robot."""
        await self._api.send(
            command=RoborockB01Q7Methods.FIND_DEVICE,
            params={},
        )

    async def send_command(self, command: CommandType, params: ParamsType) -> Any:
        """Send a vacuum command.

        This preserves the legacy ``app_segment_clean`` compatibility behavior in
        the library layer so downstream integrations do not need to normalize raw
        command payloads themselves.
        """
        if self._is_app_segment_clean(command) and isinstance(params, list) and len(params) == 1:
            first_param = params[0]
            if (
                isinstance(first_param, dict)
                and isinstance(first_param.get("segments"), list)
                and set(first_param) <= {"segments"}
            ):
                await self.clean_segments(first_param["segments"])
                return None

        return await self._api.send(command, params)

    @staticmethod
    def _normalize_segment_id(segment_id: int | str) -> int:
        """Normalize a room identifier.

        Accepts either raw integer room ids (``10``) or Home Assistant-style
        identifiers (``"10"`` / ``"1_10"``) and always returns the room id.
        """
        if isinstance(segment_id, int):
            return segment_id
        return int(str(segment_id).rsplit("_", maxsplit=1)[-1])

    @staticmethod
    def _is_app_segment_clean(command: CommandType) -> bool:
        """Return whether a command represents APP_SEGMENT_CLEAN."""
        if isinstance(command, Enum):
            value = command.value
        else:
            value = command
        return isinstance(value, str) and value.casefold() == "app_segment_clean"
