# Changelog

## 0.7.1
- Logic counts SSR support cards: +300 to the estimate per card, up to 6 (a deck).
  They're progression items now. Ranks and goals come into logic sooner, closer
  to how fast a real player gets there.

## 0.7.0
Needs the matching UmamusumeX server.
- `starting_scenario: shuffled`: start with a random scenario; the others (URA
  included, now an item) are found in the multiworld.
- `starting_trainee_count` (1-10, default 5) random starting trainees.
- `starting_supports` (0-10): random SSR support cards from the start, maxed.
- Trainee Awakening item (`trainee_awakenings`, default 3): a random trainee you
  own goes to 5 stars and potential level 5.
- `fan_checks` (on): reach 250k, 500k, 1M, 2M and 3M fans over your careers.
- New goal `legend_race`: beat the SS+ Legend Race rival.
- `trap_weights`: how often each trap shows up (0 = never).

## 0.6.2
- Team Trials is a support roulette: each win sends another player one of their
  useful items, filler or traps (never progression). Played alone, it holds your
  own non-progression items. Traps can land anywhere again.
- `team_trials_checks` goes up to 30 (default 10). Logic stops asking for more
  past the 10th win.

## 0.6.1
- Team Trials checks only ever hold filler or traps (from any game). (Replaced in 0.6.2.)
- A scenario's rank check is only generated if logic can reach it: on `relaxed`,
  URA Finale: rank UG needs 19600 but URA tops out at 19250 with every item, so
  it's gone there (it made the seed fail its accessibility check).

## 0.6.0
- Legend Race rival ladder (`legend_ladder`, on by default): beat the B, A, S,
  SS and SS+ rivals in turn, 5 checks. The Archipelago save always sees its
  current rival and its entries cost no ticket, so it can't get stuck.

## 0.5.0
- New goal `all_scenarios`: finish a career in each of the 4 scenarios.
- With the `rank_score` goal, rank checks above the goal score are not generated,
  so no item ever sits past the goal (UG2/UG3 are gone at the default 20000).
- `starting_trainees: shuffled` (default): the Archipelago save starts with 5
  random trainees instead of a new account's usual five (`default`). The value
  is not called `random`: in a yaml that word picks an option at random.

## 0.4.0
- Filler is now small permanent buffs and boons: Minor Starting Stats (+5 all),
  Minor Starting Skill Points (+50), Pep Talk, Lucky Charm and RP Refill (with
  Team Trials checks). The mail filler (Monies, clocks, crystals...) is gone.
- SSR support cards from the multiworld arrive maxed when claimed.

## 0.3.0
- Team Trials checks: win your 1st..Nth match (`team_trials_checks`, 0-10).
- Progressive RP Recovery (up to 3): Team Trials RP refills twice as fast each.
- Each seed has its own save; going back to a seed resumes it.

## 0.2.1
- `logic_base` in slot data, for the server's built-in tracker.

## 0.2.0
- First release: 34 G1 checks, scenario finishes and rank tiers, global rank
  ladder, unique-race milestones, trainee careers; scenarios, per-stat training,
  starting stats/SP, stat caps, Training Guard, Dream's Luck, trainees and SSR
  supports as items; next-career traps; goals `rank_score` and `g1_collector`.
