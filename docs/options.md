# Options

Every option goes under `Umamusume Pretty Derby:` in your yaml. Defaults in
brackets.

## Goal

| Option | Values | What it does |
|---|---|---|
| `goal` | **rank_score**, g1_collector, all_scenarios, legend_race | Finish one career at `goal_rank_score` (rank checks above that score aren't generated, so nothing sits past the goal); win `goal_g1_count` different G1s across careers; finish a career in each of the 4 scenarios; or beat the SS+ Legend Race rival (needs `legend_ladder`). |
| `goal_rank_score` | 14500-23900 [**20000**] | S is 14500, SS 17500, UG 19600, UG1 20000. 21000+ adds 2 Progressive Stat Cap items. |
| `goal_g1_count` | 5-34 [**24**] | For g1_collector (needs `g1_checks` on). |
| `logic_difficulty` | relaxed, **normal**, expert | How strong logic expects an unbuffed career to be. relaxed puts more buffs before each rank. |

## Pool

| Option | Values | What it does |
|---|---|---|
| `starting_scenario` | **ura**, unity_cup, grand_live, trackblazer, shuffled | The scenario you start with; the other 3 are items. `shuffled` (or `random`) picks one at random. |
| `starting_trainees` | **shuffled**, default | Your Archipelago save starts with random trainees, or a new account's usual five. (Don't write `random` here: in a yaml that picks one of the options at random.) |
| `starting_trainee_count` | 1-10 [**5**] | How many random trainees you start with (shuffled). |
| `starting_supports` | 0-10 [**0**] | Random SSR support cards in your present box from the start, maxed. |
| `trainee_awakenings` | 0-108 [**one_per_trainee**] | Trainee Awakening items: each takes a random trainee you own (not yet maxed) to 5 stars and potential 5; with all of them maxed it waits for your next trainee. At most one per trainee the seed gives you (starting + `trainee_count`), which `one_per_trainee` is. |
| `trainee_count` | 0-103 [**15**] | Trainees shuffled in. Each one adds a "Finish a career with ..." check. |
| `support_count` | 0-122 [**30**] | SSR support cards at least, dealt evenly by stat (30 = 6 of each; Friend/Group only past 100). Spare checks deal more: 1 card per 3 (54 with the defaults). |

## Checks

Turn whole groups off to make a shorter seed:

| Option | Default | Checks |
|---|---|---|
| `g1_checks` | on | 34: win each G1 |
| `g1_place` | 1 (1-3) | The place a G1 check needs: 1 = win, 2 = 2nd or better, 3 = top 3. |
| `g1_per_scenario` | off | 136 more: win each G1 in each scenario ("Win Arima Kinen in Grand Live"), in logic once you have that scenario. Needs `g1_checks`; the plain G1 checks and the g1_collector goal still count a G1 won anywhere. |
| `scenario_rank_checks` | on | 20: rank B/A/S/SS/UG in each scenario |
| `global_rank_ladder` | on | 7: rank B+, A+, S+, SS+, UG1, UG2, UG3 in any scenario |
| `unique_race_checks` | on | 15: win 5, 10, 15 ... 75 different races |
| `legend_ladder` | on | 10: beat the C, C+, B, B+, A, A+, S, S+, SS and SS+ rivals in Legend Race, in turn (free entries on the Archipelago save) |
| `fan_checks` | on | 12: reach 250k, 500k, 750k ... 3M fans over all your careers (~250k per career) |
| `team_trials_checks` | 50 (0-100) | win your 1st, 2nd... Team Trials race (each match has 5; a lost match's wins count too); 0 turns Team Trials checks off. They hold multiworld items like any other check (or your own filler with `team_trials_roulette`). Adds up to 3 Progressive RP Recovery items. |
| `team_trials_roulette` | **false** | true: Team Trials checks hold your own good filler and traps instead of multiworld items (never progression). |
| `team_trials_trap_percentage` | 25 (0-100) | With `team_trials_roulette`: percent of the Team Trials checks that hold a trap (25 with 50 checks = 12 traps, 38 good). |

Always on: finish a career in each scenario (4) and finish a career with each
of your starting trainees and each shuffled one (`starting_trainee_count` + `trainee_count`).

A short seed (about 40 checks): `g1_checks: false`, `scenario_rank_checks: false`,
`trainee_count: 8`.

## Traps

| Option | Values | What it does |
|---|---|---|
| `trap_percentage` | 0-100 [**20**] | Percent of the rest of your filler that becomes traps (the Team Trials roulette has its own, above). |
| `trap_cap` | 1-6 [**2**] | Most traps that hit one career (one of each); the rest and repeats wait for later careers. |
| `spicy_traps` | on/[**off**] | Also shuffle Amnesia (no starting buffs for a career). |
| `trap_weights` | see below | How often each trap is picked (relative; 0 = never). Leave a trap out to keep its default. |

```yaml
  trap_weights:
    Bad Mood Trap: 15
    Bad Condition Trap: 15
    Low Energy Trap: 10
    Tunnel Vision Trap: 15
    Butterfingers Trap: 15
    Amnesia Trap: 0
```

## Excluding checks

Every Archipelago world supports these common options. They take check names or
a whole group: `G1`, `G1 per scenario`, `Scenario finishes`, `Scenario ranks`,
`Global ranks`, `Different races`, `Fans`, `Legend Race`, `Team Trials`,
`Trainees`. Excluding a group keeps its checks but fills them only with filler
and traps (from any game in the multiworld), so nobody waits on them; e.g.
`exclude_locations: [Team Trials]` for a player who doesn't want the RP grind to
hold anything important.

```yaml
Umamusume Pretty Derby:
  exclude_locations:          # never anything important here (only filler/traps)
    - Team Trials
    - Win Champions Cup
    - "Trackblazer: rank UG"
  priority_locations:         # something good is placed here
    - Win Arima Kinen
  start_inventory:            # start with these items
    Scenario: Grand Live: 1
  local_items: [Trainee Awakening] # always in your own world
```

Use exact names from [items-and-checks.md](items-and-checks.md).
