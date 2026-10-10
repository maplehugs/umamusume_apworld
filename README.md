# Umamusume: Pretty Derby for Archipelago

An [Archipelago](https://archipelago.gg) world for **Umamusume: Pretty Derby**,
played on the [UmamusumeX](../UmamusumeX-Private) private server.

Every career is a run. Winning G1s and finishing careers sends items to the
other players in your multiworld; what comes back are scenarios, trainees,
support cards and permanent buffs that make the next career stronger. Your goal
is one great career (default: rank score 20000, UG1).

Nothing is installed in the game: the private server applies the items and
reports the checks. Your normal save is untouched; the seed plays on a separate
save of the same account.

## Quick start

1. **Install the world** (whoever generates the seed): download
   `umamusume.apworld` from the releases (or build it, below) and double-click it,
   or Archipelago Launcher > *Install APWorld*.
2. **Make your player file**: copy [`examples/Umamusume.yaml`](examples/Umamusume.yaml),
   set `name`, change options if you like (see [docs/options.md](docs/options.md)),
   and put it in Archipelago's `Players/` folder with the other players' files.
3. **Generate and host**: Launcher > *Generate*, then host the zip from
   `output/` (Launcher > *Host*, or upload it to archipelago.gg > Host Game).
4. **Connect the server**: UmamusumeX dashboard > Settings > Mods: turn on
   `mod_archipelago`, fill in the room address, your slot name, the password and
   your viewer id. Start the game.

Full walkthrough: [docs/setup.md](docs/setup.md).

## Docs

- [How it works](docs/how-it-works.md): what an apworld is and how the pieces talk.
- [Setup](docs/setup.md): from nothing to playing.
- [Options](docs/options.md): every yaml option, and how to exclude checks.
- [Items and checks](docs/items-and-checks.md): the full lists.

## Building

```
python tools/sync_tables.py ../UmamusumeX-Private   # take the server's ids
python tools/build.py                                # -> dist/umamusume.apworld
```

`umamusume/tables.py` is a copy of the server's
`server/umaps/features/archipelago/tables.py`. Never edit it here: change the
server's copy and sync, so the server and the world always agree on every id.
