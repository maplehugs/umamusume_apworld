"""The race engine's skill table, built from the CLIENT'S OWN master.mdb.

skill_data.json (vendored from uma-tools) is Cygames' JP table as uma-tools
last scraped it. The server does not serve that client. Diffed against the
Global master.mdb on 2026-09-24:

  * 67 skills trigger on a different condition -- JP later reworked them and
    Global has not caught up (e.g. Special Week's unique, 100031, is
    `is_finalcorner==1&corner==0` on Global; the JSON carried JP's
    `is_last_straight==1` rework with an overtake precondition). Those skills
    fired at the wrong place on the course, or not at all.
  * 28 skills carry a different value or duration (100101 is 4s on Global, 5s
    in the JSON).
  * 20 Global skills were missing entirely (the Global-only event and scenario
    greens), so a horse holding one silently never got it.
  * The JSON has no target count, value/duration scaling type or cooldown at
    all, which every debuff and several unique skills need.

So the table is read from master.mdb -- whichever client install master_data
resolves -- and the JSON is only kept as a fallback for ids master.mdb does not
have (and for running the engine with no game install at all, e.g. in tests).

Both engines read the SAME table: the Python engine in-process, the Rust worker
from the file `ensure_file()` writes (see race_simulator._rs_worker).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import tempfile

from ... import region
from pathlib import Path

log = logging.getLogger("uma-server")

_JSON_PATH = Path(__file__).resolve().parent / "data" / "skill_data.json"
# Written next to the other server runtime data, never committed (see
# .gitignore). Regenerated whenever master.mdb is newer than it.
_CACHE_PATH = Path(os.environ.get("UMA_RACE_SKILL_TABLE")
                   or Path(__file__).resolve().parents[3] / "data" / f"race_skill_table_{region.PROCESS_REGION}.json")

_table: dict | None = None
_lock = threading.Lock()


def _alternative(row, n: int) -> dict | None:
    condition = row[f"condition_{n}"] or ""
    if not condition:
        return None
    effects = []
    for j in (1, 2, 3):
        ability = row[f"ability_type_{n}_{j}"]
        if not ability:
            continue
        effects.append({
            "type": int(ability),
            "modifier": float(row[f"float_ability_value_{n}_{j}"]),
            "target": int(row[f"target_type_{n}_{j}"]),
            "targetValue": int(row[f"target_value_{n}_{j}"]),
            "valueUsage": int(row[f"ability_value_usage_{n}_{j}"]),
            "levelUsage": int(row[f"ability_value_level_usage_{n}_{j}"]),
            # SkillAbilityAdditionalActivateType: 0 none, 1 on each overtake,
            # 2/3 on each other skill activation (see race_solver).
            "additionalActivate": int(row[f"additional_activate_type_{n}_{j}"] or 0),
        })
    return {
        "precondition": row[f"precondition_{n}"] or "",
        "condition": condition,
        "baseDuration": float(row[f"float_ability_time_{n}"]),
        "timeUsage": int(row[f"ability_time_usage_{n}"]),
        "cooldown": float(row[f"float_cooldown_time_{n}"]),
        "effects": effects,
    }


def _from_master() -> dict:
    from ... import master_data
    out = {}
    for row in master_data.query("SELECT * FROM skill_data"):
        alts = [a for a in (_alternative(row, 1), _alternative(row, 2)) if a]
        if not alts:
            continue
        out[str(row["id"])] = {
            "rarity": int(row["rarity"]),
            # activate_lot is the pre-race wisdom roll flag (the JSON's
            # wisdomCheck was copied from this very column upstream).
            "wisdomCheck": int(row["activate_lot"]),
            # skill tags; 601-615 are the passive (green) skills value usage 14
            # counts
            "tags": [int(t) for t in str(row["tag_id"] or "").split("/") if t.strip().isdigit()],
            "alternatives": alts,
        }
    return out


def build_table() -> dict:
    table = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
    try:
        master = _from_master()
    except Exception:
        log.warning("race engine: master.mdb skill_data unavailable, using the "
                    "bundled JP skill table", exc_info=True)
        return table
    table.update(master)
    return table


def skills() -> dict:
    global _table
    if _table is None:
        with _lock:
            if _table is None:
                _table = build_table()
    return _table


def ensure_file() -> Path:
    """Give Rust exactly the in-memory regional table, including fallback entries.

    A timestamp alone cannot identify the master that produced a cache. Global
    and JP share a workspace and can run at the same time.
    """
    table = skills()
    encoded = json.dumps(table, separators=(",", ":"))
    with _lock:
        try:
            fresh = _CACHE_PATH.read_text(encoding="utf-8") == encoded
        except OSError:
            fresh = False
        if not fresh:
            _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=_CACHE_PATH.parent,
                                             prefix=_CACHE_PATH.name + ".", suffix=".tmp", delete=False) as f:
                temporary = Path(f.name)
                f.write(encoded)
            try:
                os.replace(temporary, _CACHE_PATH)
            finally:
                temporary.unlink(missing_ok=True)
    return _CACHE_PATH
