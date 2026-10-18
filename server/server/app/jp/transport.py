"""JP transport, server side -- the twin of app/crypto.py.

    open_request(raw, headers, priv, sessions) -> DecodedRequest
    seal_reply(payload, decoded)               -> bytes (the reply wire)
    encode_http_body(wire)                     -> bytes (what goes in the HTTP body)

Global's client puts the key in the packet, so app/crypto.py needs no secret.
JP's client seals to an X25519 public key, so this needs (a) OUR private key --
the Hachimi plugin makes the client seal to our public key instead of
Cygames' -- and (b) per-viewer session state: udid + the tail50 the server
issued as `auth_key` at signup.

Two envelope types, and the WIRE says which (not an endpoint list):
    0xA6 session   ordinary calls         reply key MD5(sbox||sid||tail50[34:50])
    0x74 boundary  pre_signup / signup    reply key MD5(sbox||sid||udid)
ctr_header decrypts under sbox to a plaintext whose first byte is the type
(0x01 / 0x00), so the server just looks. Getting this wrong is the handoff's
documented seven-week bug: every reply fails and it reads like a server-side
policy rejection.

On this transport a wrong key yields plausible garbage, not an error. Here
every layer is checked (ctr type byte, tail50 echo, GCM tag), so a mismatch
fails loudly at the layer that is actually wrong.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import os
import struct
from dataclasses import dataclass, field
from typing import Iterable, Protocol

import lz4.block
import msgpack

from . import coneshell as cs

JP_SALT = b"r!I@mt8e5i="
SESSION, BOUNDARY = 0xA6, 0x74

# pre52[32:52]: a 20-byte per-BUILD constant the client mixes into the request
# key and AAD. It is never transmitted, rotates on client updates, and a stale
# value fails exactly like a wrong identity (GCM tag mismatch). The Hachimi
# plugin reports the live value (see arming.py); these are the builds we have
# measured, newest first, so a request opens even before the plugin reports.
KNOWN_TAIL20 = (
    bytes.fromhex("fed5204454857f24ba09fad010e2c988c5684b90"),  # iOS build, reported 2026-10-10
    bytes.fromhex("964f11a0cc8024c558877ef091bedc8337df0a6b"),  # 2.31.0  `WIRE` 2026-09-18 capture
    bytes.fromhex("84ab20d67f3ca2b3f72a573718f21e341739e2ec"),  # 2.30.5
    bytes.fromhex("4f5aeedd2b55b29f6a072b59fc01ed2604e17d5d"),  # 2.30.0
)

# The real server LZ4-compresses reply bodies over this size and sends small
# ones raw with out_size == 0 (`WIRE`: largest raw 504 B, smallest LZ4 526 B).
COMPRESS_OVER = 512


class WrongKey(Exception):
    """ctr_header did not open to a valid type byte: the client did not seal to
    our public key (plugin not loaded / not armed)."""


class BadRequest(Exception):
    """Malformed wire, unknown session, or a GCM tag that no build tail opens."""


@dataclass
class Session:
    udid: bytes
    tail50: bytes

    @property
    def tail16(self) -> bytes:
        return self.tail50[34:50]


class SessionSource(Protocol):
    def session_for(self, viewer_id: str) -> Session | None: ...
    def tail20_candidates(self) -> Iterable[bytes]: ...


@dataclass
class DecodedRequest:
    payload: dict
    sid: bytes
    udid: bytes
    kind: int
    sbox: bytes
    tail16: bytes | None = None
    tail20: bytes = field(default=b"", repr=False)
    tail50: bytes | None = field(default=None, repr=False)


def make_sid(viewer_id, udid_str: str) -> bytes:
    """The client's first SID of a session."""
    return hashlib.md5((str(viewer_id) + udid_str).encode() + JP_SALT).digest()


def next_sid(resp_sid: str) -> bytes:
    """The SID the client sends after a reply carrying data_headers.sid."""
    return hashlib.md5(resp_sid.encode() + JP_SALT).digest()


def open_request(raw: bytes, headers: dict, priv_scalar: int,
                 sessions: SessionSource) -> DecodedRequest:
    """Decrypt one JP request. `raw` is the HTTP body (base64 of the wire)."""
    try:
        wire = base64.b64decode(raw, validate=True)
    except Exception as exc:                                   # noqa: BLE001
        raise BadRequest(f"body is not base64: {exc}") from exc
    if len(wire) < 0x58:
        raise BadRequest(f"wire too short ({len(wire)} B)")

    ec_export, ctr_header, tag, ct = wire[0x04:0x24], wire[0x24:0x48], wire[0x48:0x58], wire[0x58:]
    declared = struct.unpack_from("<I", wire, 0)[0]
    if declared != len(ct) + 0x58 - 4:
        raise BadRequest(f"length field {declared} != {len(ct) + 0x58 - 4}")

    sbox = cs.x25519_ladder(priv_scalar, int.from_bytes(ec_export, "little")).to_bytes(32, "little")
    ctr_pt = cs.ctr_crypt(sbox, ec_export, ctr_header)
    kind = {0x01: SESSION, 0x00: BOUNDARY}.get(ctr_pt[0])
    if kind is None or ctr_pt[1] != 0x00:
        raise WrongKey(f"ctr_header opened to {ctr_pt[:2].hex()} -- the client did not seal to our key")

    h = {k.lower(): v for k, v in headers.items()}
    try:
        sid = bytes.fromhex(h.get("sid") or "")
    except ValueError as exc:
        raise BadRequest("SID header is not hex") from exc
    if len(sid) != 16:
        raise BadRequest("request has no 16-byte SID header")

    if kind == BOUNDARY:
        # Self-describing: the udid rides in the ctr plaintext.
        udid, tail16 = ctr_pt[2:18], None
        md5hdr = udid
    else:
        viewer = str(h.get("viewerid") or "0")
        sess = sessions.session_for(viewer)
        # The same account can play from another device (an iPhone next to the
        # PC): its session is the one the plugin reported, not the stored one.
        if sess is not None and ctr_pt[2:36] != sess.tail50[0:34]:
            for alt in getattr(sessions, "reported_sessions", lambda: [])():
                if ctr_pt[2:36] == alt.tail50[0:34]:
                    sess = alt
                    break
        if sess is None:
            raise BadRequest(f"0xA6 request for viewer {viewer} with no known session "
                             "(no signup here, and the plugin has not reported one)")
        # ctr_pt[2:36] is the client's tail50[0:34]: catch a desynced session
        # here, not as an unreadable reply later.
        if ctr_pt[2:36] != sess.tail50[0:34]:
            raise BadRequest(f"tail50 mismatch for viewer {viewer}")
        udid, tail16 = sess.udid, sess.tail16
        md5hdr = hashlib.md5(sid + tail16 + udid).digest()

    iv = hashlib.md5(ec_export + sid + udid).digest()
    seen: set[bytes] = set()
    for tail20 in (*sessions.tail20_candidates(), *KNOWN_TAIL20):
        if tail20 in seen:
            continue
        seen.add(tail20)
        key = hashlib.md5(cs.spn_whiten(sbox, md5hdr, tail20[0:16]) + sbox + md5hdr + tail20).digest()
        body = cs.gcm_open(key, iv, ct, tag, tail20 + sid + udid)
        if body is not None:
            payload = msgpack.unpackb(body, raw=False, strict_map_key=False)
            return DecodedRequest(payload=payload, sid=sid, udid=udid, kind=kind,
                                  sbox=sbox, tail16=tail16, tail20=tail20,
                                  tail50=sess.tail50 if kind == SESSION else None)
    raise BadRequest("GCM tag mismatch under every known build tail "
                     "(new client build? the plugin reports the live tail20)")


def seal_reply(payload: dict, decoded: DecodedRequest) -> bytes:
    """The reply wire: [LE32 out_size][IV 16][tag 16][ct], out_size 0 = not compressed."""
    body = msgpack.packb(payload, use_bin_type=True)
    if len(body) > COMPRESS_OVER:
        pt, out_size = lz4.block.compress(body, store_size=False), len(body)
    else:
        pt, out_size = body, 0
    tail = decoded.udid if decoded.kind == BOUNDARY else decoded.tail16
    key = cs.derive_key(decoded.sbox, decoded.sid, tail)
    iv = os.urandom(16)
    ct, tag = cs.gcm_seal(key, iv, pt, decoded.sid + tail)
    return struct.pack("<I", out_size) + iv + tag + ct


def encode_http_body(wire: bytes, accept_encoding: str) -> tuple[bytes, dict]:
    """The HTTP reply body + extra headers. `WIRE` (TLS proxy in front of the
    real server): replies are gzip(base64(wire)) with Content-Encoding: gzip --
    requests are base64 WITHOUT gzip, and mirroring the request side is what
    kept the handoff's first local login dead for an evening."""
    out = base64.b64encode(wire)
    if "gzip" in (accept_encoding or "").lower():
        return gzip.compress(out), {"Content-Encoding": "gzip"}
    return out, {}
