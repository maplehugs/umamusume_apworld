"""Practice race and room match, JP's form.

`WIRE` umacap api-20261003-222052-340 (2.31.5): a whole practice race (index,
trial_chara_load, recommend list, follow data, presets, race_start, saved list,
race_end) and a room match session (index, recommend list, presets, create_room,
change_allow_display, polling, destroy_room, room_list, my race conditions,
save_race_condition, entry list, saved results). The shared handlers
(app/handlers/practice_race*.py, room_match.py) run both modes -- presets,
shelves, rooms and the race itself, with the fixes this capture showed Global
needs too. This module answers only where JP's client differs:

  * get_recommend_race_condition_list (both modes): the server's おすすめレース
    presets for upcoming race events. Not in master, so served from the capture
    (seeds/exhibition.json, tools/build_jp_exhibition.py), each while its own
    begin_date..end_date (JST) window is open. A practice preset has no dates;
    it shares the window of the room preset with the same id.
  * trial_chara_load: the captured 体験ウマ娘 roster (use_type 4), until the
    captured next_update_time. After that the real roster has rotated to one we
    have not seen, so the list is empty.
  * Trial charas can be entered: practice race_start entry 0 in the capture is
    trained_chara_id 69, use_type 4, and rooms carry is_allow_trial_character.
    Race rows carry the entry's use_type; preset lists flag a preset whose
    trial chara has rotated out (is_expired_trial_character).
  * My race conditions (room_match/*_race_condition*): 5 saved slots, レース条件N,
    race_condition_detail null until saved. Save/delete/rename answer no data.
  * create_room / entry_room: JP's room settings (max_user_num,
    specified_entry_num, set_easy_option_type, is_allow_trial_character,
    trained_chara_restriction_upper/lower, sp_rule_data_id,
    recommend_condition_id, is_disable_recommend_npc) are kept on the room and
    served on every room_info (after()).
"""

from __future__ import annotations

import copy
import datetime
import functools
import json
import logging
import random
import time

from ... import patch, region, social
from ... import state as state_store
from ...handlers import practice_race, practice_race_lobby
from ...handlers import room_match as rm
from ...result_codes import ResultCode, refuse

log = logging.getLogger("uma-server")

JST = datetime.timezone(datetime.timedelta(hours=9))
USE_TYPE_TRIAL = 4
# Trial charas are the server's, not the account's: their ids must never meet a
# roster id, and the client pairs race rows to trained charas by that id.
TRIAL_ID_BASE = 1_900_000_000
CONDITION_KEY = "jp_room_match_conditions"   # {str(slot): {"name", "detail"}}

# RoomMatchRoomInfo fields JP added; create_room carries them all.
ROOM_EXTRAS = ("max_user_num", "specified_entry_num", "set_easy_option_type",
               "is_allow_trial_character", "trained_chara_restriction_upper",
               "trained_chara_restriction_lower", "sp_rule_data_id",
               "recommend_condition_id", "is_disable_recommend_npc")


def _ok(data=None) -> dict:
    env = {"response_code": 1, "data_headers": {"result_code": 1, "notifications": {}}}
    if data is not None:
        env["data"] = data
    return env


@functools.lru_cache(maxsize=1)
def _seed() -> dict:
    try:
        return json.loads((region.seeds_dir() / "exhibition.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.error("JP: no seeds/exhibition.json -- run tools/build_jp_exhibition.py")
        return {}


def _now() -> datetime.datetime:
    return datetime.datetime.fromtimestamp(patch._servertime(), JST)


def _jst(text: str) -> datetime.datetime:
    text = text.replace("/", "-")
    return datetime.datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)


# ============================================================== recommend ===

def _room_recommend() -> list[dict]:
    now = _now()
    return [p for p in (_seed().get("recommend") or {}).get("room_match") or []
            if _jst(p["race_condition_detail"]["begin_date"]) <= now
            <= _jst(p["race_condition_detail"]["end_date"])]


def handle_room_recommend(payload: dict) -> dict:
    return _ok({"race_condition_preset_info": copy.deepcopy(_room_recommend())})


def handle_practice_recommend(payload: dict) -> dict:
    """PracticeRaceGetRecommendRaceConditionListResponse. The list must be
    present, even when empty: PartsPracticeRaceSetRaceConditionRecommend.Setup
    throws on null and the select-race view waits forever."""
    open_ids = {p["race_condition_preset_id"] for p in _room_recommend()}
    return _ok({"race_condition_preset_info": [
        copy.deepcopy(p) for p in (_seed().get("recommend") or {}).get("practice_race") or []
        if p["race_condition_preset_id"] in open_ids]})


# ================================================================== trial ===

def _next_trial_rotation(now: datetime.datetime) -> datetime.datetime:
    """Friday 11:59:59 JST after now, when no captured roster is current."""
    at = now.replace(hour=11, minute=59, second=59, microsecond=0)
    at += datetime.timedelta(days=(4 - at.weekday()) % 7)
    return at if at > now else at + datetime.timedelta(days=7)


def _trial_live() -> bool:
    nxt = (_seed().get("trial_chara") or {}).get("next_update_time")
    return bool(nxt) and _now() <= _jst(nxt)


def trial_roster(viewer_id) -> list[dict]:
    """The current 体験ウマ娘, owned by the caller as the real server serves them."""
    if not _trial_live():
        return []
    out = []
    for i, c in enumerate(_seed()["trial_chara"]["trial_chara_array"]):
        c = copy.deepcopy(c)
        c["viewer_id"] = social._wire_id(viewer_id)
        c["trained_chara_id"] = TRIAL_ID_BASE + i
        out.append(c)
    return out


def handle_trial_chara_load(payload: dict) -> dict:
    """TrialCharaLoadResponse{trial_chara_array, next_update_time}. A missing
    field hangs the practice race screen (the loader's callback never fires).
    next_update_time is slash-separated, unlike every other JP timestamp."""
    if _trial_live():
        nxt = _seed()["trial_chara"]["next_update_time"]
    else:
        nxt = _next_trial_rotation(_now()).strftime("%Y/%m/%d %H:%M:%S")
    return _ok({"trial_chara_array": trial_roster(payload.get("viewer_id")),
                "next_update_time": nxt})


def resolve_entry(viewer_id, spec: dict) -> dict | None:
    """practice_race.resolve_entry, plus the trial charas (use_type 4)."""
    if int(spec.get("use_type") or 0) == USE_TYPE_TRIAL:
        found = next((c for c in trial_roster(viewer_id)
                      if c["trained_chara_id"] == spec.get("trained_chara_id")), None)
        return copy.deepcopy(found) if found is not None else None
    return practice_race.resolve_entry(viewer_id, spec)


# ========================================================= practice race ===

def handle_practice_race_start(payload: dict) -> dict:
    """The shared race, with trial charas; each row carries its entry's
    use_type (`WIRE`: 4 on the trial chara's row, 0 elsewhere)."""
    resp = practice_race.handle_race_start(payload, resolve=resolve_entry)
    data = resp.get("data")
    if isinstance(data, dict) and "race_result_info" in data:
        use = {c["trained_chara_id"]: int(c.get("use_type") or 0)
               for c in data["trained_chara_array"]}
        for row in data["race_result_info"]["race_horse_data_array"]:
            row["use_type"] = use.get(row["trained_chara_id"], 0)
    return resp


def _flag_expired_trial(handler):
    """is_expired_trial_character: 1 when a preset still holds a trial chara
    that has since rotated out."""
    def handle(payload: dict) -> dict:
        resp = handler(payload)
        data = resp.get("data")
        if isinstance(data, dict) and "preset_info_array" in data:
            trial = {c["trained_chara_id"] for c in trial_roster(payload.get("viewer_id"))}
            data["is_expired_trial_character"] = int(any(
                int(c.get("use_type") or 0) == USE_TYPE_TRIAL
                and c.get("trained_chara_id") not in trial
                for p in data["preset_info_array"] for c in p.get("preset_chara_array") or []))
        return resp
    return handle


# ====================================================== my race conditions ===

def _conditions(full_state: dict) -> dict:
    st = full_state.get(CONDITION_KEY)
    if not isinstance(st, dict):
        st = full_state[CONDITION_KEY] = {}
    return st


def _condition_slot(payload: dict):
    slot = int(payload.get("my_race_condition_id") or 0)
    return slot if 1 <= slot <= int(_seed().get("my_race_condition_slots") or 0) else None


def handle_get_my_race_condition_list(payload: dict) -> dict:
    st = _conditions(state_store.get_state(payload.get("viewer_id")) or {})
    pattern = _seed().get("my_race_condition_name") or ""
    out = []
    for i in range(1, int(_seed().get("my_race_condition_slots") or 0) + 1):
        slot = st.get(str(i)) or {}
        out.append({"race_condition_preset_id": i,
                    "race_condition_preset_name": slot.get("name") or pattern.format(n=i),
                    "race_condition_detail": copy.deepcopy(slot.get("detail"))})
    return _ok({"race_condition_preset_info": out})


def _edit_condition(edit):
    def handle(payload: dict) -> dict:
        slot = _condition_slot(payload)
        if slot is None:
            return refuse(ResultCode.PARAM_ERROR)
        vid = payload.get("viewer_id")
        full_state = state_store.get_state(vid) or {}
        st = _conditions(full_state)
        st[str(slot)] = edit(dict(st.get(str(slot)) or {}), payload)
        state_store.save_state(vid, full_state)
        return _ok()
    return handle


handle_save_race_condition = _edit_condition(
    lambda s, p: {**s, "detail": copy.deepcopy(p.get("race_condition_detail"))})
handle_delete_race_condition = _edit_condition(lambda s, p: {})
handle_change_race_condition_name = _edit_condition(
    lambda s, p: {**s, "name": str(p.get("race_condition_name") or "")[:32]})


# ============================================================= room match ===

def _room_entries(vid, entries, room: dict) -> list[dict] | int:
    """rm._entry_charas with JP's trial charas and rank window."""
    entries = [e for e in (entries or []) if e.get("trained_chara_id")]
    cap = room.get("specified_entry_num") or rm.MAX_CHARAS_PER_USER
    if not entries or len(entries) > cap:
        return ResultCode.PARAM_ERROR
    upper, lower = room["trained_chara_restriction_upper"], room["trained_chara_restriction_lower"]
    out = []
    for i, e in enumerate(entries):
        if int(e.get("use_type") or 0) == USE_TYPE_TRIAL and not room["is_allow_trial_character"]:
            return ResultCode.PARAM_ERROR
        chara = resolve_entry(vid, {**e, "viewer_id": None})
        rank = (chara or {}).get("rank") or 1
        if (chara is None or not rm._allowed(room, chara)
                or (upper and rank > upper) or (lower and rank < lower)):
            log.warning("JP room_match: %s cannot enter %s", vid, e.get("trained_chara_id"))
            return ResultCode.PARAM_ERROR
        chara["viewer_id"] = social._wire_id(vid)
        if e.get("running_style"):
            chara["running_style"] = e["running_style"]
        chara["member_id"] = e.get("member_id") or i + 1
        chara["race_dress_id"] = chara.get("race_cloth_id") or chara.get("race_dress_id")
        out.append(chara)
    return out


def handle_create_room(payload: dict) -> dict:
    """rm._create with JP's settings. JP limits rank with
    trained_chara_restriction_upper/lower and sends restriction 0."""
    vid = str(payload.get("viewer_id"))
    race_instance_id = int(payload.get("race_instance_id") or 0)
    course_max = rm._course_entry_num(race_instance_id)
    if not course_max:
        return refuse(ResultCode.PARAM_ERROR)
    entry_num = max(1, min(int(payload.get("entry_num") or course_max), course_max))
    private_num = int(payload.get("private_entry_num") or 0) \
        if payload.get("private_entry_type") else 0
    now = time.time()
    room = {
        "host": vid, "race_instance_id": race_instance_id,
        "room_name": str(payload.get("room_name") or ""),
        "message": str(payload.get("message") or ""),
        "season": int(payload.get("season") or 0),
        "weather": int(payload.get("weather") or 0),
        "ground_condition": int(payload.get("ground_condition") or 0),
        "motivation": int(payload.get("motivation") or 0),
        "entry_num": entry_num,
        "private_entry_type": int(payload.get("private_entry_type") or 0),
        "private_entry_num": max(0, min(private_num, entry_num)),
        "is_allow_watching": 1 if payload.get("is_allow_watching") else 0,
        "trained_chara_restriction": int(payload.get("restriction") or 0),
        "restriction_type": int(payload.get("restriction_type") or 0),
        "restrict_chara_info_array": list(payload.get("restrict_chara_info_array") or []),
        "is_allow_display": 1 if payload.get("is_allow_display_flag") else 0,
        "start_time_type": int(payload.get("start_time_type") or rm.START_TIME_TYPE_SIMPLE),
        "random_seed": random.randint(1, 2**31 - 1),
        "register_ts": now, "members": {}, "audience": {}, "checked": [], "race": None,
        **{k: int(payload.get(k) or 0) for k in ROOM_EXTRAS},
    }
    room["start_ts"] = now + rm._START_DELAY.get(room["start_time_type"], rm._START_DELAY[1])
    charas = _room_entries(vid, payload.get("entry_chara_array"), room)
    if isinstance(charas, int):
        return refuse(charas)
    if len(charas) > entry_num:
        return refuse(ResultCode.ROOM_MATCH_ENTRY_NUM_OVER_ERROR)
    room["members"][vid] = {"register_ts": now, "charas": [
        {"chara": c, "join_type": rm.ENTRY_NORMAL} for c in charas]}
    with rm._db() as conn:
        room["room_id"] = rm._new_room_id(conn)
        rm._save_room(conn, room)
    log.info("JP room_match: %s opened room %s (race %s, %s gates)",
             vid, room["room_id"], race_instance_id, entry_num)
    return _ok(rm._lobby(room, vid))


def handle_entry_room(payload: dict) -> dict:
    """rm.handle_entry_room with JP's trial charas, rank window and trainer cap
    (max_user_num, 0 = no cap)."""
    vid = str(payload.get("viewer_id"))
    with rm._db() as conn:
        room = rm._load_room(conn, payload.get("room_id"))
        if room is None:
            return refuse(ResultCode.ROOM_MATCH_NO_ROOM_ERROR)
        room = {**{k: 0 for k in ROOM_EXTRAS}, **room}
        if rm._started(room):
            return refuse(ResultCode.ROOM_MATCH_ENTRY_OVERTIME_ERROR)
        charas = _room_entries(vid, payload.get("entry_chara_array"), room)
        if isinstance(charas, int):
            return refuse(charas)
        room["members"].pop(vid, None)
        if room["max_user_num"] and len(room["members"]) + 1 > room["max_user_num"]:
            return refuse(ResultCode.ROOM_MATCH_ENTRY_NUM_OVER_ERROR)
        normal_free = (room["entry_num"] - room["private_entry_num"]
                       - rm._entrant_count(room, private=False))
        private_free = (room["private_entry_num"] - rm._entrant_count(room, private=True)
                        if rm._qualifies_private(room, vid) else 0)
        if len(charas) > max(0, normal_free) + max(0, private_free):
            return refuse(ResultCode.ROOM_MATCH_ENTRY_NUM_OVER_ERROR)
        placed = []
        for c in charas:
            kind = rm.ENTRY_NORMAL if normal_free > 0 else rm.ENTRY_PRIVATE
            normal_free -= kind == rm.ENTRY_NORMAL
            placed.append({"chara": c, "join_type": kind})
        room["members"][vid] = {"register_ts": time.time(), "charas": placed}
        room["audience"].pop(vid, None)
        rm._save_room(conn, room)
    return _ok({"room_info": rm._room_info(room, vid),
                "room_user_detail_array": [rm._room_user(room, v, rm.USER_ENTRY)
                                           for v in room["members"]]})


def _room_extras(conn, vid: str, room_id) -> dict:
    room = rm._load_room(conn, room_id)
    if room is None:
        row = conn.execute("SELECT data FROM saved_result WHERE viewer_id=? AND "
                           "saved_room_id=?", (vid, int(room_id))).fetchone()
        room = json.loads(row["data"])["room"] if row else {}
    return {k: int(room.get(k) or 0) for k in ROOM_EXTRAS}


def after(endpoint: str, payload: dict, resp: dict) -> None:
    """Serve JP's room settings on every room_info a room_match reply carries."""
    data = resp.get("data")
    if not endpoint.startswith("room_match/") or not isinstance(data, dict):
        return
    infos = [data.get("room_info"), data.get("race_result"),
             *(data.get("room_info_array") or ()), *(data.get("race_result_array") or ())]
    infos = [i for i in infos if isinstance(i, dict) and i.get("room_id")]
    if not infos:
        return
    vid = str(payload.get("viewer_id"))
    with rm._db() as conn:
        for info in infos:
            info.update(_room_extras(conn, vid, info["room_id"]))


HANDLERS = {
    "trial_chara/trial_chara_load": handle_trial_chara_load,
    "practice_race/get_recommend_race_condition_list": handle_practice_recommend,
    "practice_race/race_start": handle_practice_race_start,
    "practice_race/get_preset_array": _flag_expired_trial(
        practice_race_lobby.handle_get_preset_array),
    "room_match/get_recommend_race_condition_list": handle_room_recommend,
    "room_match/get_preset_array": _flag_expired_trial(rm.handle_get_preset_array),
    "room_match/get_my_race_condition_list": handle_get_my_race_condition_list,
    "room_match/save_race_condition": handle_save_race_condition,
    "room_match/delete_race_condition": handle_delete_race_condition,
    "room_match/change_race_condition_name": handle_change_race_condition_name,
    "room_match/create_room": handle_create_room,
    "room_match/entry_room": handle_entry_room,
}
