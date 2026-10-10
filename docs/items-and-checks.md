# Items and checks

Generated from `umamusume/tables.py`.

## Progression and buffs

| Item | Copies | Effect |
|---|---|---|
| Scenario: Unity Cup / Grand Live / Trackblazer | 1 each | Unlocks that scenario on the career screen (URA is always open). |
| Progressive Speed/Stamina/Power/Guts/Wit Training | 3 each | +20% that stat's training gain and +50 to its cap, per copy. |
| Progressive Starting Stats | 5 | +20 to every stat at career start. |
| Progressive Starting Skill Points | 3 | +200 skill points at career start. |
| Progressive Stat Cap | 0 or 2 | +50 to every stat cap (only when goal_rank_score is 21000+). |
| Progressive Training Guard | 2 | Training failure rate x0.75 per copy. |
| Progressive RP Recovery | up to 3 (with team_trials_checks) | Team Trials RP refills twice as fast per copy. |
| Dream's Luck | 1 | Every support card shows up in its own facility every turn. |
| Trainee: ... | trainee_count | The trainee, by mail. |
| Support: ... | support_count | The SSR support card, by mail (a repeat is an uncap copy). |

## Filler

| Item | Effect |
|---|---|
| Minor Starting Stats | +5 to every stat at career start, permanent (stacks). |
| Minor Starting Skill Points | +50 skill points at career start, permanent (stacks). |
| RP Refill | Team Trials RP to full, once (only with team_trials_checks). |
| Pep Talk | Next career starts in Great mood. |
| Lucky Charm | Next career starts Charming or with Practice Perfect. |

Support cards from the multiworld arrive **maxed** (limit break 4, top level) when
you claim them from the present box.

## Traps (next career, at most `trap_cap` per career)

| Trap | Effect |
|---|---|
| Bad Condition Trap | Starts with a bad condition (Night Owl, Slacker, Skin Outbreak, Migraine or Practice Poor). |
| Bad Mood Trap | Starts in Awful mood. |
| Low Energy Trap | Starts with 40 less energy. |
| Tunnel Vision Trap | One random stat's Training items do nothing this career. |
| Butterfingers Trap | Failure rate x1.5 in the Junior year. |
| Amnesia Trap | No starting stats or skill point buffs this career (spicy_traps). |

## Checks

### G1 wins (g1_checks)

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

- Win 10 different races
- Win 20 different races
- Win 35 different races
- Win 50 different races
- Win 75 different races

### Team Trials (team_trials_checks)

- Team Trials: win 1 match ... win 10 matches (the first `team_trials_checks` of them)

### Trainees

Always: your 5 starting trainees (random per seed with `starting_trainees: random`; with `fixed`, these):

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
