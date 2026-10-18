"""Daily races (daily_race/*), daily legend races (daily_legend_race/*) and
the skip shortcut (daily_race_skip/race_skip).

Sources of truth, in order:
  * ONE real capture set (UmaDumpy 20260717_180912 transactions 0026-0029,
    deshifted): daily_race/index, daily_race/recovery_ticket and
    daily_race_skip/race_skip -- their response shapes are copied exactly.
  * The Icarus bot's requests to the REAL server for everything uncaptured
    (race_entry / reflect_item_effect / race_start / replay_check and the whole
    daily_legend_race family) -- request keys are authoritative, responses are
    synthesized to the schemas Icarus documents.
  * master.mdb: `daily_race` (8 rows), `daily_race_npc` (176),
    `daily_legend_race` (29), `legend_race_boss_npc` (45), `legend_race_npc`
    (715). The *_odds_id columns on the race rows reference NO existing table
    (verified dangling), so per-run drops are server-defined below.

Races run through the REAL simulator (app/simulation/race_simulator.py), same
as practice_race: the player's veteran (with the requested running_style) vs
the race's own master-data NPC field. If the sim can't run (no Node, course
lookup fails) a deterministic stat-based outcome roll takes over so the
endpoint still answers.

DAILY RESET: keyed off the SERVED servertime day (patch._servertime(); reset
05:00 JST = 20:00 UTC). Both regions serve real time ("servertime": "now"), so
the day rolls like the real server's. On the first touch of a new day the
tickets are refilled to their caps -- item 96 to ticket_cap() (3 + any
RaceCount campaign), item 168 to its item_data.limit_num (1) -- which is what
every real load/index at the start of a day shows (JP umacap 09-28..10-03:
96=6 inside campaign 1138, 168=1). Entries spend them (reflect_item_effect /
race_skip) and are refused at 0, so a day's runs are the real number. This
replaced a frozen-time workaround that refilled item 96 on EVERY
daily_race/index call, i.e. unlimited daily races.
"""

from __future__ import annotations

import copy
import functools
import logging
import random
import zlib

from .. import master_data
from .. import patch
from .. import race_conditions
from .. import rating_formula
from .. import state as state_store
from ..simulation import race_simulator
from . import limited_shop, practice_race, registry, shop, trained_chara
from ..result_codes import ResultCode, refuse

log = logging.getLogger("uma-server")

STATE_KEY = "daily_race_state"

# ---------------------------------------------------------------------------
# SERVER-DEFINED reward tuning. master.mdb's normal/rare/bonus/drop/victory
# *_odds_id columns dangle (no odds table ships in the client db), so the
# per-run drop amounts are ours. Calibrated against the one real race_skip
# capture (0029.json: money race difficulty 4, rank 1 -> normal 4000 + five
# rare rolls of 800/900/1200 = 9300 total; rank 2 -> four rolls = 7700), and
# EXTENDED 2026-08-19 against a second real capture (captures/20260819_
# 173442, a genuine daily_race playthrough -- 3 full race_entry/race_start/
# replay_check cycles plus a 3x race_skip): both money-track normal values
# it covered (difficulty 3 -> 3000, difficulty 4 -> 4000) matched this table
# exactly, and it surfaced a rare-roll value (600) this table didn't have
# yet -- added below.
_DROP_NORMAL_BY_DIFFICULTY = {1: 1000, 2: 2000, 3: 3000, 4: 4000,
                              5: 5000}   # 5: JP race 9, 465/465 CarrotJuicer runs
_DROP_RARE_VALUES = (600, 800, 900, 1200)      # observed rare-roll sizes
_DROP_RARE_VALUES_BY_DIFFICULTY = {5: (2900, 3000, 3200)}   # JP race 9, 2,325 rolls
# Rare rolls per finishing place. Ranks 1-3 from the first captures; 4 and 5
# -> 2 rolls from JP umacap 10-03 race 10 (rank 4) and Global 20260825_094909
# 0047 (rank 5); rank 12 -> 1 roll from 20260819_173442 0026. Ranks 6-11 have
# never been captured and stay at 1.
_DROP_RARE_ROLLS_BY_RANK = {1: 5, 2: 4, 3: 3, 4: 2, 5: 2}
# The drop CURRENCY is read from the race row's pick_up_item_* (money races
# drop 91/59, support-pt races drop 30/110). Support-pt does NOT simply pay
# money's numbers at some flat rate -- the 2026-08-19 capture caught two real
# support-pt tiers dead to rights (difficulty 2 via replay_check, difficulty
# 3 via 3x race_skip) and neither matches a 1/4 (or any other flat) scaling
# of the money table: normal 400/600 vs money's 2000/3000 scaled, rare sets
# {70,80,100}/{100,120,150} vs money's shared {600,800,900,1200}. So support-
# pt gets its OWN confirmed-only table below; difficulty 4 was added from the
# 6x race_skip in captures/20260825_094909 (0047). Difficulty 1 is NOT in it
# (never captured) and falls back to the old flat-rate guess.
_SUPPORT_PT_RATE = 0.25                        # fallback ONLY -- diff 1, unconfirmed
_SUPPORT_PT_NORMAL_BY_DIFFICULTY = {2: 400, 3: 600, 4: 800}     # CONFIRMED (real capture)
_SUPPORT_PT_RARE_VALUES_BY_DIFFICULTY = {2: (70, 80, 100),      # CONFIRMED (real capture)
                                        3: (100, 120, 150),
                                        4: (150, 200, 260)}
# JP's item races (daily_race group 4, rows 5-8 and 10, pick_up category 11)
# pay no currency at all. Real race 10 (12 umacap runs, 10-03): normal is ONE
# 夢の煌めき (item 44, category 93) every run, and each rare roll is a single
# category-11 item. The rare pool is server-side and wider than the row's
# pick_up items (shoes, race leis, hint books were all seen); the pick_up items
# stand in for it here. NOT EXACT -- the real pool's odds are not in master.
_ITEM_RACE_CATEGORY = 11
_ITEM_RACE_NORMAL = (93, 44, 1)
# JP-only extra drop: トレーナーメダル (item 134, category 161), a flat 10 per
# daily race and 30 per daily legend race on every real JP run (465 race_skip
# runs, 12 umacap runs, 53 legend skips, 2 legend replay_checks). Global pays
# none (every Global capture). It feeds JP's training report, so it is gated
# on that feature's master table rather than on a region check.
_MEDAL_ITEM = (161, 134)
_MEDAL_DAILY, _MEDAL_LEGEND = 10, 30

# Legend victory: the boss's puzzle piece comes straight from the master row
# (first_clear/pick_up category 102 = 10 pieces on first clear, 1 per win,
# resolved through card_data.get_piece_id); the money on top is ours.
# Daily legend drop (drop_reward_odds_id has no table in either master, so the
# amounts are fitted to the captures): a win drops 4000 Monies (JP umacap 10-02
# and 10-03 replay_checks, both 4000), a loss 1000 support pt (Global
# 20260825_094909 0045, rank 2).
_LEGEND_WIN_DROP = (91, 59, 4000)
_LEGEND_LOSS_DROP = (30, 110, 1000)
# First win of a legend race's course grants its race_trophy, and the trophy
# pays 100 carats (both JP umacap replay_checks: trophy_reward_info
# {90, 43, 100}). The carats are NOT in reward_summary_info there (add_fcoin
# was the first clear's 150 alone), so they are credited without being echoed.
_TROPHY_REWARD = (90, 43, 100)

# daily_race/recovery_ticket (captured): spend carats, get the skip tickets
# back and purchase_num +1. Price and per-day limit are master.mdb
# `daily_race_billing` (see _billing).
_TICKET_ITEM_ID = 96                          # daily race ticket (item_data limit_num 3)
_LEGEND_TICKET_ITEM_ID = 168                  # "Daily Legend Race Ticket" (text_data cat 23)
_TICKET_CAP = 3                               # base cap, outside any campaign

# Paddock race items, master.mdb item_category 150 (116-120). effect_type 10
# raises mood to Great, 20/30 set weather/ground to effect_value, 40 moves the
# runner into brackets 1-3 (target 1) or 6-8 (target 2).
_RACE_ITEM_CATEGORY = 150
_EFFECT_MOOD, _EFFECT_WEATHER, _EFFECT_GROUND, _EFFECT_BRACKET = 10, 20, 30, 40
_MOOD_GREAT = 5
_BRACKETS = {1: range(1, 4), 2: range(6, 9)}

# campaign_data (dump.cs MasterCampaignData): TargetCategory 2 = DailyRace,
# EffectType 2 = RaceCount. Its effect_value_1 is ADDED to the base cap --
# the real server's load/index common_define.daily_race_ticket_max_num read 6
# inside campaign 224's window (data/seeds/load_index_fresh.json, servertime
# 1787060108, effect_value_1 3) and 3 in the 20260717 captures before it.
_CAMPAIGN_TARGET_DAILY_RACE = 2
_CAMPAIGN_EFFECT_RACE_COUNT = 2

_ITEM_TYPE_CARAT = 90                         # -> coin_info (fcoin)
_ITEM_TYPE_MONEY = 91                         # item 59 in item_list
_ITEM_TYPE_PIECE = 102                        # -> piece_list

_RESET_UTC_HOUR = 20                          # 05:00 JST daily reset


# ---------------------------------------------------------------------------
# envelopes

def _ok(data: dict) -> dict:
    return {"response_code": 1,
            "data_headers": {"result_code": 1, "notifications": {}}, "data": data}


def _refuse(code: int = ResultCode.PARAM_ERROR) -> dict:
    return refuse(code)


def _already_played() -> dict:
    """NOT_ENOUGH_ERROR (1053) = 'daily already done today' (Icarus-documented)."""
    return refuse(ResultCode.NOT_ENOUGH_ERROR)


# ---------------------------------------------------------------------------
# per-viewer daily state

@functools.lru_cache(maxsize=1)
def _billing() -> tuple:
    """(frequency, pay_cost) from master.mdb `daily_race_billing`: purchases
    allowed per served day, and the carat price of each. Global's row is
    (1, 100), JP's (1, 30) -- the old hardcoded 30 was JP's price."""
    row = master_data.query_one(
        "SELECT frequency, pay_cost FROM daily_race_billing ORDER BY id LIMIT 1")
    if row is None:
        return (0, 0)
    return ((row["frequency"] or 0), (row["pay_cost"] or 0))


def _served_day() -> int:
    return (patch._servertime() - _RESET_UTC_HOUR * 3600) // 86400


def ticket_cap(now: int | None = None) -> int:
    """The daily race ticket cap right now: the base 3 plus every active
    DailyRace RaceCount campaign (3 -> 6 during those events). Checked against
    the SERVED time, the same clock the client tests campaign windows with."""
    now = int(now if now is not None else patch._servertime())
    try:
        row = master_data.query_one(
            "SELECT COALESCE(SUM(effect_value_1), 0) AS bonus FROM campaign_data "
            "WHERE target_type=? AND effect_type_1=? AND start_time<=? AND end_time>=?",
            (_CAMPAIGN_TARGET_DAILY_RACE, _CAMPAIGN_EFFECT_RACE_COUNT, now, now))
    except Exception:
        log.exception("daily race RaceCount campaign lookup failed; using the base cap")
        return _TICKET_CAP
    return _TICKET_CAP + int(row["bonus"] if row else 0)


def _daily_state(full_state: dict) -> dict:
    """The viewer's daily-race block, rolled to the current served day, with
    the day's tickets refilled on the first touch of a new day."""
    drs = full_state.setdefault(STATE_KEY, {})
    day = _served_day()
    if drs.get("day") != day:
        drs["day"] = day
        drs["daily"] = {}      # str(daily_race_id) -> {is_played, is_cleared}
        drs["legend"] = {}     # str(daily_legend_race_id) -> {is_played, is_cleared}
        drs["purchase_num"] = 0
        drs.pop("pending", None)
    drs.setdefault("daily", {})
    drs.setdefault("legend", {})
    drs.setdefault("purchase_num", 0)
    drs.setdefault("daily_cleared_ever", [])   # lifetime first-clear tracking
    drs.setdefault("legend_cleared_ever", [])
    # Lifetime daily-race runs, played or skipped -- mission condition_type
    # 200008 (missions.daily_race_entries).
    drs.setdefault("entries_total", 0)
    if drs.get("ticket_day") != day:
        drs["ticket_day"] = day
        for item_id, cap in ((_TICKET_ITEM_ID, ticket_cap()),
                             (_LEGEND_TICKET_ITEM_ID, _legend_ticket_cap())):
            have = _item_count(full_state, item_id)
            if have < cap:
                _add_item(full_state, item_id, cap - have)
    return drs


def refresh_tickets(full_state: dict) -> bool:
    """Roll the daily state and refill today's tickets if that has not
    happened yet. True when it just did -- load/index uses that to re-serve
    item_list, which is where the client reads its ticket counts from."""
    stale = (full_state.get(STATE_KEY) or {}).get("ticket_day") != _served_day()
    _daily_state(full_state)
    return stale


@functools.lru_cache(maxsize=1)
def _legend_ticket_cap() -> int:
    """item_data.limit_num of the Daily Legend Race Ticket (1 in both
    masters) -- what the real load/index shows at the start of a day."""
    row = master_data.query_one(
        "SELECT limit_num FROM item_data WHERE id=?", (_LEGEND_TICKET_ITEM_ID,))
    return (row["limit_num"] if row else 0) or 1


# ---------------------------------------------------------------------------
# reward granting (viewer containers -- keys per collection.py)

def _items(full_state: dict) -> list:
    return full_state.setdefault("item_list_state", [])


def _item_count(full_state: dict, item_id: int) -> int:
    return next((i.get("number", 0) for i in _items(full_state)
                 if i.get("item_id") == item_id), 0)


def _add_item(full_state: dict, item_id: int, delta: int) -> int:
    for i in _items(full_state):
        if i.get("item_id") == item_id:
            i["number"] = max(0, (i.get("number") or 0) + delta)
            return i["number"]
    if delta > 0:
        _items(full_state).append({"item_id": item_id, "number": delta})
        return delta
    return 0


def _empty_summary() -> dict:
    return {"add_item_list": [], "add_piece_list": [], "add_card_list": [],
            "add_card_bonus_info": None, "add_support_card_list": [],
            "add_support_card_num_array": [], "add_honor_list": [], "add_chara_list": [],
            "add_cloth_list": [], "add_music_list": [], "add_story_id_array": [],
            "add_fcoin": 0, "add_present_num": 0, "add_total_fan": 0,
            "new_chara_profile_array": [], "force_update_honor_id": 0}


def _grant(full_state: dict, category: int, item_id: int, num: int, summary: dict) -> None:
    """Apply one reward to the viewer's containers AND record it in a
    reward_summary_info, mirroring shop.py's granting so the client sees it
    live. Carats (90) go to coin_info fcoin; pieces (102) to piece_list;
    everything else (money 91/59, support pt 30/110, ...) is an item count."""
    if not item_id or num <= 0:
        return
    if category == _ITEM_TYPE_CARAT:
        wallet = full_state.setdefault("coin_info_state", {"fcoin": 0, "coin": 0})
        wallet["fcoin"] = (wallet.get("fcoin") or 0) + num
        summary["add_fcoin"] += num
    elif category == _ITEM_TYPE_PIECE:
        pieces = full_state.setdefault("piece_list_state", [])
        p = next((p for p in pieces if p.get("piece_id") == item_id), None)
        if p:
            p["piece_num"] = (p.get("piece_num") or 0) + num
        else:
            pieces.append({"piece_id": item_id, "piece_num": num})
        summary["add_piece_list"].append({"piece_id": item_id, "piece_num": num})
    else:
        _add_item(full_state, item_id, num)
        summary["add_item_list"].append({"item_id": item_id, "number": num})


def _grant_row_items(full_state: dict, row, prefix: str, summary: dict) -> list[dict]:
    """Grant the row's first_clear_item_*/pick_up_item_* triple; category 102
    entries are card ids and get resolved through card_data.get_piece_id.
    Returns the granted entries as {item_type, item_id, item_num} dicts, for
    callers that need to echo them back in a *_reward_array."""
    entries = []
    for i in (1, 2, 3):
        cat = row[f"{prefix}_item_category_{i}"] or 0
        iid = row[f"{prefix}_item_id_{i}"] or 0
        num = row[f"{prefix}_item_num_{i}"] or 0
        if not iid or num <= 0:
            continue
        if cat == _ITEM_TYPE_PIECE:
            iid = _piece_id_for_card(iid)
        _grant(full_state, cat, iid, num, summary)
        entries.append({"item_type": cat, "item_id": iid, "item_num": num})
    return entries


def _piece_id_for_card(card_id: int) -> int:
    row = master_data.query_one(
        "SELECT get_piece_id FROM card_data WHERE id=?", (card_id,))
    return row["get_piece_id"] if row and row["get_piece_id"] else card_id


# ---------------------------------------------------------------------------
# master.mdb lookups

def _daily_race_row(daily_race_id):
    return master_data.query_one(
        "SELECT * FROM daily_race WHERE id=?", (daily_race_id,))


def _legend_race_row(daily_legend_race_id):
    return master_data.query_one(
        "SELECT * FROM daily_legend_race WHERE id=?", (daily_legend_race_id,))


def _boss_row(boss_npc_id):
    return master_data.query_one(
        "SELECT * FROM legend_race_boss_npc WHERE id=?", (boss_npc_id,))


def _daily_npc_group(race_instance_id: int) -> int:
    """daily_race_npc.npc_group_id convention (verified for all 8 races):
    5800 + the race instance's suffix, e.g. 580001 -> 5801, 580034 -> 5834."""
    return 5800 + (race_instance_id - 580000)


def _legend_npc_group(boss_npc_id: int) -> int:
    """legend_race_npc.npc_group_id has NO explicit FK anywhere; the mapping
    (boss_npc_id - 103) / 2 + 20 (bosses are odd ids 103..191, groups 20..62)
    was validated by surface/distance coherence: for 28/29 daily_legend_race
    rows the mapped group's NPC aptitudes match the race's course exactly (the
    29th differs only on a mid-vs-long tiebreak for a 2400m race)."""
    return (boss_npc_id - 103) // 2 + 20


def _npc_rows(table: str, group_id: int) -> list:
    return master_data.query(
        f"SELECT * FROM {table} WHERE npc_group_id=? ORDER BY id", (group_id,))


_skill_set_cache: dict = {}


def _skill_array_from_set(skill_set_id: int) -> list[dict]:
    """skill_set row -> wire skill_array [{skill_id, level}]."""
    if skill_set_id in _skill_set_cache:
        return copy.deepcopy(_skill_set_cache[skill_set_id])
    row = master_data.query_one("SELECT * FROM skill_set WHERE id=?", (skill_set_id,))
    skills = []
    if row is not None:
        for i in range(1, 21):
            sid = row[f"skill_id{i}"] or 0
            if sid:
                skills.append({"skill_id": sid, "level": row[f"skill_level{i}"] or 1})
    _skill_set_cache[skill_set_id] = skills
    return copy.deepcopy(skills)


def _base_card_for_chara(chara_id: int) -> int:
    row = master_data.query_one(
        "SELECT id FROM card_data WHERE chara_id=? ORDER BY id LIMIT 1", (chara_id,))
    return row["id"] if row else 0


def _best_running_style(row) -> int:
    apts = {1: row["proper_running_style_nige"], 2: row["proper_running_style_senko"],
            3: row["proper_running_style_sashi"], 4: row["proper_running_style_oikomi"]}
    return max(apts, key=lambda k: apts[k] or 0)


_NPC_STAT_AND_APT = ("speed", "stamina", "pow", "guts", "wiz",
                     "proper_distance_short", "proper_distance_mile",
                     "proper_distance_middle", "proper_distance_long",
                     "proper_running_style_nige", "proper_running_style_senko",
                     "proper_running_style_sashi", "proper_running_style_oikomi",
                     "proper_ground_turf", "proper_ground_dirt")


def _npc_chara(row) -> dict:
    """A daily_race_npc / legend_race_npc row as a chara dict both the sim
    (build_horse_spec) and practice_race._build_race_horse_entry digest.
    Mob rows carry mob_id (the entry builder's mob branch takes over); real
    charas get their base card so the client shows the proper named uma.

    race_dress_id: BUG FIXED 2026-08-19 (live-reported -- entering a daily
    race hung forever on the paddock's background load, a client-side
    NullReferenceException in Gallop.TrainingBg.Load/PaddockViewController
    Base.ShowBackGround), TWICE: the first pass assumed mob rows always
    carry a real usable dress id and should never be nulled, but master.mdb
    shows that's only true for difficulty 2-4 (real values 8/11/12/70/80 --
    confirmed against the real capture, captures/20260819_173442, for money
    diff 3/4 and support-pt diff 2) -- difficulty 1's WHOLE pool (mobs AND
    real characters alike, npc_group_id 5801/5831) stores the exact same
    placeholder (1) real characters use everywhere before their card-based
    dress resolves, and unconditionally passing that placeholder through
    for mobs (who have no card to fall back to) is exactly what hung the
    difficulty-1 paddock. 8 is the real observed floor across every group
    checked (both real-character 6-digit ids and every mob id land at or
    above it) and 1 is the only placeholder ever seen, so a single '< 8 ->
    None' threshold covers both without needing to branch on chara_id."""
    chara = {k: row[k] or 0 for k in _NPC_STAT_AND_APT}
    chara_id = row["chara_id"] or 0
    dress = row["race_dress_id"] or 0
    named = chara_id > 1
    # Identity fields as the real race_entry sends them for EVERY field NPC
    # (Global 20260819_173442 0018 + 20260825_094909 0042, JP umacap 10-02/
    # 10-03): trained_chara_id = single_mode_chara_id = the npc ROW id,
    # card_id 0/nil even for named umas (chara_id + race_dress_id carry them),
    # trainer_name nil, rarity 3 named / 1 mob, talent_level 1, npc_type 0.
    chara.update({
        "viewer_id": 0,
        "trainer_name": None,
        "trained_chara_id": row["id"],
        "single_mode_chara_id": row["id"],
        "chara_id": chara_id if named else 1,
        "card_id": 0,
        "mob_id": row["mob_id"] or 0,
        "race_dress_id": dress if dress >= 8 else None,
        "running_style": _best_running_style(row),
        "skill_array": _skill_array_from_set(row["skill_set_id"] or 0),
        "motivation": 3,
        "rarity": 3 if named else 1,
        "talent_level": 1,
        "npc_type": 0,
        "rank": _rank_for_stats(chara),
        "fans": 0,
        "wins": 0,
    })
    return chara


def _boss_chara(row) -> dict:
    """A legend_race_boss_npc row as a chara dict. The boss row carries its
    own card (card_rarity_data_id = card_id * 100 + rarity) and real dress."""
    chara = {k: row[k] or 0 for k in _NPC_STAT_AND_APT}
    # Real boss entry (Global 20260825_094909 0042 boss 145, JP umacap 10-02
    # boss 325): trained_chara_id = single_mode_chara_id = the boss ROW id,
    # npc_type 3, talent_level 1, trainer_name nil, its own card and dress.
    chara.update({
        "viewer_id": 0,
        "trainer_name": None,
        "trained_chara_id": row["id"],
        "single_mode_chara_id": row["id"],
        "chara_id": row["chara_id"],
        "card_id": (row["card_rarity_data_id"] or 0) // 100 or _base_card_for_chara(row["chara_id"]),
        "mob_id": 0,
        "race_dress_id": row["race_dress_id"],
        "nickname_id": row["nickname_id"] or 0,
        "running_style": _best_running_style(row),
        "skill_array": _skill_array_from_set(row["skill_set_id"] or 0),
        "motivation": 3,
        "rarity": 3,
        "talent_level": 1,
        "npc_type": 3,
        "rank": _rank_for_stats(chara),
        "fans": 0,
        "wins": 0,
    })
    return chara


def index_boss_data(boss_npc_id: int) -> dict:
    """The boss as an INDEX screen shows it: a standalone profile card, not a
    race entrant. Shared by daily_legend_race/index and legend_race/index --
    `boss_data` is a full RaceHorseData in both (dump.cs DailyLegendRaceData
    and LegendRaceData declare the identical field).

    BUG FIXED 2026-09-11 (live-reported: "the UI of starting the legend race
    is extremely broken, buttons everywhere, and the text malformed").
    daily_legend_race/index used to serve boss_data as a two-field stub,
    {chara_id, final_grade}, from an early schema guess. The client wants all
    47 fields of a RaceHorseData; the other 45 deserialized to null/0, which
    is what left the boss card unable to lay itself out.

    Capture-validated against the sibling family's real legend_race/index
    (captures/20260904_232507 tx 17): _boss_chara + _race_horse_array
    reproduce 46 of 47 fields exactly -- every stat, aptitude, skill, plus
    card_id, rarity and race_dress_id. The overrides below are the race
    context an index has none of. The one remaining difference is
    final_grade (capture 12, derived 11); one sample is not enough to
    re-derive the mapping for the other 48 bosses, and it is a cosmetic
    grade label rather than a race input, so the derived value stands.
    """
    boss = _boss_row(boss_npc_id)
    if boss is None:
        return {}
    wire = _race_horse_array([_boss_chara(boss)])[0]
    wire.update({
        "frame_order": None,
        "running_style": None,
        "trainer_name": None,
        "trained_chara_id": boss["id"],
        "single_mode_chara_id": boss["id"],
        "npc_type": 3,
        "talent_level": 1,
        "motivation": 0,
        "popularity": 0,
        "popularity_mark_rank_array": [0, 0, 0],
    })
    return wire


def _rank_for_stats(chara: dict) -> int:
    score = rating_formula.get_rating(
        [chara.get(k, 0) for k in ("speed", "stamina", "pow", "guts", "wiz")])
    return trained_chara._rank_for_score(score)


def _entry_num(race_instance_id: int) -> int:
    row = master_data.query_one(
        "SELECT r.entry_num AS n FROM race_instance ri JOIN race r ON r.id=ri.race_id "
        "WHERE ri.id=?", (race_instance_id,))
    return (row["n"] if row else 18) or 18


def _record_last_start(drs: dict, family: str, race_id, trained_chara_id) -> None:
    drs.setdefault("last_start", {})[family] = {
        "race_id": int(race_id or 0), "trained_chara_id": int(trained_chara_id or 0)}


def _last_start_info(drs: dict, family: str) -> dict:
    """JP LastStartRaceInfo {race_id, trained_chara_id}: what the last entry
    or skip of this family used (umacap 10-03: {10, 107} right after a race 10
    skip with trained chara 107). Kept across resets, like the real one."""
    return dict((drs.get("last_start") or {}).get(family)
                or {"race_id": 0, "trained_chara_id": 0})


# ---------------------------------------------------------------------------
# field building

def _find_veteran(viewer_id, trained_chara_id):
    roster = trained_chara._get_or_seed_roster(viewer_id)
    return next((c for c in roster if c.get("trained_chara_id") == trained_chara_id), None)


def _field_seed(viewer_id, race_id: int, extra: int = 0) -> int:
    """Deterministic per (viewer, race, served day): race_entry and race_start
    must show the SAME field even across a server restart in between (hash()
    is per-process-salted, so it can't be the seed)."""
    return zlib.crc32(f"{viewer_id}:{race_id}:{_served_day()}:{extra}".encode())


def _roll_daily_conditions(viewer_id, race_id: int) -> tuple:
    """(season, weather, ground_condition) for a daily race. BUG FIXED
    2026-08-19 (live-reported: entering a daily race hung the client forever
    on the paddock's background load): this used to hardcode 1/1/1 ('daily
    rows carry no conditions' -- true of the MASTER row, master.mdb's daily_
    race table really has no season/weather/ground columns, unlike daily_
    legend_race) and, worse, never sent season/weather/ground_condition (or
    race_instance_id/random_seed/state/trained_chara_id) back in race_entry's
    response AT ALL. The real capture (captures/20260819_173442, 3 full
    daily races) showed race_entry DOES carry all of those, with season/
    weather/ground genuinely varying per attempt (observed (3,3,4), (4,2,2),
    (2,1,1) across the 3 races) -- not the constant this assumed. No master
    column backs them (this project's usual 'confirm before wiring' standard
    can't be met here), so they're server-rolled -- extra=100+ keeps this
    stream distinct from the field-selection (extra=0) and skip (extra=i+1)
    seeds sharing the same (viewer, race, day) base."""
    seed = _field_seed(viewer_id, race_id, extra=100)
    rng = random.Random(seed)
    # The season stays a server roll (3 real samples can't fix its odds), but
    # weather and ground are master race_condition's weighted draw for that
    # season and track (race_conditions.roll) -- no longer three independent
    # 1-4 rolls that served snow in summer and rain on firm ground.
    # Seasons 1-5, not 1-4: 5 is master season_data's cherry-blossom spring
    # (03-20..04-20), and the real JP server served it on 3 of 7 alt daily
    # races in one sitting (sweep 2026-10-11; Global's 3 real samples: 3,4,2).
    # NOT EXACT: the odds are unknown -- uniform is a placeholder.
    season = rng.randint(1, 5)
    row = _daily_race_row(race_id)
    cond = race_conditions.roll(row["race_instance_id"] if row else 0, rng, season=season)
    return season, cond["weather"], cond["ground_condition"]


def _daily_opponents(race_row, viewer_id) -> list[dict]:
    """The daily race's NPC field: `unique_chara_npc_max` named umas + mobs to
    fill the gate, drawn deterministically per (viewer, race, served day) so
    race_entry and race_start see the same field."""
    group = _daily_npc_group(race_row["race_instance_id"])
    pool = _npc_rows("daily_race_npc", group)
    if not pool:
        return []
    rng = random.Random(_field_seed(viewer_id, race_row["id"]))
    real = [r for r in pool if (r["chara_id"] or 0) > 1]
    mobs = [r for r in pool if (r["chara_id"] or 0) <= 1]
    want = _entry_num(race_row["race_instance_id"]) - 1
    n_real = min(len(real), race_row["unique_chara_npc_max"] or 0, want)
    picked = rng.sample(real, n_real) + rng.sample(mobs, min(len(mobs), want - n_real))
    rng.shuffle(picked)
    return [_npc_chara(r) for r in picked]


def _legend_opponents(legend_row, viewer_id) -> list[dict]:
    """Boss first, then the group's NPCs to fill the gate."""
    boss = _boss_row(legend_row["legend_race_boss_npc_id"])
    if boss is None:
        return []
    group = _legend_npc_group(boss["id"])
    pool = _npc_rows("legend_race_npc", group)
    if not pool:  # mapping miss -- nearest existing group keeps the race runnable
        near = master_data.query_one(
            "SELECT npc_group_id AS g FROM legend_race_npc "
            "ORDER BY ABS(npc_group_id - ?) LIMIT 1", (group,))
        pool = _npc_rows("legend_race_npc", near["g"]) if near else []
    rng = random.Random(_field_seed(viewer_id, legend_row["id"]))
    want = _entry_num(legend_row["race_instance_id"]) - 2  # player + boss
    picked = rng.sample(pool, min(len(pool), max(0, want)))
    return [_boss_chara(boss)] + [_npc_chara(r) for r in picked]


def _race_horse_array(horses: list[dict], gate_assignment: list[int] | None = None) -> list[dict]:
    """Wire race_horse_data_array for a field, with the same 3-category
    popularity ranks practice_race serves (the client indexes
    popularity_mark_rank_array unconditionally at [0]/[1]/[2]).

    gate_assignment: the SAME randomized gate permutation the eventual race
    simulation will use (see _do_race_entry, which rolls and persists it, and
    race_simulator.run_simulation's own docstring) -- frame_order drives the
    PRE-race gate lineup shown here at the paddock screen, and it must match
    the animation or the player sees herself standing in gate 1 here and then
    "teleport" once the race actually starts (live-reported 2026-08-24).
    Falls back to plain array order if not given (e.g. a caller with no
    paddock/entry step of its own)."""
    gates = list(gate_assignment) if gate_assignment else list(range(len(horses)))

    def _rank_by(key):
        order = sorted(range(len(horses)), key=key)
        return {idx: rank + 1 for rank, idx in enumerate(order)}

    pop = _rank_by(lambda i: -(horses[i].get("speed") or 0))
    sta = _rank_by(lambda i: -(horses[i].get("stamina") or 0))
    pw = _rank_by(lambda i: -(horses[i].get("pow", horses[i].get("power", 0)) or 0))
    return [
        practice_race._build_race_horse_entry(
            chara,
            frame_order=gates[i] + 1,
            final_grade=chara.get("rank", 1),
            popularity=pop[i],
            popularity_mark_rank_array=[pop[i], sta[i], pw[i]],
        )
        for i, chara in enumerate(horses)
    ]


# ---------------------------------------------------------------------------
# race outcome (real sim, deterministic fallback)

def _fallback_rank(player: dict, opponents: list[dict], seed: int) -> int:
    """Deterministic no-Node outcome: a stat-weighted score with a small
    seeded jitter. Only used when the real simulator can't run."""
    rng = random.Random(seed)

    def score(c):
        base = ((c.get("speed") or 0) + 0.8 * (c.get("pow", c.get("power", 0)) or 0)
                + 0.6 * (c.get("stamina") or 0) + 0.4 * (c.get("guts") or 0)
                + 0.4 * (c.get("wiz", c.get("wisdom", 0)) or 0))
        return base * rng.uniform(0.95, 1.05)

    scores = [score(player)] + [score(o) for o in opponents]
    return 1 + sum(1 for s in scores[1:] if s > scores[0])


def _run_race(player: dict, opponents: list[dict], race_instance_id: int,
              season: int, weather: int, ground: int,
              gate_assignment: list[int] | None = None, race_type: int = 10) -> dict:
    """Returns {rank, race_scenario, seed, horses, sim_results|None}. Never
    raises: any sim failure degrades to the deterministic outcome roll (an
    uncaught exception here would 500 and the client shows nothing at all).

    gate_assignment: the SAME gate permutation race_entry already showed at
    the paddock screen (see _do_race_entry) -- keeps the animation's starting
    positions consistent with what the player was already told."""
    try:
        result = race_simulator.simulate_race(
            player, opponents, race_instance_id,
            ground_condition=ground, weather=weather, season=season,
            gate_assignment=gate_assignment, race_context={"race_type": race_type})
    except Exception:
        log.exception("daily race simulation failed, using fallback outcome")
        result = None
    if result is not None:
        # sim_results is horse-index ordered (practice_race zips it against
        # horses the same way); index 0 is the player. finishOrder is 0-BASED
        # (raceRunner.ts: `finishOrder.indexOf(i)`), the wire rank is 1-based.
        rank = result["sim_results"][0]["finishOrder"] + 1
        return {"rank": rank, "race_scenario": result["race_scenario"],
                "seed": result["seed"], "horses": result["horses"],
                "sim_results": result["sim_results"]}
    seed = random.randint(0, 2**31 - 1)
    return {"rank": _fallback_rank(player, opponents, seed),
            "race_scenario": "", "seed": seed,
            "horses": [player] + opponents, "sim_results": None}


# ---------------------------------------------------------------------------
# reward application

def _normal_reward_amount(cat: int, difficulty: int) -> int:
    """The per-run 'normal' reward for this currency/difficulty -- the real
    confirmed value where a capture has one (support-pt difficulty 2-4), the
    old flat-rate guess otherwise (money is entirely confirmed; support-pt
    difficulty 1 still isn't -- see _SUPPORT_PT_NORMAL_BY_DIFFICULTY)."""
    base = _DROP_NORMAL_BY_DIFFICULTY.get(difficulty or 1, 1000)
    if cat != 30:
        return base
    confirmed = _SUPPORT_PT_NORMAL_BY_DIFFICULTY.get(difficulty)
    return confirmed if confirmed is not None else max(1, int(base * _SUPPORT_PT_RATE))


def _rare_reward_pool(cat: int, difficulty: int) -> tuple:
    """The per-roll rare-value pool for this currency/difficulty -- same
    confirmed-else-guess split as _normal_reward_amount."""
    if cat != 30:
        return _DROP_RARE_VALUES_BY_DIFFICULTY.get(difficulty, _DROP_RARE_VALUES)
    confirmed = _SUPPORT_PT_RARE_VALUES_BY_DIFFICULTY.get(difficulty)
    if confirmed is not None:
        return confirmed
    return tuple(max(1, int(v * _SUPPORT_PT_RATE)) for v in _DROP_RARE_VALUES)


def _medal_enabled() -> bool:
    return master_data.has_table("training_report_pass")


def _run_rewards(race_row, rank: int) -> tuple[list, list]:
    """(normal_reward_array, rare_reward_array) for one daily race run, shaped
    like every real replay_check / race_skip entry.

    BUG FIXED 2026-10-03: JP's item races (pick_up category 11) used to be
    paid with the Monies table, i.e. 1,000-5,000 hint books per run. See
    _ITEM_RACE_NORMAL for what they really pay."""
    cat = race_row["pick_up_item_category_1"] or _ITEM_TYPE_MONEY
    iid = race_row["pick_up_item_id_1"] or 59
    difficulty = race_row["difficulty"] or 1
    rolls = _DROP_RARE_ROLLS_BY_RANK.get(rank, 1)
    rng = random.Random()
    if cat == _ITEM_RACE_CATEGORY:
        normal = [dict(zip(("item_type", "item_id", "item_num"), _ITEM_RACE_NORMAL))]
        picks = [(race_row[f"pick_up_item_category_{i}"], race_row[f"pick_up_item_id_{i}"])
                 for i in (1, 2, 3) if race_row[f"pick_up_item_id_{i}"]]
        rare = [{"item_type": c, "item_id": i, "item_num": 1}
                for c, i in (rng.choice(picks) for _ in range(rolls))]
    else:
        normal = [{"item_type": cat, "item_id": iid,
                   "item_num": _normal_reward_amount(cat, difficulty)}]
        pool = _rare_reward_pool(cat, difficulty)
        rare = [{"item_type": cat, "item_id": iid, "item_num": rng.choice(pool)}
                for _ in range(rolls)]
    if _medal_enabled():
        normal.append({"item_type": _MEDAL_ITEM[0], "item_id": _MEDAL_ITEM[1],
                       "item_num": _MEDAL_DAILY})
    return normal, rare


def _award_daily(full_state: dict, drs: dict, race_row, rank: int) -> dict:
    """Full daily_race/replay_check reward shape (confirmed 3x real, incl. a
    loss): first-clear items (master row, once ever) on a win, plus the
    per-run normal/rare drop (_run_rewards)."""
    summary = _empty_summary()
    rid = race_row["id"]
    first_clear = []
    if rank == 1 and rid not in drs["daily_cleared_ever"]:
        first_clear = _grant_row_items(full_state, race_row, "first_clear", summary)
        drs["daily_cleared_ever"].append(rid)

    normal, rare = _run_rewards(race_row, rank)
    for r in normal + rare:
        _grant(full_state, r["item_type"], r["item_id"], r["item_num"], summary)

    rec = drs["daily"].setdefault(str(rid), {"is_played": 0, "is_cleared": 0})
    rec["is_played"] = 1
    drs["entries_total"] += 1
    if rank == 1:
        rec["is_cleared"] = 1
    return {"first_clear_reward_array": first_clear, "normal_reward_array": normal,
            "rare_reward_array": rare, "bonus_reward_array": [],
            "reward_summary_info": summary}


def _skip_reward_entry(full_state: dict, drs: dict, race_row, rank: int) -> dict:
    """One race_reward_array entry, shaped exactly like the race_skip capture:
    {rank, normal_reward_array, rare_reward_array, bonus_reward_array,
    reward_summary_info}. Also applies the rewards to the containers."""
    summary = _empty_summary()
    rid = race_row["id"]
    normal, rare = _run_rewards(race_row, rank)
    if rank == 1 and rid not in drs["daily_cleared_ever"]:
        _grant_row_items(full_state, race_row, "first_clear", summary)
        drs["daily_cleared_ever"].append(rid)
    for r in normal + rare:
        _grant(full_state, r["item_type"], r["item_id"], r["item_num"], summary)

    rec = drs["daily"].setdefault(str(rid), {"is_played": 0, "is_cleared": 0})
    rec["is_played"] = 1
    if rank == 1:
        rec["is_cleared"] = 1
    return {"rank": rank, "normal_reward_array": normal, "rare_reward_array": rare,
            "bonus_reward_array": [], "reward_summary_info": summary}


def _legend_trophy(full_state: dict, viewer_id, legend_row, player: dict | None):
    """(add_trophy_info, trophy_reward_info) for a first legend win: the
    course's race_trophy row (JP: trophy 1203501 for race_instance 1203501),
    credited to the trophy room with the winning uma's chara, plus its 100
    carats. (None, None) when the course has no trophy or it is already held."""
    from . import user_profile
    row = master_data.query_one(
        "SELECT trophy_id FROM race_trophy WHERE race_instance_id=? ORDER BY id LIMIT 1",
        (legend_row["race_instance_id"],))
    if row is None:
        return None, None
    st = user_profile._trophy_state(full_state, viewer_id)
    if str(row["trophy_id"]) in st["trophies"]:
        return None, None
    chara_id = (player or {}).get("chara_id") or ((player or {}).get("card_id") or 0) // 100
    st["trophies"][str(row["trophy_id"])] = {
        "create_time": user_profile._now(),
        "charas": {str(chara_id): 1} if chara_id else {}}
    cat, iid, num = _TROPHY_REWARD
    wallet = full_state.setdefault("coin_info_state", {"fcoin": 0, "coin": 0})
    wallet["fcoin"] = (wallet.get("fcoin") or 0) + num
    return ({"trophy_id": row["trophy_id"], "chara_id_array": [chara_id] if chara_id else []},
            {"item_type": cat, "item_id": iid, "item_num": num})


def _award_legend(full_state: dict, drs: dict, legend_row, rank: int,
                  viewer_id=None, player: dict | None = None) -> dict:
    """DailyLegendRaceReplayCheckResponse's own split (dump.cs, both regions;
    real Global 20260825_094909 0045 and JP umacap 10-02/10-03):

      first_clear -> first_clear_item_*, once ever, on a win. Master.
      victory     -> pick_up_item_* (the boss's piece x1), every win. Master;
                     both JP wins show exactly that.
      drop        -> every run: JP's medals plus a fitted amount (see
                     _LEGEND_WIN_DROP -- drop_reward_odds_id has no table).

    BUG FIXED 2026-10-03: this answered with the DAILY family's
    normal/rare/bonus arrays, which this response does not have, so the
    result screen showed nothing, and it never granted the course trophy."""
    summary = _empty_summary()
    rid = legend_row["id"]
    first_clear, victory, drop = [], [], []
    trophy, trophy_reward = None, None
    if rank == 1:
        if rid not in drs["legend_cleared_ever"]:
            first_clear = _grant_row_items(full_state, legend_row, "first_clear", summary)
            drs["legend_cleared_ever"].append(rid)
        victory = _grant_row_items(full_state, legend_row, "pick_up", summary)
        if viewer_id is not None:
            trophy, trophy_reward = _legend_trophy(full_state, viewer_id, legend_row, player)
    if _medal_enabled():
        drop.append({"item_type": _MEDAL_ITEM[0], "item_id": _MEDAL_ITEM[1],
                     "item_num": _MEDAL_LEGEND})
    cat, iid, num = _LEGEND_WIN_DROP if rank == 1 else _LEGEND_LOSS_DROP
    drop.append({"item_type": cat, "item_id": iid, "item_num": num})
    for r in drop:
        _grant(full_state, r["item_type"], r["item_id"], r["item_num"], summary)

    rec = drs["legend"].setdefault(str(rid), {"is_played": 0, "is_cleared": 0})
    rec["is_played"] = 1
    if rank == 1:
        rec["is_cleared"] = 1
    return {"first_clear_reward_array": first_clear, "drop_reward_array": drop,
            "victory_reward_array": victory, "reward_summary_info": summary,
            "add_trophy_info": trophy, "trophy_reward_info": trophy_reward}


# ---------------------------------------------------------------------------
# shared entry/start/replay flow

def _do_race_entry(payload: dict, family: str) -> dict:
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    drs = _daily_state(full_state)

    if family == "daily":
        race_id = payload.get("daily_race_id")
        row = _daily_race_row(race_id)
        if row is not None and _item_count(full_state, _TICKET_ITEM_ID) < (row["cost_num"] or 1):
            return _already_played()
    else:
        race_id = payload.get("daily_legend_race_id")
        row = _legend_race_row(race_id)
        # ONE entry per daily reset, across the WHOLE list (user-reported
        # 2026-09-11: "there's only 1 entry a day"). Gated on the legend
        # ticket, item 168, which _daily_state refills to 1 at each reset and
        # reflect_item_effect spends -- 168 reads 0 after the run in every
        # real reflect_item_effect reply (Global 20260825_094909 0043, JP
        # umacap 10-02/10-03).
        if row is not None and _item_count(full_state, _LEGEND_TICKET_ITEM_ID) < (row["cost_num"] or 1):
            return _already_played()

    player = _find_veteran(viewer_id, payload.get("trained_chara_id"))
    if row is None or player is None:
        return _refuse()

    opponents = (_daily_opponents(row, viewer_id) if family == "daily"
                 else _legend_opponents(row, viewer_id))
    if not opponents:
        return _refuse()

    # npc_type 11 marks the player's own entry (every real race_entry above).
    horses = [dict(copy.deepcopy(player), npc_type=11)] + opponents
    _record_last_start(drs, family, race_id, payload.get("trained_chara_id"))
    if family == "daily":
        season, weather, ground = _roll_daily_conditions(viewer_id, race_id)
    else:
        season = (row["season"] if row else 1) or 1
        weather = (row["weather"] if row else 1) or 1
        ground = (row["ground"] if row else 1) or 1
    seed = random.randint(0, 2**31 - 1)
    # Rolled ONCE here and persisted (same reasoning as season/weather/ground
    # above): race_entry shows the paddock lineup NOW, race_start runs the
    # actual simulated race in a LATER, separate request -- rolling the gate
    # independently in each would show one random gate at the paddock and
    # animate a different one once the race starts (live-reported 2026-08-24:
    # "always in gate 1, then randomly teleports to her actual gate" -- the
    # plain-array-index bug this fixes first, then this persistence on top of
    # it so the fix doesn't just move the mismatch from "always 1" to
    # "randomly disagrees with itself").
    course_info = race_simulator.get_course_for_race_instance(row["race_instance_id"])
    course_entry_num = course_info[2] if course_info else len(horses)
    gate_assignment = random.sample(range(max(course_entry_num, len(horses))), len(horses))
    drs["pending"] = {
        "family": family,
        "race_id": race_id,
        "trained_chara_id": payload.get("trained_chara_id"),
        "item_id_array": [],
        "result_rank": None,
        "season": season,
        "weather": weather,
        "ground": ground,
        "gate_assignment": gate_assignment,
        # Kept so */resume can hand back the SAME paddock this call served
        # rather than rebuilding a different one. The opponent field is rolled
        # here, so a rebuild at resume time would resume the player into a
        # different set of horses than the one they were looking at -- the same
        # reasoning as legend_race's pending block.
        "random_seed": seed,
        "race_instance_id": row["race_instance_id"],
        "race_horse_data_array": copy.deepcopy(
            _race_horse_array(horses, gate_assignment)),
        "race_scenario": None,
    }
    state_store.save_state(viewer_id, full_state)
    # BUG FIXED 2026-08-19: this used to answer JUST race_horse_data_array --
    # the real capture (captures/20260819_173442) shows race_entry also
    # carries season/weather/ground_condition/random_seed/race_instance_id/
    # state/trained_chara_id, and the paddock view's background load
    # (Gallop.PaddockViewControllerBase.ShowBackGround) needs at least
    # race_instance_id to resolve a course -- missing it null-refed client
    # side and hung the loading screen forever (see _roll_daily_conditions'
    # own comment for the season/weather/ground half of this fix).
    return _ok({
        "race_horse_data_array": _race_horse_array(horses, gate_assignment),
        "season": season,
        "weather": weather,
        "ground_condition": ground,
        "random_seed": seed,
        "race_instance_id": row["race_instance_id"],
        "state": 1,
        "trained_chara_id": payload.get("trained_chara_id"),
    })


def _bracket(gate: int, field_size: int) -> int:
    """1-based bracket (waku) of 0-based gate in a field of field_size: eight
    brackets, the outer ones taking the extra runners once the field passes 8."""
    base, extra = divmod(max(field_size, 8), 8)
    single = 8 - extra                     # brackets holding `base` runners
    if gate < single * base:
        return gate // base + 1
    return single + (gate - single * base) // (base + 1) + 1


def apply_race_items(full_state: dict, pending: dict, item_ids) -> list[int]:
    """Spend the paddock race items the player owns and apply them to pending.

    BUG FIXED 2026-10-05 (live-reported: "starting a daily legend race when
    using a item softlocks the game"): reflect_item_effect ignored
    item_id_array and always answered race_horse_data_array null. With no
    item that matches the real capture, but after an item the client reads
    the changed paddock back from that array, so a null left it stuck.

    The player is index 0 of pending's race_horse_data_array (race_entry puts
    them first in both families). Returns the item ids actually used."""
    used = []
    horses = pending.get("race_horse_data_array") or []
    gates = pending.get("gate_assignment") or []
    for item_id in dict.fromkeys(item_ids or []):
        if type(item_id) is not int or _item_count(full_state, item_id) < 1:
            continue
        row = master_data.query_one("SELECT * FROM item_data WHERE id=?", (item_id,))
        if not row or row["item_category"] != _RACE_ITEM_CATEGORY:
            continue
        for n in (1, 2):
            effect, target, value = (row[f"effect_type_{n}"], row[f"effect_target_{n}"],
                                     row[f"effect_value_{n}"])
            if effect == _EFFECT_MOOD:
                pending["motivation"] = _MOOD_GREAT
                if horses:
                    horses[0].update(motivation=_MOOD_GREAT, motivation_change_flag=1)
            elif effect == _EFFECT_WEATHER:
                pending["weather"] = value
            elif effect == _EFFECT_GROUND:
                pending["ground"] = value
            elif effect == _EFFECT_BRACKET and target in _BRACKETS and gates and horses:
                _move_to_bracket(horses, gates, _BRACKETS[target])
        _add_item(full_state, item_id, -1)
        used.append(item_id)
    if used and horses:
        horses[0]["item_id_array"] = list(used)
    pending["item_id_array"] = list(used)
    return used


def _move_to_bracket(horses: list[dict], gates: list[int], brackets: range) -> None:
    """Swap the player's gate (index 0) into one of `brackets`, trading places
    with whoever stands there; the stored lineup's frame_order follows."""
    field = max(max(gates) + 1, len(gates))
    if _bracket(gates[0], field) in brackets:
        return
    choices = [g for g in range(field) if _bracket(g, field) in brackets]
    if not choices:
        return
    target = random.choice(choices)
    if target in gates:
        other = gates.index(target)
        gates[other] = gates[0]
        if other < len(horses):
            horses[other]["frame_order"] = gates[0] + 1
    gates[0] = target
    horses[0].update(frame_order=target + 1, frame_order_change_flag=1)


def reflect_reply(full_state: dict, pending: dict, ticket: int, used: list[int]) -> dict:
    """reflect_item_effect's body. Without items: nulls, as captured. With
    items: the paddock after them, plus each spent item's new balance."""
    info = [{"item_id": i, "number": _item_count(full_state, i)} for i in [ticket] + used]
    if not used:
        return {"weather": None, "ground_condition": None, "race_horse_data_array": None,
                "item_info_array": info, "state": 2}
    return {"weather": pending.get("weather"), "ground_condition": pending.get("ground"),
            "race_horse_data_array": copy.deepcopy(pending.get("race_horse_data_array") or []),
            "item_info_array": info, "state": 2}


def _do_reflect_item_effect(payload: dict) -> dict:
    """dump.cs (DailyRaceReflectItemEffectResponse.CommonResponse):
    {weather, ground_condition, race_horse_data_array, item_info_array,
    state} -- NOT the empty {} this used to return, which is almost
    certainly why "using an item" looked like it did nothing client-side.

    Real captures (0019/0024/0029 in captures/20260819_173442, all with an
    EMPTY item_id_array) show item_info_array reporting the daily race
    ticket (item 96) balance DECREMENTING one call to the next: 5 -> 4 -> 3.
    That is: this endpoint is where a single (non-skip) race actually
    spends its ticket -- dump.cs's paddock method name
    StartItemSelectAndUseTicket() names the same pairing. weather/
    ground_condition/race_horse_data_array stayed null in every real
    capture (item_id_array was always empty in all three). A non-empty
    item_id_array is applied by apply_race_items, and the reply then carries
    the changed paddock (see reflect_reply).
    Matches this file's existing "never hard-refuse a normal daily run"
    policy (see module docstring) -- ticket count is tracked for display
    accuracy, never gates play, since daily_race/index tops it back up to
    cap on every call anyway."""
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    drs = _daily_state(full_state)
    pending = drs.get("pending")
    # BUG FIXED 2026-09-11: this spent item 96 (the DAILY RACE ticket) and
    # reported its balance no matter which family was racing, so a daily
    # LEGEND race burned the wrong ticket and the paddock's counter ticked
    # down on an item that run never used. The two families have their own
    # tickets -- master.mdb text_data category 23 names 96 "Daily Race
    # Ticket" and 168 "Daily Legend Race Ticket" -- and pending already
    # carries which family this run is.
    ticket = (_LEGEND_TICKET_ITEM_ID
              if (pending or {}).get("family") == "legend" else _TICKET_ITEM_ID)
    used = []
    if pending is not None:
        used = apply_race_items(full_state, pending, payload.get("item_id_array"))
        _add_item(full_state, ticket, -1)
        state_store.save_state(viewer_id, full_state)
    return _ok(reflect_reply(full_state, pending or {}, ticket, used))


def _do_race_start(payload: dict, family: str) -> dict:
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    drs = _daily_state(full_state)
    pending = drs.get("pending")
    if not pending or pending.get("family") != family:
        return _refuse()

    if family == "daily":
        row = _daily_race_row(pending["race_id"])
        # Same conditions race_entry already rolled and stashed -- keeps the
        # paddock (shown at entry) and the actual simulated race agreeing,
        # and matches the real capture's own entry-carries-the-conditions
        # shape (see _roll_daily_conditions' comment).
        season = pending.get("season", 1)
        weather = pending.get("weather", 1)
        ground = pending.get("ground", 1)
    else:
        row = _legend_race_row(pending["race_id"])
        # pending, not the row: a weather doll at the paddock overrides it.
        season = pending.get("season") or (row["season"] if row else 1) or 1
        weather = pending.get("weather") or (row["weather"] if row else 1) or 1
        ground = pending.get("ground") or (row["ground"] if row else 1) or 1
    player = _find_veteran(viewer_id, pending["trained_chara_id"])
    if row is None or player is None:
        return _refuse()

    player = dict(player, npc_type=11)
    if pending.get("motivation"):
        player["motivation"] = pending["motivation"]
    if payload.get("running_style"):
        player["running_style"] = payload["running_style"]
    opponents = (_daily_opponents(row, viewer_id) if family == "daily"
                 else _legend_opponents(row, viewer_id))

    outcome = _run_race(player, opponents, row["race_instance_id"], season, weather, ground,
                        gate_assignment=pending.get("gate_assignment"))
    pending["result_rank"] = outcome["rank"]
    pending["running_style"] = payload.get("running_style")
    pending["race_scenario"] = outcome["race_scenario"]   # replayed by resume
    state_store.save_state(viewer_id, full_state)

    log.info("%s_race/race_start: race=%s player=%s rank=%d simulated=%s",
             family if family == "daily" else "daily_legend",
             pending["race_id"], pending["trained_chara_id"], outcome["rank"],
             outcome["sim_results"] is not None)
    # BUG FIXED 2026-08-19: this used to wrap the reply in a fabricated
    # trained_chara_array + race_result_info -- the real capture shows
    # race_start answers with EXACTLY {race_scenario, state, running_style}
    # at the top level, nothing nested and nothing else. The extra/wrong
    # fields are exactly the kind of shape mismatch that can null-ref a
    # client-side deserializer expecting the real shape.
    return _ok({
        "race_scenario": outcome["race_scenario"],
        "state": 4,
        "running_style": payload.get("running_style") or player.get("running_style") or 1,
    })


def _do_replay_check(payload: dict, family: str) -> dict:
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    drs = _daily_state(full_state)
    pending = drs.get("pending")
    if not pending or pending.get("family") != family or pending.get("result_rank") is None:
        return _refuse()

    rank = pending["result_rank"]
    if family == "daily":
        row = _daily_race_row(pending["race_id"])
        if row is None:
            return _refuse()
        reward = _award_daily(full_state, drs, row, rank)
        body = {
            "rank": rank,
            "first_clear_reward_array": reward["first_clear_reward_array"],
            "normal_reward_array": reward["normal_reward_array"],
            "rare_reward_array": reward["rare_reward_array"],
            "bonus_reward_array": reward["bonus_reward_array"],
            "reward_summary_info": reward["reward_summary_info"],
            "state": 0,
        }
    else:
        row = _legend_race_row(pending["race_id"])
        if row is None:
            return _refuse()
        reward = _award_legend(full_state, drs, row, rank, viewer_id,
                               _find_veteran(viewer_id, pending.get("trained_chara_id")))
        # No trophy -> null. Global's real reply put [] there (20260825_094909
        # 0045), but the field is a LoginUserTrophyInfo object and JP's wins
        # send it as a map, so nil is the form both clients read safely.
        body = {
            "rank": rank,
            "first_clear_reward_array": reward["first_clear_reward_array"],
            "drop_reward_array": reward["drop_reward_array"],
            "victory_reward_array": reward["victory_reward_array"],
            "reward_summary_info": reward["reward_summary_info"],
            "state": 0,
            "add_trophy_info": reward["add_trophy_info"],
            "trophy_reward_info": reward["trophy_reward_info"],
        }

    drs.pop("pending", None)
    shop_info = limited_shop.roll(full_state, "daily_race" if family == "daily" else "legend_race")
    from . import campaign_walking
    walk_gauge_info = campaign_walking.gauge_info(
        full_state, "dailyrace" if family == "daily" else "dailylegendrace")
    state_store.save_state(viewer_id, full_state)
    body.update({
        "limited_shop_info": shop_info,
        "campaign_walking_gauge_info": walk_gauge_info,
        "factor_research_gauge_info": None,
    })
    return _ok(body)


# ---------------------------------------------------------------------------
# daily_race/*

@registry.endpoint("daily_race/index")
def handle_index(payload: dict) -> dict:
    """Shape matches the real captures: daily_race_record_array over every
    master row + purchase_num (Global); JP adds subscription_is_valid and
    last_start_info {race_id, trained_chara_id} (umacap 10-03), the race and
    uma the last entry or skip used."""
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    drs = _daily_state(full_state)

    records = []
    for row in master_data.query("SELECT id FROM daily_race ORDER BY id"):
        rec = drs["daily"].get(str(row["id"]), {})
        records.append({
            "daily_race_id": row["id"],
            "is_cleared": 1 if (row["id"] in drs["daily_cleared_ever"]
                                or rec.get("is_cleared")) else 0,
            "is_played": rec.get("is_played", 0),
        })
    state_store.save_state(viewer_id, full_state)
    return _ok({"daily_race_record_array": records,
                "purchase_num": drs["purchase_num"],
                "subscription_is_valid": False,
                "last_start_info": _last_start_info(drs, "daily")})


@registry.endpoint("daily_race/race_entry")
def handle_race_entry(payload: dict) -> dict:
    return _do_race_entry(payload, "daily")


@registry.endpoint("daily_race/reflect_item_effect")
def handle_reflect_item_effect(payload: dict) -> dict:
    return _do_reflect_item_effect(payload)


@registry.endpoint("daily_race/race_start")
def handle_race_start(payload: dict) -> dict:
    return _do_race_start(payload, "daily")


@registry.endpoint("daily_race/replay_check")
def handle_replay_check(payload: dict) -> dict:
    return _do_replay_check(payload, "daily")


@registry.endpoint("daily_race/recovery_ticket")
def handle_recovery_ticket(payload: dict) -> dict:
    """Captured (0027 req / 0028 resp): spend carats -> the 3 skip tickets
    (item 96) come back, purchase_num +1. Price and the per-day purchase
    limit come from daily_race_billing (_billing); a buy past the limit is
    refused."""
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    drs = _daily_state(full_state)

    frequency, cost = _billing()
    if (drs.get("purchase_num") or 0) >= frequency:
        return _refuse()
    # shop.spend_carats, not a local reimplementation (free carats first,
    # then paid -- the same shared logic gacha.py/_pay use).
    wallet = shop.spend_carats(full_state, cost)
    if wallet is None:
        return _refuse()

    summary = _empty_summary()
    cap = ticket_cap()
    _add_item(full_state, _TICKET_ITEM_ID, cap)
    summary["add_item_list"].append({"item_id": _TICKET_ITEM_ID, "number": cap})
    drs["purchase_num"] = (drs.get("purchase_num") or 0) + 1
    state_store.save_state(viewer_id, full_state)
    return _ok({"coin_info": copy.deepcopy(wallet),
                "reward_summary_info": summary,
                "purchase_num": drs["purchase_num"]})


@registry.endpoint("daily_race_skip/race_skip")
def handle_race_skip(payload: dict) -> dict:
    """Captured (0028 req / 0029 resp). Consumes race_skip_count tickets
    (validated against OUR count, not client_own_num), rolls each run's
    outcome deterministically (no scenario is served for a skip, so the full
    physics sim would be pure cost), and answers the capture's exact shape:
    race_reward_array per run + item_info_array with the remaining tickets.
    limited_shop_info rolls once per skipped run (limited_shop.roll), same
    as a real replay_check would -- real capture
    captures/20260819_173442/0033_daily_race_skip_race_skip.json shows a
    3-run skip rolling 2 fresh opens in one response, which this loop
    reproduces exactly since it calls roll() once per run too."""
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    drs = _daily_state(full_state)

    row = _daily_race_row(payload.get("daily_race_id"))
    player = _find_veteran(viewer_id, payload.get("trained_chara_id"))
    count = int(payload.get("race_skip_count") or 0)
    if row is None or player is None or count <= 0:
        return _refuse()
    if _item_count(full_state, _TICKET_ITEM_ID) < count:
        return _refuse()
    _add_item(full_state, _TICKET_ITEM_ID, -count)
    _record_last_start(drs, "daily", row["id"], payload.get("trained_chara_id"))
    # `WIRE` each skipped run is an entry: a 6-run skip cleared both 「デイリー
    # レースに出走しよう」 (1) and its 3-run sibling (JP umacap 10-03).
    drs["entries_total"] += count

    player = dict(player)
    if payload.get("running_style"):
        player["running_style"] = payload["running_style"]
    opponents = _daily_opponents(row, viewer_id)

    from . import campaign_walking
    rewards = []
    shop_info = None
    any_appeared = False
    walk_before = walk_after = None
    for i in range(count):
        rank = _fallback_rank(player, opponents, _field_seed(viewer_id, row["id"], extra=i + 1))
        rewards.append(_skip_reward_entry(full_state, drs, row, rank))
        rolled = limited_shop.roll(full_state, "daily_race")
        if rolled is not None:
            any_appeared = any_appeared or bool(rolled["appear_flag"])
            shop_info = rolled
        walked = campaign_walking.add_gauge(full_state, "dailyrace")
        if walked is not None:
            walk_before = walk_before if walk_before is not None else walked[0]
            walk_after = walked[1]
    if shop_info is not None:
        shop_info = dict(shop_info)
        shop_info["appear_flag"] = 1 if any_appeared else 0
    walk_gauge_info = ({"before_gauge": walk_before, "after_gauge": walk_after}
                       if walk_after is not None else None)

    state_store.save_state(viewer_id, full_state)
    return _ok({
        "race_reward_array": rewards,
        "item_info_array": [{"item_id": _TICKET_ITEM_ID,
                             "number": _item_count(full_state, _TICKET_ITEM_ID)}],
        "limited_shop_info": shop_info,
        "campaign_walking_gauge_info": walk_gauge_info,
        "factor_research_gauge_info": None,
    })


# ---------------------------------------------------------------------------
# daily_legend_race/*

@registry.endpoint("daily_legend_race/index")
def handle_legend_index(payload: dict) -> dict:
    """daily_legend_race/index -- the permanent daily legend race list, one
    record per daily_legend_race row (29 of them) with the boss to race.

    dump.cs DailyLegendRaceData is {daily_legend_race_id, is_cleared,
    is_played, boss_data}, where boss_data is a full RaceHorseData -- see
    index_boss_data for the two-field stub this used to serve and the
    live-reported broken UI it caused.
    """
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    drs = _daily_state(full_state)

    records = []
    for row in master_data.query(
            "SELECT id, legend_race_boss_npc_id FROM daily_legend_race ORDER BY id"):
        rec = drs["legend"].get(str(row["id"]), {})
        records.append({
            "daily_legend_race_id": row["id"],
            "boss_data": index_boss_data(row["legend_race_boss_npc_id"]),
            "is_cleared": 1 if (row["id"] in drs["legend_cleared_ever"]
                                or rec.get("is_cleared")) else 0,
            "is_played": rec.get("is_played", 0),
        })
    state_store.save_state(viewer_id, full_state)
    # update_item_array: [] in the real Global reply (20260825_094909 0041);
    # last_start_info is JP's (dump.cs), ignored by Global.
    return _ok({"daily_legend_race_record_array": records,
                "update_item_array": [],
                "last_start_info": _last_start_info(drs, "legend")})


@registry.endpoint("daily_legend_race/race_entry")
def handle_legend_race_entry(payload: dict) -> dict:
    return _do_race_entry(payload, "legend")


@registry.endpoint("daily_legend_race/reflect_item_effect")
def handle_legend_reflect_item_effect(payload: dict) -> dict:
    return _do_reflect_item_effect(payload)


@registry.endpoint("daily_legend_race/race_start")
def handle_legend_race_start(payload: dict) -> dict:
    return _do_race_start(payload, "legend")


@registry.endpoint("daily_legend_race/replay_check")
def handle_legend_replay_check(payload: dict) -> dict:
    # takes NO race_result_array (Icarus: the request body is empty)
    return _do_replay_check(payload, "legend")


# ---------------------------------------------------------------------------
# The reward preview / abandon / resume trio, for both daily families.
#
# These are the twins of legend_race/get_reward_list|reset|resume, which shipped
# 2026-09-11 -- dump.cs declares byte-identical shapes for all three
# (DailyRaceResume and DailyLegendRaceResume differ only in that the daily one
# also reports purchase_num). None of the six has ever been captured; the bodies
# follow the legend_race implementations, which were themselves corrected
# against a live report.


def _preview_rewards(row) -> list:
    """The first_clear + pick_up items a race advertises. Read-only: this is the
    rewards panel opened off the race card, so it must grant nothing.

    The odds-driven extras (normal/bonus/rare/drop/victory reward odds ids) are
    deliberately NOT listed -- their tables are not in Global's master.mdb, so
    naming them would be inventing a preview of rewards we cannot actually roll.
    """
    out = []
    for prefix in ("first_clear", "pick_up"):
        for i in (1, 2, 3):
            cat = row[f"{prefix}_item_category_{i}"] or 0
            iid = row[f"{prefix}_item_id_{i}"] or 0
            num = row[f"{prefix}_item_num_{i}"] or 0
            if not iid or num <= 0:
                continue
            if cat == _ITEM_TYPE_PIECE:
                iid = _piece_id_for_card(iid)
            out.append({"item_type": cat, "item_id": iid, "item_num": num})
    return out


def _do_reset(payload: dict, family: str) -> dict:
    """Abandon an in-flight race -> {state}.

    The ticket is NOT refunded: it was spent at reflect_item_effect, and giving
    it back here would turn "enter, look at the field, back out" into a free
    reroll of the opponents.

    Only clears a pending race belonging to THIS family -- the two daily
    families share one pending slot, so a bare pop would let the legend screen
    cancel a daily race that was mid-flight."""
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    drs = _daily_state(full_state)
    pending = drs.get("pending")
    if isinstance(pending, dict) and pending.get("family") == family:
        drs.pop("pending", None)
        state_store.save_state(viewer_id, full_state)
    return _ok({"state": 0})


def _do_resume(payload: dict, family: str, with_purchase_num: bool) -> dict:
    """The whole in-flight race, replayed from what race_entry served.

    TEN fields for daily, nine for daily legend -- not the bare {state} that
    reset returns. Answering {state} alone leaves race_horse_data_array null on
    the screen that is rebuilding the race, which is what broke the legend race
    UI live ("buttons everywhere, text malformed") before its own resume was
    corrected. An empty array is served when nothing is pending -- never null,
    for the same reason.

    state: 0 nothing pending / 2 entered, not yet run / 4 run, awaiting the
    result screen -- the same ladder legend_race/resume reports."""
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    drs = _daily_state(full_state)
    pending = drs.get("pending") or {}
    if pending.get("family") != family:
        pending = {}
    if not pending:
        state = 0
    elif pending.get("result_rank") is not None:
        state = 4
    else:
        state = 2
    bucket = drs["daily"] if family == "daily" else drs["legend"]
    rec = bucket.get(str(pending.get("race_id"))) or {}
    data = {
        "race_horse_data_array": copy.deepcopy(
            pending.get("race_horse_data_array") or []),
        "season": pending.get("season") or 0,
        "weather": pending.get("weather") or 0,
        "ground_condition": pending.get("ground") or 0,
        "random_seed": pending.get("random_seed") or 0,
        "race_instance_id": pending.get("race_instance_id") or 0,
        "race_scenario": pending.get("race_scenario"),
        "state": state,
        "is_cleared": 1 if rec.get("is_cleared") else 0,
    }
    if with_purchase_num:
        data["purchase_num"] = drs["purchase_num"]
    return _ok(data)


@registry.endpoint("daily_race/get_reward_list")
def handle_get_reward_list(payload: dict) -> dict:
    row = _daily_race_row(payload.get("daily_race_id"))
    if row is None:
        return _refuse()
    return _ok({"reward_array": _preview_rewards(row)})


@registry.endpoint("daily_race/reset")
def handle_reset(payload: dict) -> dict:
    return _do_reset(payload, "daily")


@registry.endpoint("daily_race/resume")
def handle_resume(payload: dict) -> dict:
    return _do_resume(payload, "daily", with_purchase_num=True)


@registry.endpoint("daily_race/pre_replay_check")
def handle_pre_replay_check(payload: dict) -> dict:
    """{} -> {state}. The check the client runs BEFORE offering a replay, as
    opposed to replay_check which runs the replay itself.

    Reports whether there is a finished race to replay at all: 1 when a race has
    been run and is waiting on its result screen, 0 otherwise. Saying 1 with
    nothing pending would send the client into a replay of an empty race."""
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    drs = _daily_state(full_state)
    pending = drs.get("pending") or {}
    ready = (pending.get("family") == "daily"
             and pending.get("result_rank") is not None)
    return _ok({"state": 1 if ready else 0})


@registry.endpoint("daily_legend_race/get_reward_list")
def handle_legend_get_reward_list(payload: dict) -> dict:
    row = _legend_race_row(payload.get("daily_legend_race_id"))
    if row is None:
        return _refuse()
    return _ok({"reward_array": _preview_rewards(row)})


@registry.endpoint("daily_legend_race/reset")
def handle_legend_reset(payload: dict) -> dict:
    return _do_reset(payload, "legend")


@registry.endpoint("daily_legend_race/resume")
def handle_legend_resume(payload: dict) -> dict:
    # DailyLegendRaceResume declares no purchase_num -- the daily one does.
    return _do_resume(payload, "legend", with_purchase_num=False)
