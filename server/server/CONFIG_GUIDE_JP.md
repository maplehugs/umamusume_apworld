# JP config guide (`data/jp/client_config.json`)

The JP server (`./start-server.sh --region jp`) reads only
`server/data/jp/client_config.json`. It never reads Global's
`server/client_config.json`, and Global never reads this file. The Global
file is documented in [CONFIG_GUIDE.md](CONFIG_GUIDE.md).

Values reload when you save the file (the server checks its mtime), so you
don't need to restart the server. Code changes still need a restart. Keys that
start with `_` are comments and are ignored. A missing or malformed file falls
back to the defaults below.

JP runs Global's handlers on its own data, so a key means the same thing in
both regions. This guide lists only the keys that matter for JP. Champions
Meetings are out of scope for JP for now.

## Keys

| key | type | default | meaning |
|---|---|---|---|
| `servertime` | int (unix) \| `"now"` \| null | frozen capture day | Server time. `"now"` uses the real clock (the JP file ships with this). A fixed int moves the in-game day (new-day popup, daily resets). |
| `resource_version` | string | `""` | Resource version echoed to the client, in JP's `version:hash` form (for example `"10020950:TQiUvY4C9J4N"`). It must match the installed JP client, or the client re-downloads or refuses to start. |
| `app_version` | string | `"1.35.1"` | App version reported in room-match race data. Set it to the JP client's version. |
| `auth_enforce` | bool | false | When true, a request whose crypto-header sid doesn't match the account's issued sid is rejected. |
| `maintenance` | bool | false | When true, every endpoint answers result code 101 and the client shows "Under Maintenance". |
| `feature_maintenance` | string[] | `[]` | Puts single features under maintenance. The names are the same as Global's (see CONFIG_GUIDE.md), for example `gacha`, `shop`, `present`. |
| `payment_mode` | `"instant"` \| `"receipt"` \| `"off"` | `"instant"` | Carat store. `instant` credits on payment/start, `receipt` credits on payment/finish, `off` shows the catalog only. |
| `banner_max_age_days` | int (days) \| null | null | Limits which banners `gacha/index` lists. Null = every banner. `30` = only banners still running at some point in the last 30 days of servertime (master `end_date` ≥ servertime − 30 days). Open-ended and upcoming banners, config-only banners, and banners forced with `"on": true` in `gacha_odds.json` always stay listed. Only affects the list: a hidden banner can still be pulled by id. |
| `force_ssr_rate` | int 0-100 \| null | null | Testing knob: overrides the gacha SSR tier rate. |
| `force_failure_rate` | int 0-100 \| null | null | Testing knob: every training shows and rolls this failure %. |
| `force_training_gain` | int \| null | null | Testing knob: every stat and skill points on every training pinned to this value. |
| `training_gain_multiplier` | number \| null | null | Testing knob: scales the real formula's stat and skill-point gains (energy cost unchanged), e.g. `2` doubles them. Stat caps still apply. Ignored while `force_training_gain` is set. |
| `tp_recovery_seconds` / `rp_recovery_seconds` | int | 600 / 7200 | Seconds to regenerate one TP / RP. |
| `team_trials_rp_cost` | int | 1 | RP cost of one Team Trials run. |
| `tp_refill_carat_cost` / `rp_refill_carat_cost` | int | see `app/handlers/stamina.py` | Carat price of a paid refill. |
| `tp_refill_amount` / `rp_refill_amount` | int | see `app/handlers/stamina.py` | Amount a paid refill restores. 0 fills the pool. |
| `legend_race_id` | int \| null | null | Forces this `legend_race` row open for testing. Null uses the real master schedule. |
| `serial_codes` | object | `{}` | Serial codes the gift-code screen accepts (see `app/handlers/galleries.py`). |

## Gacha files are shared with Global

`gacha_banners.json` and `gacha_odds.json` are read from `server/data/`, not
`server/data/jp/`, so both regions use the same files. Their format is in
CONFIG_GUIDE.md. Banner ids differ between the two master.mdb files, so an
exact-id section written for Global has no effect on JP. A `"*"` section
applies to both regions.
