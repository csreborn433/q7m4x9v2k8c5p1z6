"""Disable the removed NEW tab and manage the optional original CS2 buy-wheel override."""
from pathlib import Path
import hashlib
import json
import os
import re
import struct

from native_resources import console_log_path, install_override, mount_gameinfo, read_text
from native_tradeups import atomic_write
from whats_new import SEEN_ID as WHATS_NEW_SEEN

LEGACY_LOW_END = [('r_shadows', '0', '1'), ('r_dynamic', '0', '1'), ('r_particle_max_detail_level', '0', '2'),
           ('r_particle_shadows', '0', '1'), ('r_propsmaxdist', '200', '1200'), ('r_drawskybox', '0', '1'),
           ('r_drawdecals', '0', '1'), ('r_drawtracers', '0', '1'), ('r_csgo_cmaa_quality', '0', '1'),
           ('r_fog', '0', '1'), ('r_3dsky', '0', '1'), ('r_texturefilteringquality', '0', '2'),
           ('r_texture_stream_max_resolution', '128', '0'), ('fps_max', '0', '400'),
           ('fps_max_ui', '60', '120')]
PREVIOUS_LOW_END = [('r_shadows', '0', '1'), ('r_dynamic', '0', '1'), ('r_particle_max_detail_level', '0', '2'),
           ('r_particle_shadows', '0', '1'), ('r_propsmaxdist', '100', '1200'), ('r_drawskybox', '0', '1'),
           ('r_drawdecals', '0', '1'), ('r_drawtracers', '0', '1'), ('r_csgo_cmaa_quality', '0', '1'),
           ('r_fog', '0', '1'), ('r_3dsky', '0', '1'), ('r_texturefilteringquality', '0', '2'),
           ('r_texture_stream_max_resolution', '64', '0')]
# Verified with this client's help output: no removed or cheat-protected controls, and the texture minimum is 512.
LOW_END = [('r_particle_max_detail_level', '0', '3'), ('r_particle_shadows', '0', '1'),
           ('r_propsmaxdist', '100', '1200'), ('r_csgo_cmaa_quality', '0', '3'),
           ('r_texturefilteringquality', '0', '1'), ('r_texture_stream_max_resolution', '512', '2048'),
           ('r_csgo_enable_volume_fog', '0', '1'), ('r_csgo_enable_cubemap_fog', '0', '1'),
           ('r_csgo_enable_gradient_fog', '0', '1'), ('r_csgo_microshadowing', '0', '1'),
           ('r_csgo_smoke_shadow', '0', '1'), ('r_csgo_mixed_resolution_particles', '1', '1'),
           ('cl_ragdoll_limit', '8', '20')]
PREVIOUS_FRAME_LIMITS = [('fps_max', '400', '400'), ('fps_max_ui', '60', '120')]
DEFAULT_FRAME_LIMITS = [('fps_max', '222'), ('fps_max_ui', '99')]
LOW_END_JS = '[' + ','.join("['%s','%s','%s']" % row for row in LOW_END) + ']'
DEFAULTS = {'ui_low_end_pc': '0', 'ui_cs2gc_buymenu': 'cs2', 'ui_cs2gc_animations': 'cs2',
            'ui_cs2gc_whatsnew': '0', 'ui_cs2gc_smoke': '0'}
PREVIOUS_KEYS = tuple(key for key in DEFAULTS if key != 'ui_cs2gc_smoke')
WHEEL_FOLDER = 'cs2_gc_buymenu_wheel'
WHEEL_COMMENT = 'cs2_gc original buy wheel'
WHEEL_OWNER = 'cs2-gc-original-buy-wheel-v1'
WHEEL_ASSETS = ('panorama/layout/buymenu.vxml_c', 'panorama/styles/buymenu.vcss_c', 'panorama/scripts/buymenu.vjs_c')

# ---------------------------------------------------------------- settings menu
TABINFO_ANCHOR = '        CrosshairSettings: {'
LOAD_ANCHOR = "            newPanel.BLoadLayout('file://{resources}/layout/settings/' + XmlName + '.xml', false, false);"
CHECK_ANCHOR = '            $("#" + TabInfo[tabID].radioid).checked = true;'
INIT_ANCHOR = '    function _Init() {'

SETTINGS_SCRIPT = r'''
    // cs2_gc: NEW settings tab using native Settings controls.
    const _cs2gcLowEnd=__LOWEND__;
    function _CS2GCSetting(key,value){
        GameInterfaceAPI.SetSettingString(key,value);
        $.Msg('CS2GC_SETTING '+key+' '+value);
    }
    function _CS2GCApplyLowEnd(on){_cs2gcLowEnd.forEach(kv=>GameInterfaceAPI.ConsoleCommand(kv[0]+' '+(on?kv[1]:kv[2])));}
    function _CS2GCSection(parent,title,description){
        const heading=$.CreatePanel('Label',parent,'',{text:title});
        heading.AddClass('SettingsSectionTitleLabel');
        $.CreatePanel('Label',parent,'',{text:description});
    }
    function _CS2GCChoice(parent,label,active,fn){
        const b=$.CreatePanel('RadioButton',parent,'');
        b.checked=active;
        $.CreatePanel('Label',b,'',{text:label});
        b.SetPanelEvent('onactivate',fn);
        return b;
    }
    function _CS2GCChoiceRow(parent,choices){
        const row=$.CreatePanel('Panel',parent,'');
        row.AddClass('SettingsMenuDropdownContainer');
        choices.forEach(choice=>_CS2GCChoice(row,choice[0],choice[1],choice[2]));
    }
    function _CS2GCBuildNewSettings(panel){
        panel.RemoveAndDeleteChildren();
        panel.AddClass('SettingsMenuTab');
        const content=$.CreatePanel('Panel',panel,'');
        content.AddClass('SettingsMenuTabContent');
        const h=$.CreatePanel('Label',content,'',{text:'NEW'});
        h.AddClass('SettingsSectionTitleLabel');
        const lowOn=GameInterfaceAPI.GetSettingString('ui_low_end_pc')==='1';
        _CS2GCSection(content,'MAX PERFORMANCE','Aggressively reduces world detail, effects, particles, decals and texture streaming while keeping the current frame limits.');
        _CS2GCChoiceRow(content,[
            ['OFF',!lowOn,()=>{_CS2GCSetting('ui_low_end_pc','0');_CS2GCApplyLowEnd(false);_CS2GCBuildNewSettings(panel);}],
            ['ON',lowOn,()=>{_CS2GCSetting('ui_low_end_pc','1');_CS2GCApplyLowEnd(true);_CS2GCBuildNewSettings(panel);}]
        ]);
        const csgo=GameInterfaceAPI.GetSettingString('ui_cs2gc_buymenu')==='csgo';
        _CS2GCSection(content,'SELECT BUY MENU UI','Choose the current CS2 menu or the original CS2 launch-era radial buy wheel. Restart CS2 to apply the choice.');
        _CS2GCChoiceRow(content,[
            ['CS2',!csgo,()=>{_CS2GCSetting('ui_cs2gc_buymenu','cs2');_CS2GCBuildNewSettings(panel);}],
            ['CSGO',csgo,()=>{_CS2GCSetting('ui_cs2gc_buymenu','csgo');_CS2GCBuildNewSettings(panel);}]
        ]);
    }
    function _CS2GCEnsureNewTab(){
        if($('#CS2GCNewRadio'))return;
        const anchor=$('#GameRadio')||$('#CrosshairRadio');
        if(!anchor){$.Msg('CS2GC: native settings tab anchor was not found');return;}
        const radio=$.CreatePanel('RadioButton',anchor.GetParent(),'CS2GCNewRadio');
        $.CreatePanel('Label',radio,'',{text:'NEW'});
        anchor.GetParent().MoveChildAfter(radio,anchor);
        radio.SetPanelEvent('onactivate',()=>{
            if(typeof SettingsMenu!=='undefined')SettingsMenu.NavigateToTab('NewSettings');
            else NavigateToTab('NewSettings');
        });
    }
'''


def patch_settings(source):
    if '_CS2GCBuildNewSettings' in source:
        raise ValueError('Settings menu is already patched')
    if source.count(TABINFO_ANCHOR) == 1:
        source = source.replace(TABINFO_ANCHOR, '        NewSettings: {\n            xml: "",\n            radioid: "CS2GCNewRadio"\n        },\n' + TABINFO_ANCHOR, 1)
    elif len(re.findall(r'(?m)^\s*Search\s*:\s*\{', source)) == 1:
        source = re.sub(r'(?m)^(\s*)Search\s*:\s*\{',
                        r'\1NewSettings: { xml: "", radioid: "CS2GCNewRadio" },\n\1Search: {',
                        source, count=1)
    else:
        raise ValueError('Installed settings tab registry contract changed')

    if source.count(LOAD_ANCHOR) == 1:
        source = source.replace(LOAD_ANCHOR, "            if (tabID === 'NewSettings') _CS2GCBuildNewSettings(newPanel);\n"
                            "            else" + LOAD_ANCHOR[11:], 1)
    else:
        load = re.compile(r"(?m)^(\s*)newPanel\.BLoadLayout\(([^\n;]+)\);")
        if len(load.findall(source)) != 1:
            raise ValueError('Installed settings layout loader contract changed')
        source = load.sub(lambda match: match.group(1) +
            "if (tabID === 'NewSettings') _CS2GCBuildNewSettings(newPanel);\n" +
            match.group(1) + "else newPanel.BLoadLayout(" + match.group(2) + ");", source, count=1)

    if source.count(INIT_ANCHOR) == 1:
        source = source.replace(INIT_ANCHOR, SETTINGS_SCRIPT.replace('__LOWEND__', LOW_END_JS) +
                                INIT_ANCHOR + '\n        _CS2GCEnsureNewTab();', 1)
        if source.count(CHECK_ANCHOR) == 1:
            source = source.replace(CHECK_ANCHOR, '            const _cs2gcRadio = $("#CS2GCNewRadio");\n'
                                '            if (_cs2gcRadio) _cs2gcRadio.checked = tabID === "NewSettings";\n'
                                '            if ($("#" + TabInfo[tabID].radioid)) $("#" + TabInfo[tabID].radioid).checked = true;', 1)
    elif source.count('var _NavigateToTab = function') == 1 and source.count('SettingsMenu.Init();') == 1:
        source = source.replace('var _NavigateToTab = function', SETTINGS_SCRIPT.replace('__LOWEND__', LOW_END_JS) +
                                '\n    var _NavigateToTab = function', 1)
        init = re.compile(r'(?m)^([ \t]*)var _Init = function\([ \t]*\)[ \t]*\r?\n([ \t]*)\{')
        if len(init.findall(source)) != 1:
            raise ValueError('Installed settings tab initialization contract changed')
        source = init.sub(lambda match: match.group(0) + '\n' + match.group(2) + '\t_CS2GCEnsureNewTab();',
                          source, count=1)
    else:
        raise ValueError('Installed settings menu initialization contract changed')
    return source


def wheel_source_root(proxy_directory):
    """The radial wheel ships in the same early-CS2 build as the CS:GO animations, so both use one folder."""
    configured = os.environ.get('CS2GC_BUY_WHEEL_SOURCE')
    if configured:
        return Path(configured).expanduser()
    import native_animations
    return native_animations.source_root(proxy_directory)


# ItemPreviewPanel was removed from the client after the Limited Test; the old layout only uses it for a hidden
# placeholder, and an unknown panel type is a fatal layout error.
WHEEL_PANEL_TYPES = {'ItemPreviewPanel': 'Panel'}


def adapt_wheel_layout(data):
    """Rewrite the Limited Test buymenu layout so the current client can parse it.

    Its compiled tree (LaCo, binary KV3) names includes with a `_c` suffix and uses panel types that no longer
    exist; current layouts reference `.vcss`/`.vts`/`.vjs` and the loader appends `_c` itself."""
    from kv3 import OBJECT, read_kv3, read_resource, write_kv3, write_resource
    version, blocks = read_resource(data)
    layouts = [block for block in blocks if block[0] == 'LaCo']
    if len(layouts) != 1:
        raise ValueError('Compiled buy-wheel layout has no single LaCo layout tree')
    guid, root = read_kv3(layouts[0][1])

    def walk(node):
        if node.type == OBJECT:
            fields = dict(node.value)
            kind, name = fields.get('eType'), fields.get('name')
            if kind is not None and name is not None:
                if kind.value == 'PANEL' and name.value in WHEEL_PANEL_TYPES:
                    name.value = WHEEL_PANEL_TYPES[name.value]
                elif kind.value == 'REFERENCE_COMPILED' and name.value.endswith('_c'):
                    name.value = name.value[:-2]
            for _, child in node.value:
                walk(child)
        elif isinstance(node.value, list):
            for child in node.value:
                walk(child)

    walk(root)
    layouts[0][1] = write_kv3(guid, root)
    return write_resource(version, blocks)


def _validate_wheel_resource(relative, data):
    if len(data) < 16 or len(data) > 8 * 1024 * 1024:
        raise ValueError('Invalid compiled buy-wheel resource size: ' + relative)
    size, header, version, offset, count = struct.unpack_from('<IHHII', data)
    if size != len(data) or header != 12 or version != 3 or not 1 <= count <= 32:
        raise ValueError('Unsupported compiled buy-wheel resource: ' + relative)
    if relative.endswith('.vcss_c'):
        if b'buywheel' not in data.lower() or b'radial-selector' not in data.lower():
            raise ValueError('Compiled stylesheet does not contain the original radial buy-wheel styles')
    elif b'BuyMenu' not in data:
        raise ValueError('Compiled layout does not contain the native BuyMenu panel')


def install_wheel_override(proxy_directory, *, enabled, source_root=None):
    proxy = Path(proxy_directory).resolve()
    game = proxy.parent.parent
    info = game / 'csgo/gameinfo.gi'
    mod = game / WHEEL_FOLDER
    manifest_path = mod / 'cs2_gc_buy_wheel_manifest.json'
    if not info.is_file():
        return 'unavailable: installed gameinfo.gi not found'
    previous = None
    if manifest_path.exists():
        previous = json.loads(read_text(manifest_path))
        if previous.get('owner') != WHEEL_OWNER:
            raise ValueError('Buy-wheel folder is not owned by this feature')
    elif mod.exists() and any(mod.iterdir()):
        raise ValueError('Buy-wheel folder contains unowned files')

    current = read_text(info)
    if not enabled:
        if not previous:
            return 'disabled; current CS2 menu selected'
        mounted = mount_gameinfo(current, False, WHEEL_FOLDER, WHEEL_COMMENT)
        if mounted != current:
            atomic_write(info, mounted)
            return 'disabled; restart CS2 to load the current menu'
        return 'disabled; current CS2 menu selected'

    source_root = Path(source_root) if source_root is not None else wheel_source_root(proxy)
    assets = []
    hashes = {}
    for relative in WHEEL_ASSETS:
        path = source_root / Path(relative)
        if not path.is_file():
            raise FileNotFoundError('Original buy-wheel resource is missing: ' + str(path))
        data = path.read_bytes()
        _validate_wheel_resource(relative, data)
        hashes[relative] = hashlib.sha256(data).hexdigest()
        if relative.endswith('.vxml_c'):
            data = adapt_wheel_layout(data)
        assets.append((relative, data))

    if previous:
        expected = previous.get('outputs_sha256', {})
        for path in mod.glob('pak01_*.vpk'):
            if expected.get(path.name) != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError('Buy-wheel VPK was edited externally; leaving it unchanged')

    mod.mkdir(parents=True, exist_ok=True)
    from vpk_pack import pack
    pack(mod, extra=assets)
    outputs = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in mod.glob('pak01_*.vpk')}
    atomic_write(manifest_path, json.dumps({
        'owner': WHEEL_OWNER,
        'assets_sha256': hashes,
        'outputs_sha256': outputs
    }, indent=2) + '\n')
    mounted = mount_gameinfo(current, True, WHEEL_FOLDER, WHEEL_COMMENT)
    if mounted != current:
        backup = info.with_name(info.name + '.' + WHEEL_FOLDER + '_backup')
        if not backup.exists():
            with backup.open('x', encoding='utf-8', newline='') as output:
                output.write(current)
        atomic_write(info, mounted)
        return 'prepared from supplied wheel resources; restart CS2 to load the buy wheel'
    return 'installed; restart CS2 if it is currently running'


def prepare(directory, config):
    settings = install_override(directory, enabled=False, folder='cs2_gc_newsettings',
                                comment='cs2_gc NEW settings tab', owner='cs2-gc-newsettings-v1',
                                asset='panorama/scripts/settingsmenu.vts_c', patch=patch_settings)
    legacy_hud = install_override(directory, enabled=False, folder='cs2_gc_buymenu',
                                  comment='cs2_gc classic buy menu', owner='cs2-gc-buymenu-v1',
                                  asset='panorama/scripts/hud/hudmoney.vts_c', patch=lambda source: source)
    game = Path(directory).resolve().parents[1]
    values = read_settings(game / 'csgo/cfg')
    # The Limited Test radial wheel's layout loads, but the current client's CSGOBuyMenu code only drives the grid
    # and stops CS2 with a fatal error when the grid panels (e.g. promo-item) are missing. Keep it unmounted.
    wheel = install_wheel_override(directory, enabled=False)
    animations = prepare_animations(directory, values)
    return 'settings: ' + settings + '; custom menu: ' + legacy_hud + '; original wheel: ' + wheel + \
        '; CS:GO animations: ' + animations


def prepare_animations(directory, values):
    import native_animations
    enabled = values.get('ui_cs2gc_animations', DEFAULTS['ui_cs2gc_animations']) == 'csgo'
    try:
        return native_animations.install(directory, enabled=enabled,
                                         log=lambda message: print('CS:GO animations: ' + message, flush=True))
    except (OSError, ValueError, KeyError, IndexError, struct.error) as error:
        if not enabled:
            raise
        native_animations.install(directory, enabled=False)
        return 'failed (%s); CS2 animations kept' % error


# ---------------------------------------------------------------- persistence
SETTINGS_CFG = 'cs2_gc_newsettings.cfg'
# ui_cs2gc_whatsnew only accepts this release's id: an older id is dropped, so the window shows after an update.
ALLOWED = {'ui_low_end_pc': ('0', '1'), 'ui_cs2gc_buymenu': ('cs2', 'csgo'), 'ui_cs2gc_animations': ('cs2', 'csgo'),
           'ui_cs2gc_whatsnew': ('0', WHATS_NEW_SEEN), 'ui_cs2gc_smoke': ('0', '1')}
LEGACY_KEYS = ('ui_cs2gc_buymenu', 'ui_low_end_pc')  # the only keys files from before the animation toggle hold
LINE = re.compile(rb'CS2GC_SETTING (' + b'|'.join(re.escape(key.encode()) for key in sorted(ALLOWED)) + rb') (\w+)')


def settings_cfg(values, *, graphics=LOW_END, keys=None):
    lines = ['// CS2 GC NEW settings (written by the rewards helper from in-game choices).']
    for key in sorted(keys or ALLOWED):
        lines.append('setinfo %s %s' % (key, values.get(key, DEFAULTS[key])))
    if values.get('ui_low_end_pc', DEFAULTS['ui_low_end_pc']) == '1':
        lines += ['%s %s' % (name, low) for name, low, _ in graphics
                  if name not in ('fps_max', 'fps_max_ui')]
    lines += ['%s %s' % limit for limit in DEFAULT_FRAME_LIMITS]
    return '\n'.join(lines) + '\n'


def _legacy_settings_cfg(values, *, graphics, keys):
    lines = ['// CS2 GC NEW settings (written by the rewards helper from in-game choices).']
    for key in sorted(keys):
        lines.append('setinfo %s %s' % (key, values.get(key, DEFAULTS[key])))
    if values.get('ui_low_end_pc', DEFAULTS['ui_low_end_pc']) == '1':
        lines += ['%s %s' % (name, low) for name, low, _ in graphics]
    return '\n'.join(lines) + '\n'


def ensure_settings_cfg(cfg_dir):
    path = Path(cfg_dir) / SETTINGS_CFG
    if path.exists():
        original = read_text(path)
        current = re.sub(r'(?m)^[ \t]*setinfo[ \t]+ui_cs2gc_deathcam[ \t]+[01][ \t]*\r?(?:\n|$)', '', original)
        if current != original:
            atomic_write(path, current)
        values = read_settings(cfg_dir)
        previous = re.sub(r'(?m)^setinfo ui_cs2gc_whatsnew \w+$',
                          'setinfo ui_cs2gc_whatsnew ' + values.get('ui_cs2gc_whatsnew', '0'),
                          current.replace('\r\n', '\n'))
        if previous == settings_cfg(values, graphics=PREVIOUS_LOW_END, keys=PREVIOUS_KEYS):
            backup = path.with_suffix(path.suffix + '.pre-graphics-refresh.bak')
            if not backup.exists():
                atomic_write(backup, current)
            atomic_write(path, settings_cfg(values))
            return 'owned graphics preset refreshed with backup'
        previous_presets = (LEGACY_LOW_END, PREVIOUS_LOW_END, LOW_END, PREVIOUS_FRAME_LIMITS)
        legacy = {
            _legacy_settings_cfg(values, graphics=graphics, keys=keys)
            for graphics in previous_presets
            for keys in (ALLOWED, PREVIOUS_KEYS, LEGACY_KEYS)
        }
        if current.replace('\r\n', '\n') in legacy:
            migrated = dict(values, ui_low_end_pc='0')
            backup = path.with_suffix(path.suffix + '.pre-balanced.bak')
            if not backup.exists():
                atomic_write(backup, current)
            atomic_write(path, settings_cfg(migrated))
            return 'legacy performance preset backed up; low-end graphics defaulted off'
        configured_limits = {
            match.group(1).lower()
            for match in re.finditer(r'(?im)^\s*(fps_max(?:_ui)?)\s+\S+', current)
        }
        missing_limits = [limit for limit in DEFAULT_FRAME_LIMITS if limit[0] not in configured_limits]
        missing_gameplay = [key for key in ('ui_cs2gc_smoke',)
                            if not re.search(r'(?m)^\s*setinfo\s+' + key + r'\s+', current)]
        if missing_limits or missing_gameplay:
            contents = current.rstrip('\r\n')
            if contents:
                contents += '\n'
            contents += '\n'.join('%s %s' % limit for limit in missing_limits) + '\n'
            contents += ''.join('setinfo %s 0\n' % key for key in missing_gameplay)
            atomic_write(path, contents)
            return 'saved settings preserved; default frame limits added' if missing_limits else 'saved settings preserved; gameplay defaults added'
        return 'obsolete death-view toggle removed; other saved settings preserved' if current != original else 'saved settings preserved'
    atomic_write(path, settings_cfg(DEFAULTS))
    return 'balanced frame-limit defaults created'


def read_settings(cfg_dir):
    path = Path(cfg_dir) / SETTINGS_CFG
    values = {}
    if path.is_file():
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] == 'setinfo' and parts[1] in ALLOWED and parts[2] in ALLOWED[parts[1]]:
                values[parts[1]] = parts[2]
    return values


class NewSettingsBridge:
    """Persist NEW-tab choices printed to console.log (-condebug) into cs2_gc_newsettings.cfg."""

    def __init__(self, cfg_dir):
        self.cfg_dir = Path(cfg_dir)
        self.log = console_log_path(self.cfg_dir)
        self.position = self.log.stat().st_size if self.log.exists() else 0
        self.pending = b''
        self.values = dict(DEFAULTS)
        self.values.update(read_settings(self.cfg_dir))
        if not (self.cfg_dir / SETTINGS_CFG).is_file():
            atomic_write(self.cfg_dir / SETTINGS_CFG, settings_cfg(self.values))

    def consume(self, data):
        lines = (self.pending + data).split(b'\n')
        self.pending = lines.pop()[-4096:]
        changed = False
        for line in lines:
            for key, value in LINE.findall(line):
                key, value = key.decode(), value.decode()
                if value in ALLOWED[key] and self.values.get(key) != value:
                    self.values[key] = value
                    changed = True
        if changed:
            path = self.cfg_dir / SETTINGS_CFG
            contents = settings_cfg(self.values)
            for name, value in re.findall(r'(?im)^\s*(fps_max(?:_ui)?)\s+(\d+(?:\.\d+)?)\s*$', read_text(path)):
                contents = re.sub(r'(?m)^' + name.lower() + r' \S+$', name.lower() + ' ' + value, contents)
            atomic_write(path, contents)
        return changed

    def poll(self):
        if not self.log.exists():
            return False
        size = self.log.stat().st_size
        if size < self.position:
            self.position = 0
            self.pending = b''
        with self.log.open('rb') as source:
            source.seek(self.position)
            data = source.read(1024 * 1024)
            self.position = source.tell()
        return self.consume(data)
