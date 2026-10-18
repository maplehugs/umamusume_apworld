"""Undo history for every save edit the panel makes.

install() wraps state.save_state / state.delete_state in this worker process.
Before a write reaches the disk, the wrapper reads what each touched key holds
right now and keeps the FIRST such text per key for the op in progress. When
the op ends, commit() stores one history row per viewer: the op's label plus
{key: text before the op (None = the key did not exist)}.

Undo writes those texts back through save_state, so an undo is itself a
history row (undoing it is a redo). Everything is per region:
server/data[/jp]/admin_history.sqlite3, next to the saves it describes.

Only the save store is covered. accounts.sqlite3 edits (password reset,
account deletion) are not.
"""

from __future__ import annotations

import json
import sqlite3
import time

from app import region
from app import state as S

KEEP_ROWS = 2000                    # oldest rows beyond this are pruned

_orig_save = S.save_state
_orig_delete = S.delete_state
_pending: dict[str, dict] = {}      # viewer -> {key: old text | None}
_new_viewers: set[str] = set()      # viewers that had no save before this op
_reader: sqlite3.Connection | None = None
_hist: sqlite3.Connection | None = None


def _state_db() -> sqlite3.Connection:
    global _reader
    if _reader is None:
        S.get_state("__admin_probe__")          # make sure the schema exists
        _reader = sqlite3.connect(region.data_dir() / "state.sqlite3", check_same_thread=False)
    return _reader


def _db() -> sqlite3.Connection:
    global _hist
    if _hist is None:
        _hist = sqlite3.connect(region.data_dir() / "admin_history.sqlite3", check_same_thread=False)
        _hist.execute("""CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, viewer_id TEXT NOT NULL,
            label TEXT NOT NULL, keys TEXT NOT NULL, old TEXT NOT NULL, new_viewer INTEGER NOT NULL DEFAULT 0,
            undone_by INTEGER)""")
        _hist.execute("CREATE INDEX IF NOT EXISTS history_viewer ON history(viewer_id, id)")
        _hist.commit()
    return _hist


def _old_text(conn, vid, key):
    row = conn.execute("SELECT value FROM viewer_state_kv WHERE viewer_id=? AND key=?", (vid, key)).fetchone()
    return row[0] if row else None


def _tracked_save(viewer_id, state):
    vid = str(viewer_id)
    conn = _state_db()
    rec = _pending.setdefault(vid, {})
    present = conn.execute("SELECT 1 FROM viewer_state_present WHERE viewer_id=?", (vid,)).fetchone()
    if not present and vid not in rec:
        _new_viewers.add(vid)
    texts = {k: json.dumps(v) for k, v in dict.items(state)}
    for k, t in texts.items():
        if k in rec:
            continue
        old = _old_text(conn, vid, k)
        if old != t:
            rec[k] = old
    stored = {k for (k,) in conn.execute("SELECT key FROM viewer_state_kv WHERE viewer_id=?", (vid,))}
    gone = S._deleted_keys(state, stored, texts)
    for k in gone:
        if k not in rec:
            rec[k] = _old_text(conn, vid, k)
    return _orig_save(viewer_id, state)


def _tracked_delete(viewer_id):
    vid = str(viewer_id)
    rec = _pending.setdefault(vid, {})
    for k, v in _state_db().execute("SELECT key, value FROM viewer_state_kv WHERE viewer_id=?", (vid,)):
        rec.setdefault(k, v)
    return _orig_delete(viewer_id)


def install() -> None:
    S.save_state = _tracked_save
    S.delete_state = _tracked_delete


def begin() -> None:
    _pending.clear()
    _new_viewers.clear()
    # state.py diffs saves against texts it remembers from earlier reads. This
    # worker lives for hours while the game server writes the same rows, so a
    # remembered text can be stale -- and a save whose value happens to equal
    # it (an undo restoring an older value) would be skipped. Start every op
    # cold, like a one-shot admin.py run.
    S.clear_cache()


def commit(label: str) -> list[int]:
    """Store the finished op's changes; returns the new history ids."""
    ids = []
    db = _db()
    for vid, rec in _pending.items():
        rec = {k: v for k, v in rec.items() if not (v is None and _old_text(_state_db(), vid, k) is None)}
        if not rec:
            continue
        cur = db.execute(
            "INSERT INTO history (ts, viewer_id, label, keys, old, new_viewer) VALUES (?,?,?,?,?,?)",
            (time.time(), vid, label, json.dumps(sorted(rec)), json.dumps(rec), int(vid in _new_viewers)))
        ids.append(cur.lastrowid)
    if ids:
        db.execute("DELETE FROM history WHERE id <= (SELECT MAX(id) FROM history) - ?", (KEEP_ROWS,))
        db.commit()
    begin()
    return ids


def rows(viewer: str | None, limit: int = 200) -> list[dict]:
    q = "SELECT id, ts, viewer_id, label, keys, new_viewer, undone_by, length(old) FROM history"
    params: tuple = ()
    if viewer:
        q += " WHERE viewer_id=?"
        params = (viewer,)
    q += " ORDER BY id DESC LIMIT ?"
    out = []
    for r in _db().execute(q, (*params, limit)):
        out.append({"id": r[0], "ts": r[1], "viewer": r[2], "label": r[3], "keys": json.loads(r[4]),
                    "new_viewer": bool(r[5]), "undone_by": r[6], "size": r[7]})
    return out


def entry(entry_id: int) -> dict | None:
    r = _db().execute("SELECT id, viewer_id, label, keys, old, new_viewer FROM history WHERE id=?",
                      (entry_id,)).fetchone()
    if not r:
        return None
    return {"id": r[0], "viewer": r[1], "label": r[2], "keys": json.loads(r[3]),
            "old": json.loads(r[4]), "new_viewer": bool(r[5])}


def later_overlaps(entry_id: int) -> list[dict]:
    """Later changes to the same viewer that touched any of the same keys --
    undoing this entry also throws those away for the shared keys."""
    e = entry(entry_id)
    if not e:
        return []
    keys = set(e["keys"])
    out = []
    for r in _db().execute("SELECT id, label, keys FROM history WHERE viewer_id=? AND id>? ORDER BY id",
                           (e["viewer"], entry_id)):
        shared = keys & set(json.loads(r[2]))
        if shared:
            out.append({"id": r[0], "label": r[1], "keys": sorted(shared)})
    return out


def mark_undone(entry_id: int, by: int) -> None:
    _db().execute("UPDATE history SET undone_by=? WHERE id=?", (by, entry_id))
    _db().commit()
