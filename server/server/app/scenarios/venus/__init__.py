"""GRAND MASTERS (scenario 5, JP only) -- グランドマスターズ -継ぐ者達へ- ("Venus").

Built on the URA base (base.Scenario's defaults ARE URA); this class is the
whole seam between the scenario and the shared career code, which only ever
calls hooks.

WHAT LIVES WHERE
    impl.py       the mechanics -- fragments, crystals and the Wisdom, the
                  goddess levels, facility levels, the special races, and the
                  venus_data_set envelope
    formula.py    the training numbers (on ramen.formula's machinery)
    master.py     the single_mode_venus_* tables
    endpoints.py  spirit_use, venus_race_entry/start/end/out/continue,
                  venus_spirit_history
    producers.py  the event calendar and its resolvers

docs/JP_GRAND_MASTERS_SCENARIO.md is the spec: every rule, number and event
here is traced there to the real server's captures, master.mdb or the client.

JP ONLY BY CONSTRUCTION: Global's master.mdb has no single_mode_venus_*
tables, so the released-and-implemented intersection never advertises it there.
"""

from __future__ import annotations

from ..base import Scenario
from ..registry import register
from . import endpoints, formula, impl, master as M, producers


def _partner_rows() -> tuple:
    try:
        from ... import master_data
        return tuple((int(r["partner_id"]), int(r["chara_id"])) for r in master_data.query(
            "SELECT partner_id, chara_id FROM single_mode_unique_chara WHERE scenario_id=? "
            "ORDER BY partner_id", (impl.SCENARIO_ID,)))
    except Exception:                                  # noqa: BLE001
        return ()


class Venus(Scenario):
    scenario_id = impl.SCENARIO_ID
    name = "Venus"
    endpoint_prefix = "single_mode_venus"
    data_set_key = "venus_data_set"
    data_set_on_race_start = False      # real race_start: race_start_info + race_scenario only
    state_keys = (impl.STATE_KEY,)

    # ------------------------------------------------- shared-content gates --
    # The Director arrives with 205001 and the Reporter with 205034
    # (single_mode_events.NPC_UNLOCKS). The career ends on the GM final (route
    # row 990000, turn 78): no URA finals, no URA ending chain, no Happy Meek.
    uses_fixed_schedule = False
    has_versus_npc = False
    debut_reporter_event = 0
    has_director_ending = False
    has_ura_finals = False
    has_ending_chain = False
    # A special race owed on a turn the trainee raced holds the turn first and
    # keeps the next turn's beats (New Year) behind its result, as exec does.
    reserve_arrivals_after_race = True
    # Camp keeps 701/801, disabled (every real camp turn).
    camp_lists_rest = True
    # 12-15 the special race (VenusRaceTop .. VenusRaceResult).
    playing_states = frozenset({5, 12, 13, 14, 15})
    turn_end_hold_state = 5
    # Every scenario-5 partner holds a row from turn 1 (§9.4); attach drops
    # the ones a deck card carries.
    locked_npc_rows = _partner_rows()
    npc_targets = frozenset(t for t, _c in _partner_rows())

    def career_route(self, chara_info: dict):
        """The trainee's own goals, the URA finals rows (target_type 3)
        swapped for the GM final 990000 (§1)."""
        from ... import career_branches, master_data
        chara = int((chara_info or {}).get("card_id") or 0) // 100
        row = master_data.query_one(
            "SELECT id, race_set_id FROM single_mode_route WHERE scenario_id=0 AND chara_id=? "
            "ORDER BY priority DESC LIMIT 1", (chara,))
        if not row:
            return None
        ids = tuple(int(r["id"]) for r in master_data.query(
            "SELECT id FROM single_mode_route_race WHERE race_set_id=? ORDER BY id",
            (row["race_set_id"],)))
        route = career_branches.start_route(chara, row["race_set_id"], ids)
        finals = {int(r["id"]) for r in master_data.query(
            "SELECT id FROM single_mode_route_race WHERE race_set_id=? AND target_type=3",
            (row["race_set_id"],))}
        return row["id"], [i for i in route if int(i) not in finals] + [M.GM_ROUTE_ROW]

    def group_race_program(self, full_state, chara_info, group_id, turn, race_history):
        """The GM final: the most-raced category, the fixed tie order (§7.1)."""
        if int(group_id or 0) != M.GM_RACE_GROUP:
            return None
        import random
        rng = random.Random(f"venus-gm:{chara_info.get('single_mode_chara_id')}:{chara_info.get('card_id')}")
        return impl.pick_program(M.GM_RACE_GROUP, race_history, rng) or None

    def goal_race_entry_events(self, full_state, chara_info, program_id, turn):
        """決戦！グランドマスターズ at the final's race_entry (timing 2, no
        choices); every other goal race keeps the shared beat."""
        if not M.is_special_program(program_id):
            return None
        ev = producers.beat(*producers.FINAL_ENTRY, choices=[], timing=2)
        return [ev.wire_entry()] if ev else []

    def owns_goal_race_result(self, chara_info, program_id) -> bool:
        return M.is_special_program(program_id)

    def partner_outing(self, full_state, chara_info, partner, turn) -> bool:
        """A goddess outing with no story left is a plain one: its knowledge
        event (queued by award_training_gains) is all that follows (§9.2)."""
        return int(partner or 0) in M.GODDESSES

    def race_field(self, chara_info, program_id, count):
        if not M.is_special_program(program_id):
            return None
        # race_field is handed no full_state; the draw only needs a seed.
        return impl.race_field({}, chara_info, int(program_id or 0), count)

    def facility_levelup_event(self, command_id) -> tuple:
        return (producers.LEVEL_UP[0], producers.LEVEL_UP[2])

    def levels_facilities_by_training(self) -> bool:
        """Levels come from the scenario's own points (§6), not 4 trainings."""
        return False

    def gated_npc_charas(self) -> frozenset:
        """The goddesses' card stays off the training screen until 205002."""
        return frozenset({M.DARLEY})

    def appraisal_events(self):
        """The Director's appraisals carry the scenario's own ids (205113-205116);
        the Reporter's are the shared 1007-1010 (§10)."""
        return {102: [(90, 205116, 5), (70, 205115, 4), (40, 205114, 3), (0, 205113, 2)],
                103: [(90, 1010, 5), (70, 1009, 4), (40, 1008, 3), (0, 1007, 2)]}

    # ------------------------------------------------------------ endpoints --
    def extra_endpoints(self) -> dict:
        return dict(endpoints.HANDLERS)

    # ------------------------------------------------------------- response --
    def command_info(self, full_state, chara_info, home_commands):
        if not isinstance(chara_info, dict):
            return None, False
        from ...handlers import single_mode_team as smt
        changed = impl.refresh_preview(full_state, chara_info,
                                       {"command_info_array": home_commands or []},
                                       smt._support_card_levels(full_state))
        return None, bool(changed)

    def settle(self, full_state, chara_info, endpoint=""):
        """The table empties with the first command after a wisdom is used."""
        from ...handlers import single_mode_team as smt
        st = impl.state(full_state)
        if not st.get("cleared_turn"):
            return False
        live = ((full_state.get(smt.STATE_KEY) or {}).get("data") or {}).get("chara_info") or {}
        if impl.turn_of(live) > int(st["cleared_turn"]):
            impl.clear_after_use(st, impl.turn_of(live))
            return True
        return False

    def attach(self, response, full_state, chara_info, command_info_array=None, endpoint=""):
        data = (response or {}).get("data")
        if not isinstance(data, dict) or not isinstance(chara_info, dict):
            return response
        from ...handlers import single_mode_team as smt
        call = endpoint.rsplit("/", 1)[-1]
        home = data.get("home_info")
        if not isinstance(home, dict):
            home = ((full_state.get(smt.STATE_KEY) or {}).get("data") or {}).get("home_info") or {}
        live = ((full_state.get(smt.STATE_KEY) or {}).get("data") or {}).get("chara_info") or {}
        if impl.RI.career_over(chara_info):
            for ci in (chara_info, (data.get("single_mode_load_common") or {}).get("chara_info")):
                if isinstance(ci, dict) and int(ci.get("playing_state") or 1) == 1:
                    ci["playing_state"] = 5
        # gain_skills / load in the middle of a special race keep its state.
        live_ps = int(live.get("playing_state") or 1)
        if live_ps in (12, 13, 14, 15):
            for ci in (chara_info, (data.get("single_mode_load_common") or {}).get("chara_info")):
                if isinstance(ci, dict):
                    ci["playing_state"] = live_ps
        self._drop_carried_partners(chara_info)
        self.persist_upkeep(full_state, chara_info)
        for common in ("single_mode_load_common", "single_mode_start_common"):
            nested = (data.get(common) or {}).get("chara_info")
            if isinstance(nested, dict):
                self._drop_carried_partners(nested)
                self.persist_upkeep(full_state, nested)
        st = impl.state(full_state)
        sp = st["sprace"]
        rsi = scenario = reward = None
        if call in ("venus_race_entry", "venus_race_start") or (
                call == "load" and live_ps in (13, 14)):
            rsi = sp.get("race_start_info")
        if call == "venus_race_start":
            scenario = sp.get("race_scenario")
        if call == "venus_race_end":
            reward = sp.get("race_reward_info")
        venus = impl.data_set(full_state, chara_info, home, impl.reply_is_full(endpoint, data),
                              race_start_info=rsi, race_scenario=scenario, race_reward_info=reward)
        data["venus_data_set"] = venus
        for holder in (data.get("single_mode_start_common"), data.get("single_mode_load_common")):
            if isinstance(holder, dict):
                holder.pop("venus_data_set", None)
        return response

    @staticmethod
    def _drop_carried_partners(chara_info: dict) -> None:
        """A partner a deck card carries has no row of its own (101 with a
        Tazuna card, 109 with the goddesses' card)."""
        deck_charas = {formula.RF.card_meta(sid)[3] for sid in formula.RF.deck(chara_info).values()}
        carried = {t for t, c in _partner_rows() if c in deck_charas}
        if carried:
            chara_info["evaluation_info_array"] = [
                e for e in chara_info.get("evaluation_info_array") or ()
                if not (isinstance(e, dict) and e.get("target_id") in carried)]

    def persist_upkeep(self, full_state, chara_info) -> None:
        """The goddesses' card row carries one group_outing_info_array entry
        per goddess (§9.4): is_outing once the card is met, story_step 1 once
        her own outing is done; the row's story_step counts the 4th/5th
        outings (020, 021)."""
        k = impl.link_card(chara_info)
        if not k:
            return
        from ...handlers import single_mode_team as smt
        entry = smt._pal_card_entry(full_state, M.LINK_CARD)
        steps = entry.get("steps") or {}
        unlocked = 1 if entry.get("unlocked") else 0
        for row in chara_info.get("evaluation_info_array") or ():
            if not (isinstance(row, dict) and row.get("target_id") == k[0]):
                continue
            row["group_outing_info_array"] = [
                {"chara_id": g, "is_outing": unlocked, "story_step": min(1, int(steps.get(str(g), 0)))}
                for g in M.GODDESSES]
            row["story_step"] = max(0, int(steps.get(str(M.DARLEY), 0)) - 1)
            row["is_outing"] = unlocked

    # ------------------------------------------------------------- training --
    def training_gains(self, full_state, chara_info, command_id, facility_level, camp, partners):
        from ...handlers import single_mode_team as smt
        st = impl.state(full_state)
        turn = impl.served_turn(full_state, chara_info)
        served = formula.BASE_TO_SUMMER.get(command_id, command_id) if camp else command_id
        return formula.home_gains(chara_info, served, facility_level, partners,
                                  smt._support_card_levels(full_state), **impl.preview_flags(st, turn))

    def training_award_bonus(self, full_state, chara_info, command_id) -> list:
        return impl.preview_bonus(impl.state(full_state), impl.turn_of(chara_info), int(command_id or 0))

    def award_training_gains(self, full_state, chara_info, payload) -> None:
        """A successful action (§3.3, §6): a training gets its fragment now
        and 2 level points; an outing / rest owes its knowledge event; the
        Godolphin wisdom's hint payout is queued for the trained facility."""
        st = impl.state(full_state)
        turn = int(payload.get("current_turn") or impl.turn_of(chara_info))
        ctype = int(payload.get("command_type") or 0)
        cmd = int(payload.get("command_id") or 0)
        base = formula.SUMMER_TO_BASE.get(cmd, cmd)
        offer = impl.offer_for(st, turn, ctype, cmd)
        if ctype == 1:
            if cmd not in formula.SUMMER_TO_BASE and turn not in impl.SUMMER_TURNS:
                st["points"][str(base)] = int(st["points"].get(str(base), 0)) + impl.POINTS_TRAINING
            if offer:
                impl.add_fragment(full_state, *offer)
            partners = impl.preview_partners(st, turn, cmd)
            if impl.wisdom_on(st, turn, M.GODOLPHIN):
                st["godolphin"] = {"turn": turn, "command_id": cmd, "partners": partners}
            k = impl.link_card(chara_info)
            if k and k[0] in partners and \
                    impl.rng_for(full_state, "card003-roll", turn).random() < producers.CARD_TRAINING_CHANCE:
                st["card003_due"] = turn
            return
        if ctype in (3, 7) and offer:
            sid, count = offer
            st["due"].append({"goddess": M.goddess_of(sid), "spirit_id": sid, "count": count,
                              "turn": turn, "kind": ctype})

    def on_race_result(self, full_state, chara_info, race_ctx, result_rank) -> None:
        """Any ordinary race owes its knowledge event (timing 3); the GM final
        ends the career and queues its chain (§8)."""
        st = impl.state(full_state)
        turn = int(race_ctx.get("turn") or impl.turn_of(chara_info))
        program = int(race_ctx.get("program_id") or 0)
        if M.is_special_program(program):
            won = int(result_rank or 99) == 1
            chara_info["state"] = 3
            # Served by the calendar at race_out's poll, like every race beat.
            st["final"] = {"won": won, "turn": turn, "due": True,
                           "sort_id": impl.RI.goal_sort_id(chara_info, turn)}
            return
        offer = impl.offer_for(st, turn, 4, 401)
        if offer:
            sid, count = offer
            st["due"].append({"goddess": M.goddess_of(sid), "spirit_id": sid, "count": count,
                              "turn": turn, "kind": "race"})

    def hint_partners(self, full_state, chara_info, command_id, partners, hinting):
        """Godolphin's wisdom: every card on every facility shows its hint
        (§4.2); otherwise his level's hint rate gives a card that missed its
        roll a second chance at rate% of its own [INFERRED, as Beyond Dreams]."""
        st = impl.state(full_state)
        turn = impl.turn_of(chara_info)
        by_pos = formula.RF.deck(chara_info)
        normal = [p for p in partners if p in by_pos and formula.RF.is_normal_card(by_pos[p])]
        if impl.wisdom_on(st, turn, M.GODOLPHIN):
            return sorted(set(hinting) | set(normal))
        rate = impl.hint_rate(st)
        if not rate:
            return hinting
        from ...handlers import single_mode_team as smt
        out = list(hinting)
        for pos in normal:
            if pos in out:
                continue
            chance = smt._skill_hint_chance(by_pos[pos]) * rate / 100
            if impl.rng_for(full_state, "hint", turn, command_id, pos).random() < chance:
                out.append(pos)
        return out

    def hint_reveals(self, full_state, chara_info, command_id, reveals):
        """Godolphin's wisdom pays every card's hint through 400005106 alone."""
        st = impl.state(full_state)
        if impl.wisdom_on(st, impl.turn_of(chara_info), M.GODOLPHIN):
            return []
        return reveals

    def support_event_bonus_pct(self, full_state) -> int:
        """Byerley's level: support chain-event rate (§4.1, effect 9) [INFERRED
        as points on the chain share]."""
        return impl.chain_rate(impl.state(full_state)) // 10

    def race_bonus_pct(self, full_state, chara_info) -> int:
        """Darley's wisdom: race bonus +35 for the turn. The special races
        apply it as its own x1.35 (impl.reward_effects); an ordinary race on
        that turn takes it as points [INFERRED]."""
        st = impl.state(full_state)
        return 35 if impl.wisdom_on(st, impl.turn_of(chara_info), M.DARLEY) else 0

    # ----------------------------------------------------------------- flow --
    def interstitial_pending(self, full_state, chara_info, turn) -> bool:
        return impl.sprace_pending(impl.state(full_state), int(turn or 0))

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
        if ev is None or ev.source != "venus":
            return None
        st = impl.state(full_state)
        if int(event_id or 0) == producers.LEGACY[0]:
            out = []
            for g_index, g in enumerate(M.GODDESSES, start=1):
                gain = 2 * g_index - 1 if impl.level(st, g) >= 4 else 2 * g_index
                arr = event_engine.choice_reward_array(
                    {"choices": [{"effects": producers.legacy_effects(st, gain)}]}, chara_info or {})
                for row in arr:
                    out.append({"select_index": gain, "gain_param_array": row.get("gain_param_array") or []})
            return out
        if not ev.choices or len(ev.choices) < 2:
            return None
        arr = event_engine.choice_reward_array(ev.engine_event(), chara_info or {})
        if int(ev.story_id or 0) == producers.CARD_TRAINING[2]:
            # display 24: 「ランダムな{0}色の欠片を獲得」, one per goddess
            for row in arr:
                i = int(row.get("select_index") or 1)
                if 1 <= i <= 3:
                    row.setdefault("gain_param_array", []).append(
                        {"display_id": 24, "effect_value_0": M.GODDESSES[i - 1],
                         "effect_value_1": 0, "effect_value_2": 0})
        return arr

    def on_event_resolved(self, full_state, chara_info, event_id) -> dict:
        """彼女たちから、あなたたちへ (21079, the 5th goddess outing) grants Pure
        Passion through the shared machinery that also ends it."""
        if int(event_id or 0) == 21079:
            from ...handlers import single_mode_team as smt
            smt._grant_pure_passion(full_state, chara_info, M.LINK_CARD, impl.turn_of(chara_info))
        return {}

    # ------------------------------------------------------------------ run --
    def snapshot(self, full_state) -> dict:
        st = impl.state(full_state)
        return {"venus_levels": dict(st["levels"]), "venus_races": [dict(r) for r in st["races"]],
                "venus_wisdom_uses": int(st["wisdom_uses"]),
                "venus_fragments": int(st["fragments_total"])}

    def reset(self, full_state) -> None:
        impl.reset(full_state)


register(Venus())
