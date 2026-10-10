from dataclasses import dataclass

from Options import Choice, DefaultOnToggle, PerGameCommonOptions, Range, Toggle


class Goal(Choice):
    """rank_score: finish one career at or above Goal Rank Score. Rank checks above
    that score aren't generated (nothing sits past the goal).
    g1_collector: win Goal G1 Count different G1s (across careers).
    all_scenarios: finish a career in each of the 4 scenarios (needs all 3 unlocks)."""

    display_name = "Goal"
    option_rank_score = 0
    option_g1_collector = 1
    option_all_scenarios = 2
    default = 0


class GoalRankScore(Range):
    """Rank score the goal career needs. UG is 19600, UG1 20000, SS 17500, S 14500.
    21000 or more adds two Progressive Stat Cap items so it stays reachable."""

    display_name = "Goal Rank Score"
    range_start = 14500
    range_end = 23900
    default = 20000


class GoalG1Count(Range):
    """Different G1s to win for the g1_collector goal (34 exist)."""

    display_name = "Goal G1 Count"
    range_start = 5
    range_end = 34
    default = 24


class LogicDifficulty(Choice):
    """How strong logic assumes an unbuffed career is. relaxed expects more buffs
    before a rank is "in logic"; expert expects fewer."""

    display_name = "Logic Difficulty"
    option_relaxed = 0
    option_normal = 1
    option_expert = 2
    default = 1


class StartingTrainees(Choice):
    """shuffled: your Archipelago save starts with 5 random trainees.
    default: a new account's usual five (Vodka, Daiwa Scarlet, Gold Ship...).
    (Not "random": in a yaml that word picks one of the options at random.)"""

    display_name = "Starting Trainees"
    option_shuffled = 0
    option_default = 1
    default = 0


class TraineeCount(Range):
    """Extra trainees shuffled in, each with a "Finish a career with ..." check.
    Your 5 starting trainees are always yours."""

    display_name = "Trainee Count"
    range_start = 0
    range_end = 103
    default = 15


class SupportCount(Range):
    """SSR support cards shuffled in (trimmed if there is no room)."""

    display_name = "Support Card Count"
    range_start = 0
    range_end = 122
    default = 20


class G1Checks(DefaultOnToggle):
    """A check for winning each of the 34 G1s."""

    display_name = "G1 Checks"


class ScenarioRankChecks(DefaultOnToggle):
    """Rank B/A/S/SS/UG checks in each of the 4 scenarios (20 checks)."""

    display_name = "Scenario Rank Checks"


class GlobalRankLadder(DefaultOnToggle):
    """Rank B+, A+, S+, SS+, UG1, UG2, UG3 in any scenario (7 checks)."""

    display_name = "Global Rank Ladder"


class UniqueRaceChecks(DefaultOnToggle):
    """Win 10/20/35/50/75 different races across all careers (5 checks)."""

    display_name = "Unique Race Checks"


class LegendLadder(DefaultOnToggle):
    """A rival ladder in Legend Race: beat the B, A, S, SS and SS+ rivals in turn
    (5 checks). Entries are free on the Archipelago save, so it never runs out."""

    display_name = "Legend Race Ladder"


class TeamTrialsChecks(Range):
    """Team Trials match wins that are checks (the 1st win, the 2nd...). 0 = none.
    They're a support roulette: each holds another player's useful item, filler or trap."""

    display_name = "Team Trials Checks"
    range_start = 0
    range_end = 30
    default = 10


class TrapPercentage(Range):
    """Percent of filler slots that become traps."""

    display_name = "Trap Percentage"
    range_start = 0
    range_end = 100
    default = 20


class TrapCap(Range):
    """Most traps that hit one career; the rest wait for the next ones."""

    display_name = "Traps Per Career"
    range_start = 1
    range_end = 6
    default = 2


class SpicyTraps(Toggle):
    """Also shuffle Amnesia (no starting buffs for a career)."""

    display_name = "Spicy Traps"


@dataclass
class UmaOptions(PerGameCommonOptions):
    goal: Goal
    goal_rank_score: GoalRankScore
    goal_g1_count: GoalG1Count
    logic_difficulty: LogicDifficulty
    starting_trainees: StartingTrainees
    trainee_count: TraineeCount
    support_count: SupportCount
    g1_checks: G1Checks
    scenario_rank_checks: ScenarioRankChecks
    global_rank_ladder: GlobalRankLadder
    unique_race_checks: UniqueRaceChecks
    legend_ladder: LegendLadder
    team_trials_checks: TeamTrialsChecks
    trap_percentage: TrapPercentage
    trap_cap: TrapCap
    spicy_traps: SpicyTraps
