"""JP's support-card system: no levelling, no Support Pt, dupes uncap on arrival.

JP removed support-card levelling (Support Pt's last mission reward in JP
master starts 2025/09/09). What the real JP server does now (`WIRE`, the
user's own account, jp_captures):

    - a card's exp is ALWAYS its uncap's level cap (support_card_limit x
      support_card_level): all 411 owned cards in a real load/index sit
      exactly there, and a fresh account's starter Rs arrive at 2910 (Lv20);
    - a copy raises limit_break_count by one on the spot; only a copy past
      LB4 lands in `stock` (real load/index: stock > 0 only at LB4). A real
      gacha/exec took SR 20098 from LB1 to LB2 with exp 31690 (Lv35 cap),
      and the reply said so in reward_summary_info.add_support_card_limit_
      break_array: {support_card_id, before_limit_break_count,
      after_limit_break_count, is_send_stock, is_send_present};
    - Support Pt (item 110) is gone: not one of 919 real reward/load replies
      carries it, and none of the 4006 live missions pays it;
    - support_card/strengthen and the dupe route of support_card/limit_break
      are never called; limit_break_item (uncap items) still is, and its
      reply's card is at the new cap (SR LB4 -> exp 74990).

Every grant path the shared handlers have (gacha, exchange, presents, shop)
banks a copy into `stock`, which is right for Global. apply() turns that into
JP's rule after the handler has run, for any reply that hands out or shows
support cards, so Global's handlers stay exactly as they are.
"""

from __future__ import annotations

from ... import accounts
from ... import state as state_store
from ...handlers import cards, collection, shop
from ...result_codes import refuse

MAX_LIMIT_BREAK = 4
SUPPORT_PT_ITEM_ID = 110
_ITEM_CATEGORY = 30

# Where a reply shows the viewer's OWN cards (lender/friend cards elsewhere in
# a reply are someone else's and are left alone).
_OWN_CARD_KEYS = ("add_support_card_list", "support_card_list")


def normalize(full_state: dict) -> tuple[dict, bool]:
    """Apply JP's rule to the owned cards: spare copies raise the uncap up to
    LB4, and exp sits at the uncap's cap. Drops Support Pt. Returns
    ({support_card_id: before_limit_break_count} for every card whose uncap
    moved, whether full_state changed); changes full_state in place."""
    moved, changed = {}, False
    for c in full_state.get(collection.SUPPORT_CARD_KEY) or []:
        sid = c.get("support_card_id")
        lb = int(c.get("limit_break_count") or 0)
        stock = int(c.get("stock") or 0)
        spend = min(stock, max(0, MAX_LIMIT_BREAK - lb))
        if spend:
            moved[sid] = lb
            lb += spend
            c["limit_break_count"] = lb
            c["stock"] = stock - spend
            changed = True
        cap = cards._support_level_cap(sid, lb)
        if cap is not None and c.get("exp") != cap[1]:
            c["exp"] = cap[1]
            changed = True
    items = shop._items(full_state)
    kept = [i for i in items if i.get("item_id") != SUPPORT_PT_ITEM_ID]
    if len(kept) != len(items):
        items[:] = kept
        changed = True
    return moved, changed


def _is_support_pt(entry: dict) -> bool:
    if entry.get("item_id") != SUPPORT_PT_ITEM_ID:
        return False
    cat = entry.get("item_category", entry.get("item_type", _ITEM_CATEGORY))
    return cat == _ITEM_CATEGORY


def _walk(node, found: dict):
    """Collect the reply's own-card entries, single support_card_data maps and
    reward summaries, and drop Support Pt from every item list."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _OWN_CARD_KEYS and isinstance(v, list):
                found["entries"].extend(e for e in v if isinstance(e, dict))
            elif k == "support_card_data" and isinstance(v, dict) and "limit_break_count" in v:
                found["entries"].append(v)
            if k == "add_support_card_list" and v:
                found["summaries"].append(node)
            _walk(v, found)
    elif isinstance(node, list):
        if any(isinstance(e, dict) and _is_support_pt(e) for e in node):
            node[:] = [e for e in node if not (isinstance(e, dict) and _is_support_pt(e))]
        for e in node:
            _walk(e, found)


def _limit_break_array(summary: dict, owned: dict, moved: dict) -> list:
    """One entry per card this reply grants, in grant order (`WIRE` it follows
    add_support_card_num_array, not add_support_card_list's id order)."""
    order = [e.get("support_card_id") for e in summary.get("add_support_card_num_array") or []]
    order += [e.get("support_card_id") for e in summary["add_support_card_list"]]
    out, seen = [], set()
    for sid in order:
        card = owned.get(sid)
        if sid in seen or card is None:
            continue
        seen.add(sid)
        after = card.get("limit_break_count") or 0
        out.append({"support_card_id": sid,
                    "before_limit_break_count": moved.get(sid, after),
                    "after_limit_break_count": after,
                    # Only a copy past LB4 goes to stock, so a card at LB4 that
                    # holds stock received one this time.
                    "is_send_stock": after >= MAX_LIMIT_BREAK and (card.get("stock") or 0) > 0,
                    "is_send_present": False})
    return out


def apply(endpoint: str, payload: dict, resp: dict) -> dict:
    """JP's post-step for every successful reply that grants or shows the
    viewer's support cards (or Support Pt)."""
    data = resp.get("data")
    viewer_id = (payload or {}).get("viewer_id")
    if not isinstance(data, dict) or not viewer_id \
            or (resp.get("data_headers") or {}).get("result_code", 1) != 1:
        return resp
    found = {"entries": [], "summaries": []}
    _walk(data, found)
    if not found["entries"] and endpoint != "load/index":
        return resp
    with accounts.viewer_lock(viewer_id):
        full_state = state_store.get_state(viewer_id)
        if not full_state:
            return resp
        moved, changed = normalize(full_state)
        if changed:
            state_store.save_state(viewer_id, full_state)
    owned = {c.get("support_card_id"): c for c in full_state.get(collection.SUPPORT_CARD_KEY) or []}
    for e in found["entries"]:
        card = owned.get(e.get("support_card_id"))
        if card is not None:
            for k in ("exp", "limit_break_count", "stock"):
                e[k] = card.get(k) or 0
    for summary in found["summaries"]:
        summary["add_support_card_limit_break_array"] = _limit_break_array(summary, owned, moved)
    return resp


def _refuse_levelling(payload: dict) -> dict:
    """No levelling in JP: exp is always at the cap, and copies uncap on
    arrival, so there is nothing for these to do."""
    return refuse()


HANDLERS = {
    "support_card/strengthen": _refuse_levelling,
    "support_card/limit_break": _refuse_levelling,
}
