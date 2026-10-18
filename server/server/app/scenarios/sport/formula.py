"""UAF Ready GO! (scenario 7) -- the training numbers: sport-rank gains, the
home preview and the scenario's own bonus line (sport_data_set.command_info_array).

Every rule is docs/JP_UAF_SCENARIO.md §4-§6, checked against every real reply in
the headless captures (jp_docs/UAF/research_scripts/*_parity.py):

    rank gain   = min(100 - rank, (3 + (k ? k//2 + 1 : 0)) x (2 if friendship) + 3 after rest/outing/race)
                  k = card partners (+ the UAF NPC 111); 102/103 do not count       11,022/11,022
    home        = Ramen's home formula on the per-level bases below                 15,503/15,515
    bonus line  = link training (+1 base per linked sport's main stat, SP base +k, main x 1.1/1.2/1.25/1.3,
                  card stat bonuses only on the facility's own stats) x (1 + sum of competition training-bonus %)
                  minus home                                                        see §6
"""

from __future__ import annotations

import math

from ..ramen import formula as RF

SPORTS = tuple(g * 100 + 2000 + s for g in (1, 2, 3) for s in (1, 2, 3, 4, 5))   # 2101..2305
STATCMD = {1: 101, 2: 105, 3: 102, 4: 103, 5: 106}     # sport % 100 -> its stat facility
TARGET_SP = 30
MAX_RANK = 100
REST_BONUS_COMMANDS = frozenset({701, 304, 390})       # the +3 rank after these (and races); not 801
NPC_RANK_PARTNER = 111                                 # counts toward k like a card; 102/103 do not
LINK_MAIN_MULT = {0: 1.0, 1: 1.1, 2: 1.2, 3: 1.25, 4: 1.3}   # trained main stat x, by link count
LINK_MAIN_MULT_SUMMER = {0: 1.0, 1: 1.2, 2: 1.3, 3: 1.35, 4: 1.4}   # summer camp T37-40/61-64; 4 not captured
# Martial-arts Heat-Up (stance 2xx, effect type 10): + value_2 % on the link multiplier by link count
FIGHT_STANCE_PCT = {1: 30, 2: 45, 3: 54, 4: 60}
SUMMER_TURNS = frozenset(range(37, 41)) | frozenset(range(61, 65))

# {sport: {level: {target_type: base}}}: level 1 = master single_mode_training_effect scenario 7;
# levels 2-5 fitted cell by cell (every cell reproduces all its previews): main +1 per level,
# the first secondary stat +1 at level 5.
BASE = {
    2101: {1: {1: 12, 3: 1}, 2: {1: 13, 3: 1}, 3: {1: 14, 3: 1}, 4: {1: 15, 3: 1}, 5: {1: 16, 3: 2}},
    2102: {1: {2: 11, 4: 2}, 2: {2: 12, 4: 2}, 3: {2: 13, 4: 2}, 4: {2: 14, 4: 2}, 5: {2: 15, 4: 3}},
    2103: {1: {2: 2, 3: 11}, 2: {2: 2, 3: 12}, 3: {2: 2, 3: 13}, 4: {2: 2, 3: 14}, 5: {2: 3, 3: 15}},
    2104: {1: {1: 1, 3: 1, 4: 12}, 2: {1: 1, 3: 1, 4: 13}, 3: {1: 1, 3: 1, 4: 14}, 4: {1: 1, 3: 1, 4: 15},
           5: {1: 2, 3: 1, 4: 16}},
    2105: {1: {1: 2, 5: 11}, 2: {1: 2, 5: 12}, 3: {1: 2, 5: 13}, 4: {1: 2, 5: 14}, 5: {1: 3, 5: 15}},
    2201: {1: {1: 8, 3: 1}, 2: {1: 9, 3: 1}, 3: {1: 10, 3: 1}, 4: {1: 11, 3: 1}, 5: {1: 12, 3: 2}},
    2202: {1: {2: 7, 4: 2}, 2: {2: 8, 4: 2}, 3: {2: 9, 4: 2}, 4: {2: 10, 4: 2}, 5: {2: 11, 4: 3}},
    2203: {1: {2: 2, 3: 7}, 2: {2: 2, 3: 8}, 3: {2: 2, 3: 9}, 4: {2: 2, 3: 10}, 5: {2: 3, 3: 11}},
    2204: {1: {1: 1, 3: 1, 4: 8}, 2: {1: 1, 3: 1, 4: 9}, 3: {1: 1, 3: 1, 4: 10}, 4: {1: 1, 3: 1, 4: 11},
           5: {1: 2, 3: 1, 4: 12}},
    2205: {1: {1: 2, 5: 7}, 2: {1: 2, 5: 8}, 3: {1: 2, 5: 9}, 4: {1: 2, 5: 10}, 5: {1: 3, 5: 11}},
    2301: {1: {1: 14, 3: 1}, 2: {1: 15, 3: 1}, 3: {1: 16, 3: 1}, 4: {1: 17, 3: 1}, 5: {1: 18, 3: 2}},
    2302: {1: {1: 1, 2: 10, 4: 2}, 2: {1: 1, 2: 11, 4: 2}, 3: {1: 1, 2: 12, 4: 2}, 4: {1: 1, 2: 13, 4: 2},
           5: {1: 2, 2: 14, 4: 2}},
    2303: {1: {1: 1, 2: 2, 3: 10}, 2: {1: 1, 2: 2, 3: 11}, 3: {1: 1, 2: 2, 3: 12}, 4: {1: 1, 2: 2, 3: 13},
           5: {1: 2, 2: 2, 3: 14}},
    2304: {1: {1: 2, 3: 1, 4: 12}, 2: {1: 2, 3: 1, 4: 13}, 3: {1: 2, 3: 1, 4: 14}, 4: {1: 2, 3: 1, 4: 15},
           5: {1: 3, 3: 1, 4: 16}},
    2305: {1: {1: 4, 5: 10}, 2: {1: 4, 5: 11}, 3: {1: 4, 5: 12}, 4: {1: 4, 5: 13}, 5: {1: 5, 5: 14}},
}
SP = {2101: 6, 2102: 6, 2103: 6, 2104: 6, 2105: 6, 2201: 10, 2202: 10, 2203: 10, 2204: 10, 2205: 10,
      2301: 4, 2302: 6, 2303: 6, 2304: 5, 2305: 5}
ENERGY = -15                                            # every sport, every level (master target 10)
# The extra energy cost, rolled per (turn, sport), stable within the turn. NOT EXACT: the
# weights are the captures' counts (0:841 1:1696 2:1688 3:31); no master table.
ENERGY_EXTRA_WEIGHTS = ((0, 841), (1, 1696), (2, 1688), (3, 31))
SPHERE_STANCE_SP = 20                                   # ball-game Heat-Up (1xx): SP +20 after the multipliers
# single_mode_sport_link: a linked sport adds this to its own main stat's base by ITS training
# level (every sport the same), plus 1 SP.
LINK_ADD = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3}


def genre(sport: int) -> int:
    return sport // 100 - 20                            # 1 ball game, 2 martial arts, 3 variety


def main_stat(sport: int) -> int:
    return sport % 100


def level_of(rank: int) -> int:
    """The facility level shown for a sport rank (§5)."""
    return 1 if rank < 20 else 2 if rank < 30 else 3 if rank < 40 else 4 if rank < 50 else 5


def friend_fn(sport: int):
    stat_cmd = STATCMD[main_stat(sport)]
    return lambda sid, kind, cmd, bond: kind == 1 and cmd == stat_cmd and bond >= RF.FRIENDSHIP_BOND


# ----------------------------------------------------------------- sport rank
def self_rank_gain(chara_info: dict, sport: int, partners, after_rest: bool) -> int:
    """This sport's own rank gain when trained (before the 100 cap)."""
    by_pos, bond = RF.deck(chara_info), RF.bonds(chara_info)
    k = 0
    friendship = False
    stat_cmd = STATCMD[main_stat(sport)]
    for p in partners or ():
        if p in by_pos:
            k += 1
            kind, cmd, _r, _c = RF.card_meta(by_pos[p])
            if kind == 1 and cmd == stat_cmd and bond.get(p, 0) >= RF.FRIENDSHIP_BOND:
                friendship = True
        elif p == NPC_RANK_PARTNER:
            k += 1
    base = 3 + (k // 2 + 1 if k else 0)
    return base * (2 if friendship else 1) + (3 if after_rest else 0)


def gain_sport_rank_array(chara_info: dict, sport: int, offered: dict, ranks: dict, after_rest: bool) -> list:
    """[{command_id, gain_rank}] for training `sport`: itself and every other
    offered sport of its genre (link training), each at its own gain, capped
    at rank 100 (a capped sport still listed with 0). `offered` = {sport: partners}."""
    out = []
    for s in [sport] + [o for o in offered if o != sport and genre(o) == genre(sport)]:
        g = self_rank_gain(chara_info, s, offered[s], after_rest)
        out.append({"command_id": s, "gain_rank": max(0, min(g, MAX_RANK - int(ranks.get(s, 0))))})
    return out


# ----------------------------------------------------------------- stat gains
def home_raw(chara_info: dict, sport: int, level: int, partners, card_levels=None) -> dict:
    return RF.home_raw(chara_info, sport, level, partners, card_levels, table=BASE, sp=SP[sport],
                       friend_fn=friend_fn(sport))


def roll_energy_extra(rng) -> int:
    total = sum(w for _v, w in ENERGY_EXTRA_WEIGHTS)
    x = rng.randrange(total)
    for v, w in ENERGY_EXTRA_WEIGHTS:
        if x < w:
            return v
        x -= w
    return 0


def home_params(chara_info: dict, sport: int, level: int, partners, card_levels=None,
                energy: int = ENERGY) -> list:
    """home_info params_inc_dec_info_array for a sport (stats, SP, energy).
    `energy` is the rolled cost (ENERGY - extra) before cost-down cards."""
    raw = home_raw(chara_info, sport, level, partners, card_levels)
    out = []
    for tt in (1, 2, 3, 4, 5, TARGET_SP):
        if tt in raw:
            v = RF.displayed(chara_info, tt, RF.capped(raw[tt]))
            if v:
                out.append({"target_type": tt, "value": v})
    out.append({"target_type": 10, "value": RF.energy_after_cost_down(chara_info, partners, energy, card_levels)
                if hasattr(RF, "energy_after_cost_down") else energy})
    return out


def link_raw(chara_info: dict, sport: int, level: int, partners, linked, card_levels=None) -> dict:
    """The facility's raw gains with link training folded in (§6.2): each linked
    sport (sport, its level) adds LINK_ADD[level] to the base of its own main
    stat, SP base + 1 per link. A stat
    already in the facility's base takes the extra points through the home
    formula as-is; a stat the link adds gets every multiplier but no card flat
    bonus."""
    if not linked:
        return home_raw(chara_info, sport, level, partners, card_levels)
    adds: dict = {}
    for s, lv in linked:
        adds[main_stat(s)] = adds.get(main_stat(s), 0) + LINK_ADD[max(1, min(5, int(lv or 1)))]
    base = dict(BASE[sport][level])
    for tt, n in adds.items():
        if tt in base:
            base[tt] += n
    out = RF.home_raw(chara_info, sport, level, partners, card_levels, table={sport: {level: base}},
                      sp=SP[sport] + len(linked), friend_fn=friend_fn(sport))
    talents = RF.growth(chara_info.get("card_id"))
    for tt, n in adds.items():
        if tt not in BASE[sport][level]:
            out[tt] = n * _per_point(chara_info, sport, level, partners, tt, card_levels) / (1 + talents[tt - 1] / 100)
    return out


def _per_point(chara_info, sport, level, partners, tt, card_levels=None) -> float:
    """One point of base for target tt on this facility through every home
    multiplier, the card flat bonus excluded: raw is (base + bonus) x M, so
    M = raw(2) - raw(1)."""
    def raw(v):
        return RF.home_raw(chara_info, sport, level, partners, card_levels, table={sport: {level: {tt: v}}},
                           sp=0, friend_fn=friend_fn(sport)).get(tt, 0.0)
    return raw(2) - raw(1)


def bonus_params(chara_info: dict, sport: int, level: int, partners, linked, compe_pct: int,
                 card_levels=None, summer: bool | None = None, stances=()) -> list:
    """sport_data_set.command_info_array params_inc_dec_info_array: total minus home."""
    home_pre_raw = home_raw(chara_info, sport, level, partners, card_levels)
    raw = link_raw(chara_info, sport, level, partners, linked, card_levels)
    if summer is None:
        summer = int(chara_info.get("turn") or 0) in SUMMER_TURNS
    k = min(4, len(linked))
    mult = (LINK_MAIN_MULT_SUMMER if summer else LINK_MAIN_MULT)[k]
    if k and any(st // 100 == 2 for st in stances):
        mult += FIGHT_STANCE_PCT[k] / 100
    sphere = any(st // 100 == 1 for st in stances)
    own = BASE[sport][level]
    added = {main_stat(s) for s, _lv in linked} - set(own)
    # Wire order: the facility's own stats, SP, then the stats only links add (always listed).
    order = sorted(t for t in raw if t not in added and t != TARGET_SP) + \
        ([TARGET_SP] if TARGET_SP in raw else []) + sorted(t for t in raw if t in added)
    out = []
    for tt in order:
        v = raw[tt] * (mult if tt == main_stat(sport) else 1.0) * (1 + compe_pct / 100)
        if tt == TARGET_SP and sphere:
            v += SPHERE_STANCE_SP
        home_pre = RF.capped(home_pre_raw.get(tt, 0))
        delta = min(RF.PREVIEW_CAP, int(math.floor(v + 1e-9))) - home_pre
        d = RF._shown_bonus(chara_info, tt, home_pre, delta) if delta > 0 else 0
        if d or tt in added:
            out.append({"target_type": tt, "value": d})
    return out
