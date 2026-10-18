"""Game icons (VivloToolkit's icon cache, same sources and layout).

    item/<item_id>        item_icon_00032.png
    chara/<chara_id>      chr_icon_1001.png
    card/<card_id>        the trained (outfit) icon of an uma card
    support/<card_id>     support_card_s_30028.png
    supportart/<card_id>  tex_support_card_30028.png (full 3:4 card art)
    skill/<icon_id>       utx_ico_skill_10011.png (local only)

Local first: uma-tools' extracted icon set (UMA_TOOLS_ICONS, default
~/Documents/Projects/uma-tools-master/icons), then VivloToolkit's own cache if
it is installed next door, then GameTora's image mirror -- fetched once and
cached under admin_panel/cache/icons/. A miss is remembered too.
"""

from __future__ import annotations

import functools
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "cache" / "icons"
VIVLO_CACHE = Path.home() / "Documents/VivloBot/cache/icons"
LOCAL = Path(os.environ.get("UMA_TOOLS_ICONS", Path.home() / "Documents/Projects/uma-tools-master/icons"))
REMOTE = "https://gametora.com/images/umamusume/"
KINDS = ("item", "chara", "card", "support", "supportart", "skill")
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


@functools.lru_cache(maxsize=1)
def _card_icons() -> dict:
    try:
        return json.loads((LOCAL.parent / "icons.json").read_text())
    except (OSError, ValueError):
        return {}


def _sources(kind: str, ident: int) -> list:
    if kind == "item":
        return [f"{REMOTE}items/item_icon_{ident:05d}.png"]
    if kind == "chara":
        return [LOCAL / "chara" / f"chr_icon_{ident}.png", f"{REMOTE}characters/icons/chr_icon_{ident}.png"]
    if kind == "card":
        names = _card_icons().get(str(ident))
        local = [LOCAL / "chara" / f"{names[0]}.png"] if isinstance(names, list) and names else []
        return local + [f"{REMOTE}characters/icons/chr_icon_{ident // 100}_{ident}_01.png"] + _sources("chara", ident // 100)
    if kind == "skill":
        return [LOCAL / "skill" / f"utx_ico_skill_{ident}.png", f"{REMOTE}skill_icons/utx_ico_skill_{ident}.png"]
    if kind == "support":
        return [LOCAL / "support" / f"support_card_s_{ident}.png", f"{REMOTE}supports/support_card_s_{ident}.png"]
    if kind == "supportart":
        return [f"{REMOTE}supports/tex_support_card_{ident}.png"] + _sources("support", ident)
    return []


def _fetch(url: str) -> bytes | None | bool:
    """The PNG, None when the source definitely has no icon, or False when the
    fetch failed for a reason worth retrying later (offline, timeout, 5xx)."""
    req = urllib.request.Request(url, headers={"User-Agent": "UmaPS Admin Panel (personal icon cache)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
            return body if body[:4] == b"\x89PNG" else None
    except urllib.error.HTTPError as e:
        return None if e.code in (403, 404, 410) else False
    except Exception:  # noqa: BLE001 - offline / timeout: try again next time
        return False


def get(kind: str, ident: int) -> bytes | None:
    if kind not in KINDS:
        return None
    cached = CACHE / kind / f"{ident}.png"
    if cached.is_file():
        return cached.read_bytes()
    theirs = VIVLO_CACHE / kind / f"{ident}.png"
    if theirs.is_file():
        return theirs.read_bytes()
    miss = cached.with_suffix(".miss")
    if miss.exists():
        return None
    with _guard:
        lock = _locks.setdefault(f"{kind}/{ident}", threading.Lock())
    with lock:
        if cached.is_file():
            return cached.read_bytes()
        transient = False
        for src in _sources(kind, ident):
            if isinstance(src, Path):
                if src.is_file():
                    return src.read_bytes()
                continue
            body = _fetch(src)
            if body:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(body)
                return body
            transient |= body is False
        if not transient:      # remember only a definite miss
            miss.parent.mkdir(parents=True, exist_ok=True)
            miss.touch()
        return None
