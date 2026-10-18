# Umamusume: Pretty Derby for Archipelago

An [Archipelago](https://archipelago.gg) world for **Umamusume: Pretty Derby**,
played on a private server that does the game side. Everything you need is in
this repo:

- [`server/`](server/README.md): the private server, [UmamusumePS](https://github.com/systemless10/UmamusumePS)
  by systemless10 with Archipelago support added, and its web panel.
- [`apworld/`](apworld/): the world Archipelago generates seeds with.
- [`source_code_dll/`](source_code_dll/README.md): `umapd_archipelago.dll`, the
  Hachimi Edge plugin the game needs to pick up what the server changes.

> [!WARNING]
> **Early and rough.** The Archipelago basics work (checks, items, generating
> and playing a seed), but it needs a lot more testing and balancing, and parts
> of it are still broken. If something fails, please report it on
> [Discord](https://discord.gg/vb67v9BH5X) with the zip from the panel's
> **Download logs** button.

Every career is a run. Winning G1s and finishing careers sends items to the
other players in your multiworld; what comes back are scenarios, trainees,
support cards and permanent buffs that make the next career stronger. Your goal
is one great career (default: rank score 20000, UG1).

The server applies the items and reports the checks. Every account on it plays
Archipelago; a new seed starts that account over.

Screenshots of it running: [docs/showcase.md](docs/showcase.md).
Questions and bugs: [Discord](https://discord.gg/vb67v9BH5X) (attach the zip from the
panel's **Download logs** button).

## Quick start

1. **Start the server**: download the server package for your OS from the
   [releases](../../releases/latest) (or use this repo's `server/`). In it, run `./start-global.sh` (Linux/macOS) or
   right-click `start-global.ps1` > *Run with PowerShell* (Windows). It needs
   Python 3.11+ and sets up the rest the first time. Leave its window open; the
   web panel opens at <http://localhost:8189>.
2. **Point the game at it**: install Hachimi Edge, UmamusumePS's
   `hachimi_redirect.dll` plugin **and `umapd_archipelago.dll` from the
   [releases](../../releases/latest) (required)**, then set the redirect server to
   `https://127.0.0.1:8443` in the Hachimi menu
   ([steps](server/README.md#plugin-install)). Start the game and create an account.
3. **Install the world** (whoever generates the seed): download
   `umamusume.apworld` from the [releases](../../releases/latest) (or build it,
   below) and double-click it, or Archipelago Launcher > *Install APWorld*.
4. **Make your player file**: copy [`apworld/examples/Umamusume.yaml`](apworld/examples/Umamusume.yaml),
   set `name`, change options if you like (see [docs/options.md](docs/options.md)),
   and put it in Archipelago's `Players/` folder with the other players' files.
5. **Generate and host**: Launcher > *Generate*, then host the zip from
   `output/` (Launcher > *Host*, or upload it to archipelago.gg > Host Game).
6. **Connect the server**: in the web panel's **Archipelago** window, fill in the
   room address, your slot name and the password.

Full walkthrough: [docs/setup.md](docs/setup.md).

## Docs

- [Showcase](docs/showcase.md): screenshots of the game and the web panel.
- [How it works](docs/how-it-works.md): what an apworld is and how the pieces talk.
- [Setup](docs/setup.md): from nothing to playing.
- [Options](docs/options.md): every yaml option, and how to exclude checks.
- [Items and checks](docs/items-and-checks.md): the loot table (what a seed holds and what each item does) and the full lists.
- [Your saves](docs/saves.md): the Archipelago save, resuming, switching seeds, backups.
- [FAQ](docs/faq.md): softlocks, traps, Team Trials, common mistakes.
- [Changelog](CHANGELOG.md)

## Building

```
python apworld/build.py          # -> dist/umamusume.apworld and dist/umapd_archipelago.dll
python apworld/build.py 0.5.0    # same, stamped with a release version
```

The DLL is cross-compiled with zig through `uvx`; without it, only the apworld is built.

## The game plugin (required)

[source_code_dll](source_code_dll/README.md) holds `umapd_archipelago.dll`, a
Hachimi Edge plugin the game needs next to `hachimi_redirect.dll`. With it the running game picks up what the server
changes (the Legend Race ladder, items from the multiworld, a seed switch)
without going back to the title screen: it reloads the game's data on the home
screen. Download `umapd_archipelago.dll` from the [latest release](../../releases/latest),
or build it yourself with `python apworld/build.py`.

## Versions

`MAJOR.MINOR.PATCH`, as `world_version` in `apworld/umamusume/archipelago.json` and
as git tags `vX.Y.Z` with a release each. A seed must be played with a server
whose tables match the apworld that generated it; ids are never renumbered, so a
newer server keeps working with older seeds. See [CHANGELOG.md](CHANGELOG.md).

`apworld/umamusume/tables.py` is the source of truth for every item and check id.
`server/server/app/archipelago/tables.py` mirrors it: change both together and
never renumber an id.

## License

- `server/` is UmamusumePS by systemless10 with Archipelago support added,
  licensed [AGPL-3.0](server/LICENSE) like the original.
- `apworld/` and `source_code_dll/` are by Maple, also licensed
  [AGPL-3.0](LICENSE), so the whole repo is under one license.
