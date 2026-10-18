"""RaceParamDefine and course event tables, from the JP asset extraction.

`server/data/race_param_define.json` holds the client's serialized
Gallop.RaceParamDefine and CourseParamTable assets; every float is given as its
exact float32 value. Field names are the client's own.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

_DATA_DIR = Path(__file__).resolve().parents[3] / 'data'
# RACE_EXACT_REGION=global selects the Global client's assets; the course
# tables and lane curves differ between regions (see race_param_define.md).
REGION = os.environ.get('RACE_EXACT_REGION', 'jp').lower()
DATA = _DATA_DIR / ('race_param_define_global.json' if REGION == 'global' else 'race_param_define.json')


def _plain(x):
    if isinstance(x, dict):
        if set(x) == {'decimal', 'float32_hex'}:
            return float(x['decimal'])   # the decimal IS the float32 value
        return SimpleNamespace(**{k: _plain(v) for k, v in x.items()})
    if isinstance(x, list):
        return [_plain(v) for v in x]
    return x


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(DATA.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def param_define() -> SimpleNamespace:
    obj = _raw()['race_param_define']['objects'][0]['fields']
    return _plain(obj)


EVENT_CORNER, EVENT_STRAIGHT, EVENT_LANE_MAX, EVENT_MOVE_LANE_POINT, EVENT_SLOPE = 0, 2, 3, 7, 11


@lru_cache(maxsize=None)
def course_set(course_id: int) -> SimpleNamespace:
    """Master row plus the raw course events: (type, distance, offsetPerLane, values)."""
    cs = _raw()['course_sets'][str(course_id)]
    events = []
    for o in (cs.get('event_asset') or {}).get('objects') or []:
        for p in o['fields']['courseParams']:
            events.append((p['_paramType'], float(p['_distance']['decimal']),
                           float((p.get('_distanceOffsetPerLane') or {'decimal': 0.0})['decimal']), list(p['_values'])))
    m = cs['master']
    return SimpleNamespace(master=SimpleNamespace(**m), events=events)
