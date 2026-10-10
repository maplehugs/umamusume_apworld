# FAQ

**Can the seed softlock me?**
Goal races of a career are never locked, rank checks above a `rank_score` goal
aren't generated, and a lost URA final still counts as reaching the end of the
career (finish and trainee checks). If something hangs, the server log
(dashboard **Saves & logs**) says what it served.

**What does a trap do, and for how long?**
Traps hit your **next** career, at most `trap_cap` (default 2) per career; the
rest wait. The dashboard lists each one with its effect and turns left. See
[items-and-checks.md](items-and-checks.md#traps-next-career-at-most-trap_cap-per-career).

**Does a +20% training item work right away?**
Its +50 cap does, on the running career. The +20% shows from the next training
screen: a screen already shown can't change (the game applies what it shows).

**Do 2nd places count for a G1?**
No, only wins. An Alarm Clock retry that wins does count.

**Can I run out of Legend Race tickets?**
Not on the Archipelago save: its ladder races are free. (The ticket's in-game
maximum is 3; more would show as 0, so no extra tickets are handed out.)

**Team Trials says it's tallying.**
On the Archipelago save Team Trials is always open. On a normal save the
official daily window applies.

**I wrote `starting_trainees: random` and got the usual five.**
`random` in a yaml means "pick one of the option's values at random". Use
`shuffled`.

**Do other players need anything?**
Only whoever generates needs the apworld. Players of other games need nothing
from this repo.
