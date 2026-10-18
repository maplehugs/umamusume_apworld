# Your saves

Every account on the server plays Archipelago. Everything below happens on the
server; the game just logs in.

## The Archipelago save

- The first connection to a seed starts the account over as a new player's
  account under your own name and profile: URA only, 5 starting trainees
  (random per seed with `starting_trainees: shuffled`), R/SR support cards, no
  carats, Support Pt and Monies at the cap. Scouting is closed: cards come from
  the multiworld.
- Legend Race ladder races are free.
- Accounts the server hasn't seen get in on their first login.

## Resuming

Close the server, come back days later, start it again: the same room resumes
the same save. Items you already got are never applied twice (the server keeps
the room's item index), and checks you made while the room was down are sent
when it reconnects.

## Switching seeds

Point the server at another room: the account starts over for that seed, and
nothing from the old seed is kept. Going back to the old room starts it over
again, so finish a seed (or back it up) before switching.

The game keeps the old save in memory until it logs in again: go back to the
title screen after a switch (the live sync plugin does it for you).

## Starting a seed over

Stop the server, back it up (below), and delete the account's rows from
`server/server/data/state.sqlite3` (table `viewer_state_kv`, its `viewer_id`). The
next connection to the room makes a new save and the room sends every item again.

## Backups

The saves live in `server/server/data/state.sqlite3` (and `accounts.sqlite3`).
Stop the server and copy that folder.

## What the panel shows

The web panel's **Archipelago** window refreshes every few seconds while open:

- the connection, seed, items received, checks done and the goal;
- a notice when a Trainee Awakening arrives (log in again to see it);
- permanent buffs with their combined effect;
- traps and boons on the running career and the next one;
- hints: ask for one (`!hint <item>`) without a text client; what to do in your
  game and where your items are in other worlds;
- items sent (your checks and what they held) and received, each with what it
  does (a Rainbow Uncap Crystal: Enhance > Support Cards > Limit Break);
- a tracker of every check in the seed: done, available now (in logic), not yet.

To test something, the room's console can send items: `/send <slot> <item name>`.
