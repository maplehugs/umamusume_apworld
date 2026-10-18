"""RAMEN (scenario 14) -- the scenario's own master.mdb tables, read once.

Every number the scenario runs on that the game ships lives here, straight off
JP's single_mode_14_* tables; see docs/JP_RAMEN_SCENARIO.md §2 for what each
table and each effect/condition code means. Nothing in this module invents a
value -- the constants master does NOT carry (the per-level facility base
values, the gauge rules) are in formula.py, each with its derivation.
"""

from __future__ import annotations

import functools

from ... import master_data

# effect_type -- local to scenario 14 (no shared enum in the client dump).
EFFECT_PARAM = 1            # instant: energy (2,10) / motivation (2,20)
EFFECT_TRAINING = 2         # training effect up N% on a facility
EFFECT_FRIENDSHIP = 4       # friendship bonus N%, friendship trainings only
EFFECT_RACE = 7             # race bonus N%
EFFECT_LIMIT = 10           # per-training gain limit +N: (2, stat) / (2, 0) all / (2, 30) SP
EFFECT_SPECIALTY = 13       # specialty rate +N
EFFECT_HINT_RATE = 14       # hint rate +N%
EFFECT_BOND = 15            # instant: bond +N on every deck card
EFFECT_ALL_TIPS = 16        # instant: every normal deck card gets its hint
EFFECT_TRAINING_TIPS = 17   # the trained facility's hint events all fire
EFFECT_EXTRA_CARDS = 18     # finals: N support-card copies in random trainings
EFFECT_TYPE_HINTS = 19      # instant: N hints from a random deck card of a type
EFFECT_EXTRA_CARD = 20      # instant: a deck card copy appears in facility X
EFFECT_SP_TRAINING = 21     # training effect up N%, skill points only
EFFECT_FAILURE_DOWN = 22    # failure rate down N%

# condition_type
COND_PARAM = 2              # value: 1-5 stat, 10 energy, 20 motivation, 30 SP, 0 all stats
COND_COMMAND = 3            # value: facility command id, 0 any
COND_CARD_TYPE = 5          # value: a card type, spelled as its command id
COND_DECK_TYPES = 6         # value: the deck must hold >= this many card types

# active_effect_array effect_category (dump.cs SingleModeRamenDefine)
CATEGORY_REGION = 1
CATEGORY_BASIC = 2
CATEGORY_SPECIAL_FEELING = 3
CATEGORY_URAF = 4


def _rows(sql: str, params: tuple = ()) -> list:
    try:
        return [dict(r) for r in master_data.query(sql, params)]
    except Exception:                                  # noqa: BLE001
        return []


def conditions(row: dict) -> list:
    """[(condition_type, value)] of an effect row, blanks dropped."""
    out = []
    for i in (1, 2, 3):
        ctype = int(row.get(f"condition_type_{i}") or 0)
        if ctype:
            out.append((ctype, int(row.get(f"condition_value_{i}") or 0)))
    return out


@functools.lru_cache(maxsize=1)
def region_select_turns() -> dict:
    """{turn: region_select_type} -- 3 -> 1, 24 -> 2, 48 -> 3."""
    return {int(r["turn"]): int(r["region_select_type"])
            for r in _rows("SELECT region_select_type, turn FROM single_mode_14_region_select")}


@functools.lru_cache(maxsize=1)
def region_feelings() -> dict:
    """{region_id: {feeling_id: count}} -- the recipe each region costs."""
    out: dict = {}
    for r in _rows("SELECT region_id, feeling_id, feeling_num FROM single_mode_14_region_feeling"):
        out.setdefault(int(r["region_id"]), {})[int(r["feeling_id"])] = int(r["feeling_num"])
    return out


@functools.lru_cache(maxsize=1)
def region_types() -> dict:
    """{region_id: region_select_type} -- which selection a region belongs to."""
    return {int(r["region_id"]): int(r["region_select_type"])
            for r in _rows("SELECT DISTINCT region_id, region_select_type "
                           "FROM single_mode_14_region_feeling")}


@functools.lru_cache(maxsize=1)
def region_effects() -> dict:
    """{region_id: [row, ...]} -- what cooking a region grants."""
    out: dict = {}
    for r in _rows("SELECT * FROM single_mode_14_region_effect ORDER BY id"):
        out.setdefault(int(r["region_id"]), []).append(r)
    return out


@functools.lru_cache(maxsize=1)
def region_effect_by_id() -> dict:
    return {int(r["id"]): r for rows in region_effects().values() for r in rows}


@functools.lru_cache(maxsize=1)
def _region_bonus_rows() -> tuple:
    return tuple(_rows("SELECT region_id, effect_type, min_pt, max_pt, add_value "
                       "FROM single_mode_14_region_effect_bonus"))


def region_effect_bonus(region_id: int, effect_type: int, pt: int) -> int:
    """How much this period's pt (held BEFORE the tasting) upgrades a region
    effect -- e.g. region 1's training effect 20 -> 30 at 1500 pt."""
    for r in _region_bonus_rows():
        if (int(r["region_id"]) == region_id and int(r["effect_type"]) == effect_type
                and int(r["min_pt"]) <= pt <= int(r["max_pt"])):
            return int(r["add_value"])
    return 0


@functools.lru_cache(maxsize=1)
def basic_effects() -> dict:
    """{check_point_type: [row, ...]} -- every tasting's base effects."""
    out: dict = {}
    for r in _rows("SELECT * FROM single_mode_14_basic_effect ORDER BY id"):
        out.setdefault(int(r["check_point_type"]), []).append(r)
    return out


@functools.lru_cache(maxsize=1)
def basic_effect_by_id() -> dict:
    return {int(r["id"]): r for rows in basic_effects().values() for r in rows}


@functools.lru_cache(maxsize=1)
def check_points() -> dict:
    """{check_point_type: {turn, success_pt, great_success_pt}}."""
    return {int(r["check_point_type"]): {"turn": int(r["turn"]),
                                         "success_pt": int(r["success_pt"]),
                                         "great_success_pt": int(r["great_success_pt"])}
            for r in _rows("SELECT * FROM single_mode_14_check_point")}


def check_point_for_turn(turn) -> int:
    """The Jamboree held on this turn (1/2/3), or 0."""
    for cp_type, row in check_points().items():
        if row["turn"] == int(turn or 0):
            return cp_type
    return 0


def period_of(turn) -> int:
    """The check_point_type whose period a turn belongs to: turns <= 24 are
    the junior Jamboree's, <= 48 the classic's, the rest the senior's."""
    turn = int(turn or 0)
    for cp_type in sorted(check_points()):
        if turn <= check_points()[cp_type]["turn"]:
            return cp_type
    return max(check_points() or {3: 0})


@functools.lru_cache(maxsize=1)
def tasting_gain_pt() -> dict:
    """{check_point_type: pt per tasting} -- 300 / 400 / 500."""
    return {int(r["check_point_type"]): int(r["gain_pt"])
            for r in _rows("SELECT check_point_type, gain_pt FROM single_mode_14_check_point_pt")}


@functools.lru_cache(maxsize=1)
def _pt_effect_rows() -> tuple:
    return tuple(_rows("SELECT pt_min, pt_max, effect_type, effect_value "
                       "FROM single_mode_14_check_point_pt_effect"))


def pt_effect(pt: int, effect_type: int) -> int:
    """A live bonus off this period's running pt (§6.3)."""
    return sum(int(r["effect_value"]) for r in _pt_effect_rows()
               if int(r["effect_type"]) == effect_type
               and int(r["pt_min"]) <= int(pt) <= int(r["pt_max"]))


@functools.lru_cache(maxsize=1)
def _result_effect_rows() -> tuple:
    return tuple(_rows("SELECT check_point_type, result_state, effect_type, effect_value "
                       "FROM single_mode_14_check_point_effect"))


def result_effect(check_point_type: int, result_state: int, effect_type: int) -> int:
    """A passive a Jamboree result grants for the rest of the run."""
    return sum(int(r["effect_value"]) for r in _result_effect_rows()
               if int(r["check_point_type"]) == check_point_type
               and int(r["result_state"]) == result_state
               and int(r["effect_type"]) == effect_type)


@functools.lru_cache(maxsize=1)
def _feeling_bonus_rows() -> tuple:
    return tuple(_rows("SELECT feeling_num_min, feeling_num_max, add_value "
                       "FROM single_mode_14_feeling_bonus"))


def feeling_bonus(tricks_held: int) -> int:
    """The Jamboree energy bonus by tricks held: 0 / 3 / 5 / 10."""
    for r in _feeling_bonus_rows():
        if int(r["feeling_num_min"]) <= tricks_held <= int(r["feeling_num_max"]):
            return int(r["add_value"])
    return 0


@functools.lru_cache(maxsize=1)
def deck_link_types() -> dict:
    """{support_card_id: deck_type} -- 1 the older Tazuna/Light Hello cards,
    2 the SSR Tazuna 30305."""
    return {int(r["support_card_id"]): int(r["deck_type"])
            for r in _rows("SELECT deck_type, support_card_id FROM single_mode_14_deck_info")}


@functools.lru_cache(maxsize=1)
def outing_secrets() -> dict:
    """{(support_card_id, story_step): secret ingredients} for a link card's
    date steps."""
    return {(int(r["support_card_id"]), int(r["story_step"])): int(r["special_feeling_num"])
            for r in _rows("SELECT support_card_id, story_step, special_feeling_num "
                           "FROM single_mode_14_outing_effect")}


@functools.lru_cache(maxsize=1)
def finals_effects() -> list:
    return _rows("SELECT * FROM single_mode_14_finals_effect ORDER BY id")


@functools.lru_cache(maxsize=1)
def finals_effect_by_id() -> dict:
    return {int(r["id"]): r for r in finals_effects()}


@functools.lru_cache(maxsize=1)
def finals_skills() -> dict:
    """{select_type: row} -- the Ultimate Ramen skill and its hint levels."""
    return {int(r["select_type"]): r for r in _rows("SELECT * FROM single_mode_14_finals_gain_skill")}


def effect_row(category: int, effect_id: int) -> dict | None:
    """The master row behind an active_effect_array entry."""
    table = {CATEGORY_REGION: region_effect_by_id, CATEGORY_BASIC: basic_effect_by_id,
             CATEGORY_URAF: finals_effect_by_id}.get(int(category))
    return table().get(int(effect_id)) if table else None
