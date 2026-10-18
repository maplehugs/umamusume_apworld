"""The Uma Note directory: which trained umamusume the Archive keeps, how it
ranks them, and what it pays for a new scenario record.

Every rule here is read off real-server replies; none is fitted.

WHICH HORSES. The directory holds the TOP 3 by rank_score of every
(card_id, scenario_id) group. Global captures/20260818_081331/0018_note_index:
197 entries, 93 groups, never more than 3 to a group, directory_ranking 1..3
ordered by rank_score within the group; JP finishes show the same groups
(e.g. 104002: scenario 12 x3 + scenario 14 x1). The six starter horses
(trained_chara_id 1..6) are never in it: the fresh-account captures
(20260816_140811, 20260816_202505) list only the two careers, and JP's
top_directory_card_array never names a starter across 26 note/index replies.

HIDDEN HORSES. A horse removed or transferred while it is in its group's top
3 (counting horses already hidden) is kept, out of the roster, so the
directory still shows it: JP trained_chara/remove answers
update_trained_chara_id_array (kept hidden) / remove_trained_chara_id_array
(deleted), 585/585 removals consistent (docs/FEATURE_GAP_AUDIT_2026-10-02.md
A6), and the kept ones drop out of trained_chara/load while JP note/index
still lists them (66 top entries = 46 roster cards + 20 held only by hidden
horses). A hidden horse pushed out of its top 3 by a newer one is gone.

SCORE. score_summary.directory_card is the sum, per CARD, of the top 3
rank_scores among that card's directory entries (across scenarios):
1,675,160 on the 197-entry Global capture, exact to the point; the fresh
account's 15,508 likewise. (One best per card gives 709,772; every entry
2,689,669.)

FINISH. single_mode_finish_common carries the new horse's CARD directory
(all its groups), directory_ranking = the new horse's place in its group or 0
outside the top 3, and directory_card_num = the number of directory entries
(load/index carries the same count: 197 next to the 197-entry note/index).
scenario_record_array is the scenario's top 3 across all cards, sent only
when the new horse is in it (666/666 JP finishes), and
scenario_record_reward_array pays every single_mode_scenario_record
threshold the new score crosses above the scenario's previous best (Global
20260816_140811: 5,197 -> 10,311 pays exactly the 6k/7k/8k/10k rows), into
the present box under message_id 50 (that session's present/index).
"""

from __future__ import annotations

import contextvars
import copy

from .. import master_data

HIDDEN_KEY = "directory_hidden_chara"
PER_GROUP = 3
_STARTER_MAX_ID = 6
_SCENARIO_RECORD_MESSAGE_ID = 50

# (kept_hidden_ids, deleted_ids) of the last retire() in this request, for
# JP's remove reply (app/jp/features/archive.py) -- Global's reply has no
# such fields.
LAST_RETIRE: contextvars.ContextVar = contextvars.ContextVar("LAST_RETIRE", default=None)


def eligible(rec: dict) -> bool:
    """A horse the directory can hold: not a starter, not one of this
    server's generated house veterans, not a rental copy."""
    from . import trained_chara
    tcid = rec.get("trained_chara_id") or 0
    if tcid <= _STARTER_MAX_ID or tcid >= trained_chara.HOUSE_ID_BASE:
        return False
    return not rec.get("owner_viewer_id") and not rec.get("use_type")


def hidden(full_state: dict) -> list:
    rows = full_state.get(HIDDEN_KEY)
    return rows if isinstance(rows, list) else []


def pool(full_state: dict, roster: list) -> list:
    """Everything the directory ranks: the eligible roster plus the hidden."""
    return [r for r in roster if eligible(r)] + hidden(full_state)


def _order(rec: dict):
    return (-(rec.get("rank_score") or 0), rec.get("trained_chara_id") or 0)


def _groups(horses: list) -> dict:
    out: dict = {}
    for rec in horses:
        out.setdefault((rec.get("card_id"), rec.get("scenario_id")), []).append(rec)
    for members in out.values():
        members.sort(key=_order)
    return out


def ranked(horses: list) -> list:
    """[(record, directory_ranking)] for every directory entry, ordered by
    card, scenario, ranking (the capture's order)."""
    groups = _groups(horses)
    out = []
    for key in sorted(groups, key=lambda k: (k[0] or 0, k[1] or 0)):
        out.extend((rec, i) for i, rec in enumerate(groups[key][:PER_GROUP], start=1))
    return out


def ranking_of(horses: list, trained_chara_id) -> int:
    for rec, rank in ranked(horses):
        if rec.get("trained_chara_id") == trained_chara_id:
            return rank
    return 0


def _wire(viewer_id, rec: dict, rank: int) -> dict:
    """The nested trained_chara: the record, its ranking, and the owner's
    viewer_id (None keeps the record's own)."""
    tc = copy.deepcopy(rec)
    if viewer_id is not None:
        tc["viewer_id"] = viewer_id
    tc["directory_ranking"] = rank
    return tc


def card_array(viewer_id, horses: list, card_id=None) -> list:
    """DirectoryCard[] -- every entry, or one card's."""
    return [{"card_id": rec.get("card_id"), "directory_ranking": rank,
             "trained_chara": _wire(viewer_id, rec, rank)}
            for rec, rank in ranked(horses)
            if card_id is None or rec.get("card_id") == card_id]


def top_per_card(viewer_id, horses: list) -> list:
    """One entry per card: its best directory horse (ranking 1 of its best
    group), ascending card_id -- JP note/index top_directory_card_array."""
    best: dict = {}
    for rec in horses:
        cid = rec.get("card_id")
        if cid and (cid not in best or _order(rec) < _order(best[cid])):
            best[cid] = rec
    return [{"card_id": cid, "directory_ranking": 1,
             "trained_chara": _wire(viewer_id, best[cid], 1)}
            for cid in sorted(best)]


def entry_count(horses: list) -> int:
    return len(ranked(horses))


def card_score(horses: list) -> int:
    """score_summary.directory_card: per card, the top 3 rank_scores among
    its directory entries."""
    per_card: dict = {}
    for rec, _ in ranked(horses):
        per_card.setdefault(rec.get("card_id"), []).append(rec.get("rank_score") or 0)
    return sum(sum(sorted(v, reverse=True)[:PER_GROUP]) for v in per_card.values())


def scenario_top(viewer_id, horses: list, scenario_id) -> list:
    """ScenarioRecord[] -- the scenario's top 3 across every card."""
    members = sorted((r for r in horses if r.get("scenario_id") == scenario_id),
                     key=_order)[:PER_GROUP]
    return [{"scenario_id": scenario_id, "directory_ranking": i,
             "trained_chara": _wire(viewer_id, rec, i)}
            for i, rec in enumerate(members, start=1)]


def scenario_highs(full_state: dict, horses: list) -> dict:
    """{scenario_id: highest rank_score}: the recorded ledger, never below
    what the directory itself holds."""
    from . import note_archive
    ledger = note_archive._note_state(full_state).setdefault("scenario_high_scores", {})
    highs = {int(k): v for k, v in ledger.items()}
    for rec in horses:
        sid = rec.get("scenario_id")
        if sid:
            highs[sid] = max(highs.get(sid, 0), rec.get("rank_score") or 0)
    return highs


def retire(full_state: dict, roster: list, ids) -> tuple[list, list]:
    """Horses `ids` leave the roster: each one in its group's top 3 (hidden
    horses counted) moves to the hidden store, the rest are deleted. The
    caller drops all of `ids` from the roster. Returns (kept_hidden,
    deleted) and records it in LAST_RETIRE."""
    doomed = set(ids)
    horses = pool(full_state, roster)
    in_top = {rec.get("trained_chara_id") for rec, _ in ranked(horses)}
    store = full_state.setdefault(HIDDEN_KEY, [])
    kept, deleted = [], []
    for rec in roster:
        tcid = rec.get("trained_chara_id")
        if tcid not in doomed:
            continue
        if eligible(rec) and tcid in in_top:
            store.append(copy.deepcopy(rec))
            kept.append(tcid)
        else:
            deleted.append(tcid)
    LAST_RETIRE.set((kept, deleted))
    return kept, deleted


def prune_hidden(full_state: dict, roster: list) -> None:
    """Drop hidden horses a newer one has pushed out of their top 3."""
    store = hidden(full_state)
    if not store:
        return
    in_top = {rec.get("trained_chara_id") for rec, _ in ranked(pool(full_state, roster))}
    full_state[HIDDEN_KEY] = [r for r in store if r.get("trained_chara_id") in in_top]


def settle_scenario_record(full_state: dict, horses_before: list, new_rec: dict) -> list:
    """Pay every single_mode_scenario_record threshold the new horse crosses
    above its scenario's previous best, into the present box, and move the
    ledger. Returns DisplayRewardInfo[] for scenario_record_reward_array."""
    from . import note_archive, presents
    sid = new_rec.get("scenario_id")
    score = new_rec.get("rank_score") or 0
    if not sid:
        return []
    prev = scenario_highs(full_state, horses_before).get(sid, 0)
    ledger = note_archive._note_state(full_state).setdefault("scenario_high_scores", {})
    ledger[str(sid)] = max(prev, score)
    if score <= prev:
        return []
    out = []
    for row in master_data.query(
            "SELECT reward_item_category, reward_item_id, reward_num "
            "FROM single_mode_scenario_record WHERE scenario_id = ? "
            "AND need_record_min > ? AND need_record_min <= ? ORDER BY need_record_min",
            (sid, prev, score)):
        cat, iid, num = (row["reward_item_category"], row["reward_item_id"],
                         row["reward_num"])
        presents.send(full_state, cat, iid, num, message_id=_SCENARIO_RECORD_MESSAGE_ID)
        out.append({"item_type": cat, "item_id": iid, "item_num": num})
    return out
