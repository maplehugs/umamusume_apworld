"""Umamusume: Pretty Derby, played on the UmamusumeX private server, whose
Archipelago mod applies the items and reports the checks. tables.py is the
server's own table (tools/sync_tables.py), so both sides agree on every id."""

from BaseClasses import Item, ItemClassification as IC, Location, Region
from worlds.AutoWorld import World

from . import tables
from .options import UmaOptions

ITEMS = tables.item_name_to_id()
LOCATIONS = tables.location_name_to_id()
TRAINING = [f"Progressive {s} Training" for s in tables.STATS]
BASE_SCORE = {0: 10500, 1: 11500, 2: 12500}  # logic_difficulty -> unbuffed career
SCENARIO_BONUS = 1500  # a non-URA scenario's own caps and gains
SUPPORT_BONUS, SUPPORT_MAX = 300, 6  # each maxed SSR (a deck holds 6)
# Filler is small permanent buffs and next-career boons: support cards already
# arrive maxed, and mail items (Monies, clocks...) did nothing for a run.
FILLER_WEIGHTS = {
    "Minor Starting Stats": 30,
    "Minor Starting Skill Points": 10,
    "Pep Talk": 15,
    "Lucky Charm": 15,
}
TRAP_WEIGHTS = {
    "Bad Mood Trap": 15,
    "Bad Condition Trap": 15,
    "Low Energy Trap": 10,
    "Tunnel Vision Trap": 15,
    "Butterfingers Trap": 15,
    "Amnesia Trap": 0,  # spicy_traps or trap_weights turn it on
}


class UmaItem(Item):
    game = tables.GAME


class UmaLocation(Location):
    game = tables.GAME


class UmamusumeWorld(World):
    """Raise horse girls on your own server: G1 wins and finished careers send items
    across the multiworld; trainees, scenarios and permanent stat buffs come back."""

    game = tables.GAME
    options_dataclass = UmaOptions
    options: UmaOptions
    item_name_to_id = ITEMS
    item_name_groups = {"Supports": {n for n in ITEMS if n.startswith("Support: ")}}
    location_name_to_id = LOCATIONS
    topology_present = False

    def generate_early(self) -> None:
        o = self.options
        self.start_scenario = (
            self.random.choice(sorted(tables.SCENARIOS)) if o.starting_scenario == o.starting_scenario.option_shuffled else 1
        )
        if o.starting_trainees == o.starting_trainees.option_shuffled:
            self.starters = self.random.sample(sorted(tables.TRAINEES), o.starting_trainee_count.value)
        else:
            self.starters = list(tables.STARTING_TRAINEES)
        extra = sorted(set(tables.TRAINEES) - set(self.starters))
        self.trainees = self.random.sample(extra, min(o.trainee_count.value, len(extra)))
        # Dealt round by round, one of each stat per round in a random order, so any
        # count is even (30 = 6 Speed, 6 Stamina...); Friend/Group only past 100.
        pools = {k: self.random.sample(v, len(v)) for k, v in tables.SUPPORT_TYPES.items()}
        stats = [pools[s] for s in tables.STATS]
        cards = []
        for i in range(max(map(len, stats))):
            cards += [p[i] for p in self.random.sample(stats, len(stats)) if i < len(p)]
        cards += self.random.sample(pools["Friend"] + pools["Group"], len(pools["Friend"] + pools["Group"]))
        cards = cards[:o.starting_supports.value + o.support_count.value]
        self.start_supports, self.supports = cards[:o.starting_supports.value], cards[o.starting_supports.value:]
        if o.goal == o.goal.option_legend_race and not o.legend_ladder:
            raise Exception(f"{self.player_name}: the legend_race goal needs legend_ladder on")
        self.caps = 2 if self.options.goal_rank_score.value >= 21000 else 0

    # ---- logic: an estimated best rank score, like Yacht Dice's score estimate
    def estimate(self, state, scenario: int | None = None) -> int:
        p = self.player
        est = BASE_SCORE[self.options.logic_difficulty.value]
        est += 450 * sum(state.count(n, p) for n in TRAINING)
        est += 400 * state.count("Progressive Starting Stats", p)
        est += 300 * state.count("Progressive Stat Cap", p)
        est += SUPPORT_BONUS * min(SUPPORT_MAX, len(self.start_supports) + state.count_group("Supports", p))
        if scenario is None:  # any scenario: the best one owned
            owned = self.start_scenario != 1 or any(
                state.has(n, p) for sid, n in tables.SCENARIO_ITEM.items() if sid != 1)
        else:
            owned = scenario != 1
        return est + (SCENARIO_BONUS if owned else 0)

    def max_estimate(self, scenario: int | None = None) -> int:
        return (
            BASE_SCORE[self.options.logic_difficulty.value]
            + 450 * 3 * len(TRAINING)
            + 400 * 5
            + 300 * self.caps
            + SUPPORT_BONUS * min(SUPPORT_MAX, len(self.start_supports) + len(self.supports))
            + (0 if scenario == 1 else SCENARIO_BONUS)
        )

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        p, o = self.player, self.options

        def add(name, rule=None):
            loc = UmaLocation(p, name, LOCATIONS.get(name), menu)
            if rule:
                loc.access_rule = rule
            menu.locations.append(loc)
            return loc

        # A rank_score goal ends the game at that score: a rank check above it
        # would hold its item past the goal.
        cap = o.goal_rank_score.value if o.goal == o.goal.option_rank_score else 10**9
        if o.g1_checks:
            for g1 in tables.G1_RACES:
                add(tables.g1_location(g1))
        for sid in tables.SCENARIOS:
            item = None if sid == self.start_scenario else tables.SCENARIO_ITEM[sid]

            def has(s, i=item):
                return i is None or s.has(i, p)

            add(tables.finish_location(sid), has)
            if o.g1_checks and o.g1_per_scenario:
                for g1 in tables.G1_RACES:
                    add(tables.g1_scenario_location(g1, sid), has)
            if o.scenario_rank_checks:
                for tier, score in tables.RANK_TIERS:
                    if score > cap or score > self.max_estimate(sid):  # e.g. URA UG on relaxed
                        continue
                    add(tables.rank_location(sid, tier),
                        lambda s, has=has, sid=sid, score=score: has(s) and self.estimate(s, sid) >= score)
        if o.global_rank_ladder:
            for tier, score in tables.GLOBAL_RANKS:
                if score > cap:
                    continue
                add(tables.global_rank_location(tier), lambda s, score=score: self.estimate(s) >= score)
        if o.unique_race_checks:
            for n in tables.UNIQUE_RACE_MILESTONES:  # ~8 wins per career
                add(tables.unique_races_location(n), lambda s, n=n: self.estimate(s) >= 9000 + 100 * n)
        if o.legend_ladder:
            # The rival is raced with one of your trained umas: in logic once your
            # careers are expected to reach that rival's rank.
            for tier, rank_id, _row, _stats in tables.LEGEND_LADDER:
                need = tables.LEGEND_RANK_SCORE[rank_id]
                add(tables.legend_location(tier), lambda s, need=need: self.estimate(s) >= need)
        if o.fan_checks:  # ~250k fans per career
            for n in tables.FAN_MILESTONES:
                add(tables.fans_location(n), lambda s, n=n: self.estimate(s) >= tables.fans_logic(n))
        # One race won per check, in the multiworld like any other; with
        # team_trials_roulette, our own filler instead (team_trials_trap_percentage
        # of it traps, shuffled, never progression).
        tt = o.team_trials_checks.value
        roulette = []
        if o.team_trials_roulette:
            roulette = [self.trap_name() for _ in range(tt * o.team_trials_trap_percentage.value // 100)]
            roulette += [self.good_filler_name() for _ in range(tt - len(roulette))]
            self.random.shuffle(roulette)
        for n in range(1, tt + 1):  # ~3 races won per match
            loc = add(tables.team_trials_location(n),
                      lambda s, n=n: self.estimate(s) >= 11000 + 300 * min(n // 3, 10))
            if roulette:
                loc.place_locked_item(self.create_item(roulette[n - 1]))
        for card in self.starters:
            add(tables.trainee_location(card))
        for card in self.trainees:
            item = f"Trainee: {tables.TRAINEES[card]}"
            add(tables.trainee_location(card), lambda s, i=item: s.has(i, p))

        if o.goal == o.goal.option_all_scenarios:
            scenarios = [n for sid, n in tables.SCENARIO_ITEM.items() if sid != self.start_scenario]
            goal = add("Goal", lambda s: s.has_all(scenarios, p))
        elif o.goal == o.goal.option_legend_race:
            goal = add("Goal", lambda s: self.estimate(s) >= 19200)  # the SS+ rival's rank
        elif o.goal == o.goal.option_g1_collector:
            if not o.g1_checks:
                raise Exception(f"{self.player_name}: g1_collector needs g1_checks on")
            need = o.goal_g1_count.value
            goal = add("Goal", lambda s: self.estimate(s) >= 11000 + 150 * need)
        else:
            # A goal past what every buff can be expected to reach is still the goal,
            # but logic only asks for every buff.
            score = min(o.goal_rank_score.value, self.max_estimate())
            goal = add("Goal", lambda s: self.estimate(s) >= score)
        goal.place_locked_item(UmaItem("Victory", IC.progression, None, p))
        self.multiworld.completion_condition[p] = lambda s: s.has("Victory", p)
        self.multiworld.regions.append(menu)

    def create_item(self, name: str) -> UmaItem:
        # Support cards count in logic (a maxed SSR deck is most of a good career).
        if name in TRAINING or name.startswith(("Scenario:", "Trainee:", "Support:")) or name in (
            "Progressive Starting Stats",
            "Progressive Stat Cap",
        ):
            cls = IC.progression
        elif name in tables.PROGRESSIVE:  # Trainee Awakening too
            cls = IC.useful
        elif name in tables.TRAPS:
            cls = IC.trap
        else:
            cls = IC.filler
        return UmaItem(name, cls, ITEMS[name], self.player)

    def get_filler_item_name(self) -> str:
        if self.random.randrange(100) < self.options.trap_percentage.value:
            return self.trap_name()
        return self.good_filler_name()

    def trap_name(self) -> str:
        """A trap by trap_weights; good filler if every weight is 0."""
        traps = {**TRAP_WEIGHTS, **self.options.trap_weights.value}
        if self.options.spicy_traps and not traps.get("Amnesia Trap"):
            traps["Amnesia Trap"] = 5
        if any(traps.values()):
            return self.random.choices(list(traps), list(traps.values()))[0]
        return self.good_filler_name()

    def good_filler_name(self) -> str:
        filler = dict(FILLER_WEIGHTS)
        if self.options.team_trials_checks:
            filler["RP Refill"] = 15
        return self.random.choices(list(filler), list(filler.values()))[0]

    def create_items(self) -> None:
        names = [n for sid, n in tables.SCENARIO_ITEM.items() if sid != self.start_scenario]
        names += ["Trainee Awakening"] * min(self.options.trainee_awakenings.value,
                                             len(self.starters) + len(self.trainees))
        names += [n for n in TRAINING for _ in range(3)]
        names += ["Progressive Starting Stats"] * 5 + ["Progressive Starting Skill Points"] * 3
        names += ["Progressive Training Guard"] * 2 + ["Progressive Stat Cap"] * self.caps
        if o_tt := self.options.team_trials_checks.value:
            names += ["Progressive RP Recovery"] * min(3, o_tt)
        names += [f"Trainee: {tables.TRAINEES[c]}" for c in self.trainees]
        room = len(self.multiworld.get_unfilled_locations(self.player)) - len(names)
        if room < 0:
            raise Exception(f"{self.player_name}: {-room} more items than checks; turn checks on")
        supports = self.supports[:room]
        names += [f"Support: {tables.SSR_SUPPORTS[s]}" for s in supports]
        names += [self.get_filler_item_name() for _ in range(room - len(supports))]
        self.multiworld.itempool += [self.create_item(n) for n in names]

    def fill_slot_data(self) -> dict:
        o = self.options
        return {
            "goal": o.goal.current_key,
            "goal_rank_score": o.goal_rank_score.value,
            "goal_g1_count": o.goal_g1_count.value,
            "trap_cap": o.trap_cap.value,
            "world_version": tables.APWORLD_VERSION,  # the server warns on a mismatch
            "g1_place": o.g1_place.value,
            "g1_per_scenario": bool(o.g1_checks and o.g1_per_scenario),
            "logic_base": BASE_SCORE[o.logic_difficulty.value],  # the server's tracker
            "team_trials_checks": o.team_trials_checks.value,
            "trainees": self.trainees,
            "starting_trainees": self.starters,
            "starting_scenario": self.start_scenario,
            "starting_supports": self.start_supports,
        }
