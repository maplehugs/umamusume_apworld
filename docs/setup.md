# Setup

## You need

- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7 or
  newer, only on the PC that **generates** the seed.
- The UmamusumeX server running, with the game connected to it. Its panel does
  the one-time setup (certificate, port 443, the redirect): Windows asks once
  through UAC; on Linux one desktop password prompt (pkexec) covers the
  certificate in the Proton prefix, port 443 and the hosts redirect.

## 1. Install the world

Double-click `umamusume.apworld`, or Archipelago Launcher > *Install APWorld*.
On Linux, copy it into Archipelago's `custom_worlds/` folder.

## 2. Player file

Copy `examples/Umamusume.yaml`, set `name:` (your slot name, unique in the
multiworld) and adjust options ([options.md](options.md)). Put it in
Archipelago's `Players/` folder together with everyone else's yaml.

## 3. Generate and host

- Launcher > *Generate*. The seed is written to `output/AP_<number>.zip`.
- Host it: Launcher > *Host* (your PC, port 38281), or archipelago.gg >
  *Host Game* > upload the zip.

> [!NOTE]
> archipelago.gg can host a custom world's seed but can't generate one, so
> generate locally.

## 4. Connect UmamusumeX

Dashboard > **Game > Mods > Archipelago**, with the game closed:

| Setting | Value |
|---|---|
| `mod_archipelago` | On |
| `archipelago_server` | `archipelago.gg:12345`, or `localhost:38281` for your own room |
| `archipelago_slot` | your `name:` from the yaml |
| `archipelago_password` | the room's password, if any |
| `archipelago_viewer_id` | your account's viewer id (dashboard > Accounts) |

Save. Within a few seconds the page's **Connection** section (and the server log,
**System > Backups & logs**) shows `connected as <slot>`. Saving the switch also
starts the Legend Race ladder events. Start the game: you are on your Archipelago
save.

> [!IMPORTANT]
> **Close the game before saving the switch.** It changes the game's `master.mdb`
> (the ladder's Legend races), and the server can't write it while the game reads
> it. The game shows the change after a restart, or right away with the optional
> live sync plugin (step 5).

> [!TIP]
> If the Connection section says **"missing settings"**, one of the fields above
> is empty. If the dashboard shows a yellow banner about an **unknown account**,
> the game signed in with an account this server doesn't know (often an official
> one): press **Allow**, or create a new account in the game.

## 5. Optional: live sync plugin

> [!TIP]
> **Optional. Everything works without it**: you just restart the game after a
> seed switch or a Legend ladder change. With it, the running game picks those up
> on the home screen by itself.

1. Install [Hachimi Edge](https://github.com/kairusds/Hachimi-Edge) (it replaces
   the game's `cri_mana_vpx.dll`; keep a backup of the original).
2. Download `umapd_archipelago.dll` and `SHA256SUMS` from the
   [latest release](https://github.com/maplehugs/umamusume_apworld/releases/latest) and check them:
   `sha256sum -c --ignore-missing SHA256SUMS` (Windows: `Get-FileHash umapd_archipelago.dll`
   and compare with the file).
3. Copy the DLL into `<game>/hachimi/` and add it to `<game>/hachimi/config.json`:
   `"load_libraries": ["hachimi\\umapd_archipelago.dll"]`.

Full steps, log lines and the source: [source_code_dll](../source_code_dll/README.md).

## Playing

- Items arrive as **mail** (open the present box) or as buffs, which apply from
  your next career start or training screen.
- Traps and boons (Pep Talk, Lucky Charm) hit your **next** career.
- Checks are sent the moment they happen: a G1 win at the race result screen,
  career checks when the career ends.

## Back to your normal save

Close the game, turn `mod_archipelago` off, start the game. Turn it on again to
continue the seed. Custom banners and Legend races (dashboard **Custom**) are for
your normal save; they never apply on the Archipelago ladder.

## Troubleshooting

> [!TIP]
> If something in the game looks out of date (a hint level, the trainee list,
> ticket counts), restart the game.

- **Logs say "refused: InvalidSlot"**: `archipelago_slot` doesn't match the yaml `name`.
- **"cannot reach"**: check the address and port; archipelago.gg rooms change
  port when they restart after inactivity.
- **A trainee from mail doesn't appear**: restart the game once.
- **No Legend Race ladder in the game**: the game was open when you saved the
  switch. Close it, save the switch again, start it.
- **"The game is reading its data (master.mdb)"**: close the game and try again.
