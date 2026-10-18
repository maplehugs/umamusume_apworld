"""
Single source of truth for "which region is this" -- Global or JP.

Each region runs as its own server process (`./start-server.sh --region jp`
sets UMA_REGION=jp), and the two share NO data: every per-region file lives
under data_dir(), so a JP account, save, friend list or learned constant can
never be read by the Global server or the other way round. Shared game-logic
code reads data_dir() instead of branching on the region, so there is never a
scattered `if region == "jp"` in handler code.

CURRENT_REGION stays a ContextVar (defaulting to the process's region) so a
test can still run a block of code as the other region with use_region().
"""

from __future__ import annotations

import contextvars
import os
from contextlib import contextmanager
from pathlib import Path

REGIONS = ("global", "jp")

PROCESS_REGION = os.environ.get("UMA_REGION", "global").strip().lower()
if PROCESS_REGION not in REGIONS:
    raise RuntimeError(f"UMA_REGION={PROCESS_REGION!r}; expected one of {REGIONS}")

CURRENT_REGION: contextvars.ContextVar[str] = contextvars.ContextVar(
    "CURRENT_REGION", default=PROCESS_REGION
)

# UMA_DATA_ROOT exists only so tools can exercise the server against a scratch
# copy of the data (tools/jp_shape_audit.py); normal runs never set it.
_DATA_ROOT = Path(os.environ.get("UMA_DATA_ROOT") or Path(__file__).resolve().parents[1] / "data")


def data_dir() -> Path:
    """Where this region's databases and generated data live. Global keeps the
    historical server/data/ (existing installs and saves keep working); JP gets
    its own server/data/jp/ with nothing in common."""
    region = CURRENT_REGION.get()
    d = _DATA_ROOT if region == "global" else _DATA_ROOT / region
    d.mkdir(parents=True, exist_ok=True)
    return d


def seeds_dir() -> Path:
    """This region's starting data (a new account's first load/index, etc.)."""
    return data_dir() / "seeds"


@contextmanager
def use_region(name: str):
    token = CURRENT_REGION.set(name)
    try:
        yield
    finally:
        CURRENT_REGION.reset(token)
