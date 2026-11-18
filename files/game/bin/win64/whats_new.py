"""The in-game "What's new" window: shown once per release on the main menu (native_mainmenu.py).

RELEASE must match data/mod_version.txt. Closing the window saves ui_cs2gc_whatsnew = SEEN_ID through the NEW
settings bridge (native_newsettings.py), so it appears again only after the next update changes RELEASE.
"""
import re

RELEASE = '1.0.0-beta.5'
SEEN_ID = 'r' + re.sub(r'\W', '_', RELEASE)
DISPLAY_VERSION = 'V1.0'
TITLE = "WHAT'S NEW IN CS-REBORN"
SUBTITLE = DISPLAY_VERSION

# (header, [(bold lead, text)]) in display order.
SECTIONS = [
    ("WHAT'S NEW", [
        ('Vanilla Case', 'a free one-time case is waiting at the end of your inventory. It opens without a key into '
                         'any knife in its vanilla finish, with a random chance of StatTrak\u2122.'),
        ('CS:GO animations', 'NEW settings (the former Watch tab) has a toggle for the original CS:GO draw, inspect '
                             'and reload animations on guns and knives. It is off by default, so CS2 animations stay. '
                             'Restart CS2 after switching.'),
        ('Howl price', 'the M4A4 | Howl in the Armory now costs 100 stars instead of 250.'),
        ('Online play (experimental)', 'both maps now use the native lobby start for Steam parties. Direct joins '
                                        'use Hamachi/ZeroTier, LAN or a forwarded public IP; COPY CONNECT shows '
                                        'the address. Two-PC gameplay validation is still pending.'),
        ('Shared skins and Premier ratings', 'equipped skins, knives, gloves, agents and Armory items now have '
                                             'Steam peer sharing as well as direct-IP sharing. Premier profiles '
                                             'use the same channels. Everyone needs this version and matching '
                                             'custom-finish assets.'),
        ('Parties (experimental)', 'the PARTIES button in the main menu lists CS-Reborn parties from everyone, '
                                   'through Steam. Host one or press JOIN; when the host picks a map, the whole '
                                   'party follows to the host\'s server. Two-PC validation is still pending.'),
        ("What's new window", 'this window appears once after every update. Close it when you are done reading; '
                              "the WHAT'S NEW button above the Armory opens it again every time you click it."),
        ('NEW settings save', 'your choices on the NEW page are now kept between launches.'),
    ]),
]
