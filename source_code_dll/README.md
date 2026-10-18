# umapd_archipelago

A [Hachimi Edge](https://github.com/kairusds/Hachimi-Edge) plugin for the
private server in [`server/`](../server/README.md): when the server changes the
game's `master.mdb` (the Archipelago Legend ladder), the running game rereads its master data, so the change shows
up **without restarting the game**. And when the account changes behind the
game's back (Archipelago seed switch, items from the multiworld), the game logs in again by itself once you are on the home
screen, the way it does at the daily 5:00 reset. Required for Archipelago play.

Modding the game client is against the game's Terms of Service. Use it with
the private server only; it does nothing on its own, but remove it before
playing on the official servers if that matters to you.

## How it works

- After every change it commits to `master.mdb`, the server rewrites
  `<game>/hachimi/umapd_master.version` (only if the `hachimi` folder exists).
- The plugin hooks `Gallop.GameSystem.FixedUpdate` (main thread; Hachimi already
  hooks `GameSystem.Update`/`LateUpdate`, and a function can have only one hook) and
  checks that file's write time once a second. When it changed, it calls the
  game's own `Gallop.MasterDataManager.UnloadDatabases()`: all master tables
  drop their cached rows, the database connection is closed, and the next
  lookup reads the new rows. See [RE_NOTES.md](RE_NOTES.md).
- A screen that is already open keeps what it showed: leave it and come back.
- If something in the game looks out of date (a hint level, the trainee list,
  ticket counts), restart the game.
- The server also rewrites `<game>/hachimi/umapd_account.version` when the
  account changes on its own (seed switch, items received, save restored). Three
  seconds after the last such change, as soon as you are on the home screen with
  no dialog open, the plugin runs the game's day-change re-login
  (`Gallop.DateChange.OnClickDateChange`): a short loading screen, a fresh
  load/index, back on the home screen. A career, race or any other screen is
  never interrupted: it waits until you are home.

## Build

C, cross-compiled from Linux with zig (from PyPI through `uvx`, no MSVC/mingw/sudo):

```sh
uvx --from ziglang python -m ziglang cc -target x86_64-windows-gnu -shared -O2 \
    -o umapd_archipelago.dll umapd_archipelago.c
```

`python apworld/build.py` does this too and puts the DLL in `dist/` next to the apworld.

## Install (Steam Global, also under Proton)

1. Hachimi Edge: download `hachimi.dll` from its releases (check it against the
   release's `blake3.json`), rename it to `cri_mana_vpx.dll` and put it in the
   game folder (`.../steamapps/common/UmamusumePrettyDerby`). Start the game once
   so Hachimi creates `<game>/hachimi/`.

   Keep a backup of the `cri_mana_vpx.dll` that was there: it's how you undo it.

2. Copy `umapd_archipelago.dll` (from the latest release, or your own build) into `<game>/hachimi/`.

   Check a downloaded DLL against the release's `SHA256SUMS`:
   `sha256sum -c --ignore-missing SHA256SUMS` (Windows: `Get-FileHash umapd_archipelago.dll`).
   The build is reproducible: `python apworld/build.py` (Zig 0.17.0, no debug info,
   no timestamp) gives a byte-identical DLL from the same source, so the hash
   proves the release DLL is this code.

3. In `<game>/hachimi/config.json`, list it (next to any other plugin):
   `"load_libraries": ["hachimi\\umapd_archipelago.dll"]`.
   For a log in `<game>/hachimi.log`, also set `"enable_file_logging": true`.

To remove: take the line out of `load_libraries` (or delete the DLL).

## Log lines (target `umapd_archipelago`)

- `watching` and the path of `umapd_master.version`: loaded.
- `master.mdb changed: master data reloaded`: a reload happened.
- `account changed: waiting for the home screen (now on <View>)`: pending.
- `account changed: logging in again (day-change reload)`: the re-login started.
- `... UnloadDatabases threw ...`, `... not found`: tell the developer (with the log).

## Credits

- [Hachimi Edge](https://github.com/kairusds/Hachimi-Edge) by kairusds, a fork of
  [Hachimi](https://github.com/LeadRDRK/Hachimi) by LeadRDRK: the mod loader and the
  plugin API this plugin is built on. Licensed under their own terms; this plugin
  ships none of their code.
- Plugin: Maple.

Each release has a prebuilt `umapd_archipelago.dll`, built from this source with
`python apworld/build.py`. Build it yourself if you'd rather know exactly what runs
in your game.
