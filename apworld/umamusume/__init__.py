"""Umamusume: Pretty Derby, played on the private server in this repo's server/,
which applies the items and reports the checks. tables.py holds
every id; the server mirrors it, so both sides agree on every id."""

from BaseClasses import Item, ItemClassification as IC, Location, Region
from worlds.AutoWorld import World

from . import tables
from .options import UmaOptions

ITEMS = tables.item_name_to_id()
LOCATIONS = tables.location_name_to_id()
TRAINING = [f"Progressive {s} Training" for s in tables.STATS]
T = tables
# For exclude_locations / priority_locations in a YAML: "Team Trials" = all 100.
LOCATION_GROUPS = {
    "G1": {T.g1_location(g) for g in T.G1_RACES},
    "G1 per scenario": {T.g1_scenario_location(g, s) for g in T.G1_RACES for s in T.SCENARIOS},
    "Scenario finishes": {T.finish_location(s) for s in T.SCENARIOS},
    "Scenario ranks": {T.rank_location(s, tier) for s in T.SCENARIOS for tier, _ in T.RANK_TIERS},
    "Global ranks": {T.global_rank_location(tier) for tier, _ in T.GLOBAL_RANKS},
    "Different races": {T.unique_races_location(n) for n in T.UNIQUE_RACE_MILESTONES},
    "Fans": {T.fans_location(n) for n in T.FAN_MILESTONES},
    "Legend Race": {T.legend_location(tier) for tier, *_ in T.LEGEND_LADDER},
    "Team Trials": {T.team_trials_location(n) for n in range(1, T.TEAM_TRIALS_CHECKS + 1)},
    "Trainees": {T.trainee_location(c) for c in T.TRAINEES},
}
# A base-deck career with 3* umas is ~8.5k: supports carry the rest, so the
# goal needs a few maxed SSRs (none: ~16.5k at most on normal).
BASE_SCORE = {0: 7500, 1: 8500, 2: 9500}  # logic_difficulty -> unbuffed career
TRAINING_BONUS = 300  # each training item
SCENARIO_BONUS = 1500  # a non-URA scenario's own caps and gains
SUPPORT_BONUS, SUPPORT_MAX = 1200, 6  # each maxed SSR (a deck holds 6)
# How hard a ticket leans toward good cards: a card's draw weight is its value
# (60-130, averaged over the scenarios) to this power, so a 130 card comes about
# 20x as early as a 60 one. 0 = plain shuffle.
TICKET_BIAS = 4
CRYSTAL = "Rainbow Uncap Crystal"  # one SSR limit break: 4 max a card
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
    item_name_groups = {"Supports": {n for n in ITEMS if n.startswith(("Support: ", "SSR Ticket ("))}}
    location_name_to_id = LOCATIONS
    location_name_groups = LOCATION_GROUPS
    topology_present = False

    def generate_early(self) -> None:
        o = self.options
        pick = o.starting_scenario.value  # 0 ura, 1 shuffled, 2-4 that scenario
        self.start_scenario = self.random.choice(sorted(tables.SCENARIOS)) if pick == 1 else max(1, pick)
        if o.starting_trainees == o.starting_trainees.option_shuffled:
            self.starters = self.random.sample(sorted(tables.TRAINEES), o.starting_trainee_count.value)
        else:
            self.starters = list(tables.STARTING_TRAINEES)
        extra = sorted(set(tables.TRAINEES) - set(self.starters))
        self.trainees = self.random.sample(extra, min(o.trainee_count.value, len(extra)))
        # Dealt round by round, one of each stat per round in a random order, so any
        # count is even (30 = 6 Speed, 6 Stamina...); Friend/Group only past 100.
        # Each type's own order leans toward the useful cards: it is also the order
        # that type's tickets hand them out in.
        pools = {k: self.weighted_order(v) for k, v in tables.SUPPORT_TYPES.items()}
        stats = [pools[s] for s in tables.STATS]
        cards = []
        for i in range(max(map(len, stats))):
            cards += [p[i] for p in self.random.sample(stats, len(stats)) if i < len(p)]
        cards += self.random.sample(pools["Friend"] + pools["Group"], len(pools["Friend"] + pools["Group"]))
        # support_count is the floor; create_items deals more from the deck with room.
        self.start_supports, self.deck = cards[:o.starting_supports.value], cards[o.starting_supports.value:]
        self.supports = self.deck[:o.support_count.value]
        self.ticket_order = {}  # type -> its ticketed cards, deck order (create_items adds more)
        self.add_tickets(self.supports)
        if o.goal == o.goal.option_legend_race and not o.legend_ladder:
            raise Exception(f"{self.player_name}: the legend_race goal needs legend_ladder on")
        self.caps = 2 if self.options.goal_rank_score.value >= 21000 else 0

    def weighted_order(self, cards) -> list:
        """A random order where useful cards tend to come first (weighted sampling
        without replacement: sort by random() ** (1 / weight)); with
        duplicate_supports, drawn with replacement, so a card can repeat."""
        def weight(c):
            v = tables.SUPPORT_VALUE.get(c, (100,) * 4)
            return (sum(v) / len(v) / 100) ** TICKET_BIAS
        if self.options.duplicate_supports:
            return self.random.choices(cards, [weight(c) for c in cards], k=len(cards))
        return sorted(cards, key=lambda c: self.random.random() ** (1 / weight(c)), reverse=True)

    def add_tickets(self, cards) -> None:
        for c in cards:
            self.ticket_order.setdefault(tables.support_type(c), []).append(c)

    def deck_ok(self, state, score: int) -> bool:
        """tables.DECK_NEEDS: enough Speed and Wit cards and trainees for `score`."""
        cards = self.start_supports + self.ticket_cards(state)
        trainees = len(self.starters) + sum(state.has(f"Trainee: {tables.TRAINEES[c]}", self.player)
                                            for c in self.trainees)
        return tables.deck_ok(score, self.deck_counts(cards, trainees), self.deck_counts(
            self.start_supports + [c for order in self.ticket_order.values() for c in order],
            len(self.starters) + len(self.trainees)))

    def legend_ok(self, state, tier: int) -> bool:
        """tables.LEGEND_NEEDS: the cards, skill points and awakenings for rung `tier`."""
        p = self.player
        cards = self.start_supports + self.ticket_cards(state)
        seed_cards = self.start_supports + [c for order in self.ticket_order.values() for c in order]
        cards, seed_cards = set(cards), set(seed_cards)  # a copy is a limit break, not a card
        have = (len(cards), self.deck_types(cards).count("Stamina"),
                state.count("Progressive Starting Skill Points", p), state.count("Trainee Awakening", p))
        return tables.legend_ok(tier, have, (len(seed_cards), self.deck_types(seed_cards).count("Stamina"),
                                             3, self.awakenings()))

    def awakenings(self) -> int:
        return min(self.options.trainee_awakenings.value, len(self.starters) + len(self.trainees))

    @staticmethod
    def deck_types(cards) -> list:
        return [tables.support_type(c) for c in cards]

    @staticmethod
    def deck_counts(cards, trainees: int) -> tuple:
        types = [tables.support_type(c) for c in set(cards)]  # a copy is a limit break, not a card
        return types.count("Speed"), types.count("Wit"), trainees

    def ticket_cards(self, state) -> list:
        """The cards the tickets owned in `state` hand out: the first N of each type."""
        return [c for t, order in self.ticket_order.items()
                for c in order[:state.count(tables.support_ticket(t), self.player)]]

    # ---- logic: an estimated best rank score, like Yacht Dice's score estimate
    def estimate(self, state, scenario: int | None = None) -> int:
        p = self.player
        est = BASE_SCORE[self.options.logic_difficulty.value]
        est += TRAINING_BONUS * sum(state.count(n, p) for n in TRAINING)
        est += 400 * state.count("Progressive Starting Stats", p)
        est += 300 * state.count("Progressive Stat Cap", p)
        cards = self.start_supports + self.ticket_cards(state)
        crystals = None if self.options.maxed_supports else state.count(CRYSTAL, p)
        if scenario is None:  # any scenario: the best one owned
            owned = [sid for sid, n in tables.SCENARIO_ITEM.items() if sid == self.start_scenario or state.has(n, p)]
        else:
            owned = [scenario]
        return est + max(self.scenario_bonus(sid, cards, crystals) for sid in owned)

    def scenario_bonus(self, sid: int, cards, crystals: int | None) -> int:
        """Supports as they rate in that scenario, plus a non-URA scenario's own gains."""
        return (tables.support_score(cards, sid, crystals, SUPPORT_BONUS, SUPPORT_MAX)
                + (SCENARIO_BONUS if sid != 1 else 0))

    def reaches(self, state, score: int) -> bool:
        """estimate >= score and the deck for it (deck_ok); a score past every
        buff only asks for every buff."""
        return self.estimate(state) >= min(score, self.best) and self.deck_ok(state, score)

    def max_estimate(self, scenario: int | None = None) -> int:
        cards = self.start_supports + self.supports
        crystals = None if self.options.maxed_supports else self.crystals()
        return (
            BASE_SCORE[self.options.logic_difficulty.value]
            + TRAINING_BONUS * 3 * len(TRAINING)
            + 400 * 5
            + 300 * self.caps
            + max(self.scenario_bonus(sid, cards, crystals) for sid in ([scenario] if scenario else tables.SCENARIOS))
        )

    def crystals(self) -> int:
        return 0 if self.options.maxed_supports else self.options.uncap_crystals.value

    def create_regions(self) -> None:
        self.best = self.max_estimate()  # for reaches
        menu = Region("Menu", self.player, self.multiworld)
        p, o = self.player, self.options

        def add(name, rule=None):
            loc = UmaLocation(p, name, LOCATIONS.get(name), menu)
            if rule:
                loc.access_rule = rule
            menu.locations.append(loc)
            return loc

        # A rank_score goal ends the game at that score: a rank check at or just
        # under it (UG 19600 for a 20000 goal) comes with the win, its item too late.
        cap = o.goal_rank_score.value - 500 if o.goal == o.goal.option_rank_score else 10**9
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
                        lambda s, has=has, sid=sid, score=score: has(s) and self.estimate(s, sid) >= score
                        and self.deck_ok(s, score))
        if o.global_rank_ladder:
            for tier, score in tables.GLOBAL_RANKS:
                if score > cap:
                    continue
                add(tables.global_rank_location(tier), lambda s, score=score: self.reaches(s, score))
        if o.unique_race_checks:
            for n in tables.UNIQUE_RACE_MILESTONES:  # ~8 wins per career
                add(tables.unique_races_location(n), lambda s, n=n: self.reaches(s, 9000 + 100 * n))
        if o.legend_ladder:
            # The rival is raced with one of your trained umas: in logic once your
            # careers are expected to reach that rival's rank.
            for i, (tier, rank_id, _row, _stats) in enumerate(tables.LEGEND_LADDER):
                if o.goal == o.goal.option_legend_race and rank_id == tables.LEGEND_LADDER[-1][1]:
                    continue  # beating SS+ is the goal itself
                need = tables.LEGEND_RANK_SCORE[rank_id]
                add(tables.legend_location(tier),
                    lambda s, need=need, i=i: self.reaches(s, need) and self.legend_ok(s, i))
        if o.fan_checks:  # ~250k fans per career
            for n in tables.FAN_MILESTONES:
                add(tables.fans_location(n), lambda s, n=n: self.reaches(s, tables.fans_logic(n)))
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
                      lambda s, n=n: self.reaches(s, 11000 + 300 * min(n // 3, 10)))
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
            goal = add("Goal", lambda s: self.reaches(s, 19200)  # the SS+ rival's rank
                       and self.legend_ok(s, len(tables.LEGEND_LADDER) - 1))
        elif o.goal == o.goal.option_g1_collector:
            if not o.g1_checks:
                raise Exception(f"{self.player_name}: g1_collector needs g1_checks on")
            need = o.goal_g1_count.value
            goal = add("Goal", lambda s: self.reaches(s, 11000 + 150 * need))
        else:
            goal = add("Goal", lambda s: self.reaches(s, o.goal_rank_score.value))
        goal.place_locked_item(UmaItem("Victory", IC.progression, None, p))
        self.multiworld.completion_condition[p] = lambda s: s.has("Victory", p)
        self.multiworld.regions.append(menu)

    def create_item(self, name: str) -> UmaItem:
        # Support cards count in logic (a maxed SSR deck is most of a good career).
        if name in TRAINING or name.startswith(("Scenario:", "Trainee:", "Support:", "SSR Ticket (")) or name in (
            CRYSTAL,
            "Progressive Starting Stats",
            "Progressive Stat Cap",
            "Progressive Starting Skill Points",  # legend rungs (tables.LEGEND_NEEDS)
            "Trainee Awakening",
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
        o = self.options
        # The most wanted first: whatever doesn't fit in the checks is start
        # inventory instead (any set of checks generates; fewer = a shorter game).
        # Score buffs are cut last: precollected, they put the goal in logic at once.
        names = [n for sid, n in tables.SCENARIO_ITEM.items() if sid != self.start_scenario]
        names += TRAINING * 3  # stat by stat, so a cut hits them evenly
        names += ["Progressive Starting Stats"] * 5 + ["Progressive Stat Cap"] * self.caps
        names += [f"Trainee: {tables.TRAINEES[c]}" for c in self.trainees]
        names += [tables.support_ticket(tables.support_type(s)) for s in self.supports]
        names += [CRYSTAL] * self.crystals()
        names += ["Trainee Awakening"] * self.awakenings()
        names += ["Progressive RP Recovery"] * min(3, o.team_trials_checks.value)
        names += ["Progressive Starting Skill Points"] * 3 + ["Progressive Training Guard"] * 2
        slots = len(self.multiworld.get_unfilled_locations(self.player))
        names, self.start_items = names[:slots], names[slots:]
        for n in self.start_items:
            self.multiworld.push_precollected(self.create_item(n))
        # Room left: up to half as many more crystals (random), then half more SSR
        # cards (still even by stat), half filler.
        room = slots - len(names)
        more = min(room, self.random.randint(0, self.crystals() // 2))
        names += [CRYSTAL] * more
        room -= more
        extra = self.deck[len(self.supports):][:room // 2]
        names += [tables.support_ticket(tables.support_type(s)) for s in extra]
        self.add_tickets(extra)
        names += [self.get_filler_item_name() for _ in range(room - len(extra))]
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
            "maxed_supports": bool(o.maxed_supports),
            "g1_per_scenario": bool(o.g1_checks and o.g1_per_scenario),
            "logic_base": BASE_SCORE[o.logic_difficulty.value],  # the server's tracker
            "logic_training": TRAINING_BONUS,
            "logic_support": SUPPORT_BONUS,
            "support_values": True,  # the tracker rates cards by tables.SUPPORT_VALUE
            "team_trials_checks": o.team_trials_checks.value,
            "trainees": self.trainees,
            "starting_trainees": self.starters,
            "starting_scenario": self.start_scenario,
            "starting_supports": self.start_supports,
            "support_tickets": self.ticket_order,  # Nth ticket of a type -> Nth card here
            "deck_needs": True,  # the tracker applies tables.DECK_NEEDS and LEGEND_NEEDS
            "awakenings": self.awakenings(),
            "duplicate_supports": bool(o.duplicate_supports),
        }
