"""Career goal BRANCHES: which trainee stories change the goal list, when they
are due, and which goal rows they switch to -- all derived from master.mdb.

docs/CAREER_BRANCHES.md covers the route side (single_mode_route_race's
determine_race / determine_race_flag columns). This module adds the story side,
which that write-up had to source from GameTora's `rc` codes. That left three
gaps, all live-reported on Curren Bouquet (2026-09-26):

  * GameTora records no `rc` for any JP-only trainee. Curren's "あなたへ捧ぐ、
    エーデルワイス" is listed as Power +10 on every language of her page, yet
    the client plays "Kyoto Kinen -> Nikkei Sho" and "target race changed to
    Tenno Sho (Spring)" when it fires. The client reads that production from
    its own master (single_mode_story_data.show_clear), so the goal change has
    to come from master too.
  * Nothing said WHEN a branch story fires. Suffixes 113-199 went into the
    random lottery, and Curren's fired on turn 8 of a career whose branch sits
    on turn 51.
  * Follow-on groups were never switched. Fuji Kiseki's NHK Mile choice leads
    to the Mile Championship on turn 46, not the Kikuka Sho; GameTora's `rc`
    names only the first race.

What master holds (JP's tables, shipped as data/events/story_branches.json
because Global's master.mdb lacks both -- see tools/build_story_branches.py):

  single_mode_story_condition_set  story S plays only after parent P, where
      P's choice (gain_select) or story arm (select_index) was a given value.
      Daiwa Scarlet: 501009203 "Before the Japanese Derby" needs 501009115
      "Her" with gain_select 2, and "Before the Oaks" needs gain_select 1.
      Following those chains from a branch story to the "Before the X" stories
      it unlocks names the goal race each choice leads to -- every group it
      touches, not just the first.
  single_mode_story_data.show_clear on a trainee story (the client's goal-
      change production): 4 = objective changed, 5 = objective decided,
      23 = objective added, 25 = changed AND added. The stories carrying 4/23/25
      with no condition_set children are unconditional: firing them is the
      change.
  single_mode_route_race.determine_race: 1 = the default arm, 2 = the flagged
      alternative, 3 = one of N arms (or, alone in its slot, a goal an event
      ADDS -- Curren's Tenno Sho (Spring)), 7 = a goal an event adds.

Timing: the one real capture of a branch story (`docs/tachyon switch`) has
Agnes Tachyon's "Report: A Clear Gaze" on turn 32, the turn after her
Satsuki Sho goal (31) and two turns before the branch it decides (33/34).
fire_turn() generalises that: two turns before the branch, but never before
the goal ahead of it has been run.
"""
from __future__ import annotations

import functools
import json
import logging
import os
from dataclasses import dataclass

from . import master_data

log = logging.getLogger(__name__)

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                     "data", "events", "story_branches.json")

# single_mode_story_data.show_clear on a trainee story (NOT the response enum of
# the same name -- see the note above UNLOCK_OUTING_DISPLAY_ID in event_engine).
SHOW_CHANGE = 4
SHOW_DECIDE = 5
SHOW_ADD = 23
SHOW_CHANGE_ADD = 25
_UNCONDITIONAL_SHOWS = (SHOW_CHANGE, SHOW_ADD, SHOW_CHANGE_ADD)

DR_DEFAULT = 1
DR_ALTERNATE = 2
# A lone row with one of these is a goal that only exists once an event adds it.
_ADDED_GOAL_DR = (3, 7)

# Two turns ahead of the branch, as in the Tachyon capture (turn 32 for 33/34).
LEAD_TURNS = 2

# The shared camp-end beats have a fixed turn, which is what anchors chara 1132's
# "Summer Camp (Year 2) Ends" (show_clear 4) to her Classic-autumn branch rather
# than the spring one it follows.
_FIXED_SUFFIX_TURN = {300: 40, 301: 64}


@dataclass(frozen=True)
class Arm:
    id: int
    sort_id: int
    turn: int
    program: int
    inst: int
    race_id: int
    dr: int
    flag: int
    gen: int


@dataclass(frozen=True)
class BranchStory:
    story_id: int
    # One tuple of Arm ids per choice, in choice order. An unconditional story
    # has exactly one.
    choices: tuple
    # True when the SERVER picks the arm by story branch (select_index), as for
    # Agnes Tachyon's mood check or Matikanefukukitaru's fortune, rather than
    # the player picking a choice.
    by_select_index: bool
    sort_ids: frozenset
    first_turn: int


@functools.lru_cache(maxsize=1)
def _data() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        log.exception("story branch data unreadable (%s); no master-derived branches", _PATH)
        return {"roots": [], "conditions": []}


def _band(chara_id: int) -> tuple:
    base = 500000000 + chara_id * 1000
    return base, base + 999


@functools.lru_cache(maxsize=256)
def route_rows(race_set_id: int) -> tuple:
    """Every row of a race set as Arm (determine_race 0 rows included), id order."""
    rows = master_data.query(
        "SELECT rr.id AS id, rr.sort_id AS sort_id, rr.turn AS turn, "
        "       rr.condition_type AS ct, rr.target_type AS tt, rr.condition_id AS program, "
        "       rr.determine_race AS dr, rr.determine_race_flag AS flag, "
        "       rr.determine_race_for_generate AS gen, "
        "       p.race_instance_id AS inst, ri.race_id AS race_id "
        "FROM single_mode_route_race rr "
        "LEFT JOIN single_mode_program p ON rr.condition_type = 1 AND p.id = rr.condition_id "
        "LEFT JOIN race_instance ri ON ri.id = p.race_instance_id "
        "WHERE rr.race_set_id=? ORDER BY rr.id", (race_set_id,))
    return tuple(Arm(id=r["id"], sort_id=r["sort_id"], turn=r["turn"] or 0,
                     program=r["program"] or 0, inst=r["inst"] or 0,
                     race_id=r["race_id"] or 0, dr=r["dr"] or 0,
                     flag=r["flag"] or 0, gen=r["gen"] or 0)
                 for r in rows if r["tt"] in (1, 3))


def arms(race_set_id: int) -> tuple:
    """The branch rows (determine_race != 0) of a race set."""
    return tuple(a for a in route_rows(race_set_id) if a.dr)


def _groups(race_set_id: int) -> dict:
    out: dict = {}
    for a in arms(race_set_id):
        out.setdefault(a.sort_id, []).append(a)
    return out


def _race_stories(chara_id: int, race_set_id: int, arm: Arm, prefix: str,
                  every_run: bool = False) -> frozenset:
    """The trainee's "{prefix}{race}" stories for arm's race.

    By default only THIS running of the race, counted over the route, which is
    what places an "After the X" story on its goal's turn. every_run takes all
    of them: a story chain can run through a running that is not a goal at all
    (Ines Fujin's leads through a Classic Arima Kinen her route never lists, so
    her Senior Arima's "Before" story is the second of two), and the caller
    then bounds the match by turn instead -- see _pick_arms."""
    if not arm.program or not arm.race_id:
        return frozenset()
    from .handlers import single_mode_team as smt
    info = smt._race_info_for_program(arm.program)
    name = info and info.get("story_name")
    if not name:
        return frozenset()
    if every_run:
        found = set()
        for k in range(6):
            found.update(smt._find_race_story_ids(chara_id, prefix, name, k, 99))
        return frozenset(found)
    turns = sorted({a.turn for a in route_rows(race_set_id) if a.race_id == arm.race_id})
    occ = turns.index(arm.turn) if arm.turn in turns else 0
    return frozenset(smt._find_race_story_ids(chara_id, prefix, name, occ, len(turns)))


def _children(chara_id: int) -> dict:
    """{parent story: [(child story, gain_select, select_index), ...]} in the band."""
    lo, hi = _band(chara_id)
    out: dict = {}
    for row in _data().get("conditions") or ():
        sid = row["story_id"]
        if not lo <= sid <= hi:
            continue
        for parent, gain, sel in row["parents"]:
            out.setdefault(parent, []).append((sid, gain or 0, sel or 0))
    return out


def _descendants(children: dict, root: int, by_select: bool, value: int) -> set:
    """Every story reachable from `root` taking branch `value`: its direct
    children on that value, then their plain (unconditioned) descendants. A
    child that is itself gated on ANOTHER choice is a separate root and stops
    the walk there."""
    seen: set = set()
    frontier = [c for c, g, s in children.get(root, ())
                if (s if by_select else g) == value]
    while frontier:
        sid = frontier.pop()
        if sid in seen:
            continue
        seen.add(sid)
        frontier.extend(c for c, g, s in children.get(sid, ()) if not g and not s)
    return seen


def _pick_arms(chara_id: int, race_set_id: int, stories: set, after_turn: int = 0) -> tuple:
    """The arms after `after_turn` whose "Before the X" story is among
    `stories`, one per group. The turn bound is what keeps chara 1135's
    Senior-year "Before the Tenno Sho (Autumn)" off her Classic-year arm.

    A group whose arms all run the same race (Mejiro Ardan's two Senior Tenno
    Sho (Autumn) rows) matches on both; it takes the arm carrying a flag
    already chosen elsewhere in this choice (her flags pair 107101/107102
    across both groups), and is skipped when nothing settles it."""
    chosen, ambiguous = {}, {}
    for sort_id, group in _groups(race_set_id).items():
        group = [a for a in group if a.turn > after_turn]
        # This running's own story first; any running only when that finds
        # nothing (see _race_stories). Taking any running outright lets
        # Ardan's Senior "Before the Tenno Sho (Autumn)" claim her Classic arm.
        hit = [a for a in group if _race_stories(chara_id, race_set_id, a, "Before the ") & stories]
        if not hit:
            hit = [a for a in group if _race_stories(
                chara_id, race_set_id, a, "Before the ", every_run=True) & stories]
        if len(hit) == 1:
            chosen[sort_id] = hit[0]
        elif hit:
            ambiguous[sort_id] = hit
    flags = {a.flag for a in chosen.values() if a.flag}
    for sort_id, hit in ambiguous.items():
        by_flag = [a for a in hit if a.flag in flags]
        if len(by_flag) == 1:
            chosen[sort_id] = by_flag[0]
    return tuple(a.id for a in sorted(chosen.values(), key=lambda a: a.turn))


def anchor_turn(chara_id: int, race_set_id: int, story_id: int) -> int:
    """The turn a non-random story is known to play on, or 0: the goal race it
    is the "After the X" story of, or a fixed camp-end beat."""
    fixed = _FIXED_SUFFIX_TURN.get(story_id % 1000)
    if fixed:
        return fixed
    for row in route_rows(race_set_id):
        if story_id in _race_stories(chara_id, race_set_id, row, "After the "):
            return row.turn
    return 0


def _unconditional_arms(chara_id: int, race_set_id: int, story_id: int, show: int) -> tuple:
    """What a show_clear 4/23/25 story does: switch to the next flagged
    alternative (4), add the next event-added goal (23), or both (25)."""
    anchor = anchor_turn(chara_id, race_set_id, story_id)
    groups = _groups(race_set_id)
    out = []
    if show in (SHOW_CHANGE, SHOW_CHANGE_ADD):
        alts = sorted((a for g in groups.values() if len(g) > 1 for a in g
                       if a.dr == DR_ALTERNATE and min(x.turn for x in g) > anchor),
                      key=lambda a: a.turn)
        if alts:
            out.append(alts[0])
    if show in (SHOW_ADD, SHOW_CHANGE_ADD):
        added = sorted((g[0] for g in groups.values()
                        if len(g) == 1 and g[0].dr in _ADDED_GOAL_DR and g[0].turn > anchor),
                       key=lambda a: a.turn)
        if added:
            out.append(added[0])
    return tuple(a.id for a in out)


@functools.lru_cache(maxsize=256)
def branch_stories(chara_id: int, race_set_id: int) -> dict:
    """{story_id: BranchStory} for every trainee story that edits this route."""
    if not chara_id or not race_set_id or not arms(race_set_id):
        return {}
    lo, hi = _band(chara_id)
    children = _children(chara_id)
    by_id = {a.id: a for a in route_rows(race_set_id)}
    out: dict = {}

    def add(story_id, choices, by_select):
        choices = tuple(c for c in choices)
        ids = {i for c in choices for i in c}
        if not ids:
            return
        sorts = frozenset(by_id[i].sort_id for i in ids)
        first = min(a.turn for a in arms(race_set_id) if a.sort_id in sorts)
        out[story_id] = BranchStory(story_id, choices, by_select, sorts, first)

    # Choice roots: any story a condition row gates on a gain_select or
    # select_index value, plus story_root's own list.
    roots = {r["story_id"] for r in _data().get("roots") or () if lo <= r["story_id"] <= hi}
    roots |= {p for p, kids in children.items() if lo <= p <= hi
              and any(g or s for _c, g, s in kids)}
    for root in sorted(roots):
        kids = children.get(root, ())
        by_select = not any(g for _c, g, _s in kids) and any(s for _c, _g, s in kids)
        values = sorted({(s if by_select else g) for _c, g, s in kids} - {0})
        anchor = anchor_turn(chara_id, race_set_id, root)
        choices = [_pick_arms(chara_id, race_set_id,
                              _descendants(children, root, by_select, v), anchor)
                   for v in values]
        if any(choices):
            add(root, choices, by_select)

    # Unconditional goal-change stories.
    for r in master_data.query(
            "SELECT story_id, show_clear FROM single_mode_story_data "
            "WHERE story_id BETWEEN ? AND ? AND show_clear IN (?, ?, ?)",
            (lo, hi, *_UNCONDITIONAL_SHOWS)):
        if r["story_id"] in out:
            continue
        picked = _unconditional_arms(chara_id, race_set_id, r["story_id"], r["show_clear"])
        if picked:
            add(r["story_id"], (picked,), False)
    return out


def added_goal_ids(chara_id: int, race_set_id: int) -> frozenset:
    """Route rows that only exist once a story adds them (lone determine_race
    3/7 rows some branch story targets)."""
    lone = {g[0].id for g in _groups(race_set_id).values()
            if len(g) == 1 and g[0].dr in _ADDED_GOAL_DR}
    targeted = {i for bs in branch_stories(chara_id, race_set_id).values()
                for c in bs.choices for i in c}
    return frozenset(lone & targeted)


def start_route(chara_id: int, race_set_id: int, ids) -> list:
    """The route a career STARTS on: one arm per branch group, and no goal
    that an event has yet to add.

    The arm is master's default (determine_race 1) where the group has one --
    Curren Bouquet starts on the Kyoto Kinen and her event moves her to the
    Nikkei Sho, which is what the client's own production says happens.
    determine_race_for_generate, which this used to key off, marks the arm a
    GENERATED career runs, and disagrees with determine_race 1 in five groups
    (charas 1109, 1132, 1134, 1135, 1144). Groups with no default row keep the
    old rule."""
    ids = [int(i) for i in ids]
    drop = set(added_goal_ids(chara_id, race_set_id))
    for group in _groups(race_set_id).values():
        if len(group) < 2:
            continue
        pick = (next((a for a in group if a.dr == DR_DEFAULT), None)
                or next((a for a in group if a.gen == 0), None)
                or min(group, key=lambda a: a.id))
        drop |= {a.id for a in group if a.id != pick.id}
    return [i for i in ids if i not in drop]


def fire_turn(race_set_id: int, bs: BranchStory) -> int:
    """The turn a branch story with no natural trigger is due on."""
    before = [a.turn for a in route_rows(race_set_id)
              if a.turn < bs.first_turn and a.sort_id not in bs.sort_ids]
    floor = (max(before) + 1) if before else 2
    return max(2, floor, bs.first_turn - LEAD_TURNS)


def effects_for_choice(race_set_id: int, bs: BranchStory, index: int) -> list:
    """race_change effects for choice `index` (0-based), naming the exact route
    row so a same-race group (Ardan's two Tenno Sho rows) lands on the right one."""
    if not 0 <= index < len(bs.choices):
        return []
    by_id = {a.id: a for a in route_rows(race_set_id)}
    return [{"type": "race_change", "race_instance_id": by_id[i].inst, "route_race_id": i}
            for i in bs.choices[index] if i in by_id]


# --- CHAPTER BEATS ------------------------------------------------------------
# A trainee's own story chapters (event_category 2, suffix 113-199: Tachyon's
# "Report:" series, Still in Love's "Still ..." pieces) play on a FIXED turn,
# and master says which: JP's gallery_list_id is turn * 1000 + order within the
# turn. Checked against the Tachyon capture (4 of 4 trainee stories on exactly
# that turn) and against 186 real URA / Unity Cup / Grand Live careers in the
# bot corpus (774 of 825 chapter beats on exactly that turn; 44 of the 51
# misses are chara 1098, which never shows one). The rule it replaces --
# "two turns before goal race N" -- agreed with master on 16 of 540.
#
# Global's master holds placeholders there, so the rows ship in
# story_branches.json from JP (tools/build_story_branches.py) like the
# condition sets do.

# condition_type in single_mode_story_condition_set
GATE_ALL = 1
GATE_ANY = 2


@functools.lru_cache(maxsize=512)
def chapter_stories(chara_id: int) -> tuple:
    """((story_id, turn), ...) for this trainee's chapter beats, in play order.

    Two chapters sharing one slot (same turn AND order) are alternatives, not a
    pair: Oguri Cap's two "天皇賞（春）にて" (118/119) never both play -- across
    37 real careers exactly one does, by whether she ran the Tenno Sho (Spring)
    that turn. Where a condition set tells them apart (Narita Brian's "頂" /
    "告") gate_met picks; where none does, nothing here can, so they are left
    to whichever trigger owns them rather than played both."""
    lo, hi = _band(chara_id)
    rows = sorted((r["order"], r["story_id"], r["turn"])
                  for r in _data().get("chapters") or () if lo <= r["story_id"] <= hi)
    slots: dict = {}
    for order, sid, _turn in rows:
        slots.setdefault(order, []).append(sid)
    gates = _gates()
    undecidable = {sid for sids in slots.values() if len(sids) > 1
                   and not any(s in gates for s in sids) for sid in sids}
    return tuple((sid, turn) for _order, sid, turn in rows if sid not in undecidable)


@functools.lru_cache(maxsize=512)
def chapter_band_ids(chara_id: int) -> frozenset:
    """Every chapter story of this trainee, scheduled or not -- none of them
    belongs in the random lottery."""
    lo, hi = _band(chara_id)
    return frozenset(r["story_id"] for r in _data().get("chapters") or ()
                     if lo <= r["story_id"] <= hi)


@functools.lru_cache(maxsize=1)
def _gates() -> dict:
    """{story_id: (condition_type, ((parent, gain_select, select_index), ...))}"""
    return {r["story_id"]: (r.get("type", GATE_ALL),
                            tuple((p, g or 0, s or 0) for p, g, s in r["parents"]))
            for r in _data().get("conditions") or () if r.get("parents")}


@functools.lru_cache(maxsize=1)
def gate_parents() -> frozenset:
    """Every story some other story's condition names -- the ones worth
    remembering once they have played."""
    return frozenset(p for _t, parents in _gates().values() for p, _g, _s in parents)


def gate_met(story_id: int, played, choices) -> bool:
    """Whether `story_id`'s condition set is satisfied. `played` holds the
    stories served this career; `choices` maps a story to the choice picked on
    it (gain_select). An ungated story is always met. A select_index condition
    (a server-picked story arm) is never met: nothing here picks those."""
    gate = _gates().get(story_id)
    if gate is None:
        return True
    kind, parents = gate

    def ok(parent, gain, sel):
        if parent not in played or sel:
            return False
        return not gain or choices.get(parent) == gain

    hits = [ok(*p) for p in parents]
    return any(hits) if kind == GATE_ANY else all(hits)
