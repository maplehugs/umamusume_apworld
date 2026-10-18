"""Helpers shared by the worker ops: master text, save load/save, arg parsing."""

from __future__ import annotations

import functools
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime

from app import master_data as M
from app import region
from app import state as state_store

# Each region's own default account (same as admin.py / career.py).
DEFAULT_VIEWERS = {"global": "900000000001", "jp": "900000000002"}
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

STATS = ("speed", "stamina", "power", "guts", "wiz")
APTITUDES = (
    "proper_ground_turf", "proper_ground_dirt",
    "proper_distance_short", "proper_distance_mile", "proper_distance_middle", "proper_distance_long",
    "proper_running_style_nige", "proper_running_style_senko",
    "proper_running_style_sashi", "proper_running_style_oikomi",
)


class OpError(Exception):
    """A refusal the panel shows as-is (bad input, nothing to edit, ...)."""


def region_name() -> str:
    return region.PROCESS_REGION


def now_str() -> str:
    return datetime.now().strftime(TIME_FORMAT)


_prefer_english = True


def set_prefer_english(enabled: bool) -> None:
    global _prefer_english
    if enabled == _prefer_english:
        return
    _prefer_english = enabled
    # The workers serialize requests. Clear display catalogues when a browser
    # requests another language; the game's master connection stays untouched.
    from . import catalog
    for value in vars(catalog).values():
        if callable(getattr(value, "cache_clear", None)):
            value.cache_clear()
    for module_name, cache_name in (("misc", "_songs"), ("umas", "awakening_skills")):
        module = sys.modules.get(f"admin_panel.ops.{module_name}")
        if module is not None:
            getattr(module, cache_name).cache_clear()


@functools.lru_cache(maxsize=1)
def english_connection():
    candidates = [os.environ.get("UMA_EN_TEXT_MDB"), *M._EN_TEXT_CANDIDATES,
                  Path(__file__).resolve().parents[2] / "master.mdb"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            conn = sqlite3.connect(Path(candidate).resolve().as_uri() + "?mode=ro", uri=True)
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='text_data'").fetchone():
                return conn
            conn.close()
    return None


@M.context_cache(maxsize=None)
def _texts(category: int, prefer_english: bool) -> dict:
    # Bypass the server's always-English matching view for native labels.
    out = {int(r[0]): r[1] for r in M.query(
        "SELECT [index], text FROM main.text_data WHERE category=?", (category,))}
    if prefer_english and region_name() == "jp":
        conn = english_connection()
        if conn is not None:
            for index, label in conn.execute(
                    "SELECT [index], text FROM text_data WHERE category=?", (category,)):
                if int(index) in out and label and label.strip():
                    out[int(index)] = label
    return out


def texts(category: int) -> dict:
    return _texts(category, _prefer_english)


def text(category: int, index, default: str = "") -> str:
    if index is None:
        return default
    try:
        return texts(category).get(int(index), default)
    except (TypeError, ValueError):
        return default


def load(viewer) -> dict:
    full_state = state_store.get_state(viewer)
    if full_state is None:
        raise OpError(f"No save for viewer {viewer} on {region_name()}.")
    return full_state


def save(viewer, full_state) -> None:
    state_store.save_state(viewer, full_state)


def int_arg(args: dict, key: str, default=None, lo=None, hi=None):
    value = args.get(key, default)
    if value is None or value == "":
        if default is None:
            raise OpError(f"Missing {key}.")
        value = default
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise OpError(f"{key} must be a whole number.") from None
    if lo is not None and value < lo:
        raise OpError(f"{key} must be at least {lo}.")
    if hi is not None and value > hi:
        raise OpError(f"{key} must be at most {hi}.")
    return value


def opt_int(args: dict, key: str, lo=None, hi=None):
    """An optional whole number: None when absent/blank."""
    if args.get(key) in (None, ""):
        return None
    return int_arg(args, key, lo=lo, hi=hi)


def ids_arg(args: dict, key: str = "ids") -> list[int]:
    raw = args.get(key) or []
    try:
        return [int(x) for x in raw]
    except (TypeError, ValueError):
        raise OpError(f"{key} must be a list of ids.") from None


def find(entries: list, field: str, value):
    return next((e for e in entries if isinstance(e, dict) and e.get(field) == value), None)


def item_count(full_state: dict, item_id: int) -> int:
    it = find(full_state.get("item_list_state") or [], "item_id", item_id)
    return int(it.get("number") or 0) if it else 0


def set_item(full_state: dict, item_id: int, number: int) -> None:
    """Set an item's count; 0 removes the row (what the server's own spend
    paths leave behind is a 0 row, which the client also accepts)."""
    items = full_state.setdefault("item_list_state", [])
    it = find(items, "item_id", item_id)
    if number <= 0:
        if it:
            items.remove(it)
        return
    if it:
        it["number"] = number
    else:
        items.append({"item_id": item_id, "number": number})


def chara_name(chara_id) -> str:
    return text(6, chara_id) or text(170, chara_id) or f"Chara {chara_id}"


def card_name(card_id) -> str:
    return text(4, card_id) or f"Card {card_id}"


def skill_name(skill_id) -> str:
    return text(47, skill_id) or f"Skill {skill_id}"
