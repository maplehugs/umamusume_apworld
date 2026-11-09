"""Archipelago: the room settings (client_config.json), the game server's
connection state (archipelago_status.json) and the played account's progress:
tracker, goal, buffs, traps and boons, sent and received items, hints."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import urllib.request
from pathlib import Path

from app import archipelago, master_data, problems
from app import state as state_store
from app.archipelago import client, tables
from app.handlers import single_mode_team

from . import op
from .career_tuning import _read, _write
from .common import OpError

KEYS = ("archipelago_server", "archipelago_slot", "archipelago_password")
# The release's own plugin, shipped in the server package (server/package.py).
BUNDLED_DLL = Path(__file__).resolve().parents[2] / "plugin" / "umapd_archipelago.dll"
DLLS = ("hachimi_redirect.dll", "umapd_archipelago.dll")
# What Fix downloads when they're missing. Hachimi Edge is pinned (and checked) to the version
# these steps were tested with; it goes in as the game's cri_mana_vpx.dll (source_code_dll/README.md).
HACHIMI_URL = "https://github.com/kairusds/Hachimi-Edge/releases/download/v0.33.1/hachimi.dll"
HACHIMI_SHA256 = "293ebab44bf98798a1ab91188cca5e4ebcc6919863d7d309a9a3de49997efb4a"
REDIRECT_URL = "https://github.com/systemless10/UmamusumePS/releases/download/plugin/hachimi_redirect.dll"
REDIRECT_SHA256 = "a4de623a493f74b9d129903d2a20b15d4b3694a9ff7117c00b0dc3e36ade3a4f"  # if upstream updates it, Fix fails until this is bumped
LOADER = "cri_mana_vpx.dll"


def _status() -> dict:
    try:
        return json.loads(client.status_path().read_text())
    except (OSError, ValueError):
        return {"state": "off", "detail": "the game server isn't running"}


@op("archipelago.get")
def get(viewer, args):
    cfg = _read()
    status = _status()
    out = {
        "settings": {k: cfg.get(k) for k in KEYS},
        "connection": {"state": status.get("state"), "detail": status.get("detail")},
        "room": status.get("room") or {},
        "item_names": sorted(tables.item_name_to_id()),
        "save": None,
    }
    vid = archipelago.target_viewer()
    # No account until the game logs in once: the panel asks for that first.
    out["account"] = bool(vid)
    out["problems"] = problems.recent()
    out["game_address"] = "https://127.0.0.1:" + ("8444" if os.environ.get("UMA_REGION") == "jp" else "8443")
    full_state = state_store.get_state(vid) if vid else None
    if not full_state or archipelago.AP_KEY not in full_state:
        return out
    st = archipelago.ap_state(full_state)
    names = {v: k for k, v in tables.location_name_to_id().items()}
    out["save"] = {
        "viewer": vid,
        "seed": st.get("seed_name"),
        "items_received": st.get("next_index", 0),
        "checks_done": len(st.get("checked") or ()),
        "recent_checks": [names.get(i, str(i)) for i in (st.get("checked") or ())[-8:]][::-1],
        "next_career": [archipelago.item_name(t) for t in st.get("traps") or ()],
        "different_races_won": len(st.get("races_won") or ()),
    }
    out["tracker"] = archipelago.tracker(full_state)
    out["goal"] = archipelago.goal_progress(full_state)
    out["received"] = [{**r, "info": archipelago.item_info(r.get("item", ""))}
                       for r in reversed((st.get("received") or [])[-200:])]
    out["permanent"] = archipelago.permanent_buffs(full_state)
    # Done checks, newest first, with what they held (only checks already done:
    # the rest of the scout list is a spoiler).
    scouted = st.get("scouted") or {}
    out["sent"] = [{"where": names.get(loc, str(loc)), **scouted.get(str(loc), {"item": "?", "to": "", "flags": 0})}
                   for loc in reversed(st.get("checked") or [])][:200]
    for row in out["sent"]:  # another game's item names just match nothing here
        row["info"] = archipelago.item_info(row["item"])
    running = (full_state.get(single_mode_team.STATE_KEY) or {}).get("data") or {}
    out["effects"] = archipelago.effects_report(full_state, running.get("chara_info"))
    out["hints"] = [h for h in st.get("hints") or () if h.get("mine_to_find") or h.get("for_me")]
    return out


@op("archipelago.set")
def set_(viewer, args):
    data = _read()
    for k, v in (args.get("values") or {}).items():
        if k not in KEYS:
            raise OpError(f"Unknown setting {k}.")
        data[k] = str(v).strip() or None
    _write(data)
    return get(viewer, {})


@op("archipelago.say")
def say(viewer, args):
    """A chat line or room command for the game server's connection to send
    (the hint button sends "!hint <item>")."""
    text = str(args.get("text") or "").strip()[:200]
    if not text:
        raise OpError("Nothing to send.")
    if _status().get("state") != "connected":
        raise OpError("Not connected to the Archipelago room.")
    with client.say_path().open("a") as f:
        f.write(text.replace("\n", " ") + "\n")
    return {"ok": True}


# ---- game setup: the Hachimi plugins and the master.mdb the server reads

def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _libraries(cfg: Path) -> list:
    return json.loads(cfg.read_text(encoding="utf-8-sig")).get("load_libraries") or []


def _fetch(url: str, dest: Path, sha: str | None = None) -> None:
    """Download url to dest (all or nothing). With sha the file must match it, else it must at least be a DLL."""
    part = dest.with_name(dest.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, part.open("wb") as f:
            shutil.copyfileobj(r, f)
        if (sha and _sha(part) != sha) or part.read_bytes()[:2] != b"MZ":
            raise OpError(f"The download of {dest.name} is not the expected file: try again, or install it by hand (docs/setup.md).")
        part.replace(dest)
    except OSError as e:
        raise OpError(f"Could not download or save {dest.name} ({e}). Check the internet, that Umamusume is fully closed (Task Manager), and that antivirus isn't blocking it: Windows Defender can delete these mod DLLs, so add the game folder to its exclusions. Then press Fix again: it continues where it stopped.") from e
    finally:
        part.unlink(missing_ok=True)


def _has_hachimi(game: Path) -> bool:
    """Hachimi already sits in the game as its cri_mana_vpx.dll, whatever the version."""
    loader = game / LOADER
    if not loader.is_file():
        return False
    data = loader.read_bytes()
    # the game's own CRI dll is small: only a big file that names itself Hachimi counts
    return hashlib.sha256(data).hexdigest() == HACHIMI_SHA256 or (len(data) > 10_000_000 and b"hachimi" in data.lower())


@op("archipelago.setup")
def setup(viewer, args):
    """Each thing the game needs, ok or not, and whether Fix can sort it out."""
    hachimi = archipelago.hachimi_dir()
    rows, fixable = [], False

    def row(ok, name, detail):
        rows.append({"ok": bool(ok), "name": name, "detail": detail})

    game = hachimi.parent
    can_install = hachimi.name == "hachimi" and (game / LOADER).is_file()  # the game folder is really there
    if hachimi.is_dir():
        row(True, "Hachimi folder", str(hachimi))
    elif can_install:
        row(False, "Hachimi folder", "not there yet: Fix installs Hachimi Edge, then start the game once"
            if not _has_hachimi(game) else "Hachimi is installed: start the game once so it creates the folder")
        fixable |= not _has_hachimi(game)
    else:
        row(False, "Hachimi folder", f"game not found at {game}. Steam > right-click the game > Manage > Browse local files, then run start-global.bat with --game-dir \"that folder\"")
    if hachimi.is_dir() and can_install:
        ok = _has_hachimi(game)
        row(ok, LOADER, "Hachimi" if ok else "the game's own file (a game update or Steam verify restores it): Fix reinstalls Hachimi")
        fixable |= not ok
    redirect = hachimi / DLLS[0]
    row(redirect.is_file(), DLLS[0], "installed" if redirect.is_file()
        else "missing" + (": Fix downloads it" if can_install or hachimi.is_dir() else ""))
    fixable |= not redirect.is_file() and (can_install or hachimi.is_dir())
    plugin = hachimi / DLLS[1]
    if not plugin.is_file():
        row(False, DLLS[1], "missing" + (": Fix installs it" if BUNDLED_DLL.is_file() else ""))
        fixable |= BUNDLED_DLL.is_file()
    elif not BUNDLED_DLL.is_file():
        row(True, DLLS[1], f"installed (sha256 {_sha(plugin)[:12]}...)")
    elif _sha(plugin) == _sha(BUNDLED_DLL):
        row(True, DLLS[1], "installed, the same file as this release")
    else:
        row(False, DLLS[1], "a different version from this release's: Fix replaces it")
        fixable = True
    cfg = hachimi / "config.json"
    try:
        libs = {Path(x.replace("\\", "/")).name.lower() for x in _libraries(cfg)}
        missing = [d for d in DLLS if d not in libs]
        row(not missing, "config.json load_libraries",
            "lists both plugins" if not missing else f"doesn't list {', '.join(missing)}: Fix adds it")
        fixable |= bool(missing)
    except OSError:
        row(False, "config.json", "not found: start the game once with Hachimi so it creates it")
    except ValueError:
        row(False, "config.json", "not valid JSON: fix it by hand or delete it so Hachimi makes a new one")
    mdb = master_data.MASTER_MDB_PATH
    try:
        days = int((time.time() - mdb.stat().st_mtime) // 86400)
        row(days <= 14, "master.mdb", f"{mdb}, updated {days} days ago" + (
            "" if days <= 14 else ": old game data. Start Umamusume once, wait for the title screen, then Check files again"))
    except OSError:
        row(False, "master.mdb", f"{mdb} not found")
    return {"rows": rows, "fixable": fixable and (can_install or hachimi.is_dir())}  # Fix needs the game folder


@op("archipelago.setup_fix")
def setup_fix(viewer, args):
    """Install Hachimi Edge and hachimi_redirect.dll if missing, this release's
    umapd_archipelago.dll, and list the plugins in config.json (backed up once to
    config.json.bak). config.json only exists after the game ran once with Hachimi."""
    hachimi = archipelago.hachimi_dir()
    game = hachimi.parent
    if hachimi.name != "hachimi" or not (game / LOADER).is_file():
        raise OpError(f"The game isn't at {game}: run start-global.bat with --game-dir \"the game's folder\" (Steam > right-click the game > Manage > Browse local files).")
    if not _has_hachimi(game):  # also after a game update or Steam verify put the game's own file back
        orig = game / (LOADER + ".orig")  # the game's own file: how you undo this
        if not orig.exists():
            part = orig.with_name(orig.name + ".part")
            shutil.copyfile(game / LOADER, part)
            part.replace(orig)
        _fetch(HACHIMI_URL, game / LOADER, HACHIMI_SHA256)
    hachimi.mkdir(exist_ok=True)
    if not (hachimi / DLLS[0]).is_file():
        _fetch(REDIRECT_URL, hachimi / DLLS[0], REDIRECT_SHA256)
    plugin = hachimi / DLLS[1]
    if BUNDLED_DLL.is_file() and not (plugin.is_file() and _sha(plugin) == _sha(BUNDLED_DLL)):
        try:
            shutil.copyfile(BUNDLED_DLL, plugin)
        except OSError as e:
            raise OpError(f"Could not copy {DLLS[1]} (close the game first): {e}") from e
    cfg = hachimi / "config.json"
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8-sig"))
        except ValueError as e:
            raise OpError("hachimi/config.json isn't valid JSON: fix it by hand.") from e
        libs = data.setdefault("load_libraries", [])
        have = {Path(x.replace("\\", "/")).name.lower() for x in libs}
        add = [f"hachimi\\{d}" for d in DLLS if d not in have and (hachimi / d).is_file()]
        if add:
            bak = cfg.with_name("config.json.bak")
            if not bak.exists():
                shutil.copyfile(cfg, bak)
            libs += add
            cfg.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    return setup(viewer, args)
