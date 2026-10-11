# Items and checks

Generated from `umamusume/tables.py`.

## Loot table at a glance

A seed has one item per check: every check you can send holds something for
someone in the multiworld, and as many items come back to you. With the example
YAML's defaults that is **170 checks out, 170 items in**:

| Checks you send | Count |
|---|---|
| Team Trials races won | 50 |
| G1 wins | 34 |
| Scenario ranks B/A/S/SS/UG (4 scenarios) | 20 |
| Finish a career with a trainee (5 starting + 15) | 20 |
| Different races won, every 5 | 15 |
| Fans, every 250k | 12 |
| Legend Race ladder C..SS+ | 10 |
| Global rank B+..UG1 (up to the goal) | 5 |
| Finish a scenario (final won) | 4 |

| Items you get, most first | Count | What it does |
|---|---|---|
| Support: SSR cards | 54 (even by stat) | Mailed, maxed on claim. Your career deck. |
| Trainee Awakening | 20 (one per trainee) | A trainee to 5 stars, potential 5. |
| Trainee: ... | 15 | New trainees, each with its own "finish a career" check. |
| Progressive Training | 15 (3 per stat) | +20% gain, +50 cap on that stat each. |
| Minor Starting Stats | ~10 | +5 every stat at career start, forever. |
| Pep Talk / Lucky Charm | ~9 / ~5 | Next career starts in Great mood / Charming or Practice Perfect. |
| RP Refill | ~6 | Team Trials RP to full. |
| Progressive Starting Stats | 5 | +20 every stat at career start. |
| Minor Starting Skill Points | ~4 | +50 SP at career start, forever. |
| Scenarios | 3 | Every scenario but your starting one. |
| Progressive Starting Skill Points | 3 | +200 SP at career start. |
| Progressive RP Recovery | 3 | Team Trials RP refills twice as fast each. |
| Progressive Training Guard | 2 | Failure rate x0.75 each. |
| Traps | ~16 (trap_percentage 20) | A bad start for one career, at most `trap_cap` per career. |

How the pool is built, most wanted first: scenarios, trainees, `support_count`
cards, Progressive Training, Starting Stats, awakenings, RP Recovery, Starting
Skill Points, Training Guard. Whatever doesn't fit in your checks is **start
inventory** instead (you get it when you connect), so any set of checks
generates: fewer checks is a shorter game that starts stronger. Spare checks
after that deal 1 more SSR card per 3 (still even by stat), the rest is filler,
`trap_percentage` of it traps. "~" counts are rolled by the weights below.

### Turning checks on and off

Simulated seeds, everything else default:

| Checks on | Checks | Cards | Filler (traps) | From the start |
|---|---|---|---|---|
| Nothing (only scenario finishes and trainees) | 24 | 30 (24 from the start) | 0 | 69: 24 cards, 20 awakenings, all Progressive buffs |
| Only G1 | 58 | 30 | 0 | 35: 20 awakenings, 5 Progressive Training, the Starting buffs |
| Everything but Team Trials | 120 | 39 | 18 (6) | nothing |
| **Default** | **170** | **54** | **50 (16)** | nothing |
| Everything, `g1_per_scenario`, Team Trials 100 | 358 | 117 | 175 (47) | nothing |

| Group | Checks | Option |
|---|---|---|
| Team Trials races won | 0-100 (50) | `team_trials_checks` |
| G1 wins | 34, +136 per scenario | `g1_checks`, `g1_per_scenario` |
| Scenario ranks | 20 | `scenario_rank_checks` |
| Different races | 15 | `unique_race_checks` |
| Fans | 12 | `fan_checks` |
| Legend Race | 10 | `legend_ladder` |
| Global ranks | 5 (7 past a 20800 goal) | `global_rank_ladder` |
| Finish a scenario | 4 | always |
| Finish a career with a trainee | starting + `trainee_count` | always |

Past 100 cards the stats can't stay even (the game has 20 Wit SSRs, 28 Speed).
Rather keep a group's checks but nothing important in them? `exclude_locations`,
see [options](options.md#excluding-checks).

## Progression and buffs

| Item | Copies | Effect |
|---|---|---|
| Scenario: URA Finale / Unity Cup / Grand Live / Trackblazer | 1 each, except your starting scenario | Unlocks that scenario on the career screen. |
| Progressive Speed/Stamina/Power/Guts/Wit Training | 3 each | +20% that stat's training gain and +50 to its cap, per copy. |
| Progressive Starting Stats | 5 | +20 to every stat at career start. |
| Progressive Starting Skill Points | 3 | +200 skill points at career start. |
| Progressive Stat Cap | 0 or 2 | +50 to every stat cap (only when goal_rank_score is 21000+). |
| Progressive Training Guard | 2 | Training failure rate x0.75 per copy. |
| Progressive RP Recovery | up to 3 (with team_trials_checks) | Team Trials RP refills twice as fast per copy (the 5-RP bar: 30 min, then 15, 7.5, ~4). |
| Trainee: ... | trainee_count | The trainee, by mail. |
| Support: ... | support_count | The SSR support card, by mail, maxed when claimed. Dealt evenly by stat (30 = 6 each of Speed, Stamina, Power, Guts, Wit; Friend/Group cards only past 100). Progression: up to 6 count toward the logic estimate. |
| Trainee Awakening | trainee_awakenings (one per trainee) | A random trainee you own, not yet maxed, goes to 5 stars and potential level 5 (log in again to see it). With all of them maxed it waits for the next trainee you claim. |

## Filler

Rolled by weight for every leftover slot.

| Item | Weight | Effect |
|---|---|---|
| Minor Starting Stats | 30 | +5 to every stat at career start, permanent (stacks). |
| Pep Talk | 15 | Next career starts in Great mood. |
| Lucky Charm | 15 | Next career starts Charming or with Practice Perfect. |
| RP Refill | 15 | Team Trials RP to full, once (only with team_trials_checks). |
| Minor Starting Skill Points | 10 | +50 skill points at career start, permanent (stacks). |

Support cards from the multiworld arrive **maxed** (limit break 4, top level) when
you claim them from the present box.

## Traps (next career, at most `trap_cap` per career)

Default weights (`trap_weights` changes them).

| Trap | Weight | Effect |
|---|---|---|
| Bad Condition Trap | 15 | Starts with a bad condition (Night Owl, Slacker, Skin Outbreak, Migraine or Practice Poor). |
| Bad Mood Trap | 15 | Starts in Awful mood. |
| Low Energy Trap | 10 | Starts with 40 less energy. |
| Tunnel Vision Trap | 15 | One random stat loses its Progressive Training bonus (gain and cap) this career. The training itself still works. |
| Butterfingers Trap | 15 | Failure rate x1.5 in the Junior year. |
| Amnesia Trap | 0 | No starting stats or skill point buffs this career (spicy_traps, or a trap_weights entry). |

## Checks

### G1 wins (g1_checks)

With `g1_per_scenario` there is also "Win <G1> in <scenario>" for each G1 below in
each of the 4 scenarios (136 more).

- Win February Stakes
- Win Takamatsunomiya Kinen
- Win Osaka Hai
- Win Oka Sho
- Win Satsuki Sho
- Win Tenno Sho (Spring)
- Win NHK Mile Cup
- Win Victoria Mile
- Win Japanese Oaks
- Win Tokyo Yushun (Japanese Derby)
- Win Yasuda Kinen
- Win Takarazuka Kinen
- Win Sprinters Stakes
- Win Shuka Sho
- Win Kikuka Sho
- Win Tenno Sho (Autumn)
- Win Queen Elizabeth II Cup
- Win Mile Championship
- Win Japan Cup
- Win Champions Cup
- Win Hanshin Juvenile Fillies
- Win Asahi Hai Futurity Stakes
- Win Arima Kinen
- Win Hopeful Stakes
- Win Teio Sho
- Win Japan Dirt Derby
- Win JBC Ladies' Classic
- Win JBC Sprint
- Win JBC Classic
- Win Tokyo Daishoten
- Win Kawasaki Kinen
- Win Zen-Nippon Junior Yushun
- Win Kashiwa Kinen
- Win Mile Championship Nambu Hai

### Scenarios

"Finish a <scenario> career" needs the scenario's final won: 1st place in the
turn-78 race (URA's Finals; in Trackblazer the last Climax leg). "Finish a career
with <trainee>" only needs the career to reach its last turn, final won or not.
A goal missed mid-career ends the career early and counts for neither.

- Finish a URA Finale career
- Finish a Unity Cup career
- Finish a Grand Live career
- Finish a Trackblazer career
- `<Scenario>: rank B / A / S / SS / UG` (scenario_rank_checks)

### Global rank ladder (global_rank_ladder)

- Reach rank B+ (8200)
- Reach rank A+ (12100)
- Reach rank S+ (15900)
- Reach rank SS+ (19200)
- Reach rank UG1 (20000)
- Reach rank UG2 (20400)
- Reach rank UG3 (20800)

### Different races (unique_race_checks)

- Win 5, 10, 15 ... 75 different races (every 5)

### Legend Race ladder (legend_ladder)

On the Archipelago save, Legend Race always shows your current rival; beating it
opens the next. Entries there cost no ticket.

- Legend Race: beat the C rival (1200 m)
- Legend Race: beat the C+ rival (1600 m)
- Legend Race: beat the B rival (1600 m)
- Legend Race: beat the B+ rival (2000 m)
- Legend Race: beat the A rival (2000 m)
- Legend Race: beat the A+ rival (2200 m)
- Legend Race: beat the S rival (2200 m)
- Legend Race: beat the S+ rival (2500 m)
- Legend Race: beat the SS rival (2400 m)
- Legend Race: beat the SS+ rival (3000 m)

### Fans (fan_checks)

- Reach 250,000, 500,000, 750,000 ... 3,000,000 fans, every 250k (summed over every finished career)

### Team Trials (team_trials_checks)

- Team Trials: win 1 race ... win 50 races (the first `team_trials_checks` of them; every race won of a match's 5 counts, lost match or not)
- Multiworld items like any other check. With `team_trials_roulette`, a roulette of your own good filler and traps instead, `team_trials_trap_percentage` of them traps (25: 38 good, 12 traps of 50), never progression.

### Trainees

Always: your 5 starting trainees (random per seed with `starting_trainees: shuffled`; with `default`, these):

- Finish a career with [Red Strife] Gold Ship
- Finish a career with [Wild Top Gear] Vodka
- Finish a career with [Peak Blue] Daiwa Scarlet
- Finish a career with [Blossom in Learning] Sakura Bakushin O
- Finish a career with [Bestest Prize ♪] Haru Urara

Shuffled (`trainee_count` of these):

- Finish a career with [Special Dreamer] Special Week
- Finish a career with [Hopp'n♪Happy Heart] Special Week
- Finish a career with [Ruler of Japan] Special Week
- Finish a career with [Innocent Silence] Silence Suzuka
- Finish a career with [Peak Joy] Tokai Teio
- Finish a career with [Beyond the Horizon] Tokai Teio
- Finish a career with [Formula R] Maruzensky
- Finish a career with [Hot☆Summer Night] Maruzensky
- Finish a career with [Shooting Star Revue] Fuji Kiseki
- Finish a career with [Succès Étoilé] Fuji Kiseki
- Finish a career with [Starlight Beat] Oguri Cap
- Finish a career with [Ashen Miracle] Oguri Cap
- Finish a career with [RUN! RUIN! LAUNCHER!] Gold Ship
- Finish a career with [Fiery Aqua Vitae] Vodka
- Finish a career with [Nuit Étoilée de Scarlet] Daiwa Scarlet
- Finish a career with [Wild Frontier] Taiki Shuttle
- Finish a career with [Bubblegum☆Memories] Taiki Shuttle
- Finish a career with [Stone-Piercing Blue] Grass Wonder
- Finish a career with [Saintly Jade Cleric] Grass Wonder
- Finish a career with [Azure Amazon] Hishi Amazon
- Finish a career with [Frontline Elegance] Mejiro McQueen
- Finish a career with [End of the Skies] Mejiro McQueen
- Finish a career with [Fair Lady of the Waves] Mejiro McQueen
- Finish a career with [El☆Número 1] El Condor Pasa
- Finish a career with [Kukulkan Warrior] El Condor Pasa
- Finish a career with [O Sole Suo!] T.M. Opera O
- Finish a career with [New Year, Same Radiance!] T.M. Opera O
- Finish a career with [Maverick] Narita Brian
- Finish a career with [Emperor's Path] Symboli Rudolf
- Finish a career with [Archer by Moonlight] Symboli Rudolf
- Finish a career with [Empress Road] Air Groove
- Finish a career with [Quercus Civilis] Air Groove
- Finish a career with [Full-Color Fangirling] Agnes Digital
- Finish a career with [Fanatic♡Jiangshi] Agnes Digital
- Finish a career with [Reeling in the Big One] Seiun Sky
- Finish a career with [Soirée des Chatons] Seiun Sky
- Finish a career with [Fast as Lightning] Tamamo Cross
- Finish a career with [Raging Thunder] Tamamo Cross
- Finish a career with [Noble Seamair] Fine Motion
- Finish a career with [Titania] Fine Motion
- Finish a career with [pf. Winning Equation...] Biwa Hayahide
- Finish a career with [Rouge Caroler] Biwa Hayahide
- Finish a career with [Scramble☆Zone] Mayano Top Gun
- Finish a career with [Sunlight Bouquet] Mayano Top Gun
- Finish a career with [Creeping Shadow] Manhattan Cafe
- Finish a career with [MB-19890425] Mihono Bourbon
- Finish a career with [CODE: ICING] Mihono Bourbon
- Finish a career with [Down the Line] Mejiro Ryan
- Finish a career with [Buono ☆ Alla Moda] Hishi Akebono
- Finish a career with [Darl'n Snowflake] Yukino Bijin
- Finish a career with [Rosy Dreams] Rice Shower
- Finish a career with [Vampire Makeover!] Rice Shower
- Finish a career with [Always Electrifying] Ines Fujin
- Finish a career with [tach-nology] Agnes Tachyon
- Finish a career with [Starry Nocturne] Admire Vega
- Finish a career with [Edomurasaki] Inari One
- Finish a career with [Golden Dream] Inari One
- Finish a career with [Get to Winning!] Winning Ticket
- Finish a career with [Dream Deliverer] Winning Ticket
- Finish a career with [unsigned] Air Shakur
- Finish a career with [Meisterschaft] Eishin Flash
- Finish a career with [Precise Chocolatier] Eishin Flash
- Finish a career with [Fille Éclair] Curren Chan
- Finish a career with [Ma Chérie of the New Moon] Curren Chan
- Finish a career with [Princess of Pink] Kawakami Princess
- Finish a career with [Authentic / 1928] Gold City
- Finish a career with [Autumn Cosmos] Gold City
- Finish a career with [Rocket☆Star] Seeking the Pearl
- Finish a career with [Platanus Witch] Sweep Tosho
- Finish a career with [Murmuring Stream] Super Creek
- Finish a career with [Chiffon-Wrapped Mummy] Super Creek
- Finish a career with [LOVE☆4EVER] Smart Falcon
- Finish a career with [Twilight Triumph] Smart Falcon
- Finish a career with [Heroic Author] Zenno Rob Roy
- Finish a career with [Jokester ☆ Vibes] Tosen Jordan
- Finish a career with [Desperate Measures] Nakayama Festa
- Finish a career with [Nevertheless] Narita Taishin
- Finish a career with [Difference Engineer] Narita Taishin
- Finish a career with [Layered Petals] Nishino Flower
- Finish a career with [New Year ♪ New Urara!] Haru Urara
- Finish a career with [Iron Ambition] Bamboo Memory
- Finish a career with [Rising☆Fortune] Matikanefukukitaru
- Finish a career with [Lucky Tidings] Matikanefukukitaru
- Finish a career with [Turbulent Blue] Meisho Doto
- Finish a career with [Dot-o'-Lantern] Meisho Doto
- Finish a career with [Off the Line] Mejiro Dober
- Finish a career with [Sapphire Sojourn] Mejiro Dober
- Finish a career with [Poinsettia Ribbon] Nice Nature
- Finish a career with [Run & Win] Nice Nature
- Finish a career with [King of Emeralds] King Halo
- Finish a career with [Cheerleader in Noble White] King Halo
- Finish a career with [Clippety-Tippety-Clop] Matikanetannhauser
- Finish a career with [Line Breakthrough] Mejiro Palmer
- Finish a career with [Natural Brilliance] Satono Diamond
- Finish a career with [Gilded Shrine to Glory] Kitasan Black
- Finish a career with [Strength in Full Bloom] Sakura Chiyono O
- Finish a career with [Crystalline] Mejiro Ardan
- Finish a career with [Blazed Head, Covered Fists] Yaeno Muteki
- Finish a career with [Brunissage Line] Mejiro Bright
- Finish a career with [Fluttertail Spirit] Yamanin Zephyr
- Finish a career with [Flare] Aston Machan
- Finish a career with [Eightfold☆Fortune] Copano Rickey
- Finish a career with [Butterfly Sting] Wonder Acute
