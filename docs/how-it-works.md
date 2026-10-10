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
  Umamusume client  <->  UmamusumeX server  <->  Archipelago room  <->  other players
       (unchanged)        (the "client")         (MultiServer)
```

- The **room** (archipelago.gg or your own Launcher > Host) holds the seed. It
  knows which item sits behind every check.
- The **UmamusumeX server** connects to the room as your slot. When you win a G1
  or finish a career, it tells the room "check X done"; the room sends the item
  behind it to whoever owns it. When an item for you arrives, the server applies
  it to your Archipelago save.
- The **game** needs nothing. It just sees mail in the present box, a new
  scenario on the career screen, or bigger numbers in training.

## Your saves

While `mod_archipelago` is on, your account plays a **separate save**:

- made the first time you connect, with your name and profile but a new
  player's collection (URA only, 5 trainees, R/SR cards);
- scouting is closed there (cards come from the multiworld);
- turning the mod off brings your normal save back (switch with the game closed);
- **each seed has its own save**: closing the server and coming back to the same
  room resumes it; joining another seed starts a new save and keeps the old one,
  so going back to the old room resumes it too. Your normal save is never touched.

## Logic

A career's rank score mostly depends on your buffs, so logic doesn't count items:
it estimates the best rank score you can reach with what you have:

```
estimate = base + 450 per training item + 400 per starting-stats item
         + 300 per stat-cap item + 1500 with a non-URA scenario
```

`base` is 10500 / 11500 / 12500 for relaxed / normal / expert
(`logic_difficulty`). A rank check (or the goal) is "in logic" once the estimate
reaches it. A goal above what every buff could reach only asks for every buff.
