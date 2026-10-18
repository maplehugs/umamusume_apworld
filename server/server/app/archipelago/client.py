"""The Archipelago connection: a daemon thread that stays connected to the room in
client_config.json, applies received items to the account that logged in last
and sends its checks.

Protocol: docs/network protocol.md in ArchipelagoMW/Archipelago. Items are applied
in the order the server lists them; `next_index` (persisted with the items, in the
same save) makes a reconnect, which resends everything from 0, apply nothing twice.

The connection state is written to archipelago_status.json in the region's data
dir, for the admin panel (its ops run in a separate worker process).
"""

from __future__ import annotations

import json
import logging
import ssl
import threading
import time
import uuid

from websockets.sync.client import connect

from .. import accounts, config, region
from .. import archipelago
from .. import state as state_store
from . import tables

log = logging.getLogger("uma-server")
# The library logs every frame (pings included) at DEBUG.
logging.getLogger("websockets").setLevel(logging.INFO)

AP_VERSION = {"major": 0, "minor": 6, "build": 7, "class": "Version"}
ITEMS_ALL = 0b111  # others' items, our own-world items and starting inventory
CLIENT_GOAL = 30
RETRY_SECONDS = 15


STATUS = {"state": "off", "detail": ""}
# Room numbers for the panel: hint points, what a hint costs, the room's answer
# to the last command the panel sent.
ROOM = {"hint_points": None, "hint_cost": None, "last_reply": ""}


def status_path():
    return region.data_dir() / "archipelago_status.json"


def say_path():
    """Chat lines / !commands from the panel (one per line), sent by this thread."""
    return region.data_dir() / "archipelago_say.txt"


def _status(state: str | None = None, detail: str = "") -> None:
    """Write STATUS and ROOM for the panel; no state: only ROOM changed."""
    if state is not None:
        STATUS.update(state=state, detail=detail)
    try:
        status_path().write_text(json.dumps({**STATUS, "at": int(time.time()), "room": ROOM}))
    except OSError:
        log.warning("archipelago: could not write %s", status_path(), exc_info=True)


def _config():
    host = str(config.get("archipelago_server", "")).strip()
    slot = str(config.get("archipelago_slot", "")).strip()
    missing = [k for k, v in (("archipelago_server", host), ("archipelago_slot", slot)) if not v]
    if missing:
        return ", ".join(missing)
    return host, slot, str(config.get("archipelago_password", "") or "")


def start() -> None:
    if region.PROCESS_REGION == "global":
        threading.Thread(target=_run_forever, name="archipelago", daemon=True).start()


def _run_forever() -> None:
    while True:
        cfg = _config()
        if not isinstance(cfg, tuple):
            _status("off", f"not set yet: {cfg}")
            time.sleep(5)
            continue
        try:
            _Session(*cfg).run()
        except Exception as exc:  # network, refusal, a new seed: retry later
            _status("error", str(exc))
            log.warning("archipelago: %s (retrying in %ss)", exc, RETRY_SECONDS)
        time.sleep(RETRY_SECONDS)


class _Session:
    def __init__(self, host, slot, password):
        self.cfg = (host, slot, password)
        self.host, self.slot, self.password = host, slot, password
        self.vid = None
        self.ws = None
        self.connected = False
        self.players = {}
        self.slot_num = None
        self.team = 0
        self.games = {}  # slot -> game
        self.names = {}  # game -> ({item id: name}, {location id: name})

    def run(self):
        urls = [self.host] if "://" in self.host else [f"wss://{self.host}", f"ws://{self.host}"]
        last = None
        for url in urls:
            try:
                ctx = ssl.create_default_context() if url.startswith("wss://") else None
                with connect(url, ssl=ctx, max_size=16 * 1024 * 1024, open_timeout=10) as ws:
                    self.ws = ws
                    _status("connecting", url)
                    self._loop()
                    return
            except (OSError, ssl.SSLError) as exc:
                last = exc
        raise ConnectionError(f"cannot reach {self.host}: {last}")

    def _loop(self):
        while _config() == self.cfg:  # a settings change reconnects
            try:
                raw = self.ws.recv(timeout=1)
            except TimeoutError:
                raw = None
            if raw is not None:
                for pkt in json.loads(raw):
                    self._handle(pkt)
            self._flush_outbox()

    def _send(self, *cmds):
        self.ws.send(json.dumps(list(cmds)))

    def _flush_outbox(self):
        if not self.connected:
            return
        try:
            said = say_path().read_text().splitlines()
            say_path().unlink()
        except OSError:
            said = []
        for text in filter(None, said):
            ROOM["last_reply"] = ""
            self._send({"cmd": "Say", "text": text})
        locs, goal = [], False
        while not archipelago.OUTBOX.empty():
            entry = archipelago.OUTBOX.get_nowait()
            if entry == "GOAL":
                goal = True
            else:
                locs.append(entry)
        if locs:
            self._send({"cmd": "LocationChecks", "locations": locs})
        if goal:
            self._send({"cmd": "StatusUpdate", "status": CLIENT_GOAL})

    def _handle(self, p):
        cmd = p.get("cmd")
        if cmd == "RoomInfo":
            self.vid = archipelago.target_viewer()
            if self.vid is None:
                raise RuntimeError("no account yet: log in to the game once")
            self.seed = p["seed_name"]
            self.hint_cost_pct = p.get("hint_cost") or 0
            # Every game's names, to show hints and other players' items readably.
            self._send({"cmd": "GetDataPackage", "games": p.get("games") or []})
            self._send({
                "cmd": "Connect", "game": tables.GAME, "name": self.slot, "password": self.password,
                "uuid": str(uuid.uuid4()), "version": AP_VERSION, "items_handling": ITEMS_ALL,
                "tags": [], "slot_data": True,
            })
        elif cmd == "ConnectionRefused":
            raise RuntimeError(f"refused: {', '.join(p.get('errors') or ['?'])}")
        elif cmd == "Connected":
            self.players = {pl["slot"]: pl["alias"] for pl in p.get("players", [])}
            self.slot_num = p.get("slot")
            self.team = p.get("team", 0)
            self.games = {int(k): v.get("game") for k, v in (p.get("slot_info") or {}).items()}
            room_checked = set(p.get("checked_locations") or ())
            every = sorted(room_checked | set(p.get("missing_locations") or ()))
            ROOM["hint_points"] = p.get("hint_points")
            ROOM["hint_cost"] = max(1, int(getattr(self, "hint_cost_pct", 0) * len(every) / 100))
            with accounts.viewer_lock(self.vid):
                archipelago.start_seed(self.vid, self.seed)  # a new seed: a fresh save
            with _Edit(self.vid) as full_state:
                st = archipelago.ap_state(full_state)
                st["slot_data"] = p.get("slot_data") or {}
                st["locations"] = every  # this seed's checks, for the tracker
                archipelago.apply_starters(full_state)
                pending = sorted(set(st["checked"]) - room_checked)
                # Checks the room already has (a collect, a /send_location) show as done too.
                st["checked"] = sorted(set(st["checked"]) | room_checked)
                goal = st["goal_done"]
            self.connected = True
            _status("connected", f"{self.slot} @ {self.host} (viewer {self.vid})")
            log.info("archipelago: connected as %s to %s", self.slot, self.host)
            if pending:
                self._send({"cmd": "LocationChecks", "locations": pending})
            if goal:
                self._send({"cmd": "StatusUpdate", "status": CLIENT_GOAL})
            hints = self._hints_key()
            self._send({"cmd": "Get", "keys": [hints]}, {"cmd": "SetNotify", "keys": [hints]})
            # What sits at each of our checks, to show what a done check sent and to whom.
            self._send({"cmd": "LocationScouts", "locations": every, "create_as_hint": 0})
        elif cmd == "LocationInfo":
            with _Edit(self.vid) as full_state:
                archipelago.ap_state(full_state)["scouted"] = {
                    str(it["location"]): {
                        "item": self._name(it.get("player"), 0, it.get("item")),
                        "to": self.players.get(it.get("player"), str(it.get("player"))),
                        "flags": it.get("flags", 0),
                    }
                    for it in p.get("locations") or ()
                }
        elif cmd == "DataPackage":
            for game, data in (p.get("data", {}).get("games") or {}).items():
                self.names[game] = (
                    {v: k for k, v in data.get("item_name_to_id", {}).items()},
                    {v: k for k, v in data.get("location_name_to_id", {}).items()},
                )
        elif cmd in ("Retrieved", "SetReply"):
            key = self._hints_key()
            raw = p.get("keys", {}).get(key) if cmd == "Retrieved" else (
                p.get("value") if p.get("key") == key else None)
            if raw is not None:
                with _Edit(self.vid) as full_state:
                    archipelago.ap_state(full_state)["hints"] = [self._hint(h) for h in raw]
        elif cmd == "ReceivedItems":
            with _Edit(self.vid) as full_state:
                self._receive(full_state, p)
        elif cmd == "RoomUpdate":
            if "hint_points" in p:
                ROOM["hint_points"] = p["hint_points"]
                _status()
            if p.get("checked_locations"):
                with _Edit(self.vid) as full_state:
                    st = archipelago.ap_state(full_state)
                    st["checked"] = sorted(set(st["checked"]) | set(p["checked_locations"]))
        elif cmd == "PrintJSON":
            # The room's answer to a command we sent (e.g. "!hint": not enough points).
            if p.get("type") in ("CommandResult", "AdminCommandResult") or (
                p.get("type") == "Hint" and p.get("receiving") == self.slot_num
            ):
                ROOM["last_reply"] = "".join(self._text(d) for d in p.get("data", ()))
                _status()
            if p.get("receiving") == self.slot_num or p.get("type") in ("Chat", "Goal", "Hint"):
                log.info("archipelago: %s", "".join(self._text(d) for d in p.get("data", ())))

    def _receive(self, full_state, p):
        st = archipelago.ap_state(full_state)
        idx = p["index"]
        if idx > st["next_index"]:  # missed some: ask for the whole list again
            self._send({"cmd": "Sync"})
            return
        received = st.setdefault("received", [])
        for i, item in enumerate(p.get("items") or (), start=idx):
            sender = self.players.get(item.get("player"), "")
            if i >= st["next_index"]:  # a reconnect replays from 0: apply once
                archipelago.apply_item(full_state, item["item"], sender)
                st["next_index"] = i + 1
                archipelago.touch_account()
            if i >= len(received):  # the log (re)fills from the replay too
                received.append({
                    "item": archipelago.item_name(item["item"]),
                    "from": sender,
                    "where": self._name(item.get("player"), 1, item.get("location")),
                    "flags": item.get("flags", 0),
                })

    def _hints_key(self):
        return f"_read_hints_{self.team}_{self.slot_num}"

    def _name(self, slot, kind, ident):
        """kind 0 = item, 1 = location, in `slot`'s game."""
        table = self.names.get(self.games.get(slot), ({}, {}))[kind]
        return table.get(ident, f"#{ident}")

    def _hint(self, h):
        """A stored hint, readable: who finds what, where, for whom."""
        finder, receiver = h.get("finding_player"), h.get("receiving_player")
        return {
            "item": self._name(receiver, 0, h.get("item")),
            "location": self._name(finder, 1, h.get("location")),
            "finder": self.players.get(finder, str(finder)),
            "receiver": self.players.get(receiver, str(receiver)),
            "for_me": receiver == self.slot_num,
            "found": bool(h.get("found")),
        }

    def _text(self, d):
        kind = d.get("type")
        if kind == "player_id":
            return self.players.get(int(d["text"]), d["text"])
        if kind in ("item_id", "location_id"):
            return self._name(d.get("player"), 0 if kind == "item_id" else 1, int(d["text"]))
        return d.get("text", "")


class _Edit:
    """`with _Edit(vid) as full_state`: the Archipelago save under the account's
    request lock, saved on a clean exit."""

    def __init__(self, viewer_id):
        self.vid = viewer_id

    def __enter__(self):
        self._lock = accounts.viewer_lock(self.vid)
        self._lock.acquire()
        try:
            self.full_state = state_store.get_state(self.vid)
            if self.full_state is None:
                raise RuntimeError(f"no save for viewer {self.vid}")
        except BaseException:
            self._lock.release()
            raise
        return self.full_state

    def __exit__(self, exc_type, *_):
        try:
            if exc_type is None:
                state_store.save_state(self.vid, self.full_state)
        finally:
            self._lock.release()
        return False
