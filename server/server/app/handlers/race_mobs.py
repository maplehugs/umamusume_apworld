"""Mob (NPC) fillers for the two "bring your own umas" race modes: practice
race and room match. Both fill whatever gates the players leave empty with
anonymous mob umas -- never a named character, never one of somebody's own
trained charas.

The two modes fill DIFFERENTLY, and each is kept to what is actually known
about it:

PRACTICE RACE -- preset_mobs()
    The field is master.mdb's own mob presets: single_mode_npc's mob rows
    (mob_id 8xxx, chara_id 1), used EXACTLY as master defines them -- their
    stats, aptitudes, skill_set, motivation range, mob face and dress. They
    are NOT scaled to the player's uma. They used to be: practice race
    borrowed single_mode_team._mob_opponents, which is built for career races
    (rescaled to 45-75% of the trainee, ~15% named runners, and a borrowed
    named-uma face) -- so practice fields carried real named umas and tracked
    the player's own strength, neither of which the real mode does.

ROOM MATCH -- room_mobs()
    Read straight off real room_match responses (captures/20260924_195146:
    0010/0013 get_saved_race_result, 0033 race_start). Room mobs are NOT
    single_mode_npc rows -- no master table carries their numbers (checked in
    both the Global and JP master.mdb). What the captures show:

      * 17 fixed mob SLOTS, single_mode_chara_id == trained_chara_id == 35..51.
        A field needing N mobs draws N distinct slots.
      * Each slot keeps the same running style, running-style aptitudes and
        10-skill pool in every capture (_ROOM_SLOTS below). A weaker field
        draws a random SUBSET of the pool (6 of the 10 in 0033).
      * Distance/ground aptitude is built around the race itself: A on the
        race's own distance and surface, F on the neighbouring distances,
        G otherwise (a 2000m turf race gave every mob 1/2/7/2 and 7/1).
      * The face is a random mob_data id (8xxx) wearing its own dress (see
        mob_dress).
      * Stats DO scale with the room's entrants -- the same course (800005)
        gave (650,683,507,317,688) against a 3474-total entrant and
        (1000,1000,1000,557,1000) against a 5123-total one -- with a ~3% jitter
        per stat per mob. Those two captures are the anchors _ROOM_ANCHORS
        interpolates between; outside them the weaker anchor scales down
        proportionally and the stronger one holds (its 1000s look like a cap).

final_grade -- mob_rank()
    Every mob carries its real rank (single_mode_rank from the career score),
    not a blank one. The captures confirm the mapping: mob scores 6135/6341 ->
    grade 10 and 13131/13179 -> grade 14, matching the served final_grade.
    Leaving it unset is what made every practice-race mob show as G.
"""

from __future__ import annotations

import functools
import random

from .. import master_data, rating_formula

MOB_CHARA_ID = 1

# Highest mob a race field may use. Global's single_mode_npc never goes past
# it, so this is a no-op there. JP's master adds mob rows past it: groups 51
# and 61-69 on 9xxx mobs, plus group-0 mobs up to 8633, all on the newer NPC
# outfits (dress 27-29). Real JP career races field none of them (181 distinct
# mobs over the ramen captures, all 8000-8509), and a watched race with one in
# its field hangs on the pre-race loading screen (2026-09-26, twice).
MAX_RACE_MOB_ID = 8612

# --------------------------------------------------------------- shared ---


@functools.lru_cache(maxsize=None)
def mob_dress(mob_id: int) -> int:
    """The race_dress_id a mob must wear: its own mob_data.dress_id (8/11/12).

    The client draws a mob's portrait from a pre-rendered
    mob_chr_icon_{mob}_{dress} asset, which only exists for the mob's own
    dress. Any other dress leaves the portrait blank, e.g. in the race result
    list (user-reported on JP 2026-09-27). Real servers always send the own
    dress (all 31 room mobs in captures/20260924_195146, all 556 Unity Cup
    mobs in fixtures/capture_06d26c) or the placeholder 1 (career races).
    single_mode_npc's race_dress_id is NOT it: every mob row there says 8,
    which is right for only about a quarter of them."""
    row = master_data.query_one(
        "SELECT dress_id FROM mob_data WHERE mob_id=?", (int(mob_id),))
    return (row["dress_id"] if row else 0) or 1


def mob_rank(horse: dict) -> int:
    """single_mode_rank id for a horse's stats + skills."""
    from . import trained_chara
    return trained_chara._rank_for_score(rating_formula.get_career_score(horse))


def _running_style_from_aptitudes(row: dict) -> int:
    apts = {1: row.get("proper_running_style_nige", 1),
            2: row.get("proper_running_style_senko", 1),
            3: row.get("proper_running_style_sashi", 1),
            4: row.get("proper_running_style_oikomi", 1)}
    return max(apts, key=apts.get)


@functools.lru_cache(maxsize=None)
def _skill_set(skill_set_id: int) -> tuple:
    if not skill_set_id:
        return ()
    row = master_data.query_one("SELECT * FROM skill_set WHERE id=?", (skill_set_id,))
    if row is None:
        return ()
    return tuple((row[f"skill_id{n}"], row[f"skill_level{n}"] or 1)
                 for n in range(1, 21) if row[f"skill_id{n}"])


def _base_mob(slot_id: int, mob_id: int, dress_id: int) -> dict:
    """The fields every mob shares, in the trained-chara shape
    practice_race._build_race_horse_entry reads."""
    return {"viewer_id": 0, "trainer_name": None, "owner_viewer_id": 0,
            "owner_trainer_name": "",
            "trained_chara_id": slot_id, "single_mode_chara_id": slot_id,
            "nickname_id": 0, "card_id": 0, "chara_id": MOB_CHARA_ID,
            "mob_id": mob_id, "race_dress_id": dress_id,
            "rarity": 1, "talent_level": 1, "npc_type": 0,
            "chara_color_type": 0, "win_saddle_id_array": [],
            "wins": 0, "fans": 0}


# ---------------------------------------------------------- practice race ---


@functools.lru_cache(maxsize=1)
def _preset_rows() -> tuple:
    return tuple(dict(r) for r in master_data.query(
        "SELECT * FROM single_mode_npc WHERE mob_id > 0 AND mob_id <= ? AND chara_id = ? "
        "ORDER BY id", (MAX_RACE_MOB_ID, MOB_CHARA_ID)))


def preset_mobs(count: int, rng: random.Random, avoid_ids=()) -> list[dict]:
    """`count` distinct master.mdb mob presets, unscaled. Distinct by row AND
    by face, so no two mobs in one field share a mob_id. avoid_ids: the
    entrants' trained_chara_ids -- this server's roster ids are small enough to
    collide with npc row ids, and the client pairs rows to trained charas by
    that id."""
    avoid = set(avoid_ids or ())
    rows = [r for r in _preset_rows() if r["id"] not in avoid]
    rng.shuffle(rows)
    out, faces = [], set()
    for row in rows:
        if len(out) >= count:
            break
        if row["mob_id"] in faces:
            continue
        faces.add(row["mob_id"])
        mob = _base_mob(row["id"], row["mob_id"], mob_dress(row["mob_id"]))
        mob.update({
            "speed": row["speed"], "stamina": row["stamina"], "power": row["pow"],
            "guts": row["guts"], "wiz": row["wiz"],
            "running_style": _running_style_from_aptitudes(row),
            "motivation": rng.randint(max(1, row["motivation_min"] or 1),
                                      max(1, row["motivation_max"] or 5)),
            "skill_array": [{"skill_id": s, "level": lv}
                            for s, lv in _skill_set(row["skill_set_id"] or 0)],
        })
        for k in ("proper_distance_short", "proper_distance_mile",
                  "proper_distance_middle", "proper_distance_long",
                  "proper_running_style_nige", "proper_running_style_senko",
                  "proper_running_style_sashi", "proper_running_style_oikomi",
                  "proper_ground_turf", "proper_ground_dirt"):
            mob[k] = row[k]
        mob["rank"] = mob_rank(mob)
        out.append(mob)
    return out


# ------------------------------------------------------------- room match ---

# Skill pools, each shared by the slots listed against it in _ROOM_SLOTS.
# Order is as served in capture 0010.
_POOLS = {
    "A": (200172, 200182, 201522, 200112, 201621, 201202, 200542, 200032, 200072, 201631),
    "B": (201122, 200152, 200022, 200162, 201212, 201282, 201631, 200252, 200262, 201252),
    "C": (200282, 201352, 201532, 201641, 200132, 200482, 200012, 201232, 200142, 200272),
    "D": (200042, 200952, 200072, 200262, 201392, 201641, 201422, 201182, 200252, 200752),
    "E": (200222, 200622, 200722, 200102, 201072, 200032, 200062, 201482, 200432, 200232),
    "F": (201552, 200102, 200162, 200712, 200112, 201082, 201492, 200152, 201631, 200052),
    "G": (201312, 200202, 200572, 200122, 201222, 200042, 201581, 200462, 200192, 200082),
    "H": (201402, 201542, 200242, 200952, 200092, 200742, 201641, 200362, 200052, 200212),
}

# slot id -> (running_style, (nige, senko, sashi, oikomi) aptitude, skill pool).
# 37/39/49 appear only in 0033's 6-skill field; their pools are the 10-skill
# pools those 6 are exact subsets of.
_ROOM_SLOTS = {
    35: (1, (7, 3, 2, 1), "A"), 36: (1, (7, 4, 3, 1), "B"),
    37: (2, (3, 7, 3, 1), "G"), 38: (2, (3, 7, 3, 1), "C"),
    39: (3, (3, 4, 7, 1), "H"), 40: (3, (3, 4, 7, 1), "D"),
    41: (4, (3, 4, 3, 7), "E"), 42: (1, (7, 3, 2, 1), "F"),
    43: (1, (7, 4, 3, 1), "A"), 44: (2, (3, 7, 3, 1), "B"),
    45: (2, (3, 7, 3, 1), "G"), 46: (3, (3, 4, 7, 1), "C"),
    47: (3, (3, 4, 7, 1), "H"), 48: (4, (3, 4, 3, 7), "D"),
    49: (4, (1, 3, 4, 7), "E"), 50: (1, (7, 3, 4, 3), "F"),
    51: (2, (1, 7, 4, 3), "G"),
}
ROOM_MOB_SLOTS = tuple(_ROOM_SLOTS)

_STAT_KEYS = ("speed", "stamina", "power", "guts", "wiz")

# (entrant 5-stat total, mob stat line, mob skill count) -- the two captures.
_ROOM_ANCHORS = (
    (3474, (650, 683, 507, 317, 688), 6),
    (5123, (1000, 1000, 1000, 557, 1000), 10),
)
_ROOM_JITTER = 0.03


def _room_mob_base(entrant_total: float) -> tuple[list[float], int]:
    (lo_t, lo_s, lo_n), (hi_t, hi_s, hi_n) = _ROOM_ANCHORS
    if entrant_total <= lo_t:
        f = max(entrant_total, 1) / lo_t
        return [s * f for s in lo_s], lo_n
    if entrant_total >= hi_t:
        return list(hi_s), hi_n
    t = (entrant_total - lo_t) / (hi_t - lo_t)
    return ([a + (b - a) * t for a, b in zip(lo_s, hi_s)],
            round(lo_n + (hi_n - lo_n) * t))


@functools.lru_cache(maxsize=1)
def _room_faces() -> tuple:
    return tuple(r["mob_id"] for r in master_data.query(
        "SELECT mob_id FROM mob_data WHERE mob_id BETWEEN 8000 AND ? ORDER BY mob_id",
        (MAX_RACE_MOB_ID,)))


def _distance_bucket(distance: int) -> int:
    """1 short / 2 mile / 3 middle / 4 long, by the game's own boundaries."""
    if distance <= 1400:
        return 1
    if distance <= 1800:
        return 2
    if distance <= 2400:
        return 3
    return 4


@functools.lru_cache(maxsize=None)
def _race_course(race_instance_id: int) -> tuple[int, int]:
    """(distance bucket, ground 1 turf / 2 dirt) for a race instance."""
    row = master_data.query_one(
        "SELECT rcs.distance, rcs.ground FROM race_instance ri "
        "JOIN race r ON r.id = ri.race_id "
        "JOIN race_course_set rcs ON rcs.id = r.course_set WHERE ri.id = ?",
        (race_instance_id,))
    if row is None:
        return 3, 1
    return _distance_bucket(row["distance"]), row["ground"]


def room_mobs(entrants: list[dict], count: int, race_instance_id: int,
              rng: random.Random, motivation: int = 0) -> list[dict]:
    """`count` room-match mobs for a field whose players are `entrants`
    (trained-chara dicts). motivation 0 = each mob rolls its own.

    Slots whose id an entrant's own trained_chara_id already uses are drawn
    last and re-keyed if they must be used (see preset_mobs' avoid_ids)."""
    count = max(0, min(count, len(_ROOM_SLOTS)))
    if not count:
        return []
    totals = [sum((c.get(k) if k != "power" else c.get("power", c.get("pow")))
                  or 0 for k in _STAT_KEYS) for c in entrants] or [0]
    base, n_skills = _room_mob_base(sum(totals) / len(totals))
    bucket, ground = _race_course(race_instance_id)
    distance_apt = {d: 7 if d == bucket else 2 if abs(d - bucket) == 1 else 1
                    for d in (1, 2, 3, 4)}
    faces = rng.sample(_room_faces(), count) if len(_room_faces()) >= count \
        else [rng.choice(_room_faces() or (8000,)) for _ in range(count)]

    taken = {c.get("trained_chara_id") for c in entrants}
    free = [s for s in ROOM_MOB_SLOTS if s not in taken]
    clashing = [s for s in ROOM_MOB_SLOTS if s in taken]
    slots = sorted(rng.sample(free, min(count, len(free)))
                   + clashing[:max(0, count - len(free))])

    out = []
    for slot, face in zip(slots, faces):
        style, (nige, senko, sashi, oikomi), pool = _ROOM_SLOTS[slot]
        wire_id = slot
        while wire_id in taken:
            wire_id += 1000
        mob = _base_mob(wire_id, face, mob_dress(face))
        for k, v in zip(_STAT_KEYS, base):
            mob[k] = max(1, round(v * rng.uniform(1 - _ROOM_JITTER, 1 + _ROOM_JITTER)))
        mob.update({
            "running_style": style,
            "proper_running_style_nige": nige, "proper_running_style_senko": senko,
            "proper_running_style_sashi": sashi, "proper_running_style_oikomi": oikomi,
            "proper_distance_short": distance_apt[1], "proper_distance_mile": distance_apt[2],
            "proper_distance_middle": distance_apt[3], "proper_distance_long": distance_apt[4],
            "proper_ground_turf": 7 if ground == 1 else 1,
            "proper_ground_dirt": 7 if ground == 2 else 1,
            "motivation": motivation or rng.randint(1, 5),
            "skill_array": [{"skill_id": s, "level": 1}
                            for s in rng.sample(_POOLS[pool], min(n_skills, len(_POOLS[pool])))],
        })
        mob["rank"] = mob_rank(mob)
        out.append(mob)
    return out
