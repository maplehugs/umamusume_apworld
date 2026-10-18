"""JP's skill evolution (スキル進化): conditions tracked through a career, the
evolutions picked on the spark screen, and the evolved skills on the veteran.

WHAT THE REAL SERVER DOES (`WIRE`, jp_captures, 688 career starts, 70 spark
screens with picks):

    - every career reply's chara_info carries skill_upgrade_info_array
      [{condition_id, total_count, current_count}], sorted by condition_id, for
      every evolution this career could reach:
        card        skill_upgrade_description rows of the trainee's card with
                    rank <= talent_level (a Lv5 card lists its rank-3 and
                    rank-5 rows, a Lv7 card its rank-7 row too);
        scenario    skill_upgrade_speciality rows of the career's scenario;
        succession  skill_upgrade_succession_skill rows whose card the account
                    owns at 3 stars or more (the first condition says so, and
                    it is always 1/1 when the row is listed);
      the finish reply's chara_info carries [] (the career is over);
    - conditions sharing `num` are alternatives, different `num`s are all
      required (card 113101: evolved via 11310104 2/2 while its alternative
      11310103 stayed 0/1); current_count stops at total_count;
    - single_mode*/factor_select names the picks: skill_id_array plus
      gain_skill_upgrade_info_array [{upgrade_type, skill_id}], upgrade_type
      1 card / 2 scenario / 0 succession;
    - the finish reply's chara_info then holds the evolved skills in
      skill_array (sorted by id, the unique skill first) and the skills they
      replaced in disable_skill_id_array -- [202791, 203041, 203541, 911091]
      for [414041, 113101111, 113101211, 92111091].

The skill an evolution replaces: a card row's is the card's own gold skill
unlocked at the same rank (available_skill_set.need_rank == rank; exactly one
for all 625 rows), a scenario row's and a succession row's name it
(base_skill_id).

THE CONDITIONS are Japanese prose only (text_data 290), 287 distinct shapes.
_parse turns each into a counter over the career: stats, skills held by tag or
effect, fans, race results from race_history, outings / rests / motivation-ups
/ conditions tallied from the request stream here, fired events, and the Ramen
Jamborees. A condition no rule reads (scenario milestones of scenarios this
server does not run) counts as met, so a gap in the parser never blocks an
evolution; unparsed() lists them. Event conditions that name an outcome
("...で<choice>する") count once the event has fired.

Everything here is JP-only: app/jp/server.py calls before() and after() around
each request. Global's handlers are untouched.
"""

from __future__ import annotations

import functools
import logging
import re
import time

from ... import epithets, event_engine, master_data, scenarios
from ... import state as state_store
from ...handlers import collection
from ...handlers import single_mode_team as smt

log = logging.getLogger(__name__)

HANDLERS: dict = {}

# Per-career tallies (full_state, reset by every career start).
KEY = "jp_skill_upgrade"

# gain_skill_upgrade_info_array's upgrade_type, per master upgrade_type.
_WIRE_TYPE = {1: 1, 2: 2, 3: 0}

# skill_data columns: (ability_type, value) pairs of both effect slots.
_ABILITY_COLS = tuple((f"ability_type_{i}_{j}", f"float_ability_value_{i}_{j}")
                      for i in (1, 2) for j in (1, 2, 3))

_STATS = {"スピード": "speed", "スタミナ": "stamina", "パワー": "power",
          "根性": "guts", "賢さ": "wiz"}
# ＜...＞ skill families -> skill_data.tag_id.
_TAGS = {"逃げ": "101", "先行": "102", "差し": "103", "追込": "104",
         "短距離": "201", "マイル": "202", "中距離": "203", "長距離": "204",
         "ダート": "502"}
# "<effect>スキル" -> the ability types that effect is (value > 0).
_EFFECTS = {"速度が上がる": {21, 22, 27}, "加速力が上がる": {31},
            "持久力が回復する": {9}, "コース取りがうまくなる": {28},
            "能力を引き出す": {1, 2, 3, 4, 5}}
_STYLES = {"逃げ": 1, "先行": 2, "差し": 3, "追込": 4}
_YEARS = {"ジュニア": 0, "クラシック": 1, "シニア": 2}
_GROUNDS = {"良": 1, "稍重": 2, "重": 3, "不良": 4}
_BANDS = {"短距離": "sprint", "マイル": "mile", "中距離": "medium", "長距離": "long"}
_GRADE_WORDS = (("GⅡまたはGⅠ", {"g1", "g2"}), ("重賞", {"g1", "g2", "g3"}),
                ("GⅠ", {"g1"}), ("GⅡ", {"g2"}), ("GⅢ", {"g3"}), ("レース", None))

_REST_COMMAND_ID = 701
_REST_COMMAND_TYPE = 7
_OUTING_COMMAND_TYPE = 3
_PAL_OUTING_GROUP = 390
_CAMP_GROUP = 304
_RECREATION_GROUPS = {301, 390, 304}


# ------------------------------------------------------------ master data --

def available() -> bool:
    return master_data.has_table("skill_upgrade_condition")


def _jp_text(category: int, index: int) -> str:
    row = master_data.query_one(
        "SELECT text FROM main.text_data WHERE category=? AND [index]=?", (category, index))
    return row["text"] if row else ""


def _norm(text: str) -> str:
    """Line breaks, spaces and full-width digits out; ASCII parens and G1-style
    grades to the forms race names use."""
    text = (text or "").replace("\\n", "").replace("\n", "").strip()
    text = re.sub(r"\s+", "", text)
    text = text.translate(str.maketrans("０１２３４５６７８９()ｍ〇", "0123456789（）m○"))
    return text.replace("G1", "GⅠ").replace("G2", "GⅡ").replace("G3", "GⅢ")


@functools.lru_cache(maxsize=None)
def _conditions(description_id: int) -> tuple:
    return tuple(dict(r) for r in master_data.query(
        "SELECT id, upgrade_type, num, sub_num FROM skill_upgrade_condition "
        "WHERE description_id=? ORDER BY id", (description_id,)))


@functools.lru_cache(maxsize=None)
def _card_base_skill(card_id: int, rank: int) -> int:
    row = master_data.query_one(
        "SELECT a.skill_id FROM available_skill_set a JOIN skill_data s ON s.id=a.skill_id "
        "WHERE a.available_skill_set_id=? AND a.need_rank=? AND s.rarity=2", (card_id, rank))
    return int(row["skill_id"]) if row else 0


def _evolutions(chara_info: dict, full_state: dict) -> list[dict]:
    """Every evolution this career lists: {description_id, wire_type,
    skill_id, base_skill_id, conditions}."""
    now = int(time.time())
    out = []
    card_id = int(chara_info.get("card_id") or 0)
    talent = int(chara_info.get("talent_level") or 1)
    for r in master_data.query(
            "SELECT id, rank, skill_id FROM skill_upgrade_description "
            "WHERE card_id=? AND rank<=? AND start_date<=?", (card_id, talent, now)):
        out.append({"description_id": r["id"], "wire_type": 1, "skill_id": r["skill_id"],
                    "base_skill_id": _card_base_skill(card_id, r["rank"]), "rank": r["rank"]})
    for r in master_data.query(
            "SELECT skill_id, base_skill_id FROM skill_upgrade_speciality "
            "WHERE scenario_id=? AND start_date<=?",
            (int(chara_info.get("scenario_id") or 0), now)):
        out.append({"description_id": r["skill_id"], "wire_type": 2,
                    "skill_id": r["skill_id"], "base_skill_id": r["base_skill_id"]})
    owned = {c.get("card_id"): int(c.get("rarity") or 0)
             for c in full_state.get(collection.CARD_LIST_KEY) or () if isinstance(c, dict)}
    for r in master_data.query(
            "SELECT card_id, base_skill_id, skill_id FROM skill_upgrade_succession_skill "
            "WHERE start_date<=?", (now,)):
        if owned.get(r["card_id"], 0) >= 3:
            out.append({"description_id": r["base_skill_id"], "wire_type": 0,
                        "skill_id": r["skill_id"], "base_skill_id": r["base_skill_id"]})
    for e in out:
        e["conditions"] = _conditions(e["description_id"])
    return [e for e in out if e["conditions"] and e["base_skill_id"]]


# ------------------------------------------------------------ race lookups --

@functools.lru_cache(maxsize=1)
def _race_names() -> dict:
    """Normalised JP race name -> race_instance ids (text 28 full name, 29
    short name: "ジャパンカップ" / "ジャパンC")."""
    names: dict = {}
    for r in master_data.query(
            "SELECT [index], text FROM main.text_data WHERE category IN (28, 29)"):
        names.setdefault(_norm(r["text"]), set()).add(int(r["index"]))
    return names


@functools.lru_cache(maxsize=None)
def _track_ids(name: str) -> frozenset:
    return frozenset(int(r["index"]) for r in master_data.query(
        "SELECT [index] FROM main.text_data WHERE category=35 AND text=?", (name,)))


@functools.lru_cache(maxsize=None)
def _race(program_id: int) -> dict | None:
    info = epithets._race_info(program_id)
    return dict(info) if info else None


def _resolve_race(name: str):
    """'有馬記念（クラシック級）' -> ({instance ids}, year index or None)."""
    year = None
    m = re.fullmatch(r"(.+?)（(ジュニア|クラシック|シニア)級）", name)
    if m:
        name, year = m.group(1), _YEARS[m.group(2)]
    ids = _race_names().get(name)
    if not ids and name.endswith("カップ"):
        ids = _race_names().get(name[:-3] + "C")
    return (frozenset(ids), year) if ids else None


def _race_list(blob: str):
    parts = [p for p in blob.split("、") if p]
    resolved = [_resolve_race(p) for p in parts]
    return tuple(resolved) if parts and all(resolved) else None


# ----------------------------------------------------------------- parser --
# A condition compiles to fn(ctx) -> (current, total).

def _capped(n, total):
    return min(int(n), total), total


def _race_filter(body: str):
    """The race set a '...をN勝以上する' clause counts, or None when the body
    is not a race category (it names races, or something else entirely)."""
    f = {}
    m = re.match(r"(ジュニア|クラシック|シニア)級で", body)
    if m:
        f["year"], body = _YEARS[m.group(1)], body[m.end():]
    m = re.match(r"作戦「(逃げ|先行|差し|追込)」(?:かつ(\d+)番人気)?で", body)
    if m:
        f["style"] = _STYLES[m.group(1)]
        if m.group(2):
            f["popularity"] = int(m.group(2))
        body = body[m.end():]
    m = re.match(r"((?:「[^」]+」)+)のバ場状態で", body)
    if m:
        f["grounds"] = {_GROUNDS[g] for g in re.findall(r"「([^」]+)」", m.group(1))}
        body = body[m.end():]
    m = re.match(r"(.+?)レース場で", body)
    if m:
        f["tracks"] = _track_ids(m.group(1))
        body = body[m.end():]
    m = re.match(r"(短距離|マイル|中距離|長距離)(?:の)?", body)
    if m:
        f["band"], body = _BANDS[m.group(1)], body[m.end():]
    m = re.match(r"(\d+)mの", body)
    if m:
        f["distance"], body = int(m.group(1)), body[m.end():]
    m = re.match(r"(芝|ダート)(?:の)?", body)
    if m:
        f["surface"], body = ("turf" if m.group(1) == "芝" else "dirt"), body[m.end():]
    f["grades"] = None
    for word, grades in _GRADE_WORDS:
        if body == word:
            f["grades"], body = grades, ""
            break
    return f if body == "" else None


def _race_matches(rec: dict, f: dict) -> bool:
    info = rec["info"]
    if f.get("grades") is not None and info["grade"] not in f["grades"]:
        return False
    for key in ("band", "surface", "distance"):
        if key in f and info[key] != f[key]:
            return False
    if "tracks" in f and info["track_id"] not in f["tracks"]:
        return False
    if "year" in f and rec["year"] != f["year"]:
        return False
    if "style" in f and rec["style"] != f["style"]:
        return False
    if "popularity" in f and not (rec["popularity"] and rec["popularity"] <= f["popularity"]):
        return False
    if "grounds" in f and rec["ground"] not in f["grounds"]:
        return False
    return True


def _named_hits(ctx, race, won_only=True, max_rank=1):
    ids, year = race
    return [r for r in ctx["races"] if r["instance"] in ids
            and (year is None or r["year"] == year)
            and (not won_only or r["rank"] <= max_rank)]


def _back_to_back(ctx, race) -> int:
    years = sorted({r["year"] for r in _named_hits(ctx, race)})
    best = run = 0
    for i, y in enumerate(years):
        run = run + 1 if i and y == years[i - 1] + 1 else 1
        best = max(best, run)
    return min(best, 2)


def _event_ids(title: str) -> frozenset:
    return _event_titles().get(title, frozenset())


@functools.lru_cache(maxsize=1)
def _event_titles() -> dict:
    out: dict = {}
    for r in master_data.query("SELECT [index], text FROM main.text_data WHERE category=181"):
        out.setdefault(_norm(r["text"]), set()).add(int(r["index"]))
    return {k: frozenset(v) for k, v in out.items()}


@functools.lru_cache(maxsize=None)
def _skill_ids_named(name: str) -> frozenset:
    return frozenset(int(r["index"]) for r in master_data.query(
        "SELECT [index] FROM main.text_data WHERE category=47 AND text=?", (name,)))


@functools.lru_cache(maxsize=None)
def _condition_ids_named(name: str) -> frozenset:
    return frozenset(int(r["index"]) for r in master_data.query(
        "SELECT [index] FROM main.text_data WHERE category=142 AND text=?", (name,)))


@functools.lru_cache(maxsize=None)
def _skill_row(skill_id: int) -> dict:
    row = master_data.query_one("SELECT * FROM skill_data WHERE id=?", (skill_id,))
    if row is None:
        return {"tags": frozenset(), "effects": frozenset(), "group_id": 0}
    effects = {int(row[a]) for a, v in _ABILITY_COLS if row[a] and (row[v] or 0) > 0}
    return {"tags": frozenset((row["tag_id"] or "").split("/")),
            "effects": frozenset(effects), "group_id": int(row["group_id"] or 0)}


def _parse(text: str):
    """(fn(ctx) -> (current, total), parsed?) for one condition's prose."""
    t = _norm(text)
    m = re.fullmatch(r"基礎能力\[(.+?)\]が(\d+)以上になる", t)
    if m and m.group(1) in _STATS:
        stat, n = _STATS[m.group(1)], int(m.group(2))
        return (lambda c: _capped(c["ci"].get(stat) or 0, n)), True
    m = re.fullmatch(r"ファン数が(\d+)人以上になる", t)
    if m:
        n = int(m.group(1))
        return (lambda c: _capped(c["ci"].get("fans") or 0, n)), True
    m = re.fullmatch(r"＜(.+?)＞(?:の)?スキルを(\d+)個以上所持する", t)
    if m and m.group(1) in _TAGS:
        tag, n = _TAGS[m.group(1)], int(m.group(2))
        return (lambda c: _capped(sum(tag in _skill_row(s)["tags"] for s in c["skills"]), n)), True
    m = re.fullmatch(r"(.+?)スキルを(\d+)個以上所持する", t)
    if m and m.group(1) in _EFFECTS:
        eff, n = _EFFECTS[m.group(1)], int(m.group(2))
        return (lambda c: _capped(sum(bool(eff & _skill_row(s)["effects"])
                                      for s in c["skills"]), n)), True
    m = re.fullmatch(r"スキル「(.+)」を所持する", t)
    if m:
        ids = _skill_ids_named(m.group(1))
        return (lambda c: (int(bool(ids & set(c["skills"]))), 1)), bool(ids)

    # --- races ---
    m = re.fullmatch(r"(.+?)を二連覇する", t)
    if m and _race_list(m.group(1)):
        races = _race_list(m.group(1))
        return (lambda c: (sum(_back_to_back(c, r) for r in races), 2 * len(races))), True
    m = re.fullmatch(r"(.+?)に出走する", t)
    if m and _race_list(m.group(1)):
        races = _race_list(m.group(1))
        return (lambda c: (sum(bool(_named_hits(c, r, won_only=False)) for r in races),
                           len(races))), True
    m = re.fullmatch(r"(.+?)で(\d+)着以内になる", t)
    if m and _race_list(m.group(1)):
        races, place = _race_list(m.group(1)), int(m.group(2))
        return (lambda c: (int(all(_named_hits(c, r, max_rank=place) for r in races)), 1)), True
    m = re.fullmatch(r"(.+?)を勝利する", t)
    if m and _race_list(m.group(1)):
        races = _race_list(m.group(1))
        return (lambda c: (sum(bool(_named_hits(c, r)) for r in races), len(races))), True
    m = re.fullmatch(r"(.+?)を?(\d+)勝以上する", t) or re.fullmatch(r"(.+?)を勝利する()", t)
    if m:
        f = _race_filter(m.group(1).removesuffix("を"))
        if f is not None:
            n = int(m.group(2) or 1)
            return (lambda c: _capped(sum(r["rank"] == 1 and _race_matches(r, f)
                                          for r in c["races"]), n)), True
    m = re.fullmatch(r"(.+?)で(\d+)着以内を(\d+)回以上とる", t)
    if m and _race_filter(m.group(1)) is not None:
        f, place, n = _race_filter(m.group(1)), int(m.group(2)), int(m.group(3))
        return (lambda c: _capped(sum(r["rank"] <= place and _race_matches(r, f)
                                      for r in c["races"]), n)), True
    m = re.fullmatch(r"(.+?)で(\d+)着を(\d+)回以上とる", t)
    if m and _race_filter(m.group(1)) is not None:
        f, place, n = _race_filter(m.group(1)), int(m.group(2)), int(m.group(3))
        return (lambda c: _capped(sum(r["rank"] == place and _race_matches(r, f)
                                      for r in c["races"]), n)), True

    # --- the career's own tallies ---
    for pattern, key in ((r"育成ウマ娘とのお出かけを(\d+)回以上行う", "outings"),
                         (r"友人タイプまたはグループタイプとのお出かけを(\d+)回以上行う", "pal_outings"),
                         (r"合宿中に「お休み＆お出かけ」を(\d+)回以上行う", "camp_rests"),
                         (r"(\d+)回以上お休みする", "rests"),
                         (r"やる気が上がる育成イベントを(\d+)回以上発生させる", "motivation_ups")):
        m = re.fullmatch(pattern, t)
        if m:
            n = int(m.group(1))
            return (lambda c, key=key: _capped(c["tally"].get(key, 0), n)), True
    m = re.fullmatch(r"トレーニングに\d+度も失敗しない", t)
    if m:
        return (lambda c: (int(c["failures"] == 0), 1)), True
    m = re.fullmatch(r"育成中に(\d+)回以上「(.+)」になる", t)
    if m and _condition_ids_named(m.group(2)):
        n, name = int(m.group(1)), m.group(2)
        return (lambda c: _capped(c["tally"].get("onsets", {}).get(name, 0), n)), True
    m = re.fullmatch(r"「(.+)」を持つ状態で育成を完了する", t)
    if m and _condition_ids_named(m.group(1)):
        ids = _condition_ids_named(m.group(1))
        return (lambda c: (int(bool(ids & c["effects"])), 1)), True

    # --- events: fired counts; a named outcome is taken as the event itself ---
    m = re.fullmatch(r"育成イベント((?:「[^」]+」)+)(?:のいずれか)?(.*)", t)
    if m:
        ids = frozenset().union(*(_event_ids(x) for x in re.findall(r"「([^」]+)」", m.group(1))))
        times = re.fullmatch(r"を(\d+)回以上(?:目撃|発生させ)る", m.group(2))
        n = int(times.group(1)) if times else 1
        return (lambda c: _capped(sum(1 for s in c["fired"] if s in ids), n)), bool(ids)

    # --- succession (listed only when the card is owned at 3 stars+) ---
    if re.fullmatch(r"育成開始時に★3以上の育成ウマ娘.+を解放している", t):
        return (lambda c: (1, 1)), True
    if t == "育成開始時に継承してヒントを獲得している":
        return (lambda c: (int(c["base_group"] in c["start_tip_groups"]), 1)), True

    # --- Ramen (scenario 14) Jamborees ---
    if t == "すべてのラーメン・ジャンボリーを大盛況以上で完了する":
        return (lambda c: (int(len([r for r in c["ramen"] if r["result_state"] >= 2]) >= 3), 1)), True
    if t == "超ラーメン・ジャンボリー極を大盛況以上で完了する":
        return (lambda c: (int(any(r["check_point_type"] == 3 and r["result_state"] >= 2
                                   for r in c["ramen"])), 1)), True

    # --- Onsen (scenario 12) bathing parties: いい湯 = result_type 2 (Good) ---
    if t == "すべての湯浴み会をいい湯以上で完了する":
        return (lambda c: (int(len([r for r in c["onsen"] if r["result_type"] >= 2]) >= 3), 1)), True
    if t == "第3回湯浴み会をいい湯以上で完了する":
        return (lambda c: (int(any(r["schedule_id"] == 3 and r["result_type"] >= 2
                                   for r in c["onsen"])), 1)), True

    # --- Beyond Dreams (scenario 13) Reflections: Excellent! = result_type 2 ---
    if t == "すべての振り返りをExcellent!で完了する":
        return (lambda c: (int(len([r for r in c["breeders"] if r["result_type"] >= 2]) >= 5), 1)), True
    if t == "第5回振り返りをExcellent!で完了する":
        return (lambda c: (int(any(r["schedule_id"] == 5 and r["result_type"] >= 2
                                   for r in c["breeders"])), 1)), True

    # --- Design Your Island (scenario 11) evaluations: 大好評 = result_state 2 ---
    if t == "すべてのトレセン島評価会を大好評で完了する":
        return (lambda c: (int(len([r for r in c["pioneer"] if r["result_state"] >= 2]) >= 5), 1)), True
    if t == "最終評価会を大好評で完了する":
        return (lambda c: (int(any(r["check_point_type"] == 5 and r["result_state"] >= 2
                                   for r in c["pioneer"])), 1)), True

    # --- Run! Mecha Umamusume (scenario 9) Upgrade Exams: S評価 = result_type 3 ---
    if t == "すべてのUpgradeExamをS評価で完了する":
        return (lambda c: (int(len([r for r in c["mecha"] if r["result_type"] >= 3]) >= 5), 1)), True
    if t == "第5回UpgradeExamをS評価で完了する":
        return (lambda c: (int(any(r["schedule_id"] == 5 and r["result_type"] >= 3
                                   for r in c["mecha"])), 1)), True

    # --- Project L'Arc (scenario 6): the scenario's alternative conditions
    # (skill_up_scenario_condition, text 326). Expectation is served in tenths
    # of a percent, so 100 % is 1000 (U1: 60302 at 7/100 with the rate at 73).
    m = re.fullmatch(r"期待度(\d+)[％%]以上になる", t)
    if m:
        n = int(m.group(1))
        return (lambda c: _capped(int(c["arc"].get("rate") or 0) // 10, n)), True
    m = re.fullmatch(r"海外適性Lvの合計が(\d+)以上になる", t)
    if m:
        n = int(m.group(1))
        return (lambda c: _capped(int(c["arc"].get("levels") or 0), n)), True

    return (lambda c: (1, 1)), False


@functools.lru_cache(maxsize=None)
def _compiled(condition_id: int):
    return _parse(_jp_text(290, condition_id))


# Scenarios whose real wire shows these rows: L'Arc (U1, 60301 / 60302). Beyond
# Dreams has six rows in master too, but no capture shows them on its wire.
_SCENARIO_ROWS_ON_WIRE = frozenset({6})


@functools.lru_cache(maxsize=None)
def _compiled_scenario(row_id: int):
    return _parse(_jp_text(326, row_id))


def _scenario_rows(chara_info: dict, ctx: dict) -> list[dict]:
    """skill_up_scenario_condition (L'Arc, Beyond Dreams): the scenario's
    alternative conditions for each evolution rank the card reaches, listed
    once per rank (U1: 60301 / 60302 beside the card's rank-3 rows). Each rank
    is one group (num 101) of two options; meeting either evolves the card's
    skill of that rank in place of its own conditions (GameTora, L'Arc guide;
    docs/JP_LARC_SCENARIO.md §14, U21). Rows carry "rank" for _met."""
    scenario = int(chara_info.get("scenario_id") or 0)
    if scenario not in _SCENARIO_ROWS_ON_WIRE:
        return []
    talent = int(chara_info.get("talent_level") or 1)
    rows = []
    for r in master_data.query(
            "SELECT id, rank, condition_id FROM skill_up_scenario_condition "
            "WHERE scenario_id=? AND rank<=? ORDER BY condition_id",
            (scenario, talent)):
        fn, _ok = _compiled_scenario(int(r["id"]))
        try:
            cur, total = fn(ctx)
        except Exception:                                      # noqa: BLE001
            log.exception("scenario evolution condition %s failed", r["id"])
            cur, total = 0, 1
        rows.append({"condition_id": int(r["condition_id"]), "total_count": int(total),
                     "current_count": int(min(cur, total)), "rank": int(r["rank"])})
    return rows


def unparsed() -> list[tuple[int, str]]:
    """Every condition the parser cannot read (counted as met)."""
    out = []
    for r in master_data.query("SELECT id FROM skill_upgrade_condition ORDER BY id"):
        if not _compiled(r["id"])[1]:
            out.append((r["id"], _jp_text(290, r["id"])))
    return out


# -------------------------------------------------------------- evaluation --

def _tracker(full_state: dict) -> dict:
    return full_state.setdefault(KEY, {"tally": {}, "start_tip_groups": None,
                                       "effects_seen": []})


def _context(chara_info: dict, career_data: dict, full_state: dict) -> dict:
    races = []
    for e in career_data.get("race_history") or ():
        info = _race(e.get("program_id"))
        if info is None:
            continue
        races.append({"info": info, "instance": info["instance_id"],
                      "rank": int(e.get("result_rank") or 99),
                      "year": epithets._year_index(e.get("turn")),
                      "style": e.get("running_style"),
                      "popularity": e.get("popularity"),
                      "ground": e.get("ground_condition")})
    disabled = set(chara_info.get("disable_skill_id_array") or ())
    tracker = _tracker(full_state)
    start_groups = tracker.get("start_tip_groups")
    if start_groups is None:
        start_groups = [t.get("group_id") for t in chara_info.get("skill_tips_array") or ()]
    try:
        snap = scenarios.for_chara(chara_info).snapshot(full_state) or {}
    except Exception:                                          # noqa: BLE001
        snap = {}
    return {"ci": chara_info, "races": races,
            "skills": [s.get("skill_id") for s in chara_info.get("skill_array") or ()
                       if s.get("skill_id") not in disabled],
            "effects": set(chara_info.get("chara_effect_id_array") or ()),
            "fired": list(full_state.get(event_engine.FIRED_EVENTS_KEY) or ()),
            "failures": int(((career_data.get(smt.TRAINING_TALLY_KEY) or {})
                             .get("failures")) or 0),
            "tally": tracker.get("tally") or {},
            "start_tip_groups": set(start_groups),
            "ramen": list(snap.get("ramen_results") or ()),
            "onsen": list(snap.get("onsen_results") or ()),
            "breeders": list(snap.get("breeders_reviews") or ()),
            "pioneer": list(snap.get("pioneer_results") or ()),
            "mecha": list(snap.get("mecha_results") or ()),
            "arc": {"rate": snap.get("arc_rate"), "levels": snap.get("arc_level_sum")},
            "base_group": 0}


def _progress(evo: dict, ctx: dict) -> list[dict]:
    ctx["base_group"] = _skill_row(evo["base_skill_id"])["group_id"]
    rows = []
    for cond in evo["conditions"]:
        fn, _ok = _compiled(cond["id"])
        try:
            cur, total = fn(ctx)
        except Exception:                                      # noqa: BLE001
            log.exception("skill evolution condition %s failed", cond["id"])
            cur, total = 0, 1
        rows.append({"condition_id": cond["id"], "total_count": int(total),
                     "current_count": int(min(cur, total))})
    return rows


def _met(evo: dict, rows: list[dict], scenario_rows=()) -> bool:
    """The card's own groups all met, or (a card evolution only) any of the
    scenario's alternative options for the evolution's rank."""
    if evo["wire_type"] == 1 and any(r["rank"] == evo.get("rank") and r["current_count"] >= r["total_count"]
                                     for r in scenario_rows):
        return True
    by_id = {r["condition_id"]: r for r in rows}
    groups: dict = {}
    for cond in evo["conditions"]:
        r = by_id[cond["id"]]
        groups.setdefault(cond["num"], []).append(r["current_count"] >= r["total_count"])
    return all(any(g) for g in groups.values())


def upgrade_info(chara_info: dict, career_data: dict, full_state: dict) -> list[dict]:
    ctx = _context(chara_info, career_data, full_state)
    rows = []
    for evo in _evolutions(chara_info, full_state):
        rows += _progress(evo, ctx)
    seen = {r["condition_id"] for r in rows}
    rows += [{k: v for k, v in r.items() if k != "rank"}
             for r in _scenario_rows(chara_info, ctx) if r["condition_id"] not in seen]
    return sorted(rows, key=lambda r: r["condition_id"])


# --------------------------------------------------------------- applying --

def _apply_picks(viewer_id, picks: list) -> None:
    """Swap each picked evolution's base skill for the evolved one on the
    persisted career, so finish builds the veteran with it."""
    full_state = state_store.get_state(viewer_id) or {}
    career = (full_state.get(smt.STATE_KEY) or {}).get("data") or {}
    ci = career.get("chara_info")
    if not isinstance(ci, dict) or not picks:
        return
    ctx = _context(ci, career, full_state)
    evos = {(e["wire_type"], e["skill_id"]): e for e in _evolutions(ci, full_state)}
    scenario_rows = _scenario_rows(ci, ctx)
    skills = ci.setdefault("skill_array", [])
    disabled = ci.setdefault("disable_skill_id_array", [])
    for pick in picks:
        key = (int(pick.get("upgrade_type") or 0), int(pick.get("skill_id") or 0))
        evo = evos.get(key)
        if evo is None:
            log.warning("skill evolution %s refused: not offered to this career", key)
            continue
        owned = next((s for s in skills if s.get("skill_id") == evo["base_skill_id"]), None)
        if owned is None:
            log.warning("skill evolution %s refused: base skill %s not learned",
                        key, evo["base_skill_id"])
            continue
        if not _met(evo, _progress(evo, ctx), scenario_rows):
            log.warning("skill evolution %s refused: conditions not met", key)
            continue
        skills.remove(owned)
        skills.append({"skill_id": evo["skill_id"], "level": owned.get("level") or 1})
        disabled.append(evo["base_skill_id"])
        log.info("skill evolution: %s -> %s", evo["base_skill_id"], evo["skill_id"])
    unique = [s for s in skills if 100000 <= (s.get("skill_id") or 0) < 200000]
    rest = sorted((s for s in skills if s not in unique), key=lambda s: s.get("skill_id") or 0)
    ci["skill_array"] = unique + rest
    ci["disable_skill_id_array"] = sorted(set(disabled))
    state_store.save_state(viewer_id, full_state)


# ------------------------------------------------------------- the hooks --

def _is_career(endpoint: str) -> bool:
    return endpoint.startswith("single_mode") and "/" in endpoint


def _action(endpoint: str) -> str:
    return endpoint.rsplit("/", 1)[-1]


def before(endpoint: str, payload: dict):
    """Runs before the handler: picks applied on factor_select; the trainee's
    motivation and conditions noted for after()."""
    if not _is_career(endpoint) or not available():
        return None
    viewer_id = payload.get("viewer_id")
    if _action(endpoint) == "factor_select":
        try:
            _apply_picks(viewer_id, list(payload.get("gain_skill_upgrade_info_array") or ()))
        except Exception:                                      # noqa: BLE001
            log.exception("skill evolution: applying picks failed")
        return None
    ci = (((state_store.get_state(viewer_id) or {}).get(smt.STATE_KEY) or {})
          .get("data") or {}).get("chara_info") or {}
    return {"motivation": ci.get("motivation")}


def _chara_infos(data):
    """Every chara_info in a reply: top level and one *_common map down."""
    if not isinstance(data, dict):
        return
    if isinstance(data.get("chara_info"), dict):
        yield data["chara_info"]
    for k, v in data.items():
        if k.endswith("_common") and isinstance(v, dict) and isinstance(v.get("chara_info"), dict):
            yield v["chara_info"]


def _tally(endpoint: str, payload: dict, data: dict, full_state: dict, noted) -> None:
    tracker = _tracker(full_state)
    tally = tracker.setdefault("tally", {})
    action = _action(endpoint)
    if action == "exec_command":
        ctype = payload.get("command_type")
        cid = payload.get("command_id")
        group = payload.get("command_group_id")
        camp = group == _CAMP_GROUP or cid == _CAMP_GROUP or (
            (group in _RECREATION_GROUPS or ctype == _OUTING_COMMAND_TYPE)
            and smt._is_camp_turn(payload.get("current_turn")))
        if camp:
            tally["camp_rests"] = tally.get("camp_rests", 0) + 1
            tally["rests"] = tally.get("rests", 0) + 1
        elif cid == _REST_COMMAND_ID or ctype == _REST_COMMAND_TYPE:
            tally["rests"] = tally.get("rests", 0) + 1
        elif group == _PAL_OUTING_GROUP:
            tally["pal_outings"] = tally.get("pal_outings", 0) + 1
        elif group in _RECREATION_GROUPS or ctype == _OUTING_COMMAND_TYPE:
            tally["outings"] = tally.get("outings", 0) + 1
    ci = next(_chara_infos(data), None)
    if ci is None:
        return
    if action == "check_event" and noted and noted.get("motivation") is not None:
        if (ci.get("motivation") or 0) > (noted["motivation"] or 0):
            tally["motivation_ups"] = tally.get("motivation_ups", 0) + 1
    now = set(ci.get("chara_effect_id_array") or ())
    seen = set(tracker.get("effects_seen") or ())
    for cid in now - seen:
        name = _jp_text(142, cid)
        if name:
            onsets = tally.setdefault("onsets", {})
            onsets[name] = onsets.get(name, 0) + 1
    tracker["effects_seen"] = sorted(now)


def after(endpoint: str, payload: dict, resp: dict, noted) -> None:
    """Runs on the finished reply: tallies this request, then stamps every
    chara_info with the career's skill_upgrade_info_array."""
    if not _is_career(endpoint) or not available():
        return
    if (resp.get("data_headers") or {}).get("result_code", 1) != 1:
        return
    data = resp.get("data")
    if not isinstance(data, dict):
        return
    viewer_id = payload.get("viewer_id")
    full_state = state_store.get_state(viewer_id) or {}
    career = (full_state.get(smt.STATE_KEY) or {}).get("data")
    if _action(endpoint) == "start":
        full_state.pop(KEY, None)
    if not isinstance(career, dict) or not isinstance(career.get("chara_info"), dict):
        # No career (finish, give-up): nothing to evolve towards.
        for ci in _chara_infos(data):
            ci["skill_upgrade_info_array"] = []
        return
    try:
        tracker = _tracker(full_state)
        if tracker.get("start_tip_groups") is None:
            tracker["start_tip_groups"] = sorted(
                {t.get("group_id") for t in career["chara_info"].get("skill_tips_array") or ()})
        _tally(endpoint, payload, data, full_state, noted)
        state_store.save_state(viewer_id, full_state)
        for ci in _chara_infos(data):
            ci["skill_upgrade_info_array"] = upgrade_info(ci, career, full_state)
    except Exception:                                          # noqa: BLE001
        log.exception("skill evolution: stamping %s failed", endpoint)
