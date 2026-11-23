"""Owned, opt-in installation of the user's standalone Prime Karambit test model."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib

import kv3
import native_animations as na
from inventory_item import as_dict, collect, parse
from native_agents import references
from native_finishes import Source, _block, make_vtex
from native_tradeups import atomic_write, digest, mount_gameinfo, parse as spans, read_text

OWNER = 'cs2-gc-prime-karambit-v1'
FOLDER = 'cs2_gc_prime_karambit'
MANIFEST = 'cs2_gc_prime_karambit_manifest.json'
NAME = 'weapon_knife_cs2gc_prime_karambit'
TITLE = 'PRIME Karambit'
COMMENT = 'cs2_gc standalone Prime Karambit'
IMAGE = 'econ/weapons/base_weapons/' + NAME
PRIMARY = 'animation/skeletons/characters/viewmodel.vnmskel'
SECONDARY = 'animation/skeletons/cs2gc_prime_karambit/prime_karambit.vnmskel'
MODEL = 'models/cs2gc_prime_karambit/prime_karambit.vmdl'
GRAPH = 'animation/graphs/viewmodel/viewmodel_knife_cs2gc_prime_karambit.vnmgraph'
SOUND_EVENTS = 'soundevents/cs2gc_prime_karambit.vsndevts'
DEPENDENCIES = 'cs2gc_prime_karambit_dependencies.vrman'
ROOT_GRAPH = 'animation/graphs/viewmodel/viewmodel.vnmgraph_c'
WEAPONS = 'scripts/weapons.vdata_c'
SOUND_MANIFEST = 'soundevents/soundevents_manifest.vrman_c'
OVERRIDES = (ROOT_GRAPH, WEAPONS, SOUND_MANIFEST)
CLIP_FOLDER = 'animation/anims/viewmodel/knife/cs2gc_prime_karambit/'
CLIPS = ('idle', 'draw', 'inspect_1', 'slash1', 'slash2', 'midslash1', 'midslash2', 'stab', 'stab_miss')
HUD_ICON = 'panorama/images/icons/equipment/knife_cs2gc_prime_karambit.vsvg_c'
DESCRIPTION = 'The original PRIME Karambit, with its own inspect and attack animations.'
BUNDLE = 'cs2_gc_prime_karambit_assets'
BUNDLE_MANIFEST = 'cs2_gc_prime_karambit_bundle.json'
PACKS = ('pak01_dir.vpk', 'pak01_000.vpk')


def resource_parts(data):
    version, blocks = kv3.read_resource(data)
    return version, blocks, dict(blocks)


def reference_ids(data):
    _, _, blocks = resource_parts(data)
    body = blocks['RERL']
    offset, count = struct.unpack_from('<II', body)
    names = references(data)
    if len(names) != count:
        raise ValueError('Invalid native resource reference table')
    return {name: struct.unpack_from('<Q', body, offset + i * 16)[0] for i, name in enumerate(names)}


def extend_references(body, additions):
    offset, count = struct.unpack_from('<II', body)
    entries = []
    for i in range(count):
        entry = offset + i * 16
        identity, relative = struct.unpack_from('<Qq', body, entry)
        start = entry + 8 + relative
        if not 0 <= start < len(body) or b'\0' not in body[start:]:
            raise ValueError('Invalid resource reference')
        entries.append((body[start:body.index(b'\0', start)].decode('utf-8'), identity))
    existing = dict(entries)
    for name, identity in additions.items():
        if name in existing and existing[name] != identity:
            raise ValueError('Compiler resource ID differs from installed client: ' + name)
        if name not in existing:
            entries.append((name, identity))
    result = bytearray(body[:offset])
    struct.pack_into('<I', result, 4, len(entries))
    result.extend(b'\0' * (16 * len(entries)))
    for i, (name, identity) in enumerate(entries):
        entry = offset + i * 16
        struct.pack_into('<Qq', result, entry, identity, len(result) - entry - 8)
        result.extend(name.encode('utf-8') + b'\0')
    return bytes(result)


def replace_data(data, payload, additions):
    version, blocks, named = resource_parts(data)
    rerl = extend_references(named['RERL'], additions) if additions else named.get('RERL')
    return kv3.write_resource(version, [[name, payload if name == 'DATA' else rerl if name == 'RERL' else body]
                                        for name, body in blocks])


def unique(values, description):
    values = list(values)
    if len(values) != 1:
        raise ValueError('Expected one ' + description)
    return values[0]


def augment_graph(root):
    """Append one dispatch state; no existing node or resource index moves."""
    nodes = root.get('m_nodes').value
    paths = root.get('m_nodePaths').value
    if len(paths) != len(nodes) or any(node.get('m_nNodeIdx').value != i for i, node in enumerate(nodes)):
        raise ValueError('Unexpected native graph index layout')
    if any(node.get('m_comparisionIDs') is not None and NAME in na.plain(node.get('m_comparisionIDs')) for node in nodes):
        raise ValueError('Prime Karambit graph dispatch already exists')
    candidates = []
    for machine in nodes:
        states = machine.get('m_stateDefinitions')
        if states is None:
            continue
        for index, state in enumerate(states.value):
            condition_index = state.get('m_nEntryConditionNodeIdx').value
            if condition_index < 0:
                continue
            condition = na.plain(nodes[condition_index])
            if condition.get('m_comparisionIDs') == ['weapon_knife_karambit']:
                candidates.append((machine, index, state))
    machine, stock_index, state = unique(candidates, 'native Karambit dispatch state')
    states = machine.get('m_stateDefinitions').value
    stock_state_node = state.get('m_nStateNodeIdx').value
    stock_reference = nodes[stock_state_node].get('m_nChildNodeIdx').value
    stock_condition = state.get('m_nEntryConditionNodeIdx').value
    ref_slots = root.get('m_referencedGraphSlots').value
    resources = root.get('m_resources').value
    slot = ref_slots[nodes[stock_reference].get('m_nReferencedGraphIdx').value]
    resource_index = slot.get('m_dataSlotIdx').value
    if resources[resource_index].value != 'animation/graphs/viewmodel/viewmodel_knife_karambit.vnmgraph':
        raise ValueError('Native Karambit state references a different graph')
    incoming = [transition for other in states for transition in other.get('m_transitionDefinitions').value
                if transition.get('m_nTargetStateIdx').value == stock_index]
    incoming_shapes = {tuple((key, na.plain(value)) for key, value in transition.value) for transition in incoming}
    if len(incoming_shapes) != 1:
        raise ValueError('Native knife transitions no longer share one Karambit transition')
    to_stock = copy.deepcopy(incoming[0])
    stock_transition = to_stock.get('m_nTransitionNodeIdx').value
    stock_transition_condition = to_stock.get('m_nConditionNodeIdx').value
    templates = (stock_state_node, stock_reference, stock_condition, stock_transition, stock_transition_condition)
    first = len(nodes)
    new_state, new_ref, new_condition, new_transition, new_transition_condition = range(first, first + 5)
    clones = [copy.deepcopy(nodes[index]) for index in templates]
    for index, clone in enumerate(clones, first):
        na._set(clone, 'm_nNodeIdx', na._int(index))
    na._set(clones[0], 'm_nChildNodeIdx', na._int(new_ref))
    na._set(clones[1], 'm_nReferencedGraphIdx', na._int(len(ref_slots)))
    na._set(clones[3], 'm_nTargetStateNodeIdx', na._int(new_state))
    for clone in (clones[2], clones[4]):
        clone.get('m_comparisionIDs').value[0].value = NAME
    new_slot = copy.deepcopy(slot)
    na._set(new_slot, 'm_nNodeIdx', na._int(new_ref))
    na._set(new_slot, 'm_dataSlotIdx', na._int(len(resources)))
    ref_slots.append(new_slot)
    resource = copy.deepcopy(resources[resource_index])
    resource.value = GRAPH
    resources.append(resource)
    new_definition = copy.deepcopy(state)
    na._set(new_definition, 'm_nStateNodeIdx', na._int(new_state))
    na._set(new_definition, 'm_nEntryConditionNodeIdx', na._int(new_condition))
    new_definition.get('m_transitionDefinitions').value.append(to_stock)
    transition = copy.deepcopy(to_stock)
    na._set(transition, 'm_nTargetStateIdx', na._int(len(states)))
    na._set(transition, 'm_nConditionNodeIdx', na._int(new_transition_condition))
    na._set(transition, 'm_nTransitionNodeIdx', na._int(new_transition))
    for other in states:
        other.get('m_transitionDefinitions').value.append(copy.deepcopy(transition))
    states.append(new_definition)
    for index, original in enumerate(templates, first):
        path = copy.deepcopy(paths[original])
        path.value = 'CS2GC/PrimeKarambit/' + str(index)
        paths.append(path)
        if original in na.plain(root.get('m_persistentNodeIndices')):
            root.get('m_persistentNodeIndices').value.append(na._int(index))
    nodes.extend(clones)
    return root


def graph_override(data, identities):
    _, _, blocks = resource_parts(data)
    guid, root = na.read_block(blocks['DATA'])
    augment_graph(root)
    return replace_data(data, kv3.write_kv3(guid, root), {GRAPH: identities[GRAPH]})


def weapon_override(data, definition):
    _, _, blocks = resource_parts(data)
    guid, root = na.read_block(blocks['DATA'])
    if root.get(definition) is not None:
        raise ValueError('New knife ID collides with installed weapon subclass: ' + definition)
    stock = root.get('507')
    if stock is None or stock.get('m_szName').value != 'weapon_knife_karambit':
        raise ValueError('Installed native Karambit subclass differs')
    row = copy.deepcopy(stock)
    for key, value in (('m_szName', NAME), ('m_szWorldModel', MODEL), ('m_szAnimSkeleton', SECONDARY)):
        row.get(key).value = value
    root.value.append((definition, row))
    return replace_data(data, kv3.write_kv3(guid, root), {})


def manifest_groups(body):
    offset, count = struct.unpack_from('<ii', body)
    groups = []
    if offset < 8 or count < 0 or offset + count * 8 > len(body):
        raise ValueError('Unsupported resource manifest layout')
    for i in range(count):
        entry = offset + i * 8
        relative, length = struct.unpack_from('<ii', body, entry)
        start = entry + relative
        if length < 0 or start < 0 or start + length * 4 > len(body):
            raise ValueError('Invalid resource manifest group')
        names = []
        for j in range(length):
            field = start + j * 4
            position = field + struct.unpack_from('<i', body, field)[0]
            if not 0 <= position < len(body) or b'\0' not in body[position:]:
                raise ValueError('Invalid resource manifest string')
            names.append(body[position:body.index(b'\0', position)].decode('utf-8'))
        groups.append(names)
    return groups


def encode_manifest_groups(groups):
    result = bytearray(struct.pack('<ii', 8, len(groups)) + b'\0' * (len(groups) * 8))
    for i, group in enumerate(groups):
        entry, start = 8 + i * 8, len(result)
        struct.pack_into('<ii', result, entry, start - entry, len(group))
        result.extend(b'\0' * (4 * len(group)))
        for j, name in enumerate(group):
            field = start + j * 4
            struct.pack_into('<i', result, field, len(result) - field)
            result.extend(name.encode('utf-8') + b'\0')
    return bytes(result)


def sound_manifest_override(data, identities):
    _, _, blocks = resource_parts(data)
    if 'NTRO' in blocks:
        raise ValueError('Unsupported legacy sound manifest')
    groups = manifest_groups(blocks['DATA'])
    if len(groups) != 2 or SOUND_EVENTS in [name for group in groups for name in group]:
        raise ValueError('Unexpected native sound event manifest')
    groups[1].append(SOUND_EVENTS)
    return replace_data(data, encode_manifest_groups(groups), {SOUND_EVENTS: identities[SOUND_EVENTS]})


def knife_row(sections):
    original = sections['items'].get('507')
    if original is None or as_dict(original).get('name') != 'weapon_knife_karambit':
        raise ValueError('Missing native Karambit economy definition')
    replacements = {'name': NAME, 'item_name': TITLE, 'item_description': DESCRIPTION,
                    'image_inventory': IMAGE, 'model_player': MODEL, 'model_world': MODEL,
                    'attributes': [('pedestal display model', MODEL)]}
    row = [(key, replacements.get(key, copy.deepcopy(value))) for key, value in original
           if key not in ('paint_data', 'icon_default_image', 'inventory_image_data')]
    row.append(('paintable', '0'))
    return row


def patch_schema(source, definition, enabled=True):
    sections = collect(parse(source))
    row = knife_row(sections)
    existing = sections['items'].get(definition)
    for key, value in sections['items'].items():
        if isinstance(value, list) and as_dict(value).get('name') == NAME and key != definition:
            raise ValueError('Prime Karambit name already has another item ID')
    if existing is not None and existing != row:
        raise ValueError('Prime Karambit item ID collides with another definition: ' + definition)
    root = spans(source).one('items_game')
    blocks = [node for node in root.children if node.key == 'items' and node.children is not None]
    if enabled and existing is None:
        end = blocks[-1].end - 1
        return source[:end] + '\n' + _block(definition, row, 2) + '\n' + source[end:]
    if not enabled and existing is not None:
        node = unique((node for block in blocks for node in block.children if node.key == definition), 'owned knife row')
        start = source.rfind('"' + definition + '"', 0, node.opening)
        if start < 0:
            raise ValueError('Could not locate owned knife item key')
        return source[:start] + source[node.end:]
    return source


def installed_manifest(proxy, verify_packs=True):
    folder = Path(proxy).resolve().parents[1] / FOLDER
    path = folder / MANIFEST
    if not path.exists():
        if folder.exists() and any(folder.iterdir()):
            raise ValueError('Prime Karambit folder contains unowned files')
        return None
    manifest = json.loads(read_text(path))
    if (manifest.get('owner') != OWNER or manifest.get('name') != NAME
            or not isinstance(manifest.get('definition'), str) or not manifest['definition'].isdigit()
            or not 57000 <= int(manifest['definition']) <= 65535
            or not isinstance(manifest.get('enabled'), bool)
            or not isinstance(manifest.get('client_inputs'), dict)
            or set(manifest.get('client_inputs', {})) != {*OVERRIDES, PRIMARY + '_c'}):
        raise ValueError('Prime Karambit manifest identity differs')
    if verify_packs:
        for name in PACKS:
            if hashlib.sha256((folder / name).read_bytes()).hexdigest() != manifest['packs'][name]:
                raise ValueError('Prime Karambit pack changed: ' + name)
    return manifest


def packs_match(folder, packs):
    """True when both pack files exist and hash to the recorded values (an interrupted install leaves them apart)."""
    folder = Path(folder)
    return isinstance(packs, dict) and all(
        (folder / name).is_file() and hashlib.sha256((folder / name).read_bytes()).hexdigest() == packs.get(name)
        for name in PACKS)


def check_client(proxy, manifest):
    game = Path(proxy).resolve().parents[1]
    installed = Source(vpk=game / 'csgo/pak01_dir.vpk')
    core = Source(vpk=game / 'core/pak01_dir.vpk')
    for path, expected in manifest['client_inputs'].items():
        if hashlib.sha256(installed.read(path)).hexdigest() != expected:
            raise ValueError('Prime Karambit needs rebuilding for this CS2 client: ' + path)
    for dependency in manifest['dependencies']:
        if not installed.exists(dependency) and not core.exists(dependency):
            raise ValueError('Prime Karambit dependency missing: ' + dependency)


def prepare_schema(proxy, config, source):
    manifest = installed_manifest(proxy)
    if manifest is None:
        return source, 'not imported'
    enabled = manifest.get('enabled', True)
    if enabled:
        check_client(proxy, manifest)
    return patch_schema(source, manifest['definition'], enabled), 'enabled' if enabled else 'disabled'


def prepare(proxy, config):
    proxy = Path(proxy).resolve()
    manifest = installed_manifest(proxy)
    if manifest is None:
        return 'not imported'
    from fair_bot_policy import require_game_closed
    require_game_closed()
    game = proxy.parents[1]
    native = game / 'cs2_gc_native'
    target, metadata = native / 'scripts/items/items_game.txt', native / 'cs2_gc_native_manifest.json'
    source, state = read_text(target), json.loads(read_text(metadata))
    if state.get('owner') != 'cs2-gc-native-mixed-v1' or state.get('output_sha256') != digest(source):
        raise ValueError('Prime Karambit requires an unchanged owned native schema')
    changed, status = prepare_schema(proxy, config, source)
    if changed != source:
        atomic_write(target, changed)
        state['output_sha256'] = digest(changed)
        atomic_write(metadata, json.dumps(state, indent=2) + '\n')
        original = read_text(proxy / 'items_game.txt')
        atomic_write(native / 'cs2_gc_schema_stamp.txt', 'CS2_GC_NATIVE_V1 %d %d\n' % (
            zlib.crc32(original.encode()), zlib.crc32(changed.encode())))
        from vpk_pack import pack
        pack(native)
    info = game / 'csgo/gameinfo.gi'
    current = read_text(info)
    mounted = mount_gameinfo(current, manifest.get('enabled', True), FOLDER, COMMENT)
    mounted = mount_gameinfo(mounted, manifest.get('enabled', True), FOLDER, COMMENT, kind='Mod')
    if mounted != current:
        backup = info.with_name(info.name + '.' + FOLDER + '_backup')
        if not backup.exists():
            with backup.open('x', encoding='utf-8', newline='') as output:
                output.write(current)
        atomic_write(info, mounted)
    return status + ': standalone knife; live validation is separate'


def owned_assets(proxy, sdk, icon):
    """Resources this addon authored, read from the SDK output. The client-derived overrides are not part of them."""
    proxy, sdk = Path(proxy).resolve(), Path(sdk).resolve()
    previous = installed_manifest(proxy)
    game = proxy.parents[1]
    installed = Source(vpk=game / 'csgo/pak01_dir.vpk')
    schema = read_text(game / 'cs2_gc_native/scripts/items/items_game.txt')
    items = collect(parse(schema))['items']
    definition = previous['definition'] if previous else str(next(i for i in range(57000, 65536) if str(i) not in items))
    if previous is None:
        patch_schema(schema, definition)
    output = sdk / 'game/csgo'
    namespaces = ('models/cs2gc_prime_karambit', 'materials/cs2gc_prime_karambit',
                  'animation/skeletons/cs2gc_prime_karambit', CLIP_FOLDER, 'sounds/cs2gc_prime_karambit')
    files = {path.relative_to(output).as_posix(): path.read_bytes() for namespace in namespaces
             for path in (output / namespace).rglob('*') if path.is_file() and path.name.endswith('_c')}
    for path in (GRAPH, SOUND_EVENTS, DEPENDENCIES):
        files[path + '_c'] = (output / (path + '_c')).read_bytes()
    files[HUD_ICON] = (output / HUD_ICON).read_bytes()
    report = json.loads(read_text(sdk / 'content/csgo' / CLIP_FOLDER / 'compiled_validation.json'))
    def data(path):
        return na.plain(na.read_block(dict(na.resource_blocks(files[path + '_c'])[1])['DATA'])[1])
    # Clips and mesh must interpret the ring in the same asset-local space.
    model = data(MODEL)['m_modelSkeleton']
    rig = data(SECONDARY)
    if model['m_boneName'] != rig['m_boneIDs'] or model['m_nParent'] != rig['m_parentIndices']:
        raise ValueError('PRIME model and clip skeleton hierarchies differ')
    for pos, rot, ref in zip(model['m_bonePosParent'], model['m_boneRotParent'], rig['m_parentSpaceReferencePose']):
        if math.dist(pos, ref[:3]) > 0.001 or 1 - abs(sum(a*b for a,b in zip(rot, ref[4:8]))) > 1e-5:
            raise ValueError('PRIME model and clip skeleton bind transforms differ')
    if 'ring_contact' not in report:
        raise ValueError('Rebuild and verify the ring-fitted PRIME clips before exporting')
    for name in CLIPS:
        path = CLIP_FOLDER + name + '.vnmclip_c'
        if hashlib.sha256(files[path]).hexdigest() != report['animations'][name]['sha256']:
            raise ValueError('Compiled animation must pass --verify again: ' + name)
    template = installed.read('panorama/images/econ/weapons/base_weapons/weapon_knife_karambit_png.vtex_c')
    files['panorama/images/' + IMAGE + '_png.vtex_c'] = make_vtex(template, Path(icon).read_bytes())
    return files, report, definition, previous


def assemble(owned, installed, core, definition):
    """Add the three overrides derived from this client, then check collisions and dependencies."""
    inputs = {}
    for path in (*OVERRIDES, PRIMARY + '_c'):
        inputs[path] = installed.read(path)
        if inputs[path] is None:
            raise ValueError('CS2 client resource missing: ' + path)
    ids = reference_ids(owned[DEPENDENCIES + '_c'])
    files = dict(owned)
    files[ROOT_GRAPH] = graph_override(inputs[ROOT_GRAPH], ids)
    files[WEAPONS] = weapon_override(inputs[WEAPONS], definition)
    files[SOUND_MANIFEST] = sound_manifest_override(inputs[SOUND_MANIFEST], ids)
    required = (MODEL + '_c', SECONDARY + '_c', GRAPH + '_c', SOUND_EVENTS + '_c')
    if any(path not in files for path in required):
        raise ValueError('Compiled standalone knife assets are incomplete')
    dependencies = set()
    for path, data in files.items():
        if path not in OVERRIDES and (installed.exists(path) or core.exists(path)):
            raise ValueError('New knife asset collides with an installed game asset: ' + path)
        for reference in references(data):
            target = reference + '_c'
            if target not in files:
                if not installed.exists(target) and not core.exists(target):
                    raise ValueError('Unresolved knife dependency: ' + target)
                dependencies.add(target)
    return files, inputs, sorted(dependencies)


def build_assets(proxy, sdk, icon):
    owned, report, definition, previous = owned_assets(proxy, sdk, icon)
    game = Path(proxy).resolve().parents[1]
    files, inputs, dependencies = assemble(owned, Source(vpk=game / 'csgo/pak01_dir.vpk'),
                                           Source(vpk=game / 'core/pak01_dir.vpk'), definition)
    manifest = {'owner': OWNER, 'name': NAME, 'definition': definition,
                'enabled': previous.get('enabled', True) if previous else True,
                'client_inputs': {path: hashlib.sha256(data).hexdigest() for path, data in inputs.items()},
                'dependencies': dependencies, 'animation_validation': report}
    return files, manifest


def install_assets(proxy, sdk, icon):
    from fair_bot_policy import require_game_closed
    from vpk_pack import _write, build
    require_game_closed()
    files, manifest = build_assets(proxy, sdk, icon)
    directory, archive = build(sorted(files.items()))
    manifest['packs'] = {name: hashlib.sha256(data).hexdigest()
                         for name, data in (('pak01_dir.vpk', directory), ('pak01_000.vpk', archive))}
    require_game_closed()
    target = Path(proxy).resolve().parents[1] / FOLDER
    target.mkdir(parents=True, exist_ok=True)
    _write(target / 'pak01_000.vpk', archive)
    _write(target / 'pak01_dir.vpk', directory)
    atomic_write(target / MANIFEST, json.dumps(manifest, indent=2) + '\n')
    return manifest


def write_bundle(owned, report, definition, target):
    from vpk_pack import _write, build
    if any(path in owned for path in OVERRIDES):
        raise ValueError('The bundle must not contain client-derived resources')
    directory, archive = build(sorted(owned.items()))
    manifest = {'owner': OWNER, 'name': NAME, 'definition': definition,
                'files': {path: hashlib.sha256(data).hexdigest() for path, data in sorted(owned.items())},
                'packs': {name: hashlib.sha256(data).hexdigest() for name, data in zip(PACKS, (directory, archive))},
                'animation_validation': report}
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    _write(target / 'pak01_000.vpk', archive)
    _write(target / 'pak01_dir.vpk', directory)
    atomic_write(target / BUNDLE_MANIFEST, json.dumps(manifest, indent=2) + '\n')
    return manifest


def export_bundle(proxy, sdk, icon, target):
    """Developer step: the launcher payload. It holds only owned resources, never the client-derived overrides."""
    owned, report, definition, _ = owned_assets(proxy, sdk, icon)
    game = Path(proxy).resolve().parents[1]
    assemble(owned, Source(vpk=game / 'csgo/pak01_dir.vpk'), Source(vpk=game / 'core/pak01_dir.vpk'), definition)
    return write_bundle(owned, report, definition, target)


def read_bundle(folder):
    """The verified bundle manifest and its owned files; None when this build carries no Prime Karambit."""
    folder = Path(folder)
    path = folder / BUNDLE_MANIFEST
    if not path.exists():
        if folder.exists() and any(folder.iterdir()):
            raise ValueError('Prime Karambit bundle folder contains unowned files')
        return None
    manifest = json.loads(read_text(path))
    if (manifest.get('owner') != OWNER or manifest.get('name') != NAME
            or not isinstance(manifest.get('definition'), str) or not manifest['definition'].isdigit()
            or not 57000 <= int(manifest['definition']) <= 65535
            or not isinstance(manifest.get('files'), dict) or not isinstance(manifest.get('packs'), dict)):
        raise ValueError('Prime Karambit bundle identity differs')
    if not packs_match(folder, manifest['packs']):
        raise ValueError('Prime Karambit bundle pack is missing or changed')
    if any(path in OVERRIDES for path in manifest['files']):
        raise ValueError('Prime Karambit bundle must not carry client-derived resources')
    source = Source(vpk=folder / 'pak01_dir.vpk')
    files = {path: source.read(path) for path in manifest['files']}
    for path, expected in manifest['files'].items():
        if files[path] is None or hashlib.sha256(files[path]).hexdigest() != expected:
            raise ValueError('Prime Karambit bundle file is missing or changed: ' + path)
    return manifest, files


def install_bundle(proxy):
    """Launcher payload: rebuild this machine's pack from the owned bundle and the player's own CS2 files."""
    proxy = Path(proxy).resolve()
    bundled = read_bundle(proxy / BUNDLE)
    if bundled is None:
        return 'no bundled Prime Karambit'
    bundle, owned = bundled
    game = proxy.parents[1]
    installed = Source(vpk=game / 'csgo/pak01_dir.vpk')
    core = Source(vpk=game / 'core/pak01_dir.vpk')
    state = hashlib.sha256(json.dumps(bundle, sort_keys=True).encode('utf-8')).hexdigest()
    previous = installed_manifest(proxy, verify_packs=False)
    folder = game / FOLDER
    current = {}
    for path in (*OVERRIDES, PRIMARY + '_c'):
        data = installed.read(path)
        if data is None:
            raise ValueError('CS2 client resource missing: ' + path)
        current[path] = hashlib.sha256(data).hexdigest()
    if (previous is not None and previous.get('bundle') == state and previous['client_inputs'] == current
            and packs_match(folder, previous.get('packs'))):
        return 'bundled Prime Karambit already installed'
    from fair_bot_policy import require_game_closed
    from vpk_pack import _write, build
    require_game_closed()
    files, inputs, dependencies = assemble(owned, installed, core, bundle['definition'])
    directory, archive = build(sorted(files.items()))
    manifest = {'owner': OWNER, 'name': NAME, 'definition': bundle['definition'],
                'enabled': previous['enabled'] if previous else True,
                'client_inputs': current, 'dependencies': dependencies,
                'animation_validation': bundle.get('animation_validation'), 'bundle': state,
                'packs': {name: hashlib.sha256(data).hexdigest() for name, data in zip(PACKS, (directory, archive))}}
    folder.mkdir(parents=True, exist_ok=True)
    _write(folder / 'pak01_000.vpk', archive)
    _write(folder / 'pak01_dir.vpk', directory)
    atomic_write(folder / MANIFEST, json.dumps(manifest, indent=2) + '\n')
    return 'installed bundled Prime Karambit'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy-dir', type=Path, required=True)
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--icon', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true', help='Validate and construct assets without installing')
    modes.add_argument('--export-bundle', action='store_true',
                       help='Write the launcher payload (owned resources only) to tools/' + BUNDLE)
    modes.add_argument('--disable', action='store_true', help='Remove only this owned knife row and addon mount')
    modes.add_argument('--enable', action='store_true', help='Restore the already installed test knife')
    args = parser.parse_args()
    if args.disable or args.enable:
        from fair_bot_policy import require_game_closed
        require_game_closed()
        manifest = installed_manifest(args.proxy_dir)
        if manifest is None:
            parser.error('No owned Prime Karambit installation exists')
        if args.enable:
            check_client(args.proxy_dir, manifest)
        manifest['enabled'] = args.enable
        target = args.proxy_dir.resolve().parents[1] / FOLDER / MANIFEST
        atomic_write(target, json.dumps(manifest, indent=2) + '\n')
        print(prepare(args.proxy_dir, {}))
        from vpk_signatures import update
        print(update(args.proxy_dir))
    elif args.sdk is None or args.icon is None:
        parser.error('--sdk and --icon are required for validation or installation')
    elif args.export_bundle:
        manifest = export_bundle(args.proxy_dir, args.sdk, args.icon, Path(__file__).resolve().parent / BUNDLE)
        print(f'Exported {len(manifest["files"])} owned resources for item {manifest["definition"]} to tools/{BUNDLE}.')
    elif args.check:
        files, manifest = build_assets(args.proxy_dir, args.sdk, args.icon)
        print(f'Validated {len(files)} assets; candidate item ID {manifest["definition"]}. No installation changes.')
    else:
        manifest = install_assets(args.proxy_dir, args.sdk, args.icon)
        print('Installed owned test assets for item ' + manifest['definition'] + '; run native preparation before granting.')


if __name__ == '__main__':
    main()
