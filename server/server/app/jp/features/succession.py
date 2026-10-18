"""JP's borrowable-parent list and the six-slot profile picks behind it.

    pre_single_mode/get_succession_trained_chara  {is_get_friend_info}
    user/change_practice_partner                  {trained_chara_id_array}  (JP form)
    user/change_support_card                      {support_card_id_array}   (JP form)

plus total_skill_pt, the per-horse field the list (and every JP trained chara)
carries.

Every rule below was checked against all 29 real replies of the list
(jp_captures/CarrotJuicer, 2026-07-26..09-25: 20 with is_get_friend_info true,
9 false) -- see docs/FEATURE_GAP_AUDIT_2026-10-02.md.

THE LIST
--------
`WIRE` succession_trained_chara_data.summary_user_info_array is every account
the player FOLLOWS -- friend state 1 (follow) and 3 (mutual), never 2
(follower only): 120/120 against the friend/index captured 15 s earlier. It is
ordered by viewer_id ascending (27/29 replies; the other two are not ordered by
any field in the reply).

succession_trained_chara_array is, per listed account in that order, exactly
the horses in its partner_chara_id_array (the non-zero slots): 3,331/3,331
accounts. The FULL trained chara, as that account's own roster holds it.
Within one account the order is slot order on 9/9 flag-false replies; the
flag-true replies use an order no field in the reply explains, so slot order is
kept there too (the client lists them in its own sort).

Each summary's user_trained_chara_array is the digest of the same horses in
SLOT order -- the 18 identity/aptitude fields, skill_count = len(skill_array),
factor_info_array, factor_extend_array, race_result_list: 12,122/12,122
digests reproduced from the full entries.

friend_load_info is the friend/index reply when is_get_friend_info is set, and
null otherwise (29/29).

total_skill_pt
--------------
= skill points spent during the career + skill points left at its end, i.e.
everything the horse held: 6,839+5 = 6,844, 6,967+4 = 6,971, 6,837+27 = 6,864
on the three of the user's own careers whose every reply is captured. The real
server sends -1 where it has no record: horses created before 2025-08-25 and
Procurement horses (use_type 5) -- 594 distinct horses, no exception. Horses
this server finished before the field was tracked are in the same position and
go out as -1.
"""

from __future__ import annotations

import copy
import logging
import re

from ... import social
from ... import state as state_store
from ...handlers import collection, directory, trained_chara, user_profile
from ...handlers import single_mode_team as smt
from ...result_codes import refuse

log = logging.getLogger("uma-server")

SLOTS = 6
NO_RECORD = -1                     # `WIRE` total_skill_pt with no record
_FOLLOWING = (social.STATE_FOLLOW, social.STATE_MUTUAL)

# The fields of user_info_summary on this reply (`WIRE`, every entry of all 29).
_SUMMARY_FIELDS = (
    "viewer_id", "name", "honor_data", "last_login_time", "leader_chara_id",
    "leader_chara_dress_id", "support_card_id", "support_card_id_array",
    "partner_chara_id", "partner_chara_id_array", "comment", "fan", "rank_score",
    "team_stadium_win_count", "single_mode_play_count", "team_evaluation_point",
    "user_support_card", "user_trained_chara_array", "circle_info", "circle_user",
    "friend_state")
_DIGEST_FIELDS = (
    "trained_chara_id", "card_id", "rank_score", "rank", "proper_ground_turf",
    "proper_ground_dirt", "proper_running_style_nige", "proper_running_style_senko",
    "proper_running_style_sashi", "proper_running_style_oikomi", "proper_distance_short",
    "proper_distance_mile", "proper_distance_middle", "proper_distance_long", "rarity",
    "talent_level", "register_time")
# Roster bookkeeping that is not part of a trained chara on the wire.
_INTERNAL = ("grand_live_songs", "grand_live_lives_done")


def _ok(data) -> dict:
    return {"response_code": 1, "data_headers": {"result_code": 1, "notifications": {}},
            "data": data}


def _slots(values) -> list:
    """A six-slot array as stored: ints, padded/truncated to six."""
    out = [int(v or 0) for v in (values or [])][:SLOTS]
    return out + [0] * (SLOTS - len(out))


def wire_trained_chara(viewer_id, entry: dict) -> dict:
    """A roster entry as another player receives it."""
    out = {k: copy.deepcopy(v) for k, v in entry.items()
           if not k.startswith("_") and k not in _INTERNAL}
    out["viewer_id"] = social._wire_id(viewer_id)
    out.setdefault("total_skill_pt", NO_RECORD)
    return out


def _digest(entry: dict) -> dict:
    out = {"viewer_id": entry["viewer_id"]}
    for k in _DIGEST_FIELDS:
        out[k] = entry.get(k)
    out["skill_count"] = len(entry.get("skill_array") or [])
    out["factor_info_array"] = [{"factor_id": f.get("factor_id"), "level": f.get("level", 0)}
                                for f in entry.get("factor_info_array") or []]
    out["factor_extend_array"] = copy.deepcopy(entry.get("factor_extend_array") or [])
    out["race_result_list"] = copy.deepcopy(entry.get("race_result_list") or [])
    return out


def _user_info(viewer_id) -> dict:
    ui = state_store.extract_json_path(str(viewer_id), "load_index", "$.data.user_info")
    return ui if isinstance(ui, dict) else {}


def _entry(me, other, card: dict, friend_state: int):
    """(summary, [full trained charas]) for one followed account, or None
    for one with no profile."""
    ui = _user_info(other)
    if not ui:
        return None                  # no profile on this server: nothing to lend
    partners = [t for t in _slots(ui.get("partner_chara_id_array")) if t]
    roster = {c.get("trained_chara_id"): c
              for c in (state_store.get_state(other) or {}).get(trained_chara.ROSTER_KEY) or []}
    horses = [wire_trained_chara(other, roster[t]) for t in partners if t in roster]
    base = directory.summary(other, card, friend_state)
    summary = {k: base.get(k) for k in _SUMMARY_FIELDS}
    summary["support_card_id"] = int(ui.get("support_card_id") or base.get("support_card_id") or 0)
    summary["support_card_id_array"] = _slots(ui.get("support_card_id_array")
                                              or [summary["support_card_id"]])
    summary["partner_chara_id"] = int(ui.get("partner_chara_id") or 0)
    summary["partner_chara_id_array"] = _slots(ui.get("partner_chara_id_array"))
    usc = base.get("user_support_card") or {}
    summary["user_support_card"] = {k: usc.get(k, 0) for k in
                                    ("support_card_id", "exp", "limit_break_count")}
    summary["user_trained_chara_array"] = [_digest(h) for h in horses]
    summary["friend_state"] = friend_state
    return summary, horses


def handle_get_succession_trained_chara(payload: dict) -> dict:
    me = payload["viewer_id"]
    followed = sorted(social.following(me), key=lambda v: (not str(v).isdigit(),
                                                           int(v) if str(v).isdigit() else 0, str(v)))
    cards = directory.cards_for(followed)
    users, horses = [], []
    for other in followed:
        card = cards.get(str(other))
        if card is None:
            continue                 # never played: absent from every list
        state = social.friend_data(me, other)["state"]
        if state not in _FOLLOWING:
            continue
        entry = _entry(me, other, card, state)
        if entry is None:
            continue
        summary, theirs = entry
        users.append(summary)
        horses.extend(theirs)
    friend_info = None
    if payload.get("is_get_friend_info"):
        from ... import dispatch
        friend_index = dispatch.HANDLERS.get("friend/index") or dispatch.registry.get("friend/index")
        # Completed against friend/index's own schema: this reply's schema was
        # built from a flag-false capture, where the field is null.
        from .. import schema
        friend_info = schema.conform("friend/index", friend_index({"viewer_id": me}),
                                     True).get("data")
    return _ok({"succession_trained_chara_data": {"succession_trained_chara_array": horses,
                                                  "summary_user_info_array": users},
                "friend_load_info": friend_info})


# ------------------------------------------------------------ profile picks
def handle_change_practice_partner(payload: dict) -> dict:
    """`WIRE` 2.31.0 (3 replies): {trained_chara_id_array: [6 ids]} -> {user_info}
    with partner_chara_id_array = the array as sent and partner_chara_id left
    as it was (1131 across all three while slot 1 changed)."""
    viewer_id = payload["viewer_id"]
    raw = payload.get("trained_chara_id_array")
    if not isinstance(raw, list) or len(raw) != SLOTS:
        return refuse()
    picks = _slots(raw)
    chosen = [t for t in picks if t]
    owned = {c.get("trained_chara_id") for c in trained_chara._get_or_seed_roster(viewer_id)}
    if not chosen or len(set(chosen)) != len(chosen) or not set(chosen) <= owned:
        return refuse()
    full_state = state_store.get_state(viewer_id) or {}
    user_info = user_profile._load_data(full_state, viewer_id).setdefault("user_info", {})
    user_info["partner_chara_id_array"] = picks
    return user_profile._save_and_republish(viewer_id, full_state, user_info)


def handle_change_support_card(payload: dict) -> dict:
    """`WIRE` 2.31.0: {support_card_id_array: [6 ids]} -> {user_info} with
    support_card_id_array = the array as sent and support_card_id = slot 1."""
    viewer_id = payload["viewer_id"]
    raw = payload.get("support_card_id_array")
    if not isinstance(raw, list) or len(raw) != SLOTS:
        return refuse()
    picks = _slots(raw)
    chosen = [c for c in picks if c]
    full_state = state_store.get_state(viewer_id) or {}
    owned = {c.get("support_card_id") for c in full_state.get(collection.SUPPORT_CARD_KEY) or []}
    if not picks[0] or len(set(chosen)) != len(chosen) or not set(chosen) <= owned:
        return refuse()
    user_info = user_profile._load_data(full_state, viewer_id).setdefault("user_info", {})
    user_info["support_card_id_array"] = picks
    user_info["support_card_id"] = picks[0]
    return user_profile._save_and_republish(viewer_id, full_state, user_info)


# ------------------------------------------------------------- total_skill_pt
SPENT_KEY = "jp_career_skill_point_spent"
_CAREER = re.compile(r"^single_mode(_[a-z]+)?/(gain_skills|finish|start)$")


def _career_sp(full_state: dict):
    ci = ((full_state.get(smt.STATE_KEY) or {}).get("data") or {}).get("chara_info") or {}
    sp = ci.get("skill_point")
    return int(sp) if isinstance(sp, int) else None


def before(endpoint: str, payload: dict):
    """gain_skills: the skill points held before the purchase. finish: the
    skill points left and the newest roster id, before the horse is filed.
    (gain_skills is the only call on this server that lowers skill_point.)"""
    m = _CAREER.match(endpoint)
    if not m:
        return None
    full_state = state_store.get_state(payload.get("viewer_id")) or {}
    if m.group(2) == "gain_skills":
        return {"sp": _career_sp(full_state)}
    if m.group(2) == "finish":
        roster = full_state.get(trained_chara.ROSTER_KEY) or []
        return {"sp": _career_sp(full_state),
                "top": max((c.get("trained_chara_id") or 0 for c in roster), default=0)}
    return None


def after(endpoint: str, payload: dict, resp: dict, noted) -> None:
    m = _CAREER.match(endpoint)
    if not m or (resp.get("data_headers") or {}).get("result_code", 1) != 1:
        return
    viewer_id = payload.get("viewer_id")
    full_state = state_store.get_state(viewer_id) or {}
    action = m.group(2)
    if action == "start":
        full_state[SPENT_KEY] = 0
    elif action == "gain_skills":
        held, now = (noted or {}).get("sp"), _career_sp(full_state)
        if held is None or now is None or SPENT_KEY not in full_state:
            return
        full_state[SPENT_KEY] += max(0, held - now)
    elif action == "finish":
        spent = full_state.pop(SPENT_KEY, None)
        left = (noted or {}).get("sp")
        if spent is not None and left is not None:
            top = (noted or {}).get("top", 0)
            for c in full_state.get(trained_chara.ROSTER_KEY) or []:
                if (c.get("trained_chara_id") or 0) > top:
                    c["total_skill_pt"] = spent + left
                    _restamp(resp.get("data"), c["trained_chara_id"], spent + left)
    state_store.save_state(viewer_id, full_state)


def _restamp(node, trained_chara_id: int, value: int) -> None:
    """The finish reply was built before the value existed: set it on every
    copy of the new horse in it."""
    if isinstance(node, dict):
        if node.get("trained_chara_id") == trained_chara_id and "skill_array" in node:
            node["total_skill_pt"] = value
        for v in node.values():
            _restamp(v, trained_chara_id, value)
    elif isinstance(node, list):
        for v in node:
            _restamp(v, trained_chara_id, value)


def mark_unrecorded(node) -> None:
    """Every full trained chara in a reply without a recorded total goes out
    as -1, the real server's value for a horse it has no record for (schema
    completion would otherwise fill 0)."""
    if isinstance(node, dict):
        if "trained_chara_id" in node and "skill_array" in node and "support_card_list" in node:
            node.setdefault("total_skill_pt", NO_RECORD)
        for v in node.values():
            mark_unrecorded(v)
    elif isinstance(node, list):
        for v in node:
            mark_unrecorded(v)


HANDLERS = {
    "pre_single_mode/get_succession_trained_chara": handle_get_succession_trained_chara,
    "user/change_practice_partner": handle_change_practice_partner,
    "user/change_support_card": handle_change_support_card,
}
