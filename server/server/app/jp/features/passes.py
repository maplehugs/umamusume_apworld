"""The account's subscriptions and factor passes, as the JP client reads them.

Holdings live in app/paid_features.py (granted with admin.py
give-paid-feature). This stamps them onto every reply that carries the
fields: load/index, payment/item_list, payment/finish and the rest. schema.py
fills those fields with "nothing held" defaults, so without this hook the client
would always see an account with no passes. The career-side effects
(pick-two inspiration, pass/ticket re-rolls and spark orders) are in
handlers/single_mode_team.py, next to the rest of the spark flow.
"""

from __future__ import annotations

from ... import paid_features
from ... import state as state_store

HANDLERS: dict = {}

_FIELDS = ("factor_premium_pass_info", "factor_order_pass_info",
           "user_subscription_info_array", "subscription_is_valid")


def after(endpoint: str, payload: dict, resp: dict) -> None:
    data = resp.get("data")
    if not isinstance(data, dict) or not any(k in data for k in _FIELDS):
        return
    full_state = state_store.get_state(payload.get("viewer_id")) or {}
    paid_features.stamp(full_state, data)
