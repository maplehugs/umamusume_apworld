# Options

Every option goes under `Umamusume Pretty Derby:` in your yaml. Defaults in
brackets.

## Goal

| Option | Values | What it does |
|---|---|---|
| `goal` | **rank_score**, g1_collector, all_scenarios | Finish one career at `goal_rank_score` (rank checks above that score aren't generated, so nothing sits past the goal); win `goal_g1_count` different G1s across careers; or finish a career in each of the 4 scenarios. |
| `goal_rank_score` | 14500-23900 [**20000**] | S is 14500, SS 17500, UG 19600, UG1 20000. 21000+ adds 2 Progressive Stat Cap items. |
| `goal_g1_count` | 5-34 [**24**] | For g1_collector (needs `g1_checks` on). |
| `logic_difficulty` | relaxed, **normal**, expert | How strong logic expects an unbuffed career to be. relaxed puts more buffs before each rank. |

## Pool

| Option | Values | What it does |
|---|---|---|
| `starting_trainees` | **shuffled**, default | Your Archipelago save starts with 5 random trainees, or a new account's usual five. (Don't write `random` here: in a yaml that picks one of the options at random.) |
| `trainee_count` | 0-103 [**15**] | Trainees shuffled in. Each one adds a "Finish a career with ..." check. |
| `support_count` | 0-122 [**20**] | SSR support cards shuffled in (trimmed when there's no room). |

## Checks

Turn whole groups off to make a shorter seed:

| Option | Default | Checks |
|---|---|---|
| `g1_checks` | on | 34: win each G1 |
| `scenario_rank_checks` | on | 20: rank B/A/S/SS/UG in each scenario |
| `global_rank_ladder` | on | 7: rank B+, A+, S+, SS+, UG1, UG2, UG3 in any scenario |
| `unique_race_checks` | on | 5: win 10/20/35/50/75 different races |
| `team_trials_checks` | 5 (0-10) | win your 1st, 2nd... Team Trials match. Adds up to 3 Progressive RP Recovery items. |

Always on: finish a career in each scenario (4) and finish a career with each
of your 5 starting trainees and each shuffled one (5 + `trainee_count`).

A short seed (about 40 checks): `g1_checks: false`, `scenario_rank_checks: false`,
`trainee_count: 8`.

## Traps

| Option | Values | What it does |
|---|---|---|
| `trap_percentage` | 0-100 [**20**] | Percent of filler that becomes traps. |
| `trap_cap` | 1-6 [**2**] | Most traps that hit one career; the rest wait for later careers. |
| `spicy_traps` | on/[**off**] | Also shuffle Amnesia (no starting buffs for a career). |

## Excluding single checks

Every Archipelago world supports these common options:

```yaml
Umamusume Pretty Derby:
  exclude_locations:          # never anything important here (only filler/traps)
    - Win Champions Cup
    - "Trackblazer: rank UG"
  priority_locations:         # something good is placed here
    - Win Arima Kinen
  start_inventory:            # start with these items
    Scenario: Grand Live: 1
  local_items: [Dream's Luck] # always in your own world
```

Use exact names from [items-and-checks.md](items-and-checks.md).
