"""Archipelago: this server plays an Archipelago multiworld seed (the apworld
is github.com/maplehugs/umamusume_apworld). There is no switch: every account
is an Archipelago account -- URA only until the multiworld sends a scenario,
no scouting, the seed's starting trainees.

The connection (client.py, settings in client_config.json:
archipelago_server / archipelago_slot / archipelago_password) plays for the
account that logged in last. The seed is remembered in that account's save;
a connection that reports a DIFFERENT seed wipes the save and starts it over
from a fresh account under the same profile (name, tutorial). Nothing from an
older seed is kept. Items from the multiworld arrive as mail (cards, trainees,
crystals), as permanent buffs (career start, training gains, failure rate), or
as one-shot boons and traps on the next career. Locations ("checks") are G1
wins, finished careers per scenario and rank tier, a global rank ladder, a
finished career per trainee, N different races won, fans and Team Trials race
wins. The goal is a career at or above the seed's rank score, N distinct G1s,
or every scenario.

The Legend Race rival ladder (legend_ladder) runs each rung as its own legend
race event: sync_legend_events keeps the ladder's events running in the game's
master.mdb (the client shows a Legend Race only while its master dates say so).

State lives in full_state[AP_KEY].
"""

from __future__ import annotations

import logging
import math
import json
import os
import queue
import random
import shutil
import sqlite3
import time
from pathlib import Path

from .. import accounts, master_data, region
from .. import state as state_store
from . import tables

log = logging.getLogger("uma-server")

AP_KEY = "archipelago"
STAT_FIELDS = ("speed", "stamina", "power", "guts", "wiz")
_STAT_TARGET_TYPE = dict(zip(STAT_FIELDS, range(1, 6)))  # params_inc_dec target_type
_ITEM_NAMES = {v: k for k, v in tables.item_name_to_id().items()}
_LOCATION_IDS = tables.location_name_to_id()
_G1_BY_RACE = {rid: name for name, ids in tables.G1_RACES.items() for rid in ids}
_BAD_CONDITIONS = (1, 2, 3, 5, 6)  # Night Owl, Slacker, Skin Outbreak, Migraine, Practice Poor
_GOOD_CONDITIONS = (8, 10)  # Charming, Practice Perfect
_JUNIOR_LAST_TURN = 24
_FINAL_TURN = 78  # every scenario's final race (URA's Finals slot)
_TRAP_CAP_DEFAULT = 2
_SUPPORT_UNCAP_MAX = 4

# Location ids (and "GOAL") for the client thread to send; it also re-sends the
# persisted `checked` list on every connect, so a lost entry is never lost for good.
OUTBOX: queue.Queue = queue.Queue()


def is_ap(viewer_id=None) -> bool:
    """Every account on this server plays Archipelago (Global only: the tables
    are Global's)."""
    return region.CURRENT_REGION.get() == "global"


def target_viewer() -> str | None:
    """The account the connection plays for: the one that logged in last."""
    rows = accounts.all_accounts()
    return str(rows[0]["viewer_id"]) if rows else None


def start_seed(viewer_id, seed: str) -> bool:
    """Play `seed` on this account. A different seed than its save's (or a save
    that never had one) wipes the save and starts a fresh one under the same
    profile. True when it wiped."""
    from ..handlers import load

    full_state = state_store.get_state(viewer_id) or {}
    if (full_state.get(AP_KEY) or {}).get("seed_name") == seed:
        return False
    profile = state_store.extract_json_path(viewer_id, load.STATE_KEY, "$.data.user_info")
    state_store.delete_state(viewer_id)
    fresh_save(viewer_id, profile, seed)
    touch_account()
    log.info("archipelago: viewer %s starts seed %s on a fresh save", viewer_id, seed)
    return True


def hachimi_dir() -> Path:
    """The game's hachimi/ folder: the launcher's, else from
    <game>/<x>_Data/Persistent/master/master.mdb."""
    mdb = master_data.MASTER_MDB_PATH
    return Path(os.environ.get("UMA_HACHIMI_DIR") or (mdb.parents[3] if len(mdb.parents) > 3 else Path(".")) / "hachimi")


def _touch_plugin(name: str) -> None:
    """Nudge the umapd_archipelago Hachimi plugin (it watches these files'
    write time). No hachimi folder: no-op."""
    hachimi = hachimi_dir()
    if hachimi.is_dir():
        try:
            (hachimi / name).write_text(f"{time.time()}\n")
        except OSError:
            log.warning("archipelago: could not update %s", hachimi / name)


def touch_account() -> None:
    """The account changed: the running game logs in again on the home screen."""
    _touch_plugin("umapd_account.version")


def touch_master() -> None:
    """master.mdb changed: the running game rereads its master data."""
    _touch_plugin("umapd_master.version")


def fresh_save(viewer_id, profile, seed=None) -> None:
    """A fresh account (load_index_fresh.json's collection) under `profile`
    (the account's user_info: name, tutorial), playing `seed`."""
    from ..handlers import collection, load

    full_state: dict = {}
    blob = load.get_or_seed_blob(full_state, viewer_id)  # no state: the fresh seed
    data = blob.setdefault("data", {})
    if isinstance(profile, dict):
        data["user_info"] = {**profile, "fan": 0, "rank_score": 0}
    for data_key, state_key in collection.DYNAMIC_CONTAINERS.items():
        if data_key in data:
            full_state[state_key] = data[data_key]
    full_state["coin_info_state"] = {"fcoin": 0, "coin": 0}
    full_state[AP_KEY] = {"seed_name": seed}
    state_store.save_state(viewer_id, full_state)


def ap_state(full_state: dict) -> dict:
    st = full_state.setdefault(AP_KEY, {})
    st.setdefault("seed_name", None)
    st.setdefault("next_index", 0)
    st.setdefault("checked", [])
    st.setdefault("have", {})  # str(item id) -> count, for counted items
    st.setdefault("traps", [])  # trap/boon ids waiting for a career start
    st.setdefault("career", {})  # this career's trap effects (reset at each start)
    st.setdefault("slot_data", {})
    st.setdefault("goal_done", False)
    st.setdefault("races_won", [])  # distinct race ids won in any career
    st.setdefault("locations", [])  # every check in this seed (from Connected)
    st.setdefault("trainees", [])  # trainee card ids received
    st.setdefault("tt_races", 0)  # Team Trials races won on this save (of each match's 5)
    return st


def _count(st: dict, item_id: int) -> int:
    return st.get("have", {}).get(str(item_id), 0)


def item_name(item_id: int) -> str:
    return _ITEM_NAMES.get(item_id, f"item {item_id}")


# ------------------------------------------------------------------ items

_MAIL_BY_ID = {row[0]: row for row in tables.MAIL.values()}
_CRYSTAL_ID = tables.MAIL["Rainbow Uncap Crystal"][0]
_LEVELING_ITEMS = (110, 59)  # Support Pt and Monies (support_card/strengthen spends both)


def apply_item(full_state: dict, item_id: int, sender: str = "") -> None:
    """Apply one received item to full_state (the caller saves)."""
    from ..handlers import presents

    st = ap_state(full_state)
    name = item_name(item_id)
    note = f"Archipelago: {name}" + (f" from {sender}" if sender else "")
    if item_id >= tables.SUPPORT_ITEM_BASE:
        presents.send(full_state, 51, item_id - tables.SUPPORT_ITEM_BASE, 1, note)
        if _maxed_supports(st):
            st.setdefault("max_supports", []).append(item_id - tables.SUPPORT_ITEM_BASE)
        st["supports_received"] = st.get("supports_received", 0) + 1
    elif item_id in _MAIL_BY_ID:
        _id, rtype, rid, num = _MAIL_BY_ID[item_id]
        presents.send(full_state, rtype, rid, num, note)
        st["have"][str(item_id)] = _count(st, item_id) + 1
    elif item_id >= tables.TRAINEE_ITEM_BASE:
        presents.send(full_state, 50, item_id - tables.TRAINEE_ITEM_BASE, 1, note)
        st["trainees"].append(item_id - tables.TRAINEE_ITEM_BASE)
    elif item_id in tables.TRAPS.values() or item_id in tables.BOONS.values():
        st["traps"].append(item_id)
    elif item_id == tables.PROGRESSIVE["Trainee Awakening"]:
        _awaken(full_state, st)
    elif item_id == tables.MINOR["RP Refill"]:
        from ..handlers import stamina

        pool = stamina.rp_info(full_state)
        missing = int(pool.get("max_rp") or 0) - int(pool.get("current_rp") or 0)
        if missing > 0:
            stamina.RP.add(full_state, missing)
    else:  # scenarios and progressive buffs: counted, read where they apply
        st["have"][str(item_id)] = _count(st, item_id) + 1
        _raise_running_caps(full_state, name)
    log.info("archipelago: received %s", note)


def _maxed_supports(st: dict) -> bool:
    """Support cards arrive maxed (seeds before 0.12.0, or maxed_supports on);
    otherwise at limit break 0, uncapped with Rainbow Uncap Crystals."""
    return bool(st.get("slot_data", {}).get("maxed_supports", True))


def _fill_leveling(full_state: dict) -> None:
    """Support Pt and Monies to the game's cap: leveling cards is never the grind
    on the Archipelago save, the cards and crystals are."""
    from ..handlers import presents

    for item_id in _LEVELING_ITEMS:
        presents._add_item(full_state, item_id, 999_999_999)  # clamped to the item's cap


def _awaken(full_state: dict, st: dict, claimed=None) -> None:
    """Trainee Awakening: an owned trainee not yet maxed (the one just claimed,
    else a random one) goes to 5 stars and potential level 5. With every trainee
    maxed it waits for the next one claimed (awaken_pending). The client sees it
    on an owned trainee after its next login."""
    from ..handlers import collection

    owned = full_state.get(collection.CARD_LIST_KEY) or []
    todo = [c for c in owned if c.get("rarity", 1) < 5 or c.get("talent_level", 1) < 5]
    if not todo:
        st["awaken_queue"] = st.get("awaken_queue", 0) + 1
        log.info("archipelago: Trainee Awakening waits for a new trainee (%d queued)", st["awaken_queue"])
        return
    card = next((c for c in todo if c["card_id"] == claimed), None) or random.choice(todo)
    card["rarity"], card["talent_level"] = 5, 5
    st.setdefault("awakened", []).append(card["card_id"])


def awaken_pending(full_state: dict, claimed=None) -> None:
    """Trainee `claimed` was just claimed: spend the Awakenings waiting for one,
    on it first (any still without a trainee to max go back in the queue)."""
    st = (full_state or {}).get(AP_KEY)
    if not st or not st.get("awaken_queue"):
        return
    queued, st["awaken_queue"] = st["awaken_queue"], 0
    for _ in range(queued):
        _awaken(full_state, st, claimed)
        claimed = None


def take_maxed_support(full_state: dict, support_card_id) -> dict | None:
    """Claiming a support card this mod mailed: the fields that max it (limit
    break 4, its top level), once per mailed copy; None for any other card."""
    from ..handlers import cards

    pending = ((full_state or {}).get(AP_KEY) or {}).get("max_supports") or []
    if support_card_id not in pending:
        return None
    cap = cards._support_level_cap(support_card_id, _SUPPORT_UNCAP_MAX)
    if cap is None:
        return None
    pending.remove(support_card_id)
    return {"limit_break_count": _SUPPORT_UNCAP_MAX, "exp": cap[1]}


def _raise_running_caps(full_state: dict, name: str) -> None:
    """A cap item also lifts the career being played, not only the next ones
    (apply_career_start adds the full amount at every start)."""
    if name == "Progressive Stat Cap":
        stats = STAT_FIELDS
    elif name.endswith(" Training") and name.startswith("Progressive "):
        stats = (STAT_FIELDS[tables.STATS.index(name.split()[1])],)
    else:
        return
    from ..handlers import single_mode_team

    ci = ((full_state.get(single_mode_team.STATE_KEY) or {}).get("data") or {}).get("chara_info")
    if isinstance(ci, dict):
        for stat in stats:
            if f"max_{stat}" in ci:
                ci[f"max_{stat}"] += 50


def starters(st: dict) -> list:
    """The seed's starting trainees (random per seed), or a fresh account's five."""
    return list(st.get("slot_data", {}).get("starting_trainees") or tables.STARTING_TRAINEES)


def apply_starters(full_state: dict) -> bool:
    """Once per save: own exactly the seed's starting trainees (plus any trainee
    already received) instead of a fresh account's five, and mail the seed's
    starting support cards. True when it changed something (the client sees
    it after its next login)."""
    from ..handlers import collection, presents

    st = ap_state(full_state)
    changed = False
    if not _maxed_supports(st):
        _fill_leveling(full_state)
    if not st.get("starting_supports_sent"):
        for sid in st.get("slot_data", {}).get("starting_supports") or []:
            presents.send(full_state, 51, sid, 1, "Archipelago: starting support card")
            if _maxed_supports(st):
                st.setdefault("max_supports", []).append(sid)
            changed = True
        st["starting_supports_sent"] = True
    if not st.get("slot_data", {}).get("starting_trainees"):
        return changed  # a seed made before random starters: keep the fresh five
    wanted = starters(st)
    if st.get("starters_applied") == wanted:
        return changed
    keep = set(wanted) | set(st["trainees"])
    owned = [c for c in full_state.get(collection.CARD_LIST_KEY) or [] if c.get("card_id") in keep]
    have = {c["card_id"] for c in owned}
    charas = full_state.setdefault(collection.CHARA_LIST_KEY, [])
    chara_ids = {c.get("chara_id") for c in charas}
    for card_id in wanted:
        if card_id in have:
            continue
        row = master_data.query_one("SELECT chara_id, default_rarity FROM card_data WHERE id=?", (card_id,))
        if not row:
            continue
        owned.append({"card_id": card_id, "rarity": row["default_rarity"] or 1, "talent_level": 1,
                      "skill_data_array": []})
        if row["chara_id"] not in chara_ids:
            charas.append({"chara_id": row["chara_id"], "training_num": 0, "love_point": 0, "fan": 1,
                           "max_grade": 0, "dress_id": 2, "mini_dress_id": 2, "love_point_pool": 0})
            chara_ids.add(row["chara_id"])
    full_state[collection.CARD_LIST_KEY] = owned
    st["starters_applied"] = wanted
    log.info("archipelago: starting trainees for this seed: %s", wanted)
    return True


def starting_scenario(st: dict) -> int:
    return int(st.get("slot_data", {}).get("starting_scenario") or 1)


def unlocked_scenarios(full_state: dict) -> set:
    st = ap_state(full_state)
    return {starting_scenario(st)} | {sid for sid in tables.SCENARIO_ITEM if _count(st, sid)}


def filter_response(viewer_id, response: dict) -> dict:
    """Offer only the scenarios this seed has unlocked."""
    data = (response or {}).get("data")
    if not isinstance(data, dict) or "single_mode_scenario_id_array" not in data or not is_ap(viewer_id):
        return response
    unlocked = unlocked_scenarios(state_store.get_state(viewer_id) or {})
    data["single_mode_scenario_id_array"] = [s for s in data["single_mode_scenario_id_array"] if s in unlocked]
    return response


def start_refusal(viewer_id, scenario_id) -> str | None:
    if not is_ap(viewer_id):
        return None
    if int(scenario_id or 1) not in unlocked_scenarios(state_store.get_state(viewer_id) or {}):
        return f"archipelago: scenario {scenario_id} not unlocked yet"
    return None


def gacha_refused(viewer_id) -> bool:
    """Scouting would hand out what the multiworld is supposed to."""
    return is_ap(viewer_id)


def _training_copies(st: dict, stat_index: int) -> int:
    if st.get("career", {}).get("tunnel") == stat_index:
        return 0
    return _count(st, tables.PROGRESSIVE[f"Progressive {tables.STATS[stat_index]} Training"])


def apply_career_start(full_state: dict, ci: dict) -> None:
    """Permanent buffs, pending boons and up to trap_cap traps on a new career's
    turn-1 chara_info, one of each; traps past the cap and repeats wait for the
    next career (the caller saves)."""
    if not is_ap():
        return
    st = ap_state(full_state)
    rng = random.Random()
    cap = int(st["slot_data"].get("trap_cap") or _TRAP_CAP_DEFAULT)
    _requeue(st)  # a career that never reached its end (closed or not)
    waiting = list(dict.fromkeys(st["traps"]))  # one of each: a repeat waits for the next career
    traps = [t for t in waiting if t in tables.TRAPS.values()][:cap]
    boons = [t for t in waiting if t in tables.BOONS.values()]
    for t in traps + boons:
        st["traps"].remove(t)
    career = st["career"] = {"taken": traps + boons}  # back in the queue unless it reaches its end
    names = {v: k for k, v in {**tables.TRAPS, **tables.BOONS}.items()}
    taken = [names[t] for t in traps + boons]
    career["effects"] = taken
    if "Tunnel Vision Trap" in taken:
        career["tunnel"] = rng.randrange(len(STAT_FIELDS))
    if "Butterfingers Trap" in taken:
        career["butterfingers"] = True

    amnesia = "Amnesia Trap" in taken
    all_cap = 50 * _count(st, tables.PROGRESSIVE["Progressive Stat Cap"])
    start = 0 if amnesia else (
        20 * _count(st, tables.PROGRESSIVE["Progressive Starting Stats"])
        + 5 * _count(st, tables.MINOR["Minor Starting Stats"])
    )
    for i, stat in enumerate(STAT_FIELDS):
        cap_up = all_cap + 50 * _training_copies(st, i)
        ci[f"max_{stat}"] = (ci.get(f"max_{stat}") or 0) + cap_up
        ci[stat] = min((ci.get(stat) or 0) + start, ci[f"max_{stat}"])
    if not amnesia:
        sp = 200 * _count(st, tables.PROGRESSIVE["Progressive Starting Skill Points"])
        sp += 50 * _count(st, tables.MINOR["Minor Starting Skill Points"])
        ci["skill_point"] = (ci.get("skill_point") or 0) + sp

    effects = ci.setdefault("chara_effect_id_array", [])
    for name in taken:
        if name == "Bad Condition Trap":
            effects.append(rng.choice([c for c in _BAD_CONDITIONS if c not in effects] or [6]))
            career.setdefault("conditions", []).append(effects[-1])
        elif name == "Bad Mood Trap":
            ci["motivation"] = 1
        elif name == "Low Energy Trap":
            ci["vital"] = max(0, (ci.get("vital") or 0) - 40)
        elif name == "Pep Talk" and "Bad Mood Trap" not in taken:
            ci["motivation"] = 5
        elif name == "Lucky Charm":
            effects.append(rng.choice([c for c in _GOOD_CONDITIONS if c not in effects] or [8]))
            career.setdefault("conditions", []).append(effects[-1])
    if taken:
        log.info("archipelago: this career starts with %s", ", ".join(taken))


def scale_training(full_state: dict | None, params: list) -> list:
    """+20% per Progressive <Stat> Training on that stat's gain. exec_command
    applies the preview as shown, so this scales both."""
    st = (full_state or {}).get(AP_KEY)
    if not st:
        return params
    for i, stat in enumerate(STAT_FIELDS):
        pct = 20 * _training_copies(st, i)
        if not pct:
            continue
        for p in params:
            if p.get("target_type") == _STAT_TARGET_TYPE[stat] and p.get("value", 0) > 0:
                p["value"] = p["value"] * (100 + pct) // 100
    return params


def scale_failure(full_state: dict | None, chara_info: dict, rate: int) -> int:
    """Training Guard (x0.75 per copy) and Butterfingers (x1.5 in the Junior year)
    on the shown failure rate, which is also the one rolled."""
    st = (full_state or {}).get(AP_KEY)
    if not st or not rate:
        return rate
    factor = 0.75 ** _count(st, tables.PROGRESSIVE["Progressive Training Guard"])
    if st.get("career", {}).get("butterfingers") and (chara_info.get("turn") or 0) <= _JUNIOR_LAST_TURN:
        factor *= 1.5
    return max(0, min(100, math.ceil(rate * factor)))


AP_RP_SECONDS = 360  # one RP on the Archipelago save: the 5-RP bar in 30 min


def rp_seconds(full_state: dict | None, seconds: int) -> int:
    """Team Trials RP refill time: its own pace on the Archipelago save, halved
    per Progressive RP Recovery."""
    st = (full_state or {}).get(AP_KEY)
    if st is None:
        return seconds
    return max(1, int(AP_RP_SECONDS * 0.5 ** _count(st, tables.PROGRESSIVE["Progressive RP Recovery"])))


# ------------------------------------------------------------------ checks


def _check(st: dict, location: str) -> None:
    loc = _LOCATION_IDS[location]
    if loc not in st["checked"]:
        st["checked"].append(loc)
        OUTBOX.put(loc)
        log.info("archipelago: check %s", location)


def _goal(st: dict, why: str) -> None:
    if not st["goal_done"]:
        st["goal_done"] = True
        OUTBOX.put("GOAL")
        log.info("archipelago: GOAL reached (%s)", why)


def on_race_result(full_state: dict, program_id, place: int, turn=None, scenario_id=None) -> None:
    """A career race was run (the caller saves). A G1 counts at slot_data
    g1_place or better (default: a win), and with g1_per_scenario also for the
    career's scenario; the turn-78 race is the scenario's final, which the
    finish check needs won."""
    if not is_ap() or not program_id:
        return
    st = ap_state(full_state)
    if turn is not None and int(turn) >= _FINAL_TURN:
        st["career"]["final_place"] = place
    row = master_data.query_one(
        "SELECT ri.race_id FROM single_mode_program p "
        "JOIN race_instance ri ON ri.id = p.race_instance_id WHERE p.id=?",
        (program_id,),
    )
    if not row:
        return
    name = _G1_BY_RACE.get(row["race_id"])
    if name and place <= int(st["slot_data"].get("g1_place") or 1):
        _check(st, tables.g1_location(name))  # the goal counts this one, any scenario
        if st["slot_data"].get("g1_per_scenario") and scenario_id in tables.SCENARIOS:
            _check(st, tables.g1_scenario_location(name, scenario_id))
    if place != 1:
        return
    if row["race_id"] not in st["races_won"]:
        st["races_won"].append(row["race_id"])
    for n in tables.UNIQUE_RACE_MILESTONES:
        if len(st["races_won"]) >= n:
            _check(st, tables.unique_races_location(n))
    if st["slot_data"].get("goal") == "g1_collector":
        g1s = sum(_LOCATION_IDS[tables.g1_location(n)] in st["checked"] for n in tables.G1_RACES)
        if g1s >= int(st["slot_data"].get("goal_g1_count") or len(tables.G1_RACES)):
            _goal(st, f"{g1s} different G1s won")


def on_team_trials_races_won(full_state: dict, wins: int) -> None:
    """A Team Trials match ended with `wins` of its races won, lost match or not
    (the caller saves): the first team_trials_checks race wins are checks;
    later wins only count."""
    if not is_ap():
        return
    st = ap_state(full_state)
    checks = int(st["slot_data"].get("team_trials_checks", tables.TEAM_TRIALS_CHECKS))
    for n in range(st["tt_races"] + 1, min(st["tt_races"] + wins, checks) + 1):
        _check(st, tables.team_trials_location(n))
    st["tt_races"] += wins


def _requeue(st: dict) -> None:
    """The running career's traps and boons go back to the front of the queue (a
    career finished at its last turn has none left: on_career_finished spent them)."""
    st["traps"][:0] = (st.get("career") or {}).pop("taken", [])


def on_career_finished(full_state: dict, chara_info: dict | None, record: dict | None,
                       reached_end: bool) -> None:
    """Any career end, give-up included (the caller saves). A legacy (`record`)
    is checked: rank checks go by its score; the finish and trainee checks need
    it to have reached its last turn. A career that never reached its last turn
    gives its traps and boons back, so losing on purpose doesn't shed them."""
    if not is_ap():
        return
    st = ap_state(full_state)
    if reached_end:  # any place in the final: its traps and boons are spent
        st["career"].pop("taken", None)
    _requeue(st)
    if not chara_info or not record:
        return
    scenario = chara_info.get("scenario_id") or 1
    score = record.get("rank_score") or 0
    st["best_score"] = max(st.get("best_score", 0), score)
    if scenario in tables.SCENARIOS:
        # Finishing a scenario means winning its final; the trainee check below
        # only needs the last turn.
        if reached_end and st["career"].get("final_place") == 1:
            _check(st, tables.finish_location(scenario))
        for tier, need in tables.RANK_TIERS:
            if score >= need:
                _check(st, tables.rank_location(scenario, tier))
    for tier, need in tables.GLOBAL_RANKS:
        if score >= need:
            _check(st, tables.global_rank_location(tier))
    if reached_end and chara_info.get("card_id") in tables.TRAINEES:
        _check(st, tables.trainee_location(chara_info["card_id"]))
    st["fans"] = st.get("fans", 0) + int(chara_info.get("fans") or 0)
    for n in tables.FAN_MILESTONES:
        if st["fans"] >= n:
            _check(st, tables.fans_location(n))
    kind = st["slot_data"].get("goal", "rank_score")
    goal = st["slot_data"].get("goal_rank_score")
    if kind == "rank_score" and goal and score >= goal:
        _goal(st, f"rank score {score} >= {goal}")
    if kind == "all_scenarios" and all(
        _LOCATION_IDS[tables.finish_location(sid)] in st["checked"] for sid in tables.SCENARIOS
    ):
        _goal(st, "a career finished in every scenario")


# ------------------------------------------------------------------ tracker
# The apworld's logic (umamusume-apworld UmamusumeWorld.estimate), kept in step.

_LOGIC_BASE_DEFAULT = 11500
_SCENARIO_BONUS = 1500
_SUPPORT_BONUS, _SUPPORT_MAX = 300, 6  # each maxed SSR, up to a deck (seeds before 0.14.0)


def logic_estimate(st: dict, scenario: int | None = None) -> int:
    have = lambda name: _count(st, tables.PROGRESSIVE[name])  # noqa: E731
    sd = st.get("slot_data", {})
    est = int(sd.get("logic_base") or _LOGIC_BASE_DEFAULT)
    support = int(sd.get("logic_support") or _SUPPORT_BONUS)
    est += int(sd.get("logic_training") or 450) * sum(have(f"Progressive {s} Training") for s in tables.STATS)
    est += 400 * have("Progressive Starting Stats") + 300 * have("Progressive Stat Cap")
    supports = st.get("supports_received", 0) + len(st.get("slot_data", {}).get("starting_supports") or [])
    if _maxed_supports(st):
        est += support * min(_SUPPORT_MAX, supports)
    else:  # half for the card, half once 4 crystals can max it
        est += support // 2 * (min(_SUPPORT_MAX, supports) + min(_SUPPORT_MAX, _count(st, _CRYSTAL_ID) // 4))
    owned = starting_scenario(st) != 1 or any(_count(st, sid) for sid in tables.SCENARIO_ITEM if sid != 1)
    if (owned if scenario is None else scenario != 1):
        est += _SCENARIO_BONUS
    return est


def tracker(full_state: dict) -> list:
    """This seed's checks in groups: [{group, checks: [{name, done, in_logic, locked}]}].
    locked: it needs an item first (a scenario, a trainee); out of logic but not
    locked: possible now, logic just expects stronger careers first. Empty until
    the client has connected once (it stores the seed's checks)."""
    st = ap_state(full_state)
    in_seed = set(st["locations"])
    done = set(st["checked"])
    scenarios = unlocked_scenarios(full_state)
    est = logic_estimate(st)
    groups = []

    def group(title, rows):
        checks = [
            {"name": name, "done": _LOCATION_IDS[name] in done, "in_logic": bool(ok), "locked": bool(locked)}
            for name, ok, *rest in rows
            for locked in [rest[0] if rest else False]
            if _LOCATION_IDS[name] in in_seed
        ]
        if checks:
            groups.append({"group": title, "checks": checks})

    group("G1 wins", [(tables.g1_location(n), True) for n in tables.G1_RACES])
    for sid, scenario in tables.SCENARIOS.items():
        group(f"G1 wins in {scenario}",
              [(tables.g1_scenario_location(n, sid), sid in scenarios, sid not in scenarios) for n in tables.G1_RACES])
    rows = []
    for sid in tables.SCENARIOS:
        rows.append((tables.finish_location(sid), sid in scenarios, sid not in scenarios))
        e = logic_estimate(st, sid)
        rows += [(tables.rank_location(sid, tier), sid in scenarios and e >= score, sid not in scenarios)
                 for tier, score in tables.RANK_TIERS]
    group("Scenarios", rows)
    group("Rank ladder", [(tables.global_rank_location(t), est >= sc) for t, sc in tables.GLOBAL_RANKS])
    group("Different races",
          [(tables.unique_races_location(n), est >= 9000 + 100 * n) for n in tables.UNIQUE_RACE_MILESTONES])
    group("Fans", [(tables.fans_location(n), est >= tables.fans_logic(n)) for n in tables.FAN_MILESTONES])
    group("Team Trials", [(tables.team_trials_location(n), est >= 11000 + 300 * min(n // 3, 10)) for n in range(1, tables.TEAM_TRIALS_CHECKS + 1)])
    group("Legend Race", [(tables.legend_location(t), est >= tables.LEGEND_RANK_SCORE[rank])
                          for t, rank, _row, _stats in tables.LEGEND_LADDER])
    have = set(starters(st)) | set(st["trainees"])
    group("Trainees", [(tables.trainee_location(c), c in have, c not in have) for c in tables.TRAINEES])
    return groups


# ------------------------------------------------------------------ legend ladder

LADDER_ROWS = [row for _tier, _rank, row, _stats in tables.LEGEND_LADDER]
_LEGEND_EVENT_DAYS = 365
_LEGEND_KEY = "legend_race_state"  # handlers.legend_race.LEGEND_KEY


def legend_tier(full_state: dict) -> int | None:
    """The Archipelago save's rung on the rival ladder, or None for any other
    save. Past the top it stays on the last rung."""
    if AP_KEY not in (full_state or {}):
        return None
    return min(full_state[AP_KEY].get("legend_rung", 0), len(LADDER_ROWS) - 1)


def legend_boss(boss: dict, tier: int) -> dict:
    """The rung's rival at this rung's strength (name, look and skills stay its own)."""
    _name, rank_id, _row, stats = tables.LEGEND_LADDER[tier]
    boss = dict(boss)
    for key, value in zip(("speed", "stamina", "pow", "guts", "wiz"), stats):
        boss[key] = value
    boss["rank"] = rank_id  # a race entrant's grade
    if "final_grade" in boss:  # a profile card (legend_race/index boss_data)
        boss["final_grade"] = rank_id
    return boss


def on_legend_result(full_state: dict, tier, rank: int) -> None:
    """A ladder run was settled (the caller saves): a win on a rung is its check
    and opens the next."""
    if tier is None or rank != 1 or AP_KEY not in full_state:
        return
    st = ap_state(full_state)
    _check(st, tables.legend_location(tables.LEGEND_LADDER[tier][0]))
    if tier == legend_tier(full_state):
        st["legend_rung"] = tier + 1
        log.info("archipelago: Legend Race rung %s beaten", tables.LEGEND_LADDER[tier][0])
    if st["slot_data"].get("goal") == "legend_race" and tier == len(LADDER_ROWS) - 1:
        _goal(st, "the SS+ Legend Race rival beaten")


def _legend_dates_file():
    return region.data_dir() / "archipelago_legend_dates.json"  # the ladder rows' own dates


def sync_legend_events() -> None:
    """At server start: keep the ladder's legend race events running in the
    game's master.mdb and tell the umapd plugin to reread it. Before the first
    edit, master.mdb is backed up and each row's own dates recorded
    (restore_legend_events puts them back). A game update that rewrites
    master.mdb is simply edited again on the next start."""
    mdb = master_data.MASTER_MDB_PATH
    now = int(time.time())
    try:
        conn = sqlite3.connect(mdb, timeout=10)
        try:
            marks = ",".join("?" * len(LADDER_ROWS))
            rows = conn.execute(f"SELECT id, notice_date, start_date, end_date FROM legend_race "
                                f"WHERE id IN ({marks})", LADDER_ROWS).fetchall()
            if all(start <= now and end > now + 30 * 86400 for _id, _n, start, end in rows):
                return
            dates_file = _legend_dates_file()
            saved = json.loads(dates_file.read_text()) if dates_file.exists() else {}
            if not saved:
                backup = region.data_dir() / "master_before_archipelago.sqlite3.bak"
                if not backup.exists():
                    shutil.copy2(mdb, backup)
            for rid, notice, start, end in rows:
                saved.setdefault(str(rid), [notice, start, end])
            dates_file.write_text(json.dumps(saved, indent=1))
            with conn:
                conn.executemany("UPDATE legend_race SET notice_date=?, start_date=?, end_date=? WHERE id=?",
                                 [(now - 3600, now - 3600, now + _LEGEND_EVENT_DAYS * 86400, rid)
                                  for rid in LADDER_ROWS])
        finally:
            conn.close()
        touch_master()
        log.info("archipelago: Legend Race ladder events running in master.mdb (rows %s)", LADDER_ROWS)
    except Exception:
        log.warning("archipelago: could not set up the Legend Race ladder events", exc_info=True)


def restore_legend_events() -> list:
    """Put the ladder rows' own master.mdb dates back (the recorded ones from
    before the first edit). Returns the restored row ids."""
    dates_file = _legend_dates_file()
    if not dates_file.exists():
        return []
    saved = json.loads(dates_file.read_text())
    conn = sqlite3.connect(master_data.MASTER_MDB_PATH, timeout=10)
    try:
        with conn:
            conn.executemany("UPDATE legend_race SET notice_date=?, start_date=?, end_date=? WHERE id=?",
                             [(*dates, int(rid)) for rid, dates in saved.items()])
    finally:
        conn.close()
    dates_file.unlink()
    touch_master()
    return [int(rid) for rid in saved]


# ------------------------------------------------------------------ admin panel

def goal_progress(full_state: dict) -> dict:
    """The seed's goal for the panel: what it asks, how far along, in logic yet."""
    st = ap_state(full_state)
    sd, est = st["slot_data"], logic_estimate(st)
    done_locs = set(st["checked"])
    kind = sd.get("goal", "rank_score")
    if kind == "g1_collector":
        target = int(sd.get("goal_g1_count") or len(tables.G1_RACES))
        current = sum(_LOCATION_IDS[tables.g1_location(n)] in done_locs for n in tables.G1_RACES)
        label, unit, logic = f"Win {target} different G1s", "G1s", est >= 11000 + 150 * target
    elif kind == "all_scenarios":
        target = len(tables.SCENARIOS)
        current = sum(_LOCATION_IDS[tables.finish_location(s)] in done_locs for s in tables.SCENARIOS)
        label, unit = "Finish a career in every scenario", "scenarios"
        logic = unlocked_scenarios(full_state) >= set(tables.SCENARIOS)
    elif kind == "legend_race":
        target = len(tables.LEGEND_LADDER)
        current = sum(_LOCATION_IDS[tables.legend_location(t[0])] in done_locs for t in tables.LEGEND_LADDER)
        label, unit, logic = "Beat the SS+ Legend Race rival", "rivals beaten", est >= 19200
    else:
        target = int(sd.get("goal_rank_score") or 20000)
        # Saves from before best_score was kept: the highest rank check already done.
        ranks = [sc for t, sc in tables.GLOBAL_RANKS if _LOCATION_IDS[tables.global_rank_location(t)] in done_locs]
        ranks += [sc for sid in tables.SCENARIOS for t, sc in tables.RANK_TIERS
                  if _LOCATION_IDS[tables.rank_location(sid, t)] in done_locs]
        current = max([st.get("best_score", 0), *ranks])
        label, unit, logic = f"One career at rank score {target}", "best career", est >= target
    done = bool(st["goal_done"])
    pct = 100 if done else min(99, current * 100 // target) if target else 0
    return {"kind": kind, "label": label, "unit": unit, "current": current, "target": target,
            "percent": pct, "done": done, "in_logic": logic}


# ------------------------------------------------------------------ effects

_CONDITION_NAMES = {
    1: "Night Owl",
    2: "Slacker",
    3: "Skin Outbreak",
    5: "Migraine",
    6: "Practice Poor",
    8: "Charming",
    10: "Practice Perfect",
}


def effects_report(full_state: dict, chara_info: dict | None) -> dict:
    """What traps and boons do to the running career, and what waits for the
    next one: {"career": [...] or None (no career running), "next": [...]}."""
    st = ap_state(full_state)
    names = {v: k for k, v in {**tables.TRAPS, **tables.BOONS}.items()}
    cap = int(st["slot_data"].get("trap_cap") or _TRAP_CAP_DEFAULT)
    pending, traps_seen, seen = [], 0, set()
    for t in st["traps"]:
        is_trap = t in tables.TRAPS.values()
        repeat = t in seen  # one of each per career
        seen.add(t)
        traps_seen += is_trap and not repeat
        name = names.get(t, str(t))
        later = repeat or (is_trap and traps_seen > cap)
        pending.append({"name": name, "trap": is_trap, "later": later, "info": item_info(name)})
    if not chara_info:
        return {"career": None, "next": pending}
    career = st.get("career") or {}
    turn = chara_info.get("turn") or 0
    conditions = set(chara_info.get("chara_effect_id_array") or ())
    rows = []
    for name in career.get("effects") or ():
        trap = name in tables.TRAPS
        if name == "Tunnel Vision Trap":
            stat = tables.STATS[career.get("tunnel", 0)]
            what, left = f"no Progressive {stat} Training bonus (the training still works)", "rest of the career"
        elif name == "Butterfingers Trap":
            what = "training failure rate x1.5"
            left = f"{_JUNIOR_LAST_TURN - turn + 1} turns (Junior year)" if turn <= _JUNIOR_LAST_TURN else "over"
        elif name == "Amnesia Trap":
            what, left = "no starting stats / skill points buffs", "this career (applied at start)"
        elif name in ("Bad Condition Trap", "Lucky Charm"):
            ids = career.get("conditions") or []
            label = ", ".join(_CONDITION_NAMES.get(c, str(c)) for c in ids) or "a condition"
            what = f"started with {label}"
            left = "until cured" if trap else "while it lasts"
            if ids and not conditions & set(ids):
                left = "over"
        elif name == "Bad Mood Trap":
            what, left = "started in Awful mood", "until your mood recovers"
        elif name == "Low Energy Trap":
            what, left = "started with 40 less energy", "start only"
        elif name == "Pep Talk":
            what, left = "started in Great mood", "start only"
        else:
            what, left = "", ""
        rows.append({"name": name, "trap": trap, "effect": what, "left": left})
    return {"career": {"turn": turn, "effects": rows}, "next": pending}


def permanent_buffs(full_state: dict) -> list:
    """The permanent items this save has, for the panel: [{name, count, each:
    one copy's effect, effect: all copies together}]."""
    st = ap_state(full_state)
    have = lambda name: _count(st, ({**tables.PROGRESSIVE, **tables.MINOR})[name])  # noqa: E731
    rows = []

    def add(name, effect, each):
        """effect: the combined text for n copies; each: what one copy gives."""
        n = have(name)
        if n:
            rows.append({"name": name, "count": n, "each": each, "effect": effect(n)})

    for stat in tables.STATS:
        add(f"Progressive {stat} Training", lambda n, s=stat: f"+{20 * n}% {s} gain, +{50 * n} {s} cap",
            "+20%, +50 cap")
    add("Progressive Stat Cap", lambda n: f"+{50 * n} to every stat cap", "+50")
    add("Progressive Starting Stats", lambda n: f"+{20 * n} to every stat at career start", "+20")
    add("Minor Starting Stats", lambda n: f"+{5 * n} to every stat at career start", "+5")
    add("Progressive Starting Skill Points", lambda n: f"+{200 * n} skill points at career start", "+200")
    add("Minor Starting Skill Points", lambda n: f"+{50 * n} skill points at career start", "+50")
    add("Progressive Training Guard", lambda n: f"training failure rate x{0.75 ** n:.2f}", "x0.75")
    add("Progressive RP Recovery", lambda n: f"Team Trials RP refills {2 ** n}x as fast", "2x")
    for sid, name in tables.SCENARIO_ITEM.items():
        if _count(st, sid):
            rows.append({"name": name, "count": 1, "each": "", "effect": "scenario unlocked"})
    return rows


# What each kind of item does, for the panel (keyed by name or name prefix).
_ITEM_INFO = {
    "Bad Condition Trap": "Trap, next career: start with a bad condition (Night Owl, Slacker, "
    "Skin Outbreak, Migraine or Practice Poor) until it's cured.",
    "Bad Mood Trap": "Trap, next career: start in Awful mood.",
    "Low Energy Trap": "Trap, next career: start with 40 less energy.",
    "Tunnel Vision Trap": "Trap, next career: one random stat loses its Progressive Training "
    "bonus (gain and cap). The training itself still works.",
    "Butterfingers Trap": "Trap, next career: training failure rate x1.5 during the Junior "
    "year (turns 1-24).",
    "Amnesia Trap": "Trap, next career: no starting stats / skill points buffs.",
    "Pep Talk": "Boon, next career: start in Great mood.",
    "Lucky Charm": "Boon, next career: start Charming or with Practice Perfect.",
    "Minor Starting Stats": "Permanent: +5 to every stat at career start.",
    "Minor Starting Skill Points": "Permanent: +50 skill points at career start.",
    "RP Refill": "Team Trials RP refilled to full, once.",
    "Progressive Stat Cap": "Permanent: +50 to every stat cap.",
    "Progressive Starting Stats": "Permanent: +20 to every stat at career start.",
    "Progressive Starting Skill Points": "Permanent: +200 skill points at career start.",
    "Progressive Training Guard": "Permanent: training failure rate x0.75.",
    "Progressive RP Recovery": "Permanent: Team Trials RP refills twice as fast.",
    "Trainee Awakening": "One random trainee you own goes to 5 stars and potential level 5 "
    "(log in again to see it); with all of them maxed, it waits for the next trainee you claim.",
    "Scenario: ": "Unlocks this scenario on the career screen.",
    "Trainee: ": "Mail: this trainee joins your roster.",
    "Support: ": "Mail: this SSR support card (maxed when you claim it, if the seed has maxed_supports).",
    "Rainbow Uncap Crystal": "Mail: one limit break for any SSR support card (Enhance > Support Cards > Limit Break). "
    "4 max a card.",
}


def item_info(name: str) -> str:
    if name.startswith("Progressive ") and name.endswith(" Training"):
        stat = name.split()[1]
        return f"Permanent: +20% {stat} training gain and +50 {stat} cap (this career too)."
    if name in _ITEM_INFO:
        return _ITEM_INFO[name]
    for prefix, text in _ITEM_INFO.items():
        if prefix.endswith(" ") and name.startswith(prefix):
            return text
    return ""
