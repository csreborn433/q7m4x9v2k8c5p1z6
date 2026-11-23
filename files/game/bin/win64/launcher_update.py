"""Check the public CS2 GC update feed and update only its verified mod payload."""
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import urllib.error
from urllib.parse import quote
import urllib.request
import zipfile


REPOSITORY = 'csreborn433/q7m4x9v2k8c5p1z6'
FEED_BRANCH = 'main'
RAW_BASE_URL = 'https://raw.githubusercontent.com/{}/'.format(REPOSITORY)
FEED_URL = RAW_BASE_URL + FEED_BRANCH + '/latest.json'
MAX_ARCHIVE_SIZE = 512 * 1024 * 1024
MAX_UNPACKED_SIZE = 2 * 1024 * 1024 * 1024
MAX_FEED_SIZE = 8 * 1024 * 1024
MAX_UPDATE_FILE_SIZE = 100 * 1024 * 1024
BIN_PREFIX = 'game/bin/win64/'
PYTHON_PREFIX = BIN_PREFIX + 'cs2_gc_python/'
MANIFEST_PATH = BIN_PREFIX + 'cs2_gc_release.json'
SUPPORTED_STEAM_BUILD = '25966348'
# Player progress, statistics and settings in the bin folder. A published update may never create or replace them,
# so installing an update cannot reset stars or inventory (package_release refuses to ship them as well).
PLAYER_DATA = frozenset((
    'cs2_gc_inventory.txt', 'cs2_gc_gsi_state.json', 'cs2_gc_rewards.txt', 'cs2_gc_matches.txt',
    'cs2_gc_premier.txt', 'cs2_gc_finish_ids.json', 'cs2_gc_gun_collections.json', 'cs2_gc_skin_families.txt',
    'cs2_gc_console.txt', 'cs2_gc_console_boot.txt', 'cs2_gc_gameplay.cfg', 'cs2_gc.cfg',
    'cs2_gc_reward_stars.txt', 'cs2_gc_pets.json', 'cs2_gc_mission_session.txt', 'cs2_gc_mission_current.txt',
    'cs2_gc_combat_session.json', 'cs2_gc_combat_events.json'))
BACKUP_LABEL = 'Before-Update'
BACKUPS_KEPT = 5


class UpdateError(ValueError):
    pass


def _request(url, opener):
    headers = {'Accept': 'application/octet-stream',
               'User-Agent': 'cs2-gc-launcher'}
    request = urllib.request.Request(url, headers=headers)
    return opener(request, timeout=30)


def _read_json(url, opener):
    with _request(url, opener) as response:
        data = response.read(MAX_FEED_SIZE + 1)
    if len(data) > MAX_FEED_SIZE:
        raise UpdateError('GitHub returned an oversized update manifest.')
    return json.loads(data)


def _safe_parts(name):
    if not name or '\\' in name or any(ord(char) < 32 for char in name):
        raise UpdateError('The update archive contains an invalid path.')
    normalized = name.rstrip('/')
    path = PurePosixPath(normalized)
    if path.as_posix() != normalized or path.is_absolute() or not path.parts or any(
            part in ('', '.', '..') or ':' in part or part.endswith(('.', ' ')) or
            part.split('.')[0].upper() in ('CON', 'PRN', 'AUX', 'NUL') or
            re.fullmatch(r'(COM|LPT)[1-9]', part.split('.')[0].upper())
            for part in path.parts):
        raise UpdateError('The update archive contains an unsafe path.')
    return path.parts


def _file_manifest(data, release_commit):
    try:
        manifest = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdateError('The public update manifest is invalid.') from error
    if not isinstance(manifest, dict):
        raise UpdateError('The public update manifest is invalid.')
    files = manifest.get('files')
    if (manifest.get('format') != 1 or manifest.get('commit') != release_commit or
            not isinstance(files, dict) or not files or
            not isinstance(manifest.get('supported_build'), dict) or
            manifest['supported_build'].get('steam_build') != SUPPORTED_STEAM_BUILD or
            not re.fullmatch(r'[0-9a-f]{40}', release_commit)):
        raise UpdateError('The public update manifest does not match this CS2 build.')
    seen = set()
    for name, expected in files.items():
        _safe_parts(name)
        canonical = name.casefold()
        if canonical in seen:
            raise UpdateError('The update manifest contains colliding file paths.')
        seen.add(canonical)
        relative = name[len(BIN_PREFIX):] if name.startswith(BIN_PREFIX) else ''
        allowed_mod_file = (
            name.startswith(PYTHON_PREFIX) or
            name.startswith(BIN_PREFIX + 'cs2_gc_payload/') or
            relative.startswith('cs2_gc_') or
            relative == 'gold_pools.txt' or
            Path(relative).suffix.lower() in ('.py', '.cmd', '.png', '.jpg')
        )
        if not (name == 'Launch CS2 GC.exe' or allowed_mod_file):
            raise UpdateError('The update manifest attempts to replace a file outside the mod payload.')
        if relative.casefold() in PLAYER_DATA:
            raise UpdateError('The update manifest attempts to replace player progress: ' + name)
        if name.startswith('CS2 GC Saves/') or not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise UpdateError('The update manifest has an invalid file checksum.')
    if MANIFEST_PATH in files:
        raise UpdateError('The update manifest is recursive.')
    return manifest, files


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def install_archive(archive_path, root, release_commit, game_closed_check=None):
    root = Path(root).resolve()
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as error:
        raise UpdateError('The downloaded update is not a valid ZIP file.') from error

    with archive:
        infos = {}
        seen_paths = set()
        unpacked_size = 0
        for info in archive.infolist():
            _safe_parts(info.filename)
            canonical = info.filename.rstrip('/').casefold()
            if canonical in seen_paths:
                raise UpdateError('The update ZIP contains colliding file paths.')
            seen_paths.add(canonical)
            if info.is_dir():
                continue
            if info.filename in infos:
                raise UpdateError('The update ZIP contains duplicate file paths.')
            if info.file_size < 0:
                raise UpdateError('The update ZIP contains an invalid file size.')
            unpacked_size += info.file_size
            if unpacked_size > MAX_UNPACKED_SIZE:
                raise UpdateError('The update ZIP expands beyond the permitted size.')
            infos[info.filename] = info

        manifest_info = infos.get(MANIFEST_PATH)
        if manifest_info is None or manifest_info.file_size > 8 * 1024 * 1024:
            raise UpdateError('The update ZIP is missing or has an oversized release manifest.')
        try:
            manifest_data = archive.read(MANIFEST_PATH)
        except KeyError as error:
            raise UpdateError('The update ZIP is missing its release manifest.') from error
        manifest, expected_files = _file_manifest(manifest_data, release_commit)
        for name, expected in expected_files.items():
            info = infos.get(name)
            if info is None:
                raise UpdateError('The update ZIP is missing ' + name + '.')
            if info.file_size > MAX_UNPACKED_SIZE:
                raise UpdateError('The update ZIP contains an oversized file.')

        current_build = None
        current_manifest_path = root / Path(*PurePosixPath(MANIFEST_PATH).parts)
        if current_manifest_path.is_file():
            try:
                current_manifest = json.loads(current_manifest_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as error:
                raise UpdateError('The installed release manifest cannot be read.') from error
            if not isinstance(current_manifest, dict):
                raise UpdateError('The installed release manifest cannot be read.')
            current_build = current_manifest.get('supported_build')
            if not isinstance(current_build, dict):
                raise UpdateError('The installed release manifest cannot be read.')
        if current_build is not None and current_build != manifest.get('supported_build'):
            raise UpdateError('The update targets a different supported CS2 build.')

        with tempfile.TemporaryDirectory(prefix='.cs2gc-update-', dir=root) as temporary:
            staged = Path(temporary)
            for name, expected in expected_files.items():
                content = archive.read(infos[name])
                if hashlib.sha256(content).hexdigest() != expected:
                    raise UpdateError('The update ZIP checksum failed for ' + name + '.')
                destination = staged / Path(*PurePosixPath(name).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            staged_manifest = staged / Path(*PurePosixPath(MANIFEST_PATH).parts)
            staged_manifest.write_bytes(manifest_data)

            for name, expected in expected_files.items():
                if name.startswith(PYTHON_PREFIX):
                    installed = root / Path(*PurePosixPath(name).parts)
                    if not installed.is_file() or _sha256_file(installed) != expected:
                        raise UpdateError('The bundled Python runtime changed; reinstall using the full launcher package.')

            with contextlib.ExitStack() as guard:
                if game_closed_check is None:
                    from fair_bot_policy import require_game_closed
                    from rewards_runtime import InstanceLock
                    require_game_closed()
                    lock = InstanceLock(root / Path(*PurePosixPath(BIN_PREFIX).parts))
                    if not lock.__enter__():
                        raise RuntimeError('Close the CS2 GC rewards helper before applying this update.')
                    guard.callback(lock.__exit__, None, None, None)
                else:
                    game_closed_check()

                backup_progress(root)
                ordered_names = sorted(
                    name for name in expected_files
                    if name != MANIFEST_PATH and not name.startswith(PYTHON_PREFIX))
                for name in ordered_names:
                    source = staged / Path(*PurePosixPath(name).parts)
                    destination = root / Path(*PurePosixPath(name).parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, destination)
                current_manifest_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged_manifest, current_manifest_path)
    print('Mod update installed: ' + release_commit, flush=True)


def _feed_file_url(name, digest, feed_commit):
    return RAW_BASE_URL + feed_commit + '/files/' + quote(name, safe='/') + '?v=' + digest


def backup_progress(root):
    """A Before-Update copy of the player's progress in "CS2 GC Saves", keeping the newest BACKUPS_KEPT.

    Updates never touch progress files (PLAYER_DATA); this copy is an extra safeguard, so a failure is reported
    without blocking the update. The caller has checked that CS2 and the rewards helper are closed."""
    proxy = Path(root) / Path(*PurePosixPath(BIN_PREFIX).parts)
    if not (proxy / 'cs2_gc_inventory.txt').is_file():
        return None
    try:
        import progress_saves
        target = progress_saves.snapshot(proxy, label=BACKUP_LABEL, strict=False)
        old = sorted(target.parent.glob(BACKUP_LABEL + '-*.zip'), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in old[BACKUPS_KEPT:]:
            if path != target:
                path.unlink(missing_ok=True)
    except (ImportError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print('Progress backup skipped: ' + str(error), flush=True)
        return None
    print('Progress backed up: ' + target.name, flush=True)
    return target


def _updated_manifest(current, feed, files):
    updated = dict(current)
    merged_files = dict(current['files'])
    merged_files.update(files)
    updated.update({
        'commit': feed['commit'],
        'version': feed['version'],
        'supported_build': feed['supported_build'],
        'files': merged_files,
        'package_id': hashlib.sha256(json.dumps(
            merged_files, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest(),
    })
    return (json.dumps(updated, indent=2) + '\n').encode('utf-8')


def _compare_with_feed(root, opener):
    """(current, manifest path, feed, feed files, feed revision, changed files); None for a local test build."""
    if opener is None:
        opener = urllib.request.build_opener().open
    local_manifest = root / Path(*PurePosixPath(MANIFEST_PATH).parts)
    try:
        current = json.loads(local_manifest.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise UpdateError('The installed release manifest is missing or invalid.') from error
    if (not isinstance(current, dict) or
            not isinstance(current.get('commit'), str) or
            not re.fullmatch(r'[0-9a-f]{40}', current['commit']) or
            not isinstance(current.get('files'), dict)):
        raise UpdateError('The installed release manifest is missing or invalid.')
    current_build = current.get('supported_build')
    if (not isinstance(current_build, dict) or
            current_build.get('steam_build') != SUPPORTED_STEAM_BUILD):
        raise UpdateError('The installed release manifest targets a different CS2 build.')
    if current.get('local_test') is True:
        return None

    try:
        feed = _read_json(FEED_URL + '?cache=' + os.urandom(8).hex(), opener)
    except (OSError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdateError('Could not check GitHub for updates: ' + str(error)) from error
    if not isinstance(feed, dict):
        raise UpdateError('GitHub returned an invalid update manifest.')
    commit = feed.get('commit')
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise UpdateError('The public update manifest has no valid source commit.')
    feed_commit = feed.get('feed_commit')
    if not isinstance(feed_commit, str) or not re.fullmatch(r'[0-9a-f]{40}', feed_commit):
        raise UpdateError('The public update manifest has no valid immutable feed revision.')
    feed, feed_files = _file_manifest(json.dumps(feed).encode('utf-8'), commit)
    if not isinstance(feed.get('version'), str):
        raise UpdateError('The public update manifest has no mod version.')

    current_files = current['files']
    for name, expected in feed_files.items():
        if name.startswith(PYTHON_PREFIX) and current_files.get(name) != expected:
            raise UpdateError('The bundled Python runtime changed; reinstall using the latest launcher.')

    changed = []
    for name, expected in feed_files.items():
        if name.startswith(PYTHON_PREFIX):
            continue
        destination = root / Path(*PurePosixPath(name).parts)
        if current_files.get(name) != expected or not destination.is_file():
            changed.append((name, expected))
    return current, local_manifest, feed, feed_files, feed_commit, changed


def pending_update(root, opener=None):
    """The published mod version that reopening the launcher would install, or None when nothing would change."""
    plan = _compare_with_feed(Path(root).resolve(), opener)
    return plan[2]['version'] if plan is not None and plan[5] else None


def check_for_updates(root, opener=None, install=True, game_closed_check=None):
    if opener is None:
        opener = urllib.request.build_opener().open
    root = Path(root).resolve()
    plan = _compare_with_feed(root, opener)
    if plan is None:
        print('Local test build: public updates are disabled. Install a normal release launcher to resume them.', flush=True)
        return False
    current, local_manifest, feed, feed_files, feed_commit, changed = plan
    commit = feed['commit']

    if not changed:
        print('Mod is up to date.', flush=True)
        if install and (current.get('commit') != commit or current.get('version') != feed['version']):
            local_manifest.parent.mkdir(parents=True, exist_ok=True)
            temporary_manifest = local_manifest.with_suffix(local_manifest.suffix + '.tmp')
            temporary_manifest.write_bytes(_updated_manifest(current, feed, feed_files))
            os.replace(temporary_manifest, local_manifest)
        return False
    if not install:
        print('Update available: ' + commit, flush=True)
        return True

    print('Downloading mod update...', flush=True)
    with tempfile.TemporaryDirectory(prefix='.cs2gc-download-', dir=root) as temporary:
        staged = Path(temporary)
        staged_files = []
        for name, expected in changed:
            destination = staged / Path(*PurePosixPath(name).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            downloaded = 0
            try:
                with _request(_feed_file_url(name, expected, feed_commit), opener) as response, destination.open('wb') as output:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        downloaded += len(block)
                        if downloaded > MAX_UPDATE_FILE_SIZE:
                            raise UpdateError('A mod update file exceeds the permitted size.')
                        digest.update(block)
                        output.write(block)
            except (OSError, urllib.error.URLError) as error:
                raise UpdateError('Could not download ' + name + ': ' + str(error)) from error
            if digest.hexdigest() != expected:
                raise UpdateError('The downloaded update failed its SHA-256 check for ' + name + '.')
            staged_files.append((name, destination))

        updated_manifest_path = staged / 'release-manifest.json'
        updated_manifest_path.write_bytes(_updated_manifest(current, feed, feed_files))
        print('Verifying and installing mod files...', flush=True)
        with contextlib.ExitStack() as guard:
            if game_closed_check is None:
                from fair_bot_policy import require_game_closed
                from rewards_runtime import InstanceLock
                require_game_closed()
                lock = InstanceLock(root / Path(*PurePosixPath(BIN_PREFIX).parts))
                if not lock.__enter__():
                    raise RuntimeError('Close the CS2 GC rewards helper before applying this update.')
                guard.callback(lock.__exit__, None, None, None)
            else:
                game_closed_check()

            backup_progress(root)
            for name, source in sorted(staged_files):
                destination = root / Path(*PurePosixPath(name).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, destination)
            os.replace(updated_manifest_path, local_manifest)
    print('Mod update installed: ' + commit, flush=True)
    return True


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true',
                        help='report whether a public update exists without installing it')
    args = parser.parse_args()
    try:
        check_for_updates(args.root, install=not args.check_only)
        return 0
    except (OSError, RuntimeError, UpdateError, zipfile.BadZipFile) as error:
        print('Update check failed: ' + str(error), file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
