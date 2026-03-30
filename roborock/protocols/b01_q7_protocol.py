"""Roborock B01 Protocol encoding and decoding."""

import json
from dataclasses import dataclass, field
from typing import Any

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from roborock import RoborockB01Q7Methods
from roborock.exceptions import RoborockException
from roborock.protocol import Utils
from roborock.roborock_message import RoborockMessage, RoborockMessageProtocol
from roborock.util import get_next_int

B01_VERSION = b"B01"
B01_Q7_DPS = 10000
CommandType = RoborockB01Q7Methods | str
ParamsType = list | dict | int | None


@dataclass
class Q7RequestMessage:
    """Data class for B01 Q7 request message."""

    dps: int
    command: CommandType
    params: ParamsType
    msg_id: int = field(default_factory=lambda: get_next_int(100000000000, 999999999999))

    def to_dps_value(self) -> dict[int, Any]:
        """Return the 'dps' payload dictionary."""
        return {
            self.dps: {
                "method": str(self.command),
                "msgId": str(self.msg_id),
                # Important: some B01 methods use an empty object `{}` (not `[]`) for
                # "no params", and some setters legitimately send `0` which is falsy.
                # Only default to `[]` when params is actually None.
                "params": self.params if self.params is not None else [],
            }
        }


def encode_mqtt_payload(request: Q7RequestMessage) -> RoborockMessage:
    """Encode payload for B01 commands over MQTT."""
    dps_data = {"dps": request.to_dps_value()}
    payload = pad(json.dumps(dps_data).encode("utf-8"), AES.block_size)
    return RoborockMessage(
        protocol=RoborockMessageProtocol.RPC_REQUEST,
        version=B01_VERSION,
        payload=payload,
    )


def decode_rpc_response(message: RoborockMessage) -> dict[int, Any]:
    """Decode a B01 RPC_RESPONSE message."""
    if not message.payload:
        raise RoborockException("Invalid B01 message format: missing payload")
    try:
        unpadded = unpad(message.payload, AES.block_size)
    except ValueError:
        # It would be better to fail down the line.
        unpadded = message.payload

    try:
        payload = json.loads(unpadded.decode())
    except (json.JSONDecodeError, TypeError) as e:
        raise RoborockException(f"Invalid B01 message payload: {e} for {message.payload!r}") from e

    datapoints = payload.get("dps", {})
    if not isinstance(datapoints, dict):
        raise RoborockException(f"Invalid B01 message format: 'dps' should be a dictionary for {message.payload!r}")
    try:
        return {int(key): value for key, value in datapoints.items()}
    except ValueError:
        raise RoborockException(f"Invalid B01 message format: 'dps' key should be an integer for {message.payload!r}")


def decode_map_response_payload(raw_payload: bytes, *, serial: str, model: str, compressed: bool = True) -> bytes:
    """Decode a raw B01/Q7 ``MAP_RESPONSE`` payload into SCMap bytes.

    Transport decoding lives here rather than in the map parser so the parser
    only deals with protobuf/map semantics.
    """
    return Utils.decode_b01_aes_hex_payload(
        raw_payload,
        Utils.derive_b01_map_key(serial, model),
        compressed=compressed,
        context="B01 map payload",
    )
