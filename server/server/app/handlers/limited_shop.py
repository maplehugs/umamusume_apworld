"""Daily/Legend-race "limited shop": running a race has a chance to unlock
a limited-time shop stocked with randomly-rolled purchasable items.

Ground truth (verified live against master.mdb and dump.cs, plus two real
captures -- NOT guessed):

  limited_exchange: exactly one row is ever "active" (start_date <=
    servertime <= end_date, both raw unix epoch ints -- same idea as
    story_event.py's _active_event_id, NOT missions.py's string-date
    _parse_mdb_datetime). The live row (id=5, odds_id=1004,
    item_lineup_value=7) carries PER-CONTEXT odds/ceiling as parts-per-
    million: daily_race_odds=350000/ceiling=3, legend_race_odds=400000/
    ceiling=2, team_stadium_odds=300000/ceiling=4, single_mode_odds=0
    (disabled). "35% per daily race run, capped at 3 opens" is the real
    behavior behind the user's "50%-ish, can trigger more than once".

  limited_exchange_reward: the random item pool, split into
    item_lineup_value slots. VERIFIED formula (checked against all 5
    historical limited_exchange rows, zero exceptions):
        group_id = (10 + (odds_id - 1000)) * 10 + slot   for slot in 1..item_lineup_value
    e.g. odds_id=1004 (7 slots) -> groups 141-147; odds_id=1000 (6 slots)
    -> groups 101-106. Each slot's rows are weighted by `odds` (parts-per-
    million WITHIN that slot; verified summing to ~1,000,000 per slot).
    `item_exchange_id` on each reward row is an ordinary item_exchange row
    (top_id 9000), bought per open through buy() below.

  Real capture captures/20260819_173442/0033_daily_race_skip_race_skip.json:
    a race_skip_count=3 call rolled 2 opens in ONE response
    (limited_shop_info: open_count=2, open_flag=1, appear_flag=1) -- exactly
    "running several at once can trigger it more than once". The following
    0034_item_show_exchange.json shows 14 limited_goods_info_array entries:
    TWO full 7-slot sets, tagged open_count=1 and open_count=2 respectively
    -- each trigger rolls and ACCUMULATES its own fresh offer set, it
    doesn't replace the previous one.

  appear_flag is 1 ONLY in the exact response of the call that produced a
  new open; every other read (a later item/show_exchange, load/index) shows
  0 while open_flag/open_count/last_open_time stay persisted -- a one-shot
  "just now" flag, not shop-open state. snapshot_info() below always
  returns 0; roll() returns 1 only when it just produced a fresh open.

  dump.cs confirms LimitedShopInfo {limited_exchange_id, open_flag,
  appear_flag, close_time, open_count, limited_sale_all_change_flag,
  last_open_time} and LimitedGoodsInfo {disp_order, open_count, reward_id
  (-> limited_exchange_reward.id), exchange_count} exactly (already matched
  by daily_races.py's now-removed hardcoded stub). item/manual_close is a
  real endpoint with an EMPTY request body -- no capture of it exists
  anywhere (checked debug_responses/ and captures/ exhaustively), so its
  effect below is an inference, flagged at the function.

Scope (user-confirmed): wired up for daily races and legend races only
(single-run via replay_check, multi-run via race_skip) -- "running in
races". team_stadium/single_mode share the same master row/odds columns so
roll() is written generically by `context`, but those two call sites are
not wired up this pass.

Per day, not per campaign (fixed 2026-10-03, see _state): open_count and
the goods reset at every daily reset, and opens stop at max_open_count = 3 +
the account's 限定セールオープン上限アップ (item 296, JP).

JP (no limited_exchange / limited_exchange_reward in its master): the pool is
seeds/limited_shop_pool.json, built from real JP captures by
tools/gen_jp_limited_shop.py. Its slots 4-7 reuse Global master's odds for the
identical reward ids; slots 1-3 and the open rates are FITTED (see _campaign).

Known design gap (no real evidence either way): the wire format has ONE
global open_count/ceiling shared across every context, but master data
gives daily/legend/team-stadium their OWN ceiling. No capture exercises two
different contexts against the same campaign to show how that should
interact. Implemented as: roll() only ever compares the shared open_count
against *that call's own* context ceiling -- so once any context's ceiling
is reached, a context with an equal-or-lower ceiling simply never fires
again (the highest-ceiling context in practice becomes the effective cap).
"""

from __future__ import annotations

import functools
import json
import random

from .. import master_data
from .. import patch
from . import registry, shop

STATE_KEY = "limited_shop_state"


@functools.lru_cache(maxsize=1)
def _all_rows() -> tuple:
    if not master_data.has_table("limited_exchange"):
        return ()        # not in this client's master (JP has no limited exchange)
    return tuple(master_data.query("SELECT * FROM limited_exchange"))


def _active_row(now_ts: int):
    for row in _all_rows():
        if row["start_date"] <= now_ts <= row["end_date"]:
            return row
    return None


def _slot_group_id(odds_id: int, slot: int) -> int:
    return (10 + (odds_id - 1000)) * 10 + slot


@functools.lru_cache(maxsize=64)
def _slot_rewards(group_id: int) -> tuple:
    return tuple(master_data.query(
        "SELECT * FROM limited_exchange_reward WHERE group_id=?", (group_id,)))


def _reward_row(reward_id: int):
    return master_data.query_one(
        "SELECT * FROM limited_exchange_reward WHERE id=?", (reward_id,))


# Where each master slot is SHOWN. Every real Global show_exchange (17 goods
# sets across captures/2026081x-0904, all on the 7-slot odds_id 1004 row)
# puts group 145 at disp_order 1, 146 at 2, 141 at 3, 142 at 4, 143 at 5,
# 144 at 6 and 147 at 7 -- the two character-piece slots first. Slot k is
# group (odds base + k), so this is slot -> disp_order. Before 2026-10-03 the
# slot number itself was served as disp_order.
_GLOBAL_DISP_ORDER_7 = {5: 1, 6: 2, 1: 3, 2: 4, 3: 5, 4: 6, 7: 7}

# No per-context ceiling on JP: real JP daily race skips open the sale 5-6
# times a day (CarrotJuicer 07-27..09-25), past Global's daily_race_ceiling of
# 3, and stop exactly at max_open_count.
_NO_CEILING = 1 << 30


@functools.lru_cache(maxsize=1)
def _jp_pool() -> dict | None:
    """JP's pool file (tools/gen_jp_limited_shop.py), or None if absent."""
    from .. import region
    path = region.seeds_dir() / "limited_shop_pool.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _campaign(now_ts: int) -> dict | None:
    """The running limited sale as one shape for both regions:
    {id, end_date, open_value, odds: {context: (ppm, ceiling)},
     slots: [(disp_order, [(reward_id, item_exchange_id, ribbon_value, weight)])]}.

    Global: master.mdb limited_exchange + limited_exchange_reward (exact).
    JP: master has neither table, so the pool comes from real JP captures
    (seeds/limited_shop_pool.json). Its slots 4-7 use Global master's odds for
    the identical reward ids, slots 1-3 use how often each reward was seen,
    and the open rates are Global's -- FITTED, see that tool's docstring."""
    row = _active_row(now_ts)
    if row is not None:
        lineup = row["item_lineup_value"] or 0
        slots = []
        for slot in range(1, lineup + 1):
            rewards = [(r["id"], r["item_exchange_id"], r["ribbon_value"] or 0, r["odds"])
                       for r in _slot_rewards(_slot_group_id(row["odds_id"], slot))]
            disp = _GLOBAL_DISP_ORDER_7.get(slot, slot) if lineup == 7 else slot
            slots.append((disp, rewards))
        return {"id": row["id"], "end_date": row["end_date"],
                "open_value": row["open_value"] or 0,
                "odds": {ctx: (row[o] or 0, row[c] or 0)
                         for ctx, (o, c) in _CONTEXT_ODDS_COLUMN.items()},
                "slots": slots}
    if master_data.has_table("limited_exchange"):
        return None          # Global, between campaigns
    pool = _jp_pool()
    if not pool:
        return None
    return {"id": pool["limited_exchange_id"], "end_date": pool["close_time"],
            "open_value": 0,
            "odds": {ctx: (ppm, _NO_CEILING) for ctx, ppm in pool["open_odds_ppm"].items()},
            "slots": [(s["disp_order"],
                       [(r["reward_id"], r["item_exchange_id"], r["ribbon_value"], r["weight"])
                        for r in s["rewards"]])
                      for s in pool["slots"]]}


def _roll_slot(rewards: list):
    total = sum(w for *_x, w in rewards)
    if total <= 0:
        return None
    threshold = random.randint(1, total)
    acc = 0
    for entry in rewards:
        acc += entry[3]
        if threshold <= acc:
            return entry
    return rewards[-1]


# What last_open_time reads after a reset, before the day's first open. Global
# serves 32400 -- epoch 0 rendered in JST, i.e. an empty DATETIME column
# (captures 20260819_173442 0021/0026/0031 and 20260825_094909 0045, all with
# open_count 0). JP serves 0 (umacap 2026-09-12 fresh account, CarrotJuicer
# 08-14/08-15 resets). JP's master is the one without limited_exchange.
def _reset_open_time() -> int:
    return 32400 if master_data.has_table("limited_exchange") else 0


def _state(full_state: dict, active_id: int) -> dict:
    """The viewer's limited-shop block, reset on a new campaign AND on every
    daily reset.

    BUG FIXED 2026-10-03: opens used to accumulate for the whole campaign, so
    after the first 3 the shop never opened again. The real server counts
    opens PER DAY: Global 08-19 reached open_count 2 and 08-25 was back at 0
    (captures above); JP CarrotJuicer shows open_count/goods/last_open_time
    returning to 0/[]/0 at every reset across 07-27..09-25, and JP item 296's
    own text is 限定セールの1日の最大オープン数 ("max opens PER DAY").
    Buying history (shop.SHOP_LIMIT_KEY) is untouched; item_exchange rows
    track their own limits independently."""
    from .daily_races import _served_day
    st = full_state.setdefault(STATE_KEY, {})
    day = _served_day()
    if st.get("limited_exchange_id") != active_id or st.get("day") != day:
        st.clear()
        st["limited_exchange_id"] = active_id
        st["day"] = day
        st["open_count"] = 0
        st["last_open_time"] = _reset_open_time()
        st["goods"] = []
    return st


# Base daily open cap. Global's limited_exchange.open_value is 3 on every row
# and JP's real max_open_count is 3 on an account with no item 296 (umacap
# 2026-09-12 viewer 149535405, 2026-09-18 viewer 900000000002).
_BASE_MAX_OPEN = 3


def max_open_count(full_state: dict, camp: dict | None = None) -> int:
    """Opens allowed per day: the base plus every 限定セールオープン上限アップ
    (item 296) bought through item/exchangeAddFrame. Real JP: bonus 0 -> 3,
    1 -> 4, 3 -> 6 (load/index user_info.bonus_limited_sale_open_num against
    the same session's limited_shop_info.max_open_count, three accounts)."""
    base = ((camp or {}).get("open_value") or 0) or _BASE_MAX_OPEN
    return base + shop.bonus_limited_sale_open_num(full_state)


# LimitedShopInfo.close_time is a real (signed) C# int32 client-side --
# master.mdb's end_date for the live "never really expires" campaign row is
# 2556143999, which OVERFLOWS int32 (max 2147483647). Sending it verbatim
# broke the client's msgpack deserialization entirely ("could not receive
# parameters from server" right after replay_check -- confirmed the actual
# cause of that report). Clamp to the same safe "far future" sentinel the
# original hardcoded stub used before this feature replaced it.
_MAX_INT32 = 2_000_000_000


def _info(camp: dict, st: dict, appear_flag: int, full_state: dict) -> dict:
    # max_open_count is JP-only on the wire (Global's LimitedShopInfo has no
    # such field); the extra key is ignored by the Global client.
    return {
        "limited_exchange_id": camp["id"],
        "open_flag": 1 if st["open_count"] > 0 else 0,
        "appear_flag": appear_flag,
        "close_time": min(camp["end_date"], _MAX_INT32),
        "max_open_count": max_open_count(full_state, camp),
        "open_count": st["open_count"],
        "limited_sale_all_change_flag": 0,
        "last_open_time": st["last_open_time"],
    }


_CONTEXT_ODDS_COLUMN = {
    "daily_race": ("daily_race_odds", "daily_race_ceiling"),
    "legend_race": ("legend_race_odds", "legend_race_ceiling"),
    "team_stadium": ("team_stadium_odds", "team_stadium_ceiling"),
    "single_mode": ("single_mode_odds", "single_mode_ceiling"),
}


def roll(full_state: dict, context: str) -> dict | None:
    """Call once per race run. Returns the current limited_shop_info dict
    (appear_flag=1 iff THIS call produced at least one fresh open), or None
    if there's no active campaign right now."""
    now_ts = patch._servertime()
    camp = _campaign(now_ts)
    if camp is None:
        return None
    st = _state(full_state, camp["id"])

    odds, ceiling = camp["odds"].get(context, (0, 0))
    fresh_open = False
    if (odds > 0 and ceiling > 0 and st["open_count"] < ceiling
            and st["open_count"] < max_open_count(full_state, camp)):
        if random.randint(1, 1_000_000) <= odds:
            st["open_count"] += 1
            st["last_open_time"] = now_ts
            for disp, rewards in camp["slots"]:
                reward = _roll_slot(rewards)
                if reward is not None:
                    st["goods"].append({
                        "disp_order": disp,
                        "open_count": st["open_count"],
                        "reward_id": reward[0],
                        "item_exchange_id": reward[1],
                        "ribbon_value": reward[2],
                        "exchange_count": 0,
                    })
            fresh_open = True

    return _info(camp, st, 1 if fresh_open else 0, full_state)


def snapshot_info(full_state: dict) -> dict | None:
    """Read-only echo (item/show_exchange) -- appear_flag always 0."""
    camp = _campaign(patch._servertime())
    if camp is None:
        return None
    st = _state(full_state, camp["id"])
    return _info(camp, st, 0, full_state)


def _goods_exchange_id(g: dict):
    """item_exchange_id of a goods entry. Entries rolled before 2026-10-03 did
    not store it; those are Global-only and resolve through master."""
    if g.get("item_exchange_id"):
        return g["item_exchange_id"]
    reward = _reward_row(g["reward_id"]) if master_data.has_table("limited_exchange_reward") else None
    return reward["item_exchange_id"] if reward else 0


def goods_array(full_state: dict) -> list:
    """LimitedGoodsInfo per rolled good. exchange_count is how many of THAT
    open's copy were bought -- real exchange_multi names the copy by
    ex_param.open_count, and the same item_exchange_id comes back in every
    open (JP slot 4 is always exchange 10220). JP adds item_exchange_id and
    ribbon_value (dump.cs); Global ignores them."""
    camp = _campaign(patch._servertime())
    if camp is None:
        return []
    st = _state(full_state, camp["id"])
    return [{
        "disp_order": g["disp_order"],
        "open_count": g["open_count"],
        "reward_id": g["reward_id"],
        "exchange_count": g.get("exchange_count") or 0,
        "item_exchange_id": _goods_exchange_id(g),
        "ribbon_value": g.get("ribbon_value") or 0,
    } for g in st["goods"]]


def buy(full_state: dict, exchange_id: int, open_count: int, count: int,
        summary: dict) -> bool:
    """Buy `count` of one open's copy of a limited good (item/exchange_multi
    with ex_param.open_count). The copy's own limit is its item_exchange row's
    change_item_limit_num (1 on every limited good); the account-lifetime
    shop limit is NOT touched.

    BUG FIXED 2026-10-03: these went through shop._buy, whose lifetime limit
    of 1 refused every later open's copy of a good already bought once."""
    camp = _campaign(patch._servertime())
    if camp is None or count <= 0:
        return False
    st = _state(full_state, camp["id"])
    good = next((g for g in st["goods"]
                 if g["open_count"] == open_count and _goods_exchange_id(g) == exchange_id), None)
    row = shop._row(exchange_id)
    if good is None or row is None:
        return False
    cap = row["change_item_limit_num"] or 1
    bought = good.get("exchange_count") or 0
    if bought + count > cap:
        return False
    if not shop._pay(full_state, row, shop._unit_price(row, 0, count)):
        return False
    shop._grant(full_state, row, count, summary)
    good["exchange_count"] = bought + count
    return True


def _ok(data: dict) -> dict:
    return {"response_code": 1,
            "data_headers": {"result_code": 1, "notifications": {}}, "data": data}


@registry.endpoint("item/manual_close")
def handle_manual_close(payload: dict) -> dict:
    """No capture exists for this endpoint anywhere (request body is empty
    per dump.cs), so its real server-side effect is unknown. Deliberately a
    no-op beyond acknowledging: resetting open_count to let the shop
    re-trigger would let a player bypass the real per-campaign ceiling by
    repeatedly closing and re-rolling, which is a worse guess to get wrong
    than "the close button doesn't do anything server-side" (plausible if
    it's purely a client-side UI dismissal). Revisit if a real capture ever
    surfaces."""
    return _ok({})
