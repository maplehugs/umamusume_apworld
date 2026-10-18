"""Career training gains, costs, failure rates and support-card effects.

Facility bases and trainee growth come from the region's master data. Callers
supply current facility levels, placements, bond, card levels and scenario
bonuses. The formula includes friendship, unique effects and the stat soft cap;
remaining assumptions are documented alongside the relevant calculation.
Community reference tables provide facility level boosts and card fallbacks.
"""

from __future__ import annotations

import functools
import json
import logging
import math
import random
from pathlib import Path

from . import config, master_data

log = logging.getLogger("uma-server")

REF_DIR = Path(__file__).resolve().parents[1] / "data" / "training_ref"

@functools.lru_cache(maxsize=None)
def trainee_growth_rates(card_id: int) -> tuple[int, ...]:
    """Speed/stamina/power/guts/wisdom growth for this exact trainee variant.

    Master is region-specific and includes cards missing from the old community
    file. An unknown card retains the zero-growth fallback.
    """
    row = master_data.query_one(
        "SELECT talent_speed, talent_stamina, talent_pow, talent_guts, talent_wiz "
        "FROM card_data WHERE id=?", (card_id,))
    return tuple(row) if row is not None else (0, 0, 0, 0, 0)

with open(REF_DIR / "cards.json", encoding="utf-8") as f:
    _CARDS = json.load(f)


class _MasterBackedCards(dict):
    """cards.json, with master.mdb standing in for any card it does not list.

    cards.json is a Global extraction: it holds every one of Global's 255
    support cards and none of the 28 JP-only ones (30304 Meisho Doto, 30305
    Tazuna, ...), so on JP those cards had no type, no specialty and no
    effects -- they never favoured their own facility, never rainbowed and
    never hinted. A card cards.json DOES list is served from it unchanged,
    and Global has no card it lacks, so Global's lookups are untouched."""

    def get(self, key, default=None):
        hit = dict.get(self, key)
        if hit is not None:
            return hit
        built = _card_from_master(key)
        return built if built is not None else default

    def __contains__(self, key):
        return dict.__contains__(self, key) or _card_from_master(key) is not None

    def __getitem__(self, key):
        hit = self.get(key)
        if hit is None:
            raise KeyError(key)
        return hit


CARD_BY_ID = _MasterBackedCards({c["id"]: c for c in _CARDS})

# support_card_data.command_id -> cards.json "type", for a normal (type 1)
# card; 2 is a friend card, 3 a group card.
_MASTER_CARD_TYPE = {101: "speed", 105: "stamina", 102: "power", 103: "guts", 106: "wisdom"}
_MASTER_RARITY = {1: "R", 2: "SR", 3: "SSR"}
# cards.json effect key -> support_card_effect_table.type. The value is the
# card's MAX-level one, which is what cards.json's effects[-1] holds.
_MASTER_EFFECT_KEYS = {
    "friendship_bonus": 1, "mood_effect": 2, "speed_bonus": 3, "stamina_bonus": 4,
    "power_bonus": 5, "guts_bonus": 6, "wisdom_bonus": 7, "training_bonus": 8,
    "initial_friendship_gauge": 14, "race_bonus": 15, "fan_bonus": 16,
    "hint_levels": 17, "hint_frequency": 18, "specialty_priority": 19,
    "skill_point_bonus": 30,
}


@functools.lru_cache(maxsize=256)
def _card_from_master(key):
    """A cards.json-shaped entry built from master.mdb, or None."""
    try:
        card_id = int(key)
    except (TypeError, ValueError):
        return None
    try:
        row = master_data.query_one(
            "SELECT support_card_type, command_id, rarity FROM support_card_data "
            "WHERE id=?", (card_id,))
    except Exception:                                  # noqa: BLE001
        return None
    if row is None:
        return None
    kind = int(row["support_card_type"] or 1)
    ctype = ("friend" if kind == 2 else "group" if kind == 3
             else _MASTER_CARD_TYPE.get(int(row["command_id"] or 0)))
    effects = {}
    for name, etype in _MASTER_EFFECT_KEYS.items():
        value = master_effect(card_id, etype)
        if value:
            effects[name] = int(value) if float(value).is_integer() else value
    return {"id": str(card_id), "title": "", "rarity": _MASTER_RARITY.get(row["rarity"], "SSR"),
            "type": ctype, "effects": [effects],
            "source": "master"}

with open(REF_DIR / "training_data.json", encoding="utf-8") as f:
    _TRAINING_DATA = json.load(f)
FACILITIES_BY_SCENARIO = {
    entry["scenario"]: entry["facilities"]
    for entry in _TRAINING_DATA
    if "scenario" in entry
}
LEVEL_BOOSTS = next(e["trainingLevelBoosts"] for e in _TRAINING_DATA if "trainingLevelBoosts" in e)

STAT_NAMES = ["speed", "stamina", "power", "guts", "wiz"]  # matches chara_info's field names
CARD_TYPE_NAMES = ["speed", "stamina", "power", "guts", "wisdom"]  # matches cards.json's "type" values
BASE_MOOD_MULTS = [-20, -10, 0, 10, 20]
MAX_STAT_1200_HALVING = 1200

_command_to_facility: dict[int, int] | None = None


def _facility_index_for(command_id: int) -> int | None:
    """base_command_id 101/102/103/106/105 -> facility 0/1/2/3/4. Queried
    from master.mdb rather than hardcoded so aliases (e.g. 601-605 for
    summer camp, which share base_command_id with the normal 101-106 IDs)
    resolve automatically."""
    global _command_to_facility
    if _command_to_facility is None:
        rows = master_data.query(
            "SELECT DISTINCT command_id, base_command_id FROM single_mode_training"
        )
        # facility type index (matches CARD_TYPE_NAMES: speed/stamina/power/guts/
        # wisdom), derived from which stat each command trains in master.mdb:
        # 101=speed, 105=stamina, 102=power, 103=guts, 106=wiz.
        base_to_facility = {101: 0, 105: 1, 102: 2, 103: 3, 106: 4}
        _command_to_facility = {
            row["command_id"]: base_to_facility[row["base_command_id"]]
            for row in rows
            if row["base_command_id"] in base_to_facility
        }
    return _command_to_facility.get(command_id)


# single_mode_training_effect.target_type -> our stat index (speed..wiz).
# 10 = energy/vital delta, 30 = skill points. Others (20, 101) are not stat
# gains for training and are ignored here.
_TARGET_TYPE_TO_STAT = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}
_TARGET_ENERGY = 10
_TARGET_SKILL_POINT = 30


def facility_stats(scenario_id: int, command_id: int) -> list:
    """The stat names a facility trains at all, ignoring caps and bonuses.

    Needed because a stat sitting at its hard cap gains 0 and is therefore
    OMITTED from params_inc_dec_info_array (see _build_training_command_info),
    which leaves nothing downstream able to say the stat was even involved --
    and "<stat> is in superb form" is exactly the case where the gain is 0.
    Read from single_mode_training_effect, so it follows master.mdb rather than
    a second hardcoded facility table."""
    stats, _sp, _energy = _master_facility_gains(scenario_id, command_id)
    if not stats:
        return []
    return [STAT_NAMES[i] for i, v in enumerate(stats) if v > 0]


def _master_facility_gains(scenario_id: int, command_id: int):
    """Current per-facility base gains straight from master.mdb
    (single_mode_training_effect) -- the authoritative, version-correct source
    (post URA/Unity rework), NOT the sim's frozen training_data.json. Returns
    (stat_gains[5], skill_point, energy_delta) for a normal success
    (result_state 2), or (None, 0, 0) if this scenario/command has no rows.

    scenario_id: 1=URA Finale, 2=Unity Cup, 4=... (as keyed in master data)."""
    def fetch(cid, sid):
        return master_data.query(
            "SELECT target_type, effect_value FROM single_mode_training_effect "
            "WHERE command_id=? AND scenario_id=? AND result_state=2 AND sub_id=1",
            (cid, sid),
        )

    rows = fetch(command_id, scenario_id)
    if not rows:  # try the base command id (e.g. summer 601 -> 101)
        base = master_data.query_one(
            "SELECT base_command_id FROM single_mode_training WHERE command_id=? LIMIT 1", (command_id,))
        base_cid = base["base_command_id"] if base else command_id
        rows = fetch(base_cid, scenario_id)
        if not rows and scenario_id != 1:  # last resort: URA's table
            rows = fetch(base_cid, 1)
    if not rows:
        return None, 0, 0

    stats = [0, 0, 0, 0, 0]
    sp = 0
    energy = 0
    for r in rows:
        tt, v = r["target_type"], r["effect_value"]
        if tt in _TARGET_TYPE_TO_STAT:
            stats[_TARGET_TYPE_TO_STAT[tt]] = v
        elif tt == _TARGET_SKILL_POINT:
            sp = v
        elif tt == _TARGET_ENERGY:
            energy = v
    return stats, sp, energy


def _card_bond(card: dict) -> int:
    effects = card.get("effects") or []
    max_level = effects[-1] if effects else {}
    return max_level.get("initial_friendship_gauge", 0)


def _card_effect(card: dict, key: str, default=0):
    effects = card.get("effects") or []
    max_level = effects[-1] if effects else {}
    return max_level.get(key, default)


NUM_TO_BONUS_KEY = {
    0: "speed_bonus", 1: "stamina_bonus", 2: "power_bonus",
    3: "guts_bonus", 4: "wisdom_bonus",
}

@functools.lru_cache(maxsize=512)
def _camp_command_for(base_command_id: int) -> int | None:
    """The summer-camp command (601-605) sharing this facility's base id: the
    level-5 row of single_mode_training that is not the base command itself."""
    row = master_data.query_one(
        "SELECT command_id FROM single_mode_training WHERE base_command_id=? "
        "AND command_level=5 AND command_id<>? LIMIT 1", (base_command_id, base_command_id))
    return row["command_id"] if row else None


@functools.lru_cache(maxsize=512)
def facility_gains(scenario_id: int, command_id: int, level: int = 1):
    """(stat_gains[5], skill_point, energy_delta) for a facility at `level`, or
    (None, 0, 0) if the scenario/command has no rows.

    A facility level adds a FIXED amount per stat, not a percentage. master.mdb
    carries only the two ends: level 1 is the base command (101-106) and level
    5 is the camp command (601-605), which is the level-5 facility. Levels 2-4
    are level 1 plus training_data.json's trainingLevelBoosts, e.g. speed
    +1/+2/+3/+4 speed, +0/+0/+1/+2 power, -1/-2/-4/-6 energy, SP unchanged.

    Checked 2026-10-05: that table reproduces the user's Trackblazer reference
    for every facility at every level, and level 1 + its level-5 row equals
    master's camp row in 19 of 20 (scenario, facility) pairs across scenarios
    1-4. The exception is URA guts (master: guts 8 -> 13, power 5 -> 5; the
    table says 12 and 6), so level 5 is read from master wherever it exists.
    URA guts levels 2-4 were then measured on the real JP server (alt careers,
    2026-10-11, empty facility, mood x growth back-solved; levels 1 and 5
    reproduce master): speed/power/guts 5/5/9, 5/5/10, 5/5/12, energy
    -23/-24/-26. The table was right at 2-3 and wrong at 4 (6/5/11):
    _URA_GUTS_LEVEL_GAINS. The old multiplier (x1.09 per
    level) also scaled SP, which never changes, and left energy at level 1's.

    A camp command id passed directly is already level 5; `level` is ignored."""
    fac = _facility_index_for(command_id)
    row = master_data.query_one(
        "SELECT base_command_id FROM single_mode_training WHERE command_id=? LIMIT 1",
        (command_id,))
    base_cid = row["base_command_id"] if row else command_id
    if command_id != base_cid:
        return _as_tuple(_master_facility_gains(scenario_id, command_id))
    stats, sp, energy = _master_facility_gains(scenario_id, base_cid)
    if stats is None or fac is None or level <= 1:
        return _as_tuple((stats, sp, energy))
    level = min(int(level), len(LEVEL_BOOSTS))
    camp = _camp_command_for(base_cid)
    if level == 5 and camp and _has_rows(scenario_id, camp):
        return _as_tuple(_master_facility_gains(scenario_id, camp))
    measured = _URA_GUTS_LEVEL_GAINS.get(level) if (scenario_id, base_cid) == (1, 103) else None
    if measured:
        return (measured[0], sp, energy + measured[1])
    boost = LEVEL_BOOSTS[level - 1][fac]
    return (tuple(stats[i] + boost[i] for i in range(5)), sp + boost[5], energy + boost[6])


# URA (scenario 1) guts facility, levels 2-4: ((speed, stamina, power, guts,
# wiz), energy change from level 1).
_URA_GUTS_LEVEL_GAINS = {2: ((5, 0, 5, 9, 0), -1), 3: ((5, 0, 5, 10, 0), -2),
                         4: ((5, 0, 5, 12, 0), -4)}


def _as_tuple(gains):
    """Immutable stats, since facility_gains' result is cached and shared."""
    stats, sp, energy = gains
    return (tuple(stats) if stats is not None else None, sp, energy)


def _has_rows(scenario_id: int, command_id: int) -> bool:
    return master_data.query_one(
        "SELECT 1 FROM single_mode_training_effect WHERE command_id=? AND scenario_id=? "
        "AND result_state=2 AND sub_id=1 LIMIT 1", (command_id, scenario_id)) is not None


def card_effect(support_card_id, key: str, default=0):
    """Public accessor: a support card's max-level effect value (0/default if
    the card or key is unknown). Used by the career handler for distribution
    (specialty_priority) and initial bond (initial_friendship_gauge)."""
    card = CARD_BY_ID.get(str(support_card_id))
    return _card_effect(card, key, default) if card else default


# support_card_effect_table.type -> what it does. Confirmed by the initial-stat
# block (9-13) already in use here and by the values matching cards.json's own
# keys where both exist. The ones cards.json OMITS are exactly the ones that
# were never applied (live-reported #28: 'pal cards energy reduction, and a lot
# more'): 17 hint level, 25/26 event effects, 27 failure-rate down, 28 energy
# cost down, 31 wit friendship recovery.
_RARITY_BASE_CAP = {1: 20, 2: 25, 3: 30}   # R/SR/SSR base cap (+5 per limit break)

EFFECT_FRIENDSHIP = 1
EFFECT_MOOD = 2
EFFECT_STAT_BONUS_BASE = 3    # 3..7 = speed/stamina/power/guts/wit's own
                              # per-training flat bonus, one type per stat --
                              # SAME quantity as cards.json's NUM_TO_BONUS_KEY.
                              # VERIFIED against real in-game text (master.mdb
                              # text_data category 155, keyed by support_card_
                              # id): id 20020 = "Speed Bonus and Initial Speed"
                              # for (type_0=3, type_1=9) -- proves 3 is the
                              # per-training "Speed Bonus" and 9 is the
                              # SEPARATE one-time "Initial Speed" (EFFECT_
                              # INITIAL_STAT_BASE below), not the same thing.
                              # An earlier version of this constant was 9,
                              # which added a one-time career-start bonus on
                              # EVERY training turn -- wrong on both counts.
EFFECT_TRAINING = 8
EFFECT_INITIAL_STAT_BASE = 9  # 9..13 = one-time career-start stat bonus, NOT
                              # applied in calculate_training_gain (that's a
                              # career-seed-time concern, not a per-turn one)
EFFECT_INITIAL_BOND = 14
EFFECT_RACE_BONUS = 15   # Race Bonus -- % bonus to the stat/SP gained from a
                        # race RESULT (not training). Decoded 2026-08-19 (see
                        # tools/extract_support_card_unique_effects.py's own
                        # module docstring for the text_data verification --
                        # 6 real cards' descriptions read "<other effect> and
                        # Race Bonus" with the other half matching an
                        # already-known type exactly). Never named here
                        # before despite being a standard 0-30 code (so it
                        # occurs on plain support_card_effect_table rows
                        # too, not just unique_effect): user-confirmed
                        # 2026-08-19 mechanic ("modifies the skill points and
                        # stats you earn from a race, the end event"). The
                        # BASE value (cards.json's own "race_bonus" key, deck-
                        # wide sum) was already wired into single_mode_team.
                        # py's _race_bonus_pct before this constant existed;
                        # what THIS constant adds is the UNIQUE-effect half
                        # (support_card_unique_effect rows using type 15,
                        # e.g. card 20003 +5% at level 25) that base-only sum
                        # was missing.
EFFECT_FAN_BONUS = 16    # Fan Bonus -- matches cards.json's max-level
                         # "fan_bonus" on every card checked.
EFFECT_HINT_LEVEL = 17
EFFECT_HINT_FREQ = 18
EFFECT_SPECIALTY_PRIORITY = 19   # Specialty Priority -- extra WEIGHT (not a
                                # percent) added to a card's own-type
                                # facility when a turn's training-partner
                                # placement is rolled (single_mode_team.py's
                                # _roll_distribution: base 100 per facility,
                                # 50 for 'away', card_effect's max-level
                                # "specialty_priority" already added to the
                                # card's own slot). Decoded 2026-08-19, same
                                # verification as EFFECT_RACE_BONUS above.
                                # User-confirmed 2026-08-19 mechanic: it's
                                # literally that same placement-weight term,
                                # and Grand Live's own "Specialty Rate Up"
                                # Live Bonus (_specialty_bonus) already rides
                                # the identical slot. What THIS constant adds
                                # is the UNIQUE-effect half (support_card_
                                # unique_effect rows using type 19, e.g.
                                # Kitasan Black SSR 30028 +20 at level 30)
                                # the base-only card_effect() call was
                                # missing.
EFFECT_EVENT_RECOVERY = 25
EFFECT_EVENT_EFFECT = 26
EFFECT_FAILURE_DOWN = 27
EFFECT_ENERGY_COST_DOWN = 28
EFFECT_SKILL_POINT = 30
EFFECT_WIT_RECOVERY = 31
EFFECT_FRIENDSHIP_ENERGY_DOWN = 113  # Light Hello (30052) -- see
                                     # support_card_unique_effect's "Character
                                     # Award" range (101-114): one bespoke
                                     # effect per specific character's pal
                                     # card, decoded from real text_data
                                     # (cat 150 name / 155 description, keyed
                                     # by support_card_id). See tools/extract_
                                     # support_card_unique_effect.py for the
                                     # full decoded catalogue (all 163 cards
                                     # that have ANY unique effect) --
                                     # data/training_ref/support_card_unique_
                                     # effects.json is the generated output.

# Decoded 2026-08-19 (see tools/extract_support_card_unique_effects.py's
# module docstring for the verification each one got). All three share the
# SAME real-data shape: value_0 = a threshold/scaling denominator, value_0_1
# = the training-effectiveness bonus % once the condition is met -- read via
# _unique_conditional_training_bonus below, NOT the generic unique_effect()
# (which only handles a SINGLE value column per type; these need both).
EFFECT_TRAINING_IF_NOT_PREFERRED = 102     # value_0 = friendship-gauge
                                           # threshold (80 in the one real
                                           # card, 30083); value_0_1 = bonus%.
                                           # Fires when this card is placed at
                                           # a facility that ISN'T its own
                                           # type (card_type_num != fac) at
                                           # bond >= threshold -- "when not on
                                           # preferred training" per its real
                                           # description.
EFFECT_TRAINING_IF_DECK_TYPE_COUNT = 103   # value_0 = distinct-card-type
                                           # threshold across the WHOLE 6-card
                                           # deck (verified against 2 real
                                           # cards, 5+/10% and 4+/15%);
                                           # value_0_1 = bonus%.
EFFECT_TRAINING_IF_FANS_GAINED = 104       # value_0 = fans per 1% (10,000 in
                                           # the one real card, 30086);
                                           # value_0_1 = the bonus CAP% (20).
                                           # Internally consistent: value_0 *
                                           # value_0_1 = 200,000, exactly the
                                           # card's own real description's
                                           # "up to 200,000 fans" cap -- not a
                                           # coincidence, this is the actual
                                           # formula: +1% per value_0 fans
                                           # gained this run, capped at
                                           # value_0_1%.

# Decoded 2026-08-19 against gametora.com's own per-card "Unique Effect"
# text (fetched directly, one card at a time -- see tools/extract_support_
# card_unique_effect.py's module docstring for which URL confirmed which).
# All five give training_effectiveness like 102/103/104 above, so they're
# ALSO read via _unique_conditional_training_bonus, just with their own
# formula branch each (the raw columns don't share one shape across all
# five the way 101's family did).
EFFECT_TRAINING_IF_MAX_ENERGY = 108   # gametora (Seeking the Pearl, 30095):
                                      # "Gain Training Effectiveness (5%);
                                      # gain additional 3% Training
                                      # Effectiveness for every 4 points of
                                      # maximum Energy above 100, up to
                                      # (20%) at 120". Raw [100,75,5,20] =
                                      # (threshold, rate*100, base%, cap%);
                                      # rate=75/100=0.75%/point (=3%/4pts).
EFFECT_TRAINING_IF_DECK_BOND_SUM = 109  # gametora (Ikuno Dictus, 30099 /
                                        # Tokai Teio SSR, 30111): "Gain
                                        # Training Effectiveness (1%) for
                                        # every 30 combined support bond, up
                                        # to (20%) at 600" -- 600 is just
                                        # the natural max (6 cards x 100
                                        # bond), not a stored value. Raw
                                        # [8,30] = (training_effectiveness,
                                        # bond-per-1%).
EFFECT_TRAINING_IF_CARDS_IN_FACILITY = 110  # gametora (El Condor Pasa,
                                            # 30102): "Training Effective-
                                            # ness (5) for every support
                                            # card in the same training
                                            # facility." Raw [8,5] =
                                            # (training_effectiveness,
                                            # per-card%).
EFFECT_TRAINING_IF_FACILITY_LEVEL = 111   # gametora (Maruzensky, 30107):
                                          # "Gain Training Effectiveness (5)
                                          # per every level of the current
                                          # training facility." Raw [8,5] =
                                          # (training_effectiveness, per-
                                          # level%).
EFFECT_TRAINING_IF_CURRENT_ENERGY = 114   # gametora (Mejiro Palmer, 30115):
                                          # "Gain Training Effectiveness
                                          # that scales with current Energy,
                                          # from (5%) at 0 Energy to (20%)
                                          # at 100+ Energy" -- linear. Raw
                                          # [8,5,20] = (training_
                                          # effectiveness, min%, max%).

EFFECT_FRIENDSHIP_STACKING = 106   # gametora (Sirius Symboli, 30091 / Twin
                                   # Turbo, 30112): "gains Friendship Bonus
                                   # (3) every time you do friendship
                                   # training with this card, up to 5 times
                                   # for a total of (15)." Raw [5,1,3] =
                                   # (max_stacks, sub_effect_type=friendship
                                   # _bonus, per_stack%). Needs a NEW per-
                                   # career stack counter (see
                                   # friendship_stacks param) -- unlike the
                                   # five above, this can't be derived
                                   # purely from THIS call's own inputs.

EFFECT_FAILURE_RATE_ZERO_CHANCE = 112   # gametora (Nakayama Festa, 30108):
                                        # "20% chance to make the current
                                        # training fail rate zero." Raw [20]
                                        # = proc chance%. A PROC, not a
                                        # gain multiplier -- calculate_
                                        # training_gain doesn't compute
                                        # failure rate at all, so this
                                        # isn't read here; see
                                        # training_failure_zero_proc()
                                        # below, called from single_mode_
                                        # team's _roll_training_failure.

EFFECT_INITIAL_STAT_DECK_COMPOSITION = 105   # gametora (Daitaku Helios,
                                             # 30116): "Gain Initial Stat Up
                                             # (10), where Stat is the type
                                             # of the card, for every card
                                             # in your support deck (Friend
                                             # and Group types give (2) to
                                             # every stat)". Raw [10,2] =
                                             # (per-matching-type-card
                                             # bonus, friend/group-bonus-to-
                                             # everything). A career-START
                                             # concern, wired via
                                             # deck_composition_initial_
                                             # stat_bonus() below and single_
                                             # mode_team.py's _apply_initial_
                                             # stats -- NOT calculate_
                                             # training_gain, which only
                                             # runs per-turn.

# Friendship Bonus that grows as current energy falls (Bamboo Memory SSR,
# 30094, "Make These Feelings Reach You!"). master.mdb row, both regions:
# [1, 10, 30, 15, 5] -- value_0 = 1 is the embedded sub-effect marker
# (Friendship Bonus, as in 106's [5,1,3]); value_0_4 = 5 is the floor (full
# energy), value_0_3 = 15 the ceiling, reached at value_0_2 = 30 energy or
# less. Linear between the two, the same shape 114 uses. value_0_1 = 10 is
# not accounted for (a step size would not divide the 5..15 span evenly).
EFFECT_FRIENDSHIP_IF_LOW_ENERGY = 107
# The BOND-GATED unique effect (JP: 30283, 30289, 30298, 30312, 30317):
# value_0 = the bond threshold (80), then two (sub-type, value) pairs in
# value_0_1/_2 and value_0_3/_4. 30283 reads "絆ゲージが80以上の時、パワー
# ボーナスとヒント獲得数アップ" -- (5, 1) power bonus, (33, 1) hint count.
EFFECT_IF_BOND = 101
# Hint count up: a '!' reveal pays this many EXTRA hint draws. Not in the
# client's SupportCardEffectType enum -- it only occurs as a 101 sub-effect.
# MEASURED (JP CarrotJuicer, 5,214 lone 20099 reveals): the three owned cards
# with it gave two skills in 949 of 1,248 reveals at bond >= 80 and never
# below; every other card never gave two.
EFFECT_HINT_COUNT = 33
# All Stats Bonus: +value to each of the five stat bonuses (3..7). Like 33 it
# only occurs as a 101 sub-effect (30161 / 30241: "全パラメータとスキルPt
# ボーナス" at bond 100).
EFFECT_ALL_STATS = 41
# Initial skill points (JP only, base table): added to the trainee's SP at
# career start, like 9-13 are to the stats.
EFFECT_INITIAL_SKILL_POINT = 32

# The unique types JP added after Global's 115. Column meanings are from
# GameTora's own renderer for them (value = value_0, value_N = value_0_N):
#   115 value = effect type (14, initial bond), value_1 = amount -- EVERY deck
#       card gets it, not just this one ("All support cards gain ...").
#   116 value = skill category (1 speed-up / 2 acceleration / 3 recovery),
#       value_1 = effect type, value_2 = per owned skill, value_3 = max skills.
#   117 value = effect type, value_2 = the max, reached at a combined facility
#       level of value_1 (25 = all five at 5); linear, so 5 levels -> 4%.
#   118 value = extra facilities (1 -> two at once), value_1 = min bond.
#   119 value = 50, value_2 = min bond: deck cards appear in training more.
#   120 value_1 = min bond, value_2 = per deck card, value_3 = max per stat:
#       +value_2 of each card's own stat bonus per deck card of that type;
#       friend/group cards count toward skill points.
#   121 value = bond bonus for every card's training, value_1 = the bonus
#       instead when training alongside this card.
#   122 value = effect type (19), value_1 = amount: the OTHER cards that
#       trained with this one get it next turn.
EFFECT_DECK_INITIAL_BOND = 115
EFFECT_PER_OWNED_SKILL = 116
EFFECT_FACILITY_LEVEL_SUM = 117
EFFECT_TWO_FACILITIES = 118
EFFECT_DECK_APPEAR_UP = 119
EFFECT_DECK_TYPE_STAT_BONUS = 120
EFFECT_TRAINING_BOND_UP = 121
EFFECT_SHARED_NEXT_TURN = 122
# 116's skill categories -> the skill_data ability_type that defines them
# (27 target speed, 31 acceleration, 9 HP recovery), self-targeted and positive.
_SKILL_CATEGORY_ABILITY = {1: 27, 2: 31, 3: 9}

_EFFECT_LEVEL_COLUMNS = [
    (0, "init"), (5, "limit_lv5"), (10, "limit_lv10"), (15, "limit_lv15"),
    (20, "limit_lv20"), (25, "limit_lv25"), (30, "limit_lv30"),
    (35, "limit_lv35"), (40, "limit_lv40"), (45, "limit_lv45"),
    (50, "limit_lv50"),
]


@master_data.context_cache(maxsize=4096)
def _effect_rows(effect_table_id: int) -> tuple:
    return tuple(dict(r) for r in master_data.query(
        "SELECT * FROM support_card_effect_table WHERE id=?", (effect_table_id,)))


@master_data.context_cache(maxsize=4096)
def _card_meta(support_card_id: int) -> tuple:
    row = master_data.query_one(
        "SELECT effect_table_id, rarity FROM support_card_data WHERE id=?",
        (support_card_id,))
    if row is None:
        return (None, 1)
    return (row["effect_table_id"], row["rarity"] or 1)


def master_effect(support_card_id, effect_type: int, level: int | None = None) -> float:
    """A card's value for ANY support_card_effect_table type at `level`
    (default: its max). Straight from master, so it covers the types
    cards.json omits entirely. Values are percentages; -1 columns mean
    'not defined at this level'.

    Between two defined levels the value is interpolated LINEARLY and
    floored; past the last defined level it holds. This used to take the last
    defined value at or below `level` (a step), which read low for every card
    below its top level where master leaves a gap -- e.g. 30312 at LB3 (level
    45) has friendship 25 at lv30 and 35 at lv50: the real JP server serves 32,
    the step served 25. Checked against 1,585 real JP previews (Beyond Dreams,
    home line): exact matches went 1,181 -> 1,518; the rest do not involve
    this (tools/preview_parity.py)."""
    table_id, rarity = _card_meta(support_card_id)
    if table_id is None:
        return 0.0
    if level is None:
        level = _RARITY_BASE_CAP.get(rarity, 30) + 20     # fully limit-broken
    for row in _effect_rows(table_id):
        if row.get("type") != effect_type:
            continue
        prev = None
        for lv, col in _EFFECT_LEVEL_COLUMNS:
            val = row.get(col)
            if val is None or val == -1:
                continue
            if lv == level:
                return float(val)
            if lv > level:
                if prev is None:
                    return 0.0
                lv0, val0 = prev
                return float(math.floor(val0 + (val - val0) * (level - lv0) / (lv - lv0)))
            prev = (lv, float(val))
        return prev[1] if prev else 0.0
    return 0.0


@master_data.context_cache(maxsize=4096)
def _unique_rows(support_card_id: int) -> tuple:
    return tuple(dict(r) for r in master_data.query(
        "SELECT lv, type_0, value_0, value_0_1, value_0_2, value_0_3, value_0_4, "
        "type_1, value_1, value_1_1, value_1_2, value_1_3, value_1_4 "
        "FROM support_card_unique_effect WHERE id=?", (support_card_id,)))


def unique_effect(support_card_id, effect_type: int, level: int | None = None,
                  bond: int | None = None) -> float:
    """A card's UNIQUE effect contribution for a type, once its unlock level is
    reached (support_card_unique_effect; live-reported #22 as never applied).

    Pass the card's `bond` to include its bond-gated (EFFECT_IF_BOND) half,
    which 187 JP and 26 Global cards carry and which nothing read before."""
    table_id, rarity = _card_meta(support_card_id)
    if level is None:
        level = _RARITY_BASE_CAP.get(rarity, 30) + 20
    total = 0.0
    for row in _unique_rows(support_card_id):
        if (row.get("lv") or 0) > level:
            continue
        if row.get("type_0") == effect_type:
            total += float(row.get("value_0") or 0)
        if row.get("type_1") == effect_type:
            total += float(row.get("value_1") or 0)
    if bond is not None:
        total += bond_gated_effect(support_card_id, effect_type, bond, level)
        if EFFECT_STAT_BONUS_BASE <= effect_type <= EFFECT_STAT_BONUS_BASE + 4:
            total += bond_gated_effect(support_card_id, EFFECT_ALL_STATS, bond, level)
    return total


def unique_params(support_card_id, effect_type: int, level: int | None = None) -> list:
    """[(value_0, value_0_1, ..., value_0_4)] for each unlocked unique slot of
    this type -- for the types whose columns are parameters, not one value."""
    table_id, rarity = _card_meta(support_card_id)
    if level is None:
        level = _RARITY_BASE_CAP.get(rarity, 30) + 20
    out = []
    for row in _unique_rows(support_card_id):
        if (row.get("lv") or 0) > level:
            continue
        for prefix, t in (("value_0", row.get("type_0")), ("value_1", row.get("type_1"))):
            if t == effect_type:
                out.append(tuple(int(row.get(k) or 0) for k in
                                 (prefix, f"{prefix}_1", f"{prefix}_2",
                                  f"{prefix}_3", f"{prefix}_4")))
    return out


@functools.lru_cache(maxsize=4096)
def skill_categories(skill_id) -> frozenset:
    """The 116 categories (_SKILL_CATEGORY_ABILITY) a skill counts toward."""
    row = master_data.query_one("SELECT * FROM skill_data WHERE id=?", (int(skill_id),))
    if row is None:
        return frozenset()
    row = dict(row)
    found = set()
    for i in (1, 2):
        for j in (1, 2, 3):
            ability = row.get(f"ability_type_{i}_{j}")
            if (ability and (row.get(f"float_ability_value_{i}_{j}") or 0) > 0
                    and row.get(f"target_type_{i}_{j}") == 1):
                found.update(c for c, a in _SKILL_CATEGORY_ABILITY.items() if a == ability)
    return frozenset(found)


def situational_unique(support_card_id, effect_type: int, level: int | None = None,
                       owned_skill_ids=(), facility_level_sum: int = 0) -> float:
    """The part of a card's unique effect that scales with the run rather than
    the card: 116 (owned skills of a category) and 117 (combined facility
    level)."""
    total = 0.0
    for category, etype, per, max_n, _ in unique_params(
            support_card_id, EFFECT_PER_OWNED_SKILL, level):
        if etype == effect_type and per:
            n = sum(1 for s in owned_skill_ids or () if category in skill_categories(s))
            total += per * min(n, max_n)
    for etype, full_at, max_v, _, _ in unique_params(
            support_card_id, EFFECT_FACILITY_LEVEL_SUM, level):
        if etype == effect_type and full_at:
            total += min(max_v, max_v * facility_level_sum / full_at)
    return total


def deck_type_stat_bonus(support_card_id, bond: int, deck_card_ids,
                         level: int | None = None) -> tuple:
    """120: (per-stat bonus list, skill-point bonus) this card adds to a
    training it is in, from the deck's composition, once its bond is met."""
    stats, sp = [0, 0, 0, 0, 0], 0
    for _, min_bond, per, max_v, _ in unique_params(
            support_card_id, EFFECT_DECK_TYPE_STAT_BONUS, level):
        if bond < min_bond:
            continue
        counts = [0] * 5
        pals = 0
        for sid in deck_card_ids or ():
            t = card_type_index(sid)
            if t is None:
                pals += 1
            else:
                counts[t] += 1
        for y in range(5):
            stats[y] += min(max_v, per * counts[y])
        sp += min(max_v, per * pals)
    return stats, sp


def bond_gated_effect(support_card_id, effect_type: int, bond: int,
                      level: int | None = None) -> float:
    """The value of `effect_type` inside this card's EFFECT_IF_BOND unique
    effect, or 0.0 while its bond is under the threshold (or it has none)."""
    table_id, rarity = _card_meta(support_card_id)
    if level is None:
        level = _RARITY_BASE_CAP.get(rarity, 30) + 20
    total = 0.0
    for row in _unique_rows(support_card_id):
        if (row.get("lv") or 0) > level:
            continue
        for prefix, t in (("value_0", row.get("type_0")), ("value_1", row.get("type_1"))):
            if t != EFFECT_IF_BOND or bond < (row.get(prefix) or 0):
                continue
            for sub, val in ((f"{prefix}_1", f"{prefix}_2"), (f"{prefix}_3", f"{prefix}_4")):
                if row.get(sub) == effect_type:
                    total += float(row.get(val) or 0)
    return total


def _deck_card_type_count(deck_card_ids) -> int:
    """Distinct card TYPES (speed/stamina/power/guts/wisdom/friend/group)
    across the full support deck -- for EFFECT_TRAINING_IF_DECK_TYPE_COUNT.
    Unlike CARD_TYPE_NAMES.index() elsewhere, this counts "friend"/"group"
    too (a card's real "type" for this purpose, per cards.json), since the
    real description just says "different card types", not "different stat
    types"."""
    types = set()
    for sid in deck_card_ids or ():
        card = CARD_BY_ID.get(str(sid))
        t = card.get("type") if card else None
        if t:
            types.add(t)
    return len(types)


def deck_composition_initial_stat_bonus(deck_card_ids, support_card_levels: dict | None) -> dict:
    """EFFECT_INITIAL_STAT_DECK_COMPOSITION (105) -- career-START only (see
    that constant's comment), called from single_mode_team.py's
    _apply_initial_stats, NOT calculate_training_gain. Fires once per deck
    card that HAS the effect unlocked (in practice 0 or 1 -- no real deck
    can hold two copies of the same support card), and when it does, grants
    a bonus for EVERY card in the deck (the granting card included): +10 to
    that card's own stat type, or +2 to every stat for Friend/Group cards.
    Returns {stat_name: total_bonus}."""
    ids = list(deck_card_ids or ())
    levels = support_card_levels or {}
    totals: dict[str, int] = {}
    granted = False
    for sid in ids:
        unique_lv = levels.get(sid)
        if not unique_lv:
            continue
        for row in _unique_rows(sid):
            if (row.get("lv") or 0) > unique_lv:
                continue
            for prefix, t in (("value_0", row.get("type_0")), ("value_1", row.get("type_1"))):
                if t != EFFECT_INITIAL_STAT_DECK_COMPOSITION:
                    continue
                per_match = row.get(prefix) or 0
                per_friend_group = row.get(f"{prefix}_1") or 0
                granted = True
                for deck_sid in ids:
                    card = CARD_BY_ID.get(str(deck_sid))
                    ctype = card.get("type") if card else None
                    if ctype in ("friend", "group"):
                        for stat in STAT_NAMES:
                            totals[stat] = totals.get(stat, 0) + per_friend_group
                    elif ctype in CARD_TYPE_NAMES:
                        stat = STAT_NAMES[CARD_TYPE_NAMES.index(ctype)]
                        totals[stat] = totals.get(stat, 0) + per_match
    if not granted:
        return {}
    return totals


def _unique_conditional_training_bonus(support_card_id, effect_type: int, level, *,
                                       deck_type_count: int = 0, total_fan: int = 0,
                                       not_preferred: bool = False, bond: int = 0,
                                       current_vital: int = 0, max_vital: int = 0,
                                       deck_bond_sum: int = 0,
                                       cards_in_facility: int = 0,
                                       facility_level: int = 0) -> float:
    """The training-effectiveness % contribution from ONE of the eight
    threshold/scaling-gated unique effects (102/103/104/108/109/110/111/114)
    for this card, at this training, or 0.0 if its condition isn't met (or
    the card doesn't have that effect at all). See the EFFECT_TRAINING_IF_*
    constants above for what each one's real formula (gametora-confirmed)
    is."""
    total = 0.0
    for row in _unique_rows(support_card_id):
        if (row.get("lv") or 0) > (level or 0):
            continue
        for prefix, t in (("value_0", row.get("type_0")), ("value_1", row.get("type_1"))):
            if t != effect_type:
                continue
            v0 = row.get(prefix) or 0
            v1 = row.get(f"{prefix}_1") or 0
            v2 = row.get(f"{prefix}_2") or 0
            v3 = row.get(f"{prefix}_3") or 0
            v4 = row.get(f"{prefix}_4") or 0
            if effect_type == EFFECT_TRAINING_IF_NOT_PREFERRED:
                if not_preferred and bond >= v0:
                    total += v1
            elif effect_type == EFFECT_TRAINING_IF_DECK_TYPE_COUNT:
                if deck_type_count >= v0:
                    total += v1
            elif effect_type == EFFECT_TRAINING_IF_FANS_GAINED:
                if v0:
                    total += min(v1, total_fan // v0)
            elif effect_type == EFFECT_TRAINING_IF_MAX_ENERGY:
                # v0 is an EMBEDDED target-effect-type marker (=8, training_
                # effectiveness -- confirmed live: 30095's row has value_0=8,
                # NOT a threshold), same convention type 101 uses for its own
                # sub-effect slots. The real params start at v1: threshold
                # (100), v2=rate*100 (75 -> 0.75%/pt), v3=base% (5), v4=cap%
                # (20) -- gametora: "5%; +3% per 4 pts above 100, up to 20%
                # at 120" (3%/4pts == 0.75%/pt, confirmed: 5+(120-100)*0.75
                # == 20).
                if max_vital > v1:
                    total += min(v4, v3 + (max_vital - v1) * (v2 / 100))
                elif max_vital:
                    total += v3
            elif effect_type == EFFECT_TRAINING_IF_DECK_BOND_SUM:
                # v0=embedded marker (8); v1=bond-per-1% (30) -- no separate
                # cap column; 20% is simply the natural ceiling (6 cards x
                # 100 bond max = 600 = 20x30).
                if v1:
                    total += deck_bond_sum // v1
            elif effect_type == EFFECT_TRAINING_IF_CARDS_IN_FACILITY:
                total += cards_in_facility * v1  # v0=embedded marker (8); v1=per-card%
            elif effect_type == EFFECT_TRAINING_IF_FACILITY_LEVEL:
                total += facility_level * v1     # v0=embedded marker (8); v1=per-level%
            elif effect_type == EFFECT_TRAINING_IF_CURRENT_ENERGY:
                # v0=embedded marker (8); v1=min%(5 at 0 energy), v2=max%(20
                # at 100+) -- linear.
                total += min(v2, v1 + (min(current_vital, 100) / 100) * (v2 - v1))
    return total


def _friendship_stack_bonus(support_card_id, level, stacks: int) -> float:
    """EFFECT_FRIENDSHIP_STACKING (106): +value_0_2 % per stack, up to
    value_0 stacks -- gametora-confirmed "+3% per friendship-training
    trigger, up to 5 stacks (15% total)". `stacks` is the CALLER's own
    running count for this card this career (see calculate_training_gain's
    friendship_stacks param) -- this function has no state of its own."""
    for row in _unique_rows(support_card_id):
        if (row.get("lv") or 0) > (level or 0):
            continue
        for prefix, t in (("value_0", row.get("type_0")), ("value_1", row.get("type_1"))):
            if t != EFFECT_FRIENDSHIP_STACKING:
                continue
            max_stacks = row.get(prefix) or 0
            per_stack = row.get(f"{prefix}_2") or 0
            return min(stacks, max_stacks) * per_stack
    return 0.0


def _low_energy_friendship_bonus(support_card_id, level, current_vital: int) -> float:
    """EFFECT_FRIENDSHIP_IF_LOW_ENERGY (107): value_0_4 % Friendship Bonus at
    100 energy, rising linearly to value_0_3 % at value_0_2 energy or below
    (5% -> 15% at <= 30 for 30094; see the constant's comment)."""
    for row in _unique_rows(support_card_id):
        if (row.get("lv") or 0) > (level or 0):
            continue
        for prefix, t in (("value_0", row.get("type_0")), ("value_1", row.get("type_1"))):
            if t != EFFECT_FRIENDSHIP_IF_LOW_ENERGY:
                continue
            low_vital = row.get(f"{prefix}_2") or 0
            ceiling = row.get(f"{prefix}_3") or 0
            floor = row.get(f"{prefix}_4") or 0
            vital = min(max(current_vital or 0, low_vital), 100)
            if low_vital >= 100:
                return float(ceiling)
            return floor + (100 - vital) / (100 - low_vital) * (ceiling - floor)
    return 0.0


def training_failure_zero_proc(in_facility_card_ids, support_card_levels: dict | None) -> bool:
    """EFFECT_FAILURE_RATE_ZERO_CHANCE (112): value_0 % independent chance,
    PER unlocked card actually placed in the trained facility this turn, to
    zero out this training's fail rate -- gametora-confirmed "20% chance to
    make the current training fail rate zero" (Nakayama Festa, 30108). Scoped
    to in-facility cards only, matching every other unique effect's own-card
    gating (108-111 etc.) rather than deck-wide type 27's failure_rate()
    styling. Caller rolls this BEFORE the normal failure_rate() roll and
    skips it entirely on a proc."""
    levels = support_card_levels or {}
    for sid in in_facility_card_ids or ():
        unique_lv = levels.get(sid)
        if not unique_lv:
            continue
        for row in _unique_rows(sid):
            if (row.get("lv") or 0) > unique_lv:
                continue
            for t, v in ((row.get("type_0"), row.get("value_0")),
                        (row.get("type_1"), row.get("value_1"))):
                if t == EFFECT_FAILURE_RATE_ZERO_CHANCE and v and random.random() * 100 < v:
                    return True
    return False


def friendship_energy_down(support_card_id, level) -> float:
    """Unique effect 113 (Light Hello): ENERGY COST DOWN when a friendship
    training occurs in her facility. value_0 names the granted effect (28), value_0_1 is the amount."""
    total = 0.0
    for row in _unique_rows(support_card_id):
        if (row.get("lv") or 0) > (level or 0):
            continue
        for prefix in ("value_0", "value_1"):
            t = row.get("type_0" if prefix == "value_0" else "type_1")
            if t == EFFECT_FRIENDSHIP_ENERGY_DOWN and row.get(prefix) == EFFECT_ENERGY_COST_DOWN:
                total += float(row.get(f"{prefix}_1") or 0)
    return total


def deck_effect_total(support_card_ids, effect_type: int) -> float:
    """Summed base + unique value of an effect type across a deck."""
    return sum(master_effect(sid, effect_type) + unique_effect(sid, effect_type)
               for sid in support_card_ids or ())


def card_level(support_card_id, exp: int = 0, limit_break_count=None) -> int:
    """A support card's level as this region's game has it. Global levels
    cards with exp (support_card_level). JP has no leveling: a card's level
    is its limit break's cap (SSR 30/35/40/45/50), whatever exp says."""
    from . import region
    if region.CURRENT_REGION.get() == "jp":
        return level_cap_for(support_card_id, limit_break_count)
    return support_card_level_from_exp(support_card_id, exp or 0)


def level_cap_for(support_card_id, limit_break_count) -> int:
    """The highest level a card can reach at this limit break: R/SR/SSR 20/25/
    30, +5 per break. A missing count is read as fully broken."""
    _table_id, rarity = _card_meta(support_card_id)
    lb = 4 if limit_break_count is None else int(limit_break_count)
    return _RARITY_BASE_CAP.get(rarity, 30) + 5 * max(0, min(4, lb))


@master_data.context_cache(maxsize=512)
def support_card_level_from_exp(support_card_id, exp: int) -> int:
    """A support card's real persistent level for `exp` (support_card_level,
    keyed by the card's rarity) -- the highest level whose total_exp <= exp.
    NEEDED separately from cards.json/_card_effect (which always reads the
    fully-maxed LAST tier regardless of the card's actual level or limit
    break -- a pre-existing simplification, not something this touches) --
    but support_card_unique_effect.lv is a REAL unlock gate: a card below it
    must not get the bonus yet. Mirrors cards.py's _support_level_cap (the
    forward level->exp direction) in reverse."""
    row = master_data.query_one(
        "SELECT rarity FROM support_card_data WHERE id=?", (support_card_id,))
    if row is None:
        return 1
    best = master_data.query_one(
        "SELECT MAX(level) AS lv FROM support_card_level WHERE rarity=? AND total_exp<=?",
        (row["rarity"], exp))
    return (best["lv"] if best and best["lv"] is not None else 1)


def _facility_base_failure(command_id, facility_level: int = 1) -> int:
    """single_mode_training.failure_rate for a facility+level (the per-facility
    base -- speed ~520, wiz ~320, and it creeps up slightly with level)."""
    row = master_data.query_one(
        "SELECT failure_rate FROM single_mode_training WHERE command_id=? AND command_level=?",
        (command_id, facility_level))
    return row["failure_rate"] if row else 520


def failure_rate(vital: int, command_id=None, facility_level: int = 1,
                 conditions=None, deck=(), extra_down_pct: int = 0,
                 facility_cards=None) -> int:
    """Displayed training failure % (0-99) at this vital.

    CORRECTED 2026-09-30 against 10,285 real JP failure rates (every facility,
    normal, camp and Design Your Island's island versions; URA, Beyond Dreams,
    Design Your Island), from 89% to 99.8% exact:
      * failure-rate down (type 27) counts only the cards STANDING IN the
        facility, each at its own level -- `facility_cards` [(id, level)].
        The whole-deck, max-level `deck` reading is kept for callers that
        have no facility (it read low on 1 in 9 real previews);
      * the ceil is taken on the value rounded to 9 places: at 50 energy
        power's (100-50)(51.6-50)/40 is 2.0000000000000018 in floats and
        ceil'd to 3, the real server shows 2;
      * Practice Perfect ◎ (11) is -4, ○ (10) -2; the total caps at 99
        (Practice Poor's +2 on a 99 still shows 99).

    Replaced 2026-08-23 with the actual client formula (recovered from a
    decompiled build, `Game::calculateFailureRate`) after the previous
    facility-aware sigmoid -- despite being independently re-fit against 625
    real (vital, failure_rate) observations and reaching R^2 .97-.99 -- was
    still an *approximation*. This is not: `x0 = 0.1*base` (base = this
    facility+level's single_mode_training.failure_rate) then
    `f = (100-vital)*(x0-vital)/40` for vital<x0 else 0, clamped to [0,99],
    scaled by the deck's failure-rate-down multiplier, ceil'd to an int, then
    the Practice Poor/Perfect bias is added as a flat +-2 (NOT a curve-shift
    the way the old model treated it). Verified against all 625 observations
    (level-1 subset, no Practice Poor/Perfect active in any of them): 120/120
    speed and 123/123 stamina exact integer matches; power 61/65, guts
    119/125, wiz 44/45 -- every remaining mismatch is the real rate coming in
    *lower* than this formula predicts, never higher, consistent with an
    unaccounted-for support-card failure-rate-down deck bonus on those
    specific captures rather than a formula error."""
    base = _facility_base_failure(command_id, facility_level) if command_id else 520
    x0 = 0.1 * base
    f = (100 - vital) * (x0 - vital) / 40.0 if vital < x0 else 0.0
    f = max(0.0, min(99.0, f))
    if facility_cards is not None:
        down = sum(max(0.0, master_effect(sid, EFFECT_FAILURE_DOWN, level))
                   for sid, level in facility_cards if sid)
        f *= max(0.0, 1 - down / 100)
    elif deck:
        # Deck FAILURE-RATE DOWN (effect type 27) -- never applied before
        # because cards.json has no key for it (live-reported #28). Tazuna's
        # SSR alone is -30%, which is the whole point of running her.
        f *= max(0.0, 1 - deck_effect_total(deck, EFFECT_FAILURE_DOWN) / 100)
    # A scenario's failure-down (Onsen's bath buff, -20%) multiplies in before
    # the ceil: ceil(f x 0.8) matches 88% of Onsen's buffed previews, the same
    # as the unbuffed formula; ceil-then-scale matched 46%.
    if extra_down_pct:
        f = round(f * max(0.0, 1 - extra_down_pct / 100), 9)
    fr = math.ceil(round(f, 9))
    conds = conditions or ()
    if 6 in conds:                       # Practice Poor -> flat +2
        fr += 2
    if 11 in conds:                      # Practice Perfect ◎ -> flat -4
        fr -= 4
    elif 10 in conds:                    # Practice Perfect ○ -> flat -2
        fr -= 2
    fr = max(0, min(99, fr))
    override = forced_failure_rate()
    return fr if override is None else override


def forced_failure_rate():
    """TESTING KNOB -- `force_failure_rate` in client_config.json.

    Pins the training failure rate to a fixed percent, both DISPLAYED and
    ROLLED, so failure/infirmary flows can be exercised on demand. Set it to
    100 to make every training fail, 0 to make none fail. Null (the default)
    means the real formula decides, which is the only setting that should ever
    be committed.

    Read through app.config, so it re-reads on file change with no server
    restart -- flip it back by setting it to null."""
    value = config.get("force_failure_rate")
    if value is None:
        return None
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        log.warning("client_config.json force_failure_rate is not an integer: %r",
                    value)
        return None


def training_energy(base_delta: int, command_id, in_facility_cards=(),
                    levels: dict | None = None) -> int:
    """The energy a training actually costs (or gives), from master's facility
    delta plus the effects of the cards PRESENT in that facility.

    Two effects fed in here, both previously read-only:
      * type 28 ENERGY COST DOWN -- the pal cards' signature (Tazuna -25%).
        `energy_cost` existed but nothing called it, so the training screen
        showed master's raw cost and a pal deck saved the player nothing.
      * type 31 WIT FRIENDSHIP RECOVERY (44 cards, +2..+5) -- wit training is
        the one facility that GIVES energy (master: command 106 is +5), and
        these cards add to that recovery -- but, per the name, only for a
        card whose OWN friendship (rainbow) training actually triggers this
        turn: a wisdom-type card at bond >= 80 (the same is_friendship test
        calculate_training_gain uses). A non-wisdom card sitting in the wit
        facility, or a wisdom card below 80 bond, gives nothing (user-
        reported 2026-09-03: was previously granted to every card merely
        present in the facility)."""
    entries = [(c, bond) for c, bond, *_ in in_facility_cards or () if c]
    if base_delta < 0:
        cost = energy_cost(base_delta, deck=[c for c, _ in entries], bonds=dict(entries),
                           levels=levels)
        # TESTING KNOB -- energy_cost_multiplier (client_config.json / admin
        # panel Career tuning); 0 makes training free.
        mult = config.get_float("energy_cost_multiplier")
        return cost if mult is None else min(0, int(round(cost * max(0.0, mult))))
    if _facility_index_for(command_id) == 4:      # wisdom
        return base_delta + int(round(sum(
            master_effect(c, EFFECT_WIT_RECOVERY)
            + bond_gated_effect(c, EFFECT_WIT_RECOVERY, bond) for c, bond in entries
            if bond >= 80 and (CARD_BY_ID.get(str(c)) or {}).get("type") == "wisdom")))
    return base_delta


def energy_cost(base_cost: int, deck=(), bonds: dict | None = None,
                levels: dict | None = None) -> int:
    """Training energy cost after the deck's ENERGY COST DOWN (type 28) --
    the pal cards' signature effect (Tazuna -25%), previously ignored. `bonds`
    ({support_card_id: bond}) adds the bond-gated half (30276: -5% at 60).

    At the card's REAL level when `levels` has it (it used max level: a
    level-30 Light Hello took 10% where the real server takes 5%), and the
    magnitude is FLOORED: real Ramen previews 20 -> 19, 21 -> 19, 22 -> 20,
    26 -> 24, 27 -> 25 at 5% (sweep 2026-10-11, preview_parity)."""
    if not deck or base_cost >= 0:
        return base_cost
    levels = levels or {}
    down = sum(master_effect(sid, EFFECT_ENERGY_COST_DOWN, levels.get(sid))
               + unique_effect(sid, EFFECT_ENERGY_COST_DOWN, level=levels.get(sid))
               for sid in deck)
    down += sum(bond_gated_effect(c, EFFECT_ENERGY_COST_DOWN, b)
                for c, b in (bonds or {}).items())
    factor = max(0.0, 1 - down / 100)
    return -math.floor(abs(base_cost) * factor + 1e-9)


def card_type_index(support_card_id):
    """A support card's facility type index (0 speed .. 4 wisdom), or None for
    friend/group/unknown cards (which don't have a training specialty)."""
    card = CARD_BY_ID.get(str(support_card_id))
    if not card or card.get("type") not in CARD_TYPE_NAMES:
        return None
    return CARD_TYPE_NAMES.index(card["type"])


# Support-card "initial stat" effects (初期スピード/…/初期賢さ): a flat stat bump
# granted at career start. Read straight from master.mdb (support_card_effect_table
# type 9-13) -- the authoritative source; cards.json omits/mislabels initial_wiz.
_INITIAL_STAT_TYPES = {9: "speed", 10: "stamina", 11: "power", 12: "guts", 13: "wiz"}
_RARITY_BASE_CAP = {1: 20, 2: 25, 3: 30}   # R/SR/SSR base level cap (+5 per limit break)
_EFFECT_LEVEL_COLS = [
    ("init", 1), ("limit_lv5", 5), ("limit_lv10", 10), ("limit_lv15", 15),
    ("limit_lv20", 20), ("limit_lv25", 25), ("limit_lv30", 30), ("limit_lv35", 35),
    ("limit_lv40", 40), ("limit_lv45", 45), ("limit_lv50", 50),
]


def initial_stat_bonuses(support_card_id, limit_break_count: int = 4) -> dict:
    """The flat starting-stat bonuses a support card grants at career start, as
    {stat: amount} for whichever of speed/stamina/power/guts/wiz it boosts. Reads
    support_card_effect_table (types 9-13) at the card's level for its rarity +
    limit break: the effect value is the last non-(-1) breakpoint at or below that
    level (the columns step up at limit-break milestones)."""
    rows = master_data.query(
        "SELECT rarity, effect_table_id FROM support_card_data WHERE id = ?",
        (support_card_id,))
    if not rows:
        return {}
    rarity = rows[0]["rarity"]
    etid = rows[0]["effect_table_id"]
    level = _RARITY_BASE_CAP.get(rarity, 30) + 5 * max(0, min(4, limit_break_count or 0))
    out: dict[str, int] = {}
    for eff in master_data.query(
            "SELECT * FROM support_card_effect_table WHERE id = ? AND type IN (9,10,11,12,13)",
            (etid,)):
        stat = _INITIAL_STAT_TYPES.get(eff["type"])
        if stat is None:
            continue
        val = 0
        for col, bp in _EFFECT_LEVEL_COLS:
            if bp > level:
                break
            v = eff[col]
            if v is not None and v != -1:
                val = v
        if val:
            out[stat] = val
    return out


def _pure_passion_friendship(support_card_id, pure_passion_cards=()) -> bool:
    """Whether a GROUP card triggers friendship training in the facility it is
    standing in right now.

    THE CONDITION IS THE WHOLE TEST -- neither the facility-type match (a group
    card has no type and could never satisfy it) nor the bond threshold applies.
    "Able to do Friendship Training with <group>" means exactly that: bond 30
    with Pure Passion up rainbows, bond 90 without it does not (user-specified
    2026-09-08)."""
    return bool(pure_passion_cards) and support_card_id in pure_passion_cards


def friendship_multiplier(in_facility_cards: list[tuple[int, int]], command_id: int,
                          scenario_friendship_bonus: int = 0,
                          pure_passion_cards=()) -> float:
    """The SAME friendship (rainbow) multiplier calculate_training_gain applies
    internally, exposed standalone so a caller that only needs this number (the
    Extra Stat Gain badge preview, which must show song_bonus x this exact
    value to match what training actually applies) never has to duplicate the
    card-type/bond-threshold logic and risk drifting from it. See
    calculate_training_gain's extra_stat_bonus docstring for why this matters:
    the badge under-reported the real gain when it just showed the raw bonus,
    unscaled, while the actual training already multiplied it (user-reported
    2026-08-16, right after the raw-bonus badge fix landed)."""
    fac = _facility_index_for(command_id)
    if fac is None:
        return 1.0
    final_friendship_bonus = 1.0
    any_friendship = False
    for sid, bond in in_facility_cards:
        card = CARD_BY_ID.get(str(sid))
        if card is None:
            continue
        if card.get("type") in ("friend", "group"):
            if _pure_passion_friendship(sid, pure_passion_cards):
                final_friendship_bonus *= 1 + (_card_effect(card, "friendship_bonus") / 100)
                any_friendship = True
            continue
        card_type_num = CARD_TYPE_NAMES.index(card["type"]) if card.get("type") in CARD_TYPE_NAMES else -1
        if card_type_num == fac and bond >= 80:
            final_friendship_bonus *= 1 + (_card_effect(card, "friendship_bonus") / 100)
            any_friendship = True
    if any_friendship and scenario_friendship_bonus:
        final_friendship_bonus *= 1 + (int(scenario_friendship_bonus) / 100)
    return final_friendship_bonus


def calculate_training_gain(
    *,
    card_id: int,
    in_facility_cards: list[tuple[int, int]],
    command_id: int,
    scenario_id: int,
    facility_level: int,
    motivation: int,
    current_stats: dict[str, int],
    max_stats: dict[str, int],
    extra_stat_bonus: dict | None = None,
    scenario_friendship_bonus: int = 0,
    support_card_levels: dict[int, int] | None = None,
    deck_card_ids: list[int] | None = None,
    total_fan: int = 0,
    current_vital: int = 0,
    max_vital: int = 0,
    deck_bond_sum: int = 0,
    friendship_stacks: dict[int, int] | None = None,
    pure_passion_cards=(),
    npc_supporter_count: int = 0,
    owned_skill_ids=(),
    facility_level_sum: int = 0,
) -> dict | None:
    """Returns {stat_name: gain, ..., 'skill_point', 'energy_cost'}, or None if
    command_id isn't a recognized training facility (e.g. it's a rest/outing/
    race command, which callers handle separately).

    in_facility_cards: (support_card_id, bond) for the cards ACTUALLY placed in
    this facility this turn -- the caller owns per-turn distribution + live bond
    state (see single_mode_team). A card at bond >= 80 in its own-type facility
    triggers friendship (rainbow) training. Base gains come from master.mdb for
    the scenario; mood/support/friendship/growth multipliers and the 1200 soft-
    cap + hard stat cap are applied on top. facility_level picks the base row
    (see facility_gains): fixed per-level stat, SP and energy values.

    npc_supporter_count: Grand Live scenario supporters recruited via a Live
    ("<name> joined your cause!") who are NOT also equipped as a real support
    card -- they appear as ordinary NPC training partners (user-confirmed
    2026-08-24), same as the Director/Reporter/Meek, but own no card of their
    own to carry any of a support card's OTHER effects (bond, friendship
    training, hints, ...).

    They count as BODIES, and only as bodies -- the two parameters whose
    real-game definition is a head count of who is standing in the facility:

      * final_char_count, the +5% per person in the facility (user-directed
        2026-08-28: a recruited uma standing in a facility is worth the same
        +5% as a support card standing there -- she used to be left out of
        it entirely, so a facility holding three of them previewed exactly
        the same gain as an empty one);
      * EFFECT_TRAINING_IF_CARDS_IN_FACILITY, the "+N% per card in this
        facility" unique effect some cards have.

    Every other per-card term (bond, friendship/rainbow, hints, stat/SP
    bonuses, mood, specialty priority, failure rate) stays untouched: those
    are properties of a CARD, and these supporters own none.

    The caller owns the 5-per-facility cap, so it never passes a count that
    would push count + npc_supporter_count past 5 (see single_mode_team
    ._npc_supporter_placements).

    support_card_levels: {support_card_id: real persistent level}, from the
    OWNED card's exp (support_card_level_from_exp) -- NOT the in-career bond
    in in_facility_cards. Needed because cards.json's mood/training/friendship/
    stat/SP values are the card's BASE support_card_effect_table numbers only;
    support_card_unique_effect (an SSR/special-card bonus gated by real card
    level, e.g. Hishi Amazon SR +10% friendship at level 25) is a SEPARATE,
    ADDITIVE table cards.json never included -- confirmed by comparing
    cards.json's own max-tier value against master_effect() alone (exact
    match) vs deck_effect_total() (master+unique, which cards.json does NOT
    match). Omitted (None) or missing a card here just skips that card's
    unique bonus -- same as if it hadn't unlocked yet, never an error.

    extra_stat_bonus: {stat_name: +N} of SCENARIO-granted flat bonuses -- today
    only Grand Live's "Extra Stat Gain" songs (トレーニングの◯上昇量+N).
    User-confirmed 2026-08-16: unlike a support card's own flat stat bonus
    (which joins `stat_bonus` and gets the FULL multiplier stack), a song's
    bonus scales with friendship ONLY -- (base + support_bonus) x full stack,
    PLUS song_bonus x friendship_only, summed before the single floor. Kept
    as a separate term (song_stat_bonus/song_sp_bonus below) rather than
    merged into stat_bonus/sp_bonus for exactly this reason. Empty/None for
    every other scenario, so URA is unaffected.

    scenario_friendship_bonus: a PERCENT applied to the friendship product, and
    only when friendship (rainbow) training actually triggered -- today that is
    Grand Live's Live Bonus. 0 for every other scenario.

    Placement note: the guide flags this as an open question -- the bonus could
    be (a) one multiplier on the whole friendship product, or (b) added to each
    card's own friendship bonus before multiplying. With two rainbow cards at
    35% those differ by ~33% (3.01 vs 4.00), so it matters. (a) is implemented,
    following the naming evidence the guide leans on: kamigame renders the live
    bonus as "friendship training GAIN AMOUNT up" (a multiplier on the result),
    whereas the support-card effect is plainly "friendship bonus". That is
    philology, not data -- settle it against a capture of a run that has one."""
    fac = _facility_index_for(command_id)
    if fac is None:
        return None

    base_stats, base_sp, energy_delta = facility_gains(scenario_id, command_id, facility_level or 1)
    if base_stats is None:
        return None

    growth = trainee_growth_rates(card_id)

    total_mood_effect = 0
    total_training_effect = 0
    final_friendship_bonus = 1.0
    any_friendship = False
    stat_bonus = [0, 0, 0, 0, 0]
    count = 0
    sp_bonus = 0
    friendship_energy_down_pct = 0.0
    deck_type_count = _deck_card_type_count(deck_card_ids)

    for sid, bond in in_facility_cards:
        card = CARD_BY_ID.get(str(sid))
        if card is None:
            continue
        # A FRIEND/GROUP CARD IS STILL A SUPPORT CARD IN THIS FACILITY. It used
        # to be skipped outright here, which silently threw away every effect
        # it owns -- Tazuna's +10 training effectiveness, Special Week's group
        # +20 mood, Rudolf's group +5 training and +1 speed, their skill-point
        # bonuses, and their body in the card-count bonus. The ONE thing that
        # is genuinely different is friendship training: they have no type to
        # match a facility with, so it takes a group's Pure Passion instead of
        # the ordinary type+bond test (user-reported 2026-09-08).
        pal = card.get("type") in ("friend", "group")
        card_type_num = CARD_TYPE_NAMES.index(card["type"]) if card.get("type") in CARD_TYPE_NAMES else -1
        unique_lv = (support_card_levels or {}).get(sid)
        # Bond-gated (101) and run-scaled (116/117) halves included -- see
        # unique_effect / situational_unique.
        unique = ((lambda t: unique_effect(sid, t, level=unique_lv, bond=bond)
                   + situational_unique(sid, t, unique_lv, owned_skill_ids,
                                        facility_level_sum))
                  if unique_lv else (lambda t: 0.0))

        total_mood_effect += _card_effect(card, "mood_effect") + unique(EFFECT_MOOD)
        total_training_effect += _card_effect(card, "training_bonus") + unique(EFFECT_TRAINING)
        if unique_lv:
            # Eight threshold/scaling-gated training-effectiveness effects,
            # decoded 2026-08-19 (102/103/104 against internal master.mdb
            # consistency, 108/109/110/111/114 against gametora.com's own
            # per-card text directly) -- see the EFFECT_TRAINING_IF_*
            # constants above for what each one means. 110 (cards-in-
            # facility) is applied in a second pass below, once `count` is
            # final -- every other one only needs THIS card's own inputs.
            total_training_effect += _unique_conditional_training_bonus(
                sid, EFFECT_TRAINING_IF_NOT_PREFERRED, unique_lv,
                not_preferred=(card_type_num != fac), bond=bond)
            total_training_effect += _unique_conditional_training_bonus(
                sid, EFFECT_TRAINING_IF_DECK_TYPE_COUNT, unique_lv,
                deck_type_count=deck_type_count)
            total_training_effect += _unique_conditional_training_bonus(
                sid, EFFECT_TRAINING_IF_FANS_GAINED, unique_lv, total_fan=total_fan)
            total_training_effect += _unique_conditional_training_bonus(
                sid, EFFECT_TRAINING_IF_MAX_ENERGY, unique_lv, max_vital=max_vital)
            total_training_effect += _unique_conditional_training_bonus(
                sid, EFFECT_TRAINING_IF_DECK_BOND_SUM, unique_lv, deck_bond_sum=deck_bond_sum)
            total_training_effect += _unique_conditional_training_bonus(
                sid, EFFECT_TRAINING_IF_FACILITY_LEVEL, unique_lv, facility_level=facility_level)
            total_training_effect += _unique_conditional_training_bonus(
                sid, EFFECT_TRAINING_IF_CURRENT_ENERGY, unique_lv, current_vital=current_vital)

        # type 113 (Light Hello, 30052): "Training Energy Cost Reduction when
        # Friendship Training occurs" -- row (113, value_0 = granted effect 28,
        # value_0_1 = amount 30). It fires when ANY card's friendship training
        # triggers in the facility she is in (a pal never rainbows herself):
        # real Ramen previews show the 30% cut in exactly the 9 facilities
        # with another rainbow card and never without one, even at her bond
        # >= 80 (27 cases); 22 -> 14 = floor(22 x 0.95 x 0.70) (sweep
        # 2026-10-11). Applied below only if any_friendship.
        if unique_lv:
            friendship_energy_down_pct += friendship_energy_down(sid, unique_lv)

        is_friendship = (_pure_passion_friendship(sid, pure_passion_cards) if pal
                         else (card_type_num == fac and bond >= 80))
        if is_friendship:
            # a unique friendship bonus multiplies the base one (DYI 20062: 1.2 × 1.1 = 1.32)
            friendship_pct = ((1 + _card_effect(card, "friendship_bonus") / 100)
                              * (1 + unique(EFFECT_FRIENDSHIP) / 100) - 1) * 100
            if unique_lv and friendship_stacks:
                # 106 (gametora-confirmed, see EFFECT_FRIENDSHIP_STACKING):
                # +3% per PAST friendship-training trigger with this card,
                # up to 5 stacks. `friendship_stacks` is the caller's own
                # running count BEFORE this training (single_mode_team.py
                # owns incrementing it once this training actually commits)
                # -- reading it here only APPLIES the bonus, never advances it.
                friendship_pct += _friendship_stack_bonus(
                    sid, unique_lv, friendship_stacks.get(sid, 0))
            if unique_lv:
                friendship_pct += _low_energy_friendship_bonus(sid, unique_lv, current_vital)
            final_friendship_bonus *= 1 + (friendship_pct / 100)
            any_friendship = True

        for y in range(5):
            if base_stats[y] != 0:
                # cards.json's extraction is missing "wisdom_bonus" on every
                # card (531/531, 2026-08-28 audit) -- speed/stamina/power/guts
                # bonuses ARE present there, so only wisdom needs the
                # straight-from-master fallback (same table `unique()` above
                # already reads, just the base tier instead of the unique one).
                base_bonus = (master_effect(sid, EFFECT_STAT_BONUS_BASE + 4) if y == 4
                             else _card_effect(card, NUM_TO_BONUS_KEY[y]))
                stat_bonus[y] += base_bonus + unique(EFFECT_STAT_BONUS_BASE + y)
        if unique_lv:
            deck_stats, deck_sp = deck_type_stat_bonus(sid, bond, deck_card_ids, unique_lv)
            for y in range(5):
                if base_stats[y] != 0:
                    stat_bonus[y] += deck_stats[y]
            sp_bonus += deck_sp
        count += 1
        sp_bonus += _card_effect(card, "skill_point_bonus") + unique(EFFECT_SKILL_POINT)

    # 110 (EFFECT_TRAINING_IF_CARDS_IN_FACILITY) needs the FINAL card count
    # for this facility, which isn't known until the loop above finishes --
    # a second, cheap pass over the same (already small) list.
    if support_card_levels:
        for sid, _bond in in_facility_cards:
            unique_lv = support_card_levels.get(sid)
            if unique_lv:
                total_training_effect += _unique_conditional_training_bonus(
                    sid, EFFECT_TRAINING_IF_CARDS_IN_FACILITY, unique_lv,
                    cards_in_facility=count + npc_supporter_count)

    # Kept OUT of stat_bonus/sp_bonus on purpose (user-confirmed 2026-08-16):
    # a song's Extra Stat Gain bonus scales with friendship ONLY, not with
    # mood/training_effect/char_count/growth the way a support card's own
    # flat bonus does -- it needs its own multiplier term below rather than
    # joining the support-card total that gets the full stack.
    song_stat_bonus = [int((extra_stat_bonus or {}).get(stat_name, 0) or 0)
                       for stat_name in STAT_NAMES]
    song_sp_bonus = int((extra_stat_bonus or {}).get("skill_point", 0) or 0)

    # Grand Live's Friendship Bonus: one multiplier on the friendship product,
    # and ONLY when a rainbow actually triggered -- it is a "friendship training
    # gain" bonus, so a training with no friendship card gets nothing from it.
    if any_friendship and scenario_friendship_bonus:
        final_friendship_bonus *= 1 + (int(scenario_friendship_bonus) / 100)

    final_mood_effect = 1 + (BASE_MOOD_MULTS[motivation] * ((total_mood_effect / 100) + 1) / 100)
    final_training_effect = 1 + (total_training_effect / 100)
    # +5% per BODY standing in the facility -- support cards and Grand Live's
    # recruited (uncarded) supporters alike; see npc_supporter_count above.
    final_char_count = 1 + ((count + npc_supporter_count) / 20)

    result = {}
    for i, stat_name in enumerate(STAT_NAMES):
        if base_stats[i] == 0:
            continue
        base_val = base_stats[i] + stat_bonus[i]
        raw_val = math.floor(
            base_val * final_friendship_bonus * final_mood_effect
            * final_training_effect * final_char_count
            * ((growth[i] / 100) + 1)
            + song_stat_bonus[i] * final_friendship_bonus
        )
        result[stat_name] = _apply_stat_cap(raw_val, current_stats.get(stat_name, 0), max_stats.get(stat_name, 9999))

    sp_raw = base_sp + sp_bonus
    result["skill_point"] = math.floor(
        final_friendship_bonus * final_mood_effect * final_training_effect * final_char_count * sp_raw
        + song_sp_bonus * final_friendship_bonus
    )
    # already signed (negative = vital cost); the cards present adjust it
    result["energy_cost"] = training_energy(energy_delta, command_id, in_facility_cards,
                                            levels=support_card_levels)
    if any_friendship and friendship_energy_down_pct and result["energy_cost"] < 0:
        result["energy_cost"] = -math.floor(
            abs(result["energy_cost"]) * max(0.0, 1 - friendship_energy_down_pct / 100) + 1e-9)

    return result


def _apply_stat_cap(stat_inc: int, current: int, max_stat: int) -> int:
    """The 1200 soft-cap (gains halve past 1200) plus the hard per-stat cap,
    as verified in for-reals-uma-sim-main's calculate_actual_stat_gain."""
    if stat_inc <= 0:
        return math.floor(stat_inc)

    if current >= MAX_STAT_1200_HALVING:
        actual = stat_inc / 2
    elif current + stat_inc > MAX_STAT_1200_HALVING:
        over = (current + stat_inc) - MAX_STAT_1200_HALVING
        actual = (MAX_STAT_1200_HALVING - current) + (over / 2)
    else:
        actual = stat_inc

    # Halving never takes a real gain to 0: a +1 above 1200 still shows +1.
    # Real JP previews: floor-but-at-least-1 matches 4,813/4,815 past 1200,
    # plain floor 4,791 (every pre-halving +1 was shown as 1, 22/22). Global
    # has no capture that separates the two; it is the same game rule.
    actual = max(1, math.floor(actual))
    if current + actual > max_stat:
        actual = max_stat - current
    return actual
