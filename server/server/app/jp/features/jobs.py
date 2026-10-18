"""Jobs (全国興行, "national tour"): send five trainees to a racecourse for ten
hours, then collect money, trainer medals, the job's main rewards, fans and
bond, plus the account-wide side payouts (circle points, Training Report
points, story-event points and roulette coins).

Ground truth: jp_captures/CarrotJuicer (account 953434236, 2026-07-28..09-24:
11 index / 90 start / 86 check_complete) plus umacap api-20261003-222052-340
(1 index / 3 start / 1 check_complete): 87 collects, 253 job results. JP
dump.cs (JobsDefine, Jobs* requests and responses, the Jobs4xxxxx/6xxxxx
strings) and JP master.mdb (jobs_reward, jobs_place, jobs_genre,
jobs_point_limit, jobs_limited_schedule, jobs_reward_sort_disp_order,
training_report_pass, story_event_*).

EXACT (master, dump.cs, or the same value in every capture):
  Timer. `WIRE` end_time = servertime + minutes_to_job_complete (600 for all
    103 rows) in all 270 started jobs, as a "YYYY-MM-DD HH:MM:SS" string.
  Frames. JobsDefine: 3 normal frames (local_push_type_index 0-2) plus the
    limited frame 3, 5 cards per job. The client's own refusals (Jobs408019
    / 408020) give the rules: a card cannot work two jobs at once, the same
    trainee cannot appear twice in one job. AnyGoingJobInfo: one jobs_reward_id
    runs in one frame at a time.
  TP skip. JobsDefine.MINUTES_PER_POINT = 20 (Jobs600002 "1TP で 20 分"):
    `WIRE` every use_tp_value is ceil(minutes left / 20), e.g. 599.4 min -> 30,
    568.4 -> 29, 525.3 -> 27. A reduce entry of 0 leaves that job running (a
    collect sent [(100080, 27), (15, 0), (4, 0), (8, 0)] and only 100080 came
    back). jobs_use_item_info is タフネス30 (item 32, TP +30 from item_data)
    used first: tp_out = tp_in + 30 * use_num - sum(use_tp_value) in all 21
    collects that carried it.
  Fixed rewards. display_reward_list = money (type 91, id 59), trainer medals
    (type 161, id 134, jobs_reward.trainer_medal), then the main reward slots
    whose disp_type is 0 (disp_type 1 slots are the client's random-drop
    placeholders). Bond: love_point (2) to every attendant, overflow banked in
    love_point_pool (bond.add_love_point); love_point_pool_map is
    {chara_id: {viewer_id, chara_id, pool_point}} for an attendant at her bond
    cap, pool_point being the pool BEFORE this grant (1 sample: 709 -> 711).
    add_item_list merges repeats (money 34000 + 2000 -> 36000).
  Fans. reward_fan_num (per attendant) is the rolled total / 5 (3800, 4000,
    4120, 4200 from 19000 / 20000 / 20600 / 21000). Circle points = the sum of
    all collected jobs' fan totals, capped by jobs_circle_point_limit
    3,000,000 per month (`WIRE`, not in master; Jobs600021 names the monthly
    cap). before/after_circle_point are the circle's month total, the same on
    every result of one collect.
  Training Report. training_report_pt (2500) per job up to
    training_report_pass.jobs_training_report_point_limit for the season
    (`WIRE` 60000 in 202607/202608, 300000 from 202609), the same before/after
    on every result of one collect.
  Story event. While story_event_data says an event is running:
    story_event_event_pt (15000) and story_event_roulette_coin (10) per job,
    capped per event by jobs_point_limit (600000 / 400; `WIRE` 585000 -> 600000
    paid only 15000, then 0). The coins are the sheet's roulette coin item
    (94/45), reported as training_reward_list. Crossing story_event_point_reward
    thresholds pays those rows (`WIRE` 291708 -> 336708 paid ids 6186-6189).
  Limited jobs. jobs_limited_schedule: start in [start_date, ending_date],
    collect until end_date (Jobs408062). limited_max_count completions each.
    `WIRE` jobs_limited_info on a limited result is [jobs_reward_id,
    limited_schedule_id]; jobs_limited_info_array lists this schedule's
    {jobs_reward_id, complete_count}.
  Index. `WIRE` jobs_going_info_array is null with nothing running;
    jobs_job_log_array is always 4 rows, row i being the team last started in
    frame i ([0, 0, 0, 0, 0] if none). jobs/start's going array holds only the
    jobs it started; its schedule_book_setting is the jobs card preset with
    the started normal frames written in (frame 3 is never stored).

MEASURED, NOT EXACT (the server-side odds tables are not in master):
  money_reward_item_odds_group_id, fan_num_odds_group_id and the bonus drop
  (random_drop_reward_group_id is 0 on every row, yet every result carries a
  drop). The value SETS below are what the real server paid. The WEIGHTS are
  frequencies counted over the 253 captured results, not the real table. The
  user chose this on 2026-10-03 over leaving collecting unbuilt.
  * Money: 4 values per group; group 1011 showed only its lowest and highest
    value (2 samples), so only those two are drawn.
  * Fans: 4 values per group, group 1000 = 2 x group 1.
  * Bonus drop: always one primary item, plus a second "rare" roll (rare
    hint books, 50 sparkles) that never appeared as the primary, in 7 of 253.
  * Main-reward order inside one disp_order: main_reward_slots_id points at a
    server-side slot table the client does not ship, and the captured order
    matches neither item id nor item_data.sort. The order is pinned for the 6
    multi-item jobs the captures show and falls back to slot order otherwise.

NOT BUILT: factor_research_gauge_info (factor research has no gauge state
here), training_challenge_result and its coins (no Training Challenge in JP),
campaign_id_array (no campaign walking capture), support_point_* (never paid
in any capture).
"""

from __future__ import annotations

import copy
import datetime
import functools
import math
import random

from ... import master_data, patch, social
from ... import state as state_store
from ...handlers import bond, collection, missions, shop, stamina, story_event
from ...handlers.stories import _grant_reward
from ...result_codes import ResultCode, refuse
from . import schedule_book

STATE_KEY = "jp_jobs"

# JobsDefine (dump.cs).
NORMAL_GOING_JOB_MAX = 3
LIMITED_FRAME = 3
CHARA_NUM_LIMIT_TO_1_JOB = 5
MINUTES_PER_POINT = 20

CIRCLE_POINT_LIMIT = 3_000_000          # `WIRE` jobs_circle_point_limit
_MONEY = (91, 59)                       # `WIRE` display type / item id
_MEDAL = (161, 134)
_TIME_FMT = "%Y-%m-%d %H:%M:%S"
# The client reads every server time string as JST (TimeUtil.
# ToLocalDateTimeFromJstString), and JP master's TEXT dates are JST too.
JST = datetime.timezone(datetime.timedelta(hours=9))
_COND_JOBS_COMPLETE = 600042            # "全国興行を N 回完了しよう"

# ---------------------------------------------------------------- measured
# Counts over the 253 captured results (see the module docstring). Tier i of
# every group shares one weight.
_MONEY_VALUES = {
    1000: (10800, 11200, 11500, 12000),
    1001: (11200, 11600, 12000, 12400),
    1010: (21600, 22400, 23000, 24000),
    1011: (31600, None, None, 34000),
}
_MONEY_TIER_WEIGHTS = (42, 63, 104, 42)
_FAN_VALUES = {
    1: (19000, 20000, 20600, 21000),
    1000: (38000, 40000, 41200, 42000),
}
_FAN_TIER_WEIGHTS = (65, 119, 43, 26)
_DROP_PRIMARY = (                       # (item_type, item_id, item_num, count)
    (91, 59, 2000, 64), (11, 161, 1, 37), (11, 160, 1, 37), (150, 116, 1, 28),
    (150, 119, 1, 19), (150, 120, 1, 19), (93, 44, 1, 17), (150, 117, 1, 12),
    (150, 118, 1, 10), (90, 43, 10, 10),
)
_DROP_EXTRA = ((11, 162, 1, 5), (11, 163, 1, 1), (93, 44, 50, 1))
_DROP_EXTRA_RATE = (7, 253)
# `WIRE` main-reward display order per jobs_reward_id (item ids).
_MAIN_ORDER = {
    4: (76, 77, 4), 5: (78, 84, 87, 7), 6: (88, 70, 1), 7: (85, 82, 86, 7),
    8: (83, 74, 10), 14: (179, 102, 103, 13),
}


def _ok(data) -> dict:
    return {"response_code": 1, "data_headers": {"result_code": 1, "notifications": {}},
            "data": data}


def _now() -> int:
    return int(patch._servertime())


def _fmt(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts, JST).strftime(_TIME_FMT)


def _master_time(text) -> int | None:
    """JP master's 'YYYY/M/D H:MM:SS' (JST) -> epoch seconds."""
    try:
        return int(datetime.datetime.strptime(str(text).strip(), "%Y/%m/%d %H:%M:%S")
                   .replace(tzinfo=JST).timestamp())
    except ValueError:
        return None


# ------------------------------------------------------------------ master
@functools.lru_cache(maxsize=None)
def _reward(jobs_reward_id: int) -> dict | None:
    row = master_data.query_one("SELECT * FROM jobs_reward WHERE id=?", (int(jobs_reward_id),))
    return dict(row) if row else None


@functools.lru_cache(maxsize=None)
def _disp_order() -> dict:
    return {(r["item_category"], r["item_id"]): r["disp_order"]
            for r in master_data.query("SELECT * FROM jobs_reward_sort_disp_order")}


@functools.lru_cache(maxsize=None)
def _point_limits() -> dict:
    row = master_data.query_one("SELECT * FROM jobs_point_limit ORDER BY id LIMIT 1")
    return dict(row) if row else {"jobs_story_event_point_limit": 0,
                                  "jobs_story_event_roulette_coin_limit": 0,
                                  "jobs_training_challenge_coin_limit": 0}


def _schedule(schedule_id: int) -> dict | None:
    row = master_data.query_one("SELECT * FROM jobs_limited_schedule WHERE id=?", (int(schedule_id),))
    return dict(row) if row else None


def _current_schedule(now: int) -> dict | None:
    """The limited schedule whose collect window (start..end_date) holds now."""
    row = master_data.query_one(
        "SELECT * FROM jobs_limited_schedule WHERE start_date<=? AND end_date>=? "
        "ORDER BY start_date DESC LIMIT 1", (now, now))
    return dict(row) if row else None


def training_report_season(now: int | None = None) -> dict | None:
    """The training_report_pass row running now (its dates are master TEXT)."""
    now = _now() if now is None else now
    if not master_data.has_table("training_report_pass"):
        return None
    for row in master_data.query("SELECT * FROM training_report_pass ORDER BY id DESC"):
        start = _master_time(row["start_date"])
        end = _master_time(row["end_date"])
        if start is not None and end is not None and start <= now <= end:
            return dict(row)
    return None


def _main_rewards(row: dict) -> list:
    """(category, item_id, num) of the real main-reward slots, in display
    order: jobs_reward_sort_disp_order, then the captured order (or slot
    order) inside one disp_order."""
    mains = [(row[f"main_reward_{k}_item_category"], row[f"main_reward_{k}_item_id"],
              row[f"main_reward_{k}_item_num"])
             for k in range(1, 10)
             if row[f"main_reward_{k}_item_disp_type"] == 0 and row[f"main_reward_{k}_item_category"]]
    pinned = _MAIN_ORDER.get(row["id"])
    if pinned and sorted(pinned) == sorted(m[1] for m in mains):
        mains.sort(key=lambda m: pinned.index(m[1]))
    order = _disp_order()
    return sorted(mains, key=lambda m: order.get((m[0], m[1]), 0))


# --------------------------------------------------------------- the rolls
def _roll_tier(values, weights) -> int | None:
    picks = [(v, w) for v, w in zip(values, weights) if v is not None]
    return random.choices([v for v, _ in picks], [w for _, w in picks])[0]


def _roll_money(row: dict) -> int:
    values = _MONEY_VALUES.get(row["money_reward_item_odds_group_id"])
    return _roll_tier(values, _MONEY_TIER_WEIGHTS) if values else row["money_min"]


def _roll_fans(row: dict) -> int:
    values = _FAN_VALUES.get(row["fan_num_odds_group_id"])
    return _roll_tier(values, _FAN_TIER_WEIGHTS) if values else row["fan_num_min"]


def _roll_drops() -> list:
    def pick(table):
        t = random.choices(table, [e[3] for e in table])[0]
        return (t[0], t[1], t[2])
    drops = [pick(_DROP_PRIMARY)]
    if random.randrange(_DROP_EXTRA_RATE[1]) < _DROP_EXTRA_RATE[0]:
        drops.append(pick(_DROP_EXTRA))
    return drops


# ------------------------------------------------------------------- state
def _state(full_state: dict) -> dict:
    st = full_state.setdefault(STATE_KEY, {})
    st.setdefault("going", [])           # [{jobs_reward_id, frame, cards, end_time}]
    st.setdefault("log", {})             # {str(frame): [card_id x5]}
    st.setdefault("limited", {})         # {str(schedule_id): {str(jobs_reward_id): count}}
    st.setdefault("circle", {})          # {"month": YYYYMM, "point": n}
    st.setdefault("training_report", {})  # {str(season_id): points from jobs}
    st.setdefault("story_event", {})     # {str(event_id): {"point": n, "coin": n}}
    st.setdefault("settings", [])        # jobs card preset, if no schedule book was saved
    st.setdefault("complete_total", 0)
    return st


def _going_wire(job: dict) -> dict:
    return {"jobs_reward_id": job["jobs_reward_id"],
            "attend_card_info_array": copy.deepcopy(job["cards"]),
            "end_time": _fmt(job["end_time"]),
            "local_push_type_index": job["frame"]}


def _limited_info(st: dict, now: int) -> list:
    sched = _current_schedule(now)
    counts = st["limited"].get(str(sched["id"]), {}) if sched else {}
    return [{"jobs_reward_id": int(rid), "complete_count": n}
            for rid, n in sorted(counts.items(), key=lambda kv: int(kv[0]))]


def _card_setting(full_state: dict, st: dict) -> list:
    stored = schedule_book.stored(full_state)
    if stored is not None and isinstance(stored.get("schedule_book_jobs_card_setting"), list):
        return copy.deepcopy(stored["schedule_book_jobs_card_setting"])
    return copy.deepcopy(st["settings"])


def _write_card_setting(full_state: dict, st: dict, started: list) -> list:
    rows = {r["jobs_frame_order"]: r for r in _card_setting(full_state, st)}
    for job in started:
        if job["frame"] >= NORMAL_GOING_JOB_MAX:
            continue
        row = {"jobs_frame_order": job["frame"], "jobs_reward_id": job["jobs_reward_id"]}
        for i, card in enumerate(job["cards"], 1):
            row[f"card_id_{i}"] = card["card_id"]
        # A preset another frame can no longer start is dropped. `WIRE` frame
        # 0 taking job 18 removed frame 2's preset for job 18, which also
        # shared card 104801 -- one sample, so it cannot say which of the
        # two conflicts the server checks; both are dropped here.
        cards = {c["card_id"] for c in job["cards"]}
        for frame, other in list(rows.items()):
            other_cards = {other.get(f"card_id_{i}") for i in range(1, CHARA_NUM_LIMIT_TO_1_JOB + 1)}
            if frame != job["frame"] and (other["jobs_reward_id"] == job["jobs_reward_id"]
                                          or cards & other_cards):
                del rows[frame]
        rows[job["frame"]] = row
    setting = [rows[k] for k in sorted(rows)]
    st["settings"] = copy.deepcopy(setting)
    stored = schedule_book.stored(full_state)
    if stored is not None:
        stored["schedule_book_jobs_card_setting"] = copy.deepcopy(setting)
    return setting


# ---------------------------------------------------------------- endpoints
def handle_index(payload: dict) -> dict:
    full_state = state_store.get_state(payload["viewer_id"]) or {}
    st = _state(full_state)
    now = _now()
    return _ok({
        "jobs_going_info_array": [_going_wire(j) for j in st["going"]] or None,
        "jobs_limited_info_array": _limited_info(st, now),
        "jobs_job_log_array": [{"top_list_index": i,
                                "card_id_array": list(st["log"].get(str(i)) or [0] * CHARA_NUM_LIMIT_TO_1_JOB)}
                               for i in range(NORMAL_GOING_JOB_MAX + 1)],
        "jobs_limited_top_new": 0,
        "schedule_book_setting": _card_setting(full_state, st),
    })


def handle_start(payload: dict) -> dict:
    viewer_id = payload["viewer_id"]
    infos = payload.get("jobs_start_job_info_array")
    if not isinstance(infos, list) or not infos:
        return refuse()
    full_state = state_store.get_state(viewer_id) or {}
    st = _state(full_state)
    now = _now()
    owned = {c.get("card_id") for c in full_state.get(collection.CARD_LIST_KEY) or []
             if isinstance(c, dict)}

    busy_frames = {j["frame"] for j in st["going"]}
    busy_rewards = {j["jobs_reward_id"] for j in st["going"]}
    busy_cards = {c["card_id"] for j in st["going"] for c in j["cards"]}
    started = []
    for info in infos:
        if not isinstance(info, dict):
            return refuse()
        rid = int(info.get("jobs_reward_id") or 0)
        frame = int(info.get("local_push_type_index", -1))
        row = _reward(rid)
        cards = [{"card_id": int(c.get("card_id") or 0), "dress_id": int(c.get("dress_id") or 0)}
                 for c in info.get("attend_card_info_array") or [] if isinstance(c, dict)]
        if row is None or not 0 <= frame <= LIMITED_FRAME or frame in busy_frames:
            return refuse()
        if (frame == LIMITED_FRAME) != bool(row["limited_schedule_id"]) or rid in busy_rewards:
            return refuse()
        card_ids = [c["card_id"] for c in cards]
        charas = {bond.chara_id_for_card(cid) for cid in card_ids}
        if (len(cards) != CHARA_NUM_LIMIT_TO_1_JOB or len(charas) != len(cards)
                or not set(card_ids) <= owned or busy_cards & set(card_ids)):
            return refuse()
        if row["limited_schedule_id"]:
            sched = _schedule(row["limited_schedule_id"])
            done = st["limited"].get(str(row["limited_schedule_id"]), {}).get(str(rid), 0)
            if (sched is None or not sched["start_date"] <= now <= sched["ending_date"]
                    or done >= (row["limited_max_count"] or 0)):
                return refuse()
        busy_frames.add(frame)
        busy_rewards.add(rid)
        busy_cards |= set(card_ids)
        started.append({"jobs_reward_id": rid, "frame": frame, "cards": cards,
                        "end_time": now + int(row["minutes_to_job_complete"]) * 60})

    st["going"] += started
    for job in started:
        st["log"][str(job["frame"])] = [c["card_id"] for c in job["cards"]]
    setting = _write_card_setting(full_state, st, started)
    state_store.save_state(viewer_id, full_state)
    return _ok({"jobs_going_info_array": [_going_wire(j) for j in started],
                "schedule_book_setting": setting})


def handle_abort(payload: dict) -> dict:
    """jobs/abort {jobs_reward_id, card_id}: the job ends with no reward
    (Jobs408035); dump.cs's response carries no fields."""
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    st = _state(full_state)
    rid = int(payload.get("jobs_reward_id") or 0)
    job = next((j for j in st["going"] if j["jobs_reward_id"] == rid), None)
    if job is None:
        return refuse()
    st["going"].remove(job)
    state_store.save_state(viewer_id, full_state)
    return _ok({})


def _merge_items(summary: dict) -> None:
    merged: dict = {}
    for e in summary["add_item_list"]:
        merged[e["item_id"]] = merged.get(e["item_id"], 0) + e["number"]
    summary["add_item_list"] = [{"item_id": k, "number": v} for k, v in merged.items()]


def _summary() -> dict:
    s = shop._empty_summary()
    s["add_support_card_limit_break_array"] = []
    return s


def handle_check_complete(payload: dict) -> dict:
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    st = _state(full_state)
    now = _now()

    # -- validate everything before anything moves
    item = payload.get("jobs_use_item_info")
    item_id = use_num = tp_per_item = 0
    if isinstance(item, dict) and int(item.get("use_num") or 0) > 0:
        item_id, use_num = int(item.get("item_id") or 0), int(item["use_num"])
        found = stamina._recovery_item(item_id)
        if not found or found[0] is not stamina.TP:
            return refuse()
        if shop.item_count(full_state, item_id) < use_num:
            return refuse(ResultCode.NOT_ENOUGH_ERROR)
        tp_per_item = found[1]
    reductions = []
    listed = set()
    for e in payload.get("jobs_reduce_tp_array") or []:
        listed.add(int((e or {}).get("jobs_reward_id") or 0))
        use = int((e or {}).get("use_tp_value") or 0)
        if use <= 0:
            continue
        job = next((j for j in st["going"] if j["jobs_reward_id"] == int(e.get("jobs_reward_id") or 0)), None)
        if job is None:
            return refuse()
        left = max(0, job["end_time"] - now)
        need = math.ceil(left / (MINUTES_PER_POINT * 60))
        if use > need + 1:              # +1: the client counted a second earlier
            return refuse()
        reductions.append((job, use))
    tp_cost = sum(use for _, use in reductions)
    tp_have = int(stamina.TP.read(full_state, now).get("current_tp") or 0) + tp_per_item * use_num
    if tp_have < tp_cost:
        return refuse(ResultCode.NOT_ENOUGH_ERROR)

    # -- TP: タフネス30 first, then the skip
    if use_num:
        shop.add_item(full_state, item_id, -use_num)
        stamina.TP.add(full_state, tp_per_item * use_num, now)
    if tp_cost:
        stamina.TP.spend(full_state, tp_cost, now)
    for job, use in reductions:
        job["end_time"] = max(now, job["end_time"] - use * MINUTES_PER_POINT * 60)

    # `WIRE` a non-empty reduce array names the jobs to collect: with all four
    # jobs finished, [(100075, 0)] collected only 100075 and the next call,
    # with [], collected the other three.
    done = [j for j in st["going"] if j["end_time"] <= now
            and (not listed or j["jobs_reward_id"] in listed)]
    st["going"] = [j for j in st["going"] if j not in done]

    results, fan_total = [], 0
    report_pt = event_pt = event_coin = 0
    for job in done:
        row = _reward(job["jobs_reward_id"])
        if row is None:
            continue
        result, fans = _collect(viewer_id, full_state, st, job, row)
        results.append(result)
        fan_total += fans
        report_pt += row["training_report_pt"]
        event_pt += row["story_event_event_pt"]
        event_coin += row["story_event_roulette_coin"]
        st["complete_total"] += 1

    limits = _point_limits()
    circle = _circle_points(viewer_id, st, fan_total)
    report = _training_report_points(st, report_pt, now)
    event = _story_event(viewer_id, full_state, st, event_pt, event_coin, limits, now)
    for r in results:
        r["before_circle_point"], r["after_circle_point"] = circle["before"], circle["after"]
        r["before_jobs_training_report_point_in_season"] = report["before"]
        r["after_jobs_training_report_point_in_season"] = report["after"]

    state_store.save_state(viewer_id, full_state)
    return _ok({
        "tp_info": stamina.tp_info(full_state),
        "jobs_result_info_array": results,
        "jobs_result_limit_info": {
            "jobs_training_report_point_limit_in_season": report["limit"],
            "jobs_story_event_point_limit": limits["jobs_story_event_point_limit"],
            "before_jobs_story_event_point": event["point_before"],
            "after_jobs_story_event_point": event["point_after"],
            "jobs_story_event_roulette_coin_limit": limits["jobs_story_event_roulette_coin_limit"],
            "before_jobs_story_event_roulette_coin": event["coin_before"],
            "after_jobs_story_event_roulette_coin": event["coin_after"],
            "jobs_training_challenge_coin_limit": limits["jobs_training_challenge_coin_limit"],
            "before_jobs_training_challenge_coin": 0,
            "after_jobs_training_challenge_coin": 0,
            "after_jobs_circle_point": circle["jobs_after"],
            "jobs_circle_point_limit": CIRCLE_POINT_LIMIT,
        },
        "jobs_going_info_array": [_going_wire(j) for j in st["going"]],
        "story_event_info": event["info"],
        "factor_research_gauge_info": None,
        "training_challenge_result": None,
        "jobs_limited_info_array": _limited_info(st, now),
    })


def _collect(viewer_id, full_state: dict, st: dict, job: dict, row: dict) -> tuple:
    """One finished job: pay it and build its JobsResultInfo. Returns
    (result, fan total for circle points)."""
    summary = _summary()
    display = [{"item_type": _MONEY[0], "item_id": _MONEY[1], "item_num": _roll_money(row)},
               {"item_type": _MEDAL[0], "item_id": _MEDAL[1], "item_num": row["trainer_medal"]}]
    display += [{"item_type": c, "item_id": i, "item_num": n} for c, i, n in _main_rewards(row)]
    additional = [{"item_type": c, "item_id": i, "item_num": n} for c, i, n in _roll_drops()]
    for e in display + additional:
        _grant_reward(full_state, e["item_type"], e["item_id"], e["item_num"], summary, viewer_id)
    _merge_items(summary)

    fans = _roll_fans(row)
    per_chara = fans // len(job["cards"])
    charas, profiles, pool_map = [], [], {}
    for card in job["cards"]:
        chara_id = bond.chara_id_for_card(card["card_id"])
        entry = bond.chara_entry(full_state, chara_id)
        fan_before = int(entry.get("fan") or 0)
        entry["fan"] = fan_before + per_chara
        love = bond.add_love_point(full_state, chara_id, row["love_point"])
        if love["love_point_pool_after"] > love["love_point_pool_before"]:
            pool_map[chara_id] = {"viewer_id": int(viewer_id), "chara_id": chara_id,
                                  "pool_point": love["love_point_pool_before"]}
        profiles += bond.new_profile_entries(full_state, chara_id)
        charas.append({"chara_id": chara_id, "dress_id": card["dress_id"],
                       "before_fan_num": fan_before, "after_fan_num": entry["fan"],
                       "love_point_info": love})

    limited = []
    if row["limited_schedule_id"]:
        counts = st["limited"].setdefault(str(row["limited_schedule_id"]), {})
        counts[str(row["id"])] = counts.get(str(row["id"]), 0) + 1
        limited = [row["id"], row["limited_schedule_id"]]

    return {
        "jobs_reward_id": row["id"],
        "card_id": job["cards"][0]["card_id"],
        "local_push_type_index": job["frame"],
        "display_reward_list": display,
        "additional_display_reward_list": additional,
        "love_point_pool_map": pool_map or [],
        "add_love_point": row["love_point"],
        "reward_fan_num": per_chara,
        "campaign_id_array": [],
        "jobs_limited_info": limited,
        "reward_summary_info": summary,
        "jobs_result_character_info_array": charas,
        "new_chara_profile_array": profiles,
    }, per_chara * len(job["cards"])


def _circle_points(viewer_id, st: dict, fans: int) -> dict:
    """Credit the collected fans to the player's circle, within the monthly
    jobs cap. Not in a circle: nothing to credit, both totals 0."""
    month = int(datetime.datetime.fromtimestamp(_now(), JST).strftime("%Y%m"))
    record = st["circle"]
    if record.get("month") != month:
        record.update(month=month, point=0)
    member = social.member_row(viewer_id)
    if member is None:
        return {"before": 0, "after": 0, "jobs_after": record["point"]}
    circle_id = member["circle_id"]
    before = social.circle_rank(circle_id)[1] or 0
    add = max(0, min(fans, CIRCLE_POINT_LIMIT - record["point"]))
    record["point"] += add
    after = social.add_circle_point(circle_id, add) if add else before
    return {"before": before, "after": after, "jobs_after": record["point"]}


def _training_report_points(st: dict, points: int, now: int) -> dict:
    season = training_report_season(now)
    if season is None:
        return {"before": 0, "after": 0, "limit": 0}
    key = str(season["season_id"])
    limit = int(season["jobs_training_report_point_limit"] or 0)
    before = st["training_report"].get(key, 0)
    after = min(limit, before + points)
    st["training_report"][key] = after
    return {"before": before, "after": after, "limit": limit}


def season_points(full_state: dict, season_id: int) -> int:
    """Training Report points this account earned in a season (jobs are the
    only source this server credits)."""
    return int(((full_state.get(STATE_KEY) or {}).get("training_report") or {}).get(str(season_id), 0))


def _earning_event(now: int) -> int | None:
    """The story event whose points can still be earned: start_date to
    ending_date. `WIRE` after event 1055's ending_date (and before its
    end_date) the real collect carried story_event_info null and 0/0 counters."""
    row = master_data.query_one(
        "SELECT story_event_id FROM story_event_data WHERE start_date<=? AND ending_date>=? "
        "ORDER BY start_date DESC LIMIT 1", (now, now))
    return int(row["story_event_id"]) if row else None


def _story_event(viewer_id, full_state: dict, st: dict, points: int, coins: int,
                 limits: dict, now: int) -> dict:
    event_id = _earning_event(now)
    if event_id is None:
        return {"info": None, "point_before": 0, "point_after": 0, "coin_before": 0, "coin_after": 0}
    record = st["story_event"].setdefault(str(event_id), {"point": 0, "coin": 0})
    point_before, coin_before = record["point"], record["coin"]
    record["point"] = min(limits["jobs_story_event_point_limit"], point_before + points)
    record["coin"] = min(limits["jobs_story_event_roulette_coin_limit"], coin_before + coins)
    add_point = record["point"] - point_before
    add_coin = record["coin"] - coin_before

    totals = full_state.setdefault("story_event_point", {})
    total_before = int(totals.get(str(event_id), 0))
    total_after = total_before + add_point
    totals[str(event_id)] = total_after

    ev_state, _ = story_event._event_state(full_state, event_id)
    sheet = story_event._sheet_row(event_id, ev_state["current_sheet"])
    coin_type, coin_item = ((sheet["use_item_category"], sheet["use_item_id"]) if sheet else (94, 45))
    if add_coin:
        shop.add_item(full_state, coin_item, add_coin)

    summary = _summary()
    reward_ids, reward_list = [], []
    for r in master_data.query(
            "SELECT * FROM story_event_point_reward WHERE story_event_id=? AND point>? AND point<=? "
            "ORDER BY point, id", (event_id, total_before, total_after)):
        reward_ids.append(r["id"])
        reward_list += _grant_reward(full_state, r["item_category"], r["item_id"], r["item_num"],
                                     summary, viewer_id)
    _merge_items(summary)

    return {
        "point_before": point_before, "point_after": record["point"],
        "coin_before": coin_before, "coin_after": record["coin"],
        "info": {
            "add_point_info": {"total": add_point, "rank_score": 0, "nickname_bonus": 0,
                               "card_bonus": 0, "support_card_bonus": 0, "win_num_bonus": 0},
            "event_id": event_id,
            "event_user_info": story_event._event_user_info(full_state, event_id,
                                                            ev_state["current_sheet"]),
            "point_reward_id_list": reward_ids,
            "reward_list": reward_list,
            "reward_summary_info": summary,
            "training_reward_list": [{"item_type": coin_type, "item_id": coin_item,
                                      "item_num": add_coin}],
            "additional_training_reward_list": [],
            "is_boost": 0,
            "new_story_id_list": [],
            "story_data_list": [],
            # `WIRE` true only on the collect that reaches the ladder's top
            # (event 1056: 1469293 -> 1514293 paid the last row, id 6119);
            # every later collect is false again.
            "get_all_point_reward": total_before < story_event._max_point_threshold(event_id) <= total_after,
        },
    }


def _complete_total(viewer_id, full_state: dict, row) -> int:
    return int((full_state.get(STATE_KEY) or {}).get("complete_total") or 0)


missions.CONDITION_HOOKS[_COND_JOBS_COMPLETE] = _complete_total


HANDLERS = {
    "jobs/index": handle_index,
    "jobs/start": handle_start,
    "jobs/check_complete": handle_check_complete,
    "jobs/abort": handle_abort,
}
