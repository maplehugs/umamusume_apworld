"""Pal (friend) and Group support cards: outings, chains and the Pure Passion buff.

Decoded from the user's real capture (UmaDumpy 20260726_174114, a URA run with
Tazuna 30021 / Riko 30036 / Kiryuin 20021 / Light Hello 30052 pal cards plus the
Symboli Rudolf 30067 and Special Week 30081 GROUP cards) + master.mdb.

master.mdb facts
----------------
support_card_data.support_card_type: 1 = normal trainer, **2 = pal**, **3 = group**
  (only 12 such cards exist: 10021/10022/10060/10074/10083/20021/30021/30036/
  30052/30080 pal, 30067/30081 group).
support_card_group(support_card_id, chara_id, outing_max): a group card's
  members, in id order -- 30067 = Rudolf 1017, Tokai Teio 1003, Tsurumaru 1073;
  30081 = McQueen 1013, Rice 1030, Winning Ticket 1035, Narita Brian 1016,
  Suzuka 1002, Special Week 1001. outing_max is 1 for every member: each member
  may be gone out with exactly ONCE.
single_mode_outing id 3 = command_group_id **390**, condition 1 -- the outing
  command itself, gated on something being unlocked (unlike 301 riverbank /
  304 camp, which are condition 0).
text_data cat 142/143 conditions 100/101/102 = "Pure Passion: Team Sirius /
  Heirs to the Throne / Progenitors and Guides" -- "Able to do Friendship
  Training with <group>, and immune to Night Owl and Slacker."

Story-id layout (both bases are 8 + <5-digit id> + <3-digit suffix>)
-------------------------------------------------------------------
PAL cards key by CHARA id (809001nnn = Tazuna), GROUP cards by CARD id
(830067nnn = Rudolf's group card). Suffixes, capture-confirmed:

  pal   +2  first-training meeting   ("Tazuna, the Director's Secretary")
        +3  repeatable training event ("Good Job! ♪")
        +4  OUTING UNLOCK, multi-choice ("Enthusiastic Pair" / "Unexpected Side")
        +5..+10  the outing chain, one per outing, in order
        +11 end-of-run bond finale   ("A Bond with Tazuna: ...")
  group +1  first-training meeting   ("Diamonds in the Rough")
        +2  OUTING UNLOCK            ("Emulation Is the Sincerest Form of Flattery")
        +3  repeatable training event ("We'll Get Stronger, Together")
        +5+i outing with member i (support_card_group order) -- capture:
             select_id 1017 -> +5, 1003 -> +6, 1073 -> +7
        +20.. / +30..  the "outed with everyone" finale events

Wire flow (capture, request/response de-shifted)
-----------------------------------------------
  exec_command {command_type: 3, command_group_id: 390, select_id: <chara_id>}
  -> response serves that partner's outing event; acking it bumps the card's
     evaluation_info_array[pos].story_step by 1.
  The unlock is evaluation_info_array[pos].is_outing flipping 0 -> 1 when the
  +4/+2 event's unlocking choice resolves. In choice_reward_array the unlock is
  gain_param_array display_id **11** (effect_value_0 = the chara/partner id);
  a choice whose select_index appears TWICE, once with display_id 11 and once
  without, is the GAMBLE choice (Riko's top option -- capture-confirmed 2
  variants for select_index 1).
"""

from __future__ import annotations

import functools

from .. import master_data

PAL_TYPE = 2
GROUP_TYPE = 3

# Suffix roles. Pal and group cards number their stories differently.
PAL_FIRST, PAL_RANDOM, PAL_UNLOCK = 2, 3, 4
PAL_CHAIN = range(5, 9)           # +5..+8, one per outing (show_progress_1 1..4;
                                  # the New Year +11 is the gauge's 5th step)
PAL_FINALE = 11
# The T78 sendoff: +9 when every date was walked, +10 when not. Never a date --
# in 60+ JP careers they only ever play at the career's last turn (78, L'Arc
# 67); serving them as outings 5 and 6 was a bug (sweep 2026-10-11).
PAL_ENDING_COMPLETE, PAL_ENDING_INCOMPLETE = 9, 10
GROUP_FIRST, GROUP_UNLOCK, GROUP_RANDOM = 1, 2, 3
GROUP_CHAIN_BASE = 5              # +5 + member index
GROUP_FINALE = range(20, 40)      # +20.. / +30.. "outed with everyone"

# A pal card with its OWN kit inside the chara band, +100 on from the older
# cards' (JP SSR Tazuna 30305, 809001101..): capture-confirmed across 64
# scenario-14 careers -- +101 first meeting (21245), +104 unlock (21253, BOTH
# choices unlock), +132 repeatable (21252), +111..+115 the dates (21246-21250,
# single_mode_story_data.show_progress_1 1..5), +121 New Year (21251). Picked
# off master: the card owns a story row at +101. No Global card does.
LINK_FIRST, LINK_RANDOM, LINK_UNLOCK = 101, 132, 104
LINK_FINALE = 121

# ...AND IT GOES OUT UNDER ITS OWN WIRE IDS, not the 10002 / play_timing 1 of
# the older cards: story suffix -> (event_id, play_timing), same 64 careers.
# The timing is what matters. The first meeting, the dates and the repeatable
# event are play_timing 6 -- beats that conclude the turn just trained, served
# under that turn with playing_state 5 -- and only the unlock and New Year open
# a turn. Served as a turn opener instead, the repeatable event advanced the
# turn mid-chain, and in the Ramen finals the client hung on the empty home
# screen after it (live-reported 2026-09-26, "期待していますね♪" on turn 73).
LINK_WIRE = {30305: {LINK_FIRST: (21245, 6), LINK_UNLOCK: (21253, 1),
                     LINK_RANDOM: (21252, 6), LINK_FINALE: (21251, 1),
                     111: (21246, 6), 112: (21247, 6), 113: (21248, 6),
                     114: (21249, 6), 115: (21250, 6)},
             # JP SSR Hoshina Kiyoko 30276, Onsen's link friend (scenario 12):
             # the same kit at offset +0 (see LINK_KIT_OFFSET), wire ids off
             # 611 real careers (docs/JP_ONSEN_SCENARIO.md §13.3). +31 went out
             # as the generic 20000 random-event id.
             30276: {1: (21211, 6), 4: (21223, 1), 32: (21218, 6), 21: (21217, 1),
                     11: (21212, 6), 12: (21213, 6), 13: (21214, 6),
                     14: (21215, 6), 15: (21216, 6), 31: (20000, 1)},
             # JP SSR Casino Drive 30290, Beyond Dreams' link friend (scenario
             # 13): the same kit at +0 in chara band 801139 -- first meeting +1,
             # unlock +4, dates +11..+15, New Year +21, repeatable +32 (7 real
             # careers, docs/JP_BEYOND_DREAMS_SCENARIO.md §5.2).
             30290: {1: (21228, 6), 4: (21240, 1), 21: (21234, 1), 32: (21235, 6),
                     11: (21229, 6), 12: (21230, 6), 13: (21231, 6),
                     14: (21232, 6), 15: (21233, 6)},
             # ...and her R card 10141: the shared first meeting and dates, her
             # own unlock at +2 (801139002, generic 10002) and repeatable 21236.
             10141: {1: (21228, 6), 21: (21234, 1), 32: (21236, 6),
                     11: (21229, 6), 12: (21230, 6), 13: (21231, 6),
                     14: (21232, 6), 15: (21233, 6)},
             # JP R Hoshina Kiyoko 10138 (1 real career, 2026-09-30): the
             # chara-keyed kit shared with her SSR, but her own two-step unlock
             # +2 -> +3 (served on consecutive turns), the repeatable +32 under
             # 21219 (the SSR's is 21218), her own +33 (21220) and the ending
             # +22 (event 38) instead of the SSR's +23.
             10138: {1: (21211, 6), 2: (21221, 1), 3: (21222, 1), 21: (21217, 1),
                     11: (21212, 6), 12: (21213, 6), 13: (21214, 6),
                     14: (21215, 6), 15: (21216, 6), 31: (20000, 1),
                     32: (21219, 6), 33: (21220, 6), 22: (38, 3)},
             # JP Tucker Brine, Design Your Island's link friend (scenario 11):
             # the same kit at +0 in chara band 809049 -- first meeting +1,
             # dates +11..+15, New Year +21, repeatable +32 (umacap + headless
             # careers, docs/JP_DESIGN_YOUR_ISLAND_SCENARIO.md §11). The SSR
             # 30257 unlocks at +4 (seen as both 21174 and 10002, so left on
             # the generic envelope); the R 10128 in two steps +2 -> +3 on
             # consecutive turns, with its own repeatable 21170 and +31 (20000).
             30257: {1: (21162, 6), 21: (21168, 1), 32: (21169, 6),
                     11: (21163, 6), 12: (21164, 6), 13: (21165, 6),
                     14: (21166, 6), 15: (21167, 6)},
             10128: {1: (21162, 6), 2: (21172, 1), 3: (21173, 1), 21: (21168, 1),
                     32: (21170, 6), 31: (20000, 1),
                     11: (21163, 6), 12: (21164, 6), 13: (21165, 6),
                     14: (21166, 6), 15: (21167, 6)}}

# Where a link kit sits in its chara band. SSR Tazuna's is found by its +101
# first meeting (the default, 100); Kiyoko's kit is the same layout at +0 --
# first +1, unlock +4, dates +11..+15 (show_progress_1 1..5), New Year +21,
# repeatable +32 -- which the +101 probe cannot see, so it is named here.
LINK_KIT_OFFSET = {30276: 0, 30290: 0, 10141: 0, 10138: 0, 30257: 0, 10128: 0}
# A link card whose unlock is not at its kit's +4 (Casino's R card: +2).
LINK_UNLOCK_SUFFIX = {10141: 2, 10138: 3, 10128: 3}
# A link card whose unlock comes in two steps: this story plays when the
# unlock roll hits, and the unlock story itself on the next turn.
LINK_PRE_UNLOCK_SUFFIX = {10138: 2, 10128: 2}
_LINK_BASE = 100          # the offset LINK_FIRST & co. are written against


def wire_ids(card_id: int, sid: int) -> tuple | None:
    """(event_id, play_timing) this card's story goes out under, or None for
    the generic support envelope."""
    kit = group_kit(card_id)
    if kit and sid == kit.get("passion_end"):
        return kit.get("passion_end_wire")
    if kit.get("wire"):
        return kit["wire"].get(sid - story_base(card_id))
    table = LINK_WIRE.get(card_id)
    return table.get(sid - story_base(card_id)) if table else None

# support_card_id -> the Pure Passion condition its group grants (text_data cat
# 142: 100 "Team Sirius", 101 "Heirs to the Throne", 102 "Progenitors and
# Guides"; cat 143 spells out what it does -- "Able to do Friendship Training
# with <group>, and immune to Night Owl and Slacker").
#
# 30081 WAS WRONG HERE (102). Its own unlock event, "We're All Shining Stars",
# carries condition_id 100 -- Special Week's group IS Team Sirius -- so it was
# granting a condition the client has no group for. Read off the event data now
# (pure_passion_condition) with this dict only as the fallback, since the event
# is the thing that actually hands the condition out.
PURE_PASSION = {30067: 101, 30081: 100, 30137: 102, 30241: 104}

# HOW LONG IT LASTS: 3-5 turns, rolled per grant (user-reported). The capture's
# one observed window -- gained turn 4, still on at 7, gone during 7 -- sits
# inside that range and is what the old fixed 4 was built from.
PURE_PASSION_TURNS_MIN = 3
PURE_PASSION_TURNS_MAX = 5

# GROUP CARDS WHOSE KIT IS NOT THE +1/+2/+3/+4/+5+i/+20 LAYOUT ABOVE. Keyed by
# card id; every other group card reads the defaults.
#
# JP SSR 30137 祖にして導く者 (Grand Masters' goddesses, members 9040/9041/9042),
# read off 6 real careers (docs/JP_GRAND_MASTERS_SCENARIO.md §9):
#   * each goddess's first outing is her +5+i story (005/006/007) and nothing
#     else -- the 8090400xx stories under her chara band are random events;
#   * once all three are done, outings with the card's own chara (Darley) play
#     +20 then +21; any other outing is a plain one;
#   * +3 (三女神の気分転換トレーニング) is served by the scenario itself (it hands
#     out knowledge fragments), so it is not the kit's repeatable; +4
#     (たった2つの預け先) is an ordinary random event;
#   * Pure Passion ends through the shared 800001001 集中力の区切り (21081),
#     lasts 2-6 turns, and is never granted by a random training roll;
#   * the wire ids per story.
GROUP_KITS = {
    30137: {
        "after_members": (20, 21), "after_partner": 9040,
        "random": None, "finale": None, "random_passion": False,
        "passion_turns": (2, 6), "passion_end": 800001001,
        "passion_end_wire": (21081, 1),
        "reserved": (1, 2, 3, 5, 6, 7, 20, 21, 30, 31, 32), "new_year": 32,
        "wire": {1: (21072, 6), 5: (21075, 6), 6: (21076, 6), 7: (21077, 6),
                 20: (21078, 6), 21: (21079, 6), 32: (21080, 1)},
    },
    # JP SSR 30241 伝説の体現者【導きの光】 (Twinkle Legends' legends, members
    # 9046/9047/9048), the same shape as 30137 off 6 real careers
    # (docs/JP_TWINKLE_LEGENDS_SCENARIO.md §12):
    #   * each legend's date is her own story -- 005 St Lite, 006 Speed
    #     Symboli, 007 Haiseiko -- which is NOT support_card_group's id order
    #     (9047, 9046, 9048), hence "member_story";
    #   * dates 4-5 (020, 021) with the card's own chara (Speed Symboli) once
    #     all three are done; any other outing pays nothing;
    #   * +3 伝説級のお食事会！？ is served by the scenario (it moves a gauge),
    #     +4 かつての学び舎 is an ordinary random event; New Year 032 too;
    #   * passion ends through 800001001 under 21158; the unlock goes out as
    #     10002 (4 careers) or 21150 (2).
    30241: {
        "after_members": (20, 21), "after_partner": 9047,
        "member_story": {9046: 5, 9047: 6, 9048: 7},
        # its unlock (002) hands out ポジティブ思考 (25) before the passion (104)
        "passion_condition": 104,
        "random": None, "finale": None, "random_passion": False,
        "passion_turns": (2, 6), "passion_end": 800001001,
        "passion_end_wire": (21158, 1),
        "reserved": (1, 2, 3, 5, 6, 7, 20, 21, 30, 31, 32), "new_year": 32,
        "wire": {1: (21149, 6), 2: (10002, 1), 5: (21152, 6), 6: (21153, 6), 7: (21154, 6),
                 20: (21155, 6), 21: (21156, 6), 32: (21157, 1)},
    },
}


def group_kit(card_id: int) -> dict:
    return GROUP_KITS.get(int(card_id or 0), {})


# MEASURED length (docs/SUPPORT_EVENT_CHANCES.md §2, 44 real JP windows,
# applied 2026-10-11, user-approved): 2-6 turns, short windows dominate.
PURE_PASSION_TURN_WEIGHTS = {2: 0.32, 3: 0.30, 4: 0.23, 5: 0.11, 6: 0.05}


def roll_passion_turns(card_id: int) -> int:
    """Every group card (both measured cards, assumed for 30067/30081)."""
    import random
    turns, weights = zip(*PURE_PASSION_TURN_WEIGHTS.items())
    return random.choices(turns, weights)[0]


def passion_turns(card_id: int) -> tuple:
    return group_kit(card_id).get("passion_turns") or (PURE_PASSION_TURNS_MIN,
                                                       PURE_PASSION_TURNS_MAX)


def random_passion(card_id: int) -> bool:
    """Whether training with this group card can re-grant Pure Passion."""
    return group_kit(card_id).get("random_passion", True)

# ...AND HOW IT ENDS: the group's +4 story, the one suffix the chain never
# claimed (30067 "The Bright Future Ahead", 30081 "Teamwork Makes the Dream
# Work!"). Every other group suffix is accounted for -- +1 first meeting, +2
# unlock, +3 repeatable, +5+i the per-member outings, +20.. the finales -- and
# neither +4 carries a condition effect of its own, which is what an event that
# TAKES the buff away rather than granting it looks like.
GROUP_PASSION_END = 4

# Per-card unlock semantics for the +4/+2 event, keyed by the card's story
# owner (chara id for pal cards, card id for group cards):
#   {select_index: probability the outing unlocks}
# EXPLICIT OVERRIDES only -- capture ground truth. Everything else is derived
# from the event data itself by unlock_chances(): a choice flagged
# random_either is the gamble (50/50) and no other choice unlocks; an event
# with no gamble unlocks on choice 1. That reproduces every known card --
# Tazuna/Kiryuin (2 plain choices -> top guaranteed), Riko/Sasami (choice 1
# random_either -> the gamble), both group cards (single ack choice).
_DEFAULT_UNLOCK = {1: 1.0}
UNLOCK_CHANCE: dict[int, dict[int, float]] = {
    9001: {1: 1.0, 2: 0.0},       # Tazuna -- capture: display_id 11 on choice 1 only
    9006: {1: 0.5, 2: 0.0, 3: 0.0},  # Riko -- capture: choice 1 dual-variant (gamble)
}
_GAMBLE_CHANCE = 0.5


@functools.lru_cache(maxsize=64)
def pure_passion_condition(card_id: int) -> int:
    """The chara_effect id this group card's unlock event hands out, read off
    the event itself; PURE_PASSION is the fallback for a card whose GameTora
    data we don't have cached."""
    if group_kit(card_id).get("passion_condition"):
        return int(group_kit(card_id)["passion_condition"])
    from .. import event_engine
    sid = unlock_story(card_id) if is_group(card_id) else None
    if sid:
        _title, ev = event_engine.event_by_story_id(card_id, sid)
        for choice in (ev or {}).get("choices") or ():
            for eff in choice.get("effects") or ():
                if eff.get("type") == "condition" and eff.get("condition_id"):
                    return int(eff["condition_id"])
    return PURE_PASSION.get(card_id, 0)


def pure_passion_card(condition_id: int) -> int:
    """Which group card owns a live Pure Passion condition -- the reverse of
    pure_passion_condition, for the expiry path, which knows the condition it
    just dropped and needs the card whose end-of-buff story to serve."""
    for card_id in PURE_PASSION:
        if pure_passion_condition(card_id) == int(condition_id or 0):
            return card_id
    return 0


def pure_passion_conditions() -> frozenset:
    """Every condition id any group card can grant -- what to strip from
    chara_effect_id_array before re-adding the ones still live."""
    return frozenset(pure_passion_condition(c) for c in PURE_PASSION) - {0}


def pure_passion_end_story(card_id: int) -> int | None:
    """The story that plays when this group's Pure Passion runs out."""
    if group_kit(card_id).get("passion_end"):
        return int(group_kit(card_id)["passion_end"])
    return story_id(card_id, GROUP_PASSION_END) if is_group(card_id) else None


@functools.lru_cache(maxsize=512)
def card_row(card_id: int) -> tuple:
    """(support_card_type, chara_id) for a support card, or (1, 0)."""
    row = master_data.query_one(
        "SELECT support_card_type, chara_id FROM support_card_data WHERE id=?",
        (card_id,))
    if row is None:
        return (1, 0)
    return (row["support_card_type"] or 1, row["chara_id"] or 0)


def card_type(card_id: int) -> int:
    return card_row(card_id)[0]


def is_pal(card_id: int) -> bool:
    return card_type(card_id) == PAL_TYPE


def is_group(card_id: int) -> bool:
    return card_type(card_id) == GROUP_TYPE


def is_pal_or_group(card_id: int) -> bool:
    return card_type(card_id) in (PAL_TYPE, GROUP_TYPE)


@functools.lru_cache(maxsize=64)
def group_members(card_id: int) -> tuple:
    """(chara_id, ...) of a group card's members, in support_card_group order --
    which is also the order their outing stories are numbered (+5 + index)."""
    return tuple(r["chara_id"] for r in master_data.query(
        "SELECT chara_id FROM support_card_group WHERE support_card_id=? ORDER BY id",
        (card_id,)))


def story_base(card_id: int) -> int:
    """The 8xxxxxnnn base this card's stories are numbered from: pal cards key
    by their CHARA id, group cards by the CARD id."""
    ctype, chara = card_row(card_id)
    key = chara if ctype == PAL_TYPE else card_id
    return 800000000 + key * 1000


def story_owner(card_id: int) -> int:
    """The id UNLOCK_CHANCE / outing select_id are keyed by (chara for pal,
    card for group)."""
    ctype, chara = card_row(card_id)
    return chara if ctype == PAL_TYPE else card_id


def partners(card_id: int) -> tuple:
    """Who this card lets you go out WITH: a pal card is one person; a group
    card is each of its members."""
    if is_pal(card_id):
        return (card_row(card_id)[1],)
    if is_group(card_id):
        return group_members(card_id)
    return ()


@functools.lru_cache(maxsize=64)
def link_offset(card_id: int):
    """This pal card's link-kit offset in its chara band (100 for SSR Tazuna's
    +101.. kit, LINK_KIT_OFFSET's for the others), or None when it has none."""
    if not is_pal(card_id):
        return None
    if card_id in LINK_KIT_OFFSET:
        return LINK_KIT_OFFSET[card_id]
    if master_data.query_one(
            "SELECT 1 FROM single_mode_story_data WHERE story_id=? AND support_card_id=?",
            (story_base(card_id) + LINK_FIRST, card_id)):
        return _LINK_BASE
    return None


@functools.lru_cache(maxsize=64)
def _link_chain(card_id: int) -> tuple:
    """The dates of a pal card with its own link kit (see LINK_FIRST), in
    show_progress_1 order; () for every other card. A kit's dates are its
    +11..+19 rows owned by the card itself or by its chara at large (Kiyoko's
    are chara-keyed: support_card_id 0, support_chara_id 9050), never another
    card's (her R card's rows in the same band)."""
    offset = link_offset(card_id)
    if offset is None:
        return ()
    base = story_base(card_id) + offset
    chara = card_row(card_id)[1]
    rows = master_data.query(
        "SELECT DISTINCT story_id, show_progress_1 FROM single_mode_story_data "
        "WHERE (support_card_id=? OR (support_card_id=0 AND support_chara_id=?)) "
        "AND show_progress_1>0 AND story_id BETWEEN ? AND ? "
        "ORDER BY show_progress_1", (card_id, chara, base + 10, base + 19))
    return tuple(int(r["story_id"]) for r in rows)


def _pal_suffix(card_id: int, old: int, link: int) -> int:
    offset = link_offset(card_id)
    return old if offset is None else link - _LINK_BASE + offset


@functools.lru_cache(maxsize=512)
def _existing_suffixes(card_id: int) -> frozenset:
    base = story_base(card_id)
    return frozenset(r["index"] - base for r in master_data.query(
        "SELECT [index] FROM text_data WHERE category=181 AND [index] BETWEEN ? AND ?",
        (base, base + 999)))


def story_id(card_id: int, suffix: int) -> int | None:
    """The story id for a suffix, or None when this card has no such story."""
    return story_base(card_id) + suffix if suffix in _existing_suffixes(card_id) else None


def first_meeting_story(card_id: int) -> int | None:
    return story_id(card_id, _pal_suffix(card_id, PAL_FIRST, LINK_FIRST)
                    if is_pal(card_id) else GROUP_FIRST)


def unlock_story(card_id: int) -> int | None:
    if card_id in LINK_UNLOCK_SUFFIX:
        return story_id(card_id, LINK_UNLOCK_SUFFIX[card_id])
    return story_id(card_id, _pal_suffix(card_id, PAL_UNLOCK, LINK_UNLOCK)
                    if is_pal(card_id) else GROUP_UNLOCK)


def pre_unlock_story(card_id: int) -> int | None:
    """The first step of a two-step unlock (LINK_PRE_UNLOCK_SUFFIX), else None."""
    suffix = LINK_PRE_UNLOCK_SUFFIX.get(card_id)
    return story_id(card_id, suffix) if suffix else None


def random_story(card_id: int) -> int | None:
    if "random" in group_kit(card_id):
        suffix = group_kit(card_id)["random"]
        return story_id(card_id, suffix) if suffix else None
    return story_id(card_id, _pal_suffix(card_id, PAL_RANDOM, LINK_RANDOM)
                    if is_pal(card_id) else GROUP_RANDOM)


@functools.lru_cache(maxsize=64)
def member_chain(card_id: int, member: int) -> tuple:
    """A group member's own outing chain: their card-band story (+5 + index)
    followed by their personal sub-chain, which lives in the MEMBER's own
    80<chara>nnn band -- e.g. Tokai Teio's 801003001 'My Way, Or...' and
    801003002 'My Weapon' under Rudolf's card.

    Derived from THIS CARD's GameTora event list (not the whole 80<member>nnn
    band): that band is shared with the member's own ordinary support cards, so
    claiming all of it would drag in unrelated events."""
    from .. import event_engine
    members = group_members(card_id)
    if member not in members:
        return ()
    chain = []
    suffix = (group_kit(card_id).get("member_story") or {}).get(
        member, GROUP_CHAIN_BASE + members.index(member))
    head = story_id(card_id, suffix)
    if head:
        chain.append(head)
    kit = group_kit(card_id)
    if kit:
        # The kit's own continuation: the card's chara walks on into the
        # after-members stories (see GROUP_KITS).
        if member == kit.get("after_partner"):
            chain += [s for s in (story_id(card_id, x) for x in kit.get("after_members") or ()) if s]
        return tuple(chain)
    gt = event_engine.gametora.load_cached("support", card_id) or {}
    base = 800000000 + member * 1000
    extra = set()
    for ev in gt.values():
        title = ev.get("name")
        if not title:
            continue
        # Only events whose own bond effect names this member -- that's how the
        # data attributes a group card's events to one of its members.
        owners = {e.get("char_id") for c in ev.get("choices") or []
                  for e in c.get("effects") or [] if e.get("char_id")}
        if owners and member not in owners:
            continue
        sid = event_engine._story_id_by_title(title, base)
        if sid:
            extra.add(sid)
    return tuple(chain + sorted(extra))


def outing_story(card_id: int, partner_chara: int, step: int) -> int | None:
    """The story for going out with `partner_chara`. A pal card walks its own
    chain in order (step = how many outings with them already done); a group
    member walks THEIR chain (see member_chain)."""
    if _link_chain(card_id):
        chain = list(_link_chain(card_id))
    elif is_pal(card_id):
        chain = [story_base(card_id) + s for s in PAL_CHAIN
                 if s in _existing_suffixes(card_id)]
    else:
        chain = member_chain(card_id, partner_chara)
    return chain[step] if step < len(chain) else None


def outing_chain_len(card_id: int, partner_chara: int | None = None) -> int:
    """How many outings this partner has left in them. For a group card that's
    per-MEMBER; with no member given it's the whole card (every member's chain),
    which is what 'have I finished this card' means."""
    if _link_chain(card_id):
        return len(_link_chain(card_id))
    if is_pal(card_id):
        return len([s for s in PAL_CHAIN if s in _existing_suffixes(card_id)])
    if partner_chara is not None:
        return len(member_chain(card_id, partner_chara))
    return sum(len(member_chain(card_id, m)) for m in group_members(card_id))


def finale_story(card_id: int) -> int | None:
    """The event that only unlocks once the whole chain / every member is done."""
    if is_pal(card_id):
        return story_id(card_id, _pal_suffix(card_id, PAL_FINALE, LINK_FINALE))
    if "finale" in group_kit(card_id):
        return story_id(card_id, group_kit(card_id)["finale"]) if group_kit(card_id)["finale"] else None
    have = sorted(s for s in _existing_suffixes(card_id) if s in GROUP_FINALE)
    return story_base(card_id) + have[0] if have else None


def ending_story(card_id: int, complete: bool) -> int | None:
    """The career-end sendoff: old kit +9/+10, link kit +22/+23 (Tazuna's
    +122/+123), complete when every date was walked."""
    if not is_pal(card_id):
        return None
    if link_offset(card_id) is None:
        return story_id(card_id, PAL_ENDING_COMPLETE if complete else PAL_ENDING_INCOMPLETE)
    return story_id(card_id, link_offset(card_id) + (22 if complete else 23))


@functools.lru_cache(maxsize=64)
def new_year_story(card_id: int) -> int | None:
    """The card's special New Year's date event -- GameTora tags exactly one
    'special' event per pal/group card with type "ny" (confirmed on all 12:
    e.g. Tazuna's 'A Bond with Tazuna: Aspirations Entrusted', Light Hello's
    'Bonding with Light Hello: Letting Loose'). Live-reported 2026-09-03:
    doing recreation with an unlocked pal/group card right after the turn-25
    New Year beat should offer THIS, not the next step of the ordinary chain.

    For a PAL card this happens to sit at the same suffix (11) `finale_story`
    already returns -- capture shows that slot was never a distinct
    "chain complete" beat, it's this. For a GROUP card it is a DIFFERENT beat
    from `finale_story` (whose GROUP_FINALE range holds several: a per-pair
    beat first, then the whole-team one) -- e.g. Rudolf's finale is suffix 20
    ('I Wanna Be Just Like Prez!') while 'ny' is 32 ('Dreaming the Same
    Dream'), so it can't be found by suffix arithmetic and is instead resolved
    by title, same technique member_chain() already uses for GameTora ->
    master.mdb mapping."""
    if group_kit(card_id).get("new_year"):
        return story_id(card_id, group_kit(card_id)["new_year"])
    offset = link_offset(card_id)
    if offset is not None:
        # A link kit's New Year date is its +21 (Tazuna 809001121, Kiyoko
        # 809050021) -- no GameTora page needed for a JP-only card.
        return story_id(card_id, _pal_suffix(card_id, PAL_FINALE, LINK_FINALE))
    from .. import event_engine
    gt = event_engine.gametora.load_cached("support", card_id) or {}
    title = next((ev.get("name") for ev in gt.values()
                 if ev.get("event_type") == "ny"), None)
    if not title:
        return None
    return event_engine._story_id_by_title(title, story_base(card_id))


@functools.lru_cache(maxsize=64)
def unlock_chances(card_id: int) -> dict:
    """{select_index: probability} for this card's outing-unlock event.
    Capture-derived overrides first; otherwise derived from the GameTora event
    itself (random_either = the gamble choice; no gamble = choice 1 unlocks)."""
    if _link_chain(card_id):
        return {1: 1.0, 2: 1.0}   # capture: display_id 11 on both choices
    override = UNLOCK_CHANCE.get(story_owner(card_id))
    if override:
        return dict(override)
    sid = unlock_story(card_id)
    if sid:
        from .. import event_engine
        _title, ev = event_engine.event_by_story_id(card_id, sid)
        choices = (ev or {}).get("choices") or []
        gambles = [i + 1 for i, c in enumerate(choices) if c.get("random_either")]
        if gambles:
            return {i: _GAMBLE_CHANCE for i in gambles}
        if choices:
            return {1: 1.0}
    return dict(_DEFAULT_UNLOCK)


def unlock_chance(card_id: int, select_index: int) -> float:
    return unlock_chances(card_id).get(select_index, 0.0)


@functools.lru_cache(maxsize=512)
def reserved_story_ids(card_id: int) -> frozenset:
    """Stories that must NEVER come out of the generic random-event pull: every
    outing-chain event and the finale. They only fire through the outing system
    (live-reported: these were leaking into the ordinary support-event pull).

    Two deliberate exceptions:
      * a PAL card's UNLOCK event stays IN the pull -- that is exactly how you
        can (rarely) unlock outings with a pal who isn't even in your deck, and
        unlocking then opens their whole chain. A GROUP card's unlock is
        reserved: you can't unlock a group you aren't running.
      * first-meeting and repeatable training events are never reserved; those
        are supposed to fire from training."""
    if not is_pal_or_group(card_id):
        return frozenset()
    base = story_base(card_id)
    have = _existing_suffixes(card_id)
    if is_pal(card_id):
        # EVERYTHING, including the unlock. The 'lucky out-of-deck unlock' the
        # user originally asked for turned out to be the engine behind repeated
        # ghost unlocks (Tazuna/Kiryuin/Riko announced before the debut race,
        # Meek re-unlocking in senior year) and it even leaked Riko's FINAL
        # outing-chain story into the pull. Pal/group content is now reachable
        # ONLY through the in-deck outing system.
        reserved = {base + s for s in have}
        # A pal card ALSO has stories in its own CARD band (830021nnn next to
        # Tazuna's 809001nnn) -- reserve those too or they stay drawable.
        card_base = 800000000 + card_id * 1000
        reserved |= {r["index"] for r in master_data.query(
            "SELECT [index] FROM text_data WHERE category=181 "
            "AND [index] BETWEEN ? AND ?", (card_base, card_base + 999))}
    else:
        # GROUP cards: reserve their ENTIRE kit. Live-hit: Rudolf's repeatable
        # 'We'll Get Stronger, Together' came out of the pull for a deck that
        # didn't run the card ('Friendship cannot change for Support Cards not
        # in your deck' on every line) and granted Pure Passion off-deck.
        if group_kit(card_id).get("reserved"):
            return frozenset(base + x for x in group_kit(card_id)["reserved"] if x in have)
        reserved = {base + s for s in have}
        for m in group_members(card_id):
            reserved |= set(member_chain(card_id, m))
    return frozenset(reserved)


def is_unlock_story(card_id: int, sid: int) -> bool:
    """Whether this story is the card's outing-unlock event -- the pal-card one
    is reachable from the generic pull, so the firing path has to recognise it
    and attach the unlock roll."""
    return bool(sid) and sid == unlock_story(card_id)


def is_reserved(card_id: int, sid: int) -> bool:
    return sid in reserved_story_ids(card_id)
