"""The in-game "What's new" window: shown once per release on the main menu (native_mainmenu.py).

RELEASE must match data/mod_version.txt. Closing the window saves ui_cs2gc_whatsnew = SEEN_ID through the NEW
settings bridge (native_newsettings.py), so it appears again only after the next update changes RELEASE.
"""
RELEASE = '1.0.14'
SEEN_ID = 'r1_0_14'
DISPLAY_VERSION = 'V1.0'  # Patch releases share one player-facing bulletin.
TITLE = "WHAT'S NEW IN CS-REBORN"
SUBTITLE = DISPLAY_VERSION
# The PRIME Karambit picture and the anime agent portraits are drawn directly below these bulletins.
PRIME_AFTER = 'NEW: PRIME Karambit'
AGENTS_AFTER = 'NEW: Anime Case'

# (header, [(bold lead, text)]) in display order.
SECTIONS = [
    ("NEW IN " + DISPLAY_VERSION, [
        ('NEW: PRIME Karambit', 'a standalone Karambit with its own inspect, draw and attack '
                                'animations, a blade-down grip and a 3D preview. Buy it in the Armory for 30 stars, then equip it as '
                                'your CT or T knife.'),
        ('Cobblestone bots', 'Add Bots in Play lets the host choose one, two or three bots. Leave it off for a human-only match.'),
        ('Menus', 'Home links directly to regular Settings. The stock buy menu is back, including with old animations enabled. The chat wheel has been removed.'),
        ('Settings', 'ordinary Settings now opens on Crosshair. Game has viewmodel sliders and a live radar preview. '
                     'The separate NEW SETTINGS tab has its own tuning icon.'),
        ('Launch banner', 'Play shows a CS:REBORN loading banner while your game is being prepared.'),
        ('Black Market', 'the former Parties tab is now BLACK MARKET: six tall offers drawn at random for your '
                         'account and then fixed, so they never change. Click a card to reveal a rare '
                         'gun or knife finish, then buy it for 30 stars. Each offer can be bought once.'),
        ('Parties', 'PARTIES now sits in the left column, where Leaderboards used to be. Host or join a Steam '
                    'lobby; your hosted party appears first in the list. Choose a map in Play when everyone is '
                    'ready. If native party travel does not connect you, use Copy Connect.'),
        ('Leaderboards', 'now lives inside PARTIES, underneath the party browser, and opens Steam profiles '
                         'discovered on this device. Recently Unboxed shows your last four pulls on Home, with '
                         'float and seed for painted items.'),
        ('Cobblestone only', 'Play now offers just Cobblestone in Casual, Competitive and Wingman. '
                             'Overpass is removed from the list.'),
        ('Armory refresh', 'a fixed 4/3/4 page. Top: Missing Link Charms (3 stars), a sticker capsule (2), the '
                           'stkr craft stickers (2) and the PRIME Karambit (30). Middle: the Sport & Field Collection (10), '
                           'the Anime Case (50) and the new glove-only Gauntlet Case (15). Bottom: Overpass 2024 (5), '
                           'Dreams & Nightmares Case (5), the Dead Hand Terminal (5) and the new Vanilla Knife Case (15).'),
        ('Vanilla Knife Case', 'opens without a key and gives one random vanilla knife, with a chance of StatTrak. '
                               'Karambit Cases you already own still open normally.'),
        ('HUD colour menu', 'NEW SETTINGS now has a HUD & SMOKE COLOUR dropdown. Pick any HUD colour and your thrown '
                            'smokes use the same colour on local CS-Reborn servers, for everyone. Team colour means '
                            'orange for T and blue for CT. The old smoke on/off toggle is gone.'),
        ('Update notice', 'when a newer CS-Reborn version is published, a banner on the main menu tells you. Close '
                          'CS2 and open the launcher again: it downloads and installs the update before you play.'),
        ('Progress stays safe', 'updates never replace your stars, inventory, statistics or settings. The launcher '
                                'also saves a Before-Update copy of your progress before installing a new version.'),
        ('NEW: Anime Case', '50 stars, no key. Unlock Goku, Itachi, Naruto, Kakashi or Sakura as standalone agents '
                            'for both teams, with their own hands and native 3D inspection. Sakura is red, '
                            'Goku and Itachi pink, Naruto and Kakashi purple.'),
        ('One-star sales', 'sellable local weapons, knives, gloves, agents, stickers, charms and containers all grant '
                           'one Armory star. The value is identical in single-item and multi-item selling.'),
        ('Video settings', 'choose Low, Medium or High and a supported aspect ratio on one Video page. '
                           'The game and menu FPS caps are separate. VSync stays off and player contrast stays on.'),
        ('Low-end mode', 'applies the native Low video preset, reduces ragdolls, and turns off first-person tracers '
                         'and animated avatars without changing sv_cheats. Switching it off restores your previous preset.'),
        ('Automatic first-person death view', 'the head-attached camera is always enabled for default, official and '
                                             'anime agents. It holds for 3 seconds, then fades to a living teammate, '
                                             'or stays at your head when nobody is alive.'),
        ('New links', 'click the CS-REBORN BETA 1.0 badge under the Armory for the official website, or '
                      "DEVELOPER for the developer's Steam profile."),
    ]),
]
