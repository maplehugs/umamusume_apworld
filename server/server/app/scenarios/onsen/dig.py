"""ONSEN (scenario 12) -- digging: tool power, the dig budget, and what every
30 dug pays. docs/JP_ONSEN_SCENARIO.md §4-§6; all three are exact against the
captures (101k dig previews, 638k tool values, every dig-bonus row).

    tool  = dig_item[level] + dig_power(type, param, rank(stat)) x 3
            + factor_bonus(type, group) per inherited blue factor      (§5)
    m     = 1 + (tool + 10 x linked charas of the type) / 100          (the +10
            never shows in the displayed tool value)
    dig   = a base-point budget spent layer by layer: a layer finishes for
            ceil(rest / m) points and the rest carries on               (§4)
"""

from __future__ import annotations

import bisect
import math

from . import master as M

SAND, SOIL, ROCK = 1, 2, 3
STAT_KEYS = {1: "speed", 2: "stamina", 3: "power", 4: "guts", 5: "wiz"}

# Stat rank for dig_power: the game's status grade. Only the edges where the
# dig_power buckets change (100/200/300/400/600/1000/1201) are pinned by the
# captures -- 100% of rows with these edges, and the TOP edge is exclusive: a
# stat of exactly 1200 is still rank 18 (§5).
RANK_EDGES = (50, 100, 150, 200, 250, 300, 350, 400, 500, 600, 700, 800, 900,
              1000, 1050, 1100, 1150, 1201)

# Link charas by the layer type they dig (dump.cs SCENARIO_LINK_CHARA_ID_*;
# the type per chara is the guide's -- only Teio's +10 is capture-proven).
LINK_CHARAS = {1003: SAND, 1026: SOIL, 1080: SOIL, 1099: ROCK, 1100: ROCK}
LINK_POWER = 10

# Budget bases (§4).
BASE_TRAINING = 25          # + deck cards standing in the facility
BASE_ASSISTANT = 10         # + assistants
BASE_REST = 15              # rest 701, a normal outing 301
BASE_KIYOKO_OUTING = 25     # her date, group outing 390
BASE_RACE = 15
BASE_GOAL_RACE = 25         # a training-goal race turn

THRESHOLD_ENERGY = 10       # target_type of the dig bonus's energy row


def stat_rank(value: int) -> int:
    return bisect.bisect_right(RANK_EDGES, int(value or 0)) + 1


def tool_value(chara_info: dict, stratum_type: int, level: int, blue_groups=None,
               enabled: bool = True) -> int:
    """The displayed dig_effect_value of one tool (§5). `blue_groups` is the
    lineage's blue-factor groups (one entry per factor, stars ignored); they
    count only once the first spring is picked (`enabled`)."""
    item = M.item_for_stratum().get(stratum_type, stratum_type)
    total = M.dig_item_values().get((item, int(level)), 0)
    for param in M.stratum_params().get(stratum_type, ()):
        rank = stat_rank(chara_info.get(STAT_KEYS[param]) or 0)
        for lo, hi, bonus in M.dig_power().get((stratum_type, param), ()):
            if lo <= rank <= hi:
                total += bonus
                break
    if enabled:
        for group in blue_groups or ():
            total += M.factor_bonus().get((stratum_type, int(group)), 0)
    return total


def link_power(linked: set, stratum_type: int) -> int:
    return LINK_POWER * sum(1 for c, t in LINK_CHARAS.items() if t == stratum_type and c in linked)


def multiplier(tool: int, link: int) -> float:
    return 1 + (tool + link) / 100


def plan(base: int, layers: list) -> list:
    """[(stratum_id, dug)] for a budget of `base` points over `layers`
    [(stratum_id, rest, m)] in order (only layers with rest > 0)."""
    out = []
    budget = int(base)
    for sid, rest, m in layers:
        if budget <= 0 or rest <= 0:
            continue
        full = math.floor(budget * m + 1e-9)
        if full >= rest:
            out.append((sid, rest))
            budget -= math.ceil(rest / m - 1e-9)
        else:
            if full > 0:
                out.append((sid, full))
            budget = 0
    return out


def bonus_for(stratum_id: int, before: int, after: int) -> dict:
    """{target_type: amount} a layer pays going from `before` to `after` dug
    (every threshold t with before < t <= after, §6)."""
    out: dict = {}
    for dv, rows in M.dig_bonus().get(int(stratum_id), ()):
        if before < dv <= after:
            for tt, v in rows:
                out[tt] = out.get(tt, 0) + v
    return out


def plan_bonus(digs: list, rests: dict) -> dict:
    """Summed dig bonus of a plan, against the current rests."""
    out: dict = {}
    info = M.stratum_info()
    for sid, amount in digs:
        vol = info[sid][2]
        before = vol - int(rests.get(str(sid), rests.get(sid, vol)))
        for tt, v in bonus_for(sid, before, before + amount).items():
            out[tt] = out.get(tt, 0) + v
    return out
