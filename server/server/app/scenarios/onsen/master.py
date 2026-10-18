"""ONSEN (scenario 12) -- the scenario's own master.mdb tables, read once.

Every number the scenario runs on that the game ships lives here, straight off
JP's single_mode_12_* tables; docs/JP_ONSEN_SCENARIO.md §2 says what each table
and each effect code means. The constants master does NOT carry (the per-level
facility base values and energy, the dig budget bases) are in formula.py and
dig.py, each with its derivation.
"""

from __future__ import annotations

import functools

from ... import master_data

# single_mode_12_onsen_effect.effect_type (client enum
# MasterSingleMode12OnsenEffect.EffectTypeEnum names 5/6/7/14/15/16/101/102/104/107;
# the rest are decoded from the rows and the capture fits, §2).
EFFECT_TRAINING = 1          # training effect +v2 %
EFFECT_HINT_RATE = 2         # hint rate +v2 %
EFFECT_ENERGY_COST = 4       # training energy cost v2 % (negative)
EFFECT_SUB_PARTNER = 5       # (1, copies, min card types): extra deck-card copies
EFFECT_AFFINITY = 7          # specialty rate +v2
EFFECT_GOAL_RACE = 8         # v4 %: "stats from training goals" -- NOT paid, §16.2
EFFECT_FAILURE = 12          # failure rate v2 % (negative)
EFFECT_FRIENDSHIP = 14       # (command_id, N): friendship bonus +N % on that facility
EFFECT_ALWAYS_SUPERIOR = 15  # every bath is a super recovery
EFFECT_HINT_COUNT = 16       # +v2 hint events per super recovery
EFFECT_PARAM = 101           # instant (target, N): 10 energy, 20 motivation, 30 SP
EFFECT_EVALUATION = 102      # instant (cards, N): bond +N to the lowest-bond cards
EFFECT_CURE = 104            # instant (condition ids...): cure them
EFFECT_SKILL_HINT = 107      # instant (0, N): N support hint events
EFFECT_MAX_VITAL = 108       # (0, N): the super recovery's energy cap

BASE_ONSEN = 1               # SingleModeScenarioOnsenDefine.DEFAULT_ONSEN_ID
LEGEND_ONSEN = 10            # LEGEND_ONSEN_ID
SUPERIOR_GROUP = 99          # the super recovery's effect group
RANK_GROUP_BASE = 100        # ryokan rank r's passives are group 100 + r

# single_mode_12_spa_ticket.type_id (client OnsenBathingTicketService.TypeId).
TICKET_DIG_COMPLETE = 1
TICKET_SUMMER_CAMP = 2
TICKET_URA_FINAL_BEFORE = 3

KIYOKO_CHARA = 9050          # UNIQUE_CHARA_ID_9050, the scenario's link friend


def _rows(sql: str, params: tuple = ()) -> list:
    try:
        return [dict(r) for r in master_data.query(sql, params)]
    except Exception:                                  # noqa: BLE001
        return []


@functools.lru_cache(maxsize=1)
def onsens() -> dict:
    """{onsen_id: open_turn}."""
    return {int(r["id"]): int(r["open_turn"])
            for r in _rows("SELECT id, open_turn FROM single_mode_12_onsen")}


@functools.lru_cache(maxsize=1)
def strata() -> dict:
    """{onsen_id: [(stratum_id, stratum_type, volume), ...]} in dig order."""
    out: dict = {}
    for r in _rows("SELECT id, onsen_id, stratum_order, stratum_type, stratum_volume "
                   "FROM single_mode_12_stratum ORDER BY onsen_id, stratum_order"):
        out.setdefault(int(r["onsen_id"]), []).append(
            (int(r["id"]), int(r["stratum_type"]), int(r["stratum_volume"])))
    return out


@functools.lru_cache(maxsize=1)
def stratum_info() -> dict:
    """{stratum_id: (onsen_id, stratum_type, volume)}."""
    return {sid: (onsen, kind, vol)
            for onsen, rows in strata().items() for sid, kind, vol in rows}


@functools.lru_cache(maxsize=1)
def effects() -> dict:
    """{group_id: [(effect_type, v1, v2, v3, v4), ...]}."""
    out: dict = {}
    for r in _rows("SELECT group_id, effect_type, effect_value_1, effect_value_2, "
                   "effect_value_3, effect_value_4 FROM single_mode_12_onsen_effect ORDER BY id"):
        out.setdefault(int(r["group_id"]), []).append(
            (int(r["effect_type"]), int(r["effect_value_1"]), int(r["effect_value_2"]),
             int(r["effect_value_3"]), int(r["effect_value_4"])))
    return out


@functools.lru_cache(maxsize=1)
def dig_item_values() -> dict:
    """{(item_id, level): dig_value}."""
    return {(int(r["item_id"]), int(r["item_level"])): int(r["dig_value"])
            for r in _rows("SELECT item_id, item_level, dig_value FROM single_mode_12_dig_item")}


@functools.lru_cache(maxsize=1)
def item_for_stratum() -> dict:
    """{stratum_type: item_id}."""
    return {int(r["stratum_type"]): int(r["item_id"])
            for r in _rows("SELECT DISTINCT item_id, stratum_type FROM single_mode_12_dig_item")}


def max_item_level() -> int:
    return max((lv for _i, lv in dig_item_values()), default=6)


@functools.lru_cache(maxsize=1)
def dig_power() -> dict:
    """{(stratum_type, param_type): [(rank_min, rank_max, bonus), ...]}."""
    out: dict = {}
    for r in _rows("SELECT stratum_type, param_type, param_rank_min, param_rank_max, "
                   "bonus_value FROM single_mode_12_dig_power ORDER BY id"):
        out.setdefault((int(r["stratum_type"]), int(r["param_type"])), []).append(
            (int(r["param_rank_min"]), int(r["param_rank_max"]), int(r["bonus_value"])))
    return out


@functools.lru_cache(maxsize=1)
def stratum_params() -> dict:
    """{stratum_type: (param, ...)} in master order: main, second, third."""
    out: dict = {}
    for r in _rows("SELECT stratum_type, param_type FROM single_mode_12_dig_power ORDER BY id"):
        lst = out.setdefault(int(r["stratum_type"]), [])
        if int(r["param_type"]) not in lst:
            lst.append(int(r["param_type"]))
    return {k: tuple(v) for k, v in out.items()}


@functools.lru_cache(maxsize=1)
def factor_bonus() -> dict:
    """{(stratum_type, factor_group_id): bonus} per inherited blue factor."""
    return {(int(r["stratum_type"]), int(r["factor_group_id"])): int(r["bonus_value"])
            for r in _rows("SELECT stratum_type, factor_group_id, bonus_value "
                           "FROM single_mode_12_factor_bonus")}


@functools.lru_cache(maxsize=1)
def dig_bonus() -> dict:
    """{stratum_id: [(dug_value, [(target_type, value), ...]), ...]} ascending."""
    out: dict = {}
    for r in _rows("SELECT stratum_id, dug_value, effect_value_1, effect_value_2 "
                   "FROM single_mode_12_dig_bonus ORDER BY stratum_id, dug_value, id"):
        rows = out.setdefault(int(r["stratum_id"]), [])
        dv = int(r["dug_value"])
        if not rows or rows[-1][0] != dv:
            rows.append((dv, []))
        rows[-1][1].append((int(r["effect_value_1"]), int(r["effect_value_2"])))
    return out


@functools.lru_cache(maxsize=1)
def ryokan_ranks() -> list:
    """[(rank, dug_onsen_num, required_onsen_id)] ascending; rank r's passive
    group is its group_id (102..105)."""
    return [(int(r["id"]), int(r["dug_onsen_num"]), int(r["dug_onsen_id"]), int(r["group_id"]))
            for r in _rows("SELECT id, group_id, dug_onsen_num, dug_onsen_id "
                           "FROM single_mode_12_ryokan_rank ORDER BY id")]


@functools.lru_cache(maxsize=1)
def schedules() -> dict:
    """{turn: schedule_id} -- the bathing parties, 24 / 48 / 72."""
    return {int(r["turn_num"]): int(r["id"])
            for r in _rows("SELECT id, turn_num FROM single_mode_12_schedule")}


@functools.lru_cache(maxsize=1)
def dug_results() -> list:
    """[(schedule_id, rank_min, rank_max, result_type)]."""
    return [(int(r["schedule_id"]), int(r["ryokan_rank_min"]), int(r["ryokan_rank_max"]),
             int(r["result_type"]))
            for r in _rows("SELECT schedule_id, ryokan_rank_min, ryokan_rank_max, result_type "
                           "FROM single_mode_12_check_dug_result")]


def dug_result(schedule_id: int, rank: int) -> int:
    for sched, lo, hi, result in dug_results():
        if sched == schedule_id and lo <= rank <= hi:
            return result
    return 1


@functools.lru_cache(maxsize=1)
def spa_tickets() -> dict:
    """{(type_id, chara_id, rarity): ticket_num}."""
    return {(int(r["type_id"]), int(r["chara_id"]), int(r["rarity"])): int(r["ticket_num"])
            for r in _rows("SELECT type_id, chara_id, rarity, ticket_num FROM single_mode_12_spa_ticket")}


@functools.lru_cache(maxsize=1)
def outing_tickets() -> dict:
    """{(chara_id, rarity, story_step): ticket_num} -- Kiyoko's dates."""
    return {(int(r["chara_id"]), int(r["rarity"]), int(r["story_step"])): int(r["ticket_num"])
            for r in _rows("SELECT chara_id, rarity, story_step, ticket_num "
                           "FROM single_mode_12_outing_effect")}


@functools.lru_cache(maxsize=1)
def assistant_params() -> list:
    """[(target_type, value)] -- the PR command's base gains."""
    return [(int(r["target_type"]), int(r["effect_value"]))
            for r in _rows("SELECT target_type, effect_value FROM single_mode_12_assistant_effect "
                           "ORDER BY id")]
