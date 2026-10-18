"""Career tuning: the region's client_config.json testing knobs that bend
career training (gains, specialty, hints, bond, energy, failure). These are
server-wide, not per save, and the game server re-reads the file on change."""

from __future__ import annotations

import json
import os

from app import config

from . import op
from .common import OpError

# key -> (kind, min, max, label, help). None/blank means the real formula decides.
KNOBS = {
    "training_gain_multiplier": ("float", 0, 100, "Training value multiplier",
                                 "Scales every training's stat and skill-point gains (2 = double). Stat caps still apply."),
    "specialty_priority_bonus": ("int", 0, 10000, "Specialty priority bonus",
                                 "Flat weight added to every support card's own-type facility in the placement roll. A card's own specialty priority is ~20-100; 500+ makes cards almost always show up on their type."),
    "hint_rate_multiplier": ("float", 0, 100, "Hint rate multiplier",
                             "Scales each placed card's skill-hint (!) chance. Base is 7% times the card's hint frequency; 15 is roughly always."),
    "bond_gain_multiplier": ("float", 0, 100, "Bond gain multiplier",
                             "Scales bond gained from training with a card."),
    "energy_cost_multiplier": ("float", 0, 10, "Energy cost multiplier",
                               "Scales the energy training costs. 0 = training is free. Wit's energy recovery is unaffected."),
    "force_failure_rate": ("int", 0, 100, "Force failure rate %",
                           "Pins every training's failure chance. 0 = never fails."),
    "force_training_gain": ("int", 0, 100000, "Force training gain",
                            "Pins every stat and skill-point gain to this number. Overrides the multiplier."),
}


def _read() -> dict:
    try:
        with open(config.CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except FileNotFoundError:
        return {}
    except ValueError as ex:
        raise OpError(f"{config.CONFIG_PATH} isn't valid JSON: {ex}") from ex


@op("tuning.get")
def get(viewer, args):
    data = _read()
    return {"path": config.CONFIG_PATH,
            "knobs": [{"key": k, "kind": kind, "min": lo, "max": hi, "label": label, "help": help_,
                       "value": data.get(k)} for k, (kind, lo, hi, label, help_) in KNOBS.items()]}


@op("tuning.set")
def set_(viewer, args):
    data = _read()
    for k, v in (args.get("values") or {}).items():
        if k not in KNOBS:
            raise OpError(f"Unknown knob {k}.")
        kind, lo, hi, label, _ = KNOBS[k]
        if v is None or v == "":
            data[k] = None
            continue
        try:
            v = int(v) if kind == "int" else float(v)
        except (TypeError, ValueError) as ex:
            raise OpError(f"{label} must be a number.") from ex
        if not lo <= v <= hi:
            raise OpError(f"{label} must be between {lo} and {hi}.")
        data[k] = v
    _write(data)
    return get(viewer, {})


def _write(data: dict) -> None:
    tmp = config.CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, config.CONFIG_PATH)
