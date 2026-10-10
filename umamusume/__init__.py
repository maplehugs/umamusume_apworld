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
FILLER_WEIGHTS = {
    "5000 Support Points": 25,
    "3 Alarm Clocks": 20,
    "Gold Uncap Crystal": 15,
    "Rainbow Uncap Crystal": 10,
    "Pep Talk": 10,
    "Lucky Charm": 10,
    "20000 Monies": 10,
    "300 Carats": 5,
}
TRAP_WEIGHTS = {
    "Bad Mood Trap": 15,
    "Bad Condition Trap": 15,
    "Low Energy Trap": 10,
    "Tunnel Vision Trap": 15,
    "Butterfingers Trap": 15,
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
    location_name_to_id = LOCATIONS
    topology_present = False

    def generate_early(self) -> None:
        extra = sorted(set(tables.TRAINEES) - set(tables.STARTING_TRAINEES))
        self.trainees = self.random.sample(extra, self.options.trainee_count.value)
        self.supports = self.random.sample(sorted(tables.SSR_SUPPORTS), self.options.support_count.value)
        self.caps = 2 if self.options.goal_rank_score.value >= 21000 else 0

    # ---- logic: an estimated best rank score, like Yacht Dice's score estimate
    def estimate(self, state, scenario: int | None = None) -> int:
        p = self.player
        est = BASE_SCORE[self.options.logic_difficulty.value]
        est += 450 * sum(state.count(n, p) for n in TRAINING)
        est += 400 * state.count("Progressive Starting Stats", p)
        est += 300 * state.count("Progressive Stat Cap", p)
        if scenario is None:  # any scenario: the best one owned
            owned = any(state.has(n, p) for n in tables.SCENARIO_ITEM.values())
        else:
            owned = scenario != 1
        return est + (SCENARIO_BONUS if owned else 0)

    def max_estimate(self) -> int:
        return (
            BASE_SCORE[self.options.logic_difficulty.value]
            + 450 * 3 * len(TRAINING)
            + 400 * 5
            + 300 * self.caps
            + SCENARIO_BONUS
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

        if o.g1_checks:
            for g1 in tables.G1_RACES:
                add(tables.g1_location(g1))
        for sid in tables.SCENARIOS:
            item = tables.SCENARIO_ITEM.get(sid)

            def has(s, i=item):
                return i is None or s.has(i, p)

            add(tables.finish_location(sid), has)
            if o.scenario_rank_checks:
                for tier, score in tables.RANK_TIERS:
                    add(tables.rank_location(sid, tier),
                        lambda s, has=has, sid=sid, score=score: has(s) and self.estimate(s, sid) >= score)
        if o.global_rank_ladder:
            for tier, score in tables.GLOBAL_RANKS:
                add(tables.global_rank_location(tier), lambda s, score=score: self.estimate(s) >= score)
        if o.unique_race_checks:
            for n in tables.UNIQUE_RACE_MILESTONES:  # ~8 wins per career
                add(tables.unique_races_location(n), lambda s, n=n: self.estimate(s) >= 9000 + 100 * n)
        for card in tables.STARTING_TRAINEES:
            add(tables.trainee_location(card))
        for card in self.trainees:
            item = f"Trainee: {tables.TRAINEES[card]}"
            add(tables.trainee_location(card), lambda s, i=item: s.has(i, p))

        if o.goal == o.goal.option_g1_collector:
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
        if name in TRAINING or name.startswith(("Scenario:", "Trainee:")) or name in (
            "Progressive Starting Stats",
            "Progressive Stat Cap",
        ):
            cls = IC.progression
        elif name.startswith("Support:") or name in tables.PROGRESSIVE:
            cls = IC.useful
        elif name in tables.TRAPS:
            cls = IC.trap
        else:
            cls = IC.filler
        return UmaItem(name, cls, ITEMS[name], self.player)

    def get_filler_item_name(self) -> str:
        if self.random.randrange(100) < self.options.trap_percentage.value:
            traps = dict(TRAP_WEIGHTS)
            if self.options.spicy_traps:
                traps["Amnesia Trap"] = 5
            return self.random.choices(list(traps), list(traps.values()))[0]
        return self.random.choices(list(FILLER_WEIGHTS), list(FILLER_WEIGHTS.values()))[0]

    def create_items(self) -> None:
        names = list(tables.SCENARIO_ITEM.values()) + ["Dream's Luck"]
        names += [n for n in TRAINING for _ in range(3)]
        names += ["Progressive Starting Stats"] * 5 + ["Progressive Starting Skill Points"] * 3
        names += ["Progressive Training Guard"] * 2 + ["Progressive Stat Cap"] * self.caps
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
            "goal": "g1_collector" if o.goal == o.goal.option_g1_collector else "rank_score",
            "goal_rank_score": o.goal_rank_score.value,
            "goal_g1_count": o.goal_g1_count.value,
            "trap_cap": o.trap_cap.value,
            "trainees": self.trainees,
        }
