"""Schedule Book settings (スケジュール帳): the presets its one-tap run uses for
daily races, daily legend races, Team Trials, jobs and const walking.

`WIRE` 2.31.0 (jp_captures/CarrotJuicer, 19 setting / 168 index / 90 jobs
start / 64 go_walking / 11 jobs index replies):

  schedule_book/setting {schedule_book_setting} -> data null; the struct is
    stored as sent.
  schedule_book/index's schedule_book_setting is the stored struct (163/165;
    both misses follow capture gaps of 19 h and 54 h), with two later writers:
    jobs/start replaces schedule_book_jobs_card_setting with its reply's
    schedule_book_setting (81/90 equal to the stored one already), and a
    const_walking/go_walking sets schedule_book_const_walking_setting.
    selected_chara_id to the walked character.
  jobs/index's schedule_book_setting is the stored jobs card setting (11/11);
  jobs.py reads and writes it.

An account that never saved one keeps the empty shape schema.py fills.
schedule_book/start (running the presets) is not built here.
"""

from __future__ import annotations

import copy

from ... import state as state_store
from ...result_codes import refuse

KEY = "jp_schedule_book_setting"


def stored(full_state: dict) -> dict | None:
    value = full_state.get(KEY)
    return value if isinstance(value, dict) else None


def handle_setting(payload: dict) -> dict:
    setting = payload.get("schedule_book_setting")
    if not isinstance(setting, dict):
        return refuse()
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    full_state[KEY] = copy.deepcopy(setting)
    state_store.save_state(viewer_id, full_state)
    return {"response_code": 1, "data_headers": {"result_code": 1, "notifications": {}},
            "data": None}


def handle_index(payload: dict) -> dict:
    """schema.py completes daily_race_info .. const_walking_info to the real
    shape; this adds the stored presets."""
    setting = stored(state_store.get_state(payload["viewer_id"]) or {})
    data = {"schedule_book_setting": copy.deepcopy(setting)} if setting else {}
    return {"response_code": 1, "data_headers": {"result_code": 1, "notifications": {}},
            "data": data}


def note_walk(full_state: dict, chara_id: int) -> None:
    """A walk makes its character the preset's walking character."""
    setting = stored(full_state)
    walking = (setting or {}).get("schedule_book_const_walking_setting")
    if isinstance(walking, dict):
        walking["selected_chara_id"] = int(chara_id)


HANDLERS = {
    "schedule_book/setting": handle_setting,
    "schedule_book/index": handle_index,
}
