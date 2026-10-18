# Changelog

## 0.13.0
- The server is in this repo now: `server/` is UmamusumePS (AGPL-3.0, by
  systemless10) with Archipelago support. The world moved to `apworld/`.
- Every account on the server plays Archipelago; a new seed starts the save over.
- Legend Race ladder works on the new server (C..SS+, `legend_race` goal too).
- Web panel is Archipelago only, with a Download logs button for bug reports.
- Linux server package with the race engines prebuilt (no Rust needed, Python
  3.11+). Windows: run `server/start-global.ps1` from the repo for now.
- `apworld/umamusume/tables.py` is the source of truth for ids; the server
  mirrors it.

## 0.12.0
Needs the matching server.
- The release now also has `umapd_archipelago.dll`, the optional Hachimi Edge
  plugin (live sync), prebuilt from `source_code_dll/`.
- Support cards arrive at limit break 0 instead of maxed. New item: Rainbow Uncap
  Crystal, one limit break for any SSR you pick (4 max a card). `uncap_crystals`
  (default 24, a deck of 6) are always in the pool; spare checks add up to half as
  many more at random.
- The Archipelago save has Support Pt and Monies to the game's cap, so leveling
  cards is free: the cards and crystals are the loot.
- `maxed_supports: true` keeps the old maxed cards (no crystals). Seeds from
  0.11.0 and older keep maxed cards too.
- Logic: a card counts half, the other half once 4 crystals can max it.
- Default seed: 51 cards, ~31 crystals, ~25 filler.

## 0.11.0
Needs the matching server.
- Any set of checks generates: items that don't fit are start inventory (most
  wanted stay in the pool: scenarios, trainees, cards, Progressive Training...).
  Everything off is a 24-check game that starts with the rest.
- `support_count` is a floor: half the spare checks deal more SSR cards, still
  even by stat (67 cards and 37 filler with the defaults, every SSR with
  everything on).
- `starting_scenario`: unity_cup, grand_live and trackblazer too.
- items-and-checks.md: what a seed holds with checks turned on and off.

## 0.10.1
- Check groups for `exclude_locations` / `priority_locations`: `Team Trials`,
  `G1`, `Fans`, `Legend Race`... (`exclude_locations: [Team Trials]` keeps the
  Team Trials checks but only filler and traps land there).

## 0.10.0
Needs the matching server.
- Team Trials checks hold multiworld items like any other check (50 more checks
  in the pool by default). `team_trials_roulette: true` brings back the old
  roulette of your own filler and traps (`team_trials_trap_percentage`).
- Trainee Awakening: one per trainee the seed gives you by default
  (`trainee_awakenings: one_per_trainee`, 20 with the defaults; was 3). One that
  arrives with every trainee maxed waits for the next trainee you claim.
- SSR support cards are dealt evenly by stat: 30 = 6 each of Speed, Stamina,
  Power, Guts and Wit (Friend/Group cards only past 100).
- Minor Starting Skill Points is rarer in the filler (weight 10, was 25).
- items-and-checks.md opens with the loot table: what a default seed holds, how
  many of each and what they do.
- The seed records its apworld version; the server warns when it
  doesn't match.

## 0.9.0
Needs the matching server.
- Team Trials checks are per race won (each of a match's 5, lost match or not),
  not per match: "Team Trials: win N races". Default 50 (was 10), up to 100.
- They hold your own filler now, `team_trials_trap_percentage` of it traps
  (default 25: 38 good, 12 traps of 50), instead of other players' items.
- Traps and boons stay queued until a career reaches its final (any place): a
  career given up or lost before it hands them back. Repeats of the same one wait
  for the next career instead of being used up together.
- Dream's Luck is no longer an item (too strong; it stays a separate server mod,
  off on the Archipelago save).
- Legend Race ladder: 10 rivals, C, C+, B, B+, A, A+, S, S+, SS, SS+ (was 5),
  each its own boss and course.
- Fan checks every 250k up to 3M (12, was 5).
- `g1_per_scenario` (off by default): win each G1 in each scenario, 136 more checks.
- Different races checks every 5 wins (5, 10 ... 75: 15 checks, was 5).
- `support_count` default 30 (was 20): more SSR cards, less filler.
- Team Trials RP on the Archipelago save: the 5-RP bar refills in 30 min (was
  10 h), halved per Progressive RP Recovery (15, 7.5, ~4 min).
- Tunnel Vision Trap's text: it turns off one stat's Progressive Training bonus;
  the training still gives its normal points.
- Tracker: each G1 shows its course, which of your trainees has it as a
  goal race (and which shuffled ones don't belong to you yet), and who has A
  aptitude for it; hinted checks show it too.

## 0.8.0
Needs the matching server.
- "Finish a <scenario> career" now needs the scenario's final won (1st in the
  turn-78 race). The trainee checks still only need the last turn.
- `g1_place` (1-3, default 1): a G1 check counts at that place or better.

## 0.7.1
- Logic counts SSR support cards: +300 to the estimate per card, up to 6 (a deck).
  They're progression items now. Ranks and goals come into logic sooner, closer
  to how fast a real player gets there.

## 0.7.0
Needs the matching server.
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
