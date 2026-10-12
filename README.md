# Umamusume: Pretty Derby for Archipelago

An [Archipelago](https://archipelago.gg) world for **Umamusume: Pretty Derby**,
played on the **UmamusumeX** private server (its Archipelago mod does the game side).

Every career is a run. Winning G1s and finishing careers sends items to the
other players in your multiworld; what comes back are scenarios, trainees,
support cards and permanent buffs that make the next career stronger. Your goal
is one great career (default: rank score 20000, UG1).

Nothing is installed in the game: the private server applies the items and
reports the checks. Your normal save is untouched; the seed plays on a separate
save of the same account.

![The tracker in the UmamusumeX dashboard](docs/media/dashboard-tracker.png)

Screenshots and a clip of it running: [docs/showcase.md](docs/showcase.md).

## Quick start

1. **Install the world** (whoever generates the seed): download
   `umamusume.apworld` from the [releases](../../releases/latest) (or build it, below) and double-click it,
   or Archipelago Launcher > *Install APWorld*.
2. **Make your player file**: copy [`examples/Umamusume.yaml`](examples/Umamusume.yaml),
   set `name`, change options if you like (see [docs/options.md](docs/options.md)),
   and put it in Archipelago's `Players/` folder with the other players' files.
3. **Generate and host**: Launcher > *Generate*, then host the zip from
   `output/` (Launcher > *Host*, or upload it to archipelago.gg > Host Game).
4. **Connect the server**: UmamusumeX dashboard > Game > Mods > Archipelago, with the
   game closed: turn on `mod_archipelago`, fill in the room address, your slot name,
   the password and your viewer id. Start the game.
5. *(Optional)* **Live sync plugin**: `umapd_archipelago.dll` from the release, for
   Hachimi Edge. Without it, restart the game after a seed switch.

Full walkthrough: [docs/setup.md](docs/setup.md).

## Docs

- [Showcase](docs/showcase.md): screenshots of the game and the dashboard.
- [How it works](docs/how-it-works.md): what an apworld is and how the pieces talk.
- [Setup](docs/setup.md): from nothing to playing.
- [Options](docs/options.md): every yaml option, and how to exclude checks.
- [Items and checks](docs/items-and-checks.md): the loot table (what a seed holds and what each item does) and the full lists.
- [Your saves](docs/saves.md): the Archipelago save, resuming, switching seeds, backups, editing.
- [FAQ](docs/faq.md): softlocks, traps, Team Trials, common mistakes.
- [Changelog](CHANGELOG.md)

## Building

```
python tools/build.py          # -> dist/umamusume.apworld
python tools/build.py 0.5.0    # same, stamped with a release version
```

## Optional: live sync plugin

> [!TIP]
> Optional: everything works without it.

[source_code_dll](source_code_dll/README.md) holds an optional Hachimi Edge plugin.
With it the running game picks up what the server changes (the Legend Race ladder,
items from the multiworld, a seed switch) without going back to the title screen:
it reloads the game's data on the home screen. Download `umapd_archipelago.dll`
from the [latest release](../../releases/latest), or build it yourself with
`python tools/build.py` (it writes `dist/umapd_archipelago.dll`).

## Versions

`MAJOR.MINOR.PATCH`, as `world_version` in `umamusume/archipelago.json` and as git
tags `vX.Y.Z` with a release each. 
> [!IMPORTANT]
> A seed must be played with a server whose tables match the apworld that
> generated it; ids are never renumbered, so a newer server keeps working with
> older seeds.
 See [CHANGELOG.md](CHANGELOG.md).

`umamusume/tables.py` is the source of truth for every item and check id. The
server mirrors it: edit `tables.py` here, make the same change on the server, and
never renumber an id. With this repo cloned next to the server, the server's
Archipelago tests fail if the two differ.
