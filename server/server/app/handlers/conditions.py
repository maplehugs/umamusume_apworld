"""Career CONDITIONS (chara_effect_id_array) and what they actually DO.

Names/descriptions are master.mdb text_data cat 142 (name) / 143 (effect text);
the mechanics below are those descriptions turned into rules. Before this, only
Practice Poor/Perfect did anything -- every other condition was a cosmetic id on
the wire (live-reported).

  1  Night Owl          "Lack of sleep may cause her Mood to drop."
  2  Slacker            "May not show up to training."
  3  Skin Outbreak      "May suffer drops in Mood."
  4  Slow Metabolism    "Cannot gain Speed from training."
  5  Migraine           "Cannot gain improvements in Mood."
  6  Practice Poor      increased training-failure chance   (in training_formula)
  7  Fast Learner       "Gains all kinds of tactical hints." -> 10% SP discount
  8  Charming           "Builds friendships faster"        -> +2 bond per training
  9  Hot Topic          "Builds rapport with fans"         -> bonus fan gain
 10  Practice Perfect O decreased failure chance            (in training_formula)
 11  Practice Perfect @ greatly decreased failure chance    (in training_formula)
 12  Under the Weather  greatly increased failure chance + mood risk
 13  Shining Brightly   decreased failure chance + no mood loss

Only the ids the URA career can actually grant are modeled; the rest (fan
promises, scenario-specific ones) pass through untouched.

JP-only ids (text_data 142/143 in JP master; Global has none of them, so on
Global everything below keyed on them is inert):

 25 ポジティブ思考 / 41, 42 メンタルガード  block ONE mood drop, then vanish
 26 幸運体質 / 43 リカバリー精神            block ONE bad condition, then vanish
 32 リフレッシュの心得  +5 energy at each turn start (single_mode_team)
103, 104 情熱ゾーン  two more Pure Passion groups
"""

from __future__ import annotations

import contextvars
import functools
import random

from .. import config
from .. import master_data

NIGHT_OWL = 1
SLACKER = 2
SKIN_OUTBREAK = 3
SLOW_METABOLISM = 4
MIGRAINE = 5
PRACTICE_POOR = 6
FAST_LEARNER = 7
CHARMING = 8
HOT_TOPIC = 9
PRACTICE_PERFECT = 10
PRACTICE_PERFECT_BIG = 11
UNDER_THE_WEATHER = 12
SHINING_BRIGHTLY = 13

# FAN PROMISES. Smart Falcon's 'Coming to a City Near You ☆' grants exactly one
# of these at random, and master.mdb states the fulfilment rule outright in the
# condition's own effect text (text_data category 143):
#
#   14 Fan Promise (Hokkaido) "Win a race at Sapporo or Hakodate ..."
#   15 Fan Promise (Hokuto)   "... at Fukushima, Niigata, or Morioka ..."
#   16 Fan Promise (Nakayama) "... at Nakayama or Funabashi ..."
#   17 Fan Promise (Kansai)   "... at Kyoto or Hanshin ..."
#   18 Fan Promise (Kokura)   "... at Kokura ..."
#   22 Idol's Promise (Kawasaki) "... at Kawasaki ..."
#
# Winning at one of its racetracks fulfils the promise, which is what unlocks
# the follow-up event ('Connecting ☆ Inspiration'). Racetrack ids are
# race_course_set.race_track_id (text_data category 35 names them).
PROMISE_TRACKS = {
    14: frozenset({10001, 10002}),          # Sapporo, Hakodate
    15: frozenset({10004, 10003, 10105}),   # Fukushima, Niigata, Morioka
    16: frozenset({10005, 10104}),          # Nakayama, Funabashi
    17: frozenset({10008, 10009}),          # Kyoto, Hanshin
    18: frozenset({10010}),                 # Kokura
    22: frozenset({10103}),                 # Kawasaki
}
PROMISES = frozenset(PROMISE_TRACKS)


def promises_held(chara_info: dict) -> set:
    return of(chara_info) & PROMISES


def promise_fulfilled_by(chara_info: dict, track_id) -> int | None:
    """The promise a win at this racetrack fulfils, or None."""
    if not track_id:
        return None
    for cid in promises_held(chara_info):
        if track_id in PROMISE_TRACKS[cid]:
            return cid
    return None


# Conditions that are BAD -- having any of these unlocks the infirmary (#7).
NEGATIVE = frozenset({NIGHT_OWL, SLACKER, SKIN_OUTBREAK, SLOW_METABOLISM,
                      MIGRAINE, PRACTICE_POOR, UNDER_THE_WEATHER})
POSITIVE = frozenset({FAST_LEARNER, CHARMING, HOT_TOPIC, PRACTICE_PERFECT,
                      PRACTICE_PERFECT_BIG, SHINING_BRIGHTLY})

# Per-turn risk that a condition PROCS at all. USER-SUPPLIED for Night Owl
# ("lets say like 20%"); the others keep their earlier approximations.
_CONDITION_PROC_CHANCE = {
    NIGHT_OWL: 0.20,
    SKIN_OUTBREAK: 0.10,
    UNDER_THE_WEATHER: 0.15,
    MIGRAINE: 0.10,
}
# What a proc costs (user-supplied): -10 energy always, and "sometimes" mood.
# The mood share is a KNOB, not ground truth.
CONDITION_PROC_ENERGY = -10
CONDITION_PROC_MOOD_CHANCE = 0.5
# ...except where the effect IS the mood drop. Skin Troubles is user-stated as
# a mood down outright ("that gives you mood downs and is served by chance" --
# the chance is which turns it fires on, not whether it costs mood when it
# does), so rolling the shared 50% on top made it a mood drop on only ~5% of
# afflicted turns: the 10% proc, halved again. Overrides only; anything absent
# keeps CONDITION_PROC_MOOD_CHANCE.
#
# Not measurable from captures/bot_logs, unlike the proc RATE (~11%, see
# _maybe_fire_condition_event): this event is served at the START of a turn, so
# there is no response between it and the turn's own command, and the only
# available baseline already has the training/rest folded in.
CONDITION_PROC_MOOD_CHANCE_BY_ID = {
    SKIN_OUTBREAK: 1.0,
}


def proc_mood_chance(condition_id: int) -> float:
    """How often a proc of this condition costs mood, once it has fired."""
    return CONDITION_PROC_MOOD_CHANCE_BY_ID.get(condition_id,
                                                CONDITION_PROC_MOOD_CHANCE)
# Each condition's OWN story suffix -- the proc plays as a real event rather
# than being folded into the training result (live-reported: "night owl is
# supposed to have an event decreasing the mood, instead its bundled with the
# training"). Present for every PLAYABLE trainee. Slacking Off has a title for
# all 83 but a real story row for only 66; the 17 without one are unreleased
# (user-confirmed 2026-09-09), so nobody reachable is missing a proc story.
CONDITION_STORY_SUFFIX = {
    NIGHT_OWL: 521,        # 'Night Owl'
    SKIN_OUTBREAK: 522,    # 'Skin Troubles'
    MIGRAINE: 722,         # 'Migraine Blues'
    SLACKER: 712,          # 'Slacking Off'
}
SLACKER_NOSHOW_CHANCE = 0.15   # chance a clicked facility is skipped entirely
_NIGHT_OWL_MOOD_CHANCE = _CONDITION_PROC_CHANCE[NIGHT_OWL]
_SKIN_OUTBREAK_MOOD_CHANCE = _CONDITION_PROC_CHANCE[SKIN_OUTBREAK]
_WEATHER_MOOD_CHANCE = _CONDITION_PROC_CHANCE[UNDER_THE_WEATHER]


# Pure Passion (text_data cat 142 ids 100/101/102, one per group card): the
# second half of its own description is "and immune to Night Owl and Slacker".
# The ids are listed here rather than imported from pal_cards to keep this
# module free of handler imports; pal_cards.pure_passion_conditions() is the
# same set, derived from the cards.
PURE_PASSION_IDS = frozenset({100, 101, 102, 103, 104})
_PURE_PASSION_IMMUNE = frozenset({NIGHT_OWL, SLACKER})


def pure_passion(chara_info: dict) -> bool:
    """Whether any group's Pure Passion is currently up."""
    return bool(of(chara_info) & PURE_PASSION_IDS)


def immune(chara_info: dict, condition_id: int) -> bool:
    """Whether a condition the trainee HAS is currently doing nothing.

    Pure Passion does not cure Night Owl or Slacker -- the trainee keeps them,
    and gets them back when the buff lapses -- it stops them PROCCING, which is
    what "immune to" means for two conditions that only ever act by rolling."""
    return condition_id in _PURE_PASSION_IMMUNE and pure_passion(chara_info)


def rolled_conditions(chara_info: dict) -> list:
    """Which NEGATIVE conditions proc this turn, each rolled separately.
    Shining Brightly suppresses them all."""
    if has(chara_info, SHINING_BRIGHTLY):
        return []
    conds = of(chara_info)
    return [cid for cid, p in _CONDITION_PROC_CHANCE.items()
            if cid in conds and not immune(chara_info, cid)
            and random.random() < p]

# Charming is a flat +2 on each partner's training bond (7 -> 9), not a
# doubling (7 -> 14) -- user-reported 2026-09-30 as bond filling far too fast.
# The +7 base itself is capture-pinned (52/52 in fixtures/capture_06d26c).
CHARMING_BOND_BONUS = 2
HOT_TOPIC_FAN_MULTIPLIER = 1.2
FAST_LEARNER_SP_DISCOUNT = 0.10


def of(chara_info: dict) -> set:
    return {int(c) for c in (chara_info.get("chara_effect_id_array") or [])
            if isinstance(c, (int, float, str)) and str(c).lstrip("-").isdigit()}


def has(chara_info: dict, condition_id: int) -> bool:
    return condition_id in of(chara_info)


def any_negative(chara_info: dict) -> bool:
    return bool(of(chara_info) & NEGATIVE)


def add(chara_info: dict, condition_id: int) -> bool:
    """Grant a condition (idempotent). Returns whether it was newly added."""
    arr = chara_info.setdefault("chara_effect_id_array", [])
    if condition_id in arr:
        return False
    if blocks_bad_condition(chara_info, condition_id):
        return False
    arr.append(condition_id)
    return True


def remove(chara_info: dict, condition_id: int) -> bool:
    arr = chara_info.get("chara_effect_id_array") or []
    if condition_id not in arr:
        return False
    chara_info["chara_effect_id_array"] = [c for c in arr if c != condition_id]
    return True


def cure_one_negative(chara_info: dict) -> int | None:
    """Remove one negative condition. Returns its id."""
    bad = sorted(of(chara_info) & NEGATIVE)
    if not bad:
        return None
    remove(chara_info, bad[0])
    return bad[0]


def cure_negatives_by_chance(chara_info: dict, chance: float, rng=None) -> list:
    """Roll SEPARATELY for each negative condition and remove the ones that
    pass. Returns the ids cured.

    The infirmary's real behaviour (user-supplied): it is a per-condition roll,
    not 'cure one'. With several debuffs a visit can clear some and leave the
    rest, which the old cure-one model could not express."""
    import random as _random
    r = rng or _random
    cured = []
    for cid in sorted(of(chara_info) & NEGATIVE):
        if r.random() < chance:
            remove(chara_info, cid)
            cured.append(cid)
    return cured


def bond_gain(chara_info: dict, base: int) -> int:
    """Charming adds a flat +2 to bond gained from training. The
    bond_gain_multiplier testing knob (client_config.json / admin panel Career
    tuning) then scales the total."""
    gain = base + CHARMING_BOND_BONUS if has(chara_info, CHARMING) else base
    mult = config.get_float("bond_gain_multiplier")
    return gain if mult is None or gain <= 0 else max(0, int(round(gain * mult)))


def fan_gain(chara_info: dict, base: int) -> int:
    """Hot Topic boosts fans earned."""
    if has(chara_info, HOT_TOPIC):
        return int(base * HOT_TOPIC_FAN_MULTIPLIER)
    return base


def sp_discount(chara_info: dict) -> float:
    return FAST_LEARNER_SP_DISCOUNT if has(chara_info, FAST_LEARNER) else 0.0


def blocks_stat(chara_info: dict, stat: str) -> bool:
    """Slow Metabolism: 'cannot gain Speed from training'."""
    return stat == "speed" and has(chara_info, SLOW_METABOLISM)


def blocks_mood_gain(chara_info: dict) -> bool:
    """Migraine: 'cannot gain improvements in Mood'."""
    return has(chara_info, MIGRAINE)


def skips_training(chara_info: dict) -> bool:
    """Slacker: 'may not show up to training' -- the clicked facility does
    nothing this turn (energy is still spent by the real game's flavour, but
    the gains are lost)."""
    return (has(chara_info, SLACKER) and not immune(chara_info, SLACKER)
            and random.random() < SLACKER_NOSHOW_CHANCE)


def turn_mood_penalty(chara_info: dict) -> int:
    """Mood lost to per-turn condition risks (Night Owl / Skin Outbreak /
    Under the Weather). Shining Brightly protects against it."""
    if has(chara_info, SHINING_BRIGHTLY):
        return 0
    drop = 0
    conds = of(chara_info)
    if (NIGHT_OWL in conds and not immune(chara_info, NIGHT_OWL)
            and random.random() < _NIGHT_OWL_MOOD_CHANCE):
        drop += 1
    if SKIN_OUTBREAK in conds and random.random() < _SKIN_OUTBREAK_MOOD_CHANCE:
        drop += 1
    if UNDER_THE_WEATHER in conds and random.random() < _WEATHER_MOOD_CHANCE:
        drop += 1
    return drop


def apply_mood(chara_info: dict, delta: int) -> int:
    """Change mood, honouring Migraine (no GAINS) and clamping 1..5."""
    if delta > 0 and blocks_mood_gain(chara_info):
        return 0
    if delta < 0:
        return -drop_mood(chara_info, -delta)
    cur = chara_info.get("motivation", 3) or 3
    new = max(1, min(5, cur + delta))
    chara_info["motivation"] = new
    return new - cur


# ONE-SHOT GUARDS (JP). Each is used up by the first thing it stops, and the
# response then says so in not_down_parameter_info (dump.cs NotDownParameterInfo)
# -- that is what makes the client play the "kept her mood" line instead of
# silently showing nothing. Capture-confirmed for 25 (umacap 2026-09-28 turns
# 27/29, 2026-09-29 turn 51; CarrotJuicer Onsen x2): a mood-down event resolves
# with motivation unchanged, 25 gone from chara_effect_id_array, and
#   param_guard_array [{"chara_effect_id": 25, "status_type": 20}]
# (status_type = ParameterGainLimitType, 20 mood). Holding 26 alongside did not
# spend it. 41/42 share 25's text; 26/43 are the bad-condition twins, whose
# BadConditionGuardInfo is {chara_effect_id, target_chara_effect_id} (the
# condition it stopped) -- shape from dump.cs, never seen used in a capture.
# Neither kind expires by itself: 25 was held turns 16-27, 26 to the career end.
MOOD_GUARDS = (25, 41, 42)          # master disp_order: 25 first
BAD_CONDITION_GUARDS = (26, 43)
REFRESH_MIND = 32

# What this request's guards stopped. Set per request by dispatch
# (begin_request) and turned into the response field by guard_report.
_GUARD_LOG: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "condition_guard_log", default=None)


def begin_request() -> None:
    _GUARD_LOG.set([])


def _log_guard(kind: str, entry: dict) -> None:
    log = _GUARD_LOG.get()
    if log is not None:
        log.append((kind, entry))


def guard_report() -> dict | None:
    """not_down_parameter_info for this request, or None when nothing fired."""
    log = _GUARD_LOG.get()
    if not log:
        return None
    return {"evaluation_chara_id_array": [],
            "param_guard_array": [e for k, e in log if k == "param"],
            "bad_condition_guard_array": [e for k, e in log if k == "bad"]}


def _held_guard(chara_info: dict, guards: tuple) -> int | None:
    held = of(chara_info)
    return next((g for g in guards if g in held), None)


def _spend_guard(chara_info: dict, guards: tuple) -> int | None:
    g = _held_guard(chara_info, guards)
    if g is not None:
        remove(chara_info, g)
    return g


# PREVIEW side (get_choice_reward): the real server swaps the plain line for
# the guarded one while a guard is up, without spending it. Display 40
# '{0}になる\n{1}により{0}になりません' is capture-confirmed as (condition,
# guard) -- (4, 26) x7 and (6, 26) x2 across umacap + headless. Display 38
# '{0} -{1}\n{2}により{0}は下がりません' is its mood twin by text alone
# (20, amount, guard): no capture previews a mood drop while 25 is held.
def mood_guard_preview(chara_info: dict | None) -> int | None:
    """The guard a mood drop would hit right now, or None."""
    if not chara_info or (chara_info.get("motivation", 3) or 3) <= 1:
        return None
    return _held_guard(chara_info, MOOD_GUARDS)


def bad_guard_preview(chara_info: dict | None, condition_id: int) -> int | None:
    """The guard that would stop this condition right now, or None."""
    if (not chara_info or int(condition_id) not in NEGATIVE
            or has(chara_info, condition_id)):
        return None
    return _held_guard(chara_info, BAD_CONDITION_GUARDS)


def drop_mood(chara_info: dict, n: int) -> int:
    """Lower mood by n (floor 1) unless a mood guard takes the hit. Returns how
    far mood actually fell. A guard blocks the whole drop, however large --
    'やる気ダウンを一度防ぐ' counts drops, not steps. A drop that could not
    move mood anyway (already Awful) does not spend it; no capture shows
    that case either way."""
    cur = chara_info.get("motivation", 3) or 3
    new = max(1, cur - max(0, n))
    if new == cur:
        return 0
    g = _spend_guard(chara_info, MOOD_GUARDS)
    if g is not None:
        _log_guard("param", {"chara_effect_id": g, "status_type": 20})
        return 0
    chara_info["motivation"] = new
    return cur - new


def blocks_bad_condition(chara_info: dict, condition_id: int) -> bool:
    """Whether a bad-condition guard stops this condition being added
    (spending the guard). Call before adding a condition."""
    if int(condition_id) not in NEGATIVE or has(chara_info, condition_id):
        return False
    g = _spend_guard(chara_info, BAD_CONDITION_GUARDS)
    if g is None:
        return False
    _log_guard("bad", {"chara_effect_id": g, "target_chara_effect_id": int(condition_id)})
    return True


# リフレッシュの心得 (32): capture-derived from 637 complete holds in the JP
# CarrotJuicer corpus (Onsen + Ramen, granted by 809050004 / 809001104). Every
# turn it is held opens with event 21148 / story 800001002 'リフレッシュ上手！'
# worth +5 energy (capped at max_vital; 1,365 uncapped samples all +5), and the
# firing that ends it removes 32 as it resolves. It lasted 3/4/5/6 firings
# 327/154/80/76 times -- 51/24/13/12%, i.e. three sure firings, then a coin
# flip after each, cut off at six.
REFRESH_EVENT_ID = 21148
REFRESH_STORY_ID = 800001002
REFRESH_ENERGY = 5
REFRESH_MIN_FIRES = 3
REFRESH_MAX_FIRES = 6
REFRESH_END_CHANCE = 0.5


def refresh_ends(fires: int, rng=random) -> bool:
    """Whether the firing numbered `fires` (1-based) is the last one."""
    if fires < REFRESH_MIN_FIRES:
        return False
    return fires >= REFRESH_MAX_FIRES or rng.random() < REFRESH_END_CHANCE


# SCHEDULED TRAINEE CONDITIONS -- master.mdb single_mode_chara_effect_buff.
# One row per trainee story beat: the condition effect_id is held from
# start_turn to end_turn, and races run in that window (only race program_id,
# when it is set) get the row's stat adds and aptitude-grade adds. Names and
# texts are the usual text_data 142/143, e.g. 1073's 凍りついた翼 (-50 all
# stats, turns 13-44) or 1131's 前程万哩 (middle-distance aptitude -2, turns
# 34-48). JP carries 8 rows; Global's table is empty, so this does nothing there.
_BUFF_STATS = {"speed": "speed_add", "stamina": "stamina_add", "power": "power_add",
               "guts": "guts_add", "wiz": "wiz_add"}
_BUFF_APTITUDES = {
    "proper_ground_turf": "turf_add", "proper_ground_dirt": "dirt_add",
    "proper_distance_short": "short_add", "proper_distance_mile": "mile_add",
    "proper_distance_middle": "middle_add", "proper_distance_long": "long_add",
    "proper_running_style_nige": "nige_add", "proper_running_style_senko": "senko_add",
    "proper_running_style_sashi": "sashi_add", "proper_running_style_oikomi": "oikomi_add",
}


@functools.lru_cache(maxsize=1)
def _scheduled_buffs() -> tuple:
    if not master_data.has_table("single_mode_chara_effect_buff"):
        return ()
    return tuple(dict(r) for r in master_data.query(
        "SELECT * FROM single_mode_chara_effect_buff ORDER BY id"))


def _active_buffs(chara_info: dict) -> list:
    chara_id = (chara_info.get("card_id") or 0) // 100
    turn = chara_info.get("turn")
    if not chara_id or turn is None:
        return []
    return [r for r in _scheduled_buffs()
            if r["chara_id"] == chara_id and r["start_turn"] <= turn <= r["end_turn"]]


def sync_scheduled(chara_info: dict) -> None:
    """Hold each scheduled condition exactly while its turn window is open."""
    chara_id = (chara_info.get("card_id") or 0) // 100
    rows = [r for r in _scheduled_buffs() if r["chara_id"] == chara_id]
    if not rows:
        return
    active = {r["effect_id"] for r in _active_buffs(chara_info)}
    for r in rows:
        if r["effect_id"] in active:
            add(chara_info, r["effect_id"])
        else:
            remove(chara_info, r["effect_id"])


def apply_race_buffs(race_chara: dict, program_id: int | None) -> None:
    """Add the scheduled stat and aptitude changes to a career race entry
    (a copy of chara_info). Aptitude grades stay within G..S (1..8)."""
    for r in _active_buffs(race_chara):
        if r["program_id"] and r["program_id"] != program_id:
            continue
        for key, col in _BUFF_STATS.items():
            if r[col]:
                race_chara[key] = max(1, (race_chara.get(key) or 0) + r[col])
        for key, col in _BUFF_APTITUDES.items():
            if r[col]:
                race_chara[key] = max(1, min(8, (race_chara.get(key) or 1) + r[col]))
