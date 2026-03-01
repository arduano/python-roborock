"""Protocol-level B01 map payload decoding utilities.

This module is intentionally limited to transport/protocol decoding steps
(base64 layers, AES layers, zlib inflation). SCMap parsing lives in
``roborock.map.b01_map_parser``.
"""

from __future__ import annotations

import base64
import hashlib
import zlib

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from roborock.exceptions import RoborockException

_B01_HASH = "5wwh9ikChRjASpMU8cxg7o1d2E"


def _derive_b01_iv(iv_seed: int) -> bytes:
    random_hex = iv_seed.to_bytes(4, "big").hex().lower()
    md5 = hashlib.md5((random_hex + _B01_HASH).encode(), usedforsecurity=False).hexdigest()
    return md5[9:25].encode()


def derive_map_key(serial: str, model: str) -> bytes:
    """Derive map decrypt key for B01/Q7 map payloads."""

    model_suffix = model.split(".")[-1]
    model_key = (model_suffix + "0" * 16)[:16].encode()
    material = f"{serial}+{model_suffix}+{serial}".encode()
    encrypted = AES.new(model_key, AES.MODE_ECB).encrypt(pad(material, AES.block_size))
    md5 = hashlib.md5(base64.b64encode(encrypted), usedforsecurity=False).hexdigest()
    return md5[8:24].encode()


def _maybe_b64(data: bytes) -> bytes | None:
    try:
        return base64.b64decode(data, validate=False)
    except Exception:
        return None


def decode_b01_map_payload(raw_payload: bytes, *, local_key: str, serial: str, model: str) -> bytes:
    """Decode raw B01 MAP_RESPONSE payload into inflated SCMap protobuf bytes."""

    layers: list[bytes] = []
    l0 = _maybe_b64(raw_payload)
    if l0 is not None:
        layers.append(l0)
        l1 = _maybe_b64(l0)
        if l1 is not None:
            layers.append(l1)
    else:
        layers.append(raw_payload)

    map_key = derive_map_key(serial, model)
    for layer in layers:
        candidates: list[bytes] = [layer]

        # Optional B01 envelope for local-key CBC decryption.
        if len(layer) > 19 and layer[:3] == b"B01":
            iv_seed = int.from_bytes(layer[7:11], "big")
            payload_len = int.from_bytes(layer[17:19], "big")
            encrypted = layer[19 : 19 + payload_len]
            try:
                decrypted = AES.new(local_key.encode(), AES.MODE_CBC, _derive_b01_iv(iv_seed)).decrypt(encrypted)
                candidates.append(unpad(decrypted, 16))
            except Exception:
                pass

        # Optional map-key ECB layer seen in Q7 payloads.
        for candidate in list(candidates):
            if len(candidate) % 16 == 0:
                try:
                    decrypted = AES.new(map_key, AES.MODE_ECB).decrypt(candidate)
                    candidates.append(decrypted)
                    candidates.append(unpad(decrypted, 16))
                except Exception:
                    pass

        for candidate in candidates:
            variants = [candidate]
            try:
                text = candidate.decode("ascii").strip()
                if len(text) > 16 and all(char in "0123456789abcdefABCDEF" for char in text[:32]):
                    variants.append(bytes.fromhex(text))
            except Exception:
                pass
            for variant in variants:
                try:
                    return zlib.decompress(variant)
                except zlib.error:
                    continue

    raise RoborockException("Failed to decode B01 map payload")
