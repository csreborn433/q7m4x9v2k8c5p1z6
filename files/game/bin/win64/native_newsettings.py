"""Persist NEW choices and prepare opt-in native UI/animation overrides."""
from pathlib import Path
import json
import re
import struct

from native_resources import console_log_path, install_override, mount_gameinfo, read_text
from native_beta_buy import remove as remove_beta_buy
from native_beta_buy import remove_classic
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
# Migration fingerprints only. A console variable existing isn't proof it is writable in retail.
OLD_WORLD_DETAIL = [('r_particle_max_detail_level', '0', '3'), ('r_particle_shadows', '0', '1'),
           ('r_propsmaxdist', '100', '1200'), ('r_csgo_cmaa_quality', '0', '3'),
           ('r_texturefilteringquality', '0', '1'), ('r_texture_stream_max_resolution', '512', '2048'),
           ('r_csgo_enable_volume_fog', '0', '1'), ('r_csgo_enable_cubemap_fog', '0', '1'),
           ('r_csgo_enable_gradient_fog', '0', '1'), ('r_csgo_microshadowing', '0', '1'),
           ('r_csgo_smoke_shadow', '0', '1'), ('r_csgo_mixed_resolution_particles', '1', '1'),
           ('cl_ragdoll_limit', '8', '20')]
# Archived client controls, not developmentonly/cheat/replicated. World quality is selected
# through CSGOPresetChanged on Video; don't issue internal implementation cvars from a cfg.
LOW_END = [('cl_ragdoll_limit', '0', '20'), ('r_drawtracers_firstperson', '0', '1'),
           ('cl_allow_animated_avatars', '0', '1')]
PREVIOUS_FRAME_LIMITS = [('fps_max', '400', '400'), ('fps_max_ui', '60', '120')]
DEFAULT_FRAME_LIMITS = [('fps_max', '222'), ('fps_max_ui', '99')]
LOW_END_JS = '[' + ','.join("['%s','%s','%s']" % row for row in LOW_END) + ']'
RESTORE_KEY = 'ui_cs2gc_lowend_restore'
RESTORE_VALUE = r'(?:-1|0|[1-9]\d{0,8})_[01]_[01]'
LOW_END_TOGGLE_JS = """
    const csLowEnd = __LOWEND__;
    let csLowEndBefore = GameInterfaceAPI.GetSettingString('__KEY__');
    function csToggleGraphics(on) {
        const read = key => {
            const value = GameInterfaceAPI.GetSettingString(key);
            return value === 'true' ? '1' : value === 'false' ? '0' : value;
        };
        if (on) {
            const before = csLowEnd.map(row => read(row[0])).join('_');
            if (/^__RESTORE__$/.test(before)) {
                csLowEndBefore = before;
                $.Msg('CS2GC_GRAPHICS_BASELINE ' + before);
            }
        }
        const before = /^__RESTORE__$/.test(csLowEndBefore) ? csLowEndBefore.split('_') : [];
        csLowEnd.forEach(([name,low,normal],i) => {
            if (on || read(name) === low) GameInterfaceAPI.SetSettingString(name, on ? low : before[i] || normal);
        });
    }
""".replace('__LOWEND__', LOW_END_JS).replace('__RESTORE__', RESTORE_VALUE).replace('__KEY__', RESTORE_KEY)
DEFAULTS = {'ui_low_end_pc': '0', 'ui_cs2gc_buymenu': 'cs2', 'ui_cs2gc_animations': 'cs2',
            'ui_cs2gc_whatsnew': '0', 'ui_cs2gc_smoke': '0', 'ui_cs2gc_controls_v1': '0', 'ui_cs2gc_home_v1': '0'}
PREVIOUS_KEYS = tuple(key for key in DEFAULTS if key not in ('ui_cs2gc_smoke', 'ui_cs2gc_controls_v1', 'ui_cs2gc_home_v1'))
WHEEL_FOLDER = 'cs2_gc_buymenu_wheel'
WHEEL_COMMENT = 'cs2_gc original buy wheel'
WHEEL_OWNER = 'cs2-gc-original-buy-wheel-v1'

# ---------------------------------------------------------------- settings menu
TABINFO_ANCHOR = '        CrosshairSettings: {'
LOAD_ANCHOR = "            newPanel.BLoadLayout('file://{resources}/layout/settings/' + XmlName + '.xml', false, false);"
CHECK_ANCHOR = '            $("#" + TabInfo[tabID].radioid).checked = true;'
INIT_ANCHOR = '    function _Init() {'

SETTINGS_SCRIPT = r'''
    // cs2_gc: NEW settings tab using native Settings controls.
    __GRAPHICS__
    function _CS2GCSetting(key,value){
        GameInterfaceAPI.SetSettingString(key,value);
        $.Msg('CS2GC_SETTING '+key+' '+value);
    }
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
        _CS2GCSection(content,'MAX PERFORMANCE','Disables retained ragdolls, first-person tracers and animated avatars. Frame limits are unchanged.');
        _CS2GCChoiceRow(content,[
            ['OFF',!lowOn,()=>{if(lowOn)csToggleGraphics(false);_CS2GCSetting('ui_low_end_pc','0');_CS2GCBuildNewSettings(panel);}],
            ['ON',lowOn,()=>{if(!lowOn)csToggleGraphics(true);_CS2GCSetting('ui_low_end_pc','1');_CS2GCBuildNewSettings(panel);}]
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
'''.replace('__GRAPHICS__', LOW_END_TOGGLE_JS)


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
        source = source.replace(INIT_ANCHOR, SETTINGS_SCRIPT +
                                INIT_ANCHOR + '\n        _CS2GCEnsureNewTab();', 1)
        if source.count(CHECK_ANCHOR) == 1:
            source = source.replace(CHECK_ANCHOR, '            const _cs2gcRadio = $("#CS2GCNewRadio");\n'
                                '            if (_cs2gcRadio) _cs2gcRadio.checked = tabID === "NewSettings";\n'
                                '            if ($("#" + TabInfo[tabID].radioid)) $("#" + TabInfo[tabID].radioid).checked = true;', 1)
    elif source.count('var _NavigateToTab = function') == 1 and source.count('SettingsMenu.Init();') == 1:
        source = source.replace('var _NavigateToTab = function', SETTINGS_SCRIPT +
                                '\n    var _NavigateToTab = function', 1)
        init = re.compile(r'(?m)^([ \t]*)var _Init = function\([ \t]*\)[ \t]*\r?\n([ \t]*)\{')
        if len(init.findall(source)) != 1:
            raise ValueError('Installed settings tab initialization contract changed')
        source = init.sub(lambda match: match.group(0) + '\n' + match.group(2) + '\t_CS2GCEnsureNewTab();',
                          source, count=1)
    else:
        raise ValueError('Installed settings menu initialization contract changed')
    return source


def disable_legacy_wheel(proxy_directory):
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
    if not previous:
        return 'disabled'
    mounted = mount_gameinfo(current, False, WHEEL_FOLDER, WHEEL_COMMENT)
    if mounted != current:
        atomic_write(info, mounted)
    return 'disabled'


def prepare(directory, config):
    settings = install_override(directory, enabled=False, folder='cs2_gc_newsettings',
                                comment='cs2_gc NEW settings tab', owner='cs2-gc-newsettings-v1',
                                asset='panorama/scripts/settingsmenu.vts_c', patch=patch_settings)
    legacy_hud = install_override(directory, enabled=False, folder='cs2_gc_buymenu',
                                  comment='cs2_gc classic buy menu', owner='cs2-gc-buymenu-v1',
                                  asset='panorama/scripts/hud/hudmoney.vts_c', patch=lambda source: source)
    game = Path(directory).resolve().parents[1]
    values = read_settings(game / 'csgo/cfg')
    wheel = disable_legacy_wheel(directory)
    beta_buy = remove_beta_buy(directory)
    classic = remove_classic(directory)
    animations = prepare_animations(directory, values)
    return 'settings: ' + settings + '; custom menu: ' + legacy_hud + '; original wheel: ' + wheel + \
        '; beta buy HUD removed: ' + beta_buy + '; classic wheel: ' + classic + '; CS:GO animations: ' + animations


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
ALLOWED = {'ui_low_end_pc': ('0', '1'), 'ui_cs2gc_buymenu': ('cs2', 'csgo', 'beta'), 'ui_cs2gc_animations': ('cs2', 'csgo'),
           'ui_cs2gc_whatsnew': ('0', WHATS_NEW_SEEN), 'ui_cs2gc_smoke': ('0', '1'), 'ui_cs2gc_controls_v1': ('1', '0'),
           'ui_cs2gc_home_v1': ('1', '0')}
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
        release_keys = tuple(k for k in ALLOWED if k != 'ui_cs2gc_home_v1')
        old_detail = [settings_cfg(values, graphics=OLD_WORLD_DETAIL, keys=keys) for keys in (release_keys, ALLOWED)]
        # Slider-adjusted frame limits still identify an owned file; compare the entire
        # remainder, never treating arbitrary user cfg commands as a migration template.
        limit_line = r'(?m)^(fps_max(?:_ui)?) (\d+(?:\.\d+)?)$'
        frame_defaults = dict(DEFAULT_FRAME_LIMITS)
        with_default_limits = re.sub(limit_line, lambda m: m[1] + ' ' + frame_defaults[m[1]], previous)
        retire_detail = values.get('ui_low_end_pc') == '1' and with_default_limits in old_detail
        if retire_detail or previous == settings_cfg(values, graphics=PREVIOUS_LOW_END, keys=PREVIOUS_KEYS):
            backup = path.with_suffix(path.suffix + ('.pre-retail-graphics.bak' if retire_detail else '.pre-graphics-refresh.bak'))
            if not backup.exists():
                atomic_write(backup, current)
            limits = dict(re.findall(limit_line, previous))
            atomic_write(path, re.sub(limit_line, lambda m: m[1] + ' ' + limits[m[1]], settings_cfg(values)))
            return 'owned graphics preset refreshed with backup'
        previous_presets = (LEGACY_LOW_END, PREVIOUS_LOW_END, OLD_WORLD_DETAIL, LOW_END, PREVIOUS_FRAME_LIMITS)
        legacy = {
            _legacy_settings_cfg(values, graphics=graphics, keys=keys)
            for graphics in previous_presets
            for keys in (ALLOWED, tuple(k for k in ALLOWED if k != 'ui_cs2gc_controls_v1'), PREVIOUS_KEYS, LEGACY_KEYS)
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
        missing_gameplay = [key for key in ('ui_cs2gc_smoke', 'ui_cs2gc_controls_v1', 'ui_cs2gc_home_v1')
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
        self.graphics_baseline = ''
        self.values = dict(DEFAULTS)
        self.values.update(read_settings(self.cfg_dir))
        if not (self.cfg_dir / SETTINGS_CFG).is_file():
            atomic_write(self.cfg_dir / SETTINGS_CFG, settings_cfg(self.values))
        else:
            match = re.search(r'(?m)^setinfo ' + RESTORE_KEY + ' (' + RESTORE_VALUE + ')$',
                              read_text(self.cfg_dir / SETTINGS_CFG).replace('\r\n', '\n'))
            if match:
                self.graphics_baseline = match[1]

    def consume(self, data):
        lines = (self.pending + data).split(b'\n')
        self.pending = lines.pop()[-4096:]
        changed = set()
        caps = ()
        for line in lines:
            baseline = re.search(rb'\bCS2GC_GRAPHICS_BASELINE (' + RESTORE_VALUE.encode() + rb')\s*$', line)
            if baseline:
                self.graphics_baseline = baseline[1].decode()
            sliders = re.search(rb'\bCS2GC_VIDEO_FPS (\d{1,4}) (\d{1,4})\s*$', line)
            if sliders and all(int(v) <= 1000 for v in sliders.groups()):
                caps = tuple(int(v) for v in sliders.groups())
            for key, value in LINE.findall(line):
                key, value = key.decode(), value.decode()
                if key in ('ui_cs2gc_controls_v1','ui_cs2gc_home_v1') and value != '1':
                    continue
                if value in ALLOWED[key] and self.values.get(key) != value:
                    self.values[key] = value
                    changed.add(key)
        path = self.cfg_dir / SETTINGS_CFG
        caps_changed = False
        if caps:
            original = contents = read_text(path)
            for name, cap in zip(('fps_max', 'fps_max_ui'), caps):
                contents, count = re.subn(r'(?im)^([ \t]*' + name + r'[ \t]+)\d+(?:\.\d+)?\b',
                                          r'\g<1>' + str(cap), contents)
                if not count:
                    contents = contents.rstrip('\r\n') + '\n%s %d\n' % (name, cap)
            caps_changed = contents != original
            if caps_changed:
                atomic_write(path, contents)
        if changed:
            if changed <= {'ui_cs2gc_controls_v1','ui_cs2gc_home_v1'}:
                contents = read_text(path)
                for key in sorted(changed):
                    contents, count = re.subn(r'(?m)^([ \t]*setinfo[ \t]+' + key + r'[ \t]+)\w+', r'\g<1>1', contents)
                    if not count:
                        contents = contents.rstrip('\r\n') + '\nsetinfo ' + key + ' 1\n'
                atomic_write(path, contents)
                return True
            contents = settings_cfg(self.values)
            if self.values['ui_low_end_pc'] == '1' and self.graphics_baseline:
                contents += 'setinfo %s %s\n' % (RESTORE_KEY, self.graphics_baseline)
            for name, value in re.findall(r'(?im)^\s*(fps_max(?:_ui)?)\s+(\d+(?:\.\d+)?)\s*$', read_text(path)):
                contents = re.sub(r'(?m)^' + name.lower() + r' \S+$', name.lower() + ' ' + value, contents)
            atomic_write(path, contents)
        return bool(changed) or caps_changed

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
