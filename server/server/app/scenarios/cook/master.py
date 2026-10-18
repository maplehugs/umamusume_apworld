"""豊食祭 (scenario 8) -- the scenario's own master.mdb tables, read once.

docs/JP_FOOD_FESTIVAL_SCENARIO.md §2-§8 say what each table and code means:

    single_mode_cook_dish            35 dishes: set, group, tier, cost, power
    single_mode_cook_dish_material   cost per material group
    single_mode_cook_dish_effect     effects per effect group (2, 21, 201-203)
    single_mode_cook_success_odds    great-success rate by friends power
    single_mode_cook_success_effect  great-success effects: rate, odds, conditions
    single_mode_cook_power_data      the five tastings: turn, thresholds, garden level
    single_mode_cook_garden_level    facility level -> garden level needed, cost
    single_mode_cook_garden_effect   110 stock cap, 130 harvest, 100/140/150 dish boosts
    single_mode_cook_material_rate   harvest multiplier by boost type and tag count
    single_mode_cook_coin_rate       care points by period and tag count
    single_mode_cook_dish_name       flavour texts (display_flavor_text_id)

The numbers master does NOT carry (the friends-power effect table, the facility
base values) are in formula.py with their evidence.
"""

from __future__ import annotations

import collections
import functools

from ... import master_data

MATERIALS = (100, 200, 300, 400, 500)        # carrot, garlic, potato, chili, strawberry
# A training's material (§3): its facility's vegetable. The camp ids map the same.
COMMAND_MATERIAL = {101: 100, 105: 200, 102: 300, 103: 400, 106: 500}

# garden_effect.effect_type
GE_DISH_TRAINING = 100       # + value_4 to a type-2 dish effect of groups value_1 / value_2
GE_STOCK_CAP = 110           # value_2 = the material's stock cap
GE_HARVEST = 130             # value_1 1 passive / 2 chosen, value_3 the amount
GE_DISH_ENERGY = 140         # + value_4 energy on cooking groups value_1 / value_2
GE_DISH_RACE = 150           # + value_4 to a type-21 dish effect of groups value_1 / value_2

# dish_effect / success_effect effect_type
EFF_TRAINING = 2             # training gain %, commands in value_2-4 (0 = all)
EFF_RACE = 21                # race reward % (§7a2)
EFF_ENERGY = 201
EFF_MOTIVATION = 202
EFF_BOND = 203
EFF_EXTRA_CARD = 204         # success effect: +value_1 extra cards on the dish's facility
EFF_MAX_ENERGY = 205
LASTING = (EFF_TRAINING, EFF_RACE)           # what dish_info keeps (§6)


def _rows(table: str) -> list:
    if not master_data.has_table(table):
        return []
    return [dict(r) for r in master_data.query(f"SELECT * FROM {table} ORDER BY id")]


@functools.lru_cache(maxsize=1)
def dishes() -> dict:
    return {int(r["id"]): {k: int(v or 0) for k, v in r.items()}
            for r in _rows("single_mode_cook_dish")}


@functools.lru_cache(maxsize=1)
def dish_costs() -> dict:
    """{material_group_id: {material_id: n}}"""
    out = collections.defaultdict(dict)
    for r in _rows("single_mode_cook_dish_material"):
        out[int(r["material_group_id"])][int(r["material_id"])] = int(r["material_num"])
    return dict(out)


@functools.lru_cache(maxsize=1)
def dish_effects() -> dict:
    """{effect_group_id: [(type, v1, v2, v3, v4)]} in master order."""
    out = collections.defaultdict(list)
    for r in _rows("single_mode_cook_dish_effect"):
        out[int(r["effect_group_id"])].append(tuple(int(r[k] or 0) for k in (
            "effect_type", "effect_value_1", "effect_value_2", "effect_value_3", "effect_value_4")))
    return dict(out)


@functools.lru_cache(maxsize=1)
def success_odds() -> list:
    return [(int(r["power_min"]), int(r["power_max"]), int(r["success_rate"]))
            for r in _rows("single_mode_cook_success_odds")]


def success_rate_band(power: int) -> int:
    """success_odds' inclusive band (client FriendsPowerModel, §11)."""
    return next((rate for lo, hi, rate in success_odds() if lo <= int(power) <= hi), 0)


@functools.lru_cache(maxsize=1)
def success_effects() -> dict:
    """{success_effect_group_id: [row]} in id order."""
    out = collections.defaultdict(list)
    for r in _rows("single_mode_cook_success_effect"):
        out[int(r["effect_group_id"])].append({k: int(v or 0) for k, v in r.items()})
    return dict(out)


@functools.lru_cache(maxsize=1)
def power_data() -> dict:
    """{cook_type: row} -- the five tastings."""
    return {int(r["cook_type"]): {k: int(v or 0) for k, v in r.items()}
            for r in _rows("single_mode_cook_power_data")}


def tasting_for_turn(turn) -> int:
    """The cook_type tasted on this turn, else 0."""
    return next((k for k, r in power_data().items() if r["turn_num"] == int(turn or 0)), 0)


@functools.lru_cache(maxsize=1)
def garden_levels() -> dict:
    """{(facility_id, facility_lv): {garden_lv, effect_group_id, coin_num}}"""
    return {(int(r["facility_id"]), int(r["facility_lv"])):
            {"garden_lv": int(r["garden_lv"]), "effect_group_id": int(r["effect_group_id"]),
             "coin_num": int(r["coin_num"])}
            for r in _rows("single_mode_cook_garden_level")}


@functools.lru_cache(maxsize=1)
def garden_effects() -> dict:
    """{effect_group_id: [(type, v1, v2, v3, v4)]}"""
    out = collections.defaultdict(list)
    for r in _rows("single_mode_cook_garden_effect"):
        out[int(r["effect_group_id"])].append(tuple(int(r[k] or 0) for k in (
            "effect_type", "effect_value_1", "effect_value_2", "effect_value_3", "effect_value_4")))
    return dict(out)


def facility_effects(facility_id: int, level: int) -> list:
    row = garden_levels().get((int(facility_id), int(level)))
    return garden_effects().get(row["effect_group_id"], []) if row else []


def stock_cap(facility_id: int, level: int) -> int:
    return next((v2 for t, _v1, v2, _v3, _v4 in facility_effects(facility_id, level)
                 if t == GE_STOCK_CAP), 999)


def harvest_amount(facility_id: int, level: int, kind: int) -> int:
    """garden_effect 130: kind 1 the cycle's passive base, 2 a care's chosen amount."""
    return next((v3 for t, v1, _v2, v3, _v4 in facility_effects(facility_id, level)
                 if t == GE_HARVEST and v1 == kind), 0)


@functools.lru_cache(maxsize=1)
def material_rates() -> dict:
    """{(boost_type, material_count): rate}"""
    return {(int(r["boost_type"]), int(r["material_count"])): int(r["material_quantity_rate"])
            for r in _rows("single_mode_cook_material_rate")}


@functools.lru_cache(maxsize=1)
def coin_rates() -> dict:
    """{(period, material_count): rate}"""
    return {(int(r["period"]), int(r["material_count"])): int(r["coin_quantity_rate"])
            for r in _rows("single_mode_cook_coin_rate")}


@functools.lru_cache(maxsize=1)
def dish_names() -> list:
    return [{k: int(v or 0) for k, v in r.items()} for r in _rows("single_mode_cook_dish_name")]


def dish_ids_of_set(dish_set_id: int) -> list:
    return [i for i, d in sorted(dishes().items()) if d["dish_set_id"] == int(dish_set_id)]
