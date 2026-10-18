"""BEYOND DREAMS (scenario 13) -- the scenario's own master.mdb tables, read once.

Every number the scenario runs on that the game ships is here, straight off
JP's single_mode_13_* tables; docs/JP_BEYOND_DREAMS_SCENARIO.md §2 says what
each table and code means. The constants master does NOT carry (the per-level
facility base values, energy, starting DP, the goal-reward bases) are in
formula.py and impl.py, each with its derivation.
"""

from __future__ import annotations

import functools

from ... import master_data

CASINO_CHARA = 1139          # SINGLE_MODE_SCENARIO_BREEDERS_UNIQUE_CHARA_ID
CASINO_SSR = 30290           # [American Dream]
CASINO_R = 10141             # [『DREAMS』責任者]
ADVISOR_TARGET = 115         # Casino as an NPC partner when her card is not in the deck
DRESS_CHARA = 1132           # DRESS_CHANGE_TARGET_CHARA_ID

# single_mode_13_add_dream_point.deck_id / breeders_data_set_start.deck_id
DECK_NONE, DECK_R, DECK_SSR = 1, 2, 3
DP_RANK_UP = 1               # condition_type 1: a member ranked up
DP_REVIEW = 2                # condition_type 2: Reflection N (condition_value)

# single_mode_13_team_sp_effect.group_type / enhance_group_array.group_type
GROUP_COMMON = 0
GROUP_PHYSICAL = 1           # client EnhanceGroupType.BaseParam
GROUP_TECHNIQUE = 2          # client SkillHint -- the guides' "Technique"
GROUP_MENTAL = 3             # client ExtendLimit -- the guides' "Mental"
GROUPS = (GROUP_PHYSICAL, GROUP_TECHNIQUE, GROUP_MENTAL)

# single_mode_13_team_sp_effect.effect_type (client TeamSpTrainingEffectType)
EFF_TAG_TRAINING = 2         # friendship bonus %, on friendship trainings
EFF_SUB_PARAM = 3            # sub-stats paid at this % (group 0's 10 = -90%)
EFF_ALL_TIPS = 5             # claim every hint on the board
EFF_SKILL_PT = 6             # SP %, added to the member bonus
EFF_EVALUATION = 7           # bond + on the trained cards
EFF_FAIL = 8                 # failure rate -%
EFF_CONSUME_HP = 9           # energy cost % (negative)
EFF_GUARANTEE_TIPS = 10      # N random cards get a hint
EFF_BASE_MAIN_LIMIT = 11     # the home line's per-stat cap +N
EFF_ADD_MAIN_LIMIT = 12      # the bonus line's per-stat cap +N
EFF_BASE_SP_LIMIT = 15       # the home line's SP cap +N
EFF_ADD_SP_LIMIT = 16        # the bonus line's SP cap +N

# single_mode_13_team_rank.effect_type (client TeamRankBonusType names 1 and 3)
TEAM_TAG_TRAINING = 1        # friendship bonus %, on friendship trainings
TEAM_SPECIALTY = 2           # specialty rate (unnamed in the client; the guides)
TEAM_HINT_RATE = 3           # hint rate %

MEETING_TURN = 3             # TEAM_MEETING_COMMAND_ENABLE_TURN
STOCK_NORMAL = 2             # TEAM_SP_TRAINING_STOCK_NORMAL_LIMIT
STOCK_LIMIT_UP = 4           # TEAM_SP_TRAINING_STOCK_LIMITUP_LIMIT
TRACK_SANTA_ANITA = 10202
TRACK_DEL_MAR = 10203


def _rows(sql: str, params: tuple = ()) -> list:
    try:
        return [dict(r) for r in master_data.query(sql, params)]
    except Exception:                                  # noqa: BLE001
        return []


@functools.lru_cache(maxsize=1)
def members() -> dict:
    """{chara_id: (bc_group_id, bc_npc_id)} -- the five DREAMS candidates."""
    return {int(r["chara_id"]): (int(r["bc_group_id"]), int(r["bc_npc_id"]))
            for r in _rows("SELECT chara_id, bc_group_id, bc_npc_id FROM single_mode_13_member "
                           "ORDER BY id")}


@functools.lru_cache(maxsize=1)
def ranks() -> dict:
    """{rank: (rank_exp, bonus_group)} -- 17 ranks, 3 exp each, rank 17 max."""
    return {int(r["rank_id"]): (int(r["rank_exp"]), int(r["rank_bonus_effect_group_id"]))
            for r in _rows("SELECT rank_id, rank_exp, rank_bonus_effect_group_id "
                           "FROM single_mode_13_rank")}


def max_rank() -> int:
    return max(ranks(), default=17)


def rank_exp(rank: int) -> int:
    return ranks().get(int(rank), (3, 0))[0]


@functools.lru_cache(maxsize=1)
def _rank_bonus_rows() -> dict:
    """{group: {condition_type: value}} -- training effect % (type 1)."""
    out: dict = {}
    for r in _rows("SELECT group_id, condition_type, effect_value FROM "
                   "single_mode_13_rank_bonus_effect_group WHERE effect_type=1"):
        out.setdefault(int(r["group_id"]), {})[int(r["condition_type"])] = int(r["effect_value"])
    return out


def member_bonus(rank: int, full: bool) -> int:
    """A member's training effect %: her rank's always-on value, +30 while her
    gauge is full (condition 1)."""
    group = ranks().get(int(rank), (3, int(rank)))[1]
    row = _rank_bonus_rows().get(group, {})
    return int(row.get(0, 0)) + (int(row.get(1, 0)) if full else 0)


@functools.lru_cache(maxsize=1)
def _team_rank_rows() -> dict:
    out: dict = {}
    for r in _rows("SELECT rank_group, effect_type, effect_value FROM single_mode_13_team_rank"):
        out.setdefault(int(r["rank_group"]), {})[int(r["effect_type"])] = int(r["effect_value"])
    return out


def team_rank_effect(team_rank: int, effect_type: int) -> int:
    return int(_team_rank_rows().get(int(team_rank), {}).get(effect_type, 0))


@functools.lru_cache(maxsize=1)
def schedules() -> list:
    """[(schedule_id, meeting_turn, start_turn, end_turn, need_team_rank, team_sp_lv)]."""
    return [(int(r["id"]), int(r["meeting_turn"]), int(r["start_turn"]), int(r["end_turn"]),
             int(r["need_team_rank"]), int(r["team_sp_lv"]))
            for r in _rows("SELECT * FROM single_mode_13_schedule ORDER BY id")]


def review_turns() -> dict:
    """{review turn: schedule_id} -- 12/24/36/48/60 (rows with a need)."""
    return {end: sid for sid, _m, _s, end, need, _lv in schedules() if need and end}


def schedule(schedule_id: int) -> tuple | None:
    return next((s for s in schedules() if s[0] == int(schedule_id)), None)


def level_limit_at(turn: int) -> int:
    """team_sp_level_limit: the team_sp_lv of the schedule row whose
    start..end holds `turn` (the limit after Reflection N is row N's)."""
    for _sid, _m, start, end, _need, lv in schedules():
        if start <= int(turn) <= (end or 99):
            return lv
    return schedules()[-1][5] if schedules() else 3


@functools.lru_cache(maxsize=1)
def dream_points() -> dict:
    """{(deck_id, condition_type, condition_value): value}."""
    return {(int(r["deck_id"]), int(r["condition_type"]), int(r["condition_value"])): int(r["value"])
            for r in _rows("SELECT deck_id, condition_type, condition_value, value "
                           "FROM single_mode_13_add_dream_point")}


def dp_rank_up(deck_id: int) -> int:
    return dream_points().get((int(deck_id), DP_RANK_UP, 0), 1)


def dp_review(deck_id: int, schedule_id: int) -> int:
    return dream_points().get((int(deck_id), DP_REVIEW, int(schedule_id)), 3)


@functools.lru_cache(maxsize=1)
def sp_levels() -> dict:
    """{(group_type, level): (need_point, effect_group)}."""
    return {(int(r["group_type"]), int(r["level"])): (int(r["need_point"]), int(r["effect_group"]))
            for r in _rows("SELECT group_type, level, need_point, effect_group "
                           "FROM single_mode_13_team_sp_level")}


def max_sp_level() -> int:
    return max((lv for g, lv in sp_levels() if g), default=8)


@functools.lru_cache(maxsize=1)
def sp_effects() -> dict:
    """{effect_group: [(id, effect_type, num_support_type, effect_value)]} in id order."""
    out: dict = {}
    for r in _rows("SELECT id, effect_group, effect_type, num_support_type, effect_value "
                   "FROM single_mode_13_team_sp_effect ORDER BY id"):
        out.setdefault(int(r["effect_group"]), []).append(
            (int(r["id"]), int(r["effect_type"]), int(r["num_support_type"]), int(r["effect_value"])))
    return out


@functools.lru_cache(maxsize=1)
def bc_programs() -> dict:
    """{program_id: (bc_group_id, determine_race_flag, skill_id)}."""
    return {int(r["program_id"]): (int(r["bc_group_id"]), int(r["determine_race_flag"]),
                                   int(r["skill_id"]))
            for r in _rows("SELECT program_id, bc_group_id, determine_race_flag, skill_id "
                           "FROM single_mode_13_bc_program_flag")}


# race_instance.npc_group_id of a BC program -> the single_mode_npc group its
# field is drawn from. 1301->61, 1302->62, 1304->63 and 1309->67 are captured
# (umacap, 4 BC fields); the rest are INFERRED by matching each group's
# ground/distance aptitudes to the course (1303 turf 2000/2200, 1305-1308 dirt
# 1200/1400/1600/1800).
BC_NPC_GROUPS = {1301: 61, 1302: 62, 1303: 64, 1304: 63, 1305: 65,
                 1306: 68, 1307: 69, 1308: 66, 1309: 67}


@functools.lru_cache(maxsize=32)
def bc_npc_rows(program_id: int) -> tuple:
    """The single_mode_npc rows a BC program's field is drawn from, or ()."""
    row = master_data.query_one(
        "SELECT ri.npc_group_id FROM single_mode_program p JOIN race_instance ri "
        "ON ri.id=p.race_instance_id WHERE p.id=?", (int(program_id),))
    group = BC_NPC_GROUPS.get(int(row["npc_group_id"])) if row else None
    if not group:
        return ()
    return tuple(dict(r) for r in _rows(
        "SELECT * FROM single_mode_npc WHERE npc_group_id=? ORDER BY id", (group,)))


def program_track(program_id: int) -> int:
    """3101-3109 run at Santa Anita, 3110-3118 at Del Mar (§2)."""
    row = master_data.query_one(
        "SELECT cs.race_track_id FROM single_mode_program p JOIN race_instance ri "
        "ON ri.id=p.race_instance_id JOIN race r ON r.id=ri.race_id JOIN race_course_set cs "
        "ON cs.id=r.course_set WHERE p.id=?", (int(program_id),))
    return int(row["race_track_id"]) if row else 0


def track_programs(track_id: int) -> list:
    return sorted(p for p in bc_programs() if program_track(p) == int(track_id))


def skill_group(skill_id: int) -> int:
    row = master_data.query_one("SELECT group_id FROM skill_data WHERE id=?", (int(skill_id),))
    return int(row["group_id"]) if row else 0
