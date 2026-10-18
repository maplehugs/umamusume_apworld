"""DESIGN YOUR ISLAND (scenario 11) -- the scenario's own master.mdb tables,
read once.

Every number the scenario runs on that the game ships is here, straight off
JP's single_mode_11_* tables; docs/JP_DESIGN_YOUR_ISLAND_SCENARIO.md §4 says
what each table and effect code means. What master does NOT carry (the normal
facilities' per-level base values, Island Training's facility weights) is in
formula.py with its derivation.
"""

from __future__ import annotations

import functools

from ... import master_data

# single_mode_11_facility_effect.effect_type (text_data 375 gives the meaning
# of every row, §4.4). v1 is a PERIOD: 9 always, 0/1 Island Training (outside
# camp), 2/3 the island versions (camp / URA finals).
EFFECT_FLAT = 1                  # (9, value, stat): +value to that stat's base
EFFECT_TRAINING = 2              # (period, %, command): training effect %
EFFECT_ALL_HINTS = 101           # (2/3, 0, 36xx): every normal card's hint fires
EFFECT_HINTS_TAKE = 102          # (2/3, 0, 36xx): every hint takes effect
EFFECT_FRIEND_PARTICIPANT = 103  # (9, 500): +5% per friendship-training card
EFFECT_MULTI_RAINBOW = 104       # (0/1, %, n): +% when n facilities hold a rainbow
EFFECT_SPECIALTY = 201           # (period, +rate, card command): specialty rate
EFFECT_HINT_RATE = 204           # (period / 9, %, command): hint rate
EFFECT_APPEAR = 205              # (9, +n): support appearance rate
EFFECT_RACE_PT = 206             # (9, 200, 1): non-goal race points +200%

# single_mode_11_check_point_eff.effect_type (§10).
CP_TRAINING = 200                # (0/1, TE %): the scenario bonus line
CP_POINTS = 202                  # (9, %): development points bonus
CP_HINT_RATE = 204               # (9, %): hint rate

PERIOD_ISLAND = 0                # Island Training (rows come in pairs, 0 and 1, always equal)
PERIOD_CAMP = 2                  # island versions in the summer camps
PERIOD_FINALS = 3                # island versions in the URA finals
PERIOD_ALWAYS = 9

FACILITIES = (101, 102, 103, 104, 105, 106)   # FacilityIdEnum; 106 = the Beach House
BEACH_HOUSE = 106
# Normal training command -> its facility, and the facility's island version.
TRAINING_TO_FACILITY = {101: 101, 105: 102, 102: 103, 103: 104, 106: 105}
FACILITY_TO_TRAINING = {v: k for k, v in TRAINING_TO_FACILITY.items()}
ISLAND_VERSIONS = {101: 3601, 105: 3602, 102: 3603, 103: 3604, 106: 3605}   # by training
ISLAND_TO_TRAINING = {v: k for k, v in ISLAND_VERSIONS.items()}
ISLAND_TRAINING = 3101
ISLAND_REST = 3606               # camp / finals rest (command_type 3)
# Stat ids of the facility's type-2 set (the stats its Island Training % lifts).
FACILITY_STATS = {101: (1, 3, 30), 102: (2, 4, 30), 103: (2, 3, 30),
                  104: (1, 3, 4, 30), 105: (1, 5, 30)}

TUCKER_CHARA = 9049              # SINGLE_MODE_SCENARIO_PIONEER_UNIQUE_CHARA_ID


def _rows(sql: str, params: tuple = ()) -> list:
    try:
        return [dict(r) for r in master_data.query(sql, params)]
    except Exception:                                  # noqa: BLE001
        return []


@functools.lru_cache(maxsize=1)
def facility_effects() -> dict:
    """{state_id: [(effect_type, v1, v2, v3, v4), ...]} in master order."""
    out: dict = {}
    for r in _rows("SELECT state_id, effect_type, effect_value_1, effect_value_2, effect_value_3, "
                   "effect_value_4 FROM single_mode_11_facility_effect ORDER BY id"):
        out.setdefault(int(r["state_id"]), []).append(
            (int(r["effect_type"]), int(r["effect_value_1"]), int(r["effect_value_2"]),
             int(r["effect_value_3"]), int(r["effect_value_4"])))
    return out


@functools.lru_cache(maxsize=1)
def lv_up() -> dict:
    """{current_state_id: [(target_state_id, cost), ...]} -- the next level;
    two entries at Lv2 -> Lv3, the route choice."""
    out: dict = {}
    for r in _rows("SELECT current_state_id, target_state_id, cost "
                   "FROM single_mode_11_facility_lv_up ORDER BY id"):
        out.setdefault(int(r["current_state_id"]), []).append(
            (int(r["target_state_id"]), int(r["cost"])))
    return out


@functools.lru_cache(maxsize=1)
def state_levels() -> dict:
    """{state_id: facility_lv}."""
    return {int(r["state_id"]): int(r["facility_lv"])
            for r in _rows("SELECT state_id, facility_lv FROM single_mode_11_facility_state")}


def level_of(state_id: int) -> int:
    return state_levels().get(int(state_id or 0), 0)


@functools.lru_cache(maxsize=1)
def planning() -> dict:
    """{(deck_id, check_point_type): (planning_turn, check_point_turn, target_pt)}."""
    return {(int(r["deck_id"]), int(r["check_point_type"])):
            (int(r["planning_turn"]), int(r["check_point_turn"]), int(r["target_pt"]))
            for r in _rows("SELECT deck_id, check_point_type, planning_turn, check_point_turn, "
                           "target_pt FROM single_mode_11_planning")}


def check_point_turns() -> dict:
    """{check_point_type: turn} -- 12 / 24 / 36 / 48 / 60."""
    return {cp: turn for (deck, cp), (_p, turn, _t) in planning().items() if deck == 0}


def check_point_for_turn(turn: int) -> int:
    return next((cp for cp, t in check_point_turns().items() if t == int(turn or 0)), 0)


def plan_for_turn(turn: int) -> int:
    """The check point (1-5) the plan running on `turn` is judged at; 0 after
    the last one or before the first plan."""
    for cp, t in sorted(check_point_turns().items()):
        if turn <= t:
            return cp
    return 0


@functools.lru_cache(maxsize=1)
def ticket_thresholds() -> dict:
    """{(deck_id, turn_min, turn_max): [first, second]}."""
    out: dict = {}
    for r in _rows("SELECT deck_id, turn_min, turn_max, gain_shima_training_pt "
                   "FROM single_mode_11_gain_training_pt ORDER BY id"):
        out.setdefault((int(r["deck_id"]), int(r["turn_min"]), int(r["turn_max"])), []).append(
            int(r["gain_shima_training_pt"]))
    return {k: sorted(v) for k, v in out.items()}


@functools.lru_cache(maxsize=1)
def pt_bonus() -> dict:
    """{check_point_type: (pt_rate, add_value_max)} -- the overflow's energy."""
    return {int(r["check_point_type"]): (int(r["pt_rate"]), int(r["add_value_max"]))
            for r in _rows("SELECT check_point_type, pt_rate, add_value_max "
                           "FROM single_mode_11_pioneer_pt_bonus")}


@functools.lru_cache(maxsize=1)
def check_point_effects() -> dict:
    """{(check_point_type, result_state): [(effect_type, v1, v2), ...]}."""
    out: dict = {}
    for r in _rows("SELECT check_point_type, result_state, effect_type, effect_value_1, "
                   "effect_value_2 FROM single_mode_11_check_point_eff ORDER BY id"):
        out.setdefault((int(r["check_point_type"]), int(r["result_state"])), []).append(
            (int(r["effect_type"]), int(r["effect_value_1"]), int(r["effect_value_2"])))
    return out


def check_point_effect(check_point_type: int, result_state: int, effect_type: int) -> int:
    return next((v2 for t, _v1, v2 in check_point_effects().get(
        (int(check_point_type), int(result_state)), ()) if t == effect_type), 0)


@functools.lru_cache(maxsize=1)
def shima_effect() -> dict:
    """{(command_id, result_state, required_facility_id): [(target_type, value), ...]}
    in master order -- the island versions' and Island Training's bases."""
    out: dict = {}
    for r in _rows("SELECT command_id, result_state, target_type, effect_value, required_facility_id "
                   "FROM single_mode_11_shima_effect ORDER BY id"):
        out.setdefault((int(r["command_id"]), int(r["result_state"]),
                        int(r["required_facility_id"])), []).append(
            (int(r["target_type"]), int(r["effect_value"])))
    return out


@functools.lru_cache(maxsize=1)
def outing_effect() -> list:
    """[(chara_id, min_card_level, pt)] -- Tucker's date reward, choice 1 then 2
    for each level band (§3.3)."""
    return [(int(r["chara_id"]), int(r["min_lv"]), int(r["value"]))
            for r in _rows("SELECT chara_id, min_lv, value FROM single_mode_11_outing_effect ORDER BY id")]


def tucker_reward(card_level: int) -> int:
    """Choice 1's points for a Tucker card at this level: 80 from Lv41, else 30."""
    best = (-1, 0)
    for chara, min_lv, value in outing_effect():
        if chara == TUCKER_CHARA and value and card_level >= min_lv and min_lv > best[0]:
            best = (min_lv, value)
    return best[1]
