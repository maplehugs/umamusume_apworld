"""
Persistent per-viewer game state, backed by SQLite.

Storage is one row per TOP-LEVEL KEY of the viewer's state dict
(viewer_state_kv), not one JSON blob per viewer. The public API is unchanged
-- get_state still hands back a plain dict and save_state still takes one --
so no caller had to change; only what hits the disk did.

Why: the original design stored the whole dict as one blob and rewrote all of
it on every save. The largest real viewer is ~3.5 MB, of which ~90% is the
`load_index` cache, and a typical request mutates one small key. Every
mutation therefore rewrote ~3.5 MB (plus WAL) to change a few hundred bytes.
That is tolerable against a local SQLite file the page cache absorbs, and is
exactly the shape that gets expensive against a networked store, where the
same write becomes a full TOAST rewrite plus a round trip. save_state now
re-writes only the keys whose serialized form actually changed (measured on
the largest real viewer: 3,501,313 bytes -> 15).

LAZY KEYS (_LAZY_KEYS) go one step further. Splitting the rows removed the
redundant WRITES but not the redundant PARSING: get_state still had to
json.loads every key and save_state still had to json.dumps every key to
diff it -- ~92 ms per request on the largest viewer, ~90% of that
`load_index`, a blob almost every endpoint carries around and never looks
at. A lazy key is not read by get_state at all. get_state returns a
LazyState, a dict that fetches and parses a lazy key the first time a caller
touches it (`[]`, .get, .setdefault, .pop, iteration); from then on it saves
and diffs exactly like any other key. `in` answers from the key list without
parsing anything. So callers are unchanged and their mutations still persist,
while the requests that never look at a big key never pay for it.

The same applies to the legacy roster (1.6 MB on the largest account) and the
other multi-hundred-KB keys: a career turn calls get_state 5-7 times (the
post-response pipeline in single_mode_team re-reads state per step) and
touches none of them, so each of those calls used to parse and re-dump the
whole roster for nothing -- measured at ~100 ms of a ~120 ms check_event.

The one asymmetry this forces: save_state must never DELETE a lazy key just
because it is absent from the dict, since absent means "never loaded" far
more often than it means "removed". An explicit delete through a LazyState
(del / pop) is recorded and does reach the disk.

The old single-blob `viewer_state` table is migrated on first connect and
then left in place, untouched, as a rollback point -- nothing reads it after
the migration.

IN MEMORY. The whole database's stored text (~25 MB across every account) is
held in _text_cache once each viewer is first read, so get_state does no SQL
for a cached viewer, and EVERY key is lazy: a LazyState parses a key only
when a caller touches it. Lazy-loading the big keys still left ~65 eager keys
(~0.9 MB) parsed on every get_state -- a ~14 ms floor under even trivial
endpoints, several times over on a career turn -- although a request
typically touches a handful of them. Each request still gets freshly parsed
objects, never shared ones, so a handler that mutates state and then fails
cannot leak that mutation into the next request.

Keys outside _LAZY_KEYS are parsed from the snapshot taken at get_state time
(what an eager read would have seen); _LAZY_KEYS keep their read-on-touch
semantics, which load.py's _reload_state relies on. A LazyState records
every explicit delete in _dropped, so save_state deletes exactly those keys
and nothing that was merely never touched (_deleted_keys).

Writes are still write-through: save_state commits each changed row before
it returns, so nothing lives only in memory and stopping the server (close(),
run from the lifespan on Ctrl-C) loses nothing. That is also what lets the
admin panel worker, admin.py and tools/ keep writing the database directly:
PRAGMA data_version changes whenever another connection commits, and the
next state call drops this region's cache (_sync_external_writes), so their
edits are visible on the very next request.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from . import region


_lock = Lock()

# Keys a LazyState reads at first touch (the current stored value) rather than
# from its get_state snapshot, and that a plain dict cannot delete by omission.
# See the module docstring. Originally the keys get_state skipped parsing, which
# every key now is; these were the ones large on real accounts and off the
# career-turn path:
# load_index (3.1 MB), legacy_roster (1.6 MB), team_stadium_state (1.2 MB),
# gacha_history / present_box_state (~230 KB on JP), and the one-time roster
# backup legacy_roster_pre_house (as big as the roster it copied, never read
# in normal play).
_LAZY_KEYS = frozenset({
    "load_index", "legacy_roster", "legacy_roster_pre_house",
    "team_stadium_state", "gacha_history", "present_box_state",
    "event_gallery", "directory_hidden_chara",
})

# Every stored row of every viewer read so far, keyed "<region>:<viewer_id>" ->
# {state_key: value_json}: always the COMPLETE set of that viewer's rows,
# exactly as on disk. get_state serves from it and save_state diffs against it
# to decide which rows to write. Unbounded on purpose -- the whole database is
# ~25 MB of text. See "IN MEMORY" in the module docstring.
_text_cache: dict[str, dict[str, str]] = {}

# region -> the PRAGMA data_version last seen on that region's connection.
_data_versions: dict[str, int] = {}

# One connection per region, created on first use. See _connect.
_conns: dict[str, sqlite3.Connection] = {}


def _db_path() -> Path:
    """This region's own database -- see region.data_dir()."""
    return region.data_dir() / "state.sqlite3"


def _cache_key(viewer_id) -> str:
    return f"{region.CURRENT_REGION.get()}:{viewer_id}"


@contextmanager
def _connect():
    """One long-lived connection per region, reused across requests.

    Every public function here holds the module-level _lock for the whole of
    its database work, so a single shared connection is safe despite
    check_same_thread=False. Reusing it matters: opening a connection, setting
    its pragmas and re-checking the schema cost ~2.5 ms, which dwarfed the
    actual query for the many small accounts (most viewers are a few hundred
    bytes) and made them slower than the original blob design.
    """
    key = region.CURRENT_REGION.get()
    conn = _conns.get(key)
    if conn is None:
        conn = sqlite3.connect(_db_path(), check_same_thread=False)
        # Under WAL this can only lose the last transactions on an OS/power
        # crash, never corrupt the database -- the right trade for a game
        # server whose state is re-derivable, and worth roughly an order of
        # magnitude on small writes.
        conn.execute("PRAGMA synchronous=NORMAL")
        _init_schema(conn)
        _conns[key] = conn
    with conn:
        yield conn


def _init_schema(conn: sqlite3.Connection) -> None:
    # WAL lets a reader run concurrently with the writer instead of blocking on
    # it. It persists in the file header, so this once-per-process call is
    # enough -- see _connect for why it is not set per connection.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS viewer_state_kv (
            viewer_id TEXT NOT NULL,
            key       TEXT NOT NULL,
            value     TEXT NOT NULL,
            PRIMARY KEY (viewer_id, key)
        )
        """
    )
    # A viewer whose state is an EMPTY dict has no kv rows at all, which would
    # otherwise be indistinguishable from a viewer that has never been seen --
    # get_state would return None instead of {}, and the account would vanish
    # from all_viewer_ids(). Three such viewers exist in the real data. This
    # table is the explicit "this viewer has state" record that the row count
    # can no longer imply.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS viewer_state_present (viewer_id TEXT PRIMARY KEY)"
    )
    _migrate_blob_table(conn)


def _migrate_blob_table(conn: sqlite3.Connection) -> None:
    """Split any rows still in the legacy single-blob `viewer_state` table into
    per-key rows. Idempotent: a viewer already recorded in viewer_state_present
    is skipped, so a half-finished run resumes cleanly.

    The legacy table is READ ONLY here and deliberately not dropped -- it stays
    as an on-disk rollback point.
    """
    legacy = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='viewer_state'"
    ).fetchone()
    if not legacy:
        return
    done = {r[0] for r in conn.execute("SELECT viewer_id FROM viewer_state_present")}
    with conn:
        for viewer_id, blob in conn.execute("SELECT viewer_id, blob FROM viewer_state"):
            if viewer_id in done:
                continue
            try:
                state = json.loads(blob)
            except (TypeError, ValueError):
                continue
            if not isinstance(state, dict):
                continue
            conn.executemany(
                "INSERT OR REPLACE INTO viewer_state_kv (viewer_id, key, value)"
                " VALUES (?,?,?)",
                [(viewer_id, k, json.dumps(v)) for k, v in state.items()],
            )
            conn.execute(
                "INSERT OR IGNORE INTO viewer_state_present (viewer_id) VALUES (?)",
                (viewer_id,),
            )


def _sync_external_writes(conn: sqlite3.Connection) -> None:
    """Drop this region's cache if another connection -- the admin panel
    worker, admin.py, a tools/ script -- has committed since we last looked.
    data_version does not move for this connection's own commits, so the
    server's own saves never invalidate anything. Call with _lock held."""
    reg = region.CURRENT_REGION.get()
    version = conn.execute("PRAGMA data_version").fetchone()[0]
    seen = _data_versions.get(reg)
    if seen == version:
        return
    _data_versions[reg] = version
    if seen is not None:
        prefix = f"{reg}:"
        for ck in [ck for ck in _text_cache if ck.startswith(prefix)]:
            del _text_cache[ck]


def _cached_rows(conn: sqlite3.Connection, viewer_id) -> dict[str, str]:
    """The viewer's complete {key: text} rows, read from disk on a cache miss.
    Call with _lock held, after _sync_external_writes."""
    ck = _cache_key(viewer_id)
    texts = _text_cache.get(ck)
    if texts is None:
        texts = dict(conn.execute(
            "SELECT key, value FROM viewer_state_kv WHERE viewer_id = ?",
            (str(viewer_id),)))
        _text_cache[ck] = texts
    return texts


def clear_cache() -> None:
    """Forget everything held in memory; the next read goes to disk."""
    with _lock:
        _text_cache.clear()
        _data_versions.clear()


def close() -> None:
    """Fold the WAL back into the database file and close every connection.
    Run on shutdown (admin_lifecycle's lifespan). Every save is already
    committed, so this is tidiness, not durability: it leaves one
    self-contained state.sqlite3 with no -wal/-shm beside it."""
    with _lock:
        for conn in _conns.values():
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                conn.close()
        _conns.clear()
        _text_cache.clear()
        _data_versions.clear()


class LazyState(dict):
    """What get_state returns: a dict whose keys are parsed on first touch
    instead of up front. See the module docstring.

    Only the parsed keys live in the underlying dict; `_pending` holds the
    keys that exist on disk but have not been read yet, and `_snap` the stored
    text of the non-_LAZY_KEYS ones as of get_state. Every dict entry point
    that can observe a key goes through _load first, and anything that walks
    the whole mapping (iteration, items, ==, copy, json.dumps, deepcopy) loads
    everything, so a caller can never see a lazy key as missing -- which
    matters: _get_or_seed_roster reads a missing roster as a brand-new account
    and would re-seed it. save_state reads the loaded keys only, via
    dict.items, so saving never forces a load either."""

    __slots__ = ("_vid", "_region", "_pending", "_snap", "_dropped")

    def __init__(self, viewer_id, snapshot: dict[str, str]) -> None:
        dict.__init__(self)
        self._vid = viewer_id
        self._region = region.CURRENT_REGION.get()
        self._pending = set(snapshot)
        self._snap = {k: t for k, t in snapshot.items() if k not in _LAZY_KEYS}
        # Keys the caller deleted: absent normally means "not loaded", so
        # save_state needs to be told these are real deletes.
        self._dropped = set()

    def _load(self, key) -> None:
        if key in self._pending:
            self._pending.discard(key)
            text = self._snap.pop(key, None)
            if text is not None:
                dict.__setitem__(self, key, json.loads(text))
                return
            token = region.CURRENT_REGION.set(self._region)
            try:
                value = load_lazy_key(self._vid, key)
            finally:
                region.CURRENT_REGION.reset(token)
            if value is not None:
                dict.__setitem__(self, key, value)

    def _load_all(self) -> None:
        for key in list(self._pending):
            self._load(key)

    def __getitem__(self, key):
        self._load(key)
        return dict.__getitem__(self, key)

    def get(self, key, default=None):
        self._load(key)
        return dict.get(self, key, default)

    def setdefault(self, key, default=None):
        self._load(key)
        self._dropped.discard(key)
        return dict.setdefault(self, key, default)

    def __contains__(self, key) -> bool:
        return dict.__contains__(self, key) or key in self._pending

    def __setitem__(self, key, value) -> None:
        self._pending.discard(key)
        self._dropped.discard(key)
        dict.__setitem__(self, key, value)

    def update(self, *args, **kwargs) -> None:
        other = dict(*args, **kwargs)
        self._pending.difference_update(other)
        self._dropped.difference_update(other)
        dict.update(self, other)

    def __delitem__(self, key) -> None:
        self._load(key)
        dict.__delitem__(self, key)
        self._dropped.add(key)

    def pop(self, key, *default):
        self._load(key)
        if dict.__contains__(self, key):
            self._dropped.add(key)
        return dict.pop(self, key, *default)

    def popitem(self):
        self._load_all()
        key, value = dict.popitem(self)
        self._dropped.add(key)
        return key, value

    def clear(self) -> None:
        self._dropped |= set(dict.keys(self)) | self._pending
        self._pending.clear()
        self._snap.clear()
        dict.clear(self)

    def __len__(self) -> int:
        return dict.__len__(self) + len(self._pending)

    def __iter__(self):
        self._load_all()
        return dict.__iter__(self)

    def keys(self):
        self._load_all()
        return dict.keys(self)

    def values(self):
        self._load_all()
        return dict.values(self)

    def items(self):
        self._load_all()
        return dict.items(self)

    def __eq__(self, other):
        self._load_all()
        if isinstance(other, LazyState):
            other._load_all()
        return dict.__eq__(self, other)

    def __ne__(self, other):
        eq = self.__eq__(other)
        return eq if eq is NotImplemented else not eq

    __hash__ = None

    def copy(self) -> dict:
        self._load_all()
        return dict(dict.items(self))

    def __reduce_ex__(self, protocol):
        # copy/deepcopy/pickle get a plain, fully loaded dict.
        return (dict, (self.copy(),))


def get_state(viewer_id: str) -> dict | None:
    """The viewer's state as a dict, served from memory and parsed key by key
    on first touch (see LazyState). None (not {}) when the viewer has no
    persisted state at all, which is the distinction callers' `or {}` idiom
    relies on."""
    vid = str(viewer_id)
    with _lock, _connect() as conn:
        _sync_external_writes(conn)
        # Only viewers with state are ever cached, so a hit implies present.
        if _cache_key(viewer_id) not in _text_cache:
            present = conn.execute(
                "SELECT 1 FROM viewer_state_present WHERE viewer_id = ?", (vid,)
            ).fetchone()
            if not present:
                return None
        # A copy: save_state updates the cached dict in place, and this
        # state's untouched keys must keep reading what get_state saw.
        snapshot = dict(_cached_rows(conn, viewer_id))
    return LazyState(viewer_id, snapshot)


def load_lazy_key(viewer_id: str, key: str):
    """Materialize one key on demand -- the current stored value, not a
    get_state snapshot. Returns None when the viewer has no stored value
    for it."""
    vid = str(viewer_id)
    with _lock, _connect() as conn:
        _sync_external_writes(conn)
        cached = _text_cache.get(_cache_key(viewer_id))
        if cached is not None:
            text = cached.get(key)
        else:
            row = conn.execute(
                "SELECT value FROM viewer_state_kv WHERE viewer_id = ? AND key = ?",
                (vid, key),
            ).fetchone()
            text = row[0] if row else None
    return None if text is None else json.loads(text)


def all_states_for_key(key: str, viewer_ids=None) -> dict:
    """{viewer_id: value} for ONE state key across every viewer, in a single
    query.

    The per-key row layout is what makes this cheap, and it is the right shape
    for any feature that needs one field from every account (team_stadium
    matchmaking scanning for opponents, say). Doing it with get_state per
    viewer means parsing all 200 accounts' entire state to reach one field:
    measured at 180 ms, against ~25 ms here for an identical result.

    Naming the key explicitly means lazy keys are readable through this too --
    there is no ambiguity about what is being loaded. Pass viewer_ids to
    restrict the scan to specific accounts.
    """
    with _lock, _connect() as conn:
        if viewer_ids is None:
            rows = conn.execute(
                "SELECT viewer_id, value FROM viewer_state_kv WHERE key = ?", (key,)
            ).fetchall()
        else:
            # Chunked to stay under SQLite's bound-variable limit (999 by
            # default on older builds) no matter how many accounts are asked
            # for at once.
            ids = [str(v) for v in viewer_ids]
            rows = []
            for i in range(0, len(ids), 400):
                chunk = ids[i:i + 400]
                rows += conn.execute(
                    "SELECT viewer_id, value FROM viewer_state_kv WHERE key = ?"
                    " AND viewer_id IN (%s)" % ",".join("?" * len(chunk)),
                    (key, *chunk),
                ).fetchall()
    return {vid: json.loads(v) for vid, v in rows}


def extract_json_path(viewer_id: str, key: str, path: str):
    """One value from deep inside a stored key, extracted by SQLite rather than
    parsed in Python.

    For a caller that needs a single field out of a large value -- jukebox's
    request-id fallback reads one small object out of the 3.1 MB load_index
    blob -- parsing the whole thing to reach it costs ~50 ms and builds
    hundreds of thousands of throwaway Python objects. json_extract does the
    walk inside SQLite and returns just that subtree: ~13 ms, same value.

    `path` is a SQLite JSON path, e.g. "$.data.music_list". Returns None when
    the key or the path is absent -- callers that need seed-if-missing
    behaviour must fall back to their own accessor, since this deliberately
    never writes.
    """
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT json_extract(value, ?) FROM viewer_state_kv"
            " WHERE viewer_id = ? AND key = ?",
            (path, str(viewer_id), key),
        ).fetchone()
    if row is None or row[0] is None:
        return None
    raw = row[0]
    if not isinstance(raw, str):
        return raw          # json_extract returns scalars natively typed
    try:
        return json.loads(raw)
    except ValueError:
        return raw          # a bare JSON string scalar


def save_state(viewer_id: str, state: dict) -> None:
    """Persist only what changed. Every top-level value present in the dict is
    re-serialized (the only way to know whether a handler mutated it in place),
    but a key whose text matches what is already stored is not written.
    Deletes follow _deleted_keys. Write-through: the rows are committed
    before this returns."""
    vid = str(viewer_id)
    # dict.items, not state.items: a LazyState must not load its unread lazy
    # keys just to find out they did not change.
    texts = {k: json.dumps(v) for k, v in dict.items(state)}
    with _lock:
        with _connect() as conn:
            _sync_external_writes(conn)
            previous = _cached_rows(conn, viewer_id)
            changed = [(vid, k, t) for k, t in texts.items() if previous.get(k) != t]
            gone = _deleted_keys(state, previous, texts)
            if changed:
                conn.executemany(
                    "INSERT INTO viewer_state_kv (viewer_id, key, value) VALUES (?,?,?)"
                    " ON CONFLICT(viewer_id, key) DO UPDATE SET value = excluded.value",
                    changed,
                )
            if gone:
                conn.executemany(
                    "DELETE FROM viewer_state_kv WHERE viewer_id = ? AND key = ?",
                    [(vid, k) for k in gone],
                )
            conn.execute(
                "INSERT OR IGNORE INTO viewer_state_present (viewer_id) VALUES (?)", (vid,)
            )
        # Committed -- only now may memory move, so a failed write leaves the
        # cache agreeing with the disk.
        previous.update((k, t) for _, k, t in changed)
        for k in gone:
            previous.pop(k, None)
    if isinstance(state, LazyState):
        state._dropped.clear()


def _deleted_keys(state: dict, stored, texts) -> set:
    """Which of the viewer's stored keys a save of `state` deletes. A LazyState
    deletes exactly what its caller explicitly removed: an absent key there
    means "never touched". A plain dict is taken as the whole state, except
    that it cannot delete a _LAZY_KEYS key by omission. admin_panel/history.py
    uses this too, so its undo log agrees with what was actually written."""
    if isinstance(state, LazyState):
        return {k for k in state._dropped if k not in texts and k in stored}
    return {k for k in stored if k not in texts and k not in _LAZY_KEYS}


def delete_state(viewer_id: str) -> None:
    vid = str(viewer_id)
    with _lock:
        with _connect() as conn:
            conn.execute("DELETE FROM viewer_state_kv WHERE viewer_id = ?", (vid,))
            conn.execute("DELETE FROM viewer_state_present WHERE viewer_id = ?", (vid,))
        _text_cache.pop(_cache_key(viewer_id), None)


def all_viewer_ids() -> list[str]:
    """Every viewer_id with persisted state -- for features that need to look
    across accounts on this server (e.g. team_stadium opponent matchmaking
    against other real accounts' submitted rosters, not fabricated players)."""
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT viewer_id FROM viewer_state_present").fetchall()
    return [r[0] for r in rows]
