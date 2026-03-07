"""Tests for B01/Q7 SCMap parser and renderer."""

from __future__ import annotations

import gzip
from pathlib import Path

from roborock.map.b01_map_parser import parse_scmap_payload, render_map_png

FIXTURE = Path(__file__).resolve().parent / "testdata" / "raw-mqtt-map301.bin.inflated.bin.gz"


def test_parse_scmap_payload_fixture() -> None:
    payload = gzip.decompress(FIXTURE.read_bytes())
    parsed = parse_scmap_payload(payload)
    assert parsed.size_x == 340
    assert parsed.size_y == 300
    assert len(parsed.map_data) >= parsed.size_x * parsed.size_y
    assert parsed.rooms is not None
    assert parsed.rooms.get(10) == "room1"


def test_render_map_png_fixture() -> None:
    payload = gzip.decompress(FIXTURE.read_bytes())
    parsed = parse_scmap_payload(payload)
    png = render_map_png(parsed)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 1024
