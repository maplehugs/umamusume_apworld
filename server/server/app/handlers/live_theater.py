"""Live Theater (concerts). Wire format decoded from the 2026-07-26 real
capture (two concerts, request-shift bug corrected against _preshift_backup):

- live_theater/index: request is boilerplate-only; response carries ONLY the
  per-song SAVED FORMATIONS (live_theater_save_info_array) plus a rolling
  live_theater_last_checked_time (each call returns the PREVIOUS visit's
  servertime and stores 'now'). The selectable song list itself is
  client-derived from master live_data x the owned music_list we already
  serve dynamically (collection.py music_list_state).

- live_theater/live_start: request = {live_theater_save_info {music_id,
  member_info_array, is_skip_story}, live_theater_setting_info,
  live_theater_vocal_chara_id_array}; response data = a VERBATIM ECHO of the
  submitted live_theater_save_info. No rewards/RNG -- the client runs the
  concert locally; the server's job is persisting the formation so index
  serves it back (vocals may be non-members; nothing else to validate).

  Unlocking is NOT done here. Songs are granted on their real conditions
  where the real server grants them (app/concerts.py); this handler only
  persists formations. (It used to add any song the client asked to play --
  user-directed 2026-08-19, replaced 2026-09-30 by the real conditions.)

These must stay real handlers (not fixture replay): the auto-indexed capture
of this session has label-shifted REQUEST bodies, so replay would serve a
frozen formation for a song the account may not even own."""

from __future__ import annotations

import copy

from .. import state as state_store
from ..patch import _servertime

SAVE_KEY = "live_theater_save_state"          # [save_info, ...] in insertion order
CHECK_KEY = "live_theater_last_checked_time"  # int (previous visit's servertime)


def _ok(data: dict) -> dict:
    return {"response_code": 1,
            "data_headers": {"result_code": 1, "notifications": {}}, "data": data}


def handle_index(payload: dict) -> dict:
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    now = _servertime()
    last = full_state.get(CHECK_KEY) or now
    full_state[CHECK_KEY] = now
    state_store.save_state(viewer_id, full_state)
    return _ok({
        "live_theater_save_info_array": copy.deepcopy(full_state.get(SAVE_KEY) or []),
        "live_theater_last_checked_time": last,
    })


def handle_live_start(payload: dict) -> dict:
    viewer_id = payload["viewer_id"]
    save_info = payload.get("live_theater_save_info") or {}
    full_state = state_store.get_state(viewer_id) or {}
    music_id = save_info.get("music_id")
    if music_id is not None:
        saves = [s for s in (full_state.get(SAVE_KEY) or [])
                 if s.get("music_id") != music_id]
        saves.append(copy.deepcopy(save_info))
        full_state[SAVE_KEY] = saves
        state_store.save_state(viewer_id, full_state)
    return _ok({"live_theater_save_info": copy.deepcopy(save_info)})
