"""Great Food Festival (scenario 8, JP only) -- 大豊食祭 ("Cook").

Built on the URA base (base.Scenario's defaults ARE URA, URA finals included);
this class is the whole seam between the scenario and the shared career code,
which only ever calls hooks.

WHAT LIVES WHERE
    impl.py       the mechanics -- the garden (harvest, cares, care points),
                  cooking, tasting, dish unlocks, cooking friends, and the
                  cook_data_set
    formula.py    the training numbers (home preview, the cook bonus line,
                  friends-power effects)
    master.py     the single_mode_cook_* tables
    endpoints.py  cooking, facility_level_up, tasting, tasting_live,
                  flavor_text_read
    producers.py  the event calendar and its resolvers

docs/JP_FOOD_FESTIVAL_SCENARIO.md is the spec: every rule, number and event
here is traced there to the real server's captures, master.mdb or the client,
and its "Not exact (as built)" list names every rule shipped on a measurement
or a guess.

JP ONLY BY CONSTRUCTION: Global's master.mdb has no single_mode_cook_* tables,
so the released-and-implemented intersection never advertises it there.
"""

from __future__ import annotations

import copy

from ..base import Scenario
from ..registry import register
from . import endpoints, formula, impl, master as M, producers  # noqa: F401  (producers registers)


class Cook(Scenario):
    scenario_id = impl.SCENARIO_ID
    name = "Cook"
    endpoint_prefix = "single_mode_cook"
    data_set_key = "cook_data_set"
    data_set_on_race_start = True       # every real race_start carries cook_data_set
    state_keys = (impl.STATE_KEY,)      # impl.ACCOUNT_KEY outlives the career

    # ------------------------------------------------- shared-content gates --
    # The Director arrives with 208043 (T1) and the Reporter with 208053 (T13):
    # single_mode_events.NPC_UNLOCKS. The real turn-78 chain is 101006 -> 2 ->
    # 10 -> the ending (208029 / 208038 / 208030) -> 32 -> 6.
    uses_fixed_schedule = False
    has_versus_npc = False
    debut_reporter_event = 0
    has_director_ending = False
    has_reporter_ending = False
    finals_events = {
        1: {"pre": (101001, 400000101, False), "post": (101002, 400000104, 12)},
        2: {"pre": (101003, 400000102, False), "post": (101004, 400000105, 13)},
        3: {"pre": (101005, 400000103, False), "post": (101006, 400000106, 14)},
    }
    _FINALS_POST = {101002: 74, 101004: 76, 101006: 78}

    # 23 the tasting (CookTasting), 24 the T72 live.
    playing_states = frozenset({5, 23, 24})
    turn_end_hold_state = 5
    locked_npc_rows = impl.npc_rows()
    npc_targets = frozenset(t for t, _c in impl.npc_rows())

    # The level-up banners by facility. Exact-after-verify: the five ids are
    # seen, which facility each belongs to is assumed in id order.
    LEVELUP_EVENTS = {101: 208033, 105: 208034, 102: 208035, 103: 208036, 106: 208037}

    def facility_levelup_event(self, command_id) -> tuple:
        return (self.LEVELUP_EVENTS.get(formula.base_of(command_id), 208033), 400000005)

    def appraisal_events(self):
        return {102: [(90, 208042, 5), (70, 208041, 4), (40, 208040, 3), (0, 208039, 2)],
                103: [(90, 1010, 5), (70, 1009, 4), (40, 1008, 3), (0, 1007, 2)]}

    def npc_supporters(self, full_state, chara_info) -> list:
        """The cooking friends train alongside from 208006 on: bodies with no
        bond and no events, as Ramen's NPC charas."""
        st = impl.state(full_state)
        return list(st["friends"]) if st["roster"] else []

    # ------------------------------------------------------------ endpoints --
    def extra_endpoints(self) -> dict:
        return dict(endpoints.HANDLERS)

    # ------------------------------------------------------------- response --
    def command_info(self, full_state, chara_info, home_commands):
        """Recompute the turn's overlay (bonus lines, cares) from the
        facilities about to be served. Persist when anything moved or a
        one-shot flag is waiting for attach()."""
        if not isinstance(chara_info, dict):
            return None, False
        from ...handlers import single_mode_team as smt
        st = impl.state(full_state)
        started = impl.ensure_started(st, chara_info)
        before = copy.deepcopy(st["preview"])
        impl.refresh_preview(full_state, chara_info, home_commands or [],
                             smt._support_card_levels(full_state), impl.turn_of(chara_info))
        return None, bool(started or st["flags"] or st["preview"] != before
                          or st["cook_flags"]["garden_level_up"])

    def attach(self, response, full_state, chara_info, command_info_array=None, endpoint=""):
        data = (response or {}).get("data")
        if not isinstance(data, dict):
            return response
        load_ci = (data.get("single_mode_load_common") or {}).get("chara_info")
        start_ci = (data.get("single_mode_start_common") or {}).get("chara_info")
        ci = chara_info if isinstance(chara_info, dict) else (load_ci or start_ci)
        if not isinstance(ci, dict):
            return response
        from ...handlers import single_mode_team as smt
        st = impl.state(full_state)
        impl.ensure_started(st, ci)
        call = (endpoint or "").rsplit("/", 1)[-1]
        if impl.career_over(ci):
            for c in (chara_info, load_ci):
                if isinstance(c, dict) and int(c.get("playing_state") or 1) == 1:
                    c["playing_state"] = 5
        home = data.get("home_info")
        for holder in (data.get("single_mode_load_common"), data.get("single_mode_start_common")):
            if not isinstance(home, dict) and isinstance(holder, dict):
                home = holder.get("home_info")
        if not isinstance(home, dict):
            home = ((full_state.get(smt.STATE_KEY) or {}).get("data") or {}).get("home_info") or {}
        commands = list(home.get("command_info_array") or ())
        turn = self._served_turn(full_state, ci, data)
        # garden_level_up_flag lives to the next check_event (§8).
        if call == "check_event" and st["cook_flags"]["garden_level_up"]:
            if st["flags"].get("glu_seen"):
                st["cook_flags"]["garden_level_up"] = 0
                st["flags"].pop("glu_seen", None)
            else:
                st["flags"]["glu_seen"] = True
        full = self._reply_is_full(call, data, ci)
        data["cook_data_set"] = impl.data_set(full_state, ci, commands, turn, full,
                                              start=(call == "start"))
        for holder in (data.get("single_mode_start_common"), data.get("single_mode_load_common")):
            if isinstance(holder, dict):
                holder.pop("cook_data_set", None)
        # Mid-chain the real home_info carries null previews, as the data set does.
        if not full and isinstance(data.get("home_info"), dict):
            data["home_info"] = dict(data["home_info"])
            data["home_info"]["command_info_array"] = [
                dict(c, params_inc_dec_info_array=None) if c.get("command_type") == 1 else dict(c)
                for c in data["home_info"].get("command_info_array") or ()]
        for ev in data.get("unchecked_event_array") or ():
            post = self._FINALS_POST.get(int(ev.get("event_id") or 0))
            if post:
                (ev.get("event_contents_info") or {})["show_clear_sort_id"] = \
                    impl.RI.goal_sort_id(ci, post)
        return response

    @staticmethod
    def _reply_is_full(call: str, data: dict, chara_info: dict) -> bool:
        """The command rows ride only the reply that leaves the client on its
        training screen: start, load, cooking, facility_level_up, tasting_live,
        and a check_event / exec_command ending the chain at playing_state 1."""
        if impl.career_over(chara_info) and call != "load":
            return False
        if call in ("start", "load", "cooking", "facility_level_up", "tasting_live"):
            return True
        if call not in ("check_event", "exec_command"):
            return False
        return (not data.get("unchecked_event_array")
                and int(chara_info.get("playing_state") or 1) == 1)

    def _served_turn(self, full_state: dict, chara_info: dict, data: dict) -> int:
        """The turn the client is shown: a tasting's hold, else the turn-end
        hold the response chokepoint is about to apply, else the run's turn."""
        from ...handlers import single_mode_team as smt
        st = impl.state(full_state)
        if int(st.get("hold_turn") or 0):
            return int(st["hold_turn"])
        turn = impl.turn_of(chara_info)
        events = data.get("unchecked_event_array") or []
        head = events[0] if events and isinstance(events[0], dict) else {}
        if (turn > 1 and int(head.get("play_timing") or 0) in self.turn_end_timings
                and int(full_state.get(smt._TURN_HOLD_RELEASED_KEY) or 0) != turn):
            return turn - 1
        return turn

    # ------------------------------------------------------------- training --
    def training_gains(self, full_state, chara_info, command_id, facility_level, camp, partners):
        from ...handlers import single_mode_team as smt
        served = formula.BASE_TO_SUMMER.get(command_id, command_id) if camp else command_id
        return formula.home_gains(chara_info, served, facility_level, partners,
                                  smt._support_card_levels(full_state))

    def training_award_bonus(self, full_state, chara_info, command_id) -> list:
        """The cook bonus line the client saw on this facility (§7), paid on
        top of home_info's."""
        row = impl.training_row(impl.state(full_state), command_id, impl.turn_of(chara_info))
        return [dict(p) for p in row.get("line") or ()]

    def award_training_gains(self, full_state, chara_info, payload) -> None:
        """A successful command: a training's care lands on its own reply; a
        rest or outing queues its care event (§3)."""
        st = impl.state(full_state)
        turn = int(payload.get("current_turn") or impl.turn_of(chara_info))
        ctype = int(payload.get("command_type") or 0)
        cmd = int(payload.get("command_id") or 0)
        if ctype == 1:
            care = impl.training_row(st, cmd, turn).get("care")
            if care:
                impl.apply_care(st, care, turn)
            impl.set_last_command(st, turn, 1, cmd, 2)
            return
        if ctype == 7 or cmd == 701:
            st["due"].append({"kind": "rest", "turn": turn, "spec": impl.care_spec(st, "rest", turn)})
            impl.set_last_command(st, turn, 7, 701, 2)
        elif ctype == 3:
            yayoi = int(payload.get("select_id") or 0) == impl.YAYOI
            st["due"].append({"kind": "yayoi" if yayoi else "outing", "turn": turn,
                              "spec": impl.care_spec(st, "yayoi" if yayoi else "rest", turn)})
            st["yayoi_due"] = yayoi
            group = int(payload.get("command_group_id") or 0) or cmd
            impl.set_last_command(st, turn, 3, group, 2)

    def on_training_failed(self, full_state, chara_info, payload) -> None:
        """§3a: the care without its tag lands on 208031's check_event."""
        st = impl.state(full_state)
        turn = int(payload.get("current_turn") or impl.turn_of(chara_info))
        cmd = int(payload.get("command_id") or 0)
        st["due"].append({"kind": "fail", "turn": turn, "spec": impl.care_spec(st, "fail", turn, cmd)})
        impl.set_last_command(st, turn, 1, cmd, 1)

    def on_race_result(self, full_state, chara_info, race_ctx, result_rank) -> None:
        st = impl.state(full_state)
        turn = int(race_ctx.get("turn") or impl.turn_of(chara_info))
        impl.set_last_command(st, turn, 4, 401, 0)
        if turn < 78:                   # none after the last finals race
            st["due"].append({"kind": "race", "turn": turn, "spec": impl.care_spec(st, "race", turn)})

    def specialty_rate_pct(self, full_state) -> int:
        """Friends-power 206 as the 得意率 multiplier, as Onsen's rank is.
        NOT EXACT: the meaning is the client's text, the form unproven (§7)."""
        return formula.power_effect(int(impl.state(full_state)["power"]), 206)

    def fan_bonus_pct(self, full_state, chara_info) -> int:
        """Friends-power 208: fan gain % (§7b, Exact as a multiplier)."""
        return formula.power_effect(int(impl.state(full_state)["power"]), 208)

    def race_bonus_pct(self, full_state, chara_info) -> int:
        """Dish effect 21 on the turn it was eaten (§7a2, 6/6)."""
        return impl.dish_race_pct(impl.state(full_state), impl.turn_of(chara_info))

    def partner_placements(self, full_state, chara_info, turn, occupied=None, standing=None) -> dict:
        """Success effect 204's extra cards for the turn (§9)."""
        return impl.extra_partners(impl.state(full_state), int(turn or 0))

    # ----------------------------------------------------------------- flow --
    def interstitial_pending(self, full_state, chara_info, turn) -> bool:
        turn = int(turn or 0)
        if impl.tasting_pending(impl.state(full_state), turn):
            return True
        return producers.closing_pending(full_state, chara_info, turn)

    def begin_hold(self, full_state, turn) -> None:
        """Only a tasting holds the served turn (until its result); a closing
        story rides the shared turn-end hold."""
        st = impl.state(full_state)
        if impl.tasting_pending(st, int(turn or 0)):
            st["hold_turn"] = int(turn or 0)

    def held_turn(self, full_state) -> int:
        return int(impl.state(full_state).get("hold_turn") or 0)

    def holds_chain_after(self, event_id) -> bool:
        return int(event_id or 0) in producers.SCREEN_EVENTS

    def choice_reward_preview(self, full_state, chara_info, event_id):
        from ... import career_events as CE
        from ... import event_engine
        ev = CE.find(full_state, event_id)
        if ev is None or ev.source != "cook" or not ev.choices:
            return None
        return event_engine.choice_reward_array(ev.engine_event(), chara_info or {})

    def on_event_resolved(self, full_state, chara_info, event_id) -> dict:
        from ... import career_events as CE
        event_id = int(event_id or 0)
        turn = impl.turn_of(chara_info)
        st = impl.state(full_state)
        if event_id == 1001 and turn <= 1:
            for ev in producers.opening_events():
                CE.emit(full_state, ev)
        elif event_id in producers.STORY_ENDING_TRIGGERS and turn >= 78:
            ev = producers.ending_event(full_state)
            if ev:
                CE.emit(full_state, ev)
        elif st.get("yayoi_due") and event_id != producers.CARE_YAYOI[0]:
            # The Yayoi outing's own story resolved: +40 of each on the reply
            # that carries 208054 (3/3).
            st["yayoi_due"] = False
            impl.flag(st, "event_gain", impl.add_materials(st, impl.YAYOI_MATERIALS))
        return {}

    # ------------------------------------------------------------------ run --
    def snapshot(self, full_state) -> dict:
        st = impl.state(full_state)
        return {"cook_results": [dict(r) for r in st["results"]],
                "cook_friends_power": int(st["power"])}

    def reset(self, full_state) -> None:
        impl.reset(full_state)


register(Cook())
