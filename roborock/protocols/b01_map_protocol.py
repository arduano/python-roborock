"""B01/Q7 map transport decoding helpers."""

import base64
import binascii
import hashlib
import zlib

from Crypto.Cipher import AES

from roborock.exceptions import RoborockException
from roborock.protocol import Utils


def derive_map_key(serial: str, model: str) -> bytes:
    """Derive the B01/Q7 map decrypt key from serial + model."""
    model_suffix = model.split(".")[-1]
    model_key = (model_suffix + "0" * 16)[:16].encode()
    material = f"{serial}+{model_suffix}+{serial}".encode()
    encrypted = Utils.encrypt_ecb(material, model_key)
    md5 = hashlib.md5(base64.b64encode(encrypted), usedforsecurity=False).hexdigest()
    return md5[8:24].encode()


def decode_map_response(raw_payload: bytes, *, serial: str, model: str) -> bytes:
    """Decode raw B01 ``MAP_RESPONSE`` payload into inflated SCMap bytes."""
    encrypted_payload = _decode_base64_payload(raw_payload)
    if len(encrypted_payload) % AES.block_size != 0:
        raise RoborockException("Unexpected encrypted B01 map payload length")

    map_key = derive_map_key(serial, model)

    try:
        compressed_hex = Utils.decrypt_ecb(encrypted_payload, map_key).decode("ascii")
        compressed_payload = bytes.fromhex(compressed_hex)
        return zlib.decompress(compressed_payload)
    except (ValueError, UnicodeDecodeError, zlib.error) as err:
        raise RoborockException("Failed to decode B01 map payload") from err


def _decode_base64_payload(raw_payload: bytes) -> bytes:
    blob = raw_payload.strip()
    padded = blob + b"=" * (-len(blob) % 4)
    try:
        return base64.b64decode(padded, validate=True)
    except binascii.Error as err:
        raise RoborockException("Failed to decode B01 map payload") from err
