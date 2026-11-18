"""Replace the CS2 startup intro movie with a custom video.

CS2 plays ``file://{resources}/videos/intro.webm`` at launch (switching to
``intro720p.webm`` on displays at or below 720p). Both are loose files under
``csgo/panorama/videos/`` and are not packed in any mounted VPK, so an override
folder mounted earlier in the search path wins cleanly. This helper mounts an
owned ``cs2_gc_intro`` folder ahead of ``csgo`` and drops the transcoded WebM
files there. No original game file is edited; removing the folder and the mount
line restores the stock intro.

The source video must be transcoded to WebM first (VP9/Opus for ``intro.webm``,
VP8/Vorbis for ``intro720p.webm``); this helper only copies the results.
"""
import argparse
import hashlib
import json
from pathlib import Path

from native_tradeups import atomic_write, mount_gameinfo, read_text

FOLDER = 'cs2_gc_intro'
COMMENT = 'cs2_gc intro movie'
OWNER = 'cs2-gc-intro-movie-v1'
MANIFEST = 'cs2_gc_intro_manifest.json'
# (override-relative target, source filename next to --source)
TARGETS = (('panorama/videos/intro.webm', 'intro.webm'),
           ('panorama/videos/intro720p.webm', 'intro720p.webm'))


def _game_from(proxy_directory):
    proxy = Path(proxy_directory).resolve()
    return proxy.parent.parent


def _transcode_ffmpeg(ffmpeg, source, out_dir):
    """Encode source to the two WebM variants. Returns {target_name: bytes}."""
    import subprocess
    out_dir = Path(out_dir)
    jobs = (
        ('intro.webm', ['-c:v', 'libvpx-vp9', '-crf', '30', '-b:v', '0', '-deadline', 'good',
                        '-cpu-used', '2', '-row-mt', '1', '-pix_fmt', 'yuv420p',
                        '-c:a', 'libopus', '-b:a', '160k', '-ar', '48000']),
        ('intro720p.webm', ['-vf', 'scale=1280:720', '-c:v', 'libvpx', '-b:v', '1500k', '-crf', '8',
                            '-deadline', 'good', '-cpu-used', '1', '-pix_fmt', 'yuv420p',
                            '-c:a', 'libvorbis', '-q:a', '4']),
    )
    produced = {}
    for name, args in jobs:
        target = out_dir / name
        command = [str(ffmpeg), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(source), *args, str(target)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0 or not target.is_file():
            raise ValueError('ffmpeg failed for ' + name + ': ' + result.stderr.strip()[:400])
        produced[name] = target.read_bytes()
    return produced


def prepare(proxy_directory, enabled=True, source=None, ffmpeg=None):
    """Install or remove the intro override.

    enabled=True mounts the folder and writes the WebM files. ``source`` may be
    a directory that already contains intro.webm/intro720p.webm, or a video file
    (e.g. .mp4) to transcode with ``ffmpeg``. With no source, existing files in
    the override folder are kept and only the mount is (re)applied.
    enabled=False removes the mount line and the owned folder.
    """
    proxy = Path(proxy_directory).resolve()
    game = _game_from(proxy)
    info = game / 'csgo/gameinfo.gi'
    mod = game / FOLDER
    manifest_path = mod / MANIFEST
    if not info.is_file():
        return 'unavailable: installed gameinfo.gi not found'
    current = read_text(info)
    previous = None
    if manifest_path.exists():
        previous = json.loads(read_text(manifest_path))
        if previous.get('owner') != OWNER:
            raise ValueError('Intro folder is not owned by this feature')
    elif mod.exists() and any(mod.iterdir()):
        raise ValueError('Intro folder contains unowned files')

    mounted = mount_gameinfo(current, bool(enabled), FOLDER, COMMENT)
    if not enabled:
        if mod.exists():
            import shutil
            shutil.rmtree(mod)
        if mounted != current:
            atomic_write(info, mounted)
            return 'disabled; restart CS2 once to unload the intro override'
        return 'disabled'

    # Resolve the WebM payloads.
    payloads = {}
    if source is not None:
        source = Path(source)
        if source.is_dir():
            for target, name in TARGETS:
                candidate = source / name
                if not candidate.is_file():
                    raise ValueError('Source folder is missing ' + name)
                payloads[target] = candidate.read_bytes()
        elif source.is_file():
            if not ffmpeg:
                raise ValueError('Transcoding a video file requires --ffmpeg')
            import tempfile
            with tempfile.TemporaryDirectory() as scratch:
                encoded = _transcode_ffmpeg(ffmpeg, source, scratch)
            for target, name in TARGETS:
                payloads[target] = encoded[name]
        else:
            raise ValueError('Intro source not found: ' + str(source))

    changed = mounted != current
    written = {}
    for target, _ in TARGETS:
        data = payloads.get(target)
        destination = mod / target
        if data is None:
            if not destination.is_file():
                raise ValueError('No source supplied and ' + target + ' is not already present')
            data = destination.read_bytes()
        written[target] = hashlib.sha256(data).hexdigest()
        if not destination.is_file() or destination.read_bytes() != data:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_name(destination.name + '.tmp')
            temp.write_bytes(data)
            temp.replace(destination)
            changed = True

    manifest = dict(owner=OWNER, files=written)
    atomic_write(manifest_path, json.dumps(manifest, indent=2) + '\n')
    if mounted != current:
        backup = info.with_name(info.name + '.' + FOLDER + '_backup')
        if not backup.exists():
            with backup.open('x', encoding='utf-8', newline='') as output:
                output.write(current)
        atomic_write(info, mounted)
    return ('prepared custom intro; RESTART CS2 ONCE to load it' if changed else
            'installed: custom intro; live verification needed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy-dir', type=Path, required=True,
                        help='game/bin/win64 directory (game root is two levels up)')
    parser.add_argument('--disable', action='store_true', help='Remove the override and restore the stock intro')
    parser.add_argument('--source', type=Path,
                        help='Folder with intro.webm/intro720p.webm, or a video file to transcode')
    parser.add_argument('--ffmpeg', type=Path, help='ffmpeg executable used when --source is a video file')
    args = parser.parse_args()
    print(prepare(args.proxy_dir, enabled=not args.disable, source=args.source, ffmpeg=args.ffmpeg))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
