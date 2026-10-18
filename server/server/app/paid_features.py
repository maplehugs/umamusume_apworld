"""Paid entitlements an account holds: the JP client's subscriptions and passes.

Nothing is sold on this server. The admin CLI grants them (admin.py
give-paid-feature) and this module is the one place their state lives, so the
handlers that gate on one (pick-two inspiration, free spark re-rolls, free
spark orders) and the replies that report them (load/index, payment/*) agree.

Stored on full_state[STATE_KEY] as {feature: end_unix_time}. Global's client
has none of these screens and no account there is ever granted one, so every
check below is False on Global.

The features, as JP's master.mdb names them (text_data 42/377/378):
  umasuku      ウマスク subscription (wire subscription_type 0, subs001)
  umaplan      ウマプラン subscription (type 1, subs004) -- 継承因子選択: the
               mid-career inspiration offers two rolls and the player keeps one
  reroll_pass  因子再獲得パス (factor_premium_pass) -- spark re-rolls without
               carats (SingleModeDefine.FactorLotteryType.PremiumPass = 4)
  order_pass   因子指定パス (factor_order_pass) -- spark orders without carats
               (SingleModeFactorOrderInfoModel.RequestTypeEnum.Pass = 2)
"""

from __future__ import annotations

import time

STATE_KEY = "paid_features"
FEATURES = ("umasuku", "umaplan", "reroll_pass", "order_pass")

# The ticket each pass stands in for (text_data 23): usable only WITHOUT the pass.
REROLL_TICKET_ITEM = 260    # 因子再獲得チケット
ORDER_TICKET_ITEM = 262     # 因子指定チケット

_SUBSCRIPTIONS = (("umasuku", 0, "jp.co.cygames.umamusume.subs001"),
                  ("umaplan", 1, "jp.co.cygames.umamusume.subs004"))


def end_time(full_state: dict, feature: str) -> int:
    held = (full_state or {}).get(STATE_KEY)
    return int((held or {}).get(feature) or 0) if isinstance(held, dict) else 0


def active(full_state: dict, feature: str) -> bool:
    return end_time(full_state, feature) > time.time()


def grant(full_state: dict, feature: str, days: int) -> int:
    """Extend (or start) a feature by `days`; returns the new end time."""
    if feature not in FEATURES:
        raise ValueError(f"unknown paid feature {feature!r} (one of {', '.join(FEATURES)})")
    held = full_state.setdefault(STATE_KEY, {})
    base = max(int(time.time()), end_time(full_state, feature))
    held[feature] = base + int(days) * 86400
    return held[feature]


def revoke(full_state: dict, feature: str) -> None:
    (full_state.get(STATE_KEY) or {}).pop(feature, None)


# ---- items (the tickets) ---------------------------------------------------
def item_count(full_state: dict, item_id: int) -> int:
    for it in full_state.get("item_list_state") or ():
        if it.get("item_id") == item_id:
            return int(it.get("number") or 0)
    return 0


def spend_item(full_state: dict, item_id: int, num: int = 1) -> bool:
    for it in full_state.get("item_list_state") or ():
        if it.get("item_id") == item_id and int(it.get("number") or 0) >= num:
            it["number"] = int(it["number"]) - num
            return True
    return False


def spend_coin(full_state: dict, cost: int) -> bool:
    """Carats, free ones first -- the same order the rest of the server uses."""
    wallet = full_state.setdefault("coin_info_state", {"fcoin": 0, "coin": 0})
    fcoin, coin = int(wallet.get("fcoin") or 0), int(wallet.get("coin") or 0)
    if fcoin + coin < cost:
        return False
    free = min(fcoin, cost)
    wallet["fcoin"], wallet["coin"] = fcoin - free, coin - (cost - free)
    return True


# ---- what the client is told -----------------------------------------------
def _pass_info(full_state: dict, feature: str) -> dict:
    """FactorPremiumPassInfo / FactorOrderPassInfo. The client's
    PassInfoBase.IsPurchased reads pass_end_time against server time."""
    return {"pass_end_time": end_time(full_state, feature), "repurchase_time": 0,
            "notice_status": 0}


def _purchase_info(full_state: dict, feature: str) -> list:
    """FactorPassPurchaseInfo[]; product_type 1 = Individual (2 = the Set)."""
    end = end_time(full_state, feature)
    if end <= time.time():
        return []
    return [{"product_type": 1, "purchase_time": int(time.time()),
             "pass_start_time": int(time.time()), "pass_end_time": end}]


def _subscription(full_state: dict, feature: str, sub_type: int, product: str) -> dict:
    valid = active(full_state, feature)
    return {"product_id": product if valid else "", "subscription_type": sub_type,
            "is_valid": valid, "order_id": "", "subscription_end_date":
            end_time(full_state, feature) if valid else 0,
            "is_in_grace_period": False, "is_in_account_hold": False}


def stamp(full_state: dict, data: dict) -> None:
    """Overwrite every entitlement field `data` carries with this account's
    real holdings. Only fields already present are touched, so it is safe on
    any reply (load/index, payment/item_list, payment/finish, ...)."""
    if not isinstance(data, dict):
        return
    if "factor_premium_pass_info" in data:
        data["factor_premium_pass_info"] = _pass_info(full_state, "reroll_pass")
    if "factor_order_pass_info" in data:
        data["factor_order_pass_info"] = _pass_info(full_state, "order_pass")
    if "factor_premium_pass_purchase_info_array" in data:
        data["factor_premium_pass_purchase_info_array"] = _purchase_info(full_state, "reroll_pass")
    if "factor_order_pass_purchase_info_array" in data:
        data["factor_order_pass_purchase_info_array"] = _purchase_info(full_state, "order_pass")
    subs = [_subscription(full_state, f, t, p) for f, t, p in _SUBSCRIPTIONS]
    if "user_subscription_info_array" in data:
        data["user_subscription_info_array"] = subs
    if "user_subscription_info" in data:
        data["user_subscription_info"] = subs[0]
    if "subscription_is_valid" in data:
        data["subscription_is_valid"] = active(full_state, "umaplan")
