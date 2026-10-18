"""This server's X25519 keypair -- what the patched JP client seals to.

Generated on first use into <JP data dir>/server_key.json (gitignored: the private
scalar is what lets anyone read traffic sealed to this server). Nothing else
needs to know it: the Hachimi plugin fetches the PUBLIC half from arming.py.
"""

from __future__ import annotations

import functools
import json
import os

from .. import region
from . import coneshell as cs


@functools.lru_cache(maxsize=1)
def _load() -> tuple[int, bytes]:
    with region.use_region("jp"):
        key_path = region.data_dir() / "server_key.json"
    if key_path.is_file():
        d = json.loads(key_path.read_text())
        priv = int(d["priv_int"])
    else:
        # Standard X25519 clamping.
        priv = int.from_bytes(os.urandom(32), "little")
        priv &= ~0b111
        priv &= (1 << 255) - 1
        priv |= 1 << 254
        key_path.write_text(json.dumps({"priv_int": str(priv)}))
        os.chmod(key_path, 0o600)
    # BIG-endian: the client reads pre52[0:32] with a big-endian load. Publishing
    # it little-endian yields a wrong-but-plausible key and silent garbage.
    pub = cs.x25519_ladder(priv, 9).to_bytes(32, "big")
    return priv, pub


def private_scalar() -> int:
    return _load()[0]


def public_key() -> bytes:
    return _load()[1]
