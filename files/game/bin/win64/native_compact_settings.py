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
        edge = find(root, 'onactivate', 'SettingsMenuVideo.ShowHudEdgePositions();')
        parent, = (n for n in walk(root) if edge in panels(n))
        set_panels(parent, [p for p in panels(parent) if p is not edge])
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


def menu_navigation(source):
    source = _replace(source, '        _LoadTab(tab, XmlName, setActiveSection);', """        _LoadTab(tab, XmlName, setActiveSection);
        if (tab === 'JsSettings')
            $.GetContextPanel().FindChildInLayoutFile(tab).SetAttributeString('set-active-section', setActiveSection);""")
    return _replace(source, '    function _OnShowMainMenu() {', """    function _OnShowMainMenu() {
        $('#MainMenuNavBarWatch').GetChild(0).SetImage('file://{images}/cs2_gc/new_settings.png');""")


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
    png = Path(__file__).with_name('ui_assets') / 'new_settings.png'
    result.append((ICON, make_vtex(index.read('panorama/images/econ/weapon_cases/crate_operation_ii_png.vtex_c'), png.read_bytes())))
    return result
