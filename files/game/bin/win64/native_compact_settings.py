"""Build the ordinary Settings pages from the local client's native controls."""
import hashlib
from pathlib import Path

import kv3
from native_resources import rewrite_script
from native_presentation import _replace

LAYOUTS = {
    'settings': '0e5d5a5bca77bd4294fb20d0ecff7806a470c9bb46d5f10f9b7699918e4512f4',
    'settings_game': '79c3d4d79fcaa6c2a4aa42c4c9659118430ceb0c11c71771d97f2ab338f0d40d',
    'settings_video': '5a083ebabd37351e58208bf036dd66fde8b1f35513c121257b188838d145be0e',
}
ICON = 'panorama/images/cs2_gc/new_settings_png.vtex_c'
VIDEO_SCRIPTS = {
    'settingsmenu_video': '785b25b6f4e6a8035ea0393aa84592c0c6491a7d4a1822b432d9536b0a16d825',
    'settingsmenu_shared': '74363c09f3a4bbfb611178fb629e69443d0172c24f4bbd0ed8c6dcaa5833f0b4',
    'video_setting_recommendations': '6a2bb945c001c0e29d07da3e7c3db50e9fbdfc6d83dda79deba1d3204270ae71',
}


def value(node, key):
    v = node.get(key)
    return v.value if v is not None else ''


def children(node):
    vec = node.get('vecChildren')
    child = node.get('child')
    return vec.value if vec is not None else [child] if child is not None else []


def panels(node):
    return [c for c in children(node) if value(c, 'eType') == 'PANEL']


def attrs(node):
    return {value(a, 'name'): value(a.get('child'), 'name') for a in children(node)
            if value(a, 'eType') == 'PANEL_ATTRIBUTE'}


def walk(node):
    yield node
    for child in children(node):
        yield from walk(child)


def find(node, key, target):
    matches = [p for p in walk(node) if value(p, 'eType') == 'PANEL' and attrs(p).get(key) == target]
    if len(matches) != 1:
        raise ValueError('Expected one settings control: ' + target)
    return matches[0]


def set_panels(node, items):
    kept = [c for c in children(node) if value(c, 'eType') != 'PANEL']
    node.value[:] = [(k, v) for k, v in node.value if k not in ('child', 'vecChildren')]
    node.value.append(('vecChildren', kv3.Node(kv3.ARRAY, kept + list(items))))


def element(kind, name, **fields):
    return kv3.Node(kv3.OBJECT, [('eType', kv3.Node(kv3.STRING, kind)),
                                 ('name', kv3.Node(kv3.STRING, name)), *fields.items()])


def panel(kind, attributes, *items):
    attributes = [element('PANEL_ATTRIBUTE', k, child=element('PANEL_ATTRIBUTE_VALUE', v))
                  for k, v in attributes.items()]
    return element('PANEL', kind, vecChildren=kv3.Node(kv3.ARRAY, attributes + list(items)))


def section(identity, title, *items):
    return panel('Panel', {'id': identity, 'class': 'SettingsBackground'},
                 panel('Label', {'class': 'SettingsSectionTitleLabel', 'text': title}),
                 panel('Panel', {'class': 'top-bottom-flow full-width'}, *items))


def preview():
    def shape(identity, style):
        return panel('Panel', {'id': identity, 'style': style})
    plan = panel('Panel', {'id': 'CsRadarMap', 'style': 'align:center center;width:172px;height:172px;'},
                 shape('LaneA', 'position:15px 19px 0px;width:80px;height:70px;border:4px solid #9aa6a7;'),
                 shape('LaneB', 'position:92px 85px 0px;width:65px;height:59px;border:4px solid #9aa6a7;'),
                 shape('Mid', 'position:48px 80px 0px;width:54px;height:29px;border:3px solid #687e81;'),
                 panel('Label', {'text': 'A', 'style': 'position:36px 35px 0px;color:#e8c876;'}),
                 panel('Label', {'text': 'B', 'style': 'position:112px 100px 0px;color:#e8c876;'}),
                 shape('Teammate', 'position:125px 84px 0px;width:7px;height:7px;background-color:#80cced;'))
    return panel('Panel', {'style': 'height:215px;width:100%;'},
                 panel('Panel', {'id': 'CsRadarFrame', 'style': 'align:center center;border-radius:50%;'
                                 'overflow:clip;border:2px solid #809092;'},
                       shape('CsRadarGround', 'width:100%;height:100%;background-color:#141f25;'),
                       plan, shape('Player', 'align:center center;width:8px;height:8px;background-color:white;')))


def game_page(root, config):
    def slider(c, title, low, high, precision):
        return panel('Panel', {'class': 'SettingsMenuDropdownContainer'}, panel('CSGOSettingsSlider', {
            'text': title, 'convar': c, 'min': f'{low:g}', 'max': f'{high:g}', 'displayprecision': str(precision)}))

    scale = config['viewmodel_range_percent'] / 100
    low, high = config['viewmodel_fov_min'], config['viewmodel_fov_max']
    if low > high:  # The runtime leaves all four native limits unchanged in this case.
        scale, low, high = 1, 60, 68
    vm = section('CsViewmodel', 'Viewmodel',
                 *([slider('viewmodel_fov', 'Field of view', low, high, 0)] if low < high else []),
                 slider('viewmodel_offset_x', 'Left / right', -2*scale, 2.5*scale, 2),
                 slider('viewmodel_offset_y', 'Near / far', -2*scale, 2*scale, 2),
                 slider('viewmodel_offset_z', 'Down / up', -2*scale, 2*scale, 2),
                 find(root, 'id', 'PreferredHandedness'))
    radar = section('SettingsRadarSettings', 'Radar',
                    preview(), *(panel('Panel', {'class': 'SettingsMenuDropdownContainer'}, find(root, 'convar', c))
                                 for c in ('cl_hud_radar_scale', 'cl_radar_scale', 'cl_hud_radar_background_alpha')))
    general = section('CsControls', 'Controls', find(root, 'id', 'enableconsoledropdown-container'),
                      find(root, 'id', 'enableconsoledropdowncmdline-container'))
    nav = find(root, 'id', 'SettingsMenuJumpButtons')
    set_panels(nav, [panel('RadioButton', {'class': 'content-navbar__tabs__btn', 'group': 'SettingsGame',
                       'onactivate': f"SettingsMenuShared.ScrollToId('{attrs(s)['id']}')"},
                      panel('Label', {'text': title})) for s, title in ((vm,'Viewmodel'), (radar,'Radar'), (general,'Controls'))])
    set_panels(find(root, 'id', 'SettingsMenuTabContent'), [vm, radar, general])


def set_attr(node, key, new_value):
    for child in children(node):
        if value(child, 'eType') == 'PANEL_ATTRIBUTE' and value(child, 'name') == key:
            child.get('child').get('name').value = new_value
            return
    node.get('vecChildren').value.insert(0, element('PANEL_ATTRIBUTE', key,
                                        child=element('PANEL_ATTRIBUTE_VALUE', new_value)))


def video_page(root):
    advanced = find(root, 'id', 'advanced_video')

    def parent_panel(container, child):
        for candidate in walk(container):
            if child in panels(candidate):
                return candidate
        raise ValueError('Expected settings control parent')

    preview = find(advanced, 'id', 'VSMapPreviewPanel')
    columns = parent_panel(advanced, preview)
    set_attr(preview, 'visible', 'false')
    settings = next(p for p in panels(columns) if p is not preview)
    style = attrs(settings).get('style', '')
    if 'width: 50%;' not in style:
        raise ValueError('Installed advanced video column contract changed')
    set_attr(settings, 'style', style.replace('width: 50%;', 'width: 100%;', 1))

    magnification_controls = parent_panel(advanced, find(advanced, 'id', 'MagnificationSlider'))
    set_attr(magnification_controls, 'visible', 'false')

    contrast = find(advanced, 'id', 'PlayerContrast')
    set_attr(parent_panel(advanced, contrast), 'visible', 'false')
    set_attr(find(advanced, 'id', 'VSyncPanel'), 'visible', 'false')

    presets = find(advanced, 'id', 'Presets')
    options = panels(presets)
    expected = ['presetlevel0', 'presetlevel1', 'presetlevel2', 'presetlevel3', 'presetlevel4']
    if [attrs(option).get('id') for option in options] != expected:
        raise ValueError('Installed video preset list contract changed')
    set_panels(presets, options[:4])


def fixed_video_script(source):
    source = _replace(source, '    function SelectSimpleVideoSettings() {', """    function ApplyFixedDefaults() {
        let changed = false;
        for (const [dd, option, setting] of [
            [$('#VSync'), 'vsync0', 'vsync'],
            [$('#PlayerContrast'), 'playercontrastlevel1', '']
        ]) {
            const current = dd && dd.GetSelected();
            if (dd && dd.FindDropDownMenuChild(option) && (!current || current.id !== option)) {
                dd.SetSelected(option);
                $.DispatchEvent('CSGOVideoChanged', setting);
                changed = true;
            }
        }
        if (changed) SettingsMenuShared.VideoSettingsApplyChanges();
    }
    SettingsMenuVideo.ApplyFixedDefaults = ApplyFixedDefaults;
    function SelectSimpleVideoSettings() {""")
    return _replace(source, "        $('#AdvancedVideoSettingsRadio').checked = true;",
                    "        $('#AdvancedVideoSettingsRadio').checked = true;\n        ApplyFixedDefaults();")


def fixed_video_shared_script(source):
    return _replace(source, '        _RefreshControlsRecursive(newTabPanel);', """        _RefreshControlsRecursive(newTabPanel);
        if (newTab == videoSettingsStr && SettingsMenuVideo.ApplyFixedDefaults)
            SettingsMenuVideo.ApplyFixedDefaults();""")


def layout(data, name, config):
    if hashlib.sha256(data).hexdigest() != LAYOUTS[name]:
        raise ValueError('Unsupported ordinary settings layout: ' + name)
    version, blocks = kv3.read_resource(data)
    block, = (b for b in blocks if b[0] == 'LaCo')
    guid, doc = kv3.read_kv3(block[1])
    root = doc.get('m_AST').get('m_pRoot')
    if name == 'settings_game':
        game_page(root, config)
    elif name == 'settings':
        crosshair = find(root, 'id', 'CrosshairRadio')
        nav, = (n for n in walk(root) if crosshair in panels(n))
        set_panels(nav, [find(nav, 'id', k) for k in ('CrosshairRadio','GameRadio','AudioRadio','VideoRadio','KBMouseRadio')])
    else:
        video_page(root)
    block[1] = kv3.write_kv3(guid, doc)
    return kv3.write_resource(version, blocks)


RADAR_JS = """
    let csRadarTimer = null;
    function csStopRadar() {
        if (csRadarTimer !== null) $.CancelScheduled(csRadarTimer);
        csRadarTimer = null;
    }
    function csStartRadar(page) {
        csStopRadar();
        const frame = page.FindChildTraverse('CsRadarFrame'), map = page.FindChildTraverse('CsRadarMap'),
              ground = page.FindChildTraverse('CsRadarGround');
        let last = '';
        function draw() {
            csRadarTimer = null;
            if (!frame.IsValid() || !page.visible || !page.BHasClass('Active')) return;
            const size = Number(GameInterfaceAPI.GetSettingString('cl_hud_radar_scale'));
            const zoom = Number(GameInterfaceAPI.GetSettingString('cl_radar_scale'));
            const alpha = Number(GameInterfaceAPI.GetSettingString('cl_hud_radar_background_alpha'));
            const signature = [size, zoom, alpha].join(':');
            if (signature !== last) {
                frame.style.width = frame.style.height = Math.round(155 * size) + 'px';
                map.style.transform = 'scale3d(' + (2*zoom*size) + ',' + (2*zoom*size) + ',1)';
                ground.style.opacity = String(alpha);
                last = signature;
            }
            csRadarTimer = $.Schedule(0.1, draw);
        }
        draw();
    }
"""


def navigation(source):
    begin = source.index('        else if (PromotedSettingsUtil.GetUnacknowledgedPromotedSettings().length')
    end = source.index('        MyPersonaAPI.RequestAccountPrivacySettings();', begin)
    source = source[:begin] + "        else NavigateToTab('CrosshairSettings');\n" + source[end:]
    source = _replace(source, '    let activeTab;', '    let activeTab;\n' + RADAR_JS)
    source = _replace(source, '    function NavigateToTab(tabID) {',
                      '    function NavigateToTab(tabID) {\n        if (!IsTabId(tabID)) return;')
    source = _replace(source, '            activeTab = tabID;', '            csStopRadar();\n            activeTab = tabID;')
    source = _replace(source, '            SettingsMenuShared.NewTabOpened(activeTab);',
                      "            if (tabID === 'GameSettings') csStartRadar(activePanel);\n"
                      '            SettingsMenuShared.NewTabOpened(activeTab);')
    source = _replace(source, '    function _OnSettingsMenuShown() {\n        SettingsMenuShared.NewTabOpened(activeTab);',
                      """    function _OnSettingsMenuShown() {
        const page = $.GetContextPanel();
        const requested = page.GetAttributeString('set-active-section', '');
        const next = IsTabId(requested) ? requested : 'CrosshairSettings';
        if (activeTab !== next) NavigateToTab(next);
        else {
            if (next === 'GameSettings') csStartRadar(page.FindChildInLayoutFile(next));
            SettingsMenuShared.NewTabOpened(next);
        }
        page.SetAttributeString('set-active-section', '');""")
    source = _replace(source, '    function _OnSettingsMenuHidden() {', '    function _OnSettingsMenuHidden() {\n        csStopRadar();')
    return _replace(source, 'return TabInfo[tabname] != null;', "return tabname !== 'Search' && tabname !== 'Promoted' && TabInfo[tabname] != null;")


def game_script(source):
    if 'function _RefreshDatacentersList()' not in source or 'function _InitGameSettings()' not in source:
        raise ValueError('Unsupported game settings script')
    return """(function () {
        const forced = GameInterfaceAPI.IsConsoleEnabledByCommandLine();
        $('#enableconsoledropdown-container').visible = !forced;
        $('#enableconsoledropdowncmdline-container').visible = forced;
        SettingsMenuShared.ChangeBackground(0);
    })();"""


VIDEO_JS = r"""var SettingsMenuVideo = (() => {
    const aspect = $('#AspectRatioEnum'), res = $('#ResolutionEnum'), hz = $('#RefreshEnum'), ratio = $('#CsRatio');
    const selected = dd => dd.GetSelected();
    const options = dd => dd.AccessDropDownMenu().Children();
    let busy = false, ready = false, groups = new Map(), frameJob = null, lastLimits = '';
    const limits = () => ['fps_max','fps_max_ui'].map(k => {
        const s = GameInterfaceAPI.GetSettingString(k);
        return s == null || s === '' ? NaN : Number(s);
    }).join(' ');
    function recordFrameLimits() {
        if (!ready) return;
        if (frameJob !== null) $.CancelScheduled(frameJob);
        frameJob = $.Schedule(.15, () => {
            frameJob = null;
            const current = limits();
            if (current !== lastLimits && /^\d{1,4} \d{1,4}$/.test(current))
                $.Msg('CS2GC_VIDEO_FPS ' + current);
            lastLimits = current;
        });
    }
    function select(dd, id, event) {
        if (!id || !dd.FindDropDownMenuChild(id)) return false;
        dd.SetSelected(id);
        if (event) $.DispatchEvent(event);
        return selected(dd)?.id === id;
    }
    function dimensions(label) {
        // The native resolution labels/IDs contain WIDTHxHEIGHT, not a stable index across displays.
        for (const str of [label?.text, label?.id]) {
            const m = /(?:^|\D)(\d+)\s*[x×]\s*(\d+)(?:\D|$)/i.exec(str || '');
            if (m && Number(m[1]) && Number(m[2])) return Number(m[1]) + 'x' + Number(m[2]);
        }
        return '';
    }
    function ratioKey(size) {
        const [w,h] = size.split('x').map(Number);
        let a=w, b=h;
        while (b) [a,b]=[b,a%b];
        const key = (w/a) + ':' + (h/a);
        return key === '8:5' ? '16:10' : key;
    }
    function setBucket(id) { return select(aspect, id, 'CSGOAspectRatioSelectionChanged'); }
    function setSize(size) {
        const item = options(res).find(item => dimensions(item) === size);
        return item && select(res, item.id, 'CSGOResolutionSelectionChanged');
    }
    function dirty(enabled = true) {
        $('#BtnApplyVideoSettings').enabled = $('#BtnDiscardVideoSettingChanges').enabled = enabled;
    }
    function refreshRatios() {
        if (busy || !ready) return;
        busy = true;
        try {
            groups = new Map();
            ratio.visible = false;
            aspect.visible = true;
            const oldBucket = selected(aspect)?.id, oldSize = dimensions(selected(res)), oldHz = selected(hz)?.id;
            if (!oldBucket || !oldSize || !aspect.enabled || !res.enabled) return;
            const modes = GameInterfaceAPI.GetAllDisplayModes();
            if (!Array.isArray(modes)) return;
            const supported = new Set(modes.filter(m => Number.isInteger(m?.width) && m.width > 0 &&
                Number.isInteger(m.height) && m.height > 0).map(m => m.width + 'x' + m.height));
            if (!supported.has(oldSize)) return;
            // Enumerate *staged* native lists, then restore pending resolution AND refresh rate.
            // Never apply a mode to discover it. Both lists must agree before we offer a ratio.
            const buckets = options(aspect).map(p => p.id);
            try {
                for (const bucket of buckets) {
                    if (!setBucket(bucket)) continue;
                    for (const option of options(res)) {
                        const size = dimensions(option);
                        if (!supported.has(size)) continue;
                        const key = ratioKey(size);
                        if (!groups.has(key)) groups.set(key, []);
                        groups.get(key).push({bucket, size});
                    }
                }
            } finally {
                setBucket(oldBucket);
                setSize(oldSize);
                select(hz, oldHz, 'CSGOResolutionSelectionChanged');
            }
            const key = ratioKey(oldSize);
            if (!groups.has(key)) return;
            ratio.RemoveAllOptions();
            for (const name of groups.keys()) {
                const label = ['64:27','43:18'].includes(name) ? '21:9 (' + name + ')' : name;
                ratio.AddOption($.CreatePanel('Label', ratio, 'ratio_' + name.replace(':','_'), {text:label}));
            }
            ratio.SetSelected('ratio_' + key.replace(':','_'));
            aspect.visible = false;
            ratio.visible = true;
        } finally { busy = false; }
    }
    function syncRatio() {
        if (busy || !ready) return;
        const size = dimensions(selected(res));
        if (!size || !ratio.visible || !groups.has(ratioKey(size))) { refreshRatios(); return; }
        busy = true;
        try { ratio.SetSelected('ratio_' + ratioKey(size).replace(':','_')); }
        finally { busy = false; }
    }
    function chooseRatio() {
        if (busy || !ratio.visible) return;
        const entries = groups.get(selected(ratio)?.id.replace('ratio_','').replace('_',':'));
        if (!entries?.length) return;
        const oldBucket = selected(aspect)?.id, oldSize = dimensions(selected(res)), oldHz = selected(hz)?.text;
        if (entries.some(e => e.size === oldSize)) return;
        const currentHeight = Number(oldSize.split('x')[1]) || GameInterfaceAPI.GetCurrentDisplayMode()?.height || 0;
        const distance = entry => Math.abs(Number(entry.size.split('x')[1]) - currentHeight);
        let staged = false;
        busy = true;
        try {
            const best = entries.reduce((a,b) => distance(a) <= distance(b) ? a : b);
            if (setBucket(best.bucket) && setSize(best.size)) { staged = true; dirty(); }
            else { setBucket(oldBucket); setSize(oldSize); }
            const rate = options(hz).find(p => p.text === oldHz);
            if (rate) select(hz, rate.id, 'CSGOResolutionSelectionChanged');
        } finally { busy = false; }
        if (staged) syncRatio(); else refreshRatios();
    }
    function defaults() {
        let changed = false;
        for (const [dd, option, setting] of [[$('#VSync'),'vsync0','vsync'],[$('#PlayerContrast'),'playercontrastlevel1','']]) {
            if (selected(dd) && selected(dd).id !== option && select(dd,option)) {
                $.DispatchEvent('CSGOVideoChanged', setting);
                changed = true;
            }
        }
        return changed;
    }
    function syncPreset() {
        const active = selected($('#Presets'))?.id;
        for (let i=0; i<3; ++i) $('#CsPreset'+i).SetHasClass('active', active === 'presetlevel'+i);
    }
    function init() {
        if (!ready) lastLimits = limits();
        ready = true;
        // After stock init, before any user edits: persist a conflicting saved VSync/contrast
        // once. Never apply an unrelated pending display change during ordinary input.
        if (defaults()) SettingsMenuShared.VideoSettingsApplyChanges();
        refreshRatios();
        syncPreset();
    }
    ratio.Data().csVideoInit = init;
    return {
        RefreshRatios: refreshRatios, SyncRatio: syncRatio, ChooseRatio: chooseRatio, RecordFrameLimits: recordFrameLimits,
        ChoosePreset(i) {
            if (![0,1,2].includes(i) || !select($('#Presets'),'presetlevel'+i,'CSGOPresetChanged')) return;
            defaults(); syncPreset(); dirty();
        },
        Apply() { defaults(); SettingsMenuShared.VideoSettingsApplyChanges(); dirty(false); syncPreset(); },
        Discard() {
            SettingsMenuShared.VideoSettingsDiscardAdvanced();
            SettingsMenuShared.VideoSettingsDiscardChanges(); init(); dirty(false);
        },
        Reset() {
            SettingsMenuShared.ResetVideoSettings(); SettingsMenuShared.ResetVideoSettingsAdvanced();
            defaults(); refreshRatios(); syncPreset(); dirty();
        }
    };
})();"""


def shared_video_script(source):
    source = _replace(source, '            gBtnDiscardVideoSettingChanges2.enabled = false;\n            $.DispatchEvent',
                      '            $.DispatchEvent')
    source = _replace(source, '        _RefreshControlsRecursive(newTabPanel);', """        _RefreshControlsRecursive(newTabPanel);
        if (newTab === videoSettingsStr) {
            const ratio = newTabPanel.FindChildInLayoutFile('CsRatio');
            if (ratio && ratio.Data().csVideoInit) ratio.Data().csVideoInit();
        }""")
    return _replace(source, '    function VideoSettingsEnableDiscard() {',
                    '    function VideoSettingsEnableDiscard() {\n        VideoSettingsOnUserInputSubmit();')


def video_recommendations(source):
    # Keep driver, VRR and refresh-rate advice; the removed recommendation re-enables VSync.
    start = source.index('        let lowLatencyType = ')
    end = source.index('        return false;', start)
    return source[:start] + source[end:]


def menu_navigation(source):
    source = _replace(source, '        _LoadTab(tab, XmlName, setActiveSection);', """        _LoadTab(tab, XmlName, setActiveSection);
        if (tab === 'JsSettings')
            $.GetContextPanel().FindChildInLayoutFile(tab).SetAttributeString('set-active-section', setActiveSection);""")
    return _replace(source, '    function _OnShowMainMenu() {', """    function _OnShowMainMenu() {
        // RadioButton prepends its own native child, so look the icon up by class; never block the menu on it.
        const csWatchNav = $('#MainMenuNavBarWatch');
        const csWatchIcon = csWatchNav ? csWatchNav.FindChildrenWithClassTraverse('mainmenu-top-navbar__radio-btn__icon')[0] : null;
        if (csWatchIcon && typeof csWatchIcon.SetImage === 'function')
            csWatchIcon.SetImage('file://{images}/cs2_gc/new_settings.png');""")


def assets(game, config):
    from native_animations import VpkIndex
    from native_finishes import make_vtex
    index = VpkIndex(game / 'csgo/pak01_dir.vpk', prefixes=('panorama/scripts/', 'panorama/layout/settings/',
                                                            'panorama/images/econ/weapon_cases/'))
    result = []
    for name in LAYOUTS:
        path = 'panorama/layout/settings/' + name + '.vxml_c'
        result.append((path, layout(index.read(path), name, config)))
    for name, patch in [('settingsmenu', navigation), ('settingsmenu_gamesettings', game_script)]:
        path = 'panorama/scripts/' + name + '.vts_c'
        result.append((path, rewrite_script(index.read(path), patch)))
    for name, patch in [('settingsmenu_video', fixed_video_script),
                        ('settingsmenu_shared', fixed_video_shared_script),
                        ('video_setting_recommendations', video_recommendations)]:
        path = 'panorama/scripts/' + name + '.vts_c'
        stock = index.read(path)
        if hashlib.sha256(stock).hexdigest() != VIDEO_SCRIPTS[name]:
            raise ValueError('Unsupported video settings script: ' + name)
        result.append((path, rewrite_script(stock, patch)))
    png = Path(__file__).with_name('ui_assets') / 'new_settings.png'
    result.append((ICON, make_vtex(index.read('panorama/images/econ/weapon_cases/crate_operation_ii_png.vtex_c'), png.read_bytes())))
    return result
