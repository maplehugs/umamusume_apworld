# Your saves

The private server keeps your account's normal save untouched while you play a
seed. Everything below happens on the server; the game just logs in.

## The Archipelago save

- Turned on in the dashboard (**Game > Mods > Archipelago**), your account is
  served from a separate save **per seed**.
- It starts as a new player's account under your own name and profile: URA
  only, 5 starting trainees (random per seed with `starting_trainees: shuffled`),
  R/SR support cards, no carats, Support Pt and Monies at the cap. Scout shows a
  single paid-only banner and can't pull: cards come from the multiworld.
- Daily race tickets refill once a day, at the daily reset. Legend Race ladder
  races are free.
- Turn the mod off (game closed) and you're back on your normal save.

## Resuming

Close the server, come back days later, start it again: the same room resumes
the same save. Items you already got are never applied twice (the server keeps
the room's item index), and checks you made while the room was down are sent
when it reconnects.

## Switching seeds

Point the mod at another room: that seed gets **its own new save**. The previous
seed's save is kept; reconnecting to that room later resumes it. 

> [!IMPORTANT]
> Switch with the game closed: the game keeps the old save in memory until it
> logs in again.

## Starting a seed over

> [!CAUTION]
> This can't be undone: stop the server and make a backup first.

With the server stopped, delete that seed's save: the rows of
viewer id `<viewer id>:ap:<seed>` in the server's state database. The next
connection to its room makes a new save and the room sends every item again.

## Backups

Dashboard **System > Backups & logs** snapshots every save, normal and
Archipelago. The server also snapshots before each dashboard edit.

## Editing a save

While the mod is on, the dashboard's account tools (**Players > Accounts**: give
items, carats, max cards...) edit the **Archipelago** save of that account. Turn
the mod off to edit the normal save.

To test something, the room's console can send items: `/send <slot> <item name>`.

## What the page shows

**Mods > Archipelago** refreshes every few seconds while open:

- a notice when a Trainee Awakening arrives (log in again to see it);
- connection, seed, items received, checks done, goal, and the apworld version
  the server matches;
- permanent buffs with their combined effect;
- traps and boons on the running career (with turns left) and the next one;
- hints: ask for one (`!hint <item>`) without a text client; what to do in your
  game and where your items are in other worlds;
- items sent (your checks and what they held) and received, each with what it
  does (a Rainbow Uncap Crystal: Enhance > Support Cards > Limit Break);
- a tracker of every check in the seed: done, available now (in logic), not yet.
