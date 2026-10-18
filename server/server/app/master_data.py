"""
Read-only access to the game's master.mdb (plain SQLite3, no encryption --
see README). Opened once, read-only, connection reused across requests.
"""

from __future__ import annotations

import functools
import logging
import os
import sqlite3
from pathlib import Path


def context_cache(maxsize=128):
    """Keep immutable custom revisions out of the stock master lookup cache."""
    def decorate(fn):
        @functools.lru_cache(maxsize=maxsize)
        def cached(revision, current_region, args, kwargs):
            return fn(*args, **dict(kwargs))
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            from . import custom_support
            return cached(custom_support.CURRENT_PACK.get(), region.CURRENT_REGION.get(),
                          args, tuple(sorted(kwargs.items())))
        wrapped.cache_clear = cached.cache_clear
        wrapped.cache_info = cached.cache_info
        return wrapped
    return decorate

from . import region

log = logging.getLogger("uma-server")

# Each region reads its OWN client's master.mdb -- JP's has 627 tables to
# Global's 416 and different columns on 55 shared ones, so the two are never
# interchangeable. The process's region is fixed at startup (region.py).
_GAME_DIRS = {
    "global": ("UmamusumePrettyDerby", "UmamusumePrettyDerby_Data"),
    "jp": ("UmamusumePrettyDerby_Jpn", "UmamusumePrettyDerby_Jpn_Data"),
}
_INSTALL, _DATA = _GAME_DIRS[region.PROCESS_REGION]
_RELATIVE_MDB = f"{_DATA}/Persistent/master/master.mdb"

# Candidates checked in order; first one that exists on disk wins. Covers a
# Windows Steam install, a native Linux Steam install, and an env var
# override for anything else (a second Steam library, a Proton prefix, ...).
_CANDIDATES = [
    p for p in [
        os.environ.get("MASTER_MDB_PATH"),
        rf"C:\Program Files (x86)\Steam\steamapps\common\{_INSTALL}\\"
        + _RELATIVE_MDB.replace("/", "\\"),
        os.path.expanduser(
            f"~/.local/share/Steam/steamapps/common/{_INSTALL}/" + _RELATIVE_MDB
        ),
    ]
    if p
]


def _resolve_mdb_path() -> Path:
    for candidate in _CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path
    # Nothing found: fall back to the first candidate so the resulting error
    # (file not found) points at a real, informative path.
    return Path(_CANDIDATES[0])


MASTER_MDB_PATH = _resolve_mdb_path()

# THE ENGLISH TEXT OVERLAY (JP only). Every server-side read of text_data is
# for MATCHING, never for display (the client renders its own master's text):
# career events are found by their title against GameTora's English pages,
# epithet rules are parsed from their English prose, missions and race stories
# are matched on English race names. JP's text_data is Japanese, so on the JP
# process all of that matched nothing -- no support, trainee, pre/post-race or
# skill-hint event resolved to its outcomes.
#
# (category, index) keys are the same in both regions' masters (story 501022720
# is "Just an Acupuncturist, No Worries! ☆" in Global and あんし～ん笹針師 in
# JP), so text_data on the JP process is a TEMP view -- which SQLite resolves
# ahead of main.text_data -- giving Global's English text where Global has the
# row and JP's own text otherwise. JP-only content keeps its Japanese text,
# which is what GameTora's pages for JP-only cards are written in.
# main.text_data still reads JP's own text.
_EN_TEXT_CANDIDATES = [
    p for p in [
        os.environ.get("UMA_EN_TEXT_MDB"),
        r"C:\Program Files (x86)\Steam\steamapps\common\UmamusumePrettyDerby"
        r"\UmamusumePrettyDerby_Data\Persistent\master\master.mdb",
        os.path.expanduser("~/.local/share/Steam/steamapps/common/UmamusumePrettyDerby/"
                           "UmamusumePrettyDerby_Data/Persistent/master/master.mdb"),
    ]
    if p
]

_conn: sqlite3.Connection | None = None


def _overlay_english_text(conn: sqlite3.Connection) -> None:
    source = next((Path(p) for p in _EN_TEXT_CANDIDATES if Path(p).is_file()), None)
    if source is None:
        log.warning("master_data: no Global master.mdb for English text (set UMA_EN_TEXT_MDB) "
                    "-- events, epithets and race stories will not resolve on JP")
        return
    conn.execute("ATTACH DATABASE ? AS en", (f"file:{source.as_posix()}?mode=ro",))
    conn.execute(
        "CREATE TEMP VIEW text_data AS "
        # A blank English row (JP-only content Global ships empty) keeps the
        # Japanese text rather than serving ''.
        "SELECT j.id, j.category, j.[index], COALESCE(NULLIF(e.text, ''), j.text) AS text "
        "FROM main.text_data j LEFT JOIN en.text_data e "
        "ON e.category = j.category AND e.[index] = j.[index]")


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        # uri=True + mode=ro: fail fast on a locked/missing file rather than
        # silently creating an empty db at the wrong path.
        uri = f"file:{MASTER_MDB_PATH.as_posix()}?mode=ro"
        _conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        if region.PROCESS_REGION == "jp":
            _overlay_english_text(_conn)
    return _conn


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    from . import custom_support
    return (custom_support.connection() or get_connection()).execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    from . import custom_support
    return (custom_support.connection() or get_connection()).execute(sql, params).fetchone()


@functools.lru_cache(maxsize=None)
def has_table(name: str) -> bool:
    """Whether this client's master.mdb has the table. The regions' schemas
    differ (JP 627 tables, Global 416, and each has some the other lacks), so
    a feature whose table is absent is simply not running in that region."""
    return query_one("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                     (name,)) is not None


def has_column(table: str, column: str) -> bool:
    """Whether this master.mdb's `table` has `column` (same region-schema
    reason as has_table: JP grew columns Global's copy of a table lacks)."""
    return any(r["name"] == column for r in query(f"PRAGMA table_info('{table}')"))


# ------------------------------------------------------- character lookups --
# Generic master.mdb reads that several unrelated features need. They lived in
# the Grand Live module, so shared career code had to import a SCENARIO to ask
# a plain master-data question -- one of the couplings that made Grand Live look
# load-bearing when it was not.

@context_cache(maxsize=1024)
def support_card_chara(support_card_id: int) -> int:
    """The CHARACTER a support card belongs to, from support_card_data.

    NOT `support_card_id // 100`. That works for a trainee card (101303 -> 1013)
    and is nonsense for a support card: 30028 // 100 = 300, which is not a
    character at all. Feeding those bogus ids to the client made it look up
    characters that do not exist, and the resulting null crashed the Live screen
    outright -- Player.log:

        NullReferenceException
          at Gallop.SingleModeScenarioLiveTopChara..ctor(bool isGrandlive,
                                                         List prevCharaInfos)
          at Gallop.SingleModeScenarioLiveTopController.InitializeView()
    """
    row = query_one(
        "SELECT chara_id FROM support_card_data WHERE id=?", (int(support_card_id),))
    return int(row["chara_id"]) if row else 0


# Trainee characters live in the 1000-1999 band; the 9xxx band is NPCs (Tazuna
# 9001, the Director 9002, Light Hello 9008, ...).
TRAINEE_CHARA_MIN, TRAINEE_CHARA_MAX = 1000, 1999


def is_trainee_chara(chara_id) -> bool:
    """Whether this chara_id is a playable trainee rather than a scenario NPC."""
    return TRAINEE_CHARA_MIN <= int(chara_id or 0) <= TRAINEE_CHARA_MAX


# ------------------------------------------------- portrait art this build has
# master.mdb ships EVERY character, including ones this (Global) build has no
# art for: those rows carry the not-released sentinel
# chara_data.start_date = 2524608000 (2050-01-01) and, exactly and only those,
# have no card_data row either -- the two agree on all 96 rows (66 released, 30
# not). A screen that draws such a chara gets a BLANK WHITE PLANE: no error, no
# placeholder, no Player.log line. The opponent panel registers a texture
# download per runner
# (PartsSingleModeScenarioTeamRaceOpponent.RegisterDownload/SetupCharaImage)
# and simply draws nothing when the path does not resolve.
#
# User-reported 2026-09-07: Unity Cup opponent teams had white gaps where Twin
# Turbo, Sirius Symboli, Narita Top Road and the like should have been -- we
# were picking named opponents from the whole single_mode_npc table, 18 of
# whose 84 characters this build cannot draw. A MOB is always renderable, so
# an undrawable named runner should become one rather than a hole.
#
# card_data is the test rather than start_date because it is what the UI
# actually needs (a chara icon is a card icon). Scenario NPCs with no card at
# all -- Happy Meek (2001), Bitter Glasse (2002), Little Cocon (2003) -- are
# therefore "undrawable" here too, which is right for the two Unity Cup girls
# and conservative for Meek, whose art DOES ship with URA; her own builder
# (single_mode_team._happy_meek_opponent) does not consult this.

@functools.lru_cache(maxsize=1)
def drawable_charas() -> frozenset:
    """The characters whose portrait this client build can actually draw."""
    return frozenset(int(r["chara_id"]) for r in
                     query("SELECT DISTINCT chara_id FROM card_data"))


def has_portrait_art(chara_id) -> bool:
    """Whether the client can draw this character at all -- see above. False
    means: ship her as a mob, or do not ship her."""
    return int(chara_id or 0) in drawable_charas()


# ------------------------------------------------------------ skill lookups --

@functools.lru_cache(maxsize=4096)
def skill_tip_key(skill_id) -> tuple[int, int]:
    """(group_id, rarity) for a skill -- the key chara_info.skill_tips_array
    entries are identified by on the wire.

    A gold skill and its white group-mate share a group_id (200581 "Speed Star"
    rarity=2 and 200582 "Prepared to Pass" rarity=1 both group to 20058), so the
    group ALONE does not say which of the pair a hint is for; the client picks
    by (group_id, rarity). Callers that filled in a fixed rarity=1 therefore
    turned every gold hint into its white group-mate -- e.g. the Fine Motion SSR
    (30010) chain finale hints Speed Star and always rendered/granted Prepared
    to Pass instead. Always take the rarity from the skill's own row rather than
    from whichever "slot" a caller thinks it fills.

    (rarity=1 within a group is not unique -- the ○/× debuff pairs collide, e.g.
    group 20033's "Corner Adept ○" 200332 and "Corner Adept ×" 200333 -- but
    that ambiguity is the game's own wire shape, not something to work around.)

    Unknown skill ids fall back to the id//10 group the whole DB follows and
    rarity 1, so a missing master row degrades instead of raising."""
    sid = int(skill_id)
    row = query_one("SELECT group_id, rarity FROM skill_data WHERE id=?", (sid,))
    if row is None:
        return sid // 10, 1
    return int(row["group_id"]), int(row["rarity"] or 1)
