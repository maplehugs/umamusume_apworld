# Reloading master data in a running client: RE notes

Game build of 2026-10-06 (Steam Global, `GameAssembly.dll` 100642816 bytes).
Sources: the method list the umapd_bigfield plugin's dump mode wrote from the
running game (`Namespace.Class::Method/argc RVA`), and the in-memory image of
`GameAssembly.dll` from its image dump (sections fixed to raw == virtual),
disassembled with `llvm-objdump` at the RVAs below. Ghidra/REA time out on the
128 MB image. Static dumpers (Il2CppDumper) fail on this game, so there are
method names but no field names: offsets below are from the code.

## How master data is held

- `Gallop.MasterDataManager` (singleton) owns:
  - `+0x10`: a list of `AbstractMasterDatabase` (one per group: `MasterGachaDatabase`,
    `MasterLegendRaceDatabase`...),
  - `+0x18`: the `LibNative.Sqlite3.Connection` on
    `<game>/UmamusumePrettyDerby_Data/Persistent/master/master.mdb`
    (`OpenMasterConnection` 0x3b44200: creates it when null, `Open(path, ..., 3)`),
  - one field per table (`get_masterGachaData` 0xa01da0 is `mov rax,[rcx+0x270]`; 415 getters).
- A table (`MasterGachaData`, `MasterLegendRace`, `MasterLegendRaceBossNpc`...,
  base `AbstractMasterData`) caches rows in dictionaries; `Get(id)` looks there,
  then `_SelectOne` queries SQLite. `Unload()` (virtual) clears every
  dictionary and the "all entries preloaded" flag (+0x18):
  `MasterGachaData::Unload` 0x36b99f0 clears +0x28; `MasterLegendRace::Unload`
  0x385f5d0 clears +0x28/+0x30/+0x38.
- A database (`MasterGachaDatabase`) keeps lazily prepared statements
  (`GetSelectQuery_GachaData` 0x3b4baf0: created when the field is null) and the
  connection at +0xc8 (`_GetOpenedConnection` 0x3b486b0: reopens it with its
  stored path when its handle is 0). `Unload()` 0x3b4b2b0 disposes and nulls
  every statement, then calls `Unload` on each of its tables.
- `LibNative.Sqlite3.Connection`: handle +0x10, path +0x18. CloseDB (0x1d00d10,
  only reached through the vtable) = `sqlite3_close(handle)` (throws on an error
  code) then handle = 0; the path is kept, so the lazy reopen above works.

## The game's own reload

- `MasterDataManager::UnloadDatabases` 0x3b43d20: for each database in +0x10,
  `Unload()` (virtual call, vtable +0x178); then a virtual call on the connection +0x18 (vtable +0x198), which is CloseDB
  (inferred: CloseDB has no direct callers; the only other
  `sqlite3_close` call is Open cleaning up after a failed open).
  Everything stays in place and is refilled lazily.
- `MasterDataManager::ForceResetDatabases` 0x3b43ef0: `UnloadDatabases`, clears
  the list, nulls the connection. Called from `LoadMasterDataCoroutine` (startup
  and after a data download; it then rebuilds everything through
  `SetupMasterGroup`), `UseDbServer`, `OnFinalize`, and the asset `DeleteAllAsync`.
- `GameSystem::SoftwareReset` 0x3f5ac20 (back to title) also exists.

## Choice

Live reload is possible: call `MasterDataManager.UnloadDatabases()` on the main
thread. It is the first step of the game's own full reload, and it leaves every
object in place, so screens and managers that hold a table or database
reference keep working and just read fresh rows on their next lookup. The
connection is closed and reopened, so SQLite's page cache can't serve old pages
either. The full reload (`ForceResetDatabases` + `SetupMasterGroup`) would swap
every database object and needs the setup coroutine: not needed.

Safe when: on the main thread between frames (no query is half-stepped: queries
run to completion synchronously). The plugin calls it from the start of
`GameSystem.FixedUpdate` (Hachimi hooks `GameSystem.Update`/`LateUpdate` itself) and through `il2cpp_runtime_invoke`, so a managed exception
(e.g. `sqlite3_close` refusing because some statement outside the databases is
still open) is caught and logged; by then every table cache is already cleared.

Limits:
- A screen that is already open keeps what it built: leave it and come back.
- Lists the client gets from the server (for example which banners
  `gacha/index`-style calls return) still come from the server; this only
  refreshes what the client reads from master.mdb.
- Some data copied out of master at login into other managers (not traced) may
  stay stale until the title screen.

# Reloading the account (load/index) without the title screen

Same sources. The request/response classes (`LoadIndexRequest`...) are in
`umamusume.Http.dll`, which the dump does not cover, and the code that copies
load/index into `WorkDataManager` (only getters there: `WorkItemData.UpdateAll`,
`WorkUserData` setters...) is spread over many classes, so the plugin does not
send load/index itself. The game already has a path that does all of it:

- Day change (the 5:00 reset): `DateChange::ExecuteDateChangeProcess` 0x3f59cb0
  pushes the day-change dialog (`DialogManager::PushDayChangeDialog`); its OK
  button is `DateChange::OnClickDateChange/1` 0x3f59d40, which never reads its
  arguments: it builds the lambda `<OnClickDateChange>b__16_0` 0x3f5a3f0 and
  calls `DialogManager::RemoveAllDialog(lambda, true, ...)`.
- The lambda: when some state is 2 or 3 it calls `GameSystem::SoftwareReset`
  (title); otherwise (in game) it optionally calls `SingleModeUtils::ClearPlayData`
  and `SceneManager::ChangeView(4, ...)`: view 4 = `DayChangeHubViewController`.
- `DayChangeHubViewController::ResetGame` 0x3df5170 starts `<ResetGame>d__1`
  (0x3df51e0): `UIManager.UnlockGameCanvas`, then
  `MainGameInitializer::InitializeMainGame/2` 0x3f5ed60 (the same login sequence
  the title's "touch to start" runs: `TitleViewController::OnClickPushStart`
  0x3e0adf0 calls it too), i.e. a fresh login + load/index applied by the game's
  own code, then on to the home screen.

So the plugin calls `DateChange.OnClickDateChange(null)`: the exact effect of
pressing OK on the day-change dialog. Where: only on the home screen
(`SceneManager.GetCurrentViewBase()` is a `Home*` view), with no dialog open
(`DialogManager.IsExistDialog`) and no view/scene change running
(`SceneManager.IsRunChangeView/IsRunChangeScene`), and 3 s after the last
account change (items arrive in bursts). The game itself skips day changes in
some views (`DateChange::IsIgnoreDateChangeOnChangeView`, `...InSingleTop`);
staying on the home screen keeps clear of all of them.

Not used: `GameSystem::SoftwareReset` 0x3f5ac20 (goes to the title screen and
needs a tap).
