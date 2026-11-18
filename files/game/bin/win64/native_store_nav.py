"""Open Store on Armory and remove Home/General from its tab strip."""
from native_resources import install_override

ANCHOR = '        MakeTabsBtnsFromStoreData();'
# The store defaults to the Home tab when nothing is active; land on the Armory (xpshop) instead.
HOME_DEFAULT = "            navBtn = _m_cp.FindChildInLayoutFile('id-store-nav-home');"
ARMORY_DEFAULT = ("            navBtn = _m_cp.FindChildInLayoutFile('id-store-nav-xpshop') ||\n"
                  "                _m_cp.FindChildInLayoutFile('id-store-nav-home');")
INSERT = '''        MakeTabsBtnsFromStoreData();
        // cs2_gc: the Armory is the Store landing page; keep Tools available.
        ['id-store-nav-home', 'id-store-nav-coupon'].forEach(id => {
            const tab = _m_cp.FindChildInLayoutFile(id);
            if (tab) { tab.visible = false; tab.style.visibility = 'collapse'; }
        });'''


def patch(source):
    if (source.count(ANCHOR) != 1 or source.count(HOME_DEFAULT) != 1
            or 'cs2_gc: the Armory is the Store landing page' in source):
        raise ValueError('Installed fullscreen Store tab contract changed; no patch written')
    return source.replace(ANCHOR, INSERT, 1).replace(HOME_DEFAULT, ARMORY_DEFAULT, 1)


def prepare(directory, config):
    return install_override(
        directory,
        enabled=True,
        folder='cs2_gc_store_nav',
        comment='cs2_gc Armory-first Store navigation',
        owner='cs2-gc-store-nav-v1',
        asset='panorama/scripts/mainmenu_store_fullscreen.vts_c',
        patch=patch,
    )
