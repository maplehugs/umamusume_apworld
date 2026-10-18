"""RAMEN (scenario 14, JP only) -- らっしゃい！トレセン軒！ -- the mechanics.

docs/JP_RAMEN_SCENARIO.md is the spec this implements, section for section; it
records where every rule and number came from (62 complete real careers, the
single_mode_14_* master tables and the JP client dump). This module holds the
career state and the rules that move it:

    the learning gauge and tricks      §3   (gauge_*, add_tricks)
    secret ingredients                 §4   (add_secrets)
    tasting                            §5   (taste)
    the scenario's bonus line          §6   (facility_bonus)
    the Ramen Jamboree                 §7   (commit_check_point, jamboree_rewards)
    region selection                   §9   (select_regions)
    the Ultimate Ramen finals          §10  (apply_uraf)

and builds the ramen_data_set every response carries (attach).

WHERE A RULE IS NOT SETTLED BY THE CAPTURES it says so where it is applied,
with the value chosen -- see "INFERRED" below and §14 of the doc.
"""

from __future__ import annotations

import copy
import logging
import random

from ... import career_events as CE
from ... import event_engine
from . import formula, master as M

log = logging.getLogger("uma-server")

SCENARIO_ID = 14
STATE_KEY = "ramen"

FEELINGS = (1, 2, 3)            # 1 noodle, 2 soup, 3 topping
GAUGE_FULL = 7
TRICK_SLOTS = 10
SECRET_CAP = 4
SECRETS_PER_TASTING = 2          # secret ingredients one tasting may spend
TASTING_SIZE = 5                 # feelings one recipe uses
PT_STEP_PCT = 10                 # +10% pt per earlier tasting this period...
PT_STEP_MAX = 5                  # ...for at most five of them
LAST_GAUGE_TURN = 72             # the gauge and tastings end with the last Jamboree
SUMMER_TURNS = frozenset({37, 38, 39, 40, 61, 62, 63, 64})
SUMMER_SSR_MULT = 8              # SSR Tazuna's summer gauge, 76k/76k rows
SUMMER_LINK_MULT = 2             # an older link card's summer gauge (2,370/2,370 rows, 2026-09-30)
FRIENDSHIP_GAUGE = 2
# The base split's total by link card (§3.1): SSR Tazuna 10, an older
# Tazuna / Light Hello card 5 (captured with 10021 and 30052), none 3.
GAUGE_TOTAL = {2: 10, 1: 5, 0: 3}
REGION_PICKS = 3

# Jamboree results (§7).
RESULT_OK, RESULT_GREAT, RESULT_SUPER = 1, 2, 3
RESULT_EVENTS = {1: {RESULT_OK: 214006, RESULT_GREAT: 214006},
                 2: {RESULT_OK: 214008, RESULT_GREAT: 214008},
                 3: {RESULT_OK: 214011, RESULT_GREAT: 214010, RESULT_SUPER: 214016}}
RESULT_STORIES = {214006: 400014006, 214008: 400014012, 214010: 400014020,
                  214011: 400014021, 214016: 400014019}
RESULT_TIMING = 24               # every captured result event, 187/187
RESULT_SHOW_CLEAR = 1401
ULTIMATE_SHOW_CLEAR = 1402
# Rewards by (check_point_type, result): all-stat, SP, fans, and whether every
# facility gains a level. Every row is captured (盛況 at all three, 2026-09-30).
JAMBOREE_REWARD = {
    (1, RESULT_GREAT): (10, 100, 3000, True),
    (1, RESULT_OK): (5, 50, 500, False),
    (2, RESULT_GREAT): (15, 150, 18000, True),
    (2, RESULT_OK): (10, 75, 2000, False),
    (3, RESULT_SUPER): (30, 250, 45000, True),
    (3, RESULT_GREAT): (20, 200, 45000, True),
    (3, RESULT_OK): (15, 150, 5000, False),
}
# Energy = base + feeling_bonus(tricks held); 30 for 大盛況 and up across 200
# samples, 20 for 盛況 (4 samples).
JAMBOREE_ENERGY = {RESULT_OK: 20, RESULT_GREAT: 30, RESULT_SUPER: 30}
# Hints (skill_id, levels). RMJ2 大盛況: 時中の妙. RMJ3: ペースキープ, 深呼吸,
# 恩返し、召し上がれ -- +1 each at 大盛況, +2/+2/+3 at 超盛況. 盛況 teaches
# none of these, only the chosen ramen skill (captured).
JAMBOREE_HINTS = {
    (2, RESULT_GREAT): ((202791, 1),),
    (3, RESULT_SUPER): ((200472, 2), (200742, 2), (210392, 3)),
    (3, RESULT_GREAT): ((200472, 1), (200742, 1), (210392, 1)),
}

# The link charas (dump.cs SCENARIO_LINK_CHARA_ID_*) in 214030's choice order,
# with the hint each teaches and the gold one when linked.
LINK_HINTS = (
    ((1022,), 201312, 201313),          # Fine Motion
    ((1077,), 201172, 201173),          # Narita Top Road
    ((1120,), 203872, 203871),          # Calstone Light O
    ((1058,), 202722, 202721),          # Meisho Doto
    ((1060,), 201102, 201103),          # Nice Nature
    ((9001, 9008), 203502, 203501),     # Tazuna / Light Hello
)
LINK_NPC_CHARAS = (1022, 1058, 1060, 1077, 1120)
NPC_CHARA_COUNT = 6              # NPC charas in training, every career (62/62)

FINALS_SKILL_TIPS = {1: 200761, 2: 201652, 3: 203851}


# ================================================================ state ===

def _blank() -> dict:
    return {
        "regions": [], "all_regions": [], "base": {}, "gauge": {},
        "tricks": [], "secrets": 0,
        "pt": 0, "tastings": 0,
        "active": {"turn": 0, "effects": []},
        "last_tasting": {"turn": 0, "info": None},
        "results": [], "twinkle": [],
        "uraf": {"type": 0, "turn": 0},
        "npcs": [], "bubbles": {"turn": 0, "map": {}},
        "extra_partners": {"turn": 0, "map": {}},
        "preview": {"turn": 0, "bonus": {}, "reduce": {}},
        "hold_turn": 0, "gauge_due": "", "flags": {}, "marks": {},
        "link_steps": {}, "auto_select": {},
        "exec_counts": {},
    }


def state(full_state: dict) -> dict:
    st = full_state.get(STATE_KEY)
    if not isinstance(st, dict):
        st = _blank()
        full_state[STATE_KEY] = st
    for k, v in _blank().items():
        st.setdefault(k, copy.deepcopy(v))
    return st


def reset(full_state: dict) -> None:
    full_state.pop(STATE_KEY, None)


def turn_of(chara_info: dict) -> int:
    return int((chara_info or {}).get("turn") or 1)


def served_turn(full_state: dict, chara_info: dict) -> int:
    """The turn the client is being shown: a Jamboree turn is held from its
    action until region selection / the live (see Ramen.held_turn), while the
    run's own turn has already moved on. The data set describes the held one
    -- the real turn-72 chain still shows the gauge and the tricks."""
    return int(state(full_state).get("hold_turn") or 0) or turn_of(chara_info)


def flag(st: dict, name: str, value=None):
    """A one-shot response flag: set with a value, read-and-clear without."""
    if value is not None:
        st["flags"][name] = value
        return value
    return st["flags"].pop(name, None)


# ========================================================== the deck ===

def link_type(chara_info: dict) -> int:
    """2 with SSR Tazuna 30305, 1 with an older Tazuna / Light Hello card,
    0 with neither (single_mode_14_deck_info)."""
    best = 0
    for sid in formula.deck(chara_info).values():
        best = max(best, M.deck_link_types().get(sid, 0))
    return best


def deck_type_count(chara_info: dict) -> int:
    """Distinct card types in the deck, friend and group included -- the
    'deck holds >= 4 types' condition (condition_type 6)."""
    kinds = set()
    for sid in formula.deck(chara_info).values():
        kind, cmd, _r, _c = formula.card_meta(sid)
        kinds.add(("normal", cmd) if kind == 1 else ("kind", kind))
    return len(kinds)


def linked_charas(chara_info: dict) -> set:
    """Every chara the deck or the trainee brings (§12)."""
    out = {int((chara_info.get("card_id") or 0) // 100)}
    for sid in formula.deck(chara_info).values():
        out.add(formula.card_meta(sid)[3])
    return out


def _conditions_met(row: dict, chara_info: dict) -> bool:
    for ctype, value in M.conditions(row):
        if ctype == M.COND_DECK_TYPES and deck_type_count(chara_info) < value:
            return False
    return True


# ===================================================== gauge & tricks ===

def gauge_total(chara_info: dict) -> int:
    return GAUGE_TOTAL[link_type(chara_info)]


def split_base(regions, total: int) -> dict:
    """The per-trick base gauge speed (§3.1): the three regions' recipe needs
    (15 in all) scaled to `total`, rounded down, the leftover handed out by
    largest remainder with ties going to the HIGHER feeling id."""
    need = {f: 0 for f in FEELINGS}
    for r in regions:
        for f, n in M.region_feelings().get(int(r), {}).items():
            need[f] = need.get(f, 0) + n
    whole = sum(need.values()) or 1
    out = {f: total * need[f] // whole for f in FEELINGS}
    left = total - sum(out.values())
    order = sorted(FEELINGS, key=lambda f: (-(total * need[f] % whole), -f))
    for f in order[:left]:
        out[f] += 1
    return out


def gauge_active(st: dict, turn: int) -> bool:
    return bool(st["regions"]) and turn <= LAST_GAUGE_TURN


def roll_bubbles(full_state: dict, chara_info: dict, turn: int) -> bool:
    """This turn's ingredient bubble per facility (§3.2): always a 2/2/1
    split of the three feelings. Rolled once per turn; True when rolled now."""
    st = state(full_state)
    if st["bubbles"].get("turn") == turn:
        return False
    rng = random.Random(f"ramen:bubbles:{CE.career_salt(full_state)}:{turn}")
    single = rng.choice(FEELINGS)
    pair = [f for f in FEELINGS if f != single]
    kinds = [single, pair[0], pair[0], pair[1], pair[1]]
    cmds = list(formula.TRAINING_COMMANDS)
    rng.shuffle(cmds)
    st["bubbles"] = {"turn": turn, "map": {str(c): f for c, f in zip(cmds, kinds)}}
    return True


def bubble(st: dict, base_cmd: int) -> int:
    return int(st["bubbles"].get("map", {}).get(str(base_cmd)) or 0)


def facility_reduce(st: dict, chara_info: dict, command_id: int, partners,
                    turn: int) -> dict:
    """{feeling: gauge points} training this facility would take (§3.3)."""
    base_cmd = formula.SUMMER_TO_BASE.get(command_id, command_id)
    base = {int(k): int(v) for k, v in st["base"].items()}
    friend = formula.is_friendship_training(chara_info, command_id, partners)
    link = link_type(chara_info)
    summer = turn in SUMMER_TURNS and link
    cards = len(formula.facility_cards(chara_info, partners))
    npcs = formula.npc_bodies(partners)
    out = {}
    for f in FEELINGS:
        v = base.get(f, 0)
        if summer:
            v = v * (SUMMER_SSR_MULT if link == 2 else SUMMER_LINK_MULT)
        if friend:
            v += FRIENDSHIP_GAUGE
        # SSR Tazuna's summer ignores the bubble; an older link card's summer
        # keeps it, and a value already at 7+ skips it without clamping down.
        if f == bubble(st, base_cmd) and not (summer and link == 2):
            if v < GAUGE_FULL:
                v += 1 + cards + npcs // 2
            elif not summer:
                v = GAUGE_FULL
        out[f] = v
    return out


def add_tricks(st: dict, feelings) -> list:
    """Append in feeling order; beyond ten the OLDEST drop (§3.5)."""
    gained = sorted(int(f) for f in feelings)
    st["tricks"] = (st["tricks"] + gained)[-TRICK_SLOTS:]
    return gained


def add_secrets(st: dict, n: int) -> None:
    """Secret ingredients, capped at four; a refused one sets the response's
    not_gain_special_feeling (§4.2)."""
    room = SECRET_CAP - int(st["secrets"])
    if n > room:
        flag(st, "not_gain_secret", True)
    st["secrets"] = int(st["secrets"]) + max(0, min(n, room))


def spend_gauge(st: dict, amounts: dict) -> list:
    """Take gauge points; a gauge that empties yields its trick and refills
    to 7, with no carry-over (§3.4)."""
    gained = []
    for f in FEELINGS:
        remain = int(st["gauge"].get(str(f), GAUGE_FULL)) - int(amounts.get(f, 0))
        if remain <= 0:
            gained.append(f)
            remain = GAUGE_FULL
        st["gauge"][str(f)] = remain
    return add_tricks(st, gained)


def plain_gauge(st: dict, chara_info: dict, turn: int) -> dict:
    """What a rest, outing, infirmary visit or race pays the gauge: the base
    split (x8 / x2 in a linked summer)."""
    link = link_type(chara_info)
    mult = (SUMMER_SSR_MULT if link == 2 else SUMMER_LINK_MULT) if (
        turn in SUMMER_TURNS and link) else 1
    return {int(f): int(v) * mult for f, v in st["base"].items()}


def train_gauge(full_state: dict, chara_info: dict, command_id, turn: int) -> list:
    """A successful training on `command_id` -- pays the reduce the player was
    shown for it this turn."""
    st = state(full_state)
    if not gauge_active(st, turn):
        return []
    preview = st["preview"]
    if preview.get("turn") != turn:
        return []
    reduce = preview["reduce"]
    # The client names a camp facility by its camp id (601-605); accept the
    # base id for it as well, so the pay-out never hinges on which one came.
    key = next((k for k in (command_id, formula.BASE_TO_SUMMER.get(command_id),
                            formula.SUMMER_TO_BASE.get(command_id))
                if k is not None and str(k) in reduce), None)
    if key is None:
        return []
    amounts = {int(f): v for f, v in (reduce.get(str(key)) or {}).items()}
    return spend_gauge(st, amounts)


# Facility order of training_exec_info_array on the wire (captured).
EXEC_INFO_ORDER = (101, 105, 102, 103, 106)


def count_training(st: dict, command_id) -> None:
    """One more successful training on this facility this career (a camp
    facility counts toward its base one)."""
    base = formula.SUMMER_TO_BASE.get(int(command_id), int(command_id))
    if base in EXEC_INFO_ORDER:
        st["exec_counts"][str(base)] = int(st["exec_counts"].get(str(base), 0)) + 1


def training_exec_info(st: dict) -> list:
    """Career training counts per facility. The real server sends them with
    the region-selection screen, and auto play's region pick
    (RamenRegionSelector.GetExecTraining) reads them; null there hangs it."""
    return [{"base_command_id": c, "exec_count": int(st["exec_counts"].get(str(c), 0))}
            for c in EXEC_INFO_ORDER]


# ======================================================= active effects ===

def active_effects(st: dict, turn: int) -> list:
    """[(category, id, value)] in force this turn: the tasting's (§5.4) and,
    in the finals, the Ultimate Ramen's (§10)."""
    out = []
    if st["active"].get("turn") == turn:
        out += [tuple(e) for e in st["active"].get("effects") or ()]
    uraf = st["uraf"]
    if uraf.get("turn") == turn and uraf.get("type"):
        out += [(M.CATEGORY_URAF, int(r["id"]), int(r["effect_value"]))
                for r in uraf_rows(uraf["type"], uraf.get("deck_ok", True))
                if int(r["effect_type"]) not in _URAF_INSTANT]
    return out


def _applies_to(row: dict, base_cmd: int) -> bool:
    for ctype, value in M.conditions(row):
        if ctype == M.COND_COMMAND and value not in (0, base_cmd):
            return False
    return True


def has_effect(st: dict, turn: int, effect_type: int) -> bool:
    return any((M.effect_row(c, e) or {}).get("effect_type") == effect_type
               for c, e, _v in active_effects(st, turn))


def effect_sum(st: dict, turn: int, effect_type: int, base_cmd: int = 0) -> int:
    """Σ this turn's active effects of one type that apply to a facility."""
    total = 0
    for cat, eid, value in active_effects(st, turn):
        row = M.effect_row(cat, eid)
        if row and int(row["effect_type"]) == effect_type and (
                not base_cmd or _applies_to(row, base_cmd)):
            total += int(value)
    return total


def limits(st: dict, turn: int) -> dict:
    """{target_type: +N} this turn's limit breaks (effect 10)."""
    out: dict = {}
    for cat, eid, value in active_effects(st, turn):
        row = M.effect_row(cat, eid)
        if not row or int(row["effect_type"]) != M.EFFECT_LIMIT:
            continue
        for ctype, target in M.conditions(row):
            if ctype != M.COND_PARAM:
                continue
            for tt in ((1, 2, 3, 4, 5) if target == 0 else (target,)):
                out[tt] = out.get(tt, 0) + int(value)
    return out


def latest_result(st: dict):
    """(check_point_type, result_state) of the most recent Jamboree, or None.
    Its passives are the ones in force -- they do NOT add up across Jamborees
    (§6.3: stacking fails the senior rainbow rows, latest-only passes)."""
    if not st["results"]:
        return None
    last = max(st["results"], key=lambda r: r["check_point_type"])
    return last["check_point_type"], last["result_state"]


def passive(st: dict, effect_type: int) -> int:
    latest = latest_result(st)
    return M.result_effect(latest[0], latest[1], effect_type) if latest else 0


def facility_bonus(full_state: dict, chara_info: dict, command_id: int, level: int,
                   partners, card_levels=None, turn: int = 0) -> list:
    """This facility's ramen_data_set.command_info_array params (§6.2)."""
    st = state(full_state)
    turn = turn or served_turn(full_state, chara_info)
    base_cmd = formula.SUMMER_TO_BASE.get(command_id, command_id)
    s = M.pt_effect(st["pt"], M.EFFECT_TRAINING) + effect_sum(st, turn, M.EFFECT_TRAINING, base_cmd)
    s_sp = s + effect_sum(st, turn, M.EFFECT_SP_TRAINING, base_cmd)
    f = 0
    if formula.is_friendship_training(chara_info, command_id, partners):
        f = passive(st, M.EFFECT_FRIENDSHIP) + effect_sum(st, turn, M.EFFECT_FRIENDSHIP, base_cmd)
    return formula.bonus_params(chara_info, command_id, level, partners, s, s_sp, f,
                                limits(st, turn), card_levels)


def failure_down(full_state: dict, turn: int) -> int:
    return effect_sum(state(full_state), turn, M.EFFECT_FAILURE_DOWN)


def specialty_bonus(full_state: dict) -> int:
    """Specialty rate: the running pt's and the latest Jamboree's (§6.4 --
    placement is random, so the size of this is not capture-verified)."""
    st = state(full_state)
    return M.pt_effect(st["pt"], M.EFFECT_SPECIALTY) + passive(st, M.EFFECT_SPECIALTY)


def hint_rate(full_state: dict) -> int:
    st = state(full_state)
    return M.pt_effect(st["pt"], M.EFFECT_HINT_RATE) + passive(st, M.EFFECT_HINT_RATE)


# ============================================================ regions ===

def selection_type(full_state: dict, chara_info: dict) -> int:
    """The region_select_type the client is choosing for right now, or 0 when
    it is not on the selection screen: one selection opens the run and one
    follows each of the first two Jamborees."""
    if int(chara_info.get("playing_state") or 1) != 45:
        return 0
    kind = len(state(full_state)["results"]) + 1
    return kind if kind in set(M.region_select_turns().values()) else 0


def valid_regions(regions, select_type: int) -> bool:
    regions = [int(r) for r in regions or ()]
    if len(regions) != REGION_PICKS or len(set(regions)) != REGION_PICKS:
        return False
    return all(M.region_types().get(r) == select_type for r in regions)


def reduce_base_array(base: dict) -> list:
    return [{"feeling_id": f, "reduce_base_turn": int(base.get(f, base.get(str(f), 0)))}
            for f in FEELINGS]


def select_regions(full_state: dict, chara_info: dict, regions) -> None:
    """Commit a selection: the new split, and the gauge restarts at 7/7/7."""
    st = state(full_state)
    st["regions"] = [int(r) for r in regions]
    st["all_regions"] = st["all_regions"] + st["regions"]
    st["base"] = {str(f): v for f, v in split_base(st["regions"],
                                                    gauge_total(chara_info)).items()}
    st["gauge"] = {str(f): GAUGE_FULL for f in FEELINGS}


def expected_pt(st: dict, turn: int) -> int:
    """The next tasting's pt (§5.6)."""
    if turn > LAST_GAUGE_TURN or not st["regions"]:
        return 0
    gain = M.tasting_gain_pt().get(M.period_of(turn), 0)
    return gain * (100 + PT_STEP_PCT * min(int(st["tastings"]), PT_STEP_MAX)) // 100


# ============================================================= tasting ===

class Refused(Exception):
    pass


def taste(full_state: dict, chara_info: dict, used, turn: int) -> dict:
    """Cook one region's recipe (§5). Returns last_tasting_info; raises
    Refused when the request is not a legal tasting."""
    st = state(full_state)
    if not gauge_active(st, turn):
        raise Refused("no tasting before the first region or after turn 72")
    if st["last_tasting"].get("turn") == turn:
        raise Refused("one tasting per turn")
    used = [dict(u) for u in used or ()]
    if len(used) != TASTING_SIZE:
        raise Refused(f"a tasting uses {TASTING_SIZE} feelings, got {len(used)}")
    slots = [u for u in used if int(u.get("feeling_index") or 0)]
    secrets = len(used) - len(slots)
    if secrets > min(SECRETS_PER_TASTING, int(st["secrets"])):
        raise Refused("too many secret ingredients")
    indices = [int(u["feeling_index"]) for u in slots]
    if len(set(indices)) != len(indices):
        raise Refused("a held trick used twice")
    for u in slots:
        i = int(u["feeling_index"])
        if not (1 <= i <= len(st["tricks"])) or st["tricks"][i - 1] != int(u.get("feeling_id") or 0):
            raise Refused(f"slot {i} does not hold feeling {u.get('feeling_id')}")
    want = {f: 0 for f in FEELINGS}
    for u in used:
        want[int(u.get("feeling_id") or 0)] = want.get(int(u.get("feeling_id") or 0), 0) + 1
    region = next((r for r in st["regions"]
                   if all(M.region_feelings().get(r, {}).get(f, 0) == want.get(f, 0)
                          for f in FEELINGS)), None)
    if region is None:
        raise Refused(f"{want} is no selected region's recipe")

    # Spend.
    drop = set(i - 1 for i in indices)
    st["tricks"] = [f for i, f in enumerate(st["tricks"]) if i not in drop]
    st["secrets"] = int(st["secrets"]) - secrets

    # Effects, the region's upgraded by the pt held BEFORE this tasting.
    pt_before = int(st["pt"])
    period = M.period_of(turn)
    effects = []
    for row in M.basic_effects().get(period, ()):
        if _conditions_met(row, chara_info):
            effects.append((M.CATEGORY_BASIC, row, int(row["effect_value"])))
    for row in M.region_effects().get(region, ()):
        if _conditions_met(row, chara_info):
            value = int(row["effect_value"]) + M.region_effect_bonus(
                region, int(row["effect_type"]), pt_before)
            effects.append((M.CATEGORY_REGION, row, value))
    lasting, not_up_bond = [], []
    for cat, row, value in effects:
        etype = int(row["effect_type"])
        if etype in _INSTANT:
            _apply_instant(full_state, chara_info, etype, row, value, turn, not_up_bond)
            continue
        lasting.append([cat, int(row["id"]), value])
    st["active"] = {"turn": turn, "effects": lasting}

    st["pt"] = pt_before + expected_pt(st, turn)
    st["tastings"] = int(st["tastings"]) + 1
    held = {f: 0 for f in FEELINGS}
    for u in slots:
        held[int(u["feeling_id"])] += 1
    info = {"feeling_id_1_num": held[1], "feeling_id_2_num": held[2],
            "feeling_id_3_num": held[3], "special_feeling_num": secrets,
            "region_id": region}
    st["last_tasting"] = {"turn": turn, "info": info}
    if not_up_bond:
        flag(st, "not_up_bond", sorted(set(not_up_bond)))
    log.info("ramen: tasting on turn %s -> region %s, pt %s -> %s, %s lasting effects",
             turn, region, pt_before, st["pt"], len(lasting))
    return info


# Effects that act once, at the tasting, and are not listed as active (§5.4).
_INSTANT = frozenset({M.EFFECT_PARAM, M.EFFECT_BOND, M.EFFECT_ALL_TIPS,
                      M.EFFECT_TYPE_HINTS, M.EFFECT_EXTRA_CARD, M.EFFECT_EXTRA_CARDS})
_URAF_INSTANT = frozenset({M.EFFECT_PARAM, M.EFFECT_EXTRA_CARDS})


def _apply_instant(full_state, chara_info, etype, row, value, turn, not_up_bond) -> None:
    st = state(full_state)
    conds = dict(M.conditions(row))
    if etype == M.EFFECT_PARAM:
        target = conds.get(M.COND_PARAM)
        if target == 10:
            event_engine._apply_effects(chara_info, [{"type": "energy", "value": f"+{value}"}])
        elif target == 20:
            event_engine._apply_effects(chara_info, [{"type": "mood", "value": f"+{value}"}])
    elif etype == M.EFFECT_BOND:
        by_pos = formula.deck(chara_info)
        for e in chara_info.get("evaluation_info_array") or ():
            if int(e.get("target_id") or 0) in by_pos:
                if int(e.get("evaluation") or 0) >= 100:
                    not_up_bond.append(formula.card_meta(by_pos[e["target_id"]])[3])
                e["evaluation"] = min(100, int(e.get("evaluation") or 0) + value)
    elif etype == M.EFFECT_ALL_TIPS:
        flag_turn(st, "all_tips", turn)
    elif etype == M.EFFECT_TYPE_HINTS:
        card_cmd = conds.get(M.COND_CARD_TYPE, 0)
        pool = [sid for sid in formula.deck(chara_info).values()
                if formula.card_meta(sid)[0] == 1 and formula.card_meta(sid)[1] == card_cmd]
        rng = random.Random(f"ramen:typehint:{CE.career_salt(full_state)}:{turn}:{row['id']}")
        for _ in range(int(value)):
            if pool:
                grant_card_hint(chara_info, rng.choice(pool), rng)
    elif etype == M.EFFECT_EXTRA_CARD:
        place_extra_card(full_state, chara_info, conds.get(M.COND_COMMAND, 0), turn)


def flag_turn(st: dict, name: str, turn: int) -> None:
    """A per-turn mark (unlike flag(), not consumed by the response)."""
    st["marks"][name] = turn


def flagged_turn(st: dict, name: str, turn: int) -> bool:
    return st["marks"].get(name) == turn


def card_hint_effects(chara_info: dict, support_card_id: int, rng) -> list:
    """One of a card's hints as effects, exactly as its '!' would pay it: a
    skill from its own pool at 1 + its hint-level effect, or its stat variant."""
    learned = {s.get("skill_id") for s in chara_info.get("skill_array") or ()}
    groups = event_engine.card_hint_groups(support_card_id)
    pool = [g for g in groups if g[0] == "stat"
            or event_engine.card_hint_open(chara_info, g[1], learned)]
    if not pool:
        return []
    kind, value = rng.choice(pool)
    if kind == "stat":
        return [dict(e) for e in value]
    level = 1 + int(round(formula.card_effect(support_card_id, 17,
                                              formula.max_level(support_card_id))))
    return [{"type": "skill_hint", "skill_id": value, "value": f"+{level}"}]


def grant_card_hint(chara_info: dict, support_card_id: int, rng) -> None:
    event_engine._apply_effects(chara_info, card_hint_effects(chara_info, support_card_id, rng))


def place_extra_card(full_state: dict, chara_info: dict, command_id: int, turn: int,
                     rng=None) -> None:
    """A random normal deck card not already there joins this facility for the
    turn (§5.5); it counts as a card in every formula."""
    st = state(full_state)
    extra = st["extra_partners"]
    if extra.get("turn") != turn:
        extra.update({"turn": turn, "map": {}})
    here = set(_placed_positions(full_state, chara_info, command_id))
    here |= set(extra["map"].get(str(command_id)) or ())
    pool = [pos for pos, sid in formula.deck(chara_info).items()
            if formula.is_normal_card(sid) and pos not in here]
    if not pool:
        return
    rng = rng or random.Random(f"ramen:extra:{CE.career_salt(full_state)}:{turn}:{command_id}")
    extra["map"].setdefault(str(command_id), []).append(rng.choice(pool))


def _placed_positions(full_state: dict, chara_info: dict, command_id: int) -> list:
    from ...handlers import single_mode_team as smt
    home = ((full_state.get(smt.STATE_KEY) or {}).get("data") or {}).get("home_info") or {}
    for c in home.get("command_info_array") or ():
        if formula.SUMMER_TO_BASE.get(c.get("command_id"), c.get("command_id")) == command_id:
            return [p for p in c.get("training_partner_array") or () if p in formula.deck(chara_info)]
    return []


def extra_partners(full_state: dict, turn: int) -> dict:
    extra = state(full_state)["extra_partners"]
    if extra.get("turn") != turn:
        return {}
    return {int(k): list(v) for k, v in (extra.get("map") or {}).items()}


# =========================================================== jamboree ===

def result_for(check_point_type: int, pt: int) -> int:
    row = M.check_points().get(check_point_type) or {}
    great = int(row.get("great_success_pt") or 0)
    if great and pt >= great:
        return RESULT_SUPER
    if pt >= int(row.get("success_pt") or 0):
        return RESULT_GREAT
    return RESULT_OK


def commit_check_point(full_state: dict, chara_info: dict, check_point_type: int,
                       twinkle) -> tuple:
    """Hold the Jamboree: record its result, reset this period's pt, and
    return (result_state, the result Event)."""
    st = state(full_state)
    result = result_for(check_point_type, int(st["pt"]))
    st["results"] = [r for r in st["results"]
                     if r["check_point_type"] != check_point_type] + [
        {"check_point_type": check_point_type, "result_state": result}]
    st["twinkle"] = st["twinkle"] + [int(t) for t in twinkle or ()]
    st["pt"], st["tastings"] = 0, 0
    event_id = RESULT_EVENTS[check_point_type][result]
    sort_id = goal_sort_id(chara_info, M.check_points()[check_point_type]["turn"])
    ev = CE.Event(
        event_id=event_id, story_id=RESULT_STORIES[event_id], play_timing=RESULT_TIMING,
        choices=[CE.Choice(effects=jamboree_rewards(full_state, chara_info,
                                                    check_point_type, result))],
        chara_id=0, show_clear=RESULT_SHOW_CLEAR, show_clear_sort_id=sort_id,
        once_key=f"ramen:result:{check_point_type}", priority=CE.PRIO_FRONT,
        resolver="ramen_result", source="ramen",
        payload={"check_point_type": check_point_type, "result_state": result})
    log.info("ramen: Jamboree %s -> result %s", check_point_type, result)
    return result, ev


def jamboree_rewards(full_state: dict, chara_info: dict, check_point_type: int,
                     result: int) -> list:
    """The result event's payout (§7.3) -- everything but the facility levels
    and the trick reset, which its resolver does."""
    st = state(full_state)
    stats, sp, fans, _levels = JAMBOREE_REWARD[(check_point_type, result)]
    energy = JAMBOREE_ENERGY[result] + M.feeling_bonus(len(st["tricks"]))
    effects = [{"type": "all_stats", "value": f"+{stats}"},
               {"type": "skill_point", "value": f"+{sp}"},
               {"type": "energy", "value": f"+{energy}"},
               {"type": "fans", "value": f"+{fans}"}]
    for skill_id, level in JAMBOREE_HINTS.get((check_point_type, result), ()):
        effects.append({"type": "skill_hint", "skill_id": skill_id, "value": f"+{level}"})
    if check_point_type == 3:
        kind = int(st["uraf"].get("type") or 0)
        row = M.finals_skills().get(kind)
        if row:
            col = {RESULT_OK: "skill_level_normal", RESULT_GREAT: "skill_level_success",
                   RESULT_SUPER: "skill_level_great_success"}[result]
            effects.append({"type": "skill_hint", "skill_id": int(row["skill_id"]),
                            "value": f"+{int(row[col])}"})
    return effects


def goal_sort_id(chara_info: dict, turn: int) -> int:
    """The route goal due on this turn, else 1 -- the result events' and 214026's
    show_clear_sort_id (every captured value matches this, 62 careers)."""
    try:
        from ... import master_data
        ids = tuple(chara_info.get("route_race_id_array") or ())
        if ids:
            marks = ",".join("?" * len(ids))
            row = master_data.query_one(
                f"SELECT sort_id FROM single_mode_route_race WHERE id IN ({marks}) "
                f"AND turn=? LIMIT 1", ids + (int(turn),))
            if row:
                return int(row["sort_id"])
    except Exception:                                  # noqa: BLE001
        log.exception("ramen: goal sort id lookup failed")
    return 1


def check_point_info(st: dict, current: int = 0) -> list:
    """Every Jamboree held so far; the one just held first, as the real
    check_point response orders them (load lists them in order)."""
    rows = sorted(st["results"], key=lambda r: r["check_point_type"])
    if current:
        rows = ([r for r in rows if r["check_point_type"] == current]
                + [r for r in rows if r["check_point_type"] != current])
    return [{"check_point_type": r["check_point_type"], "result_state": r["result_state"]}
            for r in rows]


# ============================================================= finals ===

def uraf_rows(select_type: int, deck_ok: bool = True) -> list:
    rows = [r for r in M.finals_effects()
            if int(r["select_type"]) in (0, int(select_type))]
    if not deck_ok:
        rows = [r for r in rows if all(ct != M.COND_DECK_TYPES for ct, _v in M.conditions(r))]
    return rows


def apply_uraf(full_state: dict, chara_info: dict, turn: int) -> list:
    """The Ultimate Ramen's turn (§10): +20 energy, +1 motivation, a copy of
    each support card in a random training, and the turn's lasting effects.
    Returns the not_up status codes the instant part hit."""
    st = state(full_state)
    kind = int(st["uraf"].get("type") or 0)
    deck_ok = deck_type_count(chara_info) >= 4
    st["uraf"].update({"turn": turn, "deck_ok": deck_ok})
    not_up = []
    for row in uraf_rows(kind, deck_ok):
        etype = int(row["effect_type"])
        value = int(row["effect_value"])
        target = dict(M.conditions(row)).get(M.COND_PARAM)
        if etype == M.EFFECT_PARAM and target == 10:
            if int(chara_info.get("vital") or 0) >= int(chara_info.get("max_vital") or 100):
                not_up.append(6)
            event_engine._apply_effects(chara_info, [{"type": "energy", "value": f"+{value}"}])
        elif etype == M.EFFECT_PARAM and target == 20:
            if int(chara_info.get("motivation") or 3) >= 5:
                not_up.append(20)
            event_engine._apply_effects(chara_info, [{"type": "mood", "value": f"+{value}"}])
        elif etype == M.EFFECT_EXTRA_CARDS:
            rng = random.Random(f"ramen:uraf:{CE.career_salt(full_state)}:{turn}")
            positions = list(formula.deck(chara_info))[:value]
            for pos in positions:
                cmd = rng.choice(formula.TRAINING_COMMANDS)
                extra = st["extra_partners"]
                if extra.get("turn") != turn:
                    extra.update({"turn": turn, "map": {}})
                if pos not in _placed_positions(full_state, chara_info, cmd):
                    extra["map"].setdefault(str(cmd), []).append(pos)
    return sorted(set(not_up))


def uraf_active(st: dict, turn: int) -> bool:
    return bool(st["uraf"].get("type")) and st["uraf"].get("turn") == turn


# ============================================================ envelope ===

# Responses that leave the client on its training screen get the per-turn
# arrays; everything mid-chain gets null in their place and the client keeps
# what it has (§1.1 -- nulls are significant).
_FULL_ENDPOINTS = frozenset({"tasting", "uraf_effect_apply", "ramen_live", "load",
                             "gain_skills", "start"})


def career_over(chara_info: dict) -> bool:
    """chara_info.state 3: the last finals race has been run. The real server
    serves everything from that race_out to the last gain_skills with
    playing_state 5 and the mid-chain (null) data set -- never the training
    screen again (62/62 careers)."""
    return int((chara_info or {}).get("state") or 0) == 3


def _is_full(endpoint: str, data: dict) -> bool:
    call = endpoint.rsplit("/", 1)[-1]
    if career_over(data.get("chara_info")) and call != "load":
        return False
    if call in _FULL_ENDPOINTS:
        return True
    if call not in ("check_event", "exec_command", "race_out"):
        return False
    ci = data.get("chara_info") or {}
    return (not data.get("unchecked_event_array")
            and int(ci.get("playing_state") or 1) == 1)


def evaluation_array(full_state: dict, chara_info: dict) -> list:
    """ramen_data_set.evaluation_info_array: the deck's normal charas by
    position and the NPC charas by their own id, once 214002 has run."""
    st = state(full_state)
    if not st["npcs"]:
        return []
    out = []
    for pos, sid in sorted(formula.deck(chara_info).items()):
        chara = formula.card_meta(sid)[3]
        if chara and chara < 9000:
            out.append({"target_id": pos, "chara_id": chara})
    out += [{"target_id": c, "chara_id": c} for c in sorted(st["npcs"])]
    return out


def ramen_data_set(full_state: dict, chara_info: dict, home_info: dict,
                   endpoint: str, full: bool, start: bool = False) -> dict:
    st = state(full_state)
    turn = served_turn(full_state, chara_info)
    active = gauge_active(st, turn)
    tricks = list(st["tricks"])
    ds = {
        "command_info_array": None,
        "evaluation_info_array": [] if start else evaluation_array(full_state, chara_info),
        "feeling_reduce_turn_info_array": None,
        "feeling_turn_info_array": (
            [] if start or turn > LAST_GAUGE_TURN else
            [{"feeling_id": f, "remain_turn": int(st["gauge"].get(str(f), 0)) if st["regions"] else 0}
             for f in FEELINGS]),
        "feeling_info_array": (
            [] if start or turn > LAST_GAUGE_TURN else
            [{"feeling_index": i + 1, "feeling_id": tricks[i] if i < len(tricks) else 0}
             for i in range(TRICK_SLOTS)]),
        "special_feeling_num": int(st["secrets"]),
        "active_effect_array": None,
        "uraf_effect_info": None,
        "command_feeling_info_array": None,
        "training_exec_info_array": (training_exec_info(st)
                                     if int(chara_info.get("playing_state") or 1) == 45 else None),
        "reduce_base_turn_info_array": None,
        "all_selected_region_id_array": (list(st["all_regions"])
                                         if turn > LAST_GAUGE_TURN and st["all_regions"] else None),
        "not_up_parameter_info": {"not_gain_special_feeling": bool(flag(st, "not_gain_secret"))},
    }
    if not full:
        return ds
    commands = [c for c in (home_info or {}).get("command_info_array") or ()
                if c.get("command_type") == 1]
    preview = st["preview"]
    ds["command_info_array"] = [
        {"command_type": 1, "command_id": c["command_id"],
         "params_inc_dec_info_array": [] if start else list(
             preview["bonus"].get(str(c["command_id"])) or [])}
        for c in commands]
    ds["active_effect_array"] = [
        {"effect_category": cat, "effect_id": eid, "effect_value": value}
        for cat, eid, value in active_effects(st, turn)]
    ds["uraf_effect_info"] = {"uraf_effect_type": int(st["uraf"].get("type") or 0),
                              "uraf_effect_state": 1 if uraf_active(st, turn) else 0}
    if active and not start:
        ds["feeling_reduce_turn_info_array"] = [
            {"command_type": 1, "command_id": c["command_id"],
             "feeling_turn_array": [{"feeling_id": f, "turn": int(v)} for f, v in sorted(
                 (int(k), v) for k, v in (preview["reduce"].get(str(c["command_id"])) or {}).items())]}
            for c in commands]
        camp = any(c["command_id"] in formula.SUMMER_TO_BASE for c in commands)
        rows = []
        if camp:
            rows += [{"command_type": 1, "command_id": b, "feeling_id": 0}
                     for b in sorted(formula.TRAINING_COMMANDS)]
        rows += [{"command_type": 1,
                  "command_id": formula.BASE_TO_SUMMER[b] if camp else b,
                  "feeling_id": bubble(st, b)}
                 for b in sorted(formula.TRAINING_COMMANDS)]
        ds["command_feeling_info_array"] = rows
    else:
        ds["feeling_reduce_turn_info_array"] = []
        ds["command_feeling_info_array"] = []
    return ds


def refresh_preview(full_state: dict, chara_info: dict, home_info: dict,
                    card_levels=None) -> bool:
    """Recompute this turn's scenario overlay from the facilities the client is
    about to see, and remember it -- exec_command pays exactly what it said
    (see Ramen.training_award_bonus / train_gauge). True when a new random roll
    was made and the state needs saving."""
    st = state(full_state)
    turn = served_turn(full_state, chara_info)
    rolled = roll_bubbles(full_state, chara_info, turn) if gauge_active(st, turn) else False
    bonus, reduce, placed = {}, {}, {}
    for c in (home_info or {}).get("command_info_array") or ():
        if c.get("command_type") != 1:
            continue
        cmd = int(c["command_id"])
        partners = list(c.get("training_partner_array") or ())
        placed[str(cmd)] = partners
        level = int(c.get("level") or 1)
        if not c.get("is_enable", 1):
            bonus[str(cmd)] = []
            reduce[str(cmd)] = {str(f): 0 for f in FEELINGS}
            continue
        bonus[str(cmd)] = facility_bonus(full_state, chara_info, cmd, level, partners,
                                         card_levels, turn)
        if gauge_active(st, turn):
            reduce[str(cmd)] = {str(f): v for f, v in facility_reduce(
                st, chara_info, cmd, partners, turn).items()}
    st["preview"] = {"turn": turn, "bonus": bonus, "reduce": reduce, "partners": placed}
    return rolled


# ====================================================== career plumbing ===

def _smt():
    """handlers.single_mode_team, imported on use -- a top-level import would
    close the cycle through the scenario registry."""
    from ...handlers import single_mode_team
    return single_mode_team


def recruit_npcs(full_state: dict, chara_info: dict) -> list:
    """The six NPC charas who train alongside the run from 214002 on (§12):
    every link chara the deck and the trainee do not already bring, topped up
    with random charas (62/62 careers: always six). They stand in facilities
    as bodies and nothing else -- Grand Live's uncarded supporters, exactly."""
    st = state(full_state)
    if st["npcs"]:
        return st["npcs"]
    from ... import master_data
    taken = linked_charas(chara_info)
    npcs = [c for c in LINK_NPC_CHARAS if c not in taken]
    rng = random.Random(f"ramen:npcs:{CE.career_salt(full_state)}")
    pool = sorted(c for c in master_data.drawable_charas()
                  if 1000 <= int(c) < 2000 and c not in taken and c not in npcs)
    rng.shuffle(pool)
    npcs += pool[:max(0, NPC_CHARA_COUNT - len(npcs))]
    st["npcs"] = npcs
    arr = chara_info.setdefault("evaluation_info_array", [])
    have = {e.get("target_id") for e in arr if isinstance(e, dict)}
    for chara in npcs:
        if chara not in have:
            arr.append({"target_id": chara, "training_partner_id": chara,
                        "evaluation": 0, "is_outing": 0, "story_step": 0,
                        "is_appear": 1, "group_outing_info_array": []})
    log.info("ramen: NPC charas %s join", npcs)
    return npcs


def raise_all_facilities(full_state: dict, chara_info: dict) -> None:
    """+1 to every facility, max 5 (§8): a Jamboree at 大盛況 or better."""
    smt = _smt()
    career = (full_state.get(smt.STATE_KEY) or {}).get("data") or {}
    levels = smt._facility_levels(career)
    tla = chara_info.setdefault("training_level_info_array", [])
    for cmd in formula.TRAINING_COMMANDS:
        key = str(cmd)
        levels[key] = min(5, int(levels.get(key, 1)) + 1)
        entry = next((e for e in tla if e.get("command_id") == cmd), None)
        if entry:
            entry["level"] = levels[key]
        else:
            tla.append({"command_id": cmd, "level": levels[key]})


def refresh_home(full_state: dict, chara_info: dict) -> None:
    """Rebuild the training screen off the state a scenario action just moved
    (a tasting's bond and card copies, a Jamboree's facility levels, the
    Ultimate Ramen's copies). The placement is seeded by turn, so this re-draws
    the same layout rather than re-rolling it."""
    smt = _smt()
    career = full_state.get(smt.STATE_KEY)
    if not isinstance(career, dict):
        return
    home = career["data"].get("home_info")
    if not isinstance(home, dict):
        return
    smt._refresh_command_info(
        chara_info, home, turn=chara_info.get("turn", 1),
        unlocked_npcs=[n[0] for n in full_state.get(
            smt.single_mode_events.UNLOCKED_NPCS_KEY, [])],
        facility_levels=smt._facility_levels(career["data"]),
        race_history=career["data"].get("race_history", []),
        training_bonus=smt._training_bonus(full_state, chara_info),
        friendship_bonus=smt._friendship_bonus(full_state, chara_info),
        specialty_bonus=smt._specialty_bonus(full_state, chara_info),
        support_card_levels=smt._support_card_levels(full_state),
        friendship_stacks=smt._friendship_stacks(full_state),
        full_state=full_state)
