# FAQ

**Can the seed softlock me?**
No. Goal races of a career are never locked, rank checks a scenario can't reach
(or within 500 of a `rank_score` goal) aren't generated, and Team Trials checks only
ask for what your careers are expected to reach (with `team_trials_roulette` they
never hold progression). "Finish a <scenario> career" needs that scenario's final won; a lost
final just means another career, and it still counts for the trainee's check.
If something hangs, the server log says what it served: **Download logs** in the
panel's Connection section zips it for a bug report.

**What does a trap do, and for how long?**
Traps hit your **next** career, at most `trap_cap` (default 2) per career; the
rest wait. The web panel's Archipelago window lists each one with its effect. See
[items-and-checks.md](items-and-checks.md#traps-next-career-at-most-trap_cap-per-career).

**Does a +20% training item work right away?**
Its +50 cap does, on the running career. The +20% shows from the next training
screen: a screen already shown can't change (the game applies what it shows).

**Do 2nd places count for a G1?**
No, only wins. An Alarm Clock retry that wins does count.

**Can I run out of Legend Race tickets?**
No: the ladder races are free. (The ticket's in-game
maximum is 3; more would show as 0, so no extra tickets are handed out.)

**There's no Legend Race in the game.**
The game reads the ladder when it logs in. Go back to the title screen (or
restart the game); with the live sync plugin it shows by itself.

**Something in the game looks out of date after a seed switch or new items.**
If something in the game looks out of date (a hint level, the trainee list, ticket
counts), restart the game.

**Team Trials says error 2801.**
You have no team yet. Finish a career, then register a team in Team Trials > Edit Team.

**I wrote `starting_trainees: random` and got the usual five.**
`random` in a yaml means "pick one of the option's values at random". Use
`shuffled`.

**Do other players need anything?**
Only whoever generates needs the apworld. Players of other games need nothing
from this repo.

**"master.mdb is missing" / my game data is somewhere else?**
The launcher looks in the game folder; if it isn't there, it asks you to pick
your `master.mdb` (a file dialog) and remembers it. With more than one copy it
uses the newest, and it warns when the one it uses is old (a stale copy serves
old data). To pick another one later: run the launcher with `--mdb <path>`.
