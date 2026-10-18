"""Optional, revisioned support cards. Stock requests never open a custom master.

Definitions live separately from viewer saves and the downloaded game master.
The HTTP adapter establishes a request-local pack capability; game handlers
continue using their usual master queries. All published artifacts are immutable.
"""
from __future__ import annotations

import base64
import contextvars
import logging
import copy
import functools
import hashlib
import json
import secrets
import sqlite3
import struct
import threading
import time
import zlib
from contextlib import contextmanager
from pathlib import Path

from . import region

PROTOCOL = 1
log = logging.getLogger("uma-server")
CURRENT_PACK = contextvars.ContextVar("custom_support_pack", default="")
_lock = threading.RLock()
_connections = threading.local()
_capabilities: dict[str, dict] = {}
_challenges: dict[str, dict] = {}
LEVEL_COLUMNS = ["init", *[f"limit_lv{i}" for i in range(5, 51, 5)]]
EFFECTS = {
    1: "Friendship bonus", 2: "Mood effect", 3: "Speed bonus", 4: "Stamina bonus",
    5: "Power bonus", 6: "Guts bonus", 7: "Wisdom bonus", 8: "Training bonus",
    9: "Initial speed", 10: "Initial stamina", 11: "Initial power", 12: "Initial guts",
    13: "Initial wisdom", 14: "Initial bond", 15: "Race bonus", 16: "Fan bonus",
    17: "Hint level", 18: "Hint frequency", 19: "Specialty priority",
    25: "Event recovery", 26: "Event effect", 27: "Failure rate reduction",
    28: "Energy cost reduction", 30: "Skill point bonus", 31: "Wisdom friendship recovery",
}
COMMANDS = {"speed": 101, "stamina": 105, "power": 102, "guts": 103, "wiz": 106}


def root() -> Path:
    return region.data_dir() / "custom_support"


def _db(write=False):
    p = root() / "definitions.sqlite3"
    if not write and not p.exists():
        return None
    if write:
        p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p) if write else p.as_uri() + "?mode=ro", uri=not write)
    c.row_factory = sqlite3.Row
    if write:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS cards(id INTEGER PRIMARY KEY, definition TEXT NOT NULL,
                version INTEGER NOT NULL, retired INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS revisions(digest TEXT PRIMARY KEY, manifest TEXT NOT NULL,
                created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at REAL NOT NULL,
                action TEXT NOT NULL, card_id INTEGER, detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS plugin_status(instance TEXT PRIMARY KEY,
                viewer TEXT NOT NULL, digest TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS capabilities(token_hash TEXT PRIMARY KEY, digest TEXT NOT NULL,
                instance TEXT NOT NULL, expires REAL NOT NULL, region TEXT NOT NULL, viewer TEXT NOT NULL);
        """)
    return c



def _token_hash(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


def _save_capability(db, token, c):
    db.execute("INSERT OR REPLACE INTO capabilities VALUES(?,?,?,?,?,?)",
               (_token_hash(token), c["digest"], c["instance"], c["expires"], c["region"], c["viewer"]))


def _capability(token):
    """Plugin readiness by token; persisted so a server reload keeps live clients' careers playable."""
    token = str(token)
    c = _capabilities.get(token)
    if c is None and token:
        db = _db()
        if db is not None:
            try:
                r = db.execute("SELECT * FROM capabilities WHERE token_hash=?", (_token_hash(token),)).fetchone()
            except sqlite3.OperationalError:
                r = None
            finally:
                db.close()
            if r and r["expires"] > time.time():
                c = _capabilities[token] = {k: r[k] for k in ("digest", "instance", "expires", "region", "viewer")}
    return c


@contextmanager
def _writing():
    c = _db(True)
    try:
        with c:
            yield c
    finally:
        c.close()


def _audit(c, action, card_id=None, detail=None):
    c.execute("INSERT INTO audit(at,action,card_id,detail) VALUES(?,?,?,?)",
              (time.time(), action, card_id, json.dumps(detail or {}, ensure_ascii=False)))


def is_enabled() -> bool:
    c = _db()
    if c is None:
        return False
    try:
        r = c.execute("SELECT value FROM settings WHERE key='enabled'").fetchone()
        return bool(r and r[0] == "true")
    finally:
        c.close()


def status() -> dict:
    c = _db()
    if c is None:
        return {"enabled": False, "digest": "", "cards": [], "sessions": [], "revisions": []}
    try:
        settings = dict(c.execute("SELECT key,value FROM settings"))
        cards = [dict(json.loads(r["definition"]), version=r["version"], retired=bool(r["retired"]))
                 for r in c.execute("SELECT * FROM cards ORDER BY id DESC")]
        sessions = [dict(r) for r in c.execute("SELECT viewer,digest,expires FROM plugin_status WHERE expires>?", (time.time(),))]
        revisions = [{"digest": r["digest"], "created": r["created"],
                      "cards": len(json.loads(r["manifest"])["cards"])}
                     for r in c.execute("SELECT * FROM revisions ORDER BY created DESC")]
        return {"enabled": settings.get("enabled") == "true", "digest": settings.get("active", ""),
                "cards": cards, "sessions": sessions, "revisions": revisions}
    finally:
        c.close()


def manifest(digest: str | None = None) -> dict | None:
    c = _db()
    if c is None:
        return None
    try:
        if digest is None:
            r = c.execute("SELECT value FROM settings WHERE key='active'").fetchone()
            digest = r[0] if r else ""
        return _immutable_manifest(str(root() / "definitions.sqlite3"), digest)
    finally:
        c.close()


@functools.lru_cache(maxsize=64)
def _immutable_manifest(path, digest):
    c = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)
    try:
        r = c.execute("SELECT manifest FROM revisions WHERE digest=?", (digest,)).fetchone()
        # Do not cache missing revisions; callers only pass committed digests.
        return json.loads(r[0]) if r else None
    finally:
        c.close()


def known_ids() -> set[int]:
    c = _db()
    if c is None:
        return set()
    try:
        return {r[0] for r in c.execute("SELECT id FROM cards")}
    finally:
        c.close()


def definitions() -> dict[int, dict]:
    m = manifest(CURRENT_PACK.get()) if CURRENT_PACK.get() else None
    return {int(d["id"]): d for d in m["cards"]} if m else {}


def card(sid) -> dict | None:
    try:
        return definitions().get(int(sid))
    except (TypeError, ValueError):
        return None


def event_donor(sid) -> int:
    d = card(sid)
    return int(d["event_donor"]) if d else int(sid)


def digest_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


@contextmanager
def use_pack(digest: str):
    t = CURRENT_PACK.set(digest)
    try:
        yield
    finally:
        CURRENT_PACK.reset(t)


def connection():
    digest = CURRENT_PACK.get()
    if not digest:
        return None
    key = (str(root()), region.CURRENT_REGION.get(), digest)
    pool = getattr(_connections, "pool", None)
    if pool is None:
        pool = _connections.pool = {}
    if key not in pool:
        m = manifest(digest)
        if not m:
            raise ValueError("Custom support revision is unavailable")
        p = root() / "packs" / digest / "master.mdb"
        c = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, check_same_thread=False)
        c.row_factory = sqlite3.Row
        if region.PROCESS_REGION == "jp":
            from . import master_data
            master_data._overlay_english_text(c)
        pool[key] = c
    return pool[key]


def close_connections():
    """Release this thread's private master handles (tests and worker teardown)."""
    for c in getattr(_connections, "pool", {}).values():
        c.close()
    _connections.pool = {}


def template(sid: int) -> dict:
    from . import master_data as M
    with use_pack(""):
        r = M.query_one("SELECT * FROM support_card_data WHERE id=?", (sid,))
        if not r or r["support_card_type"] != 1:
            raise ValueError("Choose an existing normal training support card")
        def txt(cat):
            row = M.query_one("SELECT text FROM main.text_data WHERE category=? AND [index]=?", (cat, sid))
            return row[0] if row else ""
        effects = [dict(x) for x in M.query("SELECT * FROM support_card_effect_table WHERE id=?", (r["effect_table_id"],))]
        hints = [dict(x) for x in M.query("SELECT * FROM single_mode_hint_gain WHERE support_card_id=? ORDER BY hint_group,id", (sid,))]
        unique = M.query_one("SELECT * FROM support_card_unique_effect WHERE id=?", (sid,))
        return {"id": 0, "template": sid, "chara_id": r["chara_id"], "rarity": r["rarity"],
                "type": next((k for k, v in COMMANDS.items() if v == r["command_id"]), "speed"),
                "name": txt(77), "title": txt(76).strip("[]"), "description": txt(88),
                "event_donor": sid, "art_donor": sid, "art": "",
                "effects": [{"type": x["type"], "values": [x.get(k, -1) for k in LEVEL_COLUMNS]}
                            for x in effects if x["type"] in EFFECTS],
                "hints": [{k: x.get(k, 0) for k in ("hint_group", "hint_gain_type", "hint_value_1", "hint_value_2")}
                          for x in hints], "unique": dict(unique) if unique else None}


def _int(v, lo, hi, label):
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise ValueError(f"{label} must be an integer from {lo} to {hi}")
    return v


def validate(d: dict, require_id=False) -> dict:
    from . import master_data as M
    if not isinstance(d, dict):
        raise ValueError("A card definition is required")
    d = copy.deepcopy(d)
    d.pop("version", None)
    d.pop("retired", None)
    with use_pack(""):
        for key in ("template", "event_donor", "art_donor"):
            _int(d.get(key), 1, 99999, key)
            r = M.query_one("SELECT * FROM support_card_data WHERE id=?", (d[key],))
            if not r or r["support_card_type"] != 1:
                raise ValueError(f"{key}: select an existing normal card in this region")
            if key == "event_donor" and r["chara_id"] != d.get("chara_id"):
                raise ValueError("The event donor must feature the same character")
        _int(d.get("chara_id"), 1, 99999, "Character")
        if not M.query_one("SELECT id FROM chara_data WHERE id=?", (d["chara_id"],)):
            raise ValueError("Character is not in this region's master")
        _int(d.get("rarity"), 1, 3, "Rarity")
        if d.get("type") not in COMMANDS:
            raise ValueError("Choose a training type")
        for key, limit in (("name", 100), ("title", 150), ("description", 2000)):
            value = d.get(key, "")
            if not isinstance(value, str) or len(value) > limit or "\0" in value:
                raise ValueError(f"{key}: maximum {limit} characters")
            d[key] = value.strip()
        if not d["name"] or not d["title"]:
            raise ValueError("Name and title are required")
        sid = _int(d.get("id", 0), 0, 99999, "Card ID")
        if require_id and not sid:
            raise ValueError("Save the draft to allocate its ID first")
        if sid and (sid // 10000 != d["rarity"] or not 9000 <= sid % 10000 <= 9999):
            raise ValueError("Custom IDs use the rarity's reserved 9000–9999 suffix")
        if sid and M.query_one("SELECT id FROM support_card_data WHERE id=?", (sid,)):
            raise ValueError("Card ID collides with the official master")
        effects = d.get("effects")
        if not isinstance(effects, list) or not effects or len(effects) > len(EFFECTS):
            raise ValueError("Invalid support effects")
        seen = set()
        for e in effects:
            if e.get("type") not in EFFECTS or e["type"] in seen:
                raise ValueError("Effects must use distinct supported types")
            seen.add(e["type"])
            values = e.get("values")
            if not isinstance(values, list) or len(values) != 11:
                raise ValueError("Each effect needs 11 level breakpoints")
            for v in values:
                _int(v, -1, {14: 100, 17: 5, 27: 100, 28: 100}.get(e["type"], 10000), EFFECTS[e["type"]])
            if all(v == -1 for v in values):
                raise ValueError("An effect needs at least one defined breakpoint")
        hints = d.get("hints", [])
        if not isinstance(hints, list) or len(hints) > 100:
            raise ValueError("Too many hint rows")
        skills, kinds = set(), {}
        for h in hints:
            g = _int(h.get("hint_group"), 1, 1000, "Hint group")
            kind = _int(h.get("hint_gain_type"), 0, 1, "Hint kind")
            if g in kinds and (kinds[g] != kind or kind == 0):
                raise ValueError("A skill hint has one row; stat rows may share a group")
            kinds[g] = kind
            val = _int(h.get("hint_value_1"), 1, 2147483647, "Hint target")
            _int(h.get("hint_value_2", 0), 0, 1000, "Hint amount")
            if kind == 0:
                if val in skills or not M.query_one("SELECT id FROM skill_data WHERE id=?", (val,)):
                    raise ValueError("Hints must use distinct existing skills in this region")
                skills.add(val)
            elif val not in (1, 2, 3, 4, 5, 30):
                raise ValueError("Stat hints target speed, stamina, power, guts, wisdom or skill points")
        if len(skills) > 20:
            raise ValueError("The displayed skill set supports up to 20 skills")
        d["hints"] = hints
        # Unique effects are cloned from the template, not arbitrary unsupported conditions.
        original = M.query_one("SELECT * FROM support_card_unique_effect WHERE id=?", (d["template"],))
        unique = d.get("unique")
        if unique is not None:
            if not original:
                raise ValueError("This template has no unique effect to inherit")
            expected = dict(original)
            for k, v in expected.items():
                if k != "id" and unique.get(k) != v:
                    raise ValueError("Unique effects currently inherit their template's verified behavior")
            d["unique"] = expected
        art = d.get("art", "")
        if not isinstance(art, str):
            raise ValueError("Invalid artwork")
        if art:
            validate_png(art)
        d["art"] = art
        for key in ("icon_focus", "card_focus"):
            focus = d.get(key)
            if focus is None:
                continue
            if not isinstance(focus, dict):
                raise ValueError("Invalid crop")
            # Per-mille of the art: top-left corner, and size as a share of
            # the largest crop of that shape that fits.
            d[key] = {"x": _int(focus.get("x"), 0, 1000, "Crop"),
                      "y": _int(focus.get("y"), 0, 1000, "Crop"),
                      "size": _int(focus.get("size"), 100, 1000, "Crop")}
    return d


# Stock support_thumb / support_card_s textures carry their rarity frame (and
# the icon its rarity badge) baked in; the UI draws nothing over them. These
# overlays come from tools/gen_support_frames.py. Slot numbers match the
# plugin's ResourcePath hooks: 2 = thumbnail, 3 = small icon.
FRAMES_DIR = Path(__file__).resolve().parent.parent / "data" / "support_frames"
FRAMED_SLOTS = {2: "thumb", 3: "s"}


# Crop shapes (width:height). The deck/list card shows its art area at 3:4
# (measured on screen: 0.742) although the texture stores it near-square, so
# stock thumbnails hold 3:4 art squeezed sideways; ours is cropped 3:4 and
# squeezed the same way.
CROP_ASPECT = {"icon_focus": (1, 1), "card_focus": (3, 4)}


def crop_box(width, height, focus, key):
    """The part of the art a framed slot shows, in pixels. Mirrors the
    studio's crop editor (custom-support.js), defaults included."""
    aw, ah = CROP_ASPECT[key]
    # Largest crop of this shape that fits.
    full_w = min(width, height * aw // ah)
    full_h = full_w * ah // aw
    if focus:
        cw, ch = max(1, full_w * focus["size"] // 1000), max(1, full_h * focus["size"] // 1000)
        x, y = width * focus["x"] // 1000, height * focus["y"] // 1000
    elif key == "icon_focus":
        # Upper middle, where a portrait's face usually sits.
        cw, ch = full_w * 6 // 10, full_h * 6 // 10
        x, y = (width - cw) // 2, height // 20
    else:
        cw, ch = full_w, full_h
        x, y = (width - cw) // 2, 0
    x, y = max(0, min(x, width - cw)), max(0, min(y, height - ch))
    return x, y, x + cw, y + ch


def framed_slot_art(png: bytes, rarity: int, slot: int, focus=None) -> bytes | None:
    """`focus` is the draft: its icon_focus / card_focus pick the crop."""
    """Custom art laid into a stock card's frame for one framed slot."""
    import io
    from PIL import Image
    name = FRAMED_SLOTS[slot]
    frame_path = FRAMES_DIR / f"{name}_{rarity}.png"
    if not frame_path.exists():
        return None
    frame = Image.open(frame_path).convert("RGBA")
    mask = Image.open(FRAMES_DIR / f"{name}_{rarity}_mask.png").convert("L")
    art = Image.open(io.BytesIO(png)).convert("RGBA")
    key = "icon_focus" if slot == 3 else "card_focus"
    art = art.crop(crop_box(art.width, art.height, (focus or {}).get(key), key))
    box = mask.getbbox() or (0, 0) + frame.size
    # Stretched, not fitted: the crop already has the shape the game shows.
    fitted = art.resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
    layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    layer.paste(fitted, box[:2])
    layer.putalpha(mask)
    layer.alpha_composite(frame)
    out = io.BytesIO()
    layer.save(out, "PNG")
    return out.getvalue()


def validate_png(data: str) -> bytes:
    try:
        raw = base64.b64decode(data.removeprefix("data:image/png;base64,"), validate=True)
    except (ValueError, TypeError) as e:
        raise ValueError("Upload a PNG image") from e
    if len(raw) > 8 * 1024 * 1024 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Artwork must be a PNG smaller than 8 MB")
    # Verify chunk boundaries and CRCs; bound dimensions before Unity decodes it.
    pos, dims, end = 8, None, False
    while pos + 12 <= len(raw):
        n = struct.unpack_from(">I", raw, pos)[0]
        if pos + n + 12 > len(raw):
            raise ValueError("Truncated PNG")
        tag, payload = raw[pos + 4:pos + 8], raw[pos + 8:pos + 8 + n]
        if zlib.crc32(tag + payload) & 0xffffffff != struct.unpack_from(">I", raw, pos + 8 + n)[0]:
            raise ValueError("Invalid PNG checksum")
        if pos == 8:
            if tag != b"IHDR" or n != 13:
                raise ValueError("Invalid PNG header")
            dims = struct.unpack_from(">II", payload)
            if not all(32 <= v <= 4096 for v in dims):
                raise ValueError("Artwork dimensions must be between 32 and 4096 pixels")
        pos += n + 12
        if tag == b"IEND":
            end = n == 0 and pos == len(raw)
            break
    if not dims or not end:
        raise ValueError("Incomplete PNG")
    return raw


def save_draft(d, version=0):
    d = validate(d)
    with _lock, _writing() as c:
        sid = d["id"]
        if not sid:
            lo = d["rarity"] * 10000 + 9000
            used = {r[0] for r in c.execute("SELECT id FROM cards")}
            from . import master_data as M
            with use_pack(""):
                used |= {r[0] for r in M.query("SELECT id FROM support_card_data WHERE id>=? AND id<?", (lo, lo + 1000))}
            sid = next((i for i in range(lo, lo + 1000) if i not in used), None)
            if sid is None:
                raise ValueError("Reserved ID range is full")
            d["id"] = sid
        old = c.execute("SELECT version,retired FROM cards WHERE id=?", (sid,)).fetchone()
        if (old and old["version"] != version) or (not old and version):
            raise ValueError("This draft changed in another editor. Reload before saving.")
        if old and old["retired"]:
            raise ValueError("Retired IDs cannot be reused; duplicate the card instead")
        c.execute("INSERT INTO cards(id,definition,version) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET definition=excluded.definition,version=excluded.version",
                  (sid, json.dumps(d, ensure_ascii=False), version + 1))
        _audit(c, "save", sid, {"version": version + 1})
    return dict(d, version=version + 1, retired=False)


def retire(sid):
    with _lock, _writing() as c:
        if not c.execute("UPDATE cards SET retired=1,version=version+1 WHERE id=?", (sid,)).rowcount:
            raise ValueError("Card not found")
        _audit(c, "retire", sid)


def set_enabled(on):
    with _lock, _writing() as c:
        if on and not manifest():
            raise ValueError("Publish a valid pack first")
        c.execute("INSERT OR REPLACE INTO settings VALUES('enabled',?)", ("true" if on else "false",))
        _audit(c, "enable" if on else "disable")


def _insert(c, table, row):
    cols = [r[1] for r in c.execute(f'PRAGMA table_info("{table}")')]
    if set(row) - set(cols):
        raise ValueError(f"Unsupported {table} schema")
    names = list(row)
    quoted = ",".join('"' + k + '"' for k in names)
    c.execute(f'INSERT INTO "{table}" ({quoted}) VALUES ({",".join("?" for _ in names)})', tuple(row[k] for k in names))


def _next(c, table):
    return int(c.execute(f'SELECT COALESCE(MAX(id),0)+1 FROM "{table}"').fetchone()[0])


def publish() -> dict:
    from . import master_data as M
    from . import event_schedule
    with _lock:
        s = status()
        drafts = [validate(d, True) for d in s["cards"] if not d["retired"]]
        events = event_schedule.validate(event_schedule.schedules(), M.get_connection())
        if not drafts and not events:
            raise ValueError("Save at least one active card or event schedule before publishing")
        # Retain old packs for pinned careers; activation only changes new sessions.
        base = digest_file(M.MASTER_MDB_PATH)
        encoded = json.dumps({"protocol": PROTOCOL, "region": region.CURRENT_REGION.get(),
                              "base_sha256": base, "cards": drafts, "events": events}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        directory = root() / "packs" / digest
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "master.mdb"
        tmp = directory / "master.pending"
        if not path.exists():
            tmp.unlink(missing_ok=True)
            src = sqlite3.connect(Path(M.MASTER_MDB_PATH).as_uri() + "?mode=ro", uri=True)
            dst = sqlite3.connect(tmp)
            dst.row_factory = sqlite3.Row
            try:
                src.backup(dst)
                event_schedule.apply(dst, events)
                for d in drafts:
                    row = dict(dst.execute("SELECT * FROM support_card_data WHERE id=?", (d["template"],)).fetchone())
                    if dst.execute("SELECT 1 FROM support_card_data WHERE id=?", (d["id"],)).fetchone():
                        raise ValueError("Custom card ID collides with base master")
                    effect_id = max(_next(dst, "support_card_effect_table"),
                                    dst.execute("SELECT COALESCE(MAX(effect_table_id),0)+1 FROM support_card_data").fetchone()[0])
                    skill_set_id = _next(dst, "skill_set")
                    row.update(id=d["id"], chara_id=d["chara_id"], rarity=d["rarity"],
                               effect_table_id=effect_id, unique_effect_id=d["id"] if d["unique"] else 0,
                               command_id=COMMANDS[d["type"]], skill_set_id=skill_set_id,
                               exchange_item_id=0, start_date=0)
                    if "exchange_item_num" in row:
                        row["exchange_item_num"] = 0
                    if "disp_order" in row:
                        row["disp_order"] = d["id"]
                    _insert(dst, "support_card_data", row)
                    for e in d["effects"]:
                        _insert(dst, "support_card_effect_table", dict(id=effect_id, type=e["type"], **dict(zip(LEVEL_COLUMNS, e["values"]))))
                    if d["unique"]:
                        u = dict(d["unique"], id=d["id"])
                        _insert(dst, "support_card_unique_effect", u)
                    sk = {r[1]: 0 for r in dst.execute("PRAGMA table_info(skill_set)")}
                    sk["id"] = skill_set_id
                    skills = [h["hint_value_1"] for h in d["hints"] if h["hint_gain_type"] == 0]
                    for i, skill in enumerate(skills, 1):
                        sk[f"skill_id{i}"] = skill
                        sk[f"skill_level{i}"] = 1
                    _insert(dst, "skill_set", sk)
                    hint_id = _next(dst, "single_mode_hint_gain")
                    for i, h in enumerate(d["hints"]):
                        hr = {r[1]: 0 for r in dst.execute("PRAGMA table_info(single_mode_hint_gain)")}
                        hr.update(h, id=hint_id + i, support_card_id=d["id"])
                        _insert(dst, "single_mode_hint_gain", hr)
                    for cat, text in ((75, "[" + d["title"] + "] " + d["name"]), (76, '[' + d["title"] + ']'), (77, d["name"]), (78, d["name"]), (88, d["description"])):
                        _insert(dst, "text_data", {"id": _next(dst, "text_data"), "category": cat, "index": d["id"], "text": text})
                    if d["unique"]:
                        for cat in (150, 155):
                            label = dst.execute("SELECT text FROM text_data WHERE category=? AND [index]=?", (cat, d["template"])).fetchone()
                            if label:
                                _insert(dst, "text_data", {"id": _next(dst, "text_data"), "category": cat, "index": d["id"], "text": label[0]})
                    if d["art"]:
                        (directory / f'{d["id"]}.png').write_bytes(validate_png(d["art"]))
                dst.commit()
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Generated master failed integrity validation")
            finally:
                src.close()
                dst.close()
            tmp.replace(path)
        cards = []
        for d in drafts:
            item = {k: v for k, v in d.items() if k != "art"}
            item["art_sha256"] = digest_file(directory / f'{d["id"]}.png') if d["art"] else ""
            item["slot_art"] = {}
            for slot in FRAMED_SLOTS if d["art"] else ():
                framed = framed_slot_art(validate_png(d["art"]), d["rarity"], slot, d)
                if framed:
                    (directory / f'{d["id"]}_{slot}.png').write_bytes(framed)
                    item["slot_art"][str(slot)] = digest_file(directory / f'{d["id"]}_{slot}.png')
            cards.append(item)
        m = {"protocol": PROTOCOL, "region": region.CURRENT_REGION.get(), "digest": digest,
             "base_sha256": base, "master_sha256": digest_file(path), "cards": cards,
             "events": events, "created": time.time()}
        with _writing() as c:
            c.execute("INSERT OR REPLACE INTO revisions VALUES(?,?,?)", (digest, json.dumps(m, ensure_ascii=False), time.time()))
            c.execute("INSERT OR REPLACE INTO settings VALUES('active',?)", (digest,))
            _audit(c, "publish", detail={"digest": digest, "cards": [d["id"] for d in drafts]})
        return m


def activate(digest):
    m = manifest(str(digest))
    if not m or not (root() / "packs" / m["digest"] / "master.mdb").exists():
        raise ValueError("Published pack is unavailable")
    with _lock, _writing() as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES('active',?)", (m["digest"],))
        _audit(c, "activate", detail={"digest": m["digest"]})
    return m


def history():
    c = _db()
    if c is None:
        return []
    try:
        return [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")]
    finally:
        c.close()


def bootstrap(protocol, target_region, base_sha256):
    m = manifest()
    if protocol != PROTOCOL or target_region != region.CURRENT_REGION.get() or not is_enabled() or not m:
        raise ValueError("Custom support cards are off or the plugin is incompatible")
    if not secrets.compare_digest(str(base_sha256), m["base_sha256"]):
        raise ValueError("Client and server master versions differ; custom cards remain hidden")
    with _lock:
        now = time.time()
        for k in list(_challenges):
            if _challenges[k]["expires"] < now:
                del _challenges[k]
        challenge = secrets.token_hex(32)
        _challenges[challenge] = {"digest": m["digest"], "expires": now + 300,
                                  "region": region.CURRENT_REGION.get()}
    return dict(m, challenge=challenge)


def ready(challenge, digest, master_sha256, instance):
    if not isinstance(instance, str) or not 16 <= len(instance) <= 128:
        raise ValueError("Invalid plugin instance")
    with _lock:
        c = _challenges.pop(str(challenge), None)
        if not c or c["expires"] < time.time() or c["digest"] != digest or c["region"] != region.CURRENT_REGION.get():
            raise ValueError("Plugin readiness challenge expired")
        m = manifest(digest)
        if not is_enabled() or not m or master_sha256 != m["master_sha256"]:
            raise ValueError("Plugin pack is not ready")
        now = time.time()
        for k in list(_capabilities):
            if _capabilities[k]["expires"] < now:
                del _capabilities[k]
        token = secrets.token_hex(32)
        _capabilities[token] = {"digest": digest, "instance": instance, "expires": now + 86400,
                                "region": region.CURRENT_REGION.get(), "viewer": ""}
        with _writing() as db:
            db.execute("INSERT OR REPLACE INTO plugin_status VALUES(?,?,?,?)", (instance, "", digest, now + 86400))
            db.execute("DELETE FROM capabilities WHERE expires<?", (now,))
            _save_capability(db, token, _capabilities[token])
        return {"token": token, "expires": now + 86400}


def renew(token):
    with _lock:
        c = _capability(token)
        if not c or c["expires"] < time.time() or c["region"] != region.CURRENT_REGION.get() or not is_enabled():
            raise ValueError("Restart the client to renew plugin readiness")
        c["expires"] = time.time() + 86400
        with _writing() as db:
            db.execute("UPDATE plugin_status SET expires=? WHERE instance=?", (c["expires"], c["instance"]))
            _save_capability(db, token, c)
        return {"token": token, "expires": c["expires"]}


@contextmanager
def request_context(headers, payload):
    digest = ""
    token = headers.get("x-uma-custom-support", "")
    with _lock:
        c = _capability(token)
        if c and c["expires"] > time.time() and c["region"] == region.CURRENT_REGION.get() and is_enabled():
            common = payload.get("request_common") or {}
            viewer = str(payload.get("viewer_id") or (common.get("viewer_id") if isinstance(common, dict) else "") or "")
            if c["viewer"] in ("", viewer):
                if viewer not in ("", "0", "unknown"):
                    if c["viewer"] != viewer:
                        c["viewer"] = viewer
                        with _writing() as db:
                            db.execute("UPDATE plugin_status SET viewer=? WHERE instance=?", (viewer, c["instance"]))
                            _save_capability(db, token, c)
                digest = c["digest"]
    with use_pack(digest):
        yield


def _direct_ref(node, ids):
    if not isinstance(node, dict):
        return False
    if any("support_card_id" in k and isinstance(v, int) and v in ids for k, v in node.items()):
        return True
    if node.get("item_type", node.get("item_category")) == 51 and isinstance(node.get("item_id"), int) and node["item_id"] in ids:
        return True
    if node.get("reward_type") == 51 and isinstance(node.get("reward_id"), int) and node["reward_id"] in ids:
        return True  # present box rows
    return node.get("card_type") == 2 and isinstance(node.get("card_id"), int) and node["card_id"] in ids


def _refs(node, ids, key=""):
    if isinstance(node, dict):
        if _direct_ref(node, ids):
            return True
        for k, v in node.items():
            if k in ("support_card_id", "leader_support_card_id", "rental_support_card_id") and isinstance(v, int) and v in ids:
                return True
            if _refs(v, ids, k):
                return True
    elif isinstance(node, (list, tuple)):
        if "support_card_id" in key and any(isinstance(v, int) and v in ids for v in node):
            return True
        return any(_refs(v, ids, key) for v in node)
    return False


def preflight(endpoint, payload):
    """Run inside the account lock, before any handler can mutate a save."""
    from . import state
    ids = known_ids()
    full = state.get_state(payload.get("viewer_id")) or {}
    if endpoint.startswith("single_mode") and full.get("single_mode_team") and full.get("_custom_support_pack"):
        if not (payload.get("is_force_delete") is True and endpoint.endswith("/finish")):
            if full["_custom_support_pack"] != CURRENT_PACK.get():
                return False
    if not ids:
        return True
    allowed = set(definitions())
    # Abandoning a career must always work: it only discards the run, so a
    # pack mismatch or hidden card must never trap the player inside it.
    if payload.get("is_force_delete") is True and endpoint.endswith("/finish"):
        return True
    if _refs(payload, ids - allowed):
        log.warning("custom_support: %s refused (payload references a card outside the active pack)", endpoint)
        return False
    full = state.get_state(payload.get("viewer_id")) or {}
    career = full.get("single_mode_team") or {}
    # Detect actual career storage without depending on scenario-specific key names.
    for k, v in full.items():
        if ("career" in k or "single_mode" in k) and _refs(v, ids):
            career = v
            break
    if endpoint.split("/")[0].startswith("single_mode") and _refs(career, ids - allowed):
        log.warning("custom_support: %s refused (career holds a card outside the active pack)", endpoint)
        return False
    if endpoint.split("/")[0].startswith("single_mode") and _refs(career, ids) and full.get("_custom_support_pack") != CURRENT_PACK.get():
        log.warning("custom_support: %s refused (career pinned to pack %s, active %s)", endpoint,
                    str(full.get("_custom_support_pack"))[:8], CURRENT_PACK.get()[:8])
        return False
    if endpoint == "support_card_deck/change_party" and ids - allowed:
        decks = full.get("support_card_deck_state") or []
        updates = {d.get("deck_id") for d in payload.get("support_card_deck_array", [])}
        if any(d.get("deck_id") in updates and _refs(d, ids - allowed) for d in decks):
            return False  # stock projection cannot overwrite hidden deck slots
    return True



def pin_career(endpoint, payload, response):
    # idle_single_mode/start (the auto-run start) creates a career too.
    if not CURRENT_PACK.get() or not endpoint.endswith("/start") or "single_mode" not in endpoint.split("/")[0]:
        return
    if (response.get("data_headers") or {}).get("result_code", 1) != 1:
        return
    from . import state
    full = state.get_state(payload.get("viewer_id")) or {}
    m = manifest(CURRENT_PACK.get()) or {}
    if m.get("events") or _refs(full.get("single_mode_team", {}), set(definitions())):
        full["_custom_support_pack"] = CURRENT_PACK.get()
        state.save_state(payload["viewer_id"], full)


def project(response):
    """Copy the wire view; never mutate canonical ownership or cached fixtures."""
    hidden = known_ids() - set(definitions())
    if not hidden:
        return response
    def walk(n, key=""):
        if isinstance(n, list):
            if "support_card_id" in key:
                return [0 if isinstance(x, int) and x in hidden else x for x in n]
            out = []
            for x in n:
                if _direct_ref(x, hidden):
                    continue
                if isinstance(x, dict) and key in ("summary_user_info_array", "directory_card_array") and _refs(x, hidden):
                    continue
                out.append(walk(x, key))
            return out
        if isinstance(n, dict):
            out = {}
            for k, v in n.items():
                if "support_card_id" in k and isinstance(v, int) and v in hidden:
                    out[k] = 0
                elif k in ("single_mode_chara_light", "single_mode_start_common", "single_mode_load_common") and _refs(v, hidden):
                    out[k] = None
                else:
                    out[k] = walk(v, k)
            return out
        return n
    result = walk(response)
    if _refs(result, hidden):
        from .result_codes import refuse
        refused = refuse()
        refused["data_headers"] = dict(response.get("data_headers") or {}, **refused["data_headers"])
        return refused
    return result
