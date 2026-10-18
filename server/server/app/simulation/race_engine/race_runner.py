"""Port of tools/raceRunner.ts -- multi-horse race harness.

Builds one RaceSolver per horse (distinct-but-deterministic per-horse seed,
same `spec.seed + i*7919` derivation as the TS bridge), steps the whole
field together in lockstep at DT=float32(0.0666)s, and returns
`{seed, frames, results, skillEvents, raceEvents, distanceDiffMax}` -- the
sole integration point with `race_simulator.run_simulation`, so the contract
must not change without updating that caller (and race_engine_rs/src/main.rs,
which returns exactly the same shape).
"""

from __future__ import annotations

from typing import Any
import struct

from .course_data import get_course
from .race_field import RaceField
from .race_solver import SkillType, _STAT_TYPES
from .race_solver_builder import RaceSolverBuilder

def _f32(value: float) -> float:
    return struct.unpack('<f', struct.pack('<f', value))[0]


DT = _f32(0.0666)
MAX_RACE_SECONDS = 400.0

_STRATEGY_IDS = {"Nige": 1, "Senkou": 2, "Sasi": 3, "Oikomi": 4, "Oonige": 5}


def _skill_id_and_level(entry) -> tuple[str, int]:
    """Accepts either a plain skill-id string (older/test callers) or the
    {"skillId", "level"} shape race_simulator.build_horse_spec sends."""
    if isinstance(entry, dict):
        return str(entry["skillId"]), int(entry.get("level") or 1)
    return str(entry), 1


def _new_builder(spec: dict, h: dict, i: int) -> RaceSolverBuilder:
    return (
        RaceSolverBuilder(1)
        .seed(spec["seed"] + i * 7919, 0)
        .course(spec["courseId"])
        .mood(max(-2, min(2, h.get("mood", 0))))
        .ground(spec["groundCondition"])
        .weather(spec["weather"])
        .season(spec["season"])
        .gate_index(h.get("gateIndex", i))
        .single_mode(bool(spec.get("singleMode")))
        .chara_ids([x.get("charaId") or 0 for x in spec["horses"]])
        .time((spec.get("raceContext") or {}).get("time", 2))
        .grade((spec.get("raceContext") or {}).get("grade", 100))
        .popularity(h.get("popularity", 1))
        .num_umas(len(spec["horses"]))
        .context({**(spec.get("raceContext") or {}), **h, **(h.get("raceContext") or {}),
                      "roster": spec["horses"], "skillIds": [_skill_id_and_level(e)[0] for e in h.get("skills") or []],
                      "maxRawStat": max(h["speed"], h["stamina"], h["power"], h["guts"], h["wisdom"])})
        .horse({
            "speed": h["speed"],
            "stamina": h["stamina"],
            "power": h["power"],
            "guts": h["guts"],
            "wisdom": h["wisdom"],
            "strategy": h["strategy"],
            "distanceAptitude": h["distanceAptitude"],
            "surfaceAptitude": h["surfaceAptitude"],
            "strategyAptitude": h["strategyAptitude"],
        })
        # Doc's "Charge Up / Conserve Power" and "Stamina Limit Break" --
        # both already ported (RaceSolverBuilder.withAsiwotameru/
        # withStaminaSyoubu in the original TS) but never enabled by the
        # upstream raceRunner.ts bridge. Real Global mechanics, so enabled
        # here. Must come after .horse()/.mood() (both read from them).
        .with_asiwotameru()
        .with_stamina_syoubu()
    )


def _wire_duration(t: float, effects, timed_duration) -> float:
    """The Skill event's duration the way the real server writes it: the
    skill's own scaled duration if it has one, -1 for a permanent one (every
    gate-time passive in a real capture is -1), 0 for an instant one (a
    heal)."""
    if timed_duration is not None:
        return timed_duration
    if t <= 0.0 or any(ef.type in _STAT_TYPES for ef in effects):
        return -1.0
    return 0.0


def run_race(spec: dict) -> dict:
    course = get_course(spec["courseId"])

    # Whether a skill id can actually be built for this race. Some skills'
    # conditions reference tokens this engine doesn't implement and those
    # throw from inside build() (not addSkill()), so a single bad skill
    # would otherwise abort the whole horse's build. Memoized across the
    # roster (most horses share most of their skills).
    skill_usable: dict[tuple, bool] = {}
    skipped_skills = []

    def is_usable(skill_id: str, level: int, h: dict, i: int) -> bool:
        key = (i, skill_id, level)
        cached = skill_usable.get(key)
        if cached is not None:
            return cached
        ok = True
        try:
            probe = _new_builder(spec, h, i)
            probe.add_skill(skill_id, level=level)
            gen = probe.build()
            next(gen)
        except Exception:
            ok = False
        skill_usable[key] = ok
        return ok

    solvers = []
    unique_ids: list[set] = []
    for i, h in enumerate(spec["horses"]):
        builder = _new_builder(spec, h, i)
        wanted = [_skill_id_and_level(e) for e in (h.get("skills") or [])]
        unique_ids.append({
            str(e["skillId"]) for e in (h.get("skills") or [])
            if isinstance(e, dict) and e.get("isUnique")
        })
        try:
            for skill_id, level in wanted:
                try:
                    builder.add_skill(skill_id, level=level)
                except Exception:
                    pass
            solver = next(builder.build())
        except Exception:
            retry = _new_builder(spec, h, i)
            for skill_id, level in wanted:
                if not is_usable(skill_id, level, h, i):
                    skipped_skills.append({"gateIndex": h.get("gateIndex", i), "skillId": skill_id})
                    continue
                try:
                    retry.add_skill(skill_id, level=level)
                except Exception:
                    pass
            solver = next(retry.build())
        solvers.append(solver)

    field = RaceField(solvers)

    n = len(solvers)
    finished: list[float | None] = [None] * n
    finished_step: list[float | None] = [None] * n
    hp_out = [False] * n
    blocked_front_time = [0.0] * n
    frames: list[dict[str, Any]] = [{
        't': 0.0,
        'horses': [{'pos': s.pos, 'speed': s.current_speed,
                    'hp': max(0.0, s.hp.hp) if hasattr(s.hp, 'hp') else 0.0,
                    'lane': s.lane, 'tempt': 0, 'block': -1} for s in solvers],
    }]
    # Largest leader-to-last gap before the leader finishes -- the scenario
    # header's distance_diff_max (matches every real capture to the metre).
    distance_diff_max = 0.0

    t = 0.0
    while any(f is None for f in finished) and t < MAX_RACE_SECONDS:
        active = [i for i in range(n) if finished[i] is None]
        prev_pos = {i: solvers[i].pos for i in active}
        field.step_all(DT, active)
        for i in active:
            s = solvers[i]
            if not s.hp.has_remaining_hp():
                hp_out[i] = True
            if s._front_blocker_index >= 0:
                blocked_front_time[i] += DT
            if s.pos >= course.distance:
                span = s.pos - prev_pos[i]
                frac = (course.distance - prev_pos[i]) / span if span > 0 else 0
                finished[i] = t + DT * frac
                finished_step[i] = t + DT
                s.finished = True
        t = _f32(t + _f32(DT))
        if all(f is None for f in finished):
            positions = [s.pos for s in solvers]
            distance_diff_max = max(distance_diff_max, max(positions) - min(positions))

        # Record every tick; race_simulator (or the Rust side) thins them to
        # the real server's recording cadence.
        frames.append({
            "t": t,
            "horses": [
                {
                    "pos": s.pos,
                    "speed": s.current_speed,
                    "hp": max(0.0, s.hp.hp) if hasattr(s.hp, "hp") else 0.0,
                    "lane": s.lane,
                    "tempt": int(s.temptation_mode) if s.is_kakari else 0,
                    "block": s._front_blocker_index,
                }
                for s in solvers
            ],
        })

    for i in range(n):
        if finished[i] is None:
            finished[i] = t
            finished_step[i] = t

    order = sorted(range(n), key=lambda i: finished[i])
    order_index = {horse_i: rank for rank, horse_i in enumerate(order)}

    results = []
    for i, s in enumerate(solvers):
        # Where she actually went into the last spurt; -1 = never did (a
        # plan that only starts at the planner's 60m margin is no spurt).
        lst = s.last_spurt_start_pos
        spurted = 0 < lst < course.distance - 60 - 1e-6
        results.append({
            "finishOrder": order_index[i],  # 0-based
            "finishTime": finished_step[i],
            "finishTimeRaw": finished[i],
            "startDelayTime": s.start_delay if isinstance(s.start_delay, (int, float)) else 0,
            "lastSpurtStartDistance": lst if spurted else -1,
            "runningStyle": _STRATEGY_IDS.get(spec["horses"][i]["strategy"], 2),
            "rushed": s.temptation_count > 0 and s.kakari_start <= course.distance,
            "hpOut": hp_out[i],
            "blockedFrontTime": blocked_front_time[i],
        })

    skill_events: list[dict] = []
    race_events: list[dict] = []
    for i, s in enumerate(solvers):
        for (at, skill_id, effects, targets, timed_duration) in s.activation_log:
            try:
                sid = int(skill_id)
            except (TypeError, ValueError):
                continue
            skill_events.append({
                "horseIndex": i,
                "skillId": sid,
                "t": at,
                "duration": _wire_duration(at, effects, timed_duration),
                "isUnique": 1 if skill_id in unique_ids[i] else 0,
                # horses the skill landed on: herself for a buff, the targets
                # for a debuff (the event's target bitmask on the wire)
                "targets": targets if targets else [i],
            })
        # Rushed episodes, under the non-numeric "kakari" sentinel skill id
        # team_stadium's PvP scoring and the career epithets read.
        spans = list(s.kakari_log)
        if s.is_kakari:
            spans.append((s._kakari_started_at, t))
        for start_t, end_t in spans:
            skill_events.append({"horseIndex": i, "skillId": "kakari", "t": start_t,
                                 "duration": end_t - start_t, "isUnique": 0})
        for at, type_id in s.event_log:
            race_events.append({"horseIndex": i, "type": int(type_id), "t": at})

    return {"seed": spec["seed"], "frames": frames, "results": results, "skillEvents": skill_events,
            "raceEvents": race_events, "distanceDiffMax": distance_diff_max, "skippedSkills": skipped_skills}
