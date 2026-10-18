"""PROJECT L'ARC (scenario 6) -- the training numbers: the home preview, its
energy, the scenario line (arc_data_set.command_info_array) and the overseas
points a training earns.

docs/JP_LARC_SCENARIO.md §8 and §9.1; jp_docs/LArc/research_scripts/larc_ref.py
is the reference model this ports (check_all.py: home 5955/5960, scenario line
5955/5955, expedition points 945/945 over 23 careers):

    home     = the shared JP product (ramen/legend pieces) on scenario 6's
               per-level bases, SP 6; members (>= 1000) are bodies, NPC
               partners 101-115 are not; cap 100, then the 1200 halving
    scenario = floor((home_pre + flat) x (100 + E) x F / 10000) - home_pre,
               cap 100, then the halving (_shown_bonus)
    exp      = 50 (wit 30) + 20 per partner + 20 per rainbow partner
"""

from __future__ import annotations

import math

from ... import training_formula as tf
from ..legend import formula as LF
from ..ramen import formula as RF
from . import master as M

TARGET_SP = RF.TARGET_SP
TARGET_ENERGY = RF.TARGET_ENERGY
STATS = RF.STATS
SUMMER_TO_BASE = RF.SUMMER_TO_BASE

# FACILITY BASE VALUES PER LEVEL {command: {level: {target_type: value}}} (§8.1).
# Lv1 = master single_mode_training_effect scenario 6; Lv2-5 fitted from the
# captures (basefit.py; guts Lv5 from one row, V5).
BASE = {
    101: {1: {1: 10, 3: 3}, 2: {1: 11, 3: 3}, 3: {1: 12, 3: 3}, 4: {1: 13, 3: 4}, 5: {1: 14, 3: 5}},
    105: {1: {2: 9, 4: 4}, 2: {2: 10, 4: 4}, 3: {2: 11, 4: 4}, 4: {2: 12, 4: 5}, 5: {2: 13, 4: 6}},
    102: {1: {2: 5, 3: 11}, 2: {2: 5, 3: 12}, 3: {2: 5, 3: 13}, 4: {2: 6, 3: 14}, 5: {2: 7, 3: 15}},
    103: {1: {1: 3, 3: 2, 4: 10}, 2: {1: 3, 3: 2, 4: 11}, 3: {1: 3, 3: 2, 4: 12},
          4: {1: 4, 3: 2, 4: 13}, 5: {1: 4, 3: 3, 4: 14}},
    106: {1: {1: 2, 5: 9}, 2: {1: 2, 5: 10}, 3: {1: 2, 5: 11}, 4: {1: 3, 5: 12}, 5: {1: 4, 5: 13}},
}
# The expedition's fixed values (master rows 6032-6052; no levels).
EXPED_BASE = {1101: {1: 16, 3: 5}, 1102: {2: 15, 4: 7}, 1103: {2: 9, 3: 17},
              1104: {1: 6, 3: 5, 4: 16}, 1105: {1: 5, 5: 14}}
BASE_SP = 6
# Energy by level (§8.1, the most common value per facility and level); the
# expedition uses master's rows.
ENERGY = {101: {1: -21, 2: -22, 3: -23, 4: -25, 5: -27},
          105: {1: -19, 2: -20, 3: -21, 4: -23, 5: -25},
          102: {1: -20, 2: -21, 3: -22, 4: -24, 5: -26},
          103: {1: -21, 2: -22, 3: -23, 4: -25, 5: -27}}
EXPED_ENERGY = {1101: -21, 1102: -19, 1103: -20, 1104: -21}
WIT_ENERGY, EXPED_WIT_ENERGY = 5, 6

FRIEND_POTENTIAL = 8        # 精神力 Lv3: friendship trainings x1.2 on the scenario line
ENERGY_POTENTIAL = 7        # 強心臓 Lv3: expedition energy -20 %
EFFECT_FLAT, EFFECT_TRAINING, EFFECT_FRIEND = 1, 2, 3


def base_of(command_id: int) -> int:
    cid = int(command_id or 0)
    return M.EXPED.get(cid, SUMMER_TO_BASE.get(cid, cid))


def is_exped(command_id: int) -> bool:
    return int(command_id or 0) in M.EXPED


def base_values(command_id: int, level: int) -> dict:
    cid = int(command_id or 0)
    if cid in EXPED_BASE:
        out = dict(EXPED_BASE[cid])
    else:
        lv = max(1, min(5, int(level or 1)))
        out = dict(BASE.get(base_of(cid), {}).get(lv, {}))
    if out:
        out[TARGET_SP] = BASE_SP
    return out


# ================================================================ home ===

def friendship_card(chara_info: dict, command_id: int, sid: int, bond: int) -> bool:
    """A rainbow: a normal card on its own facility at bond 80+."""
    kind, cmd, _r, _c = RF.card_meta(sid)
    return kind == 1 and cmd == base_of(command_id) and bond >= RF.FRIENDSHIP_BOND


def parts(chara_info: dict, command_id: int, level: int, partners, card_levels=None) -> dict:
    """The pieces of the shared product (legend.formula.parts' shape on this
    scenario's table)."""
    base = base_values(command_id, level)
    training = mood_up = 0.0
    friendship = 1.0
    bonus = {tt: 0.0 for tt in base}
    nfriend = 0
    cards = RF.facility_cards(chara_info, partners)
    deck_ids = list(RF.deck(chara_info).values())
    for sid, bond in cards:
        lv = int((card_levels or {}).get(sid) or RF.max_level(sid))

        def eff(t, _s=sid, _b=bond, _l=lv):
            return RF.card_effect(_s, t, _l) + RF.unique_effect(_s, t, _b, _l, chara_info)

        training += eff(tf.EFFECT_TRAINING)
        mood_up += eff(tf.EFFECT_MOOD)
        for tt in bonus:
            et = tf.EFFECT_SKILL_POINT if tt == TARGET_SP else tf.EFFECT_STAT_BONUS_BASE + tt - 1
            bonus[tt] += eff(et)
        ds, dsp = tf.deck_type_stat_bonus(sid, bond, deck_ids, lv)
        for tt in bonus:
            bonus[tt] += dsp if tt == TARGET_SP else ds[tt - 1]
        if friendship_card(chara_info, command_id, sid, bond):
            nfriend += 1
            friendship *= ((1 + RF.card_effect(sid, tf.EFFECT_FRIENDSHIP, lv) / 100)
                           * (1 + RF.unique_effect(sid, tf.EFFECT_FRIENDSHIP, bond, lv, chara_info) / 100))
    return {"base": base, "bonus": bonus, "training": training, "mood_up": mood_up,
            "friendship": friendship, "bodies": len(cards) + RF.npc_bodies(partners),
            "ncards": len(cards), "nfriend": nfriend, "growth": RF.growth(chara_info.get("card_id"))}


def home_line(chara_info: dict, command_id: int, level: int, partners, card_levels=None) -> dict:
    """{target_type: home_pre} -- floored, capped at 100, before the halving."""
    p = parts(chara_info, command_id, level, partners, card_levels)
    return {tt: RF.capped(v) for tt, v in LF.product(chara_info, p).items()}


def base_energy(command_id: int, level: int) -> int:
    cid = int(command_id or 0)
    if cid == 1105:
        return EXPED_WIT_ENERGY
    if cid in EXPED_ENERGY:
        return EXPED_ENERGY[cid]
    base = base_of(cid)
    if base == 106:
        return WIT_ENERGY
    return ENERGY.get(base, ENERGY[101]).get(max(1, min(5, int(level or 1))), -21)


def energy(chara_info: dict, command_id: int, level: int, partners, card_levels=None) -> int:
    """cost = -floor(|base| x prod(1 - each card's cost-down)); wit's gain plus
    the wit recovery of the friendship cards standing there (Mecha's rule)."""
    base = base_energy(command_id, level)
    if base < 0:
        mult = 1.0
        for f in LF.energy_down_factors(chara_info, partners, card_levels):
            mult *= f
        return -int(math.floor(-base * mult + 1e-9))
    total = 0.0
    for sid, bond in RF.facility_cards(chara_info, partners):
        if friendship_card(chara_info, command_id, sid, bond):
            lv = int((card_levels or {}).get(sid) or RF.max_level(sid))
            total += (max(0.0, RF.card_effect(sid, tf.EFFECT_WIT_RECOVERY, lv))
                      + tf.bond_gated_effect(sid, tf.EFFECT_WIT_RECOVERY, bond, lv))
    return base + int(round(total))


def home_gains(chara_info: dict, command_id: int, level: int, partners, card_levels=None) -> dict | None:
    """The home preview in calculate_training_gain's shape."""
    line = home_line(chara_info, command_id, level, partners, card_levels)
    if not line:
        return None
    out = {}
    for tt, pre in line.items():
        out["skill_point" if tt == TARGET_SP else STATS[tt - 1]] = RF.displayed(chara_info, tt, pre)
    out["energy_cost"] = energy(chara_info, command_id, level, partners, card_levels)
    return out


# ============================================================ scenario ===

def training_eff(approval_rate: int) -> int:
    """Master single_mode_arc_training_eff at the whole percent (§7)."""
    pct = int(approval_rate) // 10
    for lo, hi, e in M.training_eff_rows():
        if lo <= pct <= hi:
            return e
    return 0


def flat_bonus(levels: dict, target: int) -> int:
    """Effect 1 rows (§9.3): flat +v2 to target v1 at the row's level."""
    return sum(v2 for pid, plv, et, v1, v2, _v3, _v4 in M.potential_bonus()
               if et == EFFECT_FLAT and v1 == target and int(levels.get(pid, 0)) >= plv)


def extra_pct(levels: dict, command_id: int) -> int:
    """Effect 2 rows: +v2 % on facility v1 (0 = all); v3 = 1 expedition only."""
    base, exped = base_of(command_id), is_exped(command_id)
    return sum(v2 for pid, plv, et, v1, v2, v3, _v4 in M.potential_bonus()
               if et == EFFECT_TRAINING and int(levels.get(pid, 0)) >= plv
               and v1 in (0, base) and (not v3 or exped))


def scenario_delta(home_pre: int, target: int, approval_rate: int, levels: dict,
                   command_id: int, friendship: bool) -> int:
    """§8.2 before the 1200 halving; capped at 100 (U2 T66)."""
    e = training_eff(approval_rate) + extra_pct(levels, command_id)
    f = 120 if (friendship and int(levels.get(FRIEND_POTENTIAL, 0)) >= 3) else 100
    fl = flat_bonus(levels, target)
    return min(RF.PREVIEW_CAP, (home_pre + fl) * (100 + e) * f // 10000 - home_pre)


def energy_refund(home_energy: int, levels: dict, command_id: int) -> int:
    """強心臓 Lv3 on the expedition: +ceil(0.2 x the cost) (24/24)."""
    if is_exped(command_id) and int(levels.get(ENERGY_POTENTIAL, 0)) >= 3 and home_energy < 0:
        return -(home_energy // 5)
    return 0


def scenario_line(chara_info: dict, command_id: int, level: int, partners, card_levels,
                  approval_rate: int, levels: dict, home_energy: int) -> list:
    """arc_data_set.command_info_array[].params_inc_dec_info_array; zero
    entries omitted (§8.2)."""
    p = parts(chara_info, command_id, level, partners, card_levels)
    home = {tt: RF.capped(v) for tt, v in LF.product(chara_info, p).items()}
    out = []
    for tt in sorted(home):
        pre = home[tt]
        d = scenario_delta(pre, tt, approval_rate, levels, command_id, p["nfriend"] > 0)
        if d > 0 and tt <= 5:
            d = RF._shown_bonus(chara_info, tt, pre, d)
        if d > 0:
            out.append({"target_type": tt, "value": d})
    refund = energy_refund(home_energy, levels, command_id)
    if refund:
        out.append({"target_type": TARGET_ENERGY, "value": refund})
    return out


def global_exp(chara_info: dict, command_id: int, partners) -> int:
    """add_global_exp of an expedition training (§9.1, 50/50 previews):
    every partner counts (cards, NPCs, members), rainbows once more."""
    if not is_exped(command_id):
        return 0
    rainbow = sum(1 for sid, bond in RF.facility_cards(chara_info, partners)
                  if friendship_card(chara_info, command_id, sid, bond))
    return (30 if int(command_id) == 1105 else 50) + 20 * len(list(partners or ())) + 20 * rainbow


def rainbow_count(chara_info: dict, command_id: int, partners) -> int:
    return sum(1 for sid, bond in RF.facility_cards(chara_info, partners)
               if friendship_card(chara_info, command_id, sid, bond))
