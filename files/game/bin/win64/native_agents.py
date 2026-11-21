"""Import the user's compiled anime agents into an owned, standalone native addon.

Source folders remain local inputs; an explicitly supplied owned pack can be
bundled in a local launcher. Original game models, materials, items and saved
glove selections are not replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import zlib

import kv3
from inventory_item import as_dict, collect, parse
from native_finishes import Source, _block, make_vtex
from native_tradeups import atomic_write, digest, mount_gameinfo, parse as spans, read_text

FOLDER = 'cs2_gc_anime_agents'
OWNER = 'cs2-gc-anime-agents-v1'
COMMENT = 'cs2_gc standalone anime agents'
MANIFEST = 'cs2_gc_anime_agents_manifest.json'
PREFIX = 'customplayer_cs2gc_anime_'
CASE_NAME = 'crate_cs2gc_anime'
CASE_ID = '57005'
CASE_IMAGE = 'econ/weapon_cases/' + CASE_NAME
CASE_PRICE = 50
BUNDLE = 'cs2_gc_anime_agent_assets'
AGENTS = (
    ('Gokai', '57000', 'legendary'),
    ('Izachi', '57001', 'legendary'),
    ('Kasumi', '57002', 'ancient'),
    ('Kazashi', '57003', 'mythical'),
    ('Naruki', '57004', 'mythical'),
)
DISPLAY_NAMES = {'Gokai': 'Goku', 'Izachi': 'Itachi', 'Kasumi': 'Sakura',
                 'Kazashi': 'Kakashi', 'Naruki': 'Naruto'}
TIERS = ('mythical', 'legendary', 'ancient')


def _resource(data):
    if len(data) < 16:
        raise ValueError('Truncated compiled agent resource')
    size = struct.unpack_from('<I', data)[0]
    if size < 16 or size > len(data):
        raise ValueError('Invalid compiled agent resource size')
    return kv3.read_resource(data[:size])


def references(data):
    """Read RERL names; texture payloads may follow the resource's declared size."""
    body = dict(_resource(data)[1]).get('RERL')
    if body is None:
        return []
    offset, count = struct.unpack_from('<II', body)
    if offset < 8 or offset + count * 16 > len(body):
        raise ValueError('Invalid agent dependency table')
    result = []
    for index in range(count):
        field = offset + index * 16 + 8
        start = field + struct.unpack_from('<q', body, field)[0]
        if not 0 <= start < len(body):
            raise ValueError('Invalid agent dependency name offset')
        end = body.find(b'\0', start)
        if end < 0:
            raise ValueError('Unterminated agent dependency name')
        name = body[start:end].decode('utf-8')
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe agent dependency: ' + name)
        result.append(name)
    return result


def keep_model_hands(data):
    """Keep the supplied v_arms mesh in both native first-person bodygroup states."""
    version, blocks = _resource(data)
    named = dict(blocks)
    guid, root = kv3.read_kv3(named['DATA'])
    _, control = kv3.read_kv3(named['CTRL'])
    groups = root.get('m_meshGroups')
    masks = root.get('m_refMeshGroupMasks')
    meshes = control.get('embedded_meshes')
    if groups is None or masks is None or meshes is None:
        raise ValueError('Agent has no native first-person mesh groups')
    names = [entry.value for entry in groups.value]
    expected = ('first_or_third_person_@2_#&firstperson_default',
                'first_or_third_person_@3_#&firstperson_hide_default_gloves')
    if any(name not in names for name in expected):
        raise ValueError('Agent first-person bodygroups differ from the inspected models')
    arms = [mesh.get('m_nMeshIndex').value for mesh in meshes.value
            if mesh.get('m_Name').value == 'v_arms']
    if len(arms) != 1 or not 0 <= arms[0] < len(masks.value):
        raise ValueError('Expected exactly one embedded v_arms mesh')
    default, hidden = (1 << names.index(name) for name in expected)
    mask = masks.value[arms[0]]
    if mask.value not in (default, default | hidden):
        raise ValueError('Unexpected first-person arm visibility mask')
    mask.value = default | hidden
    for block in blocks:
        if block[0] == 'DATA':
            block[1] = kv3.write_kv3(guid, root)
    return kv3.write_resource(version, blocks)


def asset_plan(folder, installed):
    folder = Path(folder)
    files, records, dependencies = {}, [], set()
    for title, definition, rarity in AGENTS:
        supplied = folder / title
        models = sorted(supplied.rglob('*.vmdl_c'))
        if len(models) != 1:
            raise ValueError(title + ': expected one compiled player model')
        model = models[0]
        by_name = {}
        for path in model.parent.rglob('*'):
            if path.is_file():
                by_name.setdefault(path.name.lower(), []).append(path)
        prefixes = ('agents/models/otakku/' + model.stem.removesuffix('.vmdl') + '/',
                    model.relative_to(supplied).parent.as_posix() + '/')
        pending = [model.read_bytes()]
        visited = set()
        while pending:
            for reference in references(pending.pop()):
                compiled = reference + '_c'
                if compiled in visited:
                    continue
                visited.add(compiled)
                if reference.startswith(prefixes):
                    candidates = by_name.get(PurePosixPath(compiled).name.lower(), [])
                    if len(candidates) != 1:
                        raise ValueError(title + ': missing or ambiguous dependency ' + compiled)
                    content = candidates[0].read_bytes()
                    if installed.exists(compiled):
                        raise ValueError('Agent asset would shadow an installed game resource: ' + compiled)
                    if compiled in files and files[compiled] != content:
                        raise ValueError('Conflicting supplied agent resource: ' + compiled)
                    files[compiled] = content
                    pending.append(content)
                elif not installed.exists(compiled):
                    raise ValueError(title + ': installed dependency not found: ' + compiled)
                else:
                    dependencies.add(compiled)
        model_path = 'agents/models/cs2gc_anime/' + title.lower() + '.vmdl'
        if installed.exists(model_path + '_c'):
            raise ValueError('Standalone model path is already occupied: ' + model_path)
        files[model_path + '_c'] = keep_model_hands(model.read_bytes())
        records.append(dict(title=title, definition=definition, rarity=rarity, model=model_path))
    return files, records, sorted(dependencies)


def read_manifest(folder):
    folder = Path(folder)
    path = folder / MANIFEST
    if not path.exists():
        if folder.exists() and any(folder.iterdir()):
            raise ValueError('Anime agent folder contains unowned files')
        return None
    manifest = json.loads(read_text(path))
    if manifest.get('owner') != OWNER:
        raise ValueError('Anime agent folder is not owned by CS Reborn')
    expected = [(title, definition, rarity) for title, definition, rarity in AGENTS]
    actual = [(entry['title'], entry['definition'], entry['rarity']) for entry in manifest['agents']]
    if actual != expected:
        raise ValueError('Anime agent identities do not match this generator')
    for name in ('pak01_dir.vpk', 'pak01_000.vpk'):
        pack = folder / name
        if not pack.is_file() or hashlib.sha256(pack.read_bytes()).hexdigest() != manifest['packs'].get(name):
            raise ValueError('Anime agent pack is missing or changed: ' + name)
    return manifest


def installed_manifest(proxy):
    return read_manifest(Path(proxy).resolve().parents[1] / FOLDER)


def install_bundle(proxy):
    """Local launcher payload: only the supplied models and generated portraits."""
    proxy = Path(proxy).resolve()
    bundle = proxy / BUNDLE
    bundled = read_manifest(bundle)
    if bundled is None:
        return 'no bundled anime agents'
    previous = installed_manifest(proxy)
    if previous == bundled:
        return 'bundled anime agents already installed'
    from fair_bot_policy import require_game_closed
    from vpk_pack import _write
    require_game_closed()
    target = proxy.parents[1] / FOLDER
    target.mkdir(parents=True, exist_ok=True)
    for name in ('pak01_000.vpk', 'pak01_dir.vpk'):
        _write(target / name, (bundle / name).read_bytes())
    atomic_write(target / MANIFEST, json.dumps(bundled, indent=2) + '\n')
    return 'installed bundled anime agents'


def patch_schema(source, agents, config):
    sections = collect(parse(source))
    root = spans(source).one('items_game')
    edits = []
    if 'customplayertradable' not in sections.get('prefabs', {}):
        raise ValueError('Installed schema has no native tradable agent prefab')
    if 'weapon_case_selfopening_collection' not in sections['prefabs']:
        raise ValueError('Installed schema has no native keyless case prefab')
    rows = []
    for agent in agents:
        title, definition, rarity, model = (agent[key] for key in ('title', 'definition', 'rarity', 'model'))
        name = PREFIX + title.lower()
        display = DISPLAY_NAMES[title]
        row = [('name', name), ('prefab', 'customplayertradable'), ('item_name', display),
               ('item_description', display + ' | Anime Case'), ('item_rarity', rarity),
               ('model_player', model), ('legacy_character', '0'),
               ('image_inventory', 'econ/characters/' + name),
               ('used_by_classes', [('terrorists', '1'), ('counter-terrorists', '1')]),
               ('attributes', [('icon display model', model)]),
               ('capabilities', [('can_patch', '0')])]
        rows.append((definition, row))
    series_by_name = [key for key, value in sections.get('revolving_loot_lists', {}).items() if value == CASE_NAME]
    if len(series_by_name) > 1:
        raise ValueError('Duplicate Anime Case series')
    series = series_by_name[0] if series_by_name else str(
        max((int(key) for key in sections.get('revolving_loot_lists', {}) if key.isdigit()), default=0) + 1)
    rows.append((CASE_ID, [('name', CASE_NAME), ('prefab', 'weapon_case_selfopening_collection'),
                           ('item_name', 'Anime Case'), ('item_description', 'Five standalone anime agents for both teams.'),
                           ('image_inventory', CASE_IMAGE),
                           ('attributes', [('set supply crate series', [('attribute_class', 'supply_crate_series'),
                                                                        ('value', series)])])]))
    additions = {}

    def add(section, key, values):
        existing = sections.get(section, {}).get(key)
        if existing is not None:
            if existing != values:
                raise ValueError('Anime definition collides with existing schema: ' + section + '/' + key)
            return
        additions.setdefault(section, []).append(_block(key, values, 2) if isinstance(values, list)
                                                 else '\t\t"%s"\t"%s"' % (key, values))

    existing_names = {as_dict(value).get('name'): key for key, value in sections.get('items', {}).items()
                      if isinstance(value, list)}
    for definition, row in rows:
        name = dict(row)['name']
        if name in existing_names and existing_names[name] != definition:
            raise ValueError('Anime item name already uses another definition: ' + name)
        original_title = next((title for title, item_id, _ in AGENTS if item_id == definition), None)
        if original_title:
            legacy = [(key, original_title if key == 'item_name' else
                       original_title + ' | Anime Case' if key == 'item_description' else value)
                      for key, value in row]
            if sections.get('items', {}).get(definition) == legacy:
                nodes = [node for section in root.children if section.key == 'items'
                         for node in section.children if node.key == definition]
                if len(nodes) != 1:
                    raise ValueError('Ambiguous owned anime agent definition: ' + definition)
                for key in ('item_name', 'item_description'):
                    field = nodes[0].one(key)
                    edits.append((field.start, field.end, json.dumps(dict(row)[key])))
                continue
        add('items', definition, row)
    add('revolving_loot_lists', series, CASE_NAME)
    add('client_loot_lists', CASE_NAME, [(CASE_NAME + '_' + tier, '1') for tier in TIERS])
    for tier in TIERS:
        add('client_loot_lists', CASE_NAME + '_' + tier,
            [(PREFIX + agent['title'].lower(), '1') for agent in agents if agent['rarity'] == tier])
    for section, text in additions.items():
        blocks = [node for node in root.children if node.key == section and node.children is not None]
        if not blocks:
            raise ValueError('Missing schema section: ' + section)
        edits.append((blocks[-1].end - 1, blocks[-1].end - 1, '\n' + '\n'.join(text) + '\n'))
    campaigns = [node for section in root.children if section.key == 'seasonaloperations'
                 for node in section.children or [] if node.key == '11']
    if len(campaigns) != 1:
        raise ValueError('Expected one native Armory campaign')
    campaign = campaigns[0]
    enabled = config.get('armory_rotation_enabled', 1)
    offer_found = False
    for node in campaign.children:
        if node.key != 'operational_point_redeemable':
            continue
        name = node.text('item_name')
        if name == CASE_NAME and enabled:
            if offer_found:
                raise ValueError('Duplicate Anime Case Armory offer')
            offer_found = True
            for key, value in (('points', str(CASE_PRICE)), ('local_rotation_slot', 'limited'), ('ui_order', '2')):
                field = node.one(key)
                if field.value != value:
                    edits.append((field.start, field.end, '"' + value + '"'))
        elif name in (CASE_NAME, 'lootlist:removed_items'):
            start = source.rfind('"operational_point_redeemable"', 0, node.opening)
            if start < 0:
                raise ValueError('Expected quoted Armory row key')
            edits.append((start, node.end, ''))
    if enabled and not offer_found:
        edits.append((campaign.end - 1, campaign.end - 1, '\n' + _block('operational_point_redeemable', [
            ('item_name', CASE_NAME), ('points', str(CASE_PRICE)),
            ('local_rotation_slot', 'limited'), ('ui_order', '2'), ('flags', '2')], 3) + '\n'))
    for start, end, text in sorted(edits, reverse=True):
        source = source[:start] + text + source[end:]
    return source


def prepare_schema(proxy, config, source):
    manifest = installed_manifest(proxy)
    if manifest is None:
        return source, 'not imported'
    game = Path(proxy).resolve().parents[1]
    installed = Source(vpk=game / 'csgo/pak01_dir.vpk')
    for dependency in manifest['dependencies']:
        if not installed.exists(dependency):
            raise ValueError('Anime agent dependency missing from this client: ' + dependency)
    return patch_schema(source, manifest['agents'], config), 'five standalone agents and Anime Case'


def prepare(proxy, config):
    """Also run on a warm launch: preserve additions after other schema writers."""
    proxy = Path(proxy).resolve()
    manifest = installed_manifest(proxy)
    if manifest is None:
        return 'not imported'
    game = proxy.parents[1]
    native = game / 'cs2_gc_native'
    target, metadata = native / 'scripts/items/items_game.txt', native / 'cs2_gc_native_manifest.json'
    source, state = read_text(target), json.loads(read_text(metadata))
    if state.get('owner') != 'cs2-gc-native-mixed-v1' or state.get('output_sha256') != digest(source):
        raise ValueError('Anime agents require an unchanged owned native schema')
    changed, _ = prepare_schema(proxy, config, source)
    previous_state = json.dumps(state, sort_keys=True)
    if config.get('armory_rotation_enabled', 1):
        state.setdefault('armory_catalogue', {})[CASE_NAME] = 'limited'
    else:
        state.setdefault('armory_catalogue', {}).pop(CASE_NAME, None)
    state['armory_catalogue'].pop('lootlist:removed_items', None)
    if changed != source:
        atomic_write(target, changed)
        state['output_sha256'] = digest(changed)
        original = read_text(proxy / 'items_game.txt')
        atomic_write(native / 'cs2_gc_schema_stamp.txt', 'CS2_GC_NATIVE_V1 %d %d\n' % (
            zlib.crc32(original.encode()), zlib.crc32(changed.encode())))
        from vpk_pack import pack
        pack(native)
    if json.dumps(state, sort_keys=True) != previous_state:
        atomic_write(metadata, json.dumps(state, indent=2) + '\n')
    info = game / 'csgo/gameinfo.gi'
    current = read_text(info)
    mounted = mount_gameinfo(current, True, FOLDER, COMMENT)
    if mounted != current:
        backup = info.with_name(info.name + '.' + FOLDER + '_backup')
        if not backup.exists():
            with backup.open('x', encoding='utf-8', newline='') as output:
                output.write(current)
        atomic_write(info, mounted)
    return 'installed: five standalone agents and Anime Case; live rendering needs verification'


def import_assets(proxy, source, icon, portraits):
    from fair_bot_policy import require_game_closed
    require_game_closed()
    proxy = Path(proxy).resolve()
    game = proxy.parents[1]
    installed_manifest(proxy)  # Reject unowned or externally changed output.
    installed = Source(vpk=game / 'csgo/pak01_dir.vpk')
    files, agents, dependencies = asset_plan(source, installed)
    template = installed.read('panorama/images/econ/weapon_cases/crate_operation_ii_png.vtex_c')
    if template is None:
        raise ValueError('Installed case icon template is missing')
    files['panorama/images/' + CASE_IMAGE + '_png.vtex_c'] = make_vtex(template, Path(icon).read_bytes(), max_size=512)
    for agent in agents:
        png = Path(portraits) / (agent['title'].lower() + '.png')
        if not png.is_file():
            raise ValueError('Missing model portrait: ' + str(png))
        files['panorama/images/econ/characters/' + PREFIX + agent['title'].lower() + '_png.vtex_c'] = make_vtex(
            template, png.read_bytes(), max_size=512)
    from gameplay_config import load
    config = load(proxy)
    # Validate IDs and every required native field before writing or mounting resources.
    native_schema = game / 'cs2_gc_native/scripts/items/items_game.txt'
    patch_schema(read_text(native_schema), agents, config)
    from vpk_pack import build, _write
    directory, archive = build(sorted(files.items()))
    folder = game / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    state = dict(owner=OWNER, agents=agents, dependencies=dependencies,
                 files={name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
                 packs={name: hashlib.sha256(data).hexdigest() for name, data in
                        [('pak01_dir.vpk', directory), ('pak01_000.vpk', archive)]})
    _write(folder / 'pak01_000.vpk', archive)
    _write(folder / 'pak01_dir.vpk', directory)
    atomic_write(folder / MANIFEST, json.dumps(state, indent=2) + '\n')
    return prepare(proxy, config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy-dir', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--case-icon', type=Path, default=Path(__file__).with_name('cs2_gc_anime_case.png'))
    parser.add_argument('--portraits', type=Path, required=True)
    args = parser.parse_args()
    print(import_assets(args.proxy_dir, args.source, args.case_icon, args.portraits))
    from native_resources import ensure_first_game_path
    from vpk_signatures import update
    print(ensure_first_game_path(args.proxy_dir))
    print(update(args.proxy_dir))


if __name__ == '__main__':
    main()
