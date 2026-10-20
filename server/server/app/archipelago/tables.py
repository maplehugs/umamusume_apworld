"""Archipelago tables, a copy of the apworld's (maplehugs/umamusume_apworld,
umamusume/tables.py).

The apworld's copy is the source of truth for every id: keep this one
identical (only this docstring differs).
Pure data, no imports. Generated from master.mdb (global); ids must never be
renumbered once a seed exists.
"""

GAME = "Umamusume Pretty Derby"

# The apworld release these tables ship with (the server's Archipelago mod and the
# world are released together: a newer apworld needs the matching server).
APWORLD_VERSION = "0.16.0"
APWORLD_REPO = "maplehugs/umamusume_apworld"

SCENARIOS = {1: "URA Finale", 2: "Unity Cup", 3: "Grand Live", 4: "Trackblazer"}

# Trainees a fresh account already owns (data/seeds/load_index_fresh.json).
STARTING_TRAINEES = (100701, 100801, 100901, 104101, 105201)

TRAINEES = {
    100101: '[Special Dreamer] Special Week',
    100102: "[Hopp'n♪Happy Heart] Special Week",
    100103: '[Ruler of Japan] Special Week',
    100201: '[Innocent Silence] Silence Suzuka',
    100301: '[Peak Joy] Tokai Teio',
    100302: '[Beyond the Horizon] Tokai Teio',
    100401: '[Formula R] Maruzensky',
    100402: '[Hot☆Summer Night] Maruzensky',
    100501: '[Shooting Star Revue] Fuji Kiseki',
    100502: '[Succès Étoilé] Fuji Kiseki',
    100601: '[Starlight Beat] Oguri Cap',
    100602: '[Ashen Miracle] Oguri Cap',
    100701: '[Red Strife] Gold Ship',
    100702: '[RUN! RUIN! LAUNCHER!] Gold Ship',
    100801: '[Wild Top Gear] Vodka',
    100802: '[Fiery Aqua Vitae] Vodka',
    100901: '[Peak Blue] Daiwa Scarlet',
    100902: '[Nuit Étoilée de Scarlet] Daiwa Scarlet',
    101001: '[Wild Frontier] Taiki Shuttle',
    101002: '[Bubblegum☆Memories] Taiki Shuttle',
    101101: '[Stone-Piercing Blue] Grass Wonder',
    101102: '[Saintly Jade Cleric] Grass Wonder',
    101201: '[Azure Amazon] Hishi Amazon',
    101301: '[Frontline Elegance] Mejiro McQueen',
    101302: '[End of the Skies] Mejiro McQueen',
    101303: '[Fair Lady of the Waves] Mejiro McQueen',
    101401: '[El☆Número 1] El Condor Pasa',
    101402: '[Kukulkan Warrior] El Condor Pasa',
    101501: '[O Sole Suo!] T.M. Opera O',
    101502: '[New Year, Same Radiance!] T.M. Opera O',
    101601: '[Maverick] Narita Brian',
    101701: "[Emperor's Path] Symboli Rudolf",
    101702: '[Archer by Moonlight] Symboli Rudolf',
    101801: '[Empress Road] Air Groove',
    101802: '[Quercus Civilis] Air Groove',
    101901: '[Full-Color Fangirling] Agnes Digital',
    101902: '[Fanatic♡Jiangshi] Agnes Digital',
    102001: '[Reeling in the Big One] Seiun Sky',
    102002: '[Soirée des Chatons] Seiun Sky',
    102101: '[Fast as Lightning] Tamamo Cross',
    102102: '[Raging Thunder] Tamamo Cross',
    102201: '[Noble Seamair] Fine Motion',
    102202: '[Titania] Fine Motion',
    102301: '[pf. Winning Equation...] Biwa Hayahide',
    102302: '[Rouge Caroler] Biwa Hayahide',
    102401: '[Scramble☆Zone] Mayano Top Gun',
    102402: '[Sunlight Bouquet] Mayano Top Gun',
    102501: '[Creeping Shadow] Manhattan Cafe',
    102601: '[MB-19890425] Mihono Bourbon',
    102602: '[CODE: ICING] Mihono Bourbon',
    102701: '[Down the Line] Mejiro Ryan',
    102801: '[Buono ☆ Alla Moda] Hishi Akebono',
    102901: "[Darl'n Snowflake] Yukino Bijin",
    103001: '[Rosy Dreams] Rice Shower',
    103002: '[Vampire Makeover!] Rice Shower',
    103101: '[Always Electrifying] Ines Fujin',
    103201: '[tach-nology] Agnes Tachyon',
    103301: '[Starry Nocturne] Admire Vega',
    103401: '[Edomurasaki] Inari One',
    103402: '[Golden Dream] Inari One',
    103501: '[Get to Winning!] Winning Ticket',
    103502: '[Dream Deliverer] Winning Ticket',
    103601: '[unsigned] Air Shakur',
    103701: '[Meisterschaft] Eishin Flash',
    103702: '[Precise Chocolatier] Eishin Flash',
    103801: '[Fille Éclair] Curren Chan',
    103802: '[Ma Chérie of the New Moon] Curren Chan',
    103901: '[Princess of Pink] Kawakami Princess',
    104001: '[Authentic / 1928] Gold City',
    104002: '[Autumn Cosmos] Gold City',
    104101: '[Blossom in Learning] Sakura Bakushin O',
    104201: '[Rocket☆Star] Seeking the Pearl',
    104401: '[Platanus Witch] Sweep Tosho',
    104501: '[Murmuring Stream] Super Creek',
    104502: '[Chiffon-Wrapped Mummy] Super Creek',
    104601: '[LOVE☆4EVER] Smart Falcon',
    104602: '[Twilight Triumph] Smart Falcon',
    104701: '[Heroic Author] Zenno Rob Roy',
    104801: '[Jokester ☆ Vibes] Tosen Jordan',
    104901: '[Desperate Measures] Nakayama Festa',
    105001: '[Nevertheless] Narita Taishin',
    105002: '[Difference Engineer] Narita Taishin',
    105101: '[Layered Petals] Nishino Flower',
    105201: '[Bestest Prize ♪] Haru Urara',
    105202: '[New Year ♪ New Urara!] Haru Urara',
    105301: '[Iron Ambition] Bamboo Memory',
    105601: '[Rising☆Fortune] Matikanefukukitaru',
    105602: '[Lucky Tidings] Matikanefukukitaru',
    105801: '[Turbulent Blue] Meisho Doto',
    105802: "[Dot-o'-Lantern] Meisho Doto",
    105901: '[Off the Line] Mejiro Dober',
    105902: '[Sapphire Sojourn] Mejiro Dober',
    106001: '[Poinsettia Ribbon] Nice Nature',
    106002: '[Run & Win] Nice Nature',
    106101: '[King of Emeralds] King Halo',
    106102: '[Cheerleader in Noble White] King Halo',
    106201: '[Clippety-Tippety-Clop] Matikanetannhauser',
    106401: '[Line Breakthrough] Mejiro Palmer',
    106701: '[Natural Brilliance] Satono Diamond',
    106801: '[Gilded Shrine to Glory] Kitasan Black',
    106901: '[Strength in Full Bloom] Sakura Chiyono O',
    107101: '[Crystalline] Mejiro Ardan',
    107201: '[Blazed Head, Covered Fists] Yaeno Muteki',
    107401: '[Brunissage Line] Mejiro Bright',
    107801: '[Fluttertail Spirit] Yamanin Zephyr',
    108701: '[Flare] Aston Machan',
    109801: '[Eightfold☆Fortune] Copano Rickey',
    110001: '[Butterfly Sting] Wonder Acute',
}

SSR_SUPPORTS = {
    30001: '[The Brightest Star in Japan!] Special Week',
    30002: '[Beyond This Shining Moment] Silence Suzuka',
    30003: '[Dream Big!] Tokai Teio',
    30004: '[Breakaway Battleship] Gold Ship',
    30005: '[Wild Rider] Vodka',
    30006: '[Fairest Fleur] Grass Wonder',
    30007: "[Champion's Passion] El Condor Pasa",
    30008: '[Foolproof Plan] Seiun Sky',
    30009: '[Split the Sky, White Lightning!] Tamamo Cross',
    30010: '[Wave of Gratitude] Fine Motion',
    30011: '[Watch My Star Fly!] Ines Fujin',
    30012: '[BNWinner!] Winning Ticket',
    30013: '[7 More Centimeters] Air Shakur',
    30014: '[Run(my)way] Gold City',
    30015: '[Eat Fast! Yum Fast!] Sakura Bakushin O',
    30016: '[Piece of Mind] Super Creek',
    30017: '[My Umadol Way! ☆] Smart Falcon',
    30018: '[Even the Littlest Bud] Nishino Flower',
    30019: "[Urara's Day Off!] Haru Urara",
    30020: '[Double Carrot Punch!] Biko Pegasus',
    30021: '[Tracen Reception] Tazuna Hayakawa',
    30022: '[Your Team Ace] Mejiro McQueen',
    30023: '[Showered in Joy] Rice Shower',
    30024: '[Get Lots of Hugs for Me] Oguri Cap',
    30025: '[The Setting Sun and Rising Stars] Special Week',
    30026: '[Turbo Booooost!] Twin Turbo',
    30027: '[Go Ahead and Laugh] Mejiro Palmer',
    30028: '[Fire at My Heels] Kitasan Black',
    30029: '[The Will to Overtake] Satono Diamond',
    30030: '[Just Keep Going] Matikanetannhauser',
    30031: '[Hometown Cheers] Yukino Bijin',
    30032: '[Fiery Discipline] Yaeno Muteki',
    30033: '[Dreams <I>Do</I> Come True!] Winning Ticket',
    30034: '[Happiness Just around the Bend] Rice Shower',
    30036: '[Planned Perfection] Riko Kashimoto',
    30038: '[Peak Sakura Season] Sakura Chiyono O',
    30039: '[Princess Bride] Kawakami Princess',
    30040: '[Who Wants the First Bite?] Hishi Akebono',
    30041: '[My Thoughts, My Desires] Mejiro Dober',
    30042: '[Head-on Fight!] Bamboo Memory',
    30043: '[43, 8, 1] Nakayama Festa',
    30044: '[Two Pieces] Narita Brian',
    30045: "[It's All Mine!] Sweep Tosho",
    30046: '[Full-Blown Tantrum] Winning Ticket',
    30047: '[Mini☆Vacation] Daiwa Scarlet',
    30048: '[Winning Pitch] Mejiro Ryan',
    30052: '[From the Ground Up] Light Hello',
    30053: '[Hands Up, Crook!] Taiki Shuttle',
    30054: '[Daring to Dream] Nice Nature',
    30055: '[Paint the Sky Red] Seiun Sky',
    30056: '[Tonight, We Waltz] King Halo',
    30057: '[That Time I Became the Strongest] Gold Ship',
    30058: '[Regal Racers] Tokai Teio',
    30059: '[Fugue of Fortune] Mihono Bourbon',
    30060: '[Constellation of Stars] Twin Turbo',
    30061: '[Our Resounding Steps] Biwa Hayahide',
    30062: '[Winning Dream] Silence Suzuka',
    30063: '[Warm Heart, Soft Steps] Ikuno Dictus',
    30064: '[Beware! Halloween Night!] Tamamo Cross',
    30065: '[Magical Heroine] Zenno Rob Roy',
    30066: '[The Ghost Finds Halloween Magic] Mihono Bourbon',
    30067: '[Esteemed and Adored] Heirs to the Throne',
    30068: '[Cutie Pie with Shining Eyes] Curren Chan',
    30069: "[The Whistling Arrow's Taunt] Narita Brian",
    30070: '[Dancing Light into the Night] Yukino Bijin',
    30071: '[Make! Some! NOISE!] Daitaku Helios',
    30072: '[Party Formation] Mayano Top Gun',
    30073: '[Strict Shopper] Narita Taishin',
    30074: '[Dazzling Day in the Snow] Marvelous Sunday',
    30075: '[My Solo Spun in Spiraling Runs] Manhattan Cafe',
    30076: '[Searching for Unseen Sights] Silence Suzuka',
    30077: '[Lucky Star in the Sky] Admire Vega',
    30078: '[Touching Sleeves Is Good Luck! ♪] Matikanefukukitaru',
    30079: '[Leaping into the Unknown] Meisho Doto',
    30080: '[This Might Sting!] Sasami Anshinzawa',
    30081: '[Passing the Dream On] Team Sirius',
    30082: '[Little Cupcakes, Big Emotions] Nishino Flower',
    30083: '[Super! Sonic! Flower Power!] Sakura Bakushin O',
    30084: '[My Way] Tosen Jordan',
    30085: "[A Fan's Joy] Agnes Digital",
    30086: '[Peachy Silhouette] Narita Top Road',
    30087: '[Little by Little] Mejiro Bright',
    30088: '[Special Dreamers!] Satono Diamond',
    30089: '[A MORE MARVELOUS WORLD! ☆] Marvelous Sunday',
    30090: '[Enchaînement] Symboli Rudolf',
    30091: '[Escorte Étoile] Sirius Symboli',
    30092: '[Mag!c Number] Air Shakur',
    30093: '[Number 1 Outfit] Daiwa Scarlet',
    30094: '[Make These Feelings Reach You!] Bamboo Memory',
    30095: '[Cheer that Changed the World] Seeking the Pearl',
    30096: '[Go Go☆Princess!] Kawakami Princess',
    30097: '[Dear Mr. C.B.] Mr. C.B.',
    30098: '[Sunny Passion ♪] Haru Urara',
    30099: '[Beloved Orchid Bouquet] Ikuno Dictus',
    30100: '[Day I Dreamed Of] Rice Shower',
    30101: '[Q≠0] Agnes Tachyon',
    30102: '[Twinkle in Your Eyes ∞] El Condor Pasa',
    30103: '[Machitan☆Adventure] Matikanetannhauser',
    30104: '["Rhodonite and the Dreamstone"] Zenno Rob Roy',
    30105: '[Take Hold of Our Dreams!] Special Week',
    30106: '[Tailwind to My Goals] Air Groove',
    30107: '[Sentimental Flare ♪] Maruzensky',
    30108: '[Trusting the Dice] Nakayama Festa',
    30109: '[A Good Heart Blossoms to Its Fullest] Sakura Chiyono O',
    30110: "[It's on the House] Manhattan Cafe",
    30111: '[Teio-Oo-Oo!!!] Tokai Teio',
    30112: '[TT Ignition!] Twin Turbo',
    30113: '[Uchronia Architect] Biwa Hayahide',
    30114: '[Ah, Such Majesty] Daiichi Ruby',
    30115: '[Moonlit Devil ♪] Mejiro Palmer',
    30116: '[Sunlit Angel ♪] Daitaku Helios',
    30117: '[Onwards, Demon Queen Lackeys!] Shinko Windy',
    30118: '[A Win Foreshadowed] Symboli Kris S',
    30119: '[Hopeful Petals Dancing in the Night] Mejiro Ardan',
    30120: '[Pious Flame, Heavens Scorcher] Yaeno Muteki',
    30121: '[U & Me] Mihono Bourbon',
    30122: '[Danke Schön] Eishin Flash',
    30123: '[Glad Tidings] Narita Brian',
    30124: '[Are You Merry?] Air Groove',
    30125: "[Don't Stop Anymore!] Sakura Laurel",
    30145: '[Welcome to Umayuru] Tanino Gimlet',
    30146: '[Run Forth! Dash On! Ever Forward!] Oguri Cap',
}

# SSR support card ids by type (support_card_data.command_id; Friend/Group by
# support_card_type), so a seed can deal the stats out evenly.
SUPPORT_TYPES = {
    "Speed": (
        30002, 30003, 30014, 30015, 30018, 30020, 30025, 30026, 30028, 30039,
        30044, 30045, 30053, 30057, 30065, 30072, 30076, 30078, 30084, 30086,
        30092, 30095, 30101, 30107, 30116, 30119, 30121, 30122,
    ),
    "Stamina": (
        30004, 30008, 30009, 30016, 30022, 30023, 30029, 30038, 30043, 30046,
        30059, 30062, 30069, 30075, 30079, 30087, 30090, 30099, 30104, 30110,
        30113, 30115, 30118, 30125,
    ),
    "Power": (
        30005, 30007, 30017, 30024, 30032, 30033, 30034, 30042, 30047, 30056,
        30058, 30064, 30071, 30074, 30077, 30085, 30093, 30096, 30098, 30106,
        30114, 30123, 30145,
    ),
    "Guts": (
        30001, 30006, 30011, 30012, 30019, 30027, 30030, 30040, 30048, 30060,
        30063, 30070, 30083, 30089, 30094, 30102, 30105, 30109, 30112, 30117,
        30120,
    ),
    "Wit": (
        30010, 30013, 30031, 30041, 30054, 30055, 30061, 30066, 30068, 30073,
        30082, 30088, 30091, 30097, 30100, 30103, 30108, 30111, 30124, 30146,
    ),
    "Friend": (
        30021, 30036, 30052, 30080,
    ),
    "Group": (
        30067, 30081,
    ),
}

# Each SSR's worth in logic, per scenario (URA, Unity, Grand Live, Trackblazer):
# % of an average SSR at limit break 4 in that scenario, kept to 60-130 (a
# loose rating: a card's worth also hangs on the trainee and the race). From
# Tachyon's Lab (jechto.github.io/Tachyons-lab, GPL-3.0) tier list model: an
# empty deck, every stat weighted alike as rank score counts them (the site
# weighs them for racing), averaged over every distance and running style.
# Its Grand Concert is Grand Live. Tazuna and Riko only exist in URA and Unity.
# A scenario's link cards (master single_mode_special_chara) get +20 there.
SUPPORT_VALUE = {
    30001: ( 95,  95, 100, 110),
    30002: (115, 115, 120, 125),  # links to Grand Live
    30003: (100, 100,  95,  95),
    30004: ( 95, 105, 115, 120),
    30005: (130, 130, 130, 130),
    30006: (125, 110, 105, 130),
    30007: (115, 115, 115, 115),
    30008: (130, 130, 130, 125),
    30009: ( 85,  95, 105, 105),
    30010: (110, 115, 125, 100),
    30011: (115, 105, 100, 130),
    30012: (120, 105, 105, 125),
    30013: ( 65,  70,  75,  70),
    30014: ( 75,  80,  85,  85),
    30015: (125, 120, 120, 130),
    30016: (130, 130, 130, 130),
    30017: ( 85,  70, 115, 100),  # links to Grand Live
    30018: ( 65,  75,  90,  85),
    30019: (130, 130, 120, 130),  # links to Unity
    30020: (130, 125, 125, 130),
    30021: (115,   0,   0,   0),
    30022: ( 85,  90,  90,  75),
    30023: (100, 125, 105,  90),  # links to Unity
    30024: ( 70,  65,  95,  90),
    30025: ( 80,  70,  75,  75),
    30026: ( 80,  80,  80,  85),
    30027: (130, 115, 105, 130),
    30028: (130, 130, 130, 130),
    30029: (120, 130, 130, 110),
    30030: (130, 130, 130, 130),
    30031: (115, 115, 125, 100),
    30032: (100, 110, 115, 115),
    30033: ( 65,  65,  90,  85),
    30034: (130, 130, 130, 130),  # links to Unity
    30036: (  0, 130,   0,   0),  # links to Unity
    30038: ( 85,  90,  90,  65),
    30039: ( 85,  85,  85,  95),
    30040: (105,  80,  80,  95),
    30041: ( 80,  75,  85,  65),
    30042: ( 65,  75,  80,  85),
    30043: (125, 130, 130, 120),
    30044: ( 80,  75,  75,  80),
    30045: (100, 100,  80, 115),
    30046: ( 60,  65,  75,  75),
    30047: ( 75,  70,  80,  75),
    30048: ( 95,  80,  70,  95),
    30052: ( 60,  60, 130,  60),  # by hand: Grand Live's own card, weak elsewhere
    30053: (120, 130, 115, 125),  # links to Unity
    30054: (105, 105, 120,  95),
    30055: ( 90,  95, 125,  60),
    30056: (130, 130, 130, 130),
    30057: ( 60,  60,  60,  60),
    30058: ( 70,  65,  70,  60),
    30059: ( 60,  60,  75,  60),  # links to Grand Live
    30060: ( 60,  60,  60,  60),
    30061: ( 80,  80,  90,  65),
    30062: ( 95,  95, 115,  75),  # links to Grand Live
    30063: (110, 120, 115, 130),
    30064: (125, 120, 110, 120),
    30065: (125, 130, 120, 125),
    30066: ( 80,  80, 110,  60),  # links to Grand Live
    30067: (125, 125, 110, 125),
    30068: (110, 120, 110,  95),
    30069: ( 95, 110, 105,  85),
    30070: (110, 100,  90, 115),
    30071: ( 75,  65,  90,  90),
    30072: (130, 130, 125, 130),
    30073: ( 60,  60,  60,  60),
    30074: ( 60,  65,  75,  80),
    30075: (120, 125, 125, 110),
    30076: ( 90,  85,  95,  80),  # links to Grand Live
    30077: ( 80,  70, 100,  90),
    30078: (130, 130, 130, 130),  # links to Unity
    30079: (105, 115, 110,  95),
    30080: ( 80, 100,  95, 100),
    30081: (115, 110, 100, 120),
    30082: (105, 110, 105,  85),
    30083: ( 65,  70,  75,  80),
    30084: (130, 130, 130, 130),
    30085: ( 95,  85, 105, 115),
    30086: ( 95,  95,  90,  95),
    30087: ( 90,  90,  90,  70),
    30088: ( 80,  75,  90,  60),
    30089: (115,  95,  95, 115),
    30090: (115, 120, 120, 105),
    30091: (100, 105, 105,  85),
    30092: ( 90,  85,  75,  80),
    30093: ( 60,  60,  70,  70),
    30094: (120, 105, 105, 130),
    30095: (105, 110,  95, 110),
    30096: ( 95,  80,  75,  80),
    30097: (115, 130, 125, 105),
    30098: ( 60,  65,  60,  60),  # links to Unity
    30099: ( 65,  75,  80,  80),
    30100: ( 70,  85,  85,  60),  # links to Unity
    30101: (100, 100, 110, 105),  # links to Grand Live
    30102: ( 85,  80,  80,  90),
    30103: (130, 130, 130, 130),
    30104: ( 95, 100, 100,  80),
    30105: (100,  95, 105, 110),
    30106: (115, 105, 100, 105),
    30107: (115, 110, 110, 115),
    30108: ( 95, 105, 110, 110),
    30109: (110, 100,  85, 120),
    30110: ( 90, 100, 100,  80),
    30111: (120, 125, 130, 110),
    30112: (130, 120, 110, 130),
    30113: (100, 105, 100,  85),
    30114: (110, 100,  95,  95),
    30115: (110, 120, 105,  95),
    30116: (130, 130, 130, 130),
    30117: (125, 125, 130, 130),
    30118: ( 95, 100, 100,  80),
    30119: ( 80,  80,  80,  75),
    30120: ( 70,  85,  85,  90),
    30121: ( 90,  85, 105,  85),  # links to Grand Live
    30122: (130, 130, 120, 130),
    30123: (100,  85,  80,  80),
    30124: (125, 130, 130, 120),
    30125: ( 85,  90,  90,  70),
    30145: ( 60,  60,  60,  60),
    30146: (130, 130, 130, 120),
}


def support_score(cards, scenario: int, crystals: int | None, per_card: int, deck: int = 6) -> int:
    """Logic's support bonus: the best `deck` cards in that scenario (an unknown
    id is an average card). crystals None: cards arrive maxed; otherwise a card
    is worth half until 4 crystals max it, best cards first."""
    v = sorted((per_card * SUPPORT_VALUE.get(c, (100,) * 4)[scenario - 1] // 100 for c in cards), reverse=True)[:deck]
    return sum(v) if crystals is None else (sum(v) + sum(v[:crystals // 4])) // 2

# G1 name -> career race ids (a race run at another venue keeps its name).
G1_RACES = {
    'February Stakes': (1001,),
    'Takamatsunomiya Kinen': (1002,),
    'Osaka Hai': (1003,),
    'Oka Sho': (1004,),
    'Satsuki Sho': (1005, 1028),
    'Tenno Sho (Spring)': (1006, 1027),
    'NHK Mile Cup': (1007,),
    'Victoria Mile': (1008,),
    'Japanese Oaks': (1009,),
    'Tokyo Yushun (Japanese Derby)': (1010,),
    'Yasuda Kinen': (1011,),
    'Takarazuka Kinen': (1012, 1025),
    'Sprinters Stakes': (1013,),
    'Shuka Sho': (1014,),
    'Kikuka Sho': (1015, 1026),
    'Tenno Sho (Autumn)': (1016,),
    'Queen Elizabeth II Cup': (1017,),
    'Mile Championship': (1018,),
    'Japan Cup': (1019,),
    'Champions Cup': (1020,),
    'Hanshin Juvenile Fillies': (1021,),
    'Asahi Hai Futurity Stakes': (1022,),
    'Arima Kinen': (1023,),
    'Hopeful Stakes': (1024,),
    'Teio Sho': (1101,),
    'Japan Dirt Derby': (1102,),
    "JBC Ladies' Classic": (1103, 1111, 1114, 1117),
    'JBC Sprint': (1104, 1112, 1115, 1118),
    'JBC Classic': (1105, 1113, 1116, 1119),
    'Tokyo Daishoten': (1106,),
    'Kawasaki Kinen': (1107,),
    'Zen-Nippon Junior Yushun': (1108,),
    'Kashiwa Kinen': (1109,),
    'Mile Championship Nambu Hai': (1110,),
}

# Rank tiers checked per scenario: (name, minimum rank score; master single_mode_rank).
RANK_TIERS = (("B", 6500), ("A", 10000), ("S", 14500), ("SS", 17500), ("UG", 19600))
# Rank ladder in any scenario, between and past the per-scenario tiers.
GLOBAL_RANKS = (
    ("B+", 8200),
    ("A+", 12100),
    ("S+", 15900),
    ("SS+", 19200),
    ("UG1", 20000),
    ("UG2", 20400),
    ("UG3", 20800),
)
# "Win N different races" across all careers (any race, distinct race ids).
UNIQUE_RACE_MILESTONES = tuple(range(5, 80, 5))  # 5, 10 ... 75
# Fans summed over every finished career on the save (~250k per career).
FAN_MILESTONES = tuple(range(250_000, 3_000_001, 250_000))  # every 250k to 3M
# Legend Race rival ladder: (tier, single_mode_rank id, legend_race row, boss stats
# speed/stamina/power/guts/wit). One rival per tier, each a real legend race row
# (its own boss, longer each step); beating a tier is a check and opens the next.
LEGEND_LADDER = (
    ("C", 9, 6, (600, 420, 540, 350, 480)),  # 1200 m
    ("C+", 10, 37, (690, 490, 620, 375, 550)),  # 1600 m
    ("B", 11, 22, (780, 560, 700, 400, 620)),  # 1600 m
    ("B+", 12, 41, (865, 630, 775, 425, 685)),  # 2000 m
    ("A", 13, 29, (950, 700, 850, 450, 750)),  # 2000 m
    ("A+", 14, 48, (1025, 750, 925, 475, 825)),  # 2200 m
    ("S", 15, 19, (1100, 800, 1000, 500, 900)),  # 2200 m
    ("S+", 16, 33, (1150, 850, 1050, 525, 950)),  # 2500 m
    ("SS", 17, 11, (1200, 900, 1100, 550, 1000)),  # 2400 m
    ("SS+", 18, 26, (1200, 1000, 1150, 600, 1050)),  # 3000 m
)
# single_mode_rank min_value per rank id: logic expects careers at that rank first.
LEGEND_RANK_SCORE = {9: 3500, 10: 4900, 11: 6500, 12: 8200, 13: 10000, 14: 12100,
                     15: 14500, 16: 15900, 17: 17500, 18: 19200}
# Team Trials: a check for each of the first N races won (later wins: nothing).
TEAM_TRIALS_CHECKS = 100  # ids 600-699
STATS = ("Speed", "Stamina", "Power", "Guts", "Wit")

# ---- items: name -> id -------------------------------------------------------
# Every scenario has an item; the seed's starting scenario (slot_data) is never in the pool.
SCENARIO_ITEM = {sid: f"Scenario: {name}" for sid, name in SCENARIOS.items()}
PROGRESSIVE = {
    "Progressive Stat Cap": 10,  # +50 to every stat cap
    "Progressive Starting Stats": 11,  # +20 to every stat at career start
    "Progressive Starting Skill Points": 12,  # +200 SP at career start
    # 13 was Dream's Luck (retired: the separate mod covers it)
    "Progressive Training Guard": 14,  # failure rate x0.75 per copy
    "Progressive RP Recovery": 15,  # Team Trials RP refills twice as fast per copy
    "Trainee Awakening": 16,  # one random owned trainee to 5 stars and potential 5
    # +20% gain and +50 cap on that stat per copy
    **{f"Progressive {s} Training": 20 + i for i, s in enumerate(STATS)},
}
# 30-35 were mail items (Carats, Monies, Alarm Clocks...): retired, not loot.
# Mailed items: name -> (id, present reward_type (item_category), reward id, count).
MAIL = {"Rainbow Uncap Crystal": (36, 164, 144, 1)}  # one SSR limit break, any card
MINOR = {
    "Minor Starting Stats": 60,  # +5 to every stat at career start
    "Minor Starting Skill Points": 61,  # +50 SP at career start
    "RP Refill": 62,  # Team Trials RP to full, once
}
# One-shot effects on the next career start (same queue as traps, never capped).
BOONS = {"Pep Talk": 50, "Lucky Charm": 51}
# One-shot effects on the next career; at most slot_data["trap_cap"] per career.
TRAPS = {
    "Bad Condition Trap": 40,
    "Bad Mood Trap": 41,
    "Low Energy Trap": 42,
    "Tunnel Vision Trap": 43,  # one stat's Progressive Training bonus is off this career
    "Butterfingers Trap": 44,  # failure rate x1.5 in the Junior year
    "Amnesia Trap": 45,  # no starting stats / SP buffs this career
}
TRAINEE_ITEM_BASE = 1_000_000  # + card_id
SUPPORT_ITEM_BASE = 2_000_000  # + support_card_id (seeds before 0.16.0)
# From 0.16.0 the pool holds tickets instead: the Nth ticket of a type is the
# Nth card of that type in slot_data["support_tickets"], so logic and server agree.
SUPPORT_TICKETS = {f"SSR Ticket ({t})": 70 + i for i, t in enumerate(SUPPORT_TYPES)}


def support_ticket(support_type: str) -> str:
    return f"SSR Ticket ({support_type})"


def support_type(card: int) -> str:
    return next(t for t, cards in SUPPORT_TYPES.items() if card in cards)


# High scores need more than a strong deck on paper: cards that stack the stats
# rating runs on (Speed, Wit) and trainees to pick one whose growth fits them.
# Score floor -> (Speed cards, Wit cards, trainees) owned, each capped by what the
# seed has, so every requirement can always be met.
DECK_NEEDS = ((19600, 4, 4, 16), (17500, 3, 3, 12), (14500, 2, 2, 8))


def deck_ok(score: int, have: tuple, seed_has: tuple) -> bool:
    """have / seed_has: (Speed cards, Wit cards, trainees) owned / in the whole seed."""
    need = next((n for floor, *n in DECK_NEEDS if score >= floor), (0, 0, 0))
    return _met(need, have, seed_has)


# A Legend Race rival is a real race, not a score: from rung A it also asks for
# what builds a usable uma. Per LEGEND_LADDER rung: (SSR cards: each brings its
# gold skill and hints; Stamina cards, for the 2400 m+ rungs; Progressive Starting
# Skill Points; Trainee Awakenings: unique skill levels), capped like DECK_NEEDS.
LEGEND_NEEDS = (
    (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0),  # C-B+
    (4, 0, 1, 0),  # A
    (5, 0, 1, 1),  # A+
    (6, 1, 2, 2),  # S
    (6, 2, 2, 3),  # S+ 2500 m
    (6, 2, 3, 4),  # SS 2400 m
    (6, 3, 3, 5),  # SS+ 3000 m
)


def legend_ok(tier: int, have: tuple, seed_has: tuple) -> bool:
    """have / seed_has: (SSR cards, Stamina cards, skill point items, awakenings)."""
    return _met(LEGEND_NEEDS[tier], have, seed_has)


def _met(need, have, seed_has) -> bool:
    return all(h >= min(n, total) for h, n, total in zip(have, need, seed_has))


def item_name_to_id() -> dict:
    table = {name: sid for sid, name in SCENARIO_ITEM.items()}
    table.update(PROGRESSIVE)
    table.update(MINOR)
    table.update({name: row[0] for name, row in MAIL.items()})
    table.update(BOONS)
    table.update(TRAPS)
    table.update({f"Trainee: {n}": TRAINEE_ITEM_BASE + c for c, n in TRAINEES.items()})
    table.update({f"Support: {n}": SUPPORT_ITEM_BASE + s for s, n in SSR_SUPPORTS.items()})
    table.update(SUPPORT_TICKETS)
    return table


# ---- locations: name -> id ---------------------------------------------------
G1_LOCATION_BASE = 100  # + index in G1_RACES
FINISH_LOCATION_BASE = 200  # + scenario id
RANK_LOCATION_BASE = 300  # + scenario * 10 + tier index
UNIQUE_RACES_LOCATION_BASE = 400  # + index in UNIQUE_RACE_MILESTONES
GLOBAL_RANK_LOCATION_BASE = 450  # + index in GLOBAL_RANKS
TEAM_TRIALS_LOCATION_BASE = 600  # + races won - 1
FAN_LOCATION_BASE = 700  # + index in FAN_MILESTONES
LEGEND_LOCATION_BASE = 500  # + index in LEGEND_LADDER
G1_SCENARIO_LOCATION_BASE = 2000  # + scenario * 100 + index in G1_RACES
TRAINEE_LOCATION_BASE = 1_000_000  # + card_id


def g1_location(name: str) -> str:
    return f"Win {name}"


def finish_location(scenario_id: int) -> str:
    return f"Finish a {SCENARIOS[scenario_id]} career"


def rank_location(scenario_id: int, tier: str) -> str:
    return f"{SCENARIOS[scenario_id]}: rank {tier}"


def global_rank_location(tier: str) -> str:
    return f"Reach rank {tier}"


def unique_races_location(count: int) -> str:
    return f"Win {count} different races"


def fans_location(fans: int) -> str:
    return f"Reach {fans:,} fans"


def team_trials_location(wins: int) -> str:
    return f"Team Trials: win {wins} race" + ("s" if wins > 1 else "")


def g1_scenario_location(name: str, scenario_id: int) -> str:
    return f"Win {name} in {SCENARIOS[scenario_id]}"


def fans_logic(fans: int) -> int:
    """The rank score logic expects before a fan milestone (~250k per career)."""
    return 9000 + fans // 1500


def legend_location(tier: str) -> str:
    return f"Legend Race: beat the {tier} rival"


def trainee_location(card_id: int) -> str:
    return f"Finish a career with {TRAINEES[card_id]}"


def location_name_to_id() -> dict:
    table = {g1_location(n): G1_LOCATION_BASE + i for i, n in enumerate(G1_RACES)}
    for sid in SCENARIOS:
        table[finish_location(sid)] = FINISH_LOCATION_BASE + sid
        for i, (tier, _score) in enumerate(RANK_TIERS):
            table[rank_location(sid, tier)] = RANK_LOCATION_BASE + sid * 10 + i
    for i, n in enumerate(UNIQUE_RACE_MILESTONES):
        table[unique_races_location(n)] = UNIQUE_RACES_LOCATION_BASE + i
    for i, (tier, _score) in enumerate(GLOBAL_RANKS):
        table[global_rank_location(tier)] = GLOBAL_RANK_LOCATION_BASE + i
    for i, (tier, *_rest) in enumerate(LEGEND_LADDER):
        table[legend_location(tier)] = LEGEND_LOCATION_BASE + i
    for n in range(1, TEAM_TRIALS_CHECKS + 1):
        table[team_trials_location(n)] = TEAM_TRIALS_LOCATION_BASE + n - 1
    for i, n in enumerate(FAN_MILESTONES):
        table[fans_location(n)] = FAN_LOCATION_BASE + i
    for sid in SCENARIOS:
        for i, n in enumerate(G1_RACES):
            table[g1_scenario_location(n, sid)] = G1_SCENARIO_LOCATION_BASE + sid * 100 + i
    table.update({trainee_location(c): TRAINEE_LOCATION_BASE + c for c in TRAINEES})
    return table


if __name__ == "__main__":  # ids unique, names unique
    items, locs = item_name_to_id(), location_name_to_id()
    assert len(set(items.values())) == len(items) and len(set(locs.values())) == len(locs)
    print(len(items), "items,", len(locs), "locations: ok")
