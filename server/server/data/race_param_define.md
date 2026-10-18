# JP race asset extraction

Extracted directly from the installed JP client's `UmamusumePrettyDerby_Jpn_Data/Persistent` on October 6, 2026. No game installation files, Hachimi plugin files, or simulator code were changed.

`race_param_define.json` contains the entire Unity serialized field tree of `Gallop.RaceParamDefine` (119 root fields, including Unity bookkeeping), 142 `CourseParamTable` assets, all 204 indexed `CourseLaneAnim` assets (normal and overrun), and 140 rows from JP `master.mdb.race_course_set`. The union has 143 course-set IDs; asset and master coverage differ. Course tables preserve corners, straights, slopes, lane changes, and all other event types exactly, including their integer `_values`; the enum mapping comes from Global_dump.cs. Lane assets retain every position and quaternion sample. Each bundle includes its index hash and encrypted-file SHA-256.

Every serialized float is represented as `{"decimal": 1.2000000476837158, "float32_hex": "0x3f99999a"}`. Hex means the IEEE-754 uint32 bit pattern; little-endian bytes for that example are `9a 99 99 3f`. Integers and strings retain their native JSON types. All 1,428,703 float representations were checked by packing their decimal back to float32 and comparing the bits.

## Method and reproduction

The encrypted `meta` is SQLite3 Multiple Ciphers / ChaCha20, opened read-only with `apsw-sqlite3mc` and `PRAGMA hexkey`. The working key is `9c2bab97bcf8c0c4f1a9ea7881a213f6c9ebf9d8d4c6a8e43ce5a259bde7e9fd`, published in [Umamusume voice/text extractor](https://github.com/chinosk6/umamusume-voice-text-extractor/blob/main/voiceex/assets_decrypt.py), which attributes it to [UmamusumeExplorer](https://github.com/MarshmallowAndroid/UmamusumeExplorer/blob/master/UmamusumeData/UmaDataHelper.cs). This resolved the index without reverse engineering key derivation in the installed client.

For each `a(n,h,e)` row, read `dat/h[:2]/h`. Leave the first 256 bytes untouched; XOR subsequent bytes with the repeating 88-byte key formed by XORing each of the 11 base bytes with the eight little-endian bytes of signed int64 `e`. UnityPy 1.25.4 reads the resulting UnityFS bundle and its embedded type tree. The database dependency used was apsw-sqlite3mc 3.53.4.0.

Reproduce with `tools/extract_race_assets.py --persistent '<JP install>/UmamusumePrettyDerby_Jpn_Data/Persistent'`. Dependencies can be installed in an isolated venv. The extractor uses read-only database connections and writes only its output path.

## Sanity checks and interpretation

- `declBase = 1.0 (0x3f800000)`.
- `declRateStart = 1.2000000476837158 (0x3f99999a)`.
- `declRateMiddle = 0.800000011920929 (0x3f4ccccd)`.
- `declRateEnd = 1.0 (0x3f800000)`.
- `declRateHpZero = 1.2000000476837158 (0x3f99999a)`.
- `DeclRatePositionKeepPaseDown = 0.5 (0x3f000000)`.
- `startDelayMax = 0.10000000149011612 (0x3dcccccd)`; Global fields.tsv identifies this field at offset 0x130.
- `Temptation.TemptationStartPerVal1 = 13.0 (0x41500000)`; Global fields.tsv identifies it at TemptationParam offset 0x18. The expected ~6.5 is **not** the serialized JP value. Do not silently replace it: investigate the consumer formula or JP/Global version difference. The asset's `paramDefineVersion` string is `20180828`, not a reliable client build date.

These are JP assets, not proof that the corresponding Global asset has identical constants. Runtime-computed and nonserialized fields are outside the asset tree.

## Remaining coverage gaps

137 of the 140 master rows resolve to indexed normal lane assets using track ID, distance, zero-based ground/inout, and run_outside. Course IDs 10301, 11201, and 11202 have no matching indexed normal-lane asset. They are preserved with null lane references; no geometry was invented. Course 11202 also has no indexed event table. Extra event tables without master rows are retained.

`serialized_lane_start` is the first position/quaternion sample in a matching lane asset, **not a runtime gate transform**. Per-horse gate positions and the final gate base transform remain unextracted and are explicitly marked in `gate_positions`. Global client declarations expose `CourseLane.Init`, `CourseLane.StartPosition/StartRotation`, `HorseInitialLaneCalculator.CalcGateOffsetX`, and gate initialization with a position/rotation; reproducing or capturing those runtime calculations is a separate remaining step. This deliverable is complete for the selected serialized assets, but not for the requested runtime gate positions.
