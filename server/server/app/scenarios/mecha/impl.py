"""RUN! MECHA UMAMUSUME (scenario 9, JP only) -- the mechanics.

docs/JP_MECHA_SCENARIO.md is the spec this implements, section for section; it
records where every rule and number came from (seven real careers, the
single_mode_09_* master tables, the JP client dump). This module holds the
career state and the rules that move it:

    research levels, limits, progress     §3   (levels, add_research, progress_rate)
    research points per training          §4   (formula.research_points, refresh_preview)
    the scenario line                     §5   (formula.scenario_line, refresh_preview)
    mecha gears                           §6   (gear_rolls) -- the RATE is not exact
    overdrive and its gauge               §7   (add_energy, activate_overdrive)
    tuning, mecha EN, the UGE             §8   (set_chips, commit_uge, uge_rewards)
    research members                      §9   (recruit_members)
    link characters                       §10  (link_sum)

and builds the mecha_data_set every career response carries (data_set).
Where the captures do not settle a rule it says so where it is applied.
"""

from __future__ import annotations

import copy
import logging
import random

from ... import career_events as CE
from ..ramen import impl as RI
from . import formula, master as M

log = logging.getLogger("uma-server")

SCENARIO_ID = 9
STATE_KEY = "mecha"

LIMIT_START, LIMIT_STEP = 200, 100      # research limit: 200, +100 per UGE (§3)
GAUGE_MAX = 3                           # max_energy_num
TUNING_TURN = 3                         # TUNING_COMMAND_ENABLE_TURN
EN_FIRST = 5                            # 1.3 チューニング試験 (§8.4)
EN_PER_UGE = 6                          # minus the grade drop (§8.4, 40/40)
RACE_WATCH_RESEARCH = 7                 # 400009101: +7 to all five (§11.1)
SUMMER_TURNS = frozenset({37, 38, 39, 40, 61, 62, 63, 64})
FINALS_FIRST_TURN = 73
RESEARCH_MEMBERS = 11                   # is_research_member 1 after 209026 (§9)
HEAD_HINTS_LATE_UGES = 4                # UGEs done before 209084 replaces 209040 (dress 200803)

# MECHA GEARS (§6) -- NOT EXACT. No master table holds the odds; these are the
# measured rates: 48.6 % of non-friendship, non-overdrive facilities without a
# link card (U 139/288, career 2 161/329, career 3 13/30), 59.1 % with Biwa +
# Taishin + Gimlet (career 1, 169/286) -- about +3.5 points per link character
# carrying link effect 14 ("more gears"). The user exempted the gear frequency
# from the 1:1 rule (2026-10-03).
GEAR_BASE = 0.486
GEAR_PER_LINK = 0.035

# UGE rewards (§8.5): all five stats / SP at A or S on UGE k = 5 + 5k / 15 + 10k;
# B is one UGE lower (captured for UGE 1-2; UGE 3-5 at B is that pattern,
# INFERRED). Facilities +1 at UGE 1/3/5 with A or S (5 careers x 3 UGEs).
FACILITY_UP_UGES = frozenset({1, 3, 5})
SKILL_ZENSHIN = 200511         # 全身全霊 (group 20051 rarity 2)
SKILL_YUME = 210342            # 夢の再生方法 (group 21034 rarity 1)
SKILL_SUEASHI = 200512         # 末脚, 1.4's hint at level 3
SKILL_KESHIKI = 210341         # もう少しだけ、いい景色, the ending's hint


# ================================================================ state ===

def _blank() -> dict:
    return {
        "started": False,
        "levels": {str(s): 1 for s in M.RESEARCH_ORDER}, "limit": LIMIT_START,
        "energy": 0, "remain": 0, "od_turn": 0, "od_count": 0, "burst": 0,
        "chips": {str(c): 0 for chips in M.BOARD_CHIPS.values() for c in chips},
        "tp": 0, "results": [], "new_result": 0,
        "members": [], "roster": False,
        "gears": {"turn": 0, "map": {}},
        "preview": {"turn": 0, "od": False, "rows": {}},
        "hold_turn": 0, "flags": {}, "due": [],
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


def flag(st: dict, name: str, value=None):
    """A one-shot response flag: set with a value, read-and-clear without."""
    if value is not None:
        st["flags"][name] = value
        return value
    return st["flags"].pop(name, None)


def rng_for(full_state: dict, *parts) -> random.Random:
    return random.Random(":".join(["mecha", str(CE.career_salt(full_state))] + [str(p) for p in parts]))


def live_chara(full_state: dict) -> dict:
    from ...handlers import single_mode_team as smt
    return ((full_state.get(smt.STATE_KEY) or {}).get("data") or {}).get("chara_info") or {}


# ============================================================== links ===

def linked(chara_info: dict) -> set:
    """Every chara the deck or the trainee brings (§10: a link counts for
    either)."""
    return RI.linked_charas(chara_info)


def link_sum(chara_info: dict, effect_type: int, value_1: int | None = None) -> int:
    total = 0
    for chara in linked(chara_info):
        for t, v1, v2 in M.link_effects().get(chara, ()):
            if t == effect_type and (value_1 is None or v1 == value_1):
                total += v2
    return total


def link_en(chara_info: dict) -> int:
    return min(M.LINK_EN_CAP, link_sum(chara_info, M.LINK_EN))


def gear_links(chara_info: dict) -> int:
    return sum(1 for chara in linked(chara_info)
               if any(t == M.LINK_GEARS for t, _v1, _v2 in M.link_effects().get(chara, ())))


def ensure_started(st: dict, chara_info: dict) -> bool:
    """Career-start link effects (§3, §7.1): research levels max(1, the +20s),
    the gauge's +3 energies as whole charges. True when it ran."""
    if st["started"] or not isinstance(chara_info, dict) or not chara_info.get("support_card_array"):
        return False
    st["started"] = True
    start = max(1, link_sum(chara_info, M.LINK_START, 1))
    st["levels"] = {str(s): start for s in M.RESEARCH_ORDER}
    add_energy(st, link_sum(chara_info, M.LINK_START, 2), at_start=True)
    log.info("mecha: start levels %s, gauge %s/%s", start, st["energy"], st["remain"])
    return True


# ============================================================ research ===

def level(st: dict, status: int) -> int:
    return int(st["levels"].get(str(status), 1))


def levels(st: dict) -> dict:
    return {s: level(st, s) for s in M.RESEARCH_ORDER}


def total_research(st: dict) -> int:
    return sum(levels(st).values())


def uges_done(st: dict) -> int:
    return len(st["results"])


def result_of(st: dict, schedule_id: int) -> int:
    return next((int(r["result_type"]) for r in st["results"]
                 if int(r["schedule_id"]) == int(schedule_id)), 0)


def progress_rate(st: dict, turn: int) -> int:
    """floor(the five levels / the coming UGE's target x 100); 0 once the last
    UGE is behind the served turn (§3). It re-bases on the turn after a UGE."""
    for _sid, (t, target, _stock, _dress) in sorted(M.schedules().items()):
        if int(turn) <= t:
            return total_research(st) * 100 // max(1, target)
    return 0


def add_research(st: dict, gains) -> list:
    """Raise the levels by [(status, n)], each capped at the limit. Returns the
    statuses that were ALREADY at the limit -- not_up_macha_parameter_info's
    status_type_array (§2.3: 427/427 replies)."""
    capped = []
    for status, n in gains:
        have = level(st, status)
        if have >= int(st["limit"]):
            capped.append(int(status))
            continue
        st["levels"][str(status)] = min(int(st["limit"]), have + max(0, int(n)))
    return sorted(capped)


# ============================================================ overdrive ===

def charges_max() -> int:
    return max((row[2] for row in M.schedules().values()), default=2)


def gauge_full(st: dict) -> bool:
    return int(st["remain"]) >= charges_max()


def add_energy(st: dict, n: int, at_start: bool = False) -> bool:
    """+n gauge energy: three make a charge (§7.1). Nothing while both charges
    are held or Super Overdrive is on. True when anything was lost to a full
    gauge (overdrive_num_max_flag)."""
    lost = False
    for _ in range(max(0, int(n))):
        if gauge_full(st) or (int(st["burst"]) and not at_start):
            lost = True
            continue
        st["energy"] = int(st["energy"]) + 1
        if st["energy"] >= GAUGE_MAX:
            st["energy"] = 0
            st["remain"] = int(st["remain"]) + 1
    return lost


def overdrive_on(st: dict, turn: int) -> bool:
    return bool(st["od_turn"]) and int(st["od_turn"]) == int(turn)


def board_totals(st: dict) -> dict:
    return {b: sum(int(st["chips"].get(str(c), 0)) for c in chips) for b, chips in M.BOARD_CHIPS.items()}


def core_effects(st: dict) -> list:
    return M.core_effects(board_totals(st))


def effect_sum(st: dict, effect_type: int, value_1: int | None = None) -> int:
    return sum(v2 for t, v1, v2, _v3, _v4 in core_effects(st)
               if t == effect_type and (value_1 is None or v1 == value_1))


def has_effect(st: dict, effect_type: int) -> bool:
    return any(t == effect_type for t, *_ in core_effects(st))


def can_overdrive(st: dict, turn: int) -> str:
    """'' when an overdrive may be used now, else why not (§7.2, §7.6: with
    Super Overdrive on it is free -- with 0 charges INFERRED)."""
    if overdrive_on(st, turn):
        return "already on this turn"
    if int(st["remain"]) < 1 and not int(st["burst"]):
        return "no charge"
    return ""


def activate_overdrive(st: dict, chara_info: dict, turn: int) -> list:
    """The overdrive call (§7.2-§7.3): a charge (none under Super Overdrive),
    the count, and Leg 12's energy +15 / motivation +1. Returns the not_up
    codes the instant part hit."""
    if not int(st["burst"]):
        st["remain"] = int(st["remain"]) - 1
    st["od_turn"] = int(turn)
    st["od_count"] = int(st["od_count"]) + 1
    not_up = []
    for t, v1, v2, _v3, _v4 in core_effects(st):
        if t != M.EFF_INSTANT:
            continue
        if v1 == 10:
            vital, cap = int(chara_info.get("vital") or 0), int(chara_info.get("max_vital") or 100)
            if vital >= cap:
                not_up.append(6)
            chara_info["vital"] = max(vital, min(cap, vital + v2))
        elif v1 == 20:
            mood = int(chara_info.get("motivation") or 3)
            if mood >= 5:
                not_up.append(20)
            chara_info["motivation"] = min(5, mood + v2)
    log.info("mecha: overdrive on turn %s (%s charges left, burst %s)", turn, st["remain"], st["burst"])
    return sorted(set(not_up))


def head_research_pct(st: dict, turn: int) -> int:
    return effect_sum(st, M.EFF_RESEARCH) if overdrive_on(st, turn) else 0


# ================================================================ gears ===

def gear_rolls(full_state: dict, chara_info: dict, turn: int) -> dict:
    """{base command: rolled gear} for this turn, rolled once (§6 -- the rate
    is measured, NOT EXACT). Friendship trainings and an overdrive with the
    Head core at 3+ override it at preview time."""
    st = state(full_state)
    g = st["gears"]
    if g.get("turn") != int(turn):
        rng = rng_for(full_state, "gears", turn)
        rate = min(1.0, GEAR_BASE + GEAR_PER_LINK * gear_links(chara_info))
        st["gears"] = {"turn": int(turn),
                       "map": {str(c): rng.random() < rate for c in formula.TRAINING_COMMANDS}}
    return {int(k): bool(v) for k, v in st["gears"]["map"].items()}


# ====================================================== research members ===

def recruit_members(full_state: dict, chara_info: dict) -> list:
    """209026's roster (§9): the deck's normal cards are research members; the
    link charas the deck and the trainee do not bring join as NPC members,
    topped up with random charas to eleven members. The filler draw is NOT
    EXACT -- any chara outside the deck and the trainee fits all captured
    draws -- and uses Ramen's drawable pool."""
    st = state(full_state)
    if st["roster"]:
        return list(st["members"])
    from ... import master_data
    taken = linked(chara_info)
    normal = [p for p, sid in formula.RF.deck(chara_info).items() if formula.RF.is_normal_card(sid)]
    npcs = [c for c in M.LINK_CHARAS if c not in taken]
    rng = rng_for(full_state, "members")
    pool = sorted(c for c in master_data.drawable_charas()
                  if 1000 <= int(c) < 2000 and c not in taken and c not in npcs)
    rng.shuffle(pool)
    npcs += pool[:max(0, RESEARCH_MEMBERS - len(normal) - len(npcs))]
    st["members"] = sorted(npcs)
    st["roster"] = True
    arr = chara_info.setdefault("evaluation_info_array", [])
    have = {e.get("target_id") for e in arr if isinstance(e, dict)}
    for chara in st["members"]:
        if chara not in have:
            arr.append({"target_id": chara, "training_partner_id": chara, "evaluation": 0,
                        "is_outing": 0, "story_step": 0, "is_appear": 1,
                        "group_outing_info_array": []})
    log.info("mecha: research members %s join (deck %s)", st["members"], normal)
    return list(st["members"])


def is_member(st: dict, chara_info: dict, partner: int) -> bool:
    """is_research_member: a deck NORMAL card (once the roster is set) or an
    NPC member. The friend card and the 1xx NPCs never are."""
    if not st["roster"]:
        return False
    if int(partner) >= formula.NPC_MIN:
        return int(partner) in st["members"]
    sid = formula.RF.deck(chara_info).get(int(partner))
    return bool(sid) and formula.RF.is_normal_card(sid)


def point_members(st: dict, partners) -> int:
    """Bodies that raise research points (§4.1): every deck card, the friend
    card included, and the NPC research members."""
    return sum(1 for p in partners or ()
               if int(p) < formula.DECK_MAX or int(p) in st["members"])


# ============================================================ previews ===

def refresh_preview(full_state: dict, chara_info: dict, commands, card_levels=None,
                    turn: int | None = None) -> bool:
    """Recompute this turn's scenario overlay from the facilities about to be
    served, and remember it: exec_command pays exactly what it said. True when
    a random roll was made (persist)."""
    from ...handlers import conditions
    st = state(full_state)
    turn = int(turn or turn_of(chara_info))
    before_gear = st["gears"].get("turn")
    rolls = gear_rolls(full_state, chara_info, turn)
    od = overdrive_on(st, turn)
    effects = core_effects(st) if od else []
    all_gears = od and any(t == M.EFF_ALL_GEARS for t, *_ in effects)
    lvls = levels(st)
    lb_extra = link_sum(chara_info, M.LINK_LEARNING)
    chips = {int(k): int(v) for k, v in st["chips"].items()}
    head = head_research_pct(st, turn)
    rows = {}
    for c in commands or ():
        if c.get("command_type") != 1:
            continue
        cmd = int(formula.SERVER_ID.get(int(c["command_id"]), int(c["command_id"])))
        base = formula.base_of(cmd)
        partners = list(c.get("training_partner_array") or ())
        lv = int(c.get("level") or 1)
        p = formula.parts(chara_info, cmd, lv, partners, card_levels)
        friend = p["nfriend"] > 0
        gear = bool(friend or all_gears or rolls.get(base))
        home_energy = next((int(x.get("value") or 0) for x in c.get("params_inc_dec_info_array") or ()
                            if int(x.get("target_type") or 0) == formula.TARGET_ENERGY), 0)
        members = sum(1 for q in partners if is_member(st, chara_info, q))
        line = formula.scenario_line(chara_info, cmd, lv, partners, card_levels, mods={
            "turn": turn, "research_level": lvls[formula.FACILITY_STATUS[base]], "lb_extra": lb_extra,
            "gear": gear, "chips": chips, "overdrive": od, "core_effects": effects,
            "total_research": sum(lvls.values()), "members": members, "home_energy": home_energy})
        # A stat a condition blocks (Slow Metabolism: speed) gains nothing on
        # the home line, so it has nothing to scale here either.
        line = [x for x in line if not (1 <= x["target_type"] <= 5 and conditions.blocks_stat(
            chara_info, formula.STATS[x["target_type"] - 1]))]
        points = formula.research_points(cmd, point_members(st, partners), gear=gear, friendship=friend,
                                         chips=chips, head_pct=head, levels=lvls, limit=int(st["limit"]))
        rows[str(cmd)] = {"gear": gear, "line": line, "points": [list(x) for x in points],
                          "partners": partners}
    st["preview"] = {"turn": turn, "od": od, "rows": rows}
    return before_gear != turn


def preview_row(st: dict, command_id, turn: int) -> dict:
    pv = st["preview"]
    if int(pv.get("turn") or 0) != int(turn):
        return {}
    cmd = int(formula.SERVER_ID.get(int(command_id or 0), int(command_id or 0)))
    for key in (cmd, formula.BASE_TO_SUMMER.get(cmd), formula.SUMMER_TO_BASE.get(cmd)):
        if key is not None and str(key) in pv["rows"]:
            return pv["rows"][str(key)]
    return {}


def gain_possible(st: dict) -> bool:
    return not gauge_full(st) and not int(st["burst"])


# ================================================================= UGE ===

def uge_pending(st: dict, turn: int) -> bool:
    sid = M.schedule_for_turn(turn)
    return bool(sid) and not result_of(st, sid)


def en_for(st: dict, schedule_id: int, grade: int) -> int:
    """EN at UGE k = 6 - max(0, grade(k-1) - grade(k)), grade(0) = S (§8.4,
    40/40 captured UGEs)."""
    before = result_of(st, schedule_id - 1) if schedule_id > 1 else 3
    return EN_PER_UGE - max(0, int(before) - int(grade))


def commit_uge(st: dict, turn: int) -> tuple:
    """The upgrade_race call: the grade off the progress (§8.5). Returns
    (schedule_id, result_type)."""
    sid = M.schedule_for_turn(turn)
    grade = M.grade_for(progress_rate(st, turn))
    st["results"] = [r for r in st["results"] if int(r["schedule_id"]) != sid] + [
        {"schedule_id": sid, "result_type": grade}]
    st["new_result"] = sid
    log.info("mecha: UGE %s at turn %s -> grade %s (progress %s)", sid, turn, grade,
             progress_rate(st, turn))
    return sid, grade


def uge_reward_effects(schedule_id: int, grade: int) -> list:
    """The result event's choice (§8.5): stats and SP; at UGE 5 the two hints
    (+3 each at S, else +1 -- B at UGE 5 INFERRED from GameTora's "level 1
    hint, level 3 at S")."""
    k = int(schedule_id) if grade >= 2 else int(schedule_id) - 1
    stats, sp = 5 + 5 * k, 15 + 10 * k
    effects = [{"type": "all_stats", "value": f"+{stats}"},
               {"type": "skill_point", "value": f"+{sp}"}]
    if int(schedule_id) == 5:
        n = 3 if grade >= 3 else 1
        effects += [{"type": "skill_hint", "skill_id": SKILL_ZENSHIN, "value": f"+{n}"},
                    {"type": "skill_hint", "skill_id": SKILL_YUME, "value": f"+{n}"}]
    return effects


def apply_uge_result(full_state: dict, chara_info: dict, schedule_id: int, grade: int) -> None:
    """What the result event's check_event lands besides its choice (§8.5):
    the limit, the EN, the facilities, Super Overdrive."""
    st = state(full_state)
    st["limit"] = LIMIT_START + LIMIT_STEP * uges_done(st)
    st["tp"] = int(st["tp"]) + en_for(st, schedule_id, grade)
    if grade >= 2 and int(schedule_id) in FACILITY_UP_UGES:
        RI.raise_all_facilities(full_state, chara_info)
    if int(schedule_id) == 5 and grade >= 3:
        st["burst"] = 1                     # Super Overdrive (§7.6)


def last_uge_s(st: dict) -> bool:
    return result_of(st, 5) >= 3


def all_s(st: dict) -> bool:
    return len(st["results"]) >= 5 and all(int(r["result_type"]) >= 3 for r in st["results"])


def upgrade_result_array(st: dict) -> list:
    rows = sorted(st["results"], key=lambda r: int(r["schedule_id"]))
    new = int(flag(st, "new_result_first") or 0)
    if new:
        rows = [r for r in rows if int(r["schedule_id"]) == new] + [
            r for r in rows if int(r["schedule_id"]) != new]
    return [{"schedule_id": int(r["schedule_id"]), "result_type": int(r["result_type"])} for r in rows]


# ============================================================== tuning ===

def chip_budget(st: dict) -> int:
    return int(st["tp"]) + sum(int(v) for v in st["chips"].values())


def set_chips(st: dict, board_info_array) -> str:
    """The tuning request: the WHOLE new allocation (§8.3). '' when applied,
    else why it was refused (budget, a chip above 5, a locked chip, a chip on
    the wrong board, a board missing)."""
    new = {str(c): 0 for chips in M.BOARD_CHIPS.values() for c in chips}
    boards = set()
    for b in board_info_array or ():
        board = int(b.get("board_id") or 0)
        if board not in M.BOARD_CHIPS:
            return f"board {board}"
        boards.add(board)
        for c in b.get("chip_info_array") or ():
            chip, pt = int(c.get("chip_id") or 0), int(c.get("point") or 0)
            if chip == M.BOARD_TOTAL.get(board):
                continue                      # a board total is derived, never set
            if chip not in M.BOARD_CHIPS[board]:
                return f"chip {chip} on board {board}"
            if not 0 <= pt <= M.CHIP_MAX:
                return f"chip {chip} at {pt}"
            if pt and not M.chip_open(chip, uges_done(st)):
                return f"chip {chip} locked"
            new[str(chip)] = pt
    if boards != set(M.BOARD_CHIPS):
        return f"boards {sorted(boards)}"
    spent = sum(new.values())
    budget = chip_budget(st)
    if spent > budget:
        return f"{spent} points over a budget of {budget}"
    st["chips"] = new
    st["tp"] = budget - spent
    return ""


def board_info(st: dict) -> list:
    totals = board_totals(st)
    return [{"board_id": b,
             "chip_info_array": [{"chip_id": c, "point": int(st["chips"].get(str(c), 0))}
                                 for c in chips] + [{"chip_id": M.BOARD_TOTAL[b], "point": totals[b]}]}
            for b, chips in sorted(M.BOARD_CHIPS.items())]


# ============================================================ envelope ===

def career_over(chara_info: dict) -> bool:
    return RI.career_over(chara_info)


def evaluation_array(chara_info: dict, st: dict) -> list:
    """mecha_data_set.evaluation_info_array: chara_info's rows, each with its
    chara and is_research_member (§9)."""
    by_pos = formula.RF.deck(chara_info)
    deck_charas = {formula.RF.card_meta(sid)[3] for sid in by_pos.values()}
    npc = {t: c for t, c in M.partner_rows() if c not in deck_charas}   # 101 rides a Tazuna card
    out = []
    for e in sorted((e for e in chara_info.get("evaluation_info_array") or () if isinstance(e, dict)),
                    key=lambda e: int(e.get("target_id") or 0)):
        t = int(e.get("target_id") or 0)
        if t in by_pos:
            chara = formula.RF.card_meta(by_pos[t])[3]
        elif t in npc:
            chara = npc[t]
        elif t >= formula.NPC_MIN:
            chara = t
        else:
            continue
        out.append({"target_id": t, "chara_id": chara,
                    "is_research_member": 1 if is_member(st, chara_info, t) else 0})
    return out


def rival_info(st: dict, turn: int) -> dict:
    lv, lim = levels(st), int(st["limit"])
    out = {}
    for status, key in M.STATUS_KEYS.items():
        out[key] = lv[status]
        out[f"{key}_limit"] = lim
    out["progress_rate"] = progress_rate(st, turn)
    return out


def overdrive_info(st: dict, turn: int) -> dict:
    return {"energy_num": int(st["energy"]), "max_energy_num": GAUGE_MAX,
            "remain_num": int(st["remain"]), "max_num": charges_max(),
            "over_drive_state": 1 if overdrive_on(st, turn) else 0,
            "overdrive_count": int(st["od_count"]), "is_overdrive_burst": int(st["burst"])}


def command_rows(st: dict, commands, turn: int) -> list:
    """mecha_data_set.command_info_array, row for row with the home screen."""
    gain = gain_possible(st)
    out = []
    for c in commands or ():
        cid, ctype = int(c.get("command_id") or 0), int(c.get("command_type") or 0)
        wire = formula.WIRE_ID.get(cid, cid)
        if ctype != 1:
            out.append({"command_type": ctype, "command_id": wire, "params_inc_dec_info_array": [],
                        "point_up_info_array": [], "is_recommend": False, "energy_num": 0})
            continue
        row = preview_row(st, cid, turn)
        gear = bool(row.get("gear"))
        out.append({"command_type": 1, "command_id": wire,
                    "params_inc_dec_info_array": [dict(p) for p in row.get("line") or ()],
                    "point_up_info_array": [{"status_type": int(s), "value": int(v)}
                                            for s, v in row.get("points") or ()],
                    "is_recommend": gear, "energy_num": 1 if gear and gain else 0})
    return out


def data_set(full_state: dict, chara_info: dict, commands, turn: int, full: bool) -> dict:
    st = state(full_state)
    not_up = flag(st, "not_up") or []
    return {
        "command_info_array": command_rows(st, commands, turn) if full else None,
        "tuning_point": int(st["tp"]),
        "rival_info": rival_info(st, turn),
        "overdrive_info": overdrive_info(st, turn),
        "evaluation_info_array": evaluation_array(chara_info, st),
        "upgrade_race_result_array": upgrade_result_array(st),
        "board_info_array": board_info(st),
        "not_up_macha_parameter_info": {"status_type_array": list(not_up),
                                        "overdrive_num_max_flag": bool(flag(st, "max_flag"))},
        "sub_command_chara_info_array": [],
        "is_tuning_enable": False,
    }
