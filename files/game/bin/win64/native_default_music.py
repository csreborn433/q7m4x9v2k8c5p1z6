"""Import authorized MPEG-1 Layer III recordings and replace only CS2's default kit.

`import` produces the portable, audio-only bundle. `build` reads the local stock
pak and writes a standalone pack outside the game. Normal launcher preparation
mounts the generated pack; cs2_gc_no_default_music.txt beside the DLL opts out.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import NamedTuple

import kv3
from native_finishes import Source
from native_tradeups import atomic_write, mount_gameinfo, read_text
from resource_files import publish
from vpk_pack import build as build_vpk, KILL_SWITCH

KIT = 'valve_cs2_01'  # music_definitions/1 on client 2000933
SOUNDS = f'sounds/music/{KIT}/'
EVENTS = f'soundevents/music/{KIT}/game_sounds_music.vsndevts_c'
BUNDLE = 'cs2_gc_default_music_assets'
FOLDER = 'cs2_gc_default_music'
COMMENT = 'cs2_gc default music kit'
OWNER = 'cs2-gc-default-music-v1'
MANIFEST = FOLDER + '_manifest.json'
DISABLE = 'cs2_gc_no_default_music.txt'
PACKS = ('pak01_dir.vpk', 'pak01_000.vpk')
DIRECT = ('bombplanted', 'bombtenseccount', 'chooseteam', 'deathcam', 'lostround',
          'mainmenu', 'roundmvpanthem_01', 'roundtenseccount', 'startaction_01',
          'startaction_02', 'startround_01', 'wonround')
# This legacy kit has two round starts but no dedicated match bookends.
CUES = {**{s: s for s in DIRECT}, 'startofmatch': 'startround_02', 'endofmatch': 'wonround'}
FILENAMES = tuple(sorted({stem + '.mp3' for stem in CUES.values()}))
BITRATES = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
SOUND_DATA = struct.Struct('<HBBiIfIIIIIIII')  # VSND v4 (ValveResourceFormat Sound.Read)


class Recording(NamedTuple):
    stream: bytes
    rate: int
    channels: int
    samples: int


def recording(data):
    """Validate every frame; keep the encoded stream (including its Xing seek table), not ID3."""
    if data.startswith(b'ID3'):
        if len(data) < 10 or data[3] not in (3, 4) or any(n >= 128 for n in data[6:10]):
            raise ValueError('Unsupported ID3v2 header')
        size = sum(n << shift for n, shift in zip(data[6:10], (21, 14, 7, 0)))
        data = data[10 + size + (10 if data[3] == 4 and data[5] & 16 else 0):]
    if data[-128:-125] == b'TAG':
        data = data[:-128]
    pos = frames = rate = channels = 0
    first_size = 0
    while pos < len(data):
        header = data[pos:pos+4]
        if len(header) != 4 or header[0] != 255 or header[1] & 254 != 250:
            raise ValueError('Expected contiguous MPEG-1 Layer III frames')
        bitrate = BITRATES[header[2] >> 4]
        hz = (44100, 48000, 32000, 0)[(header[2] >> 2) & 3]
        ch = 1 if header[3] >> 6 == 3 else 2
        if not bitrate or not hz or (frames and (hz, ch) != (rate, channels)):
            raise ValueError('Unsupported or changing MP3 format')
        rate, channels = hz, ch
        length = 144000 * bitrate // hz + ((header[2] >> 1) & 1)
        if pos + length > len(data):
            raise ValueError('Truncated MP3 frame')
        if not frames:
            first_size = length
        frames += 1
        pos += length
    if frames < 2:
        raise ValueError('Empty or incomplete MP3 recording')
    x = 4 + (0 if data[1] & 1 else 2) + (17 if channels == 1 else 32)
    samples = frames * 1152
    if data[x:x+4] in (b'Info', b'Xing'):
        flags = int.from_bytes(data[x+4:x+8], 'big')
        if flags & 1 and int.from_bytes(data[x+8:x+12], 'big') != frames - 1:
            raise ValueError('MP3 seek table does not match the frame count')
        samples -= 1152  # the first frame carries the seek table, not audio
        tag = x + 8 + sum(n for i, n in enumerate((4, 4, 100, 4)) if flags & (1 << i))
        if tag + 24 <= first_size and data[tag:tag+4] in (b'LAME', b'Lavc'):
            trim = int.from_bytes(data[tag+21:tag+24], 'big')
            samples -= (trim >> 12) + (trim & 4095)
    if samples <= 0:
        raise ValueError('MP3 has no playable samples')
    return Recording(data, rate, channels, samples)


def bundle_files(folder):
    """Fixed allowlist shared by the importer and release builder; never ship game resources."""
    paths = [Path(folder) / name for name in FILENAMES]
    for path in paths:
        if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= 64 * 1024 * 1024:
            raise ValueError('Missing or invalid default music recording: ' + path.name)
    return paths


def import_bundle(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Import into a separate bundle directory')
    if destination.exists() and any(p.name not in FILENAMES for p in destination.iterdir()):
        raise ValueError('Not a dedicated default music bundle directory')
    songs = {p.name: recording(p.read_bytes()).stream for p in bundle_files(source)}
    for name, stream in songs.items():
        publish(destination / name, stream)


def replace_sound(original, song):
    size = int.from_bytes(original[:4], 'little')
    version, blocks = kv3.read_resource(original[:size])
    data = dict(blocks).get('DATA', b'')
    if version != 4 or len(data) != SOUND_DATA.size:
        raise ValueError('Unsupported stock default VSND format')
    _, codec, _, _, _, _, sentence, header, header_size, stream_size, off, count, morph, _ = SOUND_DATA.unpack(data)
    if codec != 2 or any((sentence, header, header_size, off, count, morph)) or stream_size != len(original) - size:
        raise ValueError('Unsupported stock default VSND stream')
    # Old loop markers belong to the donor recording, not the replacement.
    sound = SOUND_DATA.pack(song.rate, 2, song.channels, -1, song.samples, song.samples / song.rate,
                            0, 0, 0, len(song.stream), 0, 0, 0, 0)
    return kv3.write_resource(version, [(k, sound if k == 'DATA' else v) for k, v in blocks]) + song.stream


def update_events(original, durations):
    version, blocks = kv3.read_resource(original)
    guid, root = kv3.read_kv3(dict(blocks)['DATA'])
    seen = set()
    for event, node in root.value:
        if not event.endswith('.' + KIT):
            raise ValueError('Unexpected event outside the default music kit: ' + event)
        refs, duration = node.get('vsnd_files'), node.get('vsnd_duration')
        if not refs or not duration or duration.value <= 0:
            raise ValueError('Missing stock music sound or duration: ' + event)
        names = [refs.value] if refs.type == kv3.STRING else [ref.value for ref in refs.value]
        if not names or any(name not in durations for name in names):
            raise ValueError('Unrecognized default music sound in ' + event)
        seen.update(names)
        old = duration.value
        duration.value = max(durations[name] for name in names)
        # The stock buy-music loop/seek grid is expressed in seconds. Keep its
        # relative positions on the new track, not offsets from the old song.
        for i, name in enumerate(names, 1):
            for field in ('startpoint', 'endpoint', 'syncpoints'):
                timing = node.get(f'{field}_{i:02d}')
                if timing is not None:
                    for point in timing.value if isinstance(timing.value, list) else [timing]:
                        if point.value:
                            point.value = min(durations[name], durations[name] * point.value / old)
    if seen != set(durations):
        raise ValueError('Default music event coverage differs from the supported client')
    return kv3.write_resource(version, [(k, kv3.write_kv3(guid, root) if k == 'DATA' else v) for k, v in blocks])


def resources(stock, songs):
    files, durations = {}, {}
    for cue, name in CUES.items():
        path = SOUNDS + cue + '.vsnd'
        original = stock.read(path + '_c')
        if not original:
            raise ValueError('Missing stock default cue ' + path)
        song = songs[name]
        files[path + '_c'] = replace_sound(original, song)
        durations[path] = song.samples / song.rate
    original = stock.read(EVENTS)
    if not original:
        raise ValueError('Missing stock default music events')
    files[EVENTS] = update_events(original, durations)
    return files


def state(folder):
    if folder.resolve() != folder.parent.resolve() / folder.name:
        raise ValueError('Default music output must not be a link to another folder')
    if not folder.exists():
        return {}
    if any(p.is_symlink() or p.name not in (*PACKS, MANIFEST) for p in folder.iterdir()):
        raise ValueError('Default music folder contains unowned files')
    if not any(folder.iterdir()):
        return {}
    data = json.loads(read_text(folder / MANIFEST)) if (folder / MANIFEST).is_file() else {}
    if data.get('owner') != OWNER:
        raise ValueError('Default music folder is not owned by this feature')
    return data


def sha(data):
    return hashlib.sha256(data).hexdigest()


def generate(game, bundle, folder):
    previous = state(folder)
    directory = game / 'csgo/pak01_dir.vpk'
    audio = {p.stem: p.read_bytes() for p in bundle_files(bundle)}
    # The stock directory includes CRCs for the external sound/event payloads.
    inputs = {'stock': sha(directory.read_bytes()), 'generator': sha(Path(__file__).read_bytes()),
              'songs': {name: sha(data) for name, data in audio.items()}}
    if previous.get('inputs') == inputs and all((folder / name).is_file() and
            sha((folder / name).read_bytes()) == previous.get('packs', {}).get(name) for name in PACKS):
        return 'validated existing default music kit'
    songs = {name: recording(data) for name, data in audio.items()}
    files = resources(Source(vpk=directory), songs)
    index, archive = build_vpk(sorted(files.items()))
    manifest = {'owner': OWNER, 'inputs': inputs, 'packs': dict(zip(PACKS, map(sha, (index, archive)))),
                'cues': CUES}
    # Mark the directory as ours before publishing anything; a partial write
    # can be repaired on the next preparation without adopting unrelated files.
    if not previous:
        atomic_write(folder / MANIFEST, json.dumps({'owner': OWNER}))
    publish(folder / PACKS[1], archive)
    publish(folder / PACKS[0], index)
    atomic_write(folder / MANIFEST, json.dumps(manifest, indent=2) + '\n')
    return 'prepared default menu and match music'


def prepare(proxy):
    proxy = Path(proxy).resolve()
    game = proxy.parents[1]
    folder, bundle = game / FOLDER, proxy / BUNDLE
    if not folder.exists() and not bundle.exists():
        return 'no bundled default music kit'
    info = game / 'csgo/gameinfo.gi'
    current = read_text(info)
    enabled = bundle.exists() and not any((proxy / n).exists() for n in (DISABLE, KILL_SWITCH))
    mounted = mount_gameinfo(current, enabled, FOLDER, COMMENT)
    if enabled:
        result = generate(game, bundle, folder)
    else:
        state(folder)
        result = 'disabled'
    if mounted != current:
        backup = info.with_name(info.name + '.' + FOLDER + '_backup')
        if not backup.exists():
            with backup.open('x', encoding='utf-8', newline='') as out:
                out.write(current)
        atomic_write(info, mounted)
    if not enabled and folder.exists():
        for name in (*PACKS, MANIFEST):
            (folder / name).unlink(missing_ok=True)
        folder.rmdir()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    imp = commands.add_parser('import', help='Import only the 13 owned recordings')
    imp.add_argument('--source', type=Path, required=True)
    imp.add_argument('--bundle', type=Path, required=True)
    build = commands.add_parser('build', help='Generate a pack without mounting or changing the installed game')
    build.add_argument('--game', type=Path, required=True, help='Installed game folder containing csgo')
    build.add_argument('--bundle', type=Path, default=Path(__file__).with_name(BUNDLE))
    build.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'import':
        import_bundle(args.source, args.bundle)
        print(f'Imported {len(FILENAMES)} recordings to {args.bundle}')
    else:
        folder = (args.output / FOLDER).resolve()
        if any(folder.is_relative_to(p.resolve()) or p.resolve().is_relative_to(folder)
               for p in (args.game, args.bundle)):
            parser.error('--output must be separate from the installed game and the bundle')
        print(generate(args.game, args.bundle, folder) + ': ' + str(folder))


if __name__ == '__main__':
    main()
