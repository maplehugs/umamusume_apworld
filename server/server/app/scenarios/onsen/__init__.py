"""ONSEN (scenario 12, JP only) -- ごくらく♪ゆこま温泉郷 (Yukoma Hot Springs).

Like every scenario it builds on the URA base (base.Scenario's defaults ARE
URA); this class is the whole seam between the scenario and the shared career
code, which only ever calls hooks.

WHAT LIVES WHERE
    impl.py       the mechanics -- springs, tickets, bathing, super recovery,
                  PR, the bathing parties, and the onsen_data_set envelope
    dig.py        tool power, the dig budget, the dig bonus
    formula.py    the training numbers (on ramen.formula's machinery)
    master.py     the single_mode_12_* tables
    endpoints.py  select_dig_onsen, bathing, assistant_exec, check_dug_result,
                  onsen_live
    producers.py  the event calendar and its resolvers

docs/JP_ONSEN_SCENARIO.md is the spec: every rule, number and event here is
traced there to the real server's captures, master.mdb or the client.

JP ONLY BY CONSTRUCTION: Global's master.mdb has no single_mode_12_* tables,
so the released-and-implemented intersection never advertises it there.
"""

from __future__ import annotations

from ..base import Scenario
from ..registry import register
from . import dig as D, endpoints, formula, impl, master as M, producers


class Onsen(Scenario):
    scenario_id = impl.SCENARIO_ID
    name = "Onsen"
    endpoint_prefix = "single_mode_onsen"
    data_set_key = "onsen_data_set"
    data_set_on_race_start = True
    state_keys = (impl.STATE_KEY,)

    # ------------------------------------------------- shared-content gates --
    # The Director arrives with 212002 and the Reporter with 212016
    # (single_mode_events.NPC_UNLOCKS); none of URA's own chain or Happy Meek.
    uses_fixed_schedule = False
    has_versus_npc = False
    debut_reporter_event = 0
    # The real turn-78 chain: 101006 -> 2 -> 212039 -> onsen_live -> 37 -> 6.
    has_director_ending = False
    finals_events = {
        1: {"pre": (101001, 400000101, False), "post": (101002, 400000104, 12)},
        2: {"pre": (101003, 400000102, False), "post": (101004, 400000105, 13)},
        3: {"pre": (101005, 400000103, False), "post": (101006, 400000106, 14)},
    }
    _FINALS_POST = {101002: 74, 101004: 76, 101006: 78}

    # 36 spring selection, 37 bathing party, 42 the ending live (§1.3).
    playing_states = frozenset({5, 36, 37, 42})
    turn_end_hold_state = 5

    LEVELUP_EVENTS = {101: 212007, 102: 212008, 103: 212009, 105: 212010, 106: 212011}

    def facility_levelup_event(self, command_id) -> tuple:
        base = formula.SUMMER_TO_BASE.get(int(command_id or 0), int(command_id or 0))
        return (self.LEVELUP_EVENTS.get(base, 212007), 400000005)

    def gated_npc_charas(self) -> frozenset:
        """Kiyoko's card stays off the training screen until 212003 (turn 3,
        the first spring pick) -- 200/200 real careers flip her row there."""
        return frozenset({M.KIYOKO_CHARA})

    # NPC Kiyoko (114, no link card): her own evaluation row, and she praises
    # in SP.
    npc_targets = frozenset({114})
    sp_appraisers = frozenset({102, 114})

    def appraisal_events(self):
        """The Director's tiers and NPC Kiyoko's (114): SP +2 below bond 40,
        +3 from it, bond +5 (9 real); the 70/90 tiers' +4/+5 follow the
        Director's series on master's 0/40/70/90 thresholds (not captured)."""
        return {102: [(90, 212015, 5), (70, 212014, 4), (40, 212013, 3), (0, 212012, 2)],
                114: [(90, 212066, 5), (70, 212065, 4), (40, 212064, 3), (0, 212063, 2)]}

    # ------------------------------------------------------------ endpoints --
    def extra_endpoints(self) -> dict:
        return dict(endpoints.HANDLERS)

    def scenario_command(self, full_state, chara_info, payload):
        """PR (command_type 12, §10): its gains as params for the shared
        exec_command to apply, and its dig, ticket and completion banked."""
        if int(payload.get("command_type") or 0) != endpoints.PR_COMMAND_TYPE:
            return None
        st = impl.state(full_state)
        turn = int(payload.get("current_turn") or impl.turn_of(chara_info))
        params, bonus_params, digs = impl.assistant_preview(full_state, chara_info, turn)
        impl.apply_dig(full_state, chara_info, digs, pay=False)
        impl.add_tickets(st, impl.ASSISTANT_TICKETS)
        if impl.completed_now(st):
            st["complete_due"] = {"kind": "train", "turn": turn}
        st["pr_turn"] = turn
        merged: dict = {}
        for p in params + bonus_params:
            merged[p["target_type"]] = merged.get(p["target_type"], 0) + int(p["value"])
        return [{"target_type": tt, "value": v} for tt, v in sorted(merged.items())]

    # ------------------------------------------------------------- response --
    def command_info(self, full_state, chara_info, home_commands):
        if not isinstance(chara_info, dict):
            return None, False
        from ...handlers import single_mode_team as smt
        changed = impl.refresh_preview(full_state, chara_info,
                                       {"command_info_array": home_commands or []},
                                       smt._support_card_levels(full_state))
        return None, bool(changed)

    def attach(self, response, full_state, chara_info, command_info_array=None, endpoint=""):
        data = (response or {}).get("data")
        if not isinstance(data, dict) or not isinstance(chara_info, dict):
            return response
        from ...handlers import single_mode_team as smt
        home = data.get("home_info")
        if not isinstance(home, dict):
            home = ((full_state.get(smt.STATE_KEY) or {}).get("data") or {}).get("home_info") or {}
        if impl.RI.career_over(chara_info):
            for ci in (chara_info, (data.get("single_mode_load_common") or {}).get("chara_info")):
                if isinstance(ci, dict) and int(ci.get("playing_state") or 1) == 1:
                    ci["playing_state"] = 5
        # A held turn (party, in-chain selection) serves its pending beats with
        # playing_state 5, as the turn-end hold does elsewhere: a 1 there reads
        # as the next turn's home screen mid-chain.
        served_ci = data.get("chara_info")
        if (isinstance(served_ci, dict) and impl.state(full_state).get("hold_turn")
                and data.get("unchecked_event_array")
                and int(served_ci.get("playing_state") or 1) == 1):
            served_ci["playing_state"] = 5
        ds = impl.data_set(full_state, chara_info, home)
        data["onsen_data_set"] = ds
        for holder in (data.get("single_mode_start_common"), data.get("single_mode_load_common")):
            if isinstance(holder, dict):
                holder.pop("onsen_data_set", None)
        st = impl.state(full_state)
        turn = impl.served_turn(full_state, chara_info)
        copies = st["copies"].get("map", {}) if st["copies"].get("turn") == turn else {}
        # Spring 9's copies stand only in a facility the player can train in: a
        # race-only turn (goal race, URA finals) serves [] on every command even
        # with the buff up (463/463 real replies). Copies on the finals' disabled
        # buttons left the client on an empty home screen (T74, 2026-09-26).
        for h in (data.get("home_info"),):
            if isinstance(h, dict):
                for c in h.get("command_info_array") or ():
                    if c.get("command_type") == 1 and c.get("is_enable"):
                        c["sub_command_partner_array"] = list(copies.get(str(c.get("command_id")), []))
                    else:
                        c["sub_command_partner_array"] = []
        for ev in data.get("unchecked_event_array") or ():
            post = self._FINALS_POST.get(int(ev.get("event_id") or 0))
            if post:
                (ev.get("event_contents_info") or {})["show_clear_sort_id"] = \
                    impl.RI.goal_sort_id(chara_info, post)
        return response

    def settle(self, full_state, chara_info, endpoint=""):
        """The super-recovery gauge on every response, and Kiyoko's dates: each
        step pays tickets and readies a super recovery (§8, §13.3)."""
        if not isinstance(chara_info, dict):
            return False
        st = impl.state(full_state)
        changed = impl.track_energy(full_state, chara_info)
        k = impl.kiyoko_card(chara_info)
        if k:
            pos, sid, rarity = k
            row = next((e for e in chara_info.get("evaluation_info_array") or ()
                        if isinstance(e, dict) and int(e.get("target_id") or 0) == pos), None)
            step = int((row or {}).get("story_step") or 0)
            seen = int(st["link_steps"].get(str(sid)) or 0)
            for s in range(seen + 1, step + 1):
                impl.add_tickets(st, M.outing_tickets().get((M.KIYOKO_CHARA, rarity, s), 0))
                st["superior"] = 1
                st["spent"] = 0
                st["threshold"] = 0
            if step != seen:
                st["link_steps"][str(sid)] = step
                changed = True
        return changed

    # ------------------------------------------------------------- training --
    def training_gains(self, full_state, chara_info, command_id, facility_level, camp, partners):
        from ...handlers import single_mode_team as smt
        st = impl.state(full_state)
        turn = impl.served_turn(full_state, chara_info)
        served = formula.BASE_TO_SUMMER.get(command_id, command_id) if camp else command_id
        plan = impl.dig_plan(full_state, chara_info, impl.training_base(partners, chara_info), turn)
        energy = int(impl.plan_bonus(st, plan).get(D.THRESHOLD_ENERGY, 0))
        return formula.home_gains(chara_info, served, facility_level, partners,
                                  smt._support_card_levels(full_state), energy,
                                  impl.energy_down(st, turn), st.get("energy_cap") or None)

    def training_award_bonus(self, full_state, chara_info, command_id) -> list:
        st = impl.state(full_state)
        preview = st["preview"]
        if preview.get("turn") != impl.turn_of(chara_info):
            return []
        return [dict(p) for p in preview["bonus"].get(str(command_id)) or ()]

    def award_training_gains(self, full_state, chara_info, payload) -> None:
        """A successful action: a training digs in its own response; a rest or
        an outing queues its dig event (§4, §12.2)."""
        st = impl.state(full_state)
        st["flags"].pop("not_gain_ticket", None)
        turn = int(payload.get("current_turn") or impl.turn_of(chara_info))
        ctype = int(payload.get("command_type") or 0)
        cmd = int(payload.get("command_id") or 0)
        if ctype == 1:
            digs = impl.stored_dig(st, cmd, turn)
            if digs and impl.dig_active(st, turn):
                impl.apply_dig(full_state, chara_info, digs, pay=False)
                if impl.completed_now(st):
                    st["complete_due"] = {"kind": "train", "turn": turn}
            return
        if not impl.dig_active(st, turn):
            return
        if ctype == 7 or cmd == 701:
            st["dig_due"] = {"kind": "rest", "base": D.BASE_REST, "turn": turn}
        elif ctype == 3:
            kiyoko = (int(payload.get("command_group_id") or 0) == 390
                      and int(payload.get("select_id") or 0) == M.KIYOKO_CHARA)
            st["dig_due"] = {"kind": "outing", "turn": turn,
                             "base": D.BASE_KIYOKO_OUTING if kiyoko else D.BASE_REST}

    def on_race_result(self, full_state, chara_info, race_ctx, result_rank) -> None:
        st = impl.state(full_state)
        st["flags"].pop("not_gain_ticket", None)
        turn = int(race_ctx.get("turn") or impl.turn_of(chara_info))
        if race_ctx.get("finals_round") or not impl.dig_active(st, turn):
            return
        st["dig_due"] = {"kind": "race", "turn": turn,
                         "base": D.BASE_GOAL_RACE if race_ctx.get("is_goal") else D.BASE_RACE}

    def specialty_rate_pct(self, full_state) -> int:
        """Ryokan rank's specialty rate scales the whole own-facility weight:
        rank 1/2/3 weigh 205/290/350 in the captures, x1.4 / x1.7 (§11.1)."""
        return impl.specialty(impl.state(full_state))

    def hint_partners(self, full_state, chara_info, command_id, partners, hinting):
        """Spring 5's hint rate +100% while the buff runs: each card's hint
        chance p becomes p x (1 + rate/100), exactly x2 in the captures (§2).
        A card the shared roll missed gets the top-up p*rate/100 / (1 - p)."""
        st = impl.state(full_state)
        turn = impl.turn_of(chara_info)
        rate = impl.hint_rate(st, turn)
        if not rate:
            return hinting
        from ...handlers import single_mode_team as smt
        by_pos = impl.deck(chara_info)
        out = list(hinting)
        for pos in partners:
            if pos in out or pos not in by_pos or not formula.RF.is_normal_card(by_pos[pos]):
                continue
            p = smt._skill_hint_chance(by_pos[pos])
            chance = 1.0 if p >= 1 else p * rate / 100 / (1 - p)
            if impl.rng_for(full_state, "hint", turn, pos).random() < chance:
                out.append(pos)
        return out

    def partner_placements(self, full_state, chara_info, turn, occupied=None, standing=None) -> dict:
        return impl.place_copies(full_state, chara_info, int(turn or 0), occupied, standing)

    def training_failure_override(self, full_state, chara_info, command_id, partners):
        st = impl.state(full_state)
        down = impl.failure_down(st, impl.turn_of(chara_info))
        if not down:
            return None
        from ... import training_formula as tf
        from ...handlers import single_mode_team as smt
        base = formula.SUMMER_TO_BASE.get(command_id, command_id)
        level = 5 if command_id in formula.SUMMER_TO_BASE else next(
            (int(e.get("level") or 1) for e in chara_info.get("training_level_info_array") or ()
             if e.get("command_id") == base), 1)
        rate = tf.failure_rate(chara_info.get("vital", 100), command_id=command_id,
                               facility_level=level,
                               conditions=chara_info.get("chara_effect_id_array"),
                               facility_cards=smt._facility_failure_cards(chara_info, partners), extra_down_pct=down)
        return rate

    # ----------------------------------------------------------------- flow --
    def interstitial_pending(self, full_state, chara_info, turn) -> bool:
        return impl.party_pending(impl.state(full_state), int(turn or 0))

    def begin_hold(self, full_state, turn) -> None:
        impl.state(full_state)["hold_turn"] = int(turn or 0)

    def held_turn(self, full_state) -> int:
        return int(impl.state(full_state).get("hold_turn") or 0)

    def holds_chain_after(self, event_id) -> bool:
        return int(event_id or 0) in producers.SCREEN_EVENTS

    def choice_reward_preview(self, full_state, chara_info, event_id):
        from ... import career_events as CE
        from ... import event_engine
        ev = CE.find(full_state, event_id)
        if ev is None or ev.source != "onsen" or not ev.choices or len(ev.choices) < 2:
            return None
        return event_engine.choice_reward_array(ev.engine_event(), chara_info or {})

    def on_event_resolved(self, full_state, chara_info, event_id) -> dict:
        from ... import career_events as CE
        event_id = int(event_id or 0)
        turn = impl.turn_of(chara_info)
        ev = None
        if event_id == 1001 and turn <= 1:
            ev = producers.opening_event()
        elif event_id == producers.TOWN_BEAT[0]:
            ev = producers.reporter_event()
        elif event_id in producers.STORY_ENDING_TRIGGERS and turn >= 78:
            ev = producers.ending_event(full_state)
        if ev:
            CE.emit(full_state, ev)
        return {}

    # ------------------------------------------------------------------ run --
    def snapshot(self, full_state) -> dict:
        st = impl.state(full_state)
        return {"onsen_results": [dict(r) for r in st["results"]],
                "onsen_rank": impl.rank(st)}

    def reset(self, full_state) -> None:
        impl.reset(full_state)


register(Onsen())
