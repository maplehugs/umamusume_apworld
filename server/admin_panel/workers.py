"""The per-region worker processes and the JSON-lines calls into them."""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = Path(__file__).resolve().parent / "logs"
REGIONS = ("global", "jp")


def _python() -> str:
    """The server's venv python (it has the server's dependencies)."""
    for cand in (ROOT / "server/.venv/bin/python3.14", ROOT / "server/.venv/bin/python3",
                 ROOT / "server/.venv/Scripts/python.exe"):
        if cand.exists():
            return str(cand)
    return sys.executable


def _master_env(region: str) -> dict:
    """MASTER_MDB_PATH for one region's worker. The launching PS exports the
    path for its OWN region; handing that to the other region's worker made it
    read the wrong game's master (e.g. Global showing JP names)."""
    own = os.environ.get("UMA_REGION", "global").strip().lower()
    explicit = os.environ.get(f"MASTER_MDB_PATH_{region.upper()}")
    if explicit:
        return {"MASTER_MDB_PATH": explicit}
    if region == own and os.environ.get("MASTER_MDB_PATH"):
        return {}
    # Same defaults as start-server.sh: Global uses the repo's master.mdb, JP
    # the macOS Wine install; otherwise master_data probes the Steam paths.
    candidates = {"global": [ROOT / "master.mdb"],
                  "jp": [Path(os.environ.get("UMA_WINEPREFIX", Path.home() / "Games/steam"))
                         / "drive_c/Program Files (x86)/Steam/steamapps/common/UmamusumePrettyDerby_Jpn"
                         / "UmamusumePrettyDerby_Jpn_Data/Persistent/master/master.mdb"]}[region]
    found = next((str(p) for p in candidates if p.is_file()), None)
    return {"MASTER_MDB_PATH": found} if found else {"MASTER_MDB_PATH": ""}


class WorkerError(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


class Worker:
    def __init__(self, region: str):
        self.region = region
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.ids = itertools.count(1)
        self.started_at = None
        self.calls = 0

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _start(self) -> None:
        LOGS.mkdir(exist_ok=True)
        env = dict(os.environ, UMA_REGION=self.region, PYTHONUNBUFFERED="1")
        env.update(_master_env(self.region))
        log = open(LOGS / f"worker-{self.region}.log", "a", encoding="utf-8")
        self.proc = subprocess.Popen(
            [_python(), "-m", "admin_panel.worker"], cwd=ROOT, env=env, text=True, encoding="utf-8",
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, bufsize=1)
        ready = self.proc.stdout.readline()
        if not ready:
            raise WorkerError(f"The {self.region} worker failed to start.",
                              f"See {LOGS / f'worker-{self.region}.log'}")
        import time
        self.started_at = time.time()

    def stop(self) -> None:
        with self.lock:
            if self.alive:
                self.proc.terminate()
                try:
                    self.proc.wait(5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            self.proc = None

    def call(self, op: str, viewer: str | None, args: dict) -> dict:
        with self.lock:
            if not self.alive:
                self._start()
            rid = next(self.ids)
            try:
                self.proc.stdin.write(json.dumps({"id": rid, "op": op, "viewer": viewer, "args": args}) + "\n")
                self.proc.stdin.flush()
                while True:
                    line = self.proc.stdout.readline()
                    if not line:
                        raise WorkerError(f"The {self.region} worker stopped.",
                                          f"See {LOGS / f'worker-{self.region}.log'}")
                    msg = json.loads(line)
                    if msg.get("id") == rid:
                        break
            except (BrokenPipeError, OSError) as ex:
                self.proc = None
                raise WorkerError(f"The {self.region} worker stopped ({ex}).") from None
            self.calls += 1
        if not msg.get("ok"):
            raise WorkerError(msg.get("error") or "Failed.", msg.get("detail") or "")
        return msg


class Pool:
    def __init__(self):
        self.workers = {r: Worker(r) for r in REGIONS}

    def call(self, region: str, op: str, viewer, args) -> dict:
        if region not in self.workers:
            raise WorkerError(f"Unknown region {region}.")
        return self.workers[region].call(op, viewer, args)

    def status(self) -> dict:
        return {r: {"alive": w.alive, "started_at": w.started_at, "calls": w.calls} for r, w in self.workers.items()}

    def restart(self, region: str) -> None:
        self.workers[region].stop()

    def close(self) -> None:
        for w in self.workers.values():
            w.stop()
