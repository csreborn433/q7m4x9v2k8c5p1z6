"""Build an original radial buy board from the supported client's own layout.

No substitute buttons: each spoke contains its real category, including its
loadout, keyboard selection and native buy/donate/refund handlers. The promo
slot occupies the hub. Preparation needs no Limited Test files.
"""
import hashlib
from pathlib import Path

from kv3 import ARRAY, OBJECT, STRING, Node, read_kv3, read_resource, write_kv3, write_resource
from native_resources import install_override
from vpk_pack import KILL_SWITCH

ASSET = 'panorama/layout/buymenu.vxml_c'
FOLDER = 'cs2_gc_beta_buy'
# Compiled layout of client 2000933. Never guess the native control contract.
LAYOUT_SHA256 = '57260ee09bf092a96270b3384bf615bf46611076cebcef24f11235cf40069623'

# Clockwise from twelve o'clock, in the same order as the native number keys.
SPOKES = ((337, 4), (658, 72), (594, 312), (80, 312), (16, 72))

CLASS_STYLES = {
    'buymenu-body': 'height: 552px;',
    'buymenu__categories__container': 'flow-children: none; height: 100%;',
    'buy-wheel-background': (
        'background-img-opacity: 0; background-color: gradient(radial, 50% 50%, 0% 0%, 50% 50%, '
        'from(#17222aef), color-stop(0.25, #17222aef), color-stop(0.26, #cdab70), '
        'color-stop(0.28, #1e2e37ee), color-stop(0.76, #17242bee), color-stop(0.77, #54636cff), '
        'color-stop(0.79, #17242be0), to(#10171bcc)); border-radius: 22px;'),
    'buymenu__category__column': 'padding: 0px 4px;',
    'buymenu__category__column__header': (
        'height: 28px; margin-bottom: 2px; background-color: #1a272ff5; border-top: 2px solid #cda66c;'),
    'buymenu__category__column__label': 'font-size: 20px; vertical-align: center;',
    'buymenu__category__column__keylabel': 'margin-left: 8px;',
    # Five full rows fit; a mode with additional items remains scrollable.
    'buymenu__category__itembuttons': 'max-height: 209px; overflow: clip scroll;',
    'button-container': 'height: 39px; margin-bottom: 2px; background-color: #172028df;',
    'buywheel-item__icon': 'horizontal-align: left; margin-left: 23px; height: 25px; width: 43px;',
    'buywheel-item__name': ('horizontal-align: left; vertical-align: center; margin-left: 71px; '
                            'width: 46%; text-align: left; text-overflow: shrink;'),
}
ID_STYLES = {
    'CategoryContainer' + str(i): f'width: 276px; position: {x}px {y}px 0px;'
    for i, (x, y) in enumerate(SPOKES, 1)
}
ID_STYLES['CategoryContainerPromo'] = (
    'width: 255px; horizontal-align: left; vertical-align: top; position: 348px 251px 0px;')


def _children(node):
    # LaCo stores one child inline, but multiple children in an array.
    children, child = node.get('vecChildren'), node.get('child')
    return children.value if children is not None else [child] if child is not None else []


def _name(node, field='name'):
    value = node.get(field)
    return value.value if value is not None else ''


def _add_style(panel, style):
    value = Node(OBJECT, [('eType', Node(STRING, 'PANEL_ATTRIBUTE_VALUE')), ('name', Node(STRING, style))])
    attribute = Node(OBJECT, [('eType', Node(STRING, 'PANEL_ATTRIBUTE')), ('name', Node(STRING, 'style')),
                              ('child', value)])
    children = panel.get('vecChildren')
    if children is None:
        existing = _children(panel)
        panel.value[:] = [(k, v) for k, v in panel.value if k != 'child']
        children = Node(ARRAY, existing)
        panel.value.append(('vecChildren', children))
    children.value.insert(0, attribute)


def patch_layout(resource):
    if hashlib.sha256(resource).hexdigest() != LAYOUT_SHA256:
        raise ValueError('unsupported buy layout (expected client 2000933)')
    version, blocks = read_resource(resource)
    layout, = (b for b in blocks if b[0] == 'LaCo')
    guid, root = read_kv3(layout[1])

    def visit(node):
        children = _children(node)
        if _name(node, 'eType') == 'PANEL':
            attrs = {_name(k): _name(k.get('child')) for k in children if _name(k, 'eType') == 'PANEL_ATTRIBUTE'}
            # Prefer the specific promo rule over its ordinary column class.
            style = ID_STYLES.get(attrs.get('id')) or next(
                (CLASS_STYLES[c] for c in attrs.get('class', '').split() if c in CLASS_STYLES), None)
            if style:
                if 'style' in attrs:
                    raise ValueError('unexpected inline style on buy control')
                _add_style(node, style)
        for child in children:
            if _name(child, 'eType') != 'PANEL_ATTRIBUTE':
                visit(child)

    visit(root.get('m_AST').get('m_pRoot'))
    layout[1] = write_kv3(guid, root)
    return write_resource(version, blocks)


def prepare(directory, values):
    def install(enabled):
        return install_override(directory, enabled=enabled, folder=FOLDER, comment='cs2_gc beta buy HUD',
                                owner='cs2-gc-beta-buy-v1', asset=ASSET, patch=patch_layout, compiled_layout=True)

    if values.get('ui_cs2gc_buymenu') != 'beta' or (Path(directory) / KILL_SWITCH).exists():
        return install(False)
    try:
        status = install(True)
        if not status.startswith('unavailable:'):
            return status
    except (ValueError, OSError) as error:
        status = str(error)
    # On a client update, never leave the previous build's layout mounted.
    return status + '; stock buy HUD: ' + install(False)
