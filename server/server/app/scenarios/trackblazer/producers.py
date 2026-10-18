"""TRACKBLAZER (scenario 4) -- the scenario's own fixed story chain.

`@CE.producer(..., scenario=SCENARIO_ID)` makes career_events' own dispatch skip
these everywhere else, so nothing here can leak into a URA run and no shared
module has to know these beats exist.

WHERE THE TABLE COMES FROM
--------------------------
Two sources, and they agree. The turn of each beat was recovered from 501
finished careers in captures/bot_logs (every event id that lands on exactly one
turn), and every date matches the wiki's own fixed-event table using this
project's turn convention (turn = year_base + (month-1)*2 + 1 Early | 2 Late,
so turn 24 is Late December of the Junior year). The exact event ids, their
play_timings and their choice counts were then read off the full-body capture
captures/bot/20260905_144604_icarus.

STORY IDS ARE NOT HARDCODED. single_mode_story_data.id IS the event id, and the
wire carries short_story_id when it is non-zero and story_id otherwise -- the
capture confirms both halves of that rule (203026 served 400004400, its short
id; 203301 served 400004002, its story id, having no short one). So _story()
reads them out of master rather than freezing a second copy here that could
drift from it.

TURN KEYING. A beat is keyed on the turn the CLIENT sees it on, which for a beat
produced by exec_command is ctx.advanced_turn -- the capture shows
exec_command(current_turn=26) producing the turn-27 beat. The opening beat is
the exception: it lands on the career's very first exec_command with the turn
still 1, so the match below accepts either turn number and lets the once_key do
the rest. Getting this wrong shifts a whole chain by one turn, which is the
failure Grand Live's own table carries a warning about.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
* 203019/203020/203021/203022/203023 and 203046/203047/203048/203049. These are
  NOT pool events: master.mdb gives the first five the story "Training Level Up"
  (one id per facility) and the other four the "Director's Appraisal" bond
  tiers, i.e. the recurring families URA already has. They are served through
  Scenario.facility_levelup_event / .appraisal_events -- see this scenario's
  class. (The "shared random-event machinery" this docstring used to defer them
  to never existed.)
* The two "Achievement!" series (203803/203810/203811/203821/203822 and
  203826/203828/203830/203832/203833/203834). Each series shares one story
  across its ids, so they are a family with a trigger of its own -- not yet
  identified -- rather than distinct random stories. Still unserved.
* 203025, now IDENTIFIED: its title (text_data 181/400004013) is "Rival
  Bested!", so it is the Rival Race victory cutscene, not the race-fatigue beat
  it was guessed to be. Its reward matches impl.rival_win_reward measured on
  the capture -- +5 to two stats, or a skill hint (0094 +5 power +5 wiz, 0230
  a hint, 0300 +5 stamina +5 power). Still not served here, because it belongs
  to a race RESULT and not to a turn: Scenario.on_race_result already pays the
  reward, but nothing shows the player the event that explains it.
* (Resolved) the year-end tiers: see YEAR_END_BEST -- the wiki's two-tier
  gate is implemented, MANT's slightly different bond cut-offs noted there.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from ... import career_events as CE
from ... import master_data
from .impl import SCENARIO_ID
from . import impl

log = logging.getLogger("uma-server")


def _story(event_id: int) -> int:
    """The story id the wire carries for this beat -- short_story_id when it has
    one, story_id otherwise. See the module docstring."""
    row = master_data.query_one(
        "SELECT story_id, short_story_id FROM single_mode_story_data WHERE id=?",
        (int(event_id),))
    if row is None:
        return 0
    return int(row["short_story_id"] or row["story_id"] or 0)


# turn -> [(event_id, n_choices, play_timing)]. Capture-derived; see above.
FIXED_BEATS: dict = {
    1:  [(203026, 1, 6)],       # "The Climax Begins!" -- the opening
    3:  [(203301, 0, 1)],       # the tutorial; the wiki's "9 turns before Debut"
    13: [(203027, 0, 1)],       # "Pro Shop Grand Opening" -- the turn
                                # single_mode_turn's unique_command flips to 1
    # 203578 used to sit here on turn 44. It is a WINDOWED POOL event -- the
    # corpus has it on 17-22 / 41-46 / 65-70, 20 of 288 times on 44 -- and is
    # served (and paid) from the pool now.
}

# The exclusive seasonal beats: one arm of each group fires, never two. The
# corpus splits them ~50/50 (and three ways on turn 42), which is what says they
# are one beat with alternative stories rather than several beats that happen to
# share a turn.
SEASONAL_GROUPS: dict = {
    27: (203601, 203602),               # Chocolates / Happy Valentine's
    29: (203552, 203553),               # Target Captured / Since It's White Day
    42: (203575, 203576, 203577),       # Sporty Day / Reading / Miracle Spice
    60: (203559, 203560),               # Sudden Rain / Heartfelt Request
    68: (203585, 203586),               # Trick No Treat / Peak Halloween
    72: (203597, 203598),               # the Holiday pair
}
SEASONAL_TIMING = 1

# The year-end objectives. Each turn serves an announcement and a follow-up, and
# each has a MET and a MISSED arm -- a failure branch URA has no equivalent of.
# The pairs share their story ids (203007 and 203010 both carry short story
# 400004401), so the branch is in the reward, not the cutscene.
#
# The follow-up is titled "Best X Year Umamusume!", and the capture serves it
# for an ordinarily CLEARED objective -- so it is the met arm's second beat, not
# a separate top tier gated on anything. What each beat pays is in
# GOAL_MET_EFFECTS below.
# The scenario's own skill and its gold upgrade -- group 21006, rarities 1 and 2.
_GLITTERING_STAR = 210062
_RADIANT_STAR = 210061


GOAL_BEATS: dict = {
    24: {"met": (203010, 203059), "missed": (203007, 203056)},
    48: {"met": (203011, 203060), "missed": (203008, 203057)},
    72: {"met": (203012, 203061), "missed": (203009, 203058)},
}
GOAL_TIMING = 3

# THE "missed" IDS ARE ALSO A MET VARIANT. In the bot corpus 203007/203008/
# 203009 are served in 486 careers that go on to turn 78 and get their "Best X
# Year" follow-up (203056-203058) -- a failed objective ends the career -- and
# they pay exactly what the met arm pays: +5/+6/+7 all stats on 486/486,
# 486/486 and 484/486 careers, then one stat +10 / +5 all / +10 all on the
# follow-up (432/448/442 careers). The 1159-career 203010 arm is the same
# numbers. What selects the variant is not known, so a cleared year draws it at
# the corpus ratio, seeded per career and year.
ALT_ARM_SHARE = 486 / (486 + 1159)

# WHAT CLEARING AN OBJECTIVE PAYS, measured off the capture request by request.
# Each year is a two-event chain and BOTH halves pay; the amounts differ per
# year, so there is no single flat reward to factor out.
#
# The measurement is a straight before/after on chara_info across the
# check_event that RESOLVES each event (the reward lands on resolution, so the
# delta belongs to the id in that request's event_id, not the one it serves):
#
#   junior   0094 -> 0095 (resolve 203010): +5 all, +30 SP
#            0095 -> 0096 (resolve 203059): +10 power, +20 SP, unique 2 -> 3
#   classic  0263 -> 0264 (resolve 203011): +6 all, +40 SP
#            0264 -> 0265 (resolve 203060): +5 all, +30 SP, unique 3 -> 4
#   senior   0471 -> 0472 (resolve 203012): +7 all, +50 SP
#            0472 -> 0473 (resolve 203061): +10 all, +30 SP, unique 4 -> 5
#
# The announcement's own reward scales cleanly by year (+5/+6/+7 all stats,
# +30/+40/+50 SP). The follow-up's does not, so it is served as measured.
# Junior's is ONE stat, not five -- power in the capture, which was that
# trainee's LOWEST, but user-reported as a RANDOM stat, so random_stats is what
# is served. Classic's also carries a hint for the scenario skill "Glittering
# Star" (user-reported; skill 210062, which does not move a chara_info number
# and so could not have been read out of the stat deltas above).
#
# The unique-skill level-up rides on the FOLLOW-UP, not the announcement --
# capture-pinned: the level is still 2 in the response that resolves 203010 and
# 3 in the one that resolves 203059.

GOAL_MET_EFFECTS: dict = {
    24: {"announce": [{"type": "all_stats", "value": "+5"},
                      {"type": "skill_points", "value": "+30"}],
         "follow": [{"type": "unique_skill_level", "value": "+1"},
                    {"type": "random_stats", "value": "+10", "stat_count": 1},
                    {"type": "skill_points", "value": "+20"}]},
    48: {"announce": [{"type": "all_stats", "value": "+6"},
                      {"type": "skill_points", "value": "+40"}],
         "follow": [{"type": "unique_skill_level", "value": "+1"},
                    {"type": "all_stats", "value": "+5"},
                    {"type": "skill_points", "value": "+30"},
                    {"type": "skill_hint", "skill_id": _GLITTERING_STAR,
                     "value": "+1"}]},
    72: {"announce": [{"type": "all_stats", "value": "+7"},
                      {"type": "skill_points", "value": "+50"}],
         "follow": [{"type": "unique_skill_level", "value": "+1"},
                    {"type": "all_stats", "value": "+10"},
                    {"type": "skill_points", "value": "+30"}]},
}
# WHICH FOLLOW-UP A CLEARED YEAR GETS. Not every cleared year earns "Best X
# Year Umamusume!" -- the wiki (Game_Trackblazer) documents two tiers behind
# the announcement, each with its own master stories:
#
#   Best X Year (203050-203067)   stats + SP + unique level: Akikawa bond AND
#                                 (Etsuko bond OR Grade Points) AND fans
#   the fallback (203028-203045)  unique level ONLY: Akikawa bond AND fans --
#                                 "Each in Our Own Way" / "Into Third Year" /
#                                 "Director's Surprise!"
#   neither                       no follow-up, no unique level
#
# MANT agrees the unique level is gated on fans + Akikawa bond, with slightly
# different bond cut-offs (19 / 31 / 51 against the wiki's 15 / 30 / 50); the
# wiki's are used because it is the only source with the whole structure.
# Fans for Classic/Senior are lower for dirt careers (40k / 80k). Junior's Best
# tier lists no fan condition. This used to grant Best -- and the unique
# level -- to every cleared objective.
#
# (akikawa, etsuko, grade points, fans turf, fans dirt) per year-end turn.
YEAR_END_BEST = {24: (15, 20, 100, 0, 0), 48: (30, 40, 450, 60000, 40000),
                 72: (50, 60, 480, 120000, 80000)}
YEAR_END_FALLBACK = {24: (15, 5000, 5000), 48: (30, 60000, 40000),
                     72: (50, 120000, 80000)}
# Same variant group as the capture's 203010/203059 pair (group 3 of 6).
YEAR_END_FALLBACK_EVENT = {24: 203037, 48: 203038, 72: 203039}
_UNIQUE_ONLY = [{"type": "unique_skill_level", "value": "+1"}]


def _npc_bond(chara_info: dict, target_id: int) -> int:
    for row in (chara_info or {}).get("evaluation_info_array") or ():
        if int(row.get("target_id") or 0) == target_id:
            return int(row.get("evaluation") or 0)
    return 0


def year_end_tier(full_state: dict, chara_info: dict, turn: int) -> str | None:
    """"best", "fallback" or None for a cleared year -- see YEAR_END_BEST."""
    akikawa = _npc_bond(chara_info, 102)
    etsuko = _npc_bond(chara_info, 103)
    fans = int((chara_info or {}).get("fans") or 0)
    gp = int(((impl.state(full_state).get("objective_points") or {})
              .get(str(turn))) or 0)
    dirt = 0 < impl.objective_target(chara_info, 48) < 300
    a, e, g, f_turf, f_dirt = YEAR_END_BEST[turn]
    if akikawa >= a and (etsuko >= e or gp >= g) and fans >= (f_dirt if dirt else f_turf):
        return "best"
    a, f_turf, f_dirt = YEAR_END_FALLBACK[turn]
    if akikawa >= a and fans >= (f_dirt if dirt else f_turf):
        return "fallback"
    return None


# A MISSED objective pays nothing. Not a measurement -- the capture cleared all
# three -- but the level-up is what the guides call the reward for clearing,
# and the missed arm is the branch that does not get it.

# The career's own closer, served after the third Climax leg's post-race beat.
ENDING_BEAT = (203202, 1, 3)
ENDING_TURN = 78


def _p(stat, n):
    return {"type": stat, "value": f"+{n}"}


_MOOD_UP = {"type": "mood", "value": "+1"}


def _energy(n):
    return {"type": "energy", "value": f"+{n}"}


# WHAT THE FIXED BEATS PAY. Every one of them does, and none of them did.
#
# TWO SOURCES, AND THEY AGREE.
#  1. The full-body capture, measured as a before/after on chara_info across the
#     check_event that RESOLVES each id (the reward lands on resolution, so a
#     delta belongs to the id in that request's event_id):
#       0110 (203601) +10 power, motivation 3->4
#       0115 (203552) +10 stamina, vital 95->104 (capped at max_vital)
#       0204 (203577) +10 guts, motivation 3->4
#       0220 (203578) +12 guts, and nothing else in the whole chara_info diff
#       0351 (203559) +10 speed, vital 45->65
#       0414 (203586) +10 speed, motivation 4->5
#       0465 (203598) +10 power, vital 0->30
#       0508 (203202) +10 all, +40 SP, hint (21006, rarity 2) = Radiant Star
#  2. The 1,741-career bot_logs corpus, whose per-call digest carries the five
#     stats plus vital and motivation. That is what fills in the SEVEN arms the
#     single capture never rolled (203602, 203553, 203575, 203576, 203560,
#     203585, 203597) and what settles the energy amounts the capture could
#     only see clipped by max_vital.
#
# READING THE CORPUS. Those logs write a call's RESPONSE line BEFORE its own
# request line, so the delta for an event is between the two chara snapshots
# that PRECEDE its check_event -- which is why the naive pairing reported
# nothing for most of these. Under the right pairing every arm lands on one
# shape with a long tail of noise: 203601 78% +10 power / 17% +10 power AND
# motivation, 203602 76% / 19% the same with wisdom, and so on. The split is
# the CAP, not a random reward -- the minority rows are the careers whose
# motivation was not already 5 (and, for the energy beats, whose vital had room
# under max_vital), so the true reward is the union of the two.
#
# THE SHAPE, once assembled: every seasonal arm is +10 to ONE stat plus either
# motivation or energy, fixed per GROUP -- Valentine's and the two autumn
# groups pay mood, White Day and the rain/holiday groups pay energy, rising
# 20/20/30 as the career goes on. The three ceremonial beats (the opening, the
# tutorial, the shop opening) pay nothing, capture- and corpus-confirmed
# (203027: 1641 of 1642 careers show no change at all).
#
# (203578, +12 guts, turned out to be a pool event -- see FIXED_BEATS.)
BEAT_EFFECTS: dict = {
    # ---- ceremonial, no reward ----
    203026: [],                                     # The Climax Begins!
    203301: [],                                     # Tutorial
    203027: [],                                     # Pro Shop Grand Opening!
    # ---- turn 27, Valentine's ----
    203601: [_p("power", 10), _MOOD_UP],            # Chocolates for Someone Special
    203602: [_p("wisdom", 10), _MOOD_UP],           # Happy Valentine's Day!
    # ---- turn 29, White Day ----
    203552: [_p("stamina", 10), _energy(20)],       # Target Successfully Captured!
    203553: [_p("guts", 10), _energy(20)],          # Since It's White Day
    # ---- turn 42, the three-way ----
    203575: [_p("power", 10), _MOOD_UP],            # Sporty Umamusume Day!
    203576: [_p("wisdom", 10), _MOOD_UP],           # The Beginner's Guide to Reading
    203577: [_p("guts", 10), _MOOD_UP],             # Miracle Spice?
    # ---- turn 60, the rain ----
    203559: [_p("speed", 10), _energy(20)],         # When There's Sudden Rain
    203560: [_p("stamina", 10), _energy(20)],       # A Heartfelt Request
    # ---- turn 68, Halloween ----
    203585: [_p("wisdom", 10), _MOOD_UP],           # Trick, No Treat!
    203586: [_p("speed", 10), _MOOD_UP],            # Peak Halloween!
    # ---- turn 72, the Holiday ----
    203597: [_p("stamina", 10), _energy(30)],       # A Holiday Night Surprise
    203598: [_p("power", 10), _energy(30)],         # The Best Holiday Ever!
    # ---- the closer. Radiant Star (210061) is the RARITY 2 skill of group
    # 21006 -- the gold upgrade of the Glittering Star the classic objective
    # hands out, and the tip the capture shows appearing at (21006, 2).
    203202: [{"type": "all_stats", "value": "+10"},
             {"type": "skill_points", "value": "+40"},
             {"type": "skill_hint", "skill_id": _RADIANT_STAR, "value": "+1"}],
}


def _event(event_id: int, choices: int, timing: int, ctx, effects=None) -> CE.Event:
    return CE.Event(
        event_id=int(event_id),
        story_id=_story(event_id),
        play_timing=int(timing),
        choices=[CE.Choice(effects=list(effects or []))
                 for _ in range(max(1, choices))] if choices else [],
        chara_id=ctx.player_chara,
        once_key=f"trackblazer:{event_id}",
        priority=CE.PRIO_SCENARIO,
    )


def _due(ctx, turn: int) -> bool:
    """Whether `turn` is the turn this poll should serve. See TURN KEYING."""
    return int(turn) in (int(ctx.advanced_turn or 0), int(ctx.turn or 0))


@CE.producer("trackblazer_fixed_beats", priority=CE.PRIO_SCENARIO,
             scenario=SCENARIO_ID)
def trackblazer_fixed_beats(ctx: CE.Ctx) -> list:
    out = []
    for turn, beats in FIXED_BEATS.items():
        if not _due(ctx, turn):
            continue
        for event_id, choices, timing in beats:
            out.append(_event(event_id, choices, timing, ctx,
                              effects=BEAT_EFFECTS.get(event_id)))
    for turn, group in SEASONAL_GROUPS.items():
        if not _due(ctx, turn):
            continue
        # Seeded on the CAREER (not the trainee) so the arm is stable across a
        # re-poll of the same turn -- these are produced on every exec_command
        # until one is served, and a fresh roll each time would offer a
        # different story -- while still differing between careers. Seeding on
        # player_chara alone made the arm deterministic per trainee: every
        # Special Week run got the same "random" seasonal story every time,
        # which is issue 5.4. career_salt is drawn once per career.
        rng = random.Random((CE.career_salt(ctx.full_state) << 8) ^ int(turn))
        arm = rng.choice(group)
        out.append(_event(arm, 1, SEASONAL_TIMING, ctx,
                          effects=BEAT_EFFECTS.get(arm)))
    if _ending_due(ctx):
        event_id, choices, timing = ENDING_BEAT
        out.append(_event(event_id, choices, timing, ctx,
                          effects=BEAT_EFFECTS.get(event_id)))
    return out


# --------------------------------------------------- the RANDOM story pool --
# ~135 one-shot stories with no fixed turn, each with its OWN master story (the
# families that share one are excluded). Measured over 1,741 real careers in
# captures/bot_logs by tools/gen_trackblazer_event_pool.py, which writes
# data/trackblazer_event_pool.json:
#
#   ONE PER TURN AT MOST. 0 of ~128k real turns carried two pool events; about
#   a quarter of turns carry one (two of them, 28 and 41, about half: they
#   follow turns a seasonal beat holds).
#   THEIR OWN TURNS. Most fire anywhere in 3-71 outside summer camp; the rest
#   only in their own window (203573/203574/203578/203579 on 17-22, 41-46 and
#   65-70; 203580/203581 on 17/41/65; summer camp has its own set; ...), the
#   ids sharing a window splitting it between them.
#   ONCE PER CAREER, no id ever repeats.
#   THEY PAY. Every id pays one fixed thing (turn_hits/choices in the JSON);
#   the 31 two-choice ones offer a skill hint as choice 2.
#
# The draw follows the corpus directly: on turn T a pool event fires with the
# measured P(T) (careers that saw one / careers that reached T), and which one
# is weighted by how often each still-unfired id fired on T. The whole career's
# schedule is drawn at once from career_salt, so a re-poll of the same turn --
# these are produced on every exec_command until served -- always answers the
# same, and a second id can never slip into a turn whose own already went out.
_POOL_PATH = Path(__file__).resolve().parents[3] / "data" / "trackblazer_event_pool.json"
_pool_cache: dict | None = None


def _pool() -> dict:
    """{"events": {event_id: entry}, "turn_p": {turn: P(a pool event)},
    "weights": {turn: [(event_id, hits)]}}."""
    global _pool_cache
    if _pool_cache is None:
        try:
            with open(_POOL_PATH, encoding="utf-8") as fh:
                raw = json.load(fh)
        except OSError:
            log.warning("trackblazer: no event pool at %s; pool events disabled",
                        _POOL_PATH)
            raw = {}
        events, weights = {}, {}
        for key, ent in (raw.get("events") or {}).items():
            eid = int(key)
            events[eid] = {"story_id": int(ent["story_id"]),
                           "choices": [list(c) for c in ent.get("choices") or [[]]]}
            for t, hits in (ent.get("turn_hits") or {}).items():
                weights.setdefault(int(t), []).append((eid, int(hits)))
        reach = {int(t): int(c) for t, c in (raw.get("turn_reach") or {}).items()}
        turn_p = {t: min(1.0, sum(h for _e, h in ws) / reach[t])
                  for t, ws in weights.items() if reach.get(t)}
        _pool_cache = {"events": events, "turn_p": turn_p,
                       "weights": {t: sorted(ws) for t, ws in weights.items()}}
    return _pool_cache


def _pool_schedule(salt: int) -> dict:
    """{turn: event_id} for one career -- at most one per turn, each id once."""
    pool = _pool()
    rng = random.Random(f"tbpool:{salt}")
    fired, out = set(), {}
    for turn in sorted(pool["weights"]):
        if rng.random() >= pool["turn_p"].get(turn, 0.0):
            continue
        cands = [(e, h) for e, h in pool["weights"][turn] if e not in fired]
        if not cands:
            continue
        pick = rng.choices([e for e, _ in cands], weights=[h for _, h in cands])[0]
        fired.add(pick)
        out[turn] = pick
    return out


@CE.producer("trackblazer_random_pool", priority=CE.PRIO_NORMAL,
             scenario=SCENARIO_ID)
def trackblazer_random_pool(ctx: CE.Ctx) -> list:
    """This turn's pool story, if the career's schedule has one here."""
    turn = int(ctx.turn or 0)
    if turn <= 0:
        return []
    event_id = _pool_schedule(CE.career_salt(ctx.full_state)).get(turn)
    if event_id is None or CE.already_fired(ctx.full_state, f"tb:pool:{event_id}"):
        return []
    ent = _pool()["events"][event_id]
    return [CE.Event(
        event_id=event_id, story_id=ent["story_id"],
        # Timing follows the RESPONSE, not the event: the captured pool
        # entries are split 17 at timing 6 and 9 at timing 3, which is
        # exactly the training-turn / race-turn split (see
        # CE.ENDPOINT_TIMING). 6 is the value used when nothing says.
        play_timing=6, timing_from_endpoint=True,
        choices=[CE.Choice(effects=list(c)) for c in ent["choices"]],
        chara_id=0,
        once_key=f"tb:pool:{event_id}",
        priority=CE.PRIO_NORMAL,
        source="trackblazer_pool")]


def _ending_due(ctx) -> bool:
    """The closer waits for the third Climax leg to have actually been RUN.

    Turn 78 is reachable from turn 77, which is one of the finals window's three
    TRAINING turns -- so the loose "either turn number" match every other beat
    uses would serve the career's ending before its last race. The banked leg is
    the only unambiguous signal that the race is behind us, and the capture
    agrees: 203202 is served in the check_event that acknowledges 203106."""
    if int(ctx.turn or 0) != ENDING_TURN:
        return False
    climax = impl.state(ctx.full_state).get("climax") or {}
    return any(int(r.get("turn") or 0) == ENDING_TURN
               for r in climax.get("results") or [])


@CE.producer("trackblazer_goal_beats", priority=CE.PRIO_SCENARIO,
             scenario=SCENARIO_ID)
def trackblazer_goal_beats(ctx: CE.Ctx) -> list:
    """The three year-end objectives.

    impl.objective_met is what CONSUMES the Grade Point counter -- "ALL Grade
    Points are consumed by each objective and do not carry over" -- and it
    records its verdict, so calling it here (rather than reading win_points
    directly) is what keeps the announcement, the follow-up and any later reader
    agreeing about a year the player has already been shown the result of."""
    out = []
    for turn, arms in GOAL_BEATS.items():
        # STRICT on ctx.turn, unlike every other beat here. An objective turn is
        # a race turn, and the loose match would let the exec_command of the
        # turn BEFORE it (advanced_turn == 24 / 48 / 72) announce the year's
        # result -- and consume the Grade Points -- before the year's last race
        # had been run.
        if int(ctx.turn or 0) != turn:
            continue
        met = impl.objective_met(ctx.full_state, ctx.chara_info, turn)
        announce, follow = arms["met"] if met else arms["missed"]
        if met and random.Random("tbgoal:%s:%s" % (CE.career_salt(ctx.full_state), turn)
                                 ).random() < ALT_ARM_SHARE:
            announce, follow = arms["missed"]
        pay = GOAL_MET_EFFECTS.get(turn, {}) if met else {}
        out.append(_event(announce, 1, GOAL_TIMING, ctx,
                          effects=pay.get("announce")))
        if not met:
            out.append(_event(follow, 1, GOAL_TIMING, ctx))
            continue
        tier = year_end_tier(ctx.full_state, ctx.chara_info, turn)
        if tier == "best":
            out.append(_event(follow, 1, GOAL_TIMING, ctx, effects=pay.get("follow")))
        elif tier == "fallback":
            out.append(_event(YEAR_END_FALLBACK_EVENT[turn], 1, GOAL_TIMING, ctx,
                              effects=_UNIQUE_ONLY))
    return out
