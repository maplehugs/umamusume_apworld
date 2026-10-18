"""RUN! MECHA UMAMUSUME (scenario 9) -- the scenario's own master.mdb tables, read once.

docs/JP_MECHA_SCENARIO.md §1, §3, §7.3, §8.1 and §10 say what each table and
code means:

    single_mode_09_board            the three cores (1 Head, 2 Chest, 3 Leg)
    single_mode_09_chip             chips: board, type, the UGE that opens them
    single_mode_09_chip_effect      chip / core effects per point
    single_mode_09_learning_bonus   the research-level training boost
    single_mode_09_link_effect      the five link characters' effects
    single_mode_09_progress_rate    research progress -> UGE grade
    single_mode_09_schedule         the five UGEs: turn, target, ST-2's dress
    single_mode_09_training_boost   the cores' per-research-level stat boosts

The numbers master does NOT carry (facility base values, the gear bonus by
half-year, the UGE rewards and EN) are in formula.py and impl.py, each with its
evidence.
"""

from __future__ import annotations

import functools

from ... import master_data

# The training facilities in research order. Status types are the client's
# EventGainStatusType (101 speed .. 106 wit).
SPEED, STAMINA, POWER, GUTS, WIZ = 101, 105, 102, 103, 106
STATUS_KEYS = {SPEED: "speed", STAMINA: "stamina", POWER: "power", GUTS: "guts", WIZ: "wiz"}
RESEARCH_ORDER = (SPEED, STAMINA, POWER, GUTS, WIZ)

# Chips (§8.1). Type-1 chips per board in the wire's order; 200x the board totals.
HEAD, CHEST, LEG = 1, 2, 3
BOARD_CHIPS = {HEAD: (1005, 1006, 1007), CHEST: (1002, 1004, 1008), LEG: (1001, 1003, 1009)}
BOARD_TOTAL = {HEAD: 2001, CHEST: 2002, LEG: 2003}
BASE_CHIP = 2000
CHIP_MAX = 5
RESEARCH_CHIP_OF = {SPEED: 1001, STAMINA: 1002, POWER: 1003, GUTS: 1004, WIZ: 1005}
CHIP_HINT_RATE = 1006
CHIP_SPECIALTY = 1007
CHIP_FRIENDSHIP = 1008
CHIP_SP = 1009

# single_mode_09_chip_effect.effect_type (§7.3, §8.1).
EFF_HINT_RATE = 2
EFF_ENERGY_DOWN = 4
EFF_TRAINING = 5
EFF_RESEARCH = 6
EFF_FRIENDSHIP = 12
EFF_BOND = 15
EFF_ALL_HINTS = 17
EFF_ALL_GEARS = 18
EFF_STAT_BOOST = 19
EFF_HINTS_TAKE_EFFECT = 20
EFF_INSTANT = 22             # (10, N) energy, (20, N) motivation, on activation
EFF_SP = 24
EFF_MEMBER = 25
EFF_SPECIALTY = 26
EFF_EXTRA_PARTNERS = 27

# single_mode_09_link_effect.effect_type (§10).
LINK_GEARS = 14
LINK_START = 28              # (1, N) research levels, (2, N) gauge energy
LINK_EN = 29
LINK_LEARNING = 30
LINK_CHARAS = (1023, 1050, 1036, 1083, 1084)   # Biwa, Taishin, Shakur, Kris, Gimlet
LINK_EN_CAP = 2              # text 199/200: 最大+2

MECHA_CHARA = 2008           # ST-2 (MECHA_CHARA_ID)
LIVE_MUSIC = 1094            # LIVE_MUSIC_ID


def _rows(sql: str, params: tuple = ()) -> list:
    try:
        return [dict(r) for r in master_data.query(sql, params)]
    except Exception:                                  # noqa: BLE001
        return []


@functools.lru_cache(maxsize=1)
def chips() -> dict:
    """{chip_id: (board_id, type, schedule_id)}."""
    rows = _rows("SELECT id, schedule_id, type, board_id FROM single_mode_09_chip")
    return {int(r["id"]): (int(r["board_id"]), int(r["type"]), int(r["schedule_id"])) for r in rows}


def chip_open(chip_id: int, uges_done: int) -> bool:
    """A type-1 chip takes points once its UGE is done (schedule_id 0 = always)."""
    row = chips().get(int(chip_id))
    return bool(row) and row[1] == 1 and row[2] <= int(uges_done)


@functools.lru_cache(maxsize=1)
def _chip_effects() -> dict:
    out: dict = {}
    for r in _rows("SELECT chip_id, point, group_id, effect_category, effect_type, effect_value_1, "
                   "effect_value_2, effect_value_3, effect_value_4 FROM single_mode_09_chip_effect "
                   "ORDER BY id"):
        out.setdefault(int(r["chip_id"]), []).append(
            (int(r["point"]), int(r["group_id"]), int(r["effect_type"]), int(r["effect_value_1"]),
             int(r["effect_value_2"]), int(r["effect_value_3"]), int(r["effect_value_4"])))
    return out


def chip_effect(chip_id: int, points: int) -> list:
    """A type-1 chip's effect at its points: [(type, v1, v2, v3, v4)]."""
    return [(t, v1, v2, v3, v4) for pt, _g, t, v1, v2, v3, v4 in _chip_effects().get(int(chip_id), ())
            if pt == int(points)]


def core_effects(board_totals: dict) -> list:
    """The overdrive effects (§7.3): chip 2000 always, and each core's highest
    row reached per group. [(type, v1, v2, v3, v4)]."""
    out = [(t, v1, v2, v3, v4) for _pt, _g, t, v1, v2, v3, v4 in _chip_effects().get(BASE_CHIP, ())]
    for board, total_chip in sorted(BOARD_TOTAL.items()):
        have = int(board_totals.get(board, 0))
        best: dict = {}
        for pt, grp, t, v1, v2, v3, v4 in _chip_effects().get(total_chip, ()):
            if pt <= have and (grp not in best or pt > best[grp][0]):
                best[grp] = (pt, (t, v1, v2, v3, v4))
        out += [row for _grp, (_pt, row) in sorted(best.items())]
    return out


@functools.lru_cache(maxsize=1)
def learning_bonus() -> list:
    """[(point_min, point_max, base_value, bonus_value)]."""
    return [(int(r["point_min"]), int(r["point_max"]), int(r["base_value"]), int(r["bonus_value"]))
            for r in _rows("SELECT * FROM single_mode_09_learning_bonus ORDER BY id")]


@functools.lru_cache(maxsize=1)
def link_effects() -> dict:
    """{chara_id: [(type, v1, v2)]}."""
    out: dict = {}
    for r in _rows("SELECT chara_id, effect_type, effect_value_1, effect_value_2 "
                   "FROM single_mode_09_link_effect ORDER BY id"):
        out.setdefault(int(r["chara_id"]), []).append(
            (int(r["effect_type"]), int(r["effect_value_1"]), int(r["effect_value_2"])))
    return out


@functools.lru_cache(maxsize=1)
def progress_rates() -> list:
    """[(min, max, result_type)]."""
    return [(int(r["progress_min"]), int(r["progress_max"]), int(r["result_type"]))
            for r in _rows("SELECT * FROM single_mode_09_progress_rate ORDER BY id")]


def grade_for(progress: int) -> int:
    for lo, hi, result in progress_rates():
        if lo <= int(progress) <= hi:
            return result
    return 1


@functools.lru_cache(maxsize=1)
def schedules() -> dict:
    """{schedule_id: (turn, target_pt, stock_num, dress_id)}."""
    rows = _rows("SELECT * FROM single_mode_09_schedule ORDER BY id")
    return {int(r["id"]): (int(r["turn_num"]), int(r["target_pt"]), int(r["stock_num"]),
                           int(r["dress_id"])) for r in rows}


def schedule_for_turn(turn: int) -> int:
    return next((sid for sid, row in schedules().items() if row[0] == int(turn or 0)), 0)


@functools.lru_cache(maxsize=1)
def _boosts() -> dict:
    out: dict = {}
    for r in _rows("SELECT boost_set_id, level_min, level_max, add_value FROM single_mode_09_training_boost"):
        out.setdefault(int(r["boost_set_id"]), []).append(
            (int(r["level_min"]), int(r["level_max"]), int(r["add_value"])))
    return out


def boost(set_id: int, total_research: int) -> int:
    """+% for a set at the five levels' total (set 1 per 300, 2 per 200, 3 per 150)."""
    return next((v for lo, hi, v in _boosts().get(int(set_id), ()) if lo <= total_research <= hi), 0)


@functools.lru_cache(maxsize=1)
def partner_rows() -> tuple:
    """(partner_id, chara_id) of scenario 9's NPC trainers (single_mode_unique_chara)."""
    return tuple((int(r["partner_id"]), int(r["chara_id"])) for r in _rows(
        "SELECT partner_id, chara_id FROM single_mode_unique_chara WHERE scenario_id=9 "
        "ORDER BY partner_id"))
