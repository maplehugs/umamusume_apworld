"""Worker operations. Each op is fn(viewer, args) -> JSON-able result, and is
registered by name with @op. Ops that write declare a history label, so the
change lands in the undo history under a readable name."""

from __future__ import annotations

import importlib

OPS: dict[str, tuple] = {}


def op(name: str, label: str | None = None):
    """Register an op. `label` (a format string over args) names the change in
    the undo history; read-only ops leave it out."""
    def wrap(fn):
        OPS[name] = (fn, label)
        return fn
    return wrap


def load_all() -> None:
    for mod in ("catalog", "users", "save", "supports", "custom_support", "umas", "legacy",
                "career_ops", "career_tuning", "misc", "history_ops", "races", "umamoe",
                "archipelago"):
        importlib.import_module(f"{__name__}.{mod}")
