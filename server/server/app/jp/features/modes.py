"""JP-only game modes: what each one's index screen says for this account, and
a clean refusal for the actions not built yet.

Index screens are answered from master.mdb (which event is running or ran
last) plus the account's own progress, which starts empty -- the state a new
account has on the real server. app/jp/schema.py completes the remaining
fields to the real reply's shape.

ACTIONS that are not implemented REFUSE (result_code 205), never succeed
empty: a fake success makes the client believe it entered a race, started a
job or claimed a reward, and its local state diverges from the server's --
the same reason Global refuses career starts for scenarios it does not serve.
Status polls and replays of things that cannot change state are acknowledged.
"""

from __future__ import annotations

import time

from ... import master_data
from ... import state as state_store
from ...result_codes import refuse
from . import jobs

_WEEK = 7 * 24 * 3600


def _ok(data=None) -> dict:
    env = {"response_code": 1, "data_headers": {"result_code": 1, "notifications": {}}}
    if data is not None:
        env["data"] = data
    return env


def _latest(table: str, id_col: str, start_col: str = "start_date"):
    """The newest row that has started -- the running event, or the last one."""
    if not master_data.has_table(table):
        return None
    return master_data.query_one(
        f"SELECT * FROM {table} WHERE {start_col} <= ? ORDER BY {start_col} DESC, {id_col} DESC LIMIT 1",
        (int(time.time()),))


# ---------------------------------------------------------------------- heroes
def handle_heroes_index(payload: dict) -> dict:
    row = _latest("heroes_data", "heroes_id")
    return _ok({"heroes_id": int(row["heroes_id"]) if row else 0})


# ---------------------------------------------------------------- ultimate race
def handle_ultimate_race_index(payload: dict) -> dict:
    """No records yet: every array empty."""
    return _ok({"ultimate_race_record_array": [], "ultimate_race_archive_record_array": [],
                "ultimate_race_top_cutin_info_array": []})


# ------------------------------------------------------------- factor research
def handle_factor_research_index(payload: dict) -> dict:
    row = _latest("factor_research_data", "factor_research_event_id")
    return _ok({"factor_research_event_id": int(row["factor_research_event_id"]) if row else 0,
                "special_event_type": int(row["special_event_type"]) if row else 0})


# ---------------------------------------------------------------- collect raid
def handle_collect_raid_index(payload: dict) -> dict:
    # `WIRE` the client polls at this interval.
    return _ok({"raid_polling_interval": 5})


# ------------------------------------------------------------------- transfer
def handle_transfer_rotation_index(payload: dict) -> dict:
    """The current weekly rotation: schedule rows cycle through their
    transfer_rotation_data ids once a week from base_date."""
    sched = _latest("transfer_rotation_schedule", "id")
    rotation_id = 0
    if sched is not None:
        ids = [r["id"] for r in master_data.query(
            "SELECT id FROM transfer_rotation_data WHERE schedule_id=? ORDER BY id", (sched["id"],))]
        if ids:
            weeks = max(0, (int(time.time()) - int(sched["base_date"])) // _WEEK)
            rotation_id = ids[weeks % len(ids)]
    return _ok({"transfer_rotation_id": rotation_id, "transfer_rotation_detail_array": None})


# ------------------------------------------------------------- training report
def handle_training_report_index(payload: dict) -> dict:
    """The running season (training_report_pass dates are master TEXT, so
    _latest's integer compare cannot pick it) and the points jobs earned."""
    row = jobs.training_report_season()
    season_id = int(row["season_id"]) if row else 0
    full_state = state_store.get_state(payload["viewer_id"]) or {}
    return _ok({"training_report_info": {"season_id": season_id,
                                         "point": jobs.season_points(full_state, season_id),
                                         "is_payment": 0,
                                         "is_need_premium_pass_purchase_start_dialog": False},
                "reward_info_array": [], "season_change_flag": False,
                "premium_pass_reward_confirm_dialog_flag": False})


def _ack(payload: dict) -> dict:
    return _ok()


def _not_built(payload: dict) -> dict:
    return refuse()


_INDEX = {
    "heroes/index": handle_heroes_index,
    "ultimate_race/index": handle_ultimate_race_index,
    "factor_research/index": handle_factor_research_index,
    "collect_raid/index": handle_collect_raid_index,
    "transfer/rotation_index": handle_transfer_rotation_index,
    "training_report/index": handle_training_report_index,
    # schema.py serves these the real reply's shape, empty: nothing to add.
    "champions/index": lambda p: _ok({}),
}

# Polls and a concert replay: nothing to change, `WIRE` nothing (or only
# status) in the real reply.
_ACKS = ("champions/poll", "champions_stamp/poll", "collect_raid/polling",
         "collect_raid/get_event_info", "live/live_start")

_NOT_BUILT = (
    "champions/all_race_exec", "champions/entry", "champions/final_lobby",
    "champions/final_race_end", "champions/final_race_start", "champions/final_round_end",
    "champions/lobby", "champions/paddock_index", "champions/race_end", "champions/race_entry",
    "champions/race_start", "champions/round_end", "champions/select_league",
    "champions/set_entry_chara",
    "heroes/final_check_race", "heroes/final_get_race_list", "heroes/final_get_race_replay",
    "heroes/final_get_umaine", "heroes/final_set_umaine", "heroes/stage1_check_hero_skill",
    "heroes/stage1_check_opponent_teams", "heroes/stage1_check_round", "heroes/stage1_edit_team",
    "heroes/stage1_finish_set", "heroes/stage1_get_opponent_teams", "heroes/stage1_grand_result",
    "heroes/stage1_honor_select_chara", "heroes/stage1_honor_select_chara_list",
    "heroes/stage1_start_set",
    "ultimate_race/race_entry", "ultimate_race/race_start", "ultimate_race/reflect_item_effect",
    "ultimate_race/replay_check",
    "collect_raid/receive_individual_reward", "collect_raid/story_clear",
    "factor_research/factor_update",
    "transfer/rotation_detail", "transfer/rotation_exec_multi",
    "schedule_book/start",
    "training_roadmap/get_share_info", "training_roadmap/import_share_for_tutorial",
    "training_roadmap/pre_import_share", "training_roadmap/tutorial_finish",
    "generate_succession/index", "generate_succession/change_support_card_deck",
    "generate_succession/exec", "generate_succession/factor_select",
    "generate_succession/finish", "generate_succession/priority_factor",
    "daily_legend_race_skip/race_skip",
)

HANDLERS = {**_INDEX,
            **{ep: _ack for ep in _ACKS},
            **{ep: _not_built for ep in _NOT_BUILT}}
