"""Features only the JP client has (Global's build does not ship them yet), or
JP's form of a Global feature: each module exposes HANDLERS {endpoint:
(payload) -> response}, collected here and added to the shared pipeline by
app/jp/server.py. When Global gains one of these, its handler moves to
app/handlers/ and serves both regions."""

from __future__ import annotations

from . import (account, archive, auto_play, const_walking, exhibition, jobs, misc, modes,
               passes, plushie, profile_slots, roadmap, skill_filter, skill_set, skill_upgrade, schedule_book, stepup,
               succession, support_cards, trainer_skill)

HANDLERS: dict = {}
for _module in (account, archive, auto_play, const_walking, exhibition, jobs, misc, modes,
                passes, plushie, profile_slots, roadmap, skill_filter, skill_set, skill_upgrade, schedule_book, stepup,
                succession, support_cards, trainer_skill):
    for _ep, _fn in _module.HANDLERS.items():
        assert _ep not in HANDLERS, f"two JP feature handlers for {_ep}"
        HANDLERS[_ep] = _fn
