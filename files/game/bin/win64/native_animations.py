"""Optional CS:GO-style viewmodel animations for the current CS2 client.

The user supplies an extraction of the first public CS2 build (2023), whose weapon models still embed the
CS:GO first-person sequences (legacy AG1 animation data on the ``v_weapon_bip01_*`` rig). The current client
plays AnimGraph 2 clips (``*.vnmclip_c``) on a different rig. This module decodes the legacy sequences,
retargets them bone by bone onto the current rig and re-encodes them into copies of the installed clips, keeping
every event, sync track and skeleton reference of the installed clip. The copies are packed into an owned
search path that is mounted only while the NEW-tab toggle selects CS:GO animations (restart required).

Format references: ValveResourceFormat ModelAnimation (AnimationSegmentTable.cs, SegmentHelpers.cs,
SegmentDecoders/*.cs) and ModelAnimation2/AnimationClip.cs. No game asset ships with this helper.
"""
from pathlib import Path
import hashlib
import json
import math
import os
import struct
import zlib

import kv3

# ---------------------------------------------------------------- math (quaternions are x, y, z, w)


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def qconj(q):
    return (-q[0], -q[1], -q[2], q[3])


def qnorm(q):
    length = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / length for c in q)


def qrot(q, v):
    x, y, z, w = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx))


def tmul(parent, child):
    """Compose two (position, rotation) transforms: parent * child."""
    p = qrot(parent[1], child[0])
    return ((parent[0][0] + p[0], parent[0][1] + p[1], parent[0][2] + p[2]), qnorm(qmul(parent[1], child[1])))


def tinv(t):
    q = qconj(t[1])
    p = qrot(q, t[0])
    return ((-p[0], -p[1], -p[2]), q)


IDENTITY = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def to_model(locals_, parents, roots=None):
    out = []
    for index, local in enumerate(locals_):
        parent = parents[index]
        if parent < 0:
            out.append(tmul(roots, local) if roots else local)
        else:
            out.append(tmul(out[parent], local))
    return out


def to_local(models, parents, roots=None):
    out = []
    for index, model in enumerate(models):
        parent = parents[index]
        base = models[parent] if parent >= 0 else roots
        out.append(tmul(tinv(base), model) if base else model)
    return out


# ---------------------------------------------------------------- KV3 helpers


def plain(node):
    if node.type == kv3.OBJECT:
        return {key: plain(value) for key, value in node.value}
    if node.type in (kv3.ARRAY, kv3.ARRAY_TYPED, kv3.ARRAY_TYPE_BYTE_LENGTH, kv3.ARRAY_TYPE_AUXILIARY_BUFFER):
        return [plain(value) for value in node.value]
    return node.value


def read_block(data):
    return (kv3.read_kv4 if data[:4] == b'\x04\x33\x56\x4b' else kv3.read_kv3)(data)


def resource_blocks(data):
    version, blocks = kv3.read_resource(data)
    return version, blocks


def _float(value):
    return kv3.Node(kv3.DOUBLE, float(value))


def _int(value):
    return kv3.Node(kv3.INT64, int(value))


def _bool(value):
    return kv3.Node(kv3.BOOLEAN_TRUE if value else kv3.BOOLEAN_FALSE, bool(value))


def _set(obj, name, node):
    for index, (key, _) in enumerate(obj.value):
        if key == name:
            obj.value[index] = (key, node)
            return
    raise KeyError(name)


# ---------------------------------------------------------------- legacy (AG1) decoding

def _half(raw):
    return struct.unpack('<e', raw)[0]


def _quat48(raw):
    w1, w2, w3 = struct.unpack('<HHH', raw)
    scale = 0.70710677 / 16384.0
    def axis(word):
        value = word & 0x3FFF
        return scale * value if word & 0x4000 else scale * (value - 16384)
    x, y, z = axis(w1), axis(w2), axis(w3)
    w = math.sqrt(max(0.0, 1 - x * x - y * y - z * z))
    if w3 & 0x8000: w = -w
    if w1 & 0x8000:
        return (y, z, w, x) if w2 & 0x8000 else (z, w, x, y)
    return (w, x, y, z) if w2 & 0x8000 else (x, y, z, w)


class LegacyModel:
    """Skeleton and decoded first-person sequences of a 2023 CS2 weapon model (vmdl_c with ANIM/AGRP)."""

    def __init__(self, data):
        _, blocks = resource_blocks(data)
        named = {}
        for name, content in blocks:
            if name in ('DATA', 'ANIM', 'AGRP') and name not in named:
                named[name] = read_block(content)[1]
        if 'ANIM' not in named or 'AGRP' not in named:
            raise ValueError('Model has no embedded legacy animation')
        skeleton = plain(named['DATA'].get('m_modelSkeleton'))
        self.bones = list(skeleton['m_boneName'])
        self.parents = list(skeleton['m_nParent'])
        self.bind = [(tuple(p), tuple(q)) for p, q in zip(skeleton['m_bonePosParent'], skeleton['m_boneRotParent'])]
        self.index = {name.lower(): i for i, name in enumerate(self.bones)}
        anim = named['ANIM']
        decoder_names = [plain(item)['m_szName'] for item in anim.get('m_decoderArray').value]
        channels = []
        for channel in plain(named['AGRP'].get('m_decodeKey'))['m_dataChannelArray']:
            attribute = channel['m_szVariableName'] if channel['m_szChannelClass'] == 'BoneChannel' else None
            remap = {}
            for name, element in zip(channel['m_szElementNameArray'], channel.get('m_nElementIndexArray') or []):
                bone = self.index.get((name or '').lower())
                if bone is not None: remap[element] = bone
            channels.append((attribute, remap))
        self.segments = [self._segment(plain(item), decoder_names, channels) for item in anim.get('m_segmentArray').value]
        self.anims = {}
        for item in anim.get('m_animArray').value:
            desc = plain(item)
            data_desc = desc.get('m_pData') or desc
            self.anims[desc['m_name']] = {
                'fps': float(desc.get('fps') or 30.0),
                'frames': int(data_desc['m_nFrames']),
                'blocks': [(b['m_nStartFrame'], b['m_nEndFrame'], list(b['m_segmentIndexArray']))
                           for b in data_desc['m_frameblockArray']],
                'delta': bool(desc['m_flags'].get('m_bDelta')),
                'events': desc.get('m_eventArray') or [],
            }

    @staticmethod
    def _segment(segment, decoder_names, channels):
        container = bytes(segment['m_container'])
        decoder = decoder_names[struct.unpack_from('<h', container, 0)[0]]
        count = struct.unpack_from('<h', container, 4)[0]
        elements = struct.unpack_from('<%dh' % count, container, 8)
        attribute, remap = channels[segment['m_nLocalChannel']]
        if attribute not in ('Position', 'Angle'):
            return None
        wanted = [(slot, remap[element]) for slot, element in enumerate(elements) if element in remap]
        return decoder, attribute, count, wanted, container[8 + count * 2:]

    def sample(self, name):
        """Local (position, rotation) for every bone at every frame of a sequence."""
        anim = self.anims[name]
        frames = []
        for frame in range(anim['frames']):
            pose = [[p, q] for p, q in self.bind]
            for start, end, segment_ids in anim['blocks']:
                if not start <= frame <= end: continue
                local = frame - start
                for segment_id in segment_ids:
                    segment = self.segments[segment_id]
                    if segment is None: continue
                    decoder, attribute, count, wanted, data = segment
                    slot = 0 if attribute == 'Position' else 1
                    for element, bone in wanted:
                        value = self._read(decoder, data, count, local, element)
                        if value is not None: pose[bone][slot] = value
            frames.append([(tuple(p), qnorm(q)) for p, q in pose])
        return frames

    @staticmethod
    def _read(decoder, data, count, frame, element):
        if decoder == 'CCompressedStaticVector3':
            o = element * 6
            return tuple(_half(data[o + 2 * i:o + 2 * i + 2]) for i in range(3))
        if decoder == 'CCompressedStaticFullVector3':
            return struct.unpack_from('<3f', data, element * 12)
        if decoder == 'CCompressedAnimVector3':
            o = (frame * count + element) * 6
            return tuple(_half(data[o + 2 * i:o + 2 * i + 2]) for i in range(3))
        if decoder == 'CCompressedFullVector3':
            return struct.unpack_from('<3f', data, (frame * count + element) * 12)
        if decoder == 'CCompressedDeltaVector3':
            base = struct.unpack_from('<3f', data, element * 12)
            o = count * 12 + (frame * count + element) * 6
            delta = [_half(data[o + 2 * i:o + 2 * i + 2]) for i in range(3)]
            return tuple(b + d for b, d in zip(base, delta))
        if decoder == 'CCompressedStaticQuaternion':
            return _quat48(data[element * 6:element * 6 + 6])
        if decoder == 'CCompressedAnimQuaternion':
            o = (frame * count + element) * 6
            return _quat48(data[o:o + 6])
        if decoder == 'CCompressedFullQuaternion':
            return struct.unpack_from('<4f', data, (frame * count + element) * 16)
        return None


# ---------------------------------------------------------------- AnimGraph 2 clips

RANGE_MIN = -1.0 / math.sqrt(2.0)
RANGE_LENGTH = 2.0 / math.sqrt(2.0)
SHUFFLES = ((3, 0, 1, 2), (0, 3, 1, 2), (0, 1, 3, 2), (0, 1, 2, 3))


def decode_quaternion(d0, d1, d2):
    step = RANGE_LENGTH / 0x7FFF
    a, b, c = (d0 & 0x7FFF) * step + RANGE_MIN, (d1 & 0x7FFF) * step + RANGE_MIN, d2 * step + RANGE_MIN
    w = math.sqrt(max(0.0, 1.0 - a * a - b * b - c * c))
    values = (a, b, c, w)
    return tuple(values[i] for i in SHUFFLES[((d0 >> 14) & 2) | (d1 >> 15)])


def encode_quaternion(q):
    q = qnorm(q)
    largest = max(range(4), key=lambda i: abs(q[i]))
    if q[largest] < 0: q = tuple(-c for c in q)
    rest = [q[i] for i in range(4) if i != largest]
    words = [max(0, min(0x7FFF, int(round((value - RANGE_MIN) * 0x7FFF / RANGE_LENGTH)))) for value in rest]
    return words[0] | ((largest >> 1) & 1) << 15, words[1] | (largest & 1) << 15, words[2]


def _unorm(value, start, length):
    return max(0, min(0xFFFF, int(round((value - start) / length * 0xFFFF)))) if length else 0


def decode_clip(clip):
    """Every frame of a (plain) clip as lists of (position, rotation, scale)."""
    words = struct.unpack('<%dH' % (len(clip['m_compressedPoseData']) // 2), bytes(clip['m_compressedPoseData']))
    frames = []
    for offset in clip['m_compressedPoseOffsets']:
        bones = []
        for track in clip['m_trackCompressionSettings']:
            ranges = [track[k] for k in ('m_translationRangeX', 'm_translationRangeY', 'm_translationRangeZ')]
            position = tuple(r['m_flRangeStart'] for r in ranges)
            rotation = tuple(track['m_constantRotation'])
            scale = track['m_scaleRange']['m_flRangeStart']
            if not track['m_bIsRotationStatic']:
                rotation = decode_quaternion(*words[offset:offset + 3]); offset += 3
            if not track['m_bIsTranslationStatic']:
                position = tuple(words[offset + i] / 65535.0 * r['m_flRangeLength'] + r['m_flRangeStart'] for i, r in enumerate(ranges))
                offset += 3
            if not track['m_bIsScaleStatic']:
                scale = words[offset] / 65535.0 * track['m_scaleRange']['m_flRangeLength'] + track['m_scaleRange']['m_flRangeStart']
                offset += 1
            bones.append((position, qnorm(rotation), scale))
        frames.append(bones)
    return frames


def encode_clip(node, frames, duration):
    """Write frames into a clip KV3 node in place (settings, pose data, offsets, frame count, duration)."""
    count = len(frames)
    tracks = node.get('m_trackCompressionSettings').value
    if len(tracks) != len(frames[0]): raise ValueError('Frame bone count does not match the clip tracks')
    plans, cursor = [], 0
    for index, track in enumerate(tracks):
        positions = [frame[index][0] for frame in frames]
        rotations = [qnorm(frame[index][1]) for frame in frames]
        static_rotation = all(abs(sum(a * b for a, b in zip(r, rotations[0]))) > 0.999999 for r in rotations)
        lows = [min(p[axis] for p in positions) for axis in range(3)]
        lengths = [max(p[axis] for p in positions) - lows[axis] for axis in range(3)]
        static_translation = max(lengths) < 1e-4
        plans.append((static_rotation, static_translation, lows, lengths, rotations[0]))
        for axis, name in enumerate(('m_translationRangeX', 'm_translationRangeY', 'm_translationRangeZ')):
            span = track.get(name)
            _set(span, 'm_flRangeStart', _float(positions[0][axis] if static_translation else lows[axis]))
            _set(span, 'm_flRangeLength', _float(0.1 if static_translation or lengths[axis] < 1e-6 else lengths[axis]))
        scale = track.get('m_scaleRange')
        _set(scale, 'm_flRangeStart', _float(1.0)); _set(scale, 'm_flRangeLength', _float(0.1))
        _set(track, 'm_nTrackReadOffset', _int(cursor))
        constant = rotations[0] if static_rotation else (0.0, 0.0, 0.0, 1.0)
        _set(track, 'm_constantRotation', kv3.Node(kv3.ARRAY, [_float(c) for c in constant]))
        _set(track, 'm_bIsRotationStatic', _bool(static_rotation))
        _set(track, 'm_bIsTranslationStatic', _bool(static_translation))
        _set(track, 'm_bIsScaleStatic', _bool(True))
        cursor += (0 if static_rotation else 3) + (0 if static_translation else 3)
    words, offsets = [], []
    for frame in frames:
        offsets.append(len(words))
        for (static_rotation, static_translation, lows, lengths, _), (position, rotation, _) in zip(plans, frame):
            if not static_rotation: words.extend(encode_quaternion(rotation))
            if not static_translation:
                words.extend(_unorm(position[axis], lows[axis], lengths[axis] if lengths[axis] >= 1e-6 else 0.1) for axis in range(3))
    _set(node, 'm_compressedPoseData', kv3.Node(kv3.BINARY_BLOB, struct.pack('<%dH' % len(words), *words)))
    _set(node, 'm_compressedPoseOffsets', kv3.Node(kv3.ARRAY_TYPED, [kv3.Node(kv3.UINT32, o) for o in offsets],
                                                   subtype=kv3.UINT32))
    _set(node, 'm_nNumFrames', kv3.Node(kv3.UINT32, count))
    _set(node, 'm_flDuration', _float(duration))
    root = node.get('m_rootMotion')
    if root is not None:
        _set(root, 'm_nNumFrames', _int(count))


# ---------------------------------------------------------------- installed VPK (read only)


class VpkIndex:
    """Parse a directory VPK tree once and read entries on demand (chunk archives are opened read only)."""

    def __init__(self, directory, prefixes=('animation/',)):
        self.directory = Path(directory)
        self.entries = {}
        with self.directory.open('rb') as source:
            magic, version, tree_size = struct.unpack('<III', source.read(12))
            if magic != 0x55aa1234 or version not in (1, 2): raise ValueError('Unsupported VPK header')
            self.header = (12 if version == 1 else 28) + tree_size
            source.seek(12 if version == 1 else 28)
            tree = source.read(tree_size)
        position = 0

        def string():
            nonlocal position
            end = tree.index(b'\0', position)
            value = tree[position:end].decode('utf-8', 'replace'); position = end + 1
            return value

        while True:
            extension = string()
            if not extension: break
            while True:
                folder = string()
                if not folder: break
                keep = folder == ' ' or any((folder + '/').lower().startswith(p) for p in prefixes)
                while True:
                    name = string()
                    if not name: break
                    crc, preload, archive, offset, length, end = struct.unpack_from('<IHHIIH', tree, position)
                    position += 18
                    if end != 0xffff: raise ValueError('Invalid VPK entry')
                    small = tree[position:position + preload]; position += preload
                    if keep:
                        path = ('' if folder == ' ' else folder + '/') + name + ('' if extension == ' ' else '.' + extension)
                        self.entries[path.lower()] = (crc, small, archive, offset, length)

    def read(self, path):
        crc, small, archive, offset, length = self.entries[path.lower()]
        if archive == 0x7fff:
            chunk, offset = self.directory, offset + self.header
        else:
            chunk = self.directory.with_name(self.directory.name[:-8] + '_%03d.vpk' % archive)
        with chunk.open('rb') as data:
            data.seek(offset)
            result = small + data.read(length)
        if zlib.crc32(result) != crc: raise ValueError('VPK checksum mismatch: ' + path)
        return result

    def __contains__(self, path):
        return path.lower() in self.entries


def load_kv(vpk, path):
    """(resource version, blocks, DATA guid, DATA root node) for a compiled KV3 resource."""
    version, blocks = resource_blocks(vpk.read(path))
    data = next(content for name, content in blocks if name == 'DATA')
    guid, root = read_block(data)
    return version, blocks, guid, root


# ---------------------------------------------------------------- retargeting

FINGERS = {'0': 'thumb', '1': 'index', '2': 'middle', '3': 'ring', '4': 'pinky'}


def legacy_bone_map(old_bones):
    """Old CS:GO arm/weapon bone name -> current viewmodel bone name."""
    out = {}
    for name in old_bones:
        low = name.lower()
        if low == 'weapon_hand_r':
            out[name] = 'wpn'
            continue
        if not low.startswith('v_weapon_bip01_'): continue
        rest = low[len('v_weapon_bip01_'):]
        side, _, part = rest.partition('_')
        side = side.upper()
        if part == 'forearm': out[name] = 'arm_lower_' + side
        elif part == 'hand': out[name] = 'hand_' + side
        elif part.startswith('finger') and len(part) in (7, 8) and part[6] in FINGERS:
            out[name] = 'finger_%s_%s_%s' % (FINGERS[part[6]], part[7] if len(part) == 8 else '0', side)
    return out


def weapon_bone_map(old_bones, secondary_bones):
    out = {}
    for name in old_bones:
        low = name.lower()
        if low.startswith('v_weapon_bip01_') or low == 'weapon_hand_r': continue
        best = None
        for bone in secondary_bones:
            if bone.lower() in ('weapon', 'weapon_offset'): continue
            if low == bone.lower() or (low.startswith('v_weapon_') and low.endswith('_' + bone.lower())):
                if best is None or len(bone) > len(best): best = bone
        if best: out[name] = best
    return out


class Rig:
    """Current viewmodel rig: primary skeleton plus an optional weapon skeleton attached to ``wpn``."""

    def __init__(self, primary, secondary=None):
        self.names = list(primary['m_boneIDs'])
        self.parents = list(primary['m_parentIndices'])
        self.primary_count = len(self.names)
        if secondary:
            attach = self.names.index('wpn')
            for name, parent in zip(secondary['m_boneIDs'], secondary['m_parentIndices']):
                self.names.append(name)
                self.parents.append(attach if parent < 0 else parent + self.primary_count)
        self.index = {name: i for i, name in enumerate(self.names)}


def retarget(old, old_frames, old_idle, rig, new_idle):
    """Map old local frames onto the rig. ``new_idle`` holds the rig's local idle pose (primary + secondary)."""
    old_idle_ms = to_model(old_idle, old.parents)
    new_idle_ms = to_model(new_idle, rig.parents)
    mapping = dict(legacy_bone_map(old.bones))
    secondary_names = rig.names[rig.primary_count:]
    mapping.update(weapon_bone_map(old.bones, secondary_names))
    # Dual pistols keep one gun root per hand in the weapon skeleton; CS2 leaves ``wpn`` still for them.
    exact = {name.lower(): name for name in secondary_names if name.lower() not in ('weapon', 'weapon_offset')}
    for old_name in old.bones:
        if old_name.lower() in exact: mapping[old_name] = exact[old_name.lower()]
    pairs = {}
    for old_name, new_name in mapping.items():
        if new_name in rig.index:
            # A secondary bone may share a name with a primary one; prefer the weapon skeleton copy.
            j = max(i for i, n in enumerate(rig.names) if n == new_name)
            i = old.index[old_name.lower()]
            pairs[j] = (i, tmul(tinv(old_idle_ms[i]), new_idle_ms[j]))
    rotation_only = {j for j in pairs if rig.names[j].startswith('finger_')}
    from_child = {}
    for side in 'LR':
        shoulder, lower = 'armUpperShoulder_' + side, 'arm_lower_' + side
        if shoulder in rig.index and lower in rig.index and rig.index[lower] in pairs:
            from_child[rig.index[shoulder]] = rig.index[lower]
    follow = {}
    for side in 'LR':
        target, hand = 'wpnHand_' + side, 'hand_' + side
        if target in rig.index and hand in rig.index and rig.index[hand] in pairs:
            h, t = rig.index[hand], rig.index[target]
            follow[t] = (h, tmul(tinv(new_idle_ms[h]), new_idle_ms[t]))
    result = []
    for frame in old_frames:
        old_ms = to_model(frame, old.parents)
        targets = {j: tmul(old_ms[i], offset) for j, (i, offset) in pairs.items()}
        ms = []
        for j, parent in enumerate(rig.parents):
            base = ms[parent] if parent >= 0 else IDENTITY
            if j in rotation_only:
                ms.append((tmul(base, (new_idle[j][0], (0.0, 0.0, 0.0, 1.0)))[0], targets[j][1]))
            elif j in targets:
                ms.append(targets[j])
            elif j in from_child:
                child = from_child[j]
                ms.append(tmul(targets[child], tinv(new_idle[child])))
            elif j in follow:
                hand, offset = follow[j]
                ms.append(tmul(targets[hand], offset))
            else:
                ms.append(tmul(base, new_idle[j]))
        result.append(to_local(ms, rig.parents))
    return result, sorted(rig.names[j] for j in pairs)


# ---------------------------------------------------------------- conversion driver

VIEWMODEL_ROOT = 'animation/anims/viewmodel/'
SPECIAL_MODELS = {
    'rifle/_default_rifle': 'm4a1_silencer', 'pistol/_default_pistol': 'usp_silencer',
    'grenade/_default_grenade': 'grenade/decoy', 'knife/_default_knife': 'knife/knife_default_ct',
    'rifle/rifle_ak': 'ak47',
}
CLIP_KINDS = ('draw', 'lookat', 'reload')
# Shotgun reloads are a start/loop/end set in CS:GO but a single shell-insert clip in CS2.
SKIP_RELOAD = ('nova', 'sawedoff', 'xm1014')


def old_model_folder(folder):
    if folder in SPECIAL_MODELS: return SPECIAL_MODELS[folder]
    category, name = folder.split('/', 1)
    if category == 'knife': return 'knife/' + name
    if category == 'equipment': return name
    if category == 'grenade': return 'grenade/' + name[len('grenade_'):]
    return name.split('_', 1)[1]


def find_old_model(source_root, folder):
    directory = Path(source_root) / 'weapons' / 'models' / old_model_folder(folder)
    if not directory.is_dir(): return None
    models = sorted(p for p in directory.glob('weapon_*.vmdl_c') if not p.stem.endswith('_mag'))
    return models[0] if models else None


def old_sequence(stem, names):
    """Legacy sequence for an installed clip stem, or None when the clip should stay as installed."""
    kind = next((k for k in CLIP_KINDS if stem.startswith(k)), None)
    if kind is None: return None
    rest = stem[len(kind):]
    if kind == 'draw':
        second = rest.startswith('2_') or rest.startswith('_2_')
        for name in (('firstperson_draw2',) if second else ()) + ('firstperson_draw',):
            if name in names: return name
        return None
    if kind == 'lookat':
        if '_transfixcancel' in rest: return None
        number = rest[:2]
        for name in ('firstperson_lookat' + number, '@firstperson_lookat' + number, 'firstperson_lookat01',
                     '@firstperson_lookat01'):
            if name in names: return name
        return None
    second = rest.startswith('2')
    empty = rest.lstrip('2').startswith('_empty')
    candidates = []
    if empty: candidates += ['firstperson_empty_reload', 'firstperson_reload_empty']
    if second: candidates += ['firstperson_reload2']
    candidates += ['firstperson_reload']
    return next((name for name in candidates if name in names), None)


def _pose(frame):
    return [(tuple(p), tuple(q)) for p, q, _ in frame]


def _idle_clip(clips):
    plain_names = [c for c in clips if c.rsplit('/', 1)[1].startswith(('idle_', 'idle1_'))]
    good = [c for c in plain_names if not any(t in c for t in ('slide_back', 'empty', 'from_activity'))]
    ordered = sorted(good or plain_names, key=lambda c: (not c.rsplit('/', 1)[1].startswith('idle_'), c))
    return ordered[0] if ordered else None


def _old_idle(model):
    for name in ('firstperson_idle', 'firstperson_idle1'):
        if name in model.anims: return name
    return next((n for n in model.anims if 'idle' in n and not model.anims[n]['delta']), None)


def _scale_events(root, factor):
    events = root.get('m_events')
    if events is None or factor == 1.0: return
    for event in events.value:
        for field in ('m_flStartTime', 'm_flDuration'):
            holder = event.get(field)
            if holder is not None and holder.get('m_flValue') is not None:
                _set(holder, 'm_flValue', kv3.Node(holder.get('m_flValue').type, holder.get('m_flValue').value * factor))


class Converter:
    def __init__(self, vpk, source_root):
        self.vpk = vpk if isinstance(vpk, VpkIndex) else VpkIndex(vpk)
        self.source_root = Path(source_root)
        self.skeletons, self.models = {}, {}

    def skeleton(self, path):
        if path not in self.skeletons:
            self.skeletons[path] = plain(load_kv(self.vpk, path + '_c')[3])
        return self.skeletons[path]

    def model(self, path):
        if path not in self.models: self.models[path] = LegacyModel(path.read_bytes())
        return self.models[path]

    def folders(self):
        grouped = {}
        for path in self.vpk.entries:
            if path.startswith(VIEWMODEL_ROOT) and path.endswith('.vnmclip_c'):
                folder = path[len(VIEWMODEL_ROOT):].rsplit('/', 1)[0]
                grouped.setdefault(folder, []).append(path)
        return {folder: sorted(clips) for folder, clips in sorted(grouped.items())}

    def context(self, folder, clips):
        old_path = find_old_model(self.source_root, folder)
        if old_path is None: raise ValueError('no legacy model')
        old = self.model(old_path)
        idle_path, old_idle_name = _idle_clip(clips), _old_idle(old)
        if idle_path is None or old_idle_name is None: raise ValueError('no idle pose')
        idle = plain(load_kv(self.vpk, idle_path)[3])
        return old, idle, old.sample(old_idle_name)[0]

    def retarget_clip(self, old, sequence, old_idle, idle, clip):
        secondary = clip['m_secondaryAnimations'][0] if clip['m_secondaryAnimations'] else None
        rig = Rig(self.skeleton(clip['m_skeleton']), self.skeleton(secondary['m_skeleton']) if secondary else None)
        new_idle = _pose(decode_clip(idle)[0])
        if secondary:
            match = [s for s in idle['m_secondaryAnimations'] if s['m_skeleton'] == secondary['m_skeleton']]
            if not match: raise ValueError('idle has no %s pose' % secondary['m_skeleton'])
            new_idle += _pose(decode_clip(match[0])[0])
        if len(new_idle) != len(rig.names): raise ValueError('idle pose does not match the rig')
        frames, mapped = retarget(old, old.sample(sequence), old_idle, rig, new_idle)
        return rig, frames, mapped

    def convert_clip(self, path, old, sequence, old_idle, idle):
        version, blocks, guid, root = load_kv(self.vpk, path)
        clip = plain(root)
        if clip['m_bIsAdditive']: raise ValueError('additive clip')
        if clip['m_floatChannelData']: raise ValueError('float channels')
        identity = (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        for transform in (clip['m_rootMotion'] or {}).get('m_transforms') or []:
            if any(abs(a - b) > 1e-4 for a, b in zip(transform, identity)): raise ValueError('root motion')
        rig, frames, mapped = self.retarget_clip(old, sequence, old_idle, idle, clip)
        if 'hand_R' not in mapped or not {'wpn', 'weapon_hand_r'} & set(mapped): raise ValueError('legacy rig not recognised')
        anim = old.anims[sequence]
        duration = max(anim['frames'] - 1, 1) / anim['fps']
        primary = [[(p, q, 1.0) for p, q in frame[:rig.primary_count]] for frame in frames]
        encode_clip(root, primary, duration)
        secondaries = root.get('m_secondaryAnimations').value
        if secondaries:
            encode_clip(secondaries[0], [[(p, q, 1.0) for p, q in frame[rig.primary_count:]] for frame in frames], duration)
        _scale_events(root, duration / clip['m_flDuration'] if clip['m_flDuration'] else 1.0)
        data = kv3.write_kv3(guid, root)
        return kv3.write_resource(version, [(name, data if name == 'DATA' else content) for name, content in blocks])

    def accuracy(self, folder, clips, old, old_idle, idle):
        """Largest model-space distance between retargeted legacy lookat01 and the installed one (time aligned)."""
        installed = [c for c in clips if c.rsplit('/', 1)[1].startswith('lookat01_') and '_draw' not in c
                     and '_transfix' not in c and '_lgcy' not in c]
        if not installed or 'firstperson_lookat01' not in old.anims: return None
        clip = plain(load_kv(self.vpk, installed[0])[3])
        rig, frames, _ = self.retarget_clip(old, 'firstperson_lookat01', old_idle, idle, clip)
        current = decode_clip(clip)
        secondary = decode_clip(clip['m_secondaryAnimations'][0]) if clip['m_secondaryAnimations'] else None
        worst = 0.0
        bones = [rig.index[n] for n in ('wpn', 'hand_R', 'hand_L') if n in rig.index]
        for index in range(0, len(current), max(1, len(current) // 24)):
            source = round(index * (len(frames) - 1) / max(1, len(current) - 1))
            mine = to_model(frames[source], rig.parents)
            pose = _pose(current[index]) + (_pose(secondary[index]) if secondary else [])
            theirs = to_model(pose, rig.parents)
            for bone in bones:
                worst = max(worst, math.dist(mine[bone][0], theirs[bone][0]))
        return round(worst, 3)

    def run(self, progress=None, check=False):
        """Return ({clip path: compiled bytes}, report)."""
        outputs, report = {}, {'converted': [], 'kept': [], 'skipped': [], 'accuracy': {}}
        for folder, clips in self.folders().items():
            targets = []
            for path in clips:
                stem = path.rsplit('/', 1)[1][:-len('.vnmclip_c')]
                if not stem.startswith(CLIP_KINDS) or stem.startswith('reload') and folder.endswith(SKIP_RELOAD):
                    continue
                targets.append((path, stem))
            if not targets: continue
            try:
                old, idle, old_idle = self.context(folder, clips)
            except (ValueError, OSError, KeyError) as error:
                report['skipped'] += [(path, str(error)) for path, _ in targets]
                continue
            if check:
                try: report['accuracy'][folder] = self.accuracy(folder, clips, old, old_idle, idle)
                except (ValueError, KeyError) as error: report['accuracy'][folder] = str(error)
            for path, stem in targets:
                sequence = old_sequence(stem, old.anims)
                if sequence is None:
                    report['kept'].append(path); continue
                try:
                    outputs[path] = self.convert_clip(path, old, sequence, old_idle, idle)
                    report['converted'].append((path, sequence))
                except (ValueError, KeyError, IndexError, struct.error) as error:
                    report['skipped'].append((path, str(error)))
            if progress: progress(folder)
        return outputs, report


# ---------------------------------------------------------------- owned search path

FOLDER = 'cs2_gc_csgo_anims'
COMMENT = 'cs2_gc CS:GO viewmodel animations'
OWNER = 'cs2-gc-csgo-animations-v1'
MANIFEST = 'cs2_gc_csgo_anims_manifest.json'
CONVERTER_VERSION = 1


SOURCE_FILE = 'cs2_gc_csgo_source.txt'  # written next to the proxy by the launcher, pointing at its Steam download
DOWNLOADED_SOURCE = Path('.csreborn') / 'csgo-animations' / 'csgo'  # launcher's Steam download, below the install root


def resolve_source(folder):
    """Accept the old build's csgo folder itself or a folder that holds it (csgo or game/csgo)."""
    folder = Path(folder).expanduser()
    for candidate in (folder, folder / 'csgo', folder / 'game' / 'csgo'):
        if (candidate / 'weapons' / 'models').is_dir():
            return candidate
    return folder


def source_root(proxy_directory):
    """The developer override, else the launcher's Steam download of the first CS2 Limited Test."""
    configured = os.environ.get('CS2GC_CSGO_ANIM_SOURCE')
    if configured:
        return resolve_source(configured)
    proxy = Path(proxy_directory).resolve()
    recorded = proxy / SOURCE_FILE
    if recorded.is_file():
        text = recorded.read_text(encoding='utf-8-sig', errors='replace').strip()
        if text:
            return resolve_source(text)
    return proxy.parents[2] / DOWNLOADED_SOURCE


def installed_fingerprint(vpk):
    digest = hashlib.sha256(b'v%d' % CONVERTER_VERSION)
    for path in sorted(vpk.entries):
        if path.startswith(VIEWMODEL_ROOT) or path.startswith('animation/skeletons/'):
            digest.update(('%s:%08x\n' % (path, vpk.entries[path][0])).encode())
    return digest.hexdigest()


def source_fingerprint(root):
    models = Path(root) / 'weapons' / 'models'
    digest = hashlib.sha256()
    for path in sorted(models.rglob('weapon_*.vmdl_c')):
        if not path.stem.endswith('_mag'):
            digest.update(('%s:%d\n' % (path.relative_to(models).as_posix(), path.stat().st_size)).encode())
    return digest.hexdigest()


def _outputs(mod):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(mod.glob('pak01_*.vpk'))}


def install(proxy_directory, *, enabled, root=None, log=None):
    """Mount (or unmount) the converted CS:GO clips; conversion runs only when its inputs change."""
    from native_tradeups import atomic_write, mount_gameinfo, read_text
    proxy = Path(proxy_directory).resolve()
    game = proxy.parent.parent
    info = game / 'csgo/gameinfo.gi'
    mod = game / FOLDER
    manifest_path = mod / MANIFEST
    if not info.is_file():
        return 'unavailable: installed gameinfo.gi not found'
    previous = None
    if manifest_path.exists():
        previous = json.loads(read_text(manifest_path))
        if previous.get('owner') != OWNER:
            raise ValueError('CS:GO animation folder is not owned by this feature')
    elif mod.exists() and any(mod.iterdir()):
        raise ValueError('CS:GO animation folder contains unowned files')
    current = read_text(info)

    def unmount(message):
        mounted = mount_gameinfo(current, False, FOLDER, COMMENT)
        if mounted != current:
            atomic_write(info, mounted)
        return message

    if not enabled:
        return unmount('disabled; CS2 animations selected (restart CS2 if it is running)')
    vpk = VpkIndex(game / 'csgo/pak01_dir.vpk')
    installed = installed_fingerprint(vpk)
    root = Path(root) if root is not None else source_root(proxy)
    available = (root / 'weapons' / 'models').is_dir()
    source = source_fingerprint(root) if available else None
    cached = (previous and previous.get('version') == CONVERTER_VERSION and previous.get('installed') == installed
              and (source is None or previous.get('source') == source)
              and previous.get('outputs_sha256') and _outputs(mod) == previous['outputs_sha256'])
    if cached:
        status = 'cached %d converted clips' % previous.get('converted', 0)
    else:
        if not available:
            return unmount('unavailable: CS:GO animation source not found at %s; CS2 animations kept' % root)
        if log: log('converting CS:GO viewmodel animations from %s (one time, about a minute)' % root)
        outputs, report = Converter(vpk, root).run()
        if not outputs:
            return unmount('unavailable: no CS:GO animation could be converted; CS2 animations kept')
        mod.mkdir(parents=True, exist_ok=True)
        from vpk_pack import pack
        pack(mod, extra=sorted(outputs.items()))
        atomic_write(manifest_path, json.dumps({
            'owner': OWNER, 'version': CONVERTER_VERSION, 'installed': installed, 'source': source,
            'converted': len(report['converted']), 'kept': [path for path in report['kept']],
            'skipped': [list(item) for item in report['skipped']], 'outputs_sha256': _outputs(mod),
        }, indent=2) + '\n')
        status = 'converted %d clips (%d kept as CS2, %d skipped)' % (
            len(report['converted']), len(report['kept']), len(report['skipped']))
    mounted = mount_gameinfo(current, True, FOLDER, COMMENT)
    if mounted != current:
        backup = info.with_name(info.name + '.' + FOLDER + '_backup')
        if not backup.exists():
            with backup.open('x', encoding='utf-8', newline='') as output:
                output.write(current)
        atomic_write(info, mounted)
        return status + '; restart CS2 to load the CS:GO animations'
    return status + '; installed'


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert the CS:GO viewmodel animations (read only by default).')
    parser.add_argument('--game', type=Path, default=Path(r'C:\CSReborn\game'), help='CS2 game folder')
    parser.add_argument('--source', type=Path, default=None, help='Old animation folder (default: CS2GC_CSGO_ANIM_SOURCE or the launcher download)')
    parser.add_argument('--install', choices=('csgo', 'cs2'), help='Mount (csgo) or unmount (cs2) the owned override')
    args = parser.parse_args()
    if args.install:
        print(install(args.game / 'bin/win64', enabled=args.install == 'csgo', root=args.source, log=print))
        return 0
    vpk = VpkIndex(args.game / 'csgo/pak01_dir.vpk')
    outputs, report = Converter(vpk, args.source or source_root(args.game / 'bin/win64')).run(progress=print, check=True)
    print('converted %d, kept %d, skipped %d, %.2f MB' % (len(report['converted']), len(report['kept']),
          len(report['skipped']), sum(map(len, outputs.values())) / 1e6))
    for item in report['skipped']:
        print('skipped:', *item)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
