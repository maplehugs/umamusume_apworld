"""
Encoder/decoder for `race_scenario`, the gzip+base64 binary blob the real
client expects in a race response's `data.race_result_info.race_scenario`
for rendering the actual race animation.

This is Cygames' proprietary `Gallop.RaceSimulateData` wire format (see
`RaceSimulateData`/`RaceSimulateHorseFrameData`/`RaceSimulateHorseResultData`
in the IL2CPP dump at
`Career Dump Plugin/il2cppdumper/dump.cs`, around line 390270). The dump only
gives field names/types, not the byte-level layout (IL2CPP method bodies
aren't decompiled), so the layout below was reverse-engineered empirically:
cross-referencing the known field list against real captured blobs (see
`UmaDumpy-main/dumps/*/`), using a partial reference decoder that already
existed in `Icarus-Dev-Build-Private-main/career_bot/dailies.py`
(`parse_race_result_array`, which only decodes the header + results section)
as a starting point and extending it to the frame data.

Validated against real blobs by:
- horse[0]'s starting speed decoding to exactly 3.0 and its first-frame
  acceleration matching the physics engine's known 24.0 start-dash constant
  (see `uma-tools-master/uma-skill-tools/RaceSolver.ts`)
- distance-over-time for every horse increasing monotonically across all
  frames (zero negative deltas) and topping out just past the course's real
  distance (finish-line overshoot, expected for fixed-interval sampling)
- FinishOrder across all horses forming an exact permutation of
  [0, horse_num)
- FinishTime values landing in the expected real-world range for the
  course's distance (matches the *1e4 scaling documented in dailies.py)

Layout (all integers little-endian):
    int32   header_len (always 4)
    bytes   header (int32 Version, currently 100000002)
    float32 distance_diff_max
    int32   horse_num
    int32   horse_frame_size   (bytes per horse per frame, currently 12)
    int32   horse_result_size  (bytes per horse result record, currently 31)
    int32   pad1_len           (unidentified section before frame data;
                                 0 in every real sample seen so far)
    bytes   pad1
    int32   frame_count
    int32   frame_size         (bytes per frame = 4 + horse_num*horse_frame_size)
    bytes   frame data, frame_count frames of frame_size bytes each:
        float32 time
        per horse (horse_frame_size bytes):
            float32 distance
            int16   lane_position (raw = lane * 10000)
            int16   speed         (raw = speed * 100)
            int16   hp            (raw int, not scaled)
            int8    temptation_mode
            int8    block_front_horse_index
    int32   pad2_len           (unidentified section after frame data;
                                 0 in every real sample seen so far)
    bytes   pad2
    bytes   horse_result_size * horse_num bytes of result records, one per
            horse in the SAME index order as the frame data (not the same
            order as frame_order -- see race_horse_data_array[].frame_order
            for the index->horse mapping), each record:
        int32   finish_order (0-indexed)
        float32 finish_time       (seconds; real value = this / 1, already
                                    in seconds -- callers multiply by 1e4 to
                                    match the integer time fields used
                                    elsewhere in the wire protocol)
        float32 finish_diff_time
        float32 start_delay_time
        uint8   guts_order
        uint8   wiz_order
        float32 last_spurt_start_distance (-1.0 if no spurt data)
        uint8   running_style
        int32   defeat
        float32 finish_time_raw

The trailing event section encodes actual skill and race events as length-
prefixed records. An event-free race carries the reserved field and zero count.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER_VERSION = 100000002
FRAME_HZ = 15.0  # matches the ~0.0667s spacing seen in every real sample
SPEED_SCALE = 100.0
LANE_SCALE = 10000.0

@dataclass
class SkillEvent:
    horse_index: int
    skill_id: int
    t: float
    duration: float
    # bitmask (1 << wire horse index) of the horses the skill landed on:
    # herself for a buff, the targets for a debuff. 0 = unknown -> self.
    target_mask: int = 0


# Ground truth, from decompiling the real client's own methods (via a
# process memory dump of GameAssembly.dll -- the on-disk file has its code
# sections packed/encrypted, which is why earlier attempts against it
# produced nothing but zero-filled garbage; Ghidra's own Exception
# Directory parsing also independently fails on the packed file, which is
# what forced this whole detour). Every earlier "32-byte fixed record"
# understanding was subtly wrong -- see git history for the abandoned
# theories -- but was *self-consistently* wrong in a way that happened to
# survive byte-for-byte round-trip checks against real captures, which is
# why it took disassembly to actually find the bug: the real per-event
# format, confirmed directly from
# Gallop.RaceSimulateEventData._Deserialize_Ver20200406_OrNewer and the
# calling loop in Gallop.RaceSimulateData.Deserialize_Ver20200303_OrNewer,
# is a length-prefixed record:
#   int16   record_length   (byte count of everything below, NOT including
#                             this field itself -- i.e. 6 + paramCount*4)
#   float32 frameTime       (activation time, seconds, matches accumulatetime)
#   uint8   type            (SimulateEventType; 3 = Skill)
#   uint8   paramCount      (element count of the field below -- read
#                             directly as a single byte and used as an
#                             array-allocation size, confirmed in the
#                             decompiled deserializer)
#   int32[paramCount] param (every real Skill record seen has paramCount=6:
#                             [horse_index, skill_id, duration*10000,
#                             0, target_mask, 0] -- duration is -1 for a
#                             permanent (gate-time passive) skill and 0 for
#                             an instant one; target_mask is 1<<horse for
#                             every horse the effect landed on)
# The previous "32-byte struct with two leading unknown ints and a constant
# int16 marker=30" was this SAME layout misread 8 bytes out of phase: what
# looked like "unknown0/unknown1" was actually the *previous* record's own
# trailing param[4]/param[5] (both usually 0, hence looking like constant
# unrelated fields), and the "constant marker=30" was actually the length
# field's real value for the common 6-param case (2+4+1+1+24-2=30) -- not a
# validation sentinel at all. That 8-byte misalignment is also exactly why
# synthesized records reliably crashed even when whitelisted/format-correct
# by the old (wrong) model: the deserializer's length-prefix read landed on
# 8 bytes of unrelated data instead of the real length.
_SKILL_EVENT_PARAM_COUNT = 6
_SKILL_EVENT_STRUCT = struct.Struct("<hfBBiiiiii")  # length,time,type,paramCount,6x param


@dataclass
class RaceEvent:
    """A general RaceSimulateEventData record: SimulateEventType `type_id`
    with `params` (int32 each). Confirmed from real captured race_scenario
    blobs (decoded byte-for-byte against this same length-prefixed format).
    SimulateEventType, from the client's IL2CPP dump:

        type=3 (Skill):  paramCount=6, [horse_index, skill_id, duration*10000,
                          0, target_mask, 0] -- see SkillEvent below.
        type=4 (CompeteTop, spot struggle): paramCount=1, [horse_index].
        type=5 (CompeteFight, dueling): paramCount=1, [horse_index], one per
                          horse of the pair.
        type=6 (ReleaseConservePower): paramCount=1, [horse_index]."""
    t: float
    type_id: int
    params: tuple


def _encode_race_events(events: list[RaceEvent]) -> bytes:
    sorted_events = sorted(events, key=lambda e: e.t)
    out = bytearray()
    out += struct.pack("<i", 0)  # leading reserved/pad field, 0 in every real sample
    out += struct.pack("<i", len(sorted_events))
    for e in sorted_events:
        param_count = len(e.params)
        record_length = 4 + 1 + 1 + param_count * 4  # everything after the length prefix itself
        out += struct.pack(f"<hfBB{param_count}i", record_length, e.t, e.type_id, param_count, *e.params)
    return bytes(out)


def _skill_event_to_race_event(e: SkillEvent) -> RaceEvent:
    duration = -1 if e.duration < 0 else round(e.duration * 10000)
    return RaceEvent(t=e.t, type_id=3, params=(
        e.horse_index, e.skill_id, duration, 0,
        # The client stores this mask in an int32, even for expanded fields.
        ((e.target_mask or (1 << e.horse_index)) & 0xffffffff) -
        (0x100000000 if (e.target_mask or (1 << e.horse_index)) & 0x80000000 else 0), 0,
    ))


_FRAME_HORSE_STRUCT = struct.Struct("<fhhhbb")  # distance, lane, speed, hp, temptation, blockfront
_RESULT_STRUCT_HEAD = struct.Struct("<ifff")  # order, time, diff, delay
_RESULT_STRUCT_TAIL = struct.Struct("<fBf")  # last_spurt, running_style(+pad via manual byte), finish_time_raw


@dataclass
class HorseFrame:
    distance: float
    lane_position: float
    speed: float
    hp: float  # native float32, truncated only by encode_horse_frame
    temptation_mode: int = 0
    block_front_horse_index: int = -1


@dataclass
class HorseResult:
    finish_order: int  # 0-indexed
    finish_time: float
    finish_diff_time: float
    start_delay_time: float
    guts_order: int
    wiz_order: int
    last_spurt_start_distance: float
    running_style: int
    defeat: int
    finish_time_raw: float


def encode_horse_frame(buf: bytearray, hf: HorseFrame) -> None:
    # Native fields and their scaled products are float32; integer casts
    # truncate toward zero, including for negative lane values.
    def single(value: float) -> float:
        return struct.unpack('<f', struct.pack('<f', value))[0]

    lane_q = max(-32768, min(32767, int(single(single(hf.lane_position) * LANE_SCALE))))
    speed_q = max(-32768, min(32767, int(single(single(hf.speed) * SPEED_SCALE))))
    hp_q = max(-32768, min(32767, int(single(hf.hp))))
    # The client keeps BlockFrontHorseIndex as an sbyte (RaceSimulateHorseFrameData),
    # so a blocker past runner 127 can't be named: send -1 (BLOCK_HORSEINDEX_NULL,
    # "nobody in front") rather than fail the whole race on struct.error.
    block = hf.block_front_horse_index if -1 <= hf.block_front_horse_index <= 127 else -1
    buf.extend(_FRAME_HORSE_STRUCT.pack(
        hf.distance, lane_q, speed_q, hp_q, hf.temptation_mode, block
    ))


def encode_result(rec: HorseResult) -> bytes:
    buf = bytearray()
    buf.extend(struct.pack("<i", rec.finish_order))
    buf.extend(struct.pack("<f", rec.finish_time))
    buf.extend(struct.pack("<f", rec.finish_diff_time))
    buf.extend(struct.pack("<f", rec.start_delay_time))
    # byte GutsOrder / WizOrder on the client: past 255 runners, hold at 255
    # rather than wrap to 0.
    buf.append(max(0, min(255, rec.guts_order)))
    buf.append(max(0, min(255, rec.wiz_order)))
    buf.extend(struct.pack("<f", rec.last_spurt_start_distance))
    buf.append(rec.running_style & 0xFF)
    buf.extend(struct.pack("<i", rec.defeat))
    buf.extend(struct.pack("<f", rec.finish_time_raw))
    assert len(buf) == 31, f"result record must be 31 bytes, got {len(buf)}"
    return bytes(buf)


def encode_scenario(
    horse_num: int,
    frames: list[tuple[float, list[HorseFrame]]],  # (time, [HorseFrame per horse])
    results: list[HorseResult],  # indexed same as frames' horse order
    distance_diff_max: float = 0.0,
    skill_events: list[SkillEvent] | None = None,
    race_events: list[RaceEvent] | None = None,
) -> bytes:
    """Build the raw (pre-gzip) RaceSimulateData binary blob."""
    assert len(results) == horse_num
    horse_frame_size = _FRAME_HORSE_STRUCT.size
    frame_size = 4 + horse_num * horse_frame_size

    out = bytearray()

    # header: length-prefixed int32 Version
    header = struct.pack("<i", HEADER_VERSION)
    out.extend(struct.pack("<i", len(header)))
    out.extend(header)

    # metadata block
    out.extend(struct.pack("<fiii", distance_diff_max, horse_num, horse_frame_size, 31))

    # pad1 (unidentified, empty)
    out.extend(struct.pack("<i", 0))

    # frame data
    out.extend(struct.pack("<ii", len(frames), frame_size))
    for time_val, horse_frames in frames:
        assert len(horse_frames) == horse_num
        out.extend(struct.pack("<f", time_val))
        for hf in horse_frames:
            encode_horse_frame(out, hf)

    # pad2 (reserved, empty; events follow the result records)
    out.extend(struct.pack("<i", 0))

    # results
    for rec in results:
        out.extend(encode_result(rec))

    # Include the reserved field and count even when no events fired.
    combined_events = [_skill_event_to_race_event(e) for e in (skill_events or [])]
    combined_events += list(race_events or [])
    out.extend(_encode_race_events(combined_events))

    return bytes(out)


def decode_scenario(blob: bytes) -> dict:
    """Reference decoder, used only for round-trip validation in tests."""
    off = 0
    header_len = struct.unpack_from("<i", blob, off)[0]
    off += 4 + header_len
    distance_diff_max, horse_num, horse_frame_size, horse_result_size = struct.unpack_from("<fiii", blob, off)
    off += 16
    pad1 = struct.unpack_from("<i", blob, off)[0]
    off += 4 + pad1
    frame_count, frame_size = struct.unpack_from("<ii", blob, off)
    off += 8
    frames = []
    for _ in range(frame_count):
        t = struct.unpack_from("<f", blob, off)[0]
        horses = []
        o = off + 4
        for _h in range(horse_num):
            dist, lane_q, speed_q, hp_q, temptation, blockfront = _FRAME_HORSE_STRUCT.unpack_from(blob, o)
            horses.append(HorseFrame(dist, lane_q / LANE_SCALE, speed_q / SPEED_SCALE, hp_q, temptation, blockfront))
            o += horse_frame_size
        frames.append((t, horses))
        off += frame_size
    pad2 = struct.unpack_from("<i", blob, off)[0]
    off += 4 + pad2
    results = []
    for i in range(horse_num):
        base = off + i * horse_result_size
        rec = blob[base:base + horse_result_size]
        results.append(HorseResult(
            finish_order=struct.unpack_from("<i", rec, 0)[0],
            finish_time=struct.unpack_from("<f", rec, 4)[0],
            finish_diff_time=struct.unpack_from("<f", rec, 8)[0],
            start_delay_time=struct.unpack_from("<f", rec, 12)[0],
            guts_order=rec[16],
            wiz_order=rec[17],
            last_spurt_start_distance=struct.unpack_from("<f", rec, 18)[0],
            running_style=rec[22],
            defeat=struct.unpack_from("<i", rec, 23)[0],
            finish_time_raw=struct.unpack_from("<f", rec, 27)[0],
        ))
    off += horse_num * horse_result_size
    events = []
    if off + 8 <= len(blob):
        _, count = struct.unpack_from("<ii", blob, off)
        off += 8
        for _ in range(count):
            length, t, kind, n = struct.unpack_from("<hfBB", blob, off)
            params = list(struct.unpack_from(f"<{n}i", blob, off + 8))
            events.append({"t": t, "type": kind, "params": params})
            off += 2 + length
    return {
        "distance_diff_max": distance_diff_max,
        "horse_num": horse_num,
        "frame_count": frame_count,
        "frames": frames,
        "results": results,
        "events": events,
    }
