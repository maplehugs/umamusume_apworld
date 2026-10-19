# How it works

## What an apworld is

Archipelago shuffles the items of several games together. To do that it needs
to know, for each game:

- its **items** (things you can receive),
- its **locations** or **checks** (places an item can sit: "win the Arima Kinen"),
- its **logic** (what you need before a check is reachable).

An `.apworld` is a small Python package that tells Archipelago exactly that. It
is used **only when the seed is generated**: Archipelago reads every player's
yaml, asks each world for its items, checks and rules, and places every item
somewhere in the multiworld so that everyone can always finish. The result is
one zip file. The apworld isn't used again after that.

## During the game

```
  Umamusume client  <->  private server  <->  Archipelago room  <->  other players
  (redirect plugin)       (the "client")       (MultiServer)
```

- The **room** (archipelago.gg or your own Launcher > Host) holds the seed. It
  knows which item sits behind every check.
- The **private server** (`server/`) connects to the room as your slot. When you win a G1
  or finish a career, it tells the room "check X done"; the room sends the item
  behind it to whoever owns it. When an item for you arrives, the server applies
  it to your Archipelago save.
- The **game** only needs the redirect plugin that points it at the server. It sees mail in the present box, a new
  scenario on the career screen, or bigger numbers in training.

Both sides share one id table: `apworld/umamusume/tables.py` is the source of truth,
and the server's copy mirrors it.

## Your saves

Every account on the server plays Archipelago:

- the first connection to a seed starts the account over, with your name and
  profile but a new player's collection (URA only, 5 trainees, R/SR cards), with
  Support Pt and Monies at the cap;
- scouting is closed (cards come from the multiworld);
- closing the server and coming back to the same room resumes the save; joining
  another seed starts the account over again. See [saves.md](saves.md).

## Logic

A career's rank score mostly depends on your buffs and your deck, so logic doesn't
count items: it estimates the best rank score you can reach with what you have:

```
estimate = base + 300 per training item + 400 per starting-stats item
         + 300 per stat-cap item + your best 6 maxed SSRs (1200 for an average card)
         + 1500 with a non-URA scenario
```

Each SSR is rated per scenario: 60% to 130% of an average SSR, from
[Tachyon's Lab](https://jechto.github.io/Tachyons-lab/)'s tier list model with
every stat weighted alike (rank score counts them alike; the site weighs them for
racing), averaged over every distance and running style. A top card counts up to
1560 and a weak one 720: loose on purpose, since a card's worth also hangs on the
trainee and the race. A scenario's link cards count 20% more there. A scenario
check uses that scenario's ratings; other checks use your best scenario. An SSR
not yet maxed counts half; the other half once 4 crystals can max it (your best
cards first).
`base` is 7500 / 8500 / 9500 for relaxed / normal / expert
(`logic_difficulty`). A rank check (or the goal) is "in logic" once the estimate
reaches it. A goal above what every buff could reach only asks for every buff.

Logic is the safe line, not the real pace: a good player beats it. With a few
maxed SSRs and decent parents, a UG career comes well before logic expects it, and
the goal counts the moment you reach it.
