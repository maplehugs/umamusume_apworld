# Changelog

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
