# Setup

## You need

- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7 or
  newer, only on the PC that **generates** the seed.
- On the PC that **plays**: Umamusume: Pretty Derby (Global, Steam), started
  once so its `master.mdb` exists, [Hachimi Edge](https://github.com/kairusds/Hachimi-Edge),
  Python 3.11 or newer, and this repo's `server/` folder (a release package, or a
  clone).

## 1. Start the server

In `server/`:

- Linux/macOS: `./start-global.sh`
- Windows: right-click `start-global.ps1` > *Run with PowerShell*

The first run takes a while: it makes the Python environment, a certificate,
builds the race engines (a release package has them already built) and reads
the race courses from your game install. Keep the window open while you play.
When it's up, the web panel opens at <http://localhost:8189>.

## 2. Point the game at the server

1. Install Hachimi Edge and start the game once, so `<game>/hachimi/` exists.
2. Download `hachimi_redirect.dll` from [UmamusumePS's plugin release](https://github.com/systemless10/UmamusumePS/releases/tag/plugin)
   (or build it from `server/plugin/hachimi_redirect`) and copy it into `<game>/hachimi/`.
3. Add it to `<game>/hachimi/config.json`:
   `"load_libraries": ["hachimi\\hachimi_redirect.dll"]`.
4. Start the game, open the Hachimi menu (right arrow key) and set the redirect
   server to `https://127.0.0.1:8443`.
5. Create an account in the game. Any new account gets in.

To play on the official servers again, turn the redirect off in the Hachimi menu.

## 3. Install the world

Double-click `umamusume.apworld`, or Archipelago Launcher > *Install APWorld*.
On Linux, copy it into Archipelago's `custom_worlds/` folder.

## 4. Player file

Copy `apworld/examples/Umamusume.yaml`, set `name:` (your slot name, unique in the
multiworld) and adjust options ([options.md](options.md)). Put it in
Archipelago's `Players/` folder together with everyone else's yaml.

## 5. Generate and host

- Launcher > *Generate*. The seed is written to `output/AP_<number>.zip`.
- Host it: Launcher > *Host* (your PC, port 38281), or archipelago.gg >
  *Host Game* > upload the zip.

archipelago.gg can host a custom world's seed but can't generate one, so
generate locally.

## 6. Connect the server

In the web panel's **Archipelago** window, fill in:

- **Room**: `archipelago.gg:12345`, or `localhost:38281` for your own room
- **Slot name**: your `name:` from the yaml
- **Room password**: the room's password, if any

They're saved in `server/server/client_config.json` (`archipelago_server`,
`archipelago_slot`, `archipelago_password`) if you'd rather edit the file.
Within a few seconds the window shows `connected as <slot>`. The connection plays
for the account that logged in last, so log in once before connecting.

The first connection to a seed starts that account over for it (see
[saves.md](saves.md)). Go back to the title screen and log in again to see the
new save.

## 7. Optional: live sync plugin

Optional, everything works without it: you just log in again after a seed
switch or new items. With it, the running game picks those up on the home
screen by itself, and the Legend Race ladder shows without restarting the game.

1. Download `umapd_archipelago.dll` and `SHA256SUMS` from the
   [latest release](https://github.com/maplehugs/umamusume_apworld/releases/latest) and check them:
   `sha256sum -c --ignore-missing SHA256SUMS` (Windows: `Get-FileHash umapd_archipelago.dll`
   and compare with the file).
2. Copy the DLL into `<game>/hachimi/` and add it next to the redirect plugin in
   `<game>/hachimi/config.json`:
   `"load_libraries": ["hachimi\\hachimi_redirect.dll", "hachimi\\umapd_archipelago.dll"]`.

Full steps, log lines and the source: [source_code_dll](../source_code_dll/README.md).

## Playing

- Items arrive as **mail** (open the present box) or as buffs, which apply from
  your next career start or training screen.
- Traps and boons (Pep Talk, Lucky Charm) hit your **next** career.
- Checks are sent the moment they happen: a G1 win at the race result screen,
  career checks when the career ends.
- Team Trials and Legend Races need trained umas: finish a career first, then
  register a team in Team Trials > Edit Team.

## The Legend Race ladder

The game's own Legend Races have all ended, so when the server starts it opens
the ladder's ten Legend Races in your game's `master.mdb` (backed up once to
`server/server/data/master_before_archipelago.sqlite3.bak`). The game shows them
after its next login, or right away with the live sync plugin. To put the
original dates back, see the [server README](../server/README.md#archipelago).

## Troubleshooting

If something in the game looks out of date (a hint level, the trainee list,
ticket counts), go back to the title screen, or restart the game.

- **"refused: InvalidSlot"** in the server window: the slot doesn't match the yaml `name`.
- **"cannot reach"**: check the address and port; archipelago.gg rooms change
  port when they restart after inactivity.
- **"no account yet: log in to the game once"**: start the game and log in; the
  server connects to the room right after.
- **A trainee from mail doesn't appear**: log in again.
- **No Legend Race in the game**: log in again (or restart the game) so it reads
  the ladder.
- **Team Trials error 2801**: you have no team yet; register one in Team Trials > Edit Team.
- The server's full log is `server/server/logs/server.log`.
