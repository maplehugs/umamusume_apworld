"""Archipelago self-check, no live room needed: python test_archipelago.py
(from server/, with master.mdb available). Uses throwaway state/account databases."""

import tempfile
from pathlib import Path

from app import accounts, config, master_data, social, state
from app import archipelago as ap
from app.archipelago import tables

tmp = Path(tempfile.mkdtemp())
ap.touch_account = ap.touch_master = lambda: None  # they write the real install (the game reacts)
state._db_path = lambda: tmp / "state.sqlite3"
accounts._db_path = lambda: tmp / "accounts.sqlite3"
social._db_path = lambda: tmp / "social.sqlite3"
config.load = lambda: {}

from app import dispatch  # noqa: E402 (after the databases point at tmp)
from app.handlers import collection, presents  # noqa: E402

ID = tables.item_name_to_id()
LOC = tables.location_name_to_id()


def outbox():
    out = []
    while not ap.OUTBOX.empty():
        out.append(ap.OUTBOX.get_nowait())
    return out


# ---- an unknown viewer gets in: its first login makes the account and the save
V = "777000000001"
r = dispatch.handle_decoded("load/index", {"viewer_id": V}, None)
assert r["data_headers"]["result_code"] == 1, r["data_headers"]
assert state.get_state(V) is not None and ap.target_viewer() == V
r = dispatch.handle_decoded("load/index", {"viewer_id": V}, None)
assert r["data"]["single_mode_scenario_id_array"] == [1], "URA only until the multiworld sends a scenario"

# ---- seeds: a different seed wipes the save, same profile
s = state.get_state(V)
s["load_index"]["data"]["user_info"].update(name="Maple", tutorial_step=1000)
s["marker"] = "old"
state.save_state(V, s)
assert ap.start_seed(V, "S1")
s = state.get_state(V)
assert "marker" not in s and s[ap.AP_KEY]["seed_name"] == "S1"
assert s["load_index"]["data"]["user_info"]["name"] == "Maple", "the profile stays"
assert {c["card_id"] for c in s[collection.CARD_LIST_KEY]} == set(tables.STARTING_TRAINEES)
s["marker"] = "seed1"
state.save_state(V, s)
assert not ap.start_seed(V, "S1"), "the same seed keeps its save"
assert state.get_state(V)["marker"] == "seed1"
assert ap.start_seed(V, "S2") and "marker" not in state.get_state(V), "a new seed starts over"

# ---- items
s = state.get_state(V)
st = ap.ap_state(s)
st["slot_data"] = {"maxed_supports": True, "goal": "rank_score", "goal_rank_score": 14000}
ap.apply_item(s, ID["Scenario: Unity Cup"], "Friend")
assert ap.unlocked_scenarios(s) == {1, 2}
trainee = next(c for c in tables.TRAINEES if c not in tables.STARTING_TRAINEES)
support = next(iter(tables.SSR_SUPPORTS))
ap.apply_item(s, tables.TRAINEE_ITEM_BASE + trainee)
ap.apply_item(s, tables.SUPPORT_ITEM_BASE + support)
ap.apply_item(s, ID["Progressive Speed Training"])
ap.apply_item(s, ID["Progressive Training Guard"])
ap.apply_item(s, ID["Bad Mood Trap"])
mail = [(p["reward_type"], p["reward_id"]) for p in s[presents.PRESENT_BOX_KEY]["presents"]]
assert (50, trainee) in mail and (51, support) in mail
# the tracker rates each card in its scenario (seeds before 0.15.0: all average)
st["slot_data"]["logic_support"] = 1200
average = ap.logic_estimate(st, 1)
st["slot_data"]["support_values"] = True
assert ap.logic_estimate(st, 1) - average == 12 * (tables.SUPPORT_VALUE[support][0] - 100)
state.save_state(V, s)
assert ap.start_refusal(V, 3) and ap.start_refusal(V, 2) is None
assert ap.gacha_refused(V)
banners = dispatch.handle_decoded("gacha/index", {"viewer_id": V}, None)["data"]["gacha_info_list"]
assert len(banners) == 1, "one paid-carat banner on the Archipelago save"

# claiming the mail: the support card arrives maxed, the trainee joins
presents.handle_receive_all({"viewer_id": V})
s = state.get_state(V)
card = next(c for c in s[collection.SUPPORT_CARD_KEY] if c["support_card_id"] == support)
assert card["limit_break_count"] == 4 and card["exp"] > 0
assert trainee in {c["card_id"] for c in s[collection.CARD_LIST_KEY]}

# career start: buffs and the trap; training scale and failure
ci = {"speed": 100, "stamina": 100, "power": 100, "guts": 100, "wiz": 100, "max_speed": 1200,
      "max_stamina": 1200, "max_power": 1200, "max_guts": 1200, "max_wiz": 1200, "motivation": 3, "turn": 1}
ap.apply_career_start(s, ci)
assert ci["max_speed"] == 1250 and ci["max_stamina"] == 1200 and ci["motivation"] == 1
assert ap.ap_state(s)["traps"] == []
params = ap.scale_training(s, [{"target_type": 1, "value": 10}, {"target_type": 2, "value": 10}])
assert params == [{"target_type": 1, "value": 12}, {"target_type": 2, "value": 10}]
assert ap.scale_failure(s, ci, 20) == 15

# ---- checks
outbox()
g1 = next(iter(tables.G1_RACES))
program = master_data.query_one(
    "SELECT p.id FROM single_mode_program p JOIN race_instance ri ON ri.id = p.race_instance_id "
    "WHERE ri.race_id=? LIMIT 1", (tables.G1_RACES[g1][0],))["id"]
ap.on_race_result(s, program, 1, turn=40, scenario_id=1)
assert LOC[tables.g1_location(g1)] in outbox()
ap.on_team_trials_races_won(s, 3)
assert outbox() == [LOC[tables.team_trials_location(n)] for n in (1, 2, 3)]
ap.ap_state(s)["career"]["final_place"] = 1
ap.on_career_finished(s, {"scenario_id": 1, "card_id": 100701, "fans": 300_000}, {"rank_score": 15000},
                      reached_end=True)
sent = outbox()
for name in (tables.finish_location(1), tables.rank_location(1, "S"), tables.trainee_location(100701),
             tables.fans_location(250_000)):
    assert LOC[name] in sent, name
assert "GOAL" in sent and ap.ap_state(s)["goal_done"]
# a career that never reached its end gives its traps back
st = ap.ap_state(s)
st["career"] = {"taken": [ID["Bad Mood Trap"]]}
ap.on_career_finished(s, None, None, reached_end=False)
assert st["traps"] == [ID["Bad Mood Trap"]]

# ---- Legend ladder: the save sees only its rung, the rival at the rung's strength,
# and a win is the rung's check and opens the next (race forced to a win)
from app.handlers import daily_races, trained_chara  # noqa: E402

L = "777000000003"
dispatch.handle_decoded("load/index", {"viewer_id": L}, None)
ap.start_seed(L, "S3")
outbox()
_name, _rank, row0, stats0 = tables.LEGEND_LADDER[0]
rec = dispatch.handle_decoded("legend_race/index", {"viewer_id": L}, None)["data"]["legend_race_record_array"]
assert [r["legend_race_id"] for r in rec] == [row0] and rec[0]["boss_data"]["speed"] == stats0[0]
vet = trained_chara._get_or_seed_roster(L)[0]["trained_chara_id"]
real_run = daily_races._run_race
daily_races._run_race = lambda *a, **k: dict(real_run(*a, **k), rank=1)
for ep, p in (("legend_race/race_entry", {"legend_race_id": row0, "trained_chara_id": vet}),
              ("legend_race/reflect_item_effect", {"item_id_array": []}),
              ("legend_race/race_start", {"running_style": 1}),
              ("legend_race/replay_check", {"race_result_array": []})):
    r = dispatch.handle_decoded(ep, {"viewer_id": L, **p}, None)
    assert r["data_headers"]["result_code"] == 1, (ep, r["data_headers"])
daily_races._run_race = real_run
assert outbox() == [LOC[tables.legend_location("C")]]
assert ap.legend_tier(state.get_state(L)) == 1

# ---- Unity Cup: a purple flame reads 0% failure on the turn after a blue burst
# (the next turn's rates used to be built before the training fired its bursts)
from app.handlers import single_mode_team as smt  # noqa: E402
from app.scenarios.unity_cup import impl as uc, preview  # noqa: E402

U = "777000000004"
dispatch.handle_decoded("load/index", {"viewer_id": U}, None)
real_refusal, ap.start_refusal = ap.start_refusal, lambda *a, **k: None
dispatch.handle_decoded("single_mode_team/start", {"viewer_id": U, "start_chara": {
    "card_id": 100402, "support_card_ids": [30028, 30015, 20015, 20012, 20002],
    "friend_support_card_info": {"viewer_id": 0, "support_card_id": 30010}, "scenario_id": 2}}, None)
ap.start_refusal = real_refusal
purples = 0
for _ in range(6):
    s = state.get_state(U)
    career = s[smt.STATE_KEY]["data"]
    ci = career["chara_info"]
    ci["vital"] = 100
    for m in uc.active_members(uc.state(s)):  # everyone fires blue on this training
        m["soul"] = 5
    s.pop(preview.PREVIEW_KEY, None)
    smt._refresh_command_info(ci, career["home_info"], turn=ci["turn"], full_state=s,
                              facility_levels=smt._facility_levels(career))
    preview.command_info(s, ci, career["home_info"]["command_info_array"])
    placed = (s.get(preview.PREVIEW_KEY) or {}).get("placements") or {"101": []}
    cmd = int(max(placed, key=lambda k: len(placed[k])))
    ci["vital"] = 1  # the next turn's plain rates are high
    state.save_state(U, s)
    d = dispatch.handle_decoded("single_mode_team/exec_command", {
        "viewer_id": U, "command_type": 1, "command_id": cmd, "current_turn": ci["turn"],
        "current_vital": 1}, None)["data"]
    rates = {c["command_id"]: c["failure_rate"] for c in d["home_info"]["command_info_array"]}
    for c in (d.get("team_data_set") or {}).get("command_info_array") or ():
        if c["sp_soul_event_partner_array"]:
            purples += 1
            assert rates[c["command_id"]] == 0, (ci["turn"], c["command_id"], rates)
    while d.get("unchecked_event_array"):  # the team forms through these
        ev = d["unchecked_event_array"][0]
        d = dispatch.handle_decoded("single_mode_team/check_event", {
            "viewer_id": U, "event_id": ev["event_id"], "chara_id": ev.get("chara_id"),
            "choice_number": 1 if (ev.get("event_contents_info") or {}).get("choice_array") else 0,
            "current_turn": ci["turn"]}, None)["data"]
assert purples, "no purple flame came up"

# ---- pal/group dates: Riko's middle choice unlocks, an "end the chain" arm keeps
# her unlock from coming back, and an Heirs member gets one date (Rudolf then +20/+21)
from app import event_engine  # noqa: E402
from app.handlers import pal_cards, single_mode_team  # noqa: E402

assert pal_cards.unlock_chances(30036) == {1: 0.5, 2: 1.0, 3: 0.0}
assert [len(pal_cards.member_chain(30067, m)) for m in (1017, 1003, 1073)] == [3, 1, 1]
assert pal_cards.finale_story(30067) is None and pal_cards.pure_passion_end_story(30067) == 800001001
assert not single_mode_team._queue_pal_event(
    {"data": {}}, {event_engine.CHAIN_ENDED_KEY: ["support:30036"]},
    {"data": {"chara_info": {}}}, 30036, pal_cards.unlock_story(30036), "unlock")

# ---- the panel's hint button: a line in archipelago_say.txt goes to the room as Say
from app.archipelago import client  # noqa: E402
client.say_path = lambda: tmp / "say.txt"
client.status_path = lambda: tmp / "status.json"
(tmp / "say.txt").write_text("!hint Trainee Awakening\n")
sess = client._Session("h", "s", "")
sess.connected, sent = True, []
sess._send = lambda *cmds: sent.extend(cmds)
sess._flush_outbox()
assert sent == [{"cmd": "Say", "text": "!hint Trainee Awakening"}] and not (tmp / "say.txt").exists()
sess.slot_num = 1
sess._handle({"cmd": "PrintJSON", "type": "CommandResult", "data": [{"text": "not enough points"}]})
import json  # noqa: E402
assert json.loads((tmp / "status.json").read_text())["room"]["last_reply"] == "not enough points"
# Team Trials with no team formed yet: the best umas owned race, no refusal
r = dispatch.handle_decoded("team_stadium/opponent_list", {"viewer_id": L}, None)
assert r["data_headers"]["result_code"] == 1 and r["data"]["opponent_info_array"], r["data_headers"]

# ---- Unity Cup: training a special (Rice Shower) still seeds ten teammates, none of them her
from app.scenarios.unity_cup import impl as uc  # noqa: E402
deck = [{"position": p, "support_card_id": c} for p, c in enumerate((20027, 20031, 20012, 30074, 30070, 30010), 1)]
st = {"seed": 1}
uc.ensure_roster(st, 1, {"card_id": 103001, "support_card_array": deck})
charas = [m["chara_id"] for m in st["members"]]
assert len(set(charas)) == 10 == st["base_size"] and 1030 not in charas, charas
print("archipelago self-check: ok")
