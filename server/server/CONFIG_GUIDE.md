# Config guide (`client_config.json`)

This is the Global server's `server/client_config.json`. JP has its own file,
documented in [CONFIG_GUIDE_JP.md](CONFIG_GUIDE_JP.md).

The file itself stays instruction-free (machine-edited); this guide documents
every key. Values hot-reload on file save (mtime-checked) — no server restart —
but only VALUES: code changes still need the reload/restart.

| key | type | default | meaning |
|---|---|---|---|
| `servertime` | `"now"` \| int (unix) \| null | frozen capture day | `"now"` serves the real current time on every response, as the real server does (the shipped config uses it). An int serves that fixed time instead; null = patch.py's `FROZEN_SERVERTIME`. Changing it moves the in-game "day" (new-day popup, dailies reset). |
| `resource_version` | string | `"10007100"` | Client resource version echoed in headers. Must match the client or it re-downloads/refuses. |
| `scenario_ids` | int[] | `[1, 3]` | Scenarios offered at career start. 1 = URA, 3 = Grand Live. Unlisted scenario ids refuse to start (deliberate; unimplemented ones would softlock). |
| `force_failure_rate` | int 0-100 \| null | null | Testing knob: every training shows/uses this failure %. |
| `force_training_gain` | int \| null | null | Testing knob: every training stat gain forced to this value. |
| `training_gain_multiplier` | number \| null | null | Testing knob: scales the real formula's stat and skill-point gains (energy cost unchanged), e.g. `2` doubles them. Ignored while `force_training_gain` is set. |
| `force_ssr_rate` | int 0-100 \| null | null | Testing knob: gacha SSR tier rate override (keeps within-tier weights). |
| `auth_enforce` | bool | false | When true, a request whose crypto-header sid doesn't match the account's issued sid is rejected. Leave false while only trusted people connect (current setting per owner). Plumbing lives in `app/accounts.py`. |
| `maintenance` | bool | false | When true, every endpoint (login included) answers result code 101 and the client shows its "Under Maintenance" dialog. |
| `feature_maintenance` | string[] | `[]` | Put single features under maintenance. Their endpoints answer the feature's own 9xx code and the client shows "Feature Maintenance". Names: `gacha`, `present`, `payment`, `shop`, `single_mode`, `circle`, `team_stadium`, `daily_race`, `legend_race`, `daily_legend_race`, `main_story`, `character_story`, `extra_story`, `story_event`, `mission`, `practice_race`, `jukebox`, `campaign_walking`, `card_talent_strengthen`, `card_rarity_upgrade`, `card_unlock`, `support_card_strengthen`, `support_card_limit_break`, `support_card_sell` (see `_FEATURE_MAINTENANCE` in `app/main.py`). |
| `banner_max_age_days` | int (days) \| null | null | Limits which banners `gacha/index` lists. Null = every banner. `30` = only banners still running at some point in the last 30 days of servertime (master `end_date` ≥ servertime − 30 days). Open-ended and upcoming banners, config-only banners from `gacha_banners.json`, and banners forced with `"on": true` in `gacha_odds.json` always stay listed. Only affects the list: a hidden banner can still be pulled by id. |
| `veteran_capacity` | int | 260 | Max finished-career (legacy) umas per account. Overflow drops the oldest UNLOCKED veteran at career finish, never the new record; locked veterans are never dropped. |

## Related, but not in this file

- `server/data/gacha_banners.json` (optional; see `gacha_banners.json.example`)
  — per-banner pools/pickup/price overrides (swap the card list itself).
- `server/data/gacha_odds.json` (optional; see `gacha_odds.json.example`)
  — the layered custom-odds system: banner visibility, tier rates, per-card
  weights. Layers ON TOP of gacha_banners.json. Full format below.
- `admin.py` — live account/career edits: stats, items, currencies, plus
  `career-park <slot>` / `career-resume <slot>` / `career-slots` (career save
  slots) and `send-mail <category> <item> <num>` (admin → present box).
- Constants still hardcoded in `app/handlers/single_mode_team.py` (event
  chances, reward tables) migrate here as their systems are refactored; each
  migration adds its row to this table.

## Gacha odds (`data/gacha_odds.json`)

Optional, hot-reloaded on save (mtime check, same pattern as
`client_config.json`) — edits apply on the next request, no server restart.
Absent file = layer off, nothing changes. A malformed file is ignored (real
rates apply) rather than breaking pulls. Starter: `data/gacha_odds.json.example`.

The file is one JSON object mapping **banner selectors** to **sections**.
Keys starting with `_` are ignored — use them for comments.

### Banner selectors

| selector | matches |
|---|---|
| `"30111"` | exactly that gacha_id |
| `"301*"` | every gacha_id starting `301` (prefix) |
| `"*"` | every banner |

### Precedence (per banner)

```
master.mdb defaults
  -> gacha_banners.json pool override (if any)
    -> "*" section
      -> matching prefix sections, in FILE order
        -> exact-id section
```

Later layers win: `on` is overwritten, `rarity_rates` merges per tier,
`custom_odds` lists are concatenated (so a later section's entries rewrite an
earlier section's weights card-by-card). Within one `custom_odds` list the
**last** entry to match a card decides its weight.

### Section keys (all optional)

**`on`** (bool) — `true` forces the banner into `gacha/index`; `false` hides
it and makes `gacha/exec` refuse (205). Default while the file exists:
master `start_date`/`end_date` vs the frozen servertime (~18 banners are in
window on the capture day), so start your file with `"*": {"on": true}` to
keep everything listed. With **no** file at all, the long-standing behaviour
(every pooled banner listed) is untouched.

**`rarity_rates`** (`{"1": pct, "2": pct, "3": pct}`) — tier-first drawing:
first pick R/SR/SSR by these percentages, then a weighted card draw inside
the tier. Replaces the flat master 79/18/3. Unspecified tiers keep their
default share; values are normalized over the tiers actually present, so
they need not sum to 100. The ten-pull's guaranteed SR+ slot re-normalizes
over SR/SSR only. The `force_ssr_rate` testing knob in `client_config.json`
still **wins** over this while set (backward compat) — null it out for
`rarity_rates` to apply.

**`custom_odds`** (ordered list of `{"items": SELECTOR, "weight": VALUE}`) —
per-card weight rewrites inside the pool.

Item `SELECTOR`:

| selector | matches |
|---|---|
| `"30052"` | exactly that card id |
| `"1*"` / `"2*"` / `"3*"` | every card of that **rarity** (R / SR / SSR) |
| `"3011*"` | card-id prefix (2+ chars before the `*`) |
| `"*"` | every card in the pool |
| `["30052", "2*"]` | a list = any-of |

Weight `VALUE`:

| value | meaning |
|---|---|
| `99` (number) | absolute weight, relative to the other cards' weights (master values are per-card odds out of 1,000,000 — mixing tiny numbers with untouched master weights only works as expected inside `rarity_rates` tiers, or set every card) |
| `"weightR"` / `"weightSR"` / `"weightSSR"` | this pool's **average master weight** for that band — e.g. give one SSR the weight a normal R has |
| `"x2"`, `"x0.5"`, … | multiplier on the card's own **master** weight (not the layered value, so entry order can't compound multipliers) |
| `0` | the card never drops (a genuine zero, not "average") |

### Worked example

```json
{
  "_comment": "pickup banner: everything visible, 30111 rate-up",
  "*": { "on": true },
  "30*": { "rarity_rates": { "3": 10 } },
  "30111": {
    "rarity_rates": { "1": 76, "2": 18, "3": 6 },
    "custom_odds": [
      { "items": "1*",    "weight": "weightR" },
      { "items": "3*",    "weight": 1 },
      { "items": "30052", "weight": 99 },
      { "items": "20048", "weight": "x2" }
    ]
  }
}
```

Every banner stays listed; all `30…` banners run a 10% SSR tier; banner
30111 specifically runs 76/18/6, and inside its SSR tier card 30052 takes
`99/(99+nSSR-1)` of the SSR pulls (~97% on the real pool) because the later
`"30052"` entry overrides the earlier `"3*"` blanket. Pity counters,
exchange points and the ten-pull SR+ guarantee are unaffected by all of
this; `gacha_banners.json` pool swaps still apply first, then these weights
rewrite them.
