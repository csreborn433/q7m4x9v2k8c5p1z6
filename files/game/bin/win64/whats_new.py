"""The in-game "What's new" window: shown once per release on the main menu (native_mainmenu.py).

RELEASE must match data/mod_version.txt. Closing the window saves ui_cs2gc_whatsnew = SEEN_ID through the NEW
settings bridge (native_newsettings.py), so it appears again only after the next update changes RELEASE.
"""
RELEASE = '1.0.2'
SEEN_ID = 'r1_0_2'
DISPLAY_VERSION = 'V1.0'  # Patch releases share one player-facing bulletin.
TITLE = "WHAT'S NEW IN CS-REBORN"
SUBTITLE = DISPLAY_VERSION
# The anime agent portraits are drawn directly below this bulletin.
AGENTS_AFTER = 'NEW: Anime Case'

# (header, [(bold lead, text)]) in display order.
SECTIONS = [
    ("NEW IN " + DISPLAY_VERSION, [
        ('Launch banner', 'Play shows a CS:REBORN loading banner while your game is being prepared.'),
        ('Parties', 'open the Parties tab to host or join a Steam lobby. Your hosted party appears first in the list. '
                    'Choose a map in Play when everyone is ready. '
                    'If native party travel does not connect you, use Copy Connect.'),
        ('Leaderboards', 'open Steam profiles discovered on this device. Recently Unboxed now shows your last '
                         'four pulls on Home, with float and seed for painted items.'),
        ('Armory refresh', 'a fixed 4/3/4 page. Top: Missing Link Charms (3 stars), a sticker capsule (2), the '
                           'stkr craft stickers (2) and a Name Tag (1). Middle: the Sport & Field Collection (10), '
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
        ('Max performance', 'the low-end option disables environmental fog, microshadows and smoke shadows, '
                            'reduces particle detail and distant props, caps texture streaming at the supported '
                            '512-pixel minimum, and keeps fewer old ragdolls. Your FPS caps are preserved.'),
        ('Automatic first-person death view', 'the head-attached camera is always enabled for default, official and '
                                             'anime agents. It holds for 3 seconds, then fades to a living teammate, '
                                             'or stays at your head when nobody is alive.'),
        ('New links', 'click the CS-REBORN BETA 1.0 badge under the Armory for the official website, or '
                      "DEVELOPER for the developer's Steam profile."),
    ]),
]
