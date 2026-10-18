# Setup

## You need

- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7 or
  newer, only on the PC that **generates** the seed.
- On the PC that **plays**: Umamusume: Pretty Derby (Global, Steam), started
  once so its `master.mdb` exists, [Hachimi Edge](https://github.com/kairusds/Hachimi-Edge),
  Python 3.11 or newer, and the server: the `umaps-archipelago-server-*` package
  for your OS from the [latest release](https://github.com/maplehugs/umamusume_apworld/releases/latest),
  or this repo's `server/` folder.

## 1. Start the server

In the server package (or `server/`):

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
3. **Required:** `umapd_archipelago.dll` in `<game>/hachimi/`. Easiest: once the server
   is running, the panel's Archipelago page > **Game setup** checks your files and its
   **Fix** button installs it and lists both plugins in `config.json` (step 4). Or download it
   from the [latest release](https://github.com/maplehugs/umamusume_apworld/releases/latest)
   and copy it there. It makes the game pick up seed switches, items and the Legend Race
   ladder ([details](../source_code_dll/README.md)).
   Optional: the release's `SHA256SUMS` checks the download is the exact file published
   (`sha256sum -c --ignore-missing SHA256SUMS`; Windows: `Get-FileHash umapd_archipelago.dll`
   and compare). It isn't needed to play and doesn't go in the game folder.
4. Add both to `<game>/hachimi/config.json`:
   `"load_libraries": ["hachimi\\hachimi_redirect.dll", "hachimi\\umapd_archipelago.dll"]`.
5. Start the game, open the Hachimi menu (right arrow key) and set the redirect
   server to `https://127.0.0.1:8443`.
6. Create an account in the game. Any new account gets in.

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
- The server's full log is `server/server/logs/server.log`. For a bug report, press
  **Download logs** in the panel's Connection section: it zips the log and the
  connection status.
