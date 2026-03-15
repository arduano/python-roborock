"""B01/Q7 SCMap payload parsing and map rendering."""

from __future__ import annotations

import io
import zlib
from dataclasses import dataclass

from PIL import Image

from roborock.exceptions import RoborockException


@dataclass
class B01MapData:
    """Parsed B01 SCMap payload.

    The B01 map payload contains a protobuf message with a map header and an
    occupancy/room raster. We normalize only the fields we need for rendering
    and segment-name mapping.
    """

    size_x: int
    size_y: int
    map_data: bytes
    rooms: dict[int, str] | None = None


def _read_varint(buf: bytes, idx: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if idx >= len(buf):
            raise RoborockException("Truncated varint in B01 map payload")
        byte = buf[idx]
        idx += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, idx
        shift += 7
        if shift > 63:
            raise RoborockException("Invalid varint in B01 map payload")


def _read_len_delimited(buf: bytes, idx: int) -> tuple[bytes, int]:
    length, idx = _read_varint(buf, idx)
    end = idx + length
    if end > len(buf):
        raise RoborockException("Invalid length-delimited field in B01 map payload")
    return buf[idx:end], end


def _parse_map_data_info(blob: bytes) -> bytes:
    """Extract and inflate occupancy raster bytes from SCMap mapDataInfo."""
    idx = 0
    while idx < len(blob):
        key, idx = _read_varint(blob, idx)
        field_no = key >> 3
        wire = key & 0x07
        if wire == 0:
            _, idx = _read_varint(blob, idx)
        elif wire == 2:
            value, idx = _read_len_delimited(blob, idx)
            if field_no == 1:
                # mapData is usually zlib-compressed, but we tolerate already
                # inflated payloads to keep fixture/debug paths flexible.
                try:
                    return zlib.decompress(value)
                except zlib.error:
                    return value
        elif wire == 5:
            idx += 4
        else:
            raise RoborockException(f"Unsupported wire type {wire} in B01 map data info")
    raise RoborockException("B01 map payload missing mapData")


def _parse_room_data_info(blob: bytes) -> tuple[int | None, str | None]:
    """Extract room id/name pair from SCMap roomDataInfo entry."""
    room_id: int | None = None
    room_name: str | None = None
    idx = 0
    while idx < len(blob):
        key, idx = _read_varint(blob, idx)
        field_no = key >> 3
        wire = key & 0x07
        if wire == 0:
            value, idx = _read_varint(blob, idx)
            if field_no == 1:
                room_id = int(value)
        elif wire == 2:
            value, idx = _read_len_delimited(blob, idx)
            if field_no == 2:
                room_name = value.decode("utf-8", errors="replace")
        elif wire == 5:
            idx += 4
        else:
            raise RoborockException(f"Unsupported wire type {wire} in B01 room data info")
    return room_id, room_name


def parse_scmap_payload(payload: bytes) -> B01MapData:
    """Parse SCMap protobuf payload and extract occupancy bytes and room names."""

    size_x = 0
    size_y = 0
    grid = b""
    rooms: dict[int, str] = {}
    idx = 0
    while idx < len(payload):
        key, idx = _read_varint(payload, idx)
        field_no = key >> 3
        wire = key & 0x07

        if wire == 0:
            _, idx = _read_varint(payload, idx)
            continue

        if wire != 2:
            if wire == 5:
                idx += 4
                continue
            raise RoborockException(f"Unsupported wire type {wire} in B01 map payload")

        value, idx = _read_len_delimited(payload, idx)

        if field_no == 3:  # mapHead
            hidx = 0
            while hidx < len(value):
                hkey, hidx = _read_varint(value, hidx)
                hfield = hkey >> 3
                hwire = hkey & 0x07
                if hwire == 0:
                    hvalue, hidx = _read_varint(value, hidx)
                    if hfield == 2:
                        size_x = int(hvalue)
                    elif hfield == 3:
                        size_y = int(hvalue)
                elif hwire == 5:
                    hidx += 4
                elif hwire == 2:
                    _, hidx = _read_len_delimited(value, hidx)
                else:
                    raise RoborockException(f"Unsupported wire type {hwire} in B01 map header")
        elif field_no == 4:  # mapDataInfo
            grid = _parse_map_data_info(value)
        elif field_no == 12:  # roomDataInfo (repeated)
            room_id, room_name = _parse_room_data_info(value)
            if room_id is not None:
                rooms[room_id] = room_name or f"Room {room_id}"

    if not size_x or not size_y or not grid:
        raise RoborockException("Failed to parse B01 map header/grid")
    if len(grid) < size_x * size_y:
        raise RoborockException("B01 map data shorter than expected dimensions")
    return B01MapData(size_x=size_x, size_y=size_y, map_data=grid, rooms=rooms or None)


def render_map_png(map_data: B01MapData) -> bytes:
    """Render occupancy map bytes into PNG.

    This intentionally starts with a simple color mapping suitable for a first
    incremental PR. Rich overlays can be layered on top later.
    """

    img = Image.new("RGB", (map_data.size_x, map_data.size_y), (0, 0, 0))
    px = img.load()
    room_colors = [
        (80, 150, 255),
        (255, 170, 80),
        (120, 220, 130),
        (210, 130, 255),
        (255, 120, 170),
        (100, 220, 220),
    ]

    for i, value in enumerate(map_data.map_data[: map_data.size_x * map_data.size_y]):
        x = i % map_data.size_x
        y = map_data.size_y - 1 - (i // map_data.size_x)
        if value == 0:
            color = (0, 0, 0)
        elif value in (1, 127):
            color = (180, 180, 180)
        elif value >= 128:
            color = (255, 255, 255)
        else:
            color = room_colors[(max(value - 2, 0)) % len(room_colors)]
        px[x, y] = color

    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()
