# Setup

## You need

- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7 or
  newer, only on the PC that **generates** the seed.
- The UmamusumeX server running, with the game connected to it.

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
  *Host Game* > upload the zip. archipelago.gg can host a custom world's seed but
  can't generate one, so generate locally.

## 4. Connect UmamusumeX

Dashboard > **Game > Mods > Archipelago**, with the game closed:

| Setting | Value |
|---|---|
| `mod_archipelago` | On |
| `archipelago_server` | `archipelago.gg:12345`, or `localhost:38281` for your own room |
| `archipelago_slot` | your `name:` from the yaml |
| `archipelago_password` | the room's password, if any |
| `archipelago_viewer_id` | your account's viewer id (dashboard > Accounts) |

Save. Within a few seconds the dashboard Logs show
`archipelago: connected as <slot>`. Start the game: you are on your Archipelago
save.

## Playing

- Items arrive as **mail** (open the present box) or as buffs, which apply from
  your next career start or training screen.
- Traps and boons (Pep Talk, Lucky Charm) hit your **next** career.
- Checks are sent the moment they happen: a G1 win at the race result screen,
  career checks when the career ends.

## Back to your normal save

Close the game, turn `mod_archipelago` off, start the game. Turn it on again to
continue the seed.

## Troubleshooting

- **Logs say "refused: InvalidSlot"**: `archipelago_slot` doesn't match the yaml `name`.
- **"cannot reach"**: check the address and port; archipelago.gg rooms change
  port when they restart after inactivity.
- **A trainee from mail doesn't appear**: restart the game once.
