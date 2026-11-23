"""Small presentation overrides generated from the supported client's own resources."""
import struct
import zlib
import hashlib

from kv3 import read_resource, write_resource
from native_animations import VpkIndex
from native_resources import rewrite_script


def _replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Installed presentation contract changed: ' + old.splitlines()[0])
    return source.replace(old, new, 1)


def warehouse_inspect(source):
    # Keep the dedicated acknowledgement and item-specific compositing scenes.
    choice = """        let backgroundMap = GameInterfaceAPI.GetSettingString('ui_inspect_bkgnd_map');
        if (backgroundMap == 'mainmenu' || bUseMainMenuMap === true) {
            backgroundMap = GameInterfaceAPI.GetSettingString('ui_mainmenu_bkgnd_movie');
        }
        backgroundMap = !backgroundMap ? backgroundMap : backgroundMap + '_vanity';
        return backgroundMap;"""
    return _replace(source, choice, "        return 'warehouse_vanity';")


def cobble_loading(source):
    path = "'file://{images}/map_icons/screenshots/1080p/' + m_mapName + suffix + '.png'"
    icon = "'file://{images}/map_icons/map_icon_' + mapName + '.svg'"
    source = _replace(source, path, "m_mapName === 'cobblewingman' && n === 0 ? "
                      "'file://{images}/cs2_gc/cobblestone_banner.png' : " + path)
    source = _replace(source, icon, "mapName === 'cobblewingman' ? "
                      "'file://{images}/cs2_gc/cobblestone_emblem.png' : " + icon)
    # The native slideshow initially hides every image and never reveals a lone slide.
    return _replace(source, '        if (arrSlides.length <= 1)\n            return;',
                    """        if (arrSlides.length <= 1) {
            if (m_mapName === 'cobblewingman' && arrSlides.length === 1)
                arrSlides[0].SwitchClass('viz', 'show-first');
            return;
        }""")


def console_style(resource):
    version, blocks = read_resource(resource)
    data = dict(blocks).get('DATA', b'')
    # v3 compiled CSS has a six-byte header followed by minified CSS (not script DATA).
    if version != 3 or data[4:6] != b'\0\0' or not data[6:].startswith(b'#ConsoleText{') or b'#ConsoleInput{' not in data:
        raise ValueError('Unsupported game console style; no patch written')
    css = data[6:] + (
        b'.ConsolePanel{background-color:gradient(linear, 0% 0%, 100% 100%, from(#ffc398), to(#ffb8ce));}'
        b'#Header{background-color:#402c38;}#ConsoleText{color:#281e25;text-shadow:0px 1px 2px #49313c;}'
        b'#ConsoleInput{background-color:#332830;}')
    changed = struct.pack('<I', zlib.crc32(css)) + data[4:6] + css
    return write_resource(version, [(k, changed if k == 'DATA' else v) for k, v in blocks if k != 'SrMa'])


HUD = 'panorama/layout/hud/hud.vxml_c'
KEYS = 'panorama/layout/settings/settings_kbmouse.vxml_c'


def without_chat_wheel(path, data):
    import kv3
    from native_compact_settings import attrs, children, value, walk
    expected = {HUD: 'f4b29075dc287526d08255879e156ded6336e73e464e8fd68308303abc1a53a4',
                KEYS: '3f2eebcde56bad337559cf721d51eab992496a15ceebab9f9ea9e973f8c94b91'}
    if hashlib.sha256(data).hexdigest() != expected[path]:
        raise ValueError('Unsupported chat wheel layout: ' + path)
    version, blocks = read_resource(data)
    block, = (b for b in blocks if b[0] == 'LaCo')
    guid, doc = kv3.read_kv3(block[1])
    root = doc.get('m_AST').get('m_pRoot')
    def remove(n):
        kind, name = value(n, 'eType'), value(n, 'name')
        if kind == 'PANEL':
            a = attrs(n)
            return (a.get('id') == 'RadialRadio' if path == HUD else
                    a.get('id') == 'SettingsChatWheel' or
                    a.get('onactivate') == "SettingsMenuShared.ScrollToId('SettingsChatWheel')")
        return path == KEYS and (
            (kind == 'INCLUDE' and any(value(c, 'name') == 'panorama/scripts/settingsmenu_chatwheel.vts' for c in children(n))) or
            (kind == 'SNIPPET' and name in ('ChatWheelOptionPanel','ChatWheelHeadingPanel')))
    removed = 0
    for parent in list(walk(root)):
        old = children(parent)
        kept = [n for n in old if not remove(n)]
        if len(kept) != len(old):
            removed += len(old) - len(kept)
            parent.value[:] = [(k,v) for k,v in parent.value if k not in ('vecChildren','child')]
            if kept:
                parent.value.append(('vecChildren', kv3.Node(kv3.ARRAY, kept)))
    if removed != (1 if path == HUD else 5):
        raise ValueError('Chat wheel node count changed in ' + path)
    block[1] = kv3.write_kv3(guid, doc)
    return write_resource(version, blocks)


def assets(game):
    index = VpkIndex(game / 'csgo/pak01_dir.vpk', prefixes=('panorama/scripts/', 'panorama/styles/',
                                                           'panorama/layout/hud/', 'panorama/layout/settings/'))
    patches = [('panorama/scripts/inspect.vts_c', warehouse_inspect),
               ('panorama/scripts/loadingscreen.vts_c', cobble_loading)]
    extra = [(path, rewrite_script(index.read(path), patch)) for path, patch in patches]
    path = 'panorama/styles/gameconsole.vcss_c'
    extra.append((path, console_style(index.read(path))))
    extra.extend((p, without_chat_wheel(p, index.read(p))) for p in (HUD, KEYS))
    return extra
