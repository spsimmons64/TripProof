###################################################################################################
# PHI encryption - AES-256-GCM with versioned keys.
#
# Sealed text is "v<keyversion>:<base64(nonce || ciphertext || tag)>". The key version travels with
# the data, so rotating keys means adding a new version to PHI_KEYS; old rows still open, new rows
# seal with the newest key. The associated data binds a ciphertext to its owner (e.g.
# "leg:<recordid>"), so a PHI blob copied onto another row fails to decrypt instead of leaking.
###################################################################################################
import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


def _load_keys(spec: str) -> dict[int, bytes]:
    keys = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        version, b64 = part.split(":", 1)
        key = base64.b64decode(b64)
        if len(key) != 32:
            raise ValueError(f"PHI key version {version} is not 32 bytes")
        keys[int(version)] = key
    if not keys:
        raise ValueError("PHI_KEYS is empty")
    return keys


_KEYS = _load_keys(settings.phi_keys)
CURRENT_VERSION = max(_KEYS)


def seal_bytes(data: bytes, aad: str) -> tuple[int, bytes]:
    nonce = os.urandom(12)
    ct = AESGCM(_KEYS[CURRENT_VERSION]).encrypt(nonce, data, aad.encode())
    return CURRENT_VERSION, nonce + ct


def open_bytes(version: int, blob: bytes, aad: str) -> bytes:
    return AESGCM(_KEYS[version]).decrypt(blob[:12], blob[12:], aad.encode())


def seal_json(obj, aad: str) -> tuple[int, str]:
    version, blob = seal_bytes(json.dumps(obj, default=str).encode(), aad)
    return version, base64.b64encode(blob).decode()


def open_json(version: int, payload: str, aad: str):
    return json.loads(open_bytes(version, base64.b64decode(payload), aad))
