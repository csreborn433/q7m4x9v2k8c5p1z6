"""The in-game "What's new" window: shown once per release on the main menu (native_mainmenu.py).

RELEASE must match data/mod_version.txt. Closing the window saves ui_cs2gc_whatsnew = SEEN_ID through the NEW
settings bridge (native_newsettings.py), so it appears again only after the next update changes RELEASE.
"""
import re

RELEASE = '1.1.0-beta.1'
SEEN_ID = 'r' + re.sub(r'\W', '_', RELEASE) + '_automatic_death_view'
DISPLAY_VERSION = 'V1.1'
TITLE = "WHAT'S NEW IN CS-REBORN"
SUBTITLE = DISPLAY_VERSION

# (header, [(bold lead, text)]) in display order.
SECTIONS = [
    ("WHAT'S NEW", [
        ('NEW: Anime Case', '50 stars, no key. Unlock Goku, Itachi, Naruto, Kakashi or Sakura as standalone agents '
                            'for both teams, with their own hands and native 3D inspection. Sakura is red, '
                            'Goku and Itachi pink, Naruto and Kakashi purple.'),
        ('Armory refresh', 'the Anime Case stays in the centre of the 4/3/4 page. The new 30-star Karambit Case '
                           'contains only Karambits, including official and custom finishes with random wear and '
                           'a chance of StatTrak. Name Tags replace the agents offer for 1 star. '
                           'Charms cost 3 stars, stickers 2, and ordinary cases and collections 5.'),
        ('One-star sales', 'sellable local weapons, knives, gloves, agents, stickers, charms and containers all grant '
                           'one Armory star. The value is identical in single-item and multi-item selling.'),
        ('Max performance', 'the low-end option now disables environmental fog, microshadows and smoke shadows, '
                            'reduces particle detail and distant props, caps texture streaming at the supported '
                            '512-pixel minimum, and keeps fewer old ragdolls. Your FPS caps are preserved.'),
        ('HUD-coloured smoke', 'a new toggle below old CS:GO animations makes your thrown smoke use your HUD colour '
                               'on local CS-Reborn servers. Everyone sees the thrower\'s colour; team HUD means '
                               'orange for T and blue for CT. Off by default.'),
        ('Automatic first-person death view', 'no toggle: the head-attached camera is now always enabled for '
                                             'default, official and anime agents. It holds for 3 seconds, then fades '
                                             'to a living teammate, or stays at your head when nobody is alive.'),
        ('Clearer main menu', 'a compact CS-REBORN badge and highlighted BETA 1.1 label now match the Armory column.'),
        ('Progress preserved', 'updating the Armory, prices and settings does not reset stars, statistics or inventory; '
                               'existing saved profile data continues to load normally.'),
    ]),
]
