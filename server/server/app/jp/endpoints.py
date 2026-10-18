"""The JP-only endpoints, added to the shared pipeline's HANDLERS by server.py.

Everything else a JP client calls goes through exactly the handlers Global
uses (app/dispatch.py), reading JP's own data. What lives here is only what
is JP-specific:

    tool/pre_signup, tool/signup   the auth_key minted here IS the JP transport's
                                   session key (tail50), bound to the device udid
    tool/start_session             Global answers it from a capture; JP has none
    read_info/announce             a Global build this server serves never calls it
    plus every endpoint of a JP-only feature, from app/jp/features/

JP's per-reply header rules that Global's pipeline does not know about are
applied by finish() in server.py.
"""

from __future__ import annotations

import base64
import contextvars
import logging
import os
import secrets

from .. import accounts, config
from .. import state as state_store
from ..handlers import load as load_mod
from ..handlers import account_link

log = logging.getLogger("uma-server")

# The decoded JP request currently being served (set by server.py), for the one
# handler that needs transport facts rather than the payload: signup's udid.
CURRENT_REQUEST: contextvars.ContextVar = contextvars.ContextVar("JP_CURRENT_REQUEST", default=None)

# `WIRE` the real JP server's asset CDNs (tool/start_session, 2.31.0).
SERVER_LIST = {
    "resource_server": "prd-storage-app-umamusume.akamaized.net/dl/",
    "resource_server_cf": "prd-storage-app-umamusume.akamaized.net/dl/",
    "resource_server_login": "prd-storage-app-umamusume.akamaized.net/dl/",
    "resource_server_ingame": "prd-storage-game-umamusume.akamaized.net/dl/",
}

# `WIRE`: data_headers.server_list appears only on these (the handoff counted
# 2,153 real replies; zero of 13 load/index replies carry it, and attaching it
# everywhere killed all menu navigation).
SERVER_LIST_ENDPOINTS = frozenset({
    "tool/get_pre_download_resource_version", "tool/start_session",
    "tool/pre_signup", "tool/signup",
    "account/index", "account/get_by_transition_code",
    "account/chain_by_transition_code", "account/steam_chain_disconnect",
})


def _ok(data: dict) -> dict:
    return {"response_code": 1, "data_headers": {"result_code": 1, "notifications": {}}, "data": data}


def resource_version() -> str:
    return str(config.get("resource_version", ""))


def handle_pre_signup(payload: dict) -> dict:
    # `WIRE` {attest: false, nonce: ""}; JP has no country list (Global's does).
    return _ok({"attest": False, "nonce": ""})


def _mint_viewer_id() -> int:
    while True:
        vid = secrets.randbelow(900_000_000) + 100_000_000
        if accounts.get_account(vid) is None:
            return vid


def handle_signup(payload: dict) -> dict:
    """Global's tool.handle_signup, with JP's credential: auth_key is 50 random
    bytes the client adopts as tail50 (`WIRE`: a real signup's auth_key came
    back byte-for-byte as tail50), stored with the udid that keys the session."""
    decoded = CURRENT_REQUEST.get()
    tail50 = os.urandom(50)
    auth_key = base64.b64encode(tail50).decode()
    viewer_id = _mint_viewer_id()
    accounts.record_signup(viewer_id, auth_key, decoded.udid.hex() if decoded else None)
    # Seed the new account now, as Global does, so the first calls after signup
    # read-modify-write a real blob.
    full_state = state_store.get_state(viewer_id) or {}
    load_mod.get_or_seed_data(full_state, viewer_id)
    state_store.save_state(viewer_id, full_state)
    log.info("JP signup: minted viewer %s", viewer_id)
    return _ok({"viewer_id": viewer_id, "auth_key": auth_key})


def handle_start_session(payload: dict) -> dict:
    """`WIRE` shape: {attest, nonce, terms_updated, is_tutorial, resource_version}.
    is_tutorial follows the account: a client told "not in the tutorial" while
    its load/index says tutorial_step 0 is the handoff's documented save hazard."""
    viewer_id = payload.get("viewer_id")
    full_state = state_store.get_state(viewer_id) or {}
    data = load_mod.get_or_seed_data(full_state, viewer_id)
    state_store.save_state(viewer_id, full_state)
    step = int(((data.get("user_info") or {}).get("tutorial_step")) or 0)
    return _ok({"attest": False, "nonce": "", "terms_updated": False,
                "is_tutorial": step < 1000, "resource_version": resource_version()})


def remember_session(decoded) -> None:
    """Save credentials only after transport verified the request's GCM tag.

    Existing Cygames accounts enter through the plugin rather than signup.
    They still need durable credentials for transition-code recovery.
    """
    viewer_id = decoded.payload.get("viewer_id") if isinstance(decoded.payload, dict) else None
    if viewer_id and decoded.tail50 is not None:
        accounts.record_signup(viewer_id, base64.b64encode(decoded.tail50).decode(),
                               decoded.udid.hex())


def handle_chain_by_transition_code(payload: dict) -> dict:
    decoded = CURRENT_REQUEST.get()
    target_id = payload.get("input_viewer_id")
    target = accounts.get_account(target_id) if target_id else None
    if (decoded is not None and target and not target.get("auth_key")
            and accounts.verify_transition_password(target_id, payload.get("password"))):
        # Older plugin-backed accounts never saved their key. A verified
        # transfer can issue one now, just as JP signup does, without needing
        # the abandoned device's local save or changing the account's state.
        accounts.record_signup(target_id, base64.b64encode(os.urandom(50)).decode(),
                               decoded.udid.hex())
    resp = account_link.handle_chain_by_transition_code(payload)
    if decoded is not None and resp["data_headers"]["result_code"] == 1:
        data = resp["data"]
        # The target auth key moves to the requesting device. Keep the reply
        # sealed with the old session; the NEXT request uses these credentials.
        accounts.record_signup(data["chained_viewer_id"], data["auth_key"], decoded.udid.hex())
    return resp


def handle_announce(payload: dict) -> dict:
    """`WIRE` the real server ACCUMULATES: each call returns every announcement
    read so far (sent 30462 -> [30462], then 30463 -> [30462, 30463]). Kept in
    the same seen-list load.py filters unread_announce_id_array against."""
    viewer_id = payload.get("viewer_id")
    full_state = state_store.get_state(viewer_id) or {}
    seen = full_state.setdefault(load_mod.SEEN_ANNOUNCE_KEY, [])
    for item in payload.get("add_announce_data_array") or []:
        i = item.get("id") if isinstance(item, dict) else item
        if i is not None and i not in seen:
            seen.append(i)
    state_store.save_state(viewer_id, full_state)
    return _ok({"announce_data_array": [{"id": i} for i in seen]})


HANDLERS = {
    "tool/pre_signup": handle_pre_signup,
    "tool/signup": handle_signup,
    "tool/start_session": handle_start_session,
    "account/chain_by_transition_code": handle_chain_by_transition_code,
    "read_info/announce": handle_announce,
}
