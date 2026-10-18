"""Server-selected historical events, distributed in immutable private masters.

Only dates are changed. Event assets, rules and IDs must already exist in the
client's matching master. Stock clients continue to read their stock schedules.
"""
from __future__ import annotations

import json
import sqlite3
import datetime as dt

FAMILIES = {
    "training_challenge": ("training_challenge_master", "id"),
    "story_event": ("story_event_data", "story_event_id"),
}
DATES = ("notice_date", "start_date", "middle_date_01", "middle_date_02",
         "ending_date", "end_date", "start_result_date", "end_result_date")


def schedules():
    from . import custom_support as C
    c = C._db()
    if c is None:
        return []
    try:
        r = c.execute("SELECT value FROM settings WHERE key='event_schedules'").fetchone()
        return json.loads(r[0]) if r else []
    finally:
        c.close()


def validate(entries, connection):
    if not isinstance(entries, list):
        raise ValueError("Event schedules must be an array")
    out, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each event schedule must be an object")
        family = entry.get("family")
        if family not in FAMILIES or family in seen:
            raise ValueError("Select at most one event per supported family")
        seen.add(family)
        table, key = FAMILIES[family]
        eid, start, end = (entry.get(k) for k in ("event_id", "start_date", "end_date"))
        if any(type(v) is not int for v in (eid, start, end)) or eid <= 0 or not 0 < start < end < 2**32:
            raise ValueError("Event ID and UTC dates must be positive integers, start < end")
        row = connection.execute(f'SELECT * FROM "{table}" WHERE "{key}"=?', (eid,)).fetchone()
        if row is None:
            raise ValueError(f"{family} {eid} is absent from this client's master")
        out.append({"family": family, "event_id": eid, "start_date": start, "end_date": end})
    return out


def set_schedules(entries):
    from . import custom_support as C, master_data as M
    entries = validate(entries, M.get_connection())
    with C._writing() as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES('event_schedules',?)", (json.dumps(entries),))
        C._audit(c, "event_schedules", detail={"events": entries})
    return entries


def apply(connection, entries):
    """Shift related unlock and shop dates by the same interval as the event.

    The original main/result phase proportions are preserved. Changing the total
    window scales the original timeline; sentinel dates are made available at
    the beginning. Unselected members of an overridden family are expired.
    """
    connection.row_factory = sqlite3.Row
    entries = validate(entries, connection)
    tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for entry in entries:
        family, eid = entry["family"], entry["event_id"]
        table, key = FAMILIES[family]
        row = dict(connection.execute(f'SELECT * FROM "{table}" WHERE "{key}"=?', (eid,)).fetchone())
        old_start = row["start_date"]
        old_end = row.get("end_result_date", row["end_date"])
        span = max(1, old_end - old_start)

        def shift(value):
            if isinstance(value, str):
                if not value:
                    return value
                try:
                    stamp = dt.datetime.strptime(value, "%Y/%m/%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
                except ValueError as exc:
                    raise ValueError(f"Unrecognised event date: {value}") from exc
                return dt.datetime.fromtimestamp(shift(int(stamp.timestamp())), dt.timezone.utc).strftime("%Y/%m/%d %H:%M:%S")
            if value <= old_start:
                return entry["start_date"]
            return min(entry["end_date"], entry["start_date"] +
                       (value - old_start) * (entry["end_date"] - entry["start_date"]) // span)

        date_cols = [k for k in DATES if k in row]
        connection.execute(f'UPDATE "{table}" SET ' + ','.join(f'"{k}"=0' for k in date_cols) +
                           f' WHERE "{key}"<>?', (eid,))
        connection.execute(f'UPDATE "{table}" SET ' + ','.join(f'"{k}"=?' for k in date_cols) +
                           f' WHERE "{key}"=?', (*[shift(row[k]) for k in date_cols], eid))

        # Story missions and story unlocks explicitly reference the event ID.
        if family == "story_event":
            for related in tables:
                if not related.startswith("story_event_") or related == table:
                    continue
                cols = [r[1] for r in connection.execute(f'PRAGMA table_info("{related}")')]
                dates = [k for k in DATES if k in cols]
                if "story_event_id" not in cols or not dates or "id" not in cols:
                    continue
                for r in connection.execute(f'SELECT * FROM "{related}" WHERE story_event_id=?', (eid,)).fetchall():
                    connection.execute(f'UPDATE "{related}" SET ' + ','.join(f'"{k}"=?' for k in dates) +
                                       ' WHERE id=?', (*[shift(r[k]) for k in dates], r["id"]))
        # The test shop is explicit; story events normally have no shop.
        shop_id = row.get("shop_id")
        if shop_id and "item_exchange_top" in tables:
            connection.execute("UPDATE item_exchange_top SET start_date=?,end_date=? WHERE id=?",
                               (entry["start_date"], entry["end_date"], shop_id))
            if "item_exchange" in tables:
                connection.execute("UPDATE item_exchange SET start_date=?,end_date=? WHERE item_exchange_top_id=?",
                                   (entry["start_date"], entry["end_date"], shop_id))
        if family == "training_challenge" and "mission_data" in tables:
            for mission in connection.execute("SELECT * FROM mission_data WHERE mission_type=12 AND condition_value_1=?", (eid,)).fetchall():
                connection.execute("UPDATE mission_data SET start_date=?,end_date=? WHERE id=?",
                    (shift(mission["start_date"]), shift(mission["end_date"]), mission["id"]))
    return entries
