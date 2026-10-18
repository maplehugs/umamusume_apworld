# Race simulation and replay encoding

`race_simulator.py` runs the native Rust race engine with a Python fallback.
Both engines accept the same course, horse, condition, gate and seed inputs.
The server supplies completed outcomes and gzip/base64 replays to the client.

`scenario_format.py` encodes the captured `RaceSimulateData` framing: timestamped
horse frames, result records, and length-prefixed skill/race events. Events refer
to the same gate-ordered horse indices as the frames and results. Races without
events carry a reserved field and zero event count; they never borrow events from
another race.

The layout was reconstructed from client declarations and captured blobs.
Decoding a replay validates its framing and indexing, not complete physics or
client-rendering parity. See [Team Trials implementation](../../../docs/TEAM_TRIALS_IMPLEMENTATION.md)
for regional checks and remaining research boundaries.
