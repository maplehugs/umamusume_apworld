from dataclasses import dataclass

from Options import Choice, DefaultOnToggle, NamedRange, OptionDict, PerGameCommonOptions, Range, Toggle


class Goal(Choice):
    """rank_score: finish one career at or above Goal Rank Score. Rank checks above
    that score aren't generated (nothing sits past the goal).
    g1_collector: win Goal G1 Count different G1s (across careers).
    all_scenarios: finish a career in each of the 4 scenarios (needs all 3 unlocks).
    legend_race: beat the SS+ Legend Race rival (needs legend_ladder on). A short game."""

    display_name = "Goal"
    option_rank_score = 0
    option_g1_collector = 1
    option_all_scenarios = 2
    option_legend_race = 3
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
    """shuffled: your Archipelago save starts with random trainees (starting_trainee_count).
    default: a new account's usual five (Vodka, Daiwa Scarlet, Gold Ship...).
    (Not "random": in a yaml that word picks one of the options at random.)"""

    display_name = "Starting Trainees"
    option_shuffled = 0
    option_default = 1
    default = 0


class G1Place(Range):
    """The place a G1 check needs: 1 = win it, 2 = 2nd or better, 3 = top 3."""

    display_name = "G1 Place"
    range_start = 1
    range_end = 3
    default = 1


class G1PerScenario(Toggle):
    """Also a check for winning each G1 in each scenario (34 x 4 = 136 more), each
    in logic once you have that scenario. Needs g1_checks; the plain G1 checks (and
    the g1_collector goal) still count a G1 won in any scenario."""

    display_name = "G1 Per Scenario"


class StartingScenario(Choice):
    """The scenario you start with; the other 3 are items. shuffled: one picked at
    random (so does `random`, the YAML's own random pick)."""

    display_name = "Starting Scenario"
    option_ura = 0
    option_shuffled = 1
    option_unity_cup = 2
    option_grand_live = 3
    option_trackblazer = 4
    default = 0


class StartingTraineeCount(Range):
    """How many random trainees the save starts with (with starting_trainees: shuffled)."""

    display_name = "Starting Trainee Count"
    range_start = 1
    range_end = 10
    default = 5


class StartingSupports(Range):
    """Random SSR support cards in your present box from the start, maxed.
    They're not among the shuffled ones."""

    display_name = "Starting Support Cards"
    range_start = 0
    range_end = 10
    default = 0


class TraineeAwakenings(NamedRange):
    """Trainee Awakening items: each takes a random trainee you own, not yet maxed,
    to 5 stars and potential level 5; with every one maxed it waits for your next
    trainee. At most one per trainee the seed gives you (starting ones plus
    trainee_count); one_per_trainee = exactly that."""

    display_name = "Trainee Awakenings"
    range_start = 0
    range_end = 108
    default = 108
    special_range_names = {"one_per_trainee": 108}


class FanChecks(DefaultOnToggle):
    """Checks for fans summed over every finished career, every 250k up to 3M
    (12; a career brings ~250k)."""

    display_name = "Fan Checks"


class TraineeCount(Range):
    """Extra trainees shuffled in, each with a "Finish a career with ..." check.
    Your 5 starting trainees are always yours."""

    display_name = "Trainee Count"
    range_start = 0
    range_end = 103
    default = 15


class SupportCount(Range):
    """SSR support cards in the pool at least (dealt evenly by stat: 30 = 6 of each).
    A seed with more checks than items deals 1 more card per 2 spare checks."""

    display_name = "Support Card Count"
    range_start = 0
    range_end = 122
    default = 30


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
    """Win 5, 10, 15 ... 75 different races across all careers (15 checks)."""

    display_name = "Unique Race Checks"


class LegendLadder(DefaultOnToggle):
    """A rival ladder in Legend Race: beat the C, C+, B, B+ ... SS and SS+ rivals in
    turn (10 checks). Entries are free on the Archipelago save, so it never runs out."""

    display_name = "Legend Race Ladder"


class TeamTrialsChecks(Range):
    """Team Trials races won that are checks (the 1st, the 2nd... of each match's 5,
    lost match or not). 0 = off. They hold multiworld items like any other check,
    or your own filler with team_trials_roulette."""

    display_name = "Team Trials Checks"
    range_start = 0
    range_end = 100
    default = 50


class TeamTrialsRoulette(Toggle):
    """Team Trials checks hold your own good filler and traps instead of multiworld
    items: never progression, nobody waits on your RP."""

    display_name = "Team Trials Roulette"


class TeamTrialsTrapPercentage(Range):
    """With team_trials_roulette: percent of the Team Trials checks that hold a trap;
    the rest hold good filler (25 with 50 checks = 12 traps, 38 good)."""

    display_name = "Team Trials Trap Percentage"
    range_start = 0
    range_end = 100
    default = 25


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
    """Also shuffle Amnesia (no starting buffs for a career): sets its weight to 5
    if trap_weights leaves it at 0."""

    display_name = "Spicy Traps"


class TrapWeights(OptionDict):
    """How often each trap is picked when a filler slot becomes a trap (relative
    weights; 0 = never). Missing traps keep their default."""

    display_name = "Trap Weights"
    valid_keys = frozenset({
        "Bad Mood Trap", "Bad Condition Trap", "Low Energy Trap",
        "Tunnel Vision Trap", "Butterfingers Trap", "Amnesia Trap",
    })
    default = {
        "Bad Mood Trap": 15,
        "Bad Condition Trap": 15,
        "Low Energy Trap": 10,
        "Tunnel Vision Trap": 15,
        "Butterfingers Trap": 15,
        "Amnesia Trap": 0,
    }


@dataclass
class UmaOptions(PerGameCommonOptions):
    goal: Goal
    goal_rank_score: GoalRankScore
    goal_g1_count: GoalG1Count
    logic_difficulty: LogicDifficulty
    starting_scenario: StartingScenario
    starting_trainees: StartingTrainees
    starting_trainee_count: StartingTraineeCount
    starting_supports: StartingSupports
    trainee_count: TraineeCount
    support_count: SupportCount
    trainee_awakenings: TraineeAwakenings
    g1_checks: G1Checks
    g1_place: G1Place
    g1_per_scenario: G1PerScenario
    scenario_rank_checks: ScenarioRankChecks
    global_rank_ladder: GlobalRankLadder
    unique_race_checks: UniqueRaceChecks
    legend_ladder: LegendLadder
    team_trials_checks: TeamTrialsChecks
    team_trials_roulette: TeamTrialsRoulette
    team_trials_trap_percentage: TeamTrialsTrapPercentage
    fan_checks: FanChecks
    trap_percentage: TrapPercentage
    trap_cap: TrapCap
    spicy_traps: SpicyTraps
    trap_weights: TrapWeights
