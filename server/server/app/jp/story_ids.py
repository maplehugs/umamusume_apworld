"""JP puts the FULL story id on the wire, never the short one.

The shared pipeline serves single_mode_story_data.short_story_id when a row has
one (event_engine.wire_story_id): that is what the Global server sends. The JP
server does not. Across every JP capture (umacap DYI / Beyond Dreams / Venus /
URA and the headless DYI careers), all 1,261 served stories that have a short
id went out under their `story_id`; not one short id was served.

This rewrites the reply's events on the way out, so every producer (the
engine, the hardcoded URA and goal-scene short ids) gets the JP form. State
keeps whatever the pipeline stored; only the wire changes.
"""

from __future__ import annotations

import functools

from .. import master_data


@functools.lru_cache(maxsize=8192)
def full_story_id(story_id: int) -> int:
    """The story_id whose short copy is `story_id`; `story_id` itself when it
    is not a short id (a full id, or a row with no short copy)."""
    if master_data.query_one("SELECT 1 FROM single_mode_story_data WHERE story_id=?",
                             (story_id,)):
        return story_id
    row = master_data.query_one(
        "SELECT story_id FROM single_mode_story_data WHERE short_story_id=? ORDER BY id",
        (story_id,))
    return int(row["story_id"]) if row else story_id


def _fix(events) -> None:
    for ev in events or ():
        if not isinstance(ev, dict):
            continue
        try:
            sid = int(ev.get("story_id") or 0)
        except (TypeError, ValueError):
            continue
        if sid > 0:
            ev["story_id"] = full_story_id(sid)


def apply(resp: dict) -> None:
    """Every unchecked_event_array in the reply (top level and the
    *_load_common / *_common blocks) to full story ids."""
    def walk(node, depth=0):
        if depth > 3 or not isinstance(node, dict):
            return
        for key, val in node.items():
            if key == "unchecked_event_array" and isinstance(val, list):
                _fix(val)
            elif isinstance(val, dict):
                walk(val, depth + 1)
    walk(resp.get("data"))
