"""JP select step-up banners (gacha_data.type 14): a ladder of five ten-pulls,
each its own gacha id, climbed in order and repeated draw_limit times.

`DUMP` master gacha_stepup maps stepup_id (= the step-1 gacha id) to its rungs
by stepup_step. Rungs 2-5 have no gacha_available rows: gacha_odds_id points
them at step 1's pool. That pool's SSRs are ten stand-in slots (301-310, 3000
odds each = the whole 3% SSR mass), which gacha/select_stepup fills with SSRs
from master select_pickup (keyed by stepup_id). cost_type 92 = paid carats
only; cost_single x 10 is the ten-pull price (500/700/1000/1300/1500).
draw_guarantee_rarity puts an SR (steps 1-2) or one of the picked SSRs
(steps 3-5) in the last slot; draw_guarantee_type 1 (step 5) makes that slot
the pick the client names in draw_guarantee_card_id.

`WIRE` CarrotJuicer 2026-09-02, two full loops of stepup 50240 (draw_limit 2):
- gacha/index lists only the rung the player is on (50240, then 50241 ...),
  and gacha_select_stepup_info_array carries {stepup_id, loop_count (1-based),
  selected_info_array, before_selected_info_array}; a fresh account gets
  loop_count 1 and empty arrays.
- every exec is draw_type 1, draw_num 10. Only coin (paid) drops; fcoin is
  untouched. limit_item_info.num stays 0 (no exchange points).
- after step 5 the ladder returns to step 1: loop_count + 1, the picks move to
  before_selected_info_array and selected_info_array empties. Once the last
  loop is done, the banner and its stepup info are gone from the index.
- the select_stepup request sends loop_count 0; the reply carries the server's
  own loop_count and before_selected_info_array.
"""

from __future__ import annotations

import copy
import functools

from ... import master_data
from ... import state as state_store
from ...handlers import gacha
from ...result_codes import ResultCode, refuse

STEPUP_KEY = "jp_gacha_select_stepup"   # {str(stepup_id): {loop_count, step, selected_info_array, before_selected_info_array}}
PAID_COIN = 92                          # gacha_data.cost_type: paid carats only
PROMISED_CARD = 1                       # gacha_data.draw_guarantee_type: the named pick
_SLOT_MAX = 1000                        # real card ids start at 10001 / 100101


def _ok(data: dict) -> dict:
    return {"response_code": 1, "data_headers": {"result_code": 1, "notifications": {}}, "data": data}


@functools.lru_cache(maxsize=1)
def _ladders() -> dict:
    """{stepup_id: [rung gacha ids by step]}. Cached: master is read-only."""
    out: dict = {}
    for r in master_data.query(
            "SELECT stepup_id, target_gacha_id FROM gacha_stepup ORDER BY stepup_id, stepup_step"):
        out.setdefault(r["stepup_id"], []).append(r["target_gacha_id"])
    return out


@functools.lru_cache(maxsize=1)
def _rung_index() -> dict:
    """{rung gacha id: (stepup_id, step index)}."""
    return {gid: (sid, i) for sid, rungs in _ladders().items() for i, gid in enumerate(rungs)}


def ladder_of(gacha_id: int):
    """(stepup_id, step index) for a rung, or None if the banner is no ladder."""
    return _rung_index().get(int(gacha_id))


@functools.lru_cache(maxsize=None)
def _rung(gacha_id: int) -> dict:
    return dict(master_data.query_one(
        "SELECT cost_type, cost_single, draw_limit, gacha_odds_id, draw_guarantee_type "
        "FROM gacha_data WHERE id=?", (gacha_id,)) or {})


@functools.lru_cache(maxsize=None)
def _slots(stepup_id: int) -> tuple:
    return tuple(r["card_id"] for r in master_data.query(
        "SELECT card_id FROM gacha_available WHERE gacha_id=? AND card_id<? ORDER BY card_id",
        (stepup_id, _SLOT_MAX)))


@functools.lru_cache(maxsize=None)
def _candidates(stepup_id: int) -> frozenset:
    return frozenset(r["card_id"] for r in master_data.query(
        "SELECT card_id FROM select_pickup WHERE gacha_id=?", (stepup_id,)))


def _progress(full_state: dict, stepup_id: int) -> dict:
    """The account's place on the ladder, defaults for one never touched."""
    stored = (full_state.get(STEPUP_KEY) or {}).get(str(stepup_id)) or {}
    return {"loop_count": max(1, int(stored.get("loop_count") or 1)),
            "step": int(stored.get("step") or 0),
            "selected_info_array": list(stored.get("selected_info_array") or []),
            "before_selected_info_array": list(stored.get("before_selected_info_array") or [])}


def _info(stepup_id: int, prog: dict) -> dict:
    """GachaSelectStepupInfo on the wire."""
    return {"stepup_id": stepup_id, "loop_count": prog["loop_count"],
            "selected_info_array": copy.deepcopy(prog["selected_info_array"]),
            "before_selected_info_array": copy.deepcopy(prog["before_selected_info_array"])}


def _finished(stepup_id: int, prog: dict) -> bool:
    limit = int(_rung(stepup_id).get("draw_limit") or 0)
    return bool(limit) and prog["loop_count"] > limit


# ------------------------------------------------------------ gacha hooks
def rung_banner(banner: dict) -> dict:
    """gacha.BANNER_HOOKS entry: a rung draws from step 1's pool at its own
    paid-only price, earns no exchange points, and on step 5 promises the
    named pick."""
    hit = ladder_of(banner["gacha_id"])
    if not hit:
        return banner
    row = _rung(banner["gacha_id"])
    if not banner.get("pool") and row.get("gacha_odds_id"):
        banner["pool"] = [dict(r) for r in master_data.query(
            "SELECT card_id, rarity, odds, is_pickup FROM gacha_available WHERE gacha_id=?",
            (row["gacha_odds_id"],))]
    single = int(row.get("cost_single") or 0)
    banner.update({"single_cost": single, "multi_cost": single * 10,
                   "paid_only": row.get("cost_type") == PAID_COIN,
                   "promised_card": row.get("draw_guarantee_type") == PROMISED_CARD,
                   "counts_pity": False})
    return banner


def picked_pool(full_state: dict, gacha_id: int, pool: list) -> list:
    """gacha.POOL_HOOKS entry: each SSR slot becomes the card the player put
    in it, at the slot's odds. An unfilled slot is never drawn."""
    hit = ladder_of(gacha_id)
    if not hit:
        return pool
    picks = {int(s.get("target_card_id") or 0): int(s.get("selected_card_id") or 0)
             for s in _progress(full_state, hit[0])["selected_info_array"]}
    out = []
    for c in pool:
        if c["card_id"] < _SLOT_MAX:
            if not picks.get(c["card_id"]):
                continue
            c = {**c, "card_id": picks[c["card_id"]]}
        out.append(c)
    return out


if rung_banner not in gacha.BANNER_HOOKS:
    gacha.BANNER_HOOKS.append(rung_banner)
if picked_pool not in gacha.POOL_HOOKS:
    gacha.POOL_HOOKS.append(picked_pool)


# ---------------------------------------------------------------- gacha/index
def decorate_index(full_state: dict, data: dict) -> None:
    """Show each ladder as the rung the player is on, drop finished ladders,
    and add gacha_select_stepup_info_array for the ones still listed."""
    listed, infos = [], []
    for g in data.get("gacha_info_list") or []:
        hit = ladder_of(g["id"])
        if not hit:
            listed.append(g)
            continue
        stepup_id = hit[0]
        if any(i["stepup_id"] == stepup_id for i in infos):
            continue
        prog = _progress(full_state, stepup_id)
        if _finished(stepup_id, prog):
            continue
        rungs = _ladders()[stepup_id]
        listed.append({**g, "id": rungs[min(prog["step"], len(rungs) - 1)]})
        infos.append(_info(stepup_id, prog))
    data["gacha_info_list"] = listed
    data["gacha_select_stepup_info_array"] = infos


# ---------------------------------------------------------------- endpoints
def handle_select_stepup(payload: dict) -> dict:
    """Store the player's SSR picks for a ladder: every slot filled, each with
    a different card from the ladder's candidates. The reply is the server's
    view: its own loop_count and before_selected_info_array, never the
    client's (which sends loop_count 0)."""
    info = payload.get("select_stepup_info") or {}
    stepup_id = int(info.get("stepup_id") or 0)
    if stepup_id not in _ladders():
        return refuse(ResultCode.PARAM_ERROR)
    slots, candidates = _slots(stepup_id), _candidates(stepup_id)
    picks = [{"target_card_id": int(s.get("target_card_id") or 0),
              "selected_card_id": int(s.get("selected_card_id") or 0)}
             for s in info.get("selected_info_array") or []]
    picks.sort(key=lambda p: p["target_card_id"])
    if ([p["target_card_id"] for p in picks] != list(slots)
            or len({p["selected_card_id"] for p in picks}) != len(picks)):
        return refuse(ResultCode.PARAM_ERROR)
    if any(p["selected_card_id"] not in candidates for p in picks):
        return refuse(ResultCode.GACHA_UNSELECTABLE_CARD_SELECTED)
    viewer_id = payload["viewer_id"]
    full_state = state_store.get_state(viewer_id) or {}
    prog = _progress(full_state, stepup_id)
    if _finished(stepup_id, prog):
        return refuse(ResultCode.GACHA_NOT_IN_TERM)
    prog["selected_info_array"] = picks
    full_state.setdefault(STEPUP_KEY, {})[str(stepup_id)] = prog
    state_store.save_state(viewer_id, full_state)
    return _ok({"select_stepup_info": _info(stepup_id, prog)})


def handle_exec(payload: dict) -> dict:
    """gacha/exec: a rung pulls only as the player's current step, as a
    ten-pull, with every slot picked; then the ladder moves on. Every other
    banner is Global's pull untouched."""
    gacha_id = int(payload.get("gacha_id") or 0)
    hit = ladder_of(gacha_id)
    if not hit:
        return gacha.handle_exec(payload)
    stepup_id, step = hit
    viewer_id = payload["viewer_id"]
    prog = _progress(state_store.get_state(viewer_id) or {}, stepup_id)
    if _finished(stepup_id, prog) or prog["step"] != step:
        return refuse(ResultCode.GACHA_NOT_IN_TERM)
    if len(prog["selected_info_array"]) != len(_slots(stepup_id)):
        return refuse(ResultCode.GACHA_UNSELECTABLE_CARD_SELECTED)
    if int(payload.get("draw_num") or 0) != 10 or payload.get("item_id"):
        return refuse(ResultCode.PARAM_ERROR)

    resp = gacha.handle_exec(payload)
    if (resp.get("data_headers") or {}).get("result_code") != 1:
        return resp
    full_state = state_store.get_state(viewer_id) or {}
    prog = _progress(full_state, stepup_id)
    if step + 1 < len(_ladders()[stepup_id]):
        prog["step"] = step + 1
    else:
        prog.update({"step": 0, "loop_count": prog["loop_count"] + 1,
                     "before_selected_info_array": prog["selected_info_array"],
                     "selected_info_array": []})
    full_state.setdefault(STEPUP_KEY, {})[str(stepup_id)] = prog
    state_store.save_state(viewer_id, full_state)
    return resp


HANDLERS = {
    "gacha/select_stepup": handle_select_stepup,
    "gacha/exec": handle_exec,
}
