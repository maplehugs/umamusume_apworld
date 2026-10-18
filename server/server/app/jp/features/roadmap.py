"""育成ロードマップ: the selected-character pointer.

`WIRE` umacap api-20261011-014732-344 seq 82/85: selecting
{type, plan_id, position_id} answers it back with auto_call_skill_set_deck_id
101 (GameDefine.TRAINING_ROADMAP_DECK_ID -- the roadmap character's skill
list stands in as a skill-set deck); clearing (identifier null) answers null
and 0.

The roadmap's sheets themselves (update_plan / add_character / ...) are not
built, so training_roadmap/load never lists a character to select and
selected_info stays null -- the skill-set index's real value when nothing is
selected.
"""

from __future__ import annotations

import copy

from ... import state as state_store
from . import skill_set

STATE_KEY = "jp_training_roadmap_selected"


def _ok(data: dict) -> dict:
    return {"response_code": 1, "data_headers": {"result_code": 1, "notifications": {}}, "data": data}


def selected(full_state: dict):
    return copy.deepcopy(full_state.get(STATE_KEY))


def selected_info(full_state: dict):
    """TrainingRoadmapSelectedInfo {selected_character_identifier, character,
    succession_character, compare_source_array}; needs the stored sheet, which
    this server does not keep yet."""
    return None


def handle_update_selected_character(payload: dict) -> dict:
    ident = payload.get("identifier")
    if ident is not None:
        try:
            ident = {"type": int(ident["type"]), "plan_id": int(ident["plan_id"]),
                     "position_id": int(ident["position_id"])}
        except (KeyError, TypeError, ValueError):
            from ...result_codes import refuse
            return refuse()
    full_state = state_store.get_state(payload["viewer_id"]) or {}
    full_state[STATE_KEY] = ident
    blob = skill_set.info(full_state)
    deck = skill_set.TRAINING_ROADMAP_DECK_ID if ident else 0
    # Selecting points auto-call at the roadmap deck; clearing drops it to 0.
    if ident or blob.get("auto_call_skill_set_deck_id") == skill_set.TRAINING_ROADMAP_DECK_ID:
        blob["auto_call_skill_set_deck_id"] = deck
    state_store.save_state(payload["viewer_id"], full_state)
    return _ok({"selected_character_identifier": copy.deepcopy(ident),
                "auto_call_skill_set_deck_id": deck})


HANDLERS = {
    "training_roadmap/update_selected_character": handle_update_selected_character,
}
