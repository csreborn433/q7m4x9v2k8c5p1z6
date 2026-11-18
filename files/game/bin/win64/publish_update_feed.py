"""Publish verified, updateable mod files into a checked-out public GitHub feed."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import os
import tempfile
import zipfile

import launcher_update


FEED_MANIFEST = 'latest.json'
FEED_FILES = 'files'


def _feed_files(package_manifest):
    files = package_manifest.get('files')
    if not isinstance(files, dict):
        raise ValueError('The mod package has no file manifest')
    selected = {}
    for name, digest in files.items():
        if not isinstance(name, str) or not isinstance(digest, str):
            raise ValueError('The mod package contains an invalid file manifest entry')
        try:
            parts = launcher_update._safe_parts(name)
        except launcher_update.UpdateError as error:
            raise ValueError(str(error)) from error
        if name.startswith(launcher_update.PYTHON_PREFIX):
            selected[name] = digest
            continue
        relative = name[len(launcher_update.BIN_PREFIX):] if name.startswith(launcher_update.BIN_PREFIX) else ''
        allowed = (
            name == 'Launch CS2 GC.exe' or
            name.startswith(launcher_update.BIN_PREFIX + 'cs2_gc_payload/') or
            relative.startswith('cs2_gc_') or relative == 'gold_pools.txt' or
            PurePosixPath(relative).suffix.lower() in ('.py', '.cmd', '.png', '.jpg')
        )
        if allowed:
            selected[name] = digest
    if not selected:
        raise ValueError('The package has no updateable mod files')
    return selected


def _destination(root, relative):
    parts = launcher_update._safe_parts(relative)
    target = root.joinpath(*parts)
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('The update feed contains a symbolic link at ' + str(current))
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('The update feed path escapes its checkout')
    return target


def publish(package_path, feed_dir):
    package_path = Path(package_path)
    feed_dir = Path(feed_dir).resolve()
    if not package_path.is_file():
        raise ValueError('The mod package is missing: ' + str(package_path))
    if not feed_dir.is_dir():
        raise ValueError('The update feed checkout is missing: ' + str(feed_dir))

    with zipfile.ZipFile(package_path) as package:
        manifest_path = launcher_update.MANIFEST_PATH
        try:
            package_manifest = json.loads(package.read(manifest_path).decode('utf-8'))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError('The mod package has no valid release manifest') from error
        if (not isinstance(package_manifest, dict) or package_manifest.get('format') != 1 or
                not isinstance(package_manifest.get('commit'), str) or
                not isinstance(package_manifest.get('version'), str) or
                not isinstance(package_manifest.get('supported_build'), dict)):
            raise ValueError('The mod package release manifest is incomplete')

        files = _feed_files(package_manifest)
        feed_manifest = {
            'format': 1,
            'commit': package_manifest['commit'],
            'version': package_manifest['version'],
            'supported_build': package_manifest['supported_build'],
            'files': files,
        }
        launcher_update._file_manifest(
            json.dumps(feed_manifest).encode('utf-8'), feed_manifest['commit'])

        total_bytes = 0
        for name, expected in files.items():
            if name.startswith(launcher_update.PYTHON_PREFIX):
                continue
            try:
                entry = package.getinfo(name)
            except KeyError as error:
                raise ValueError('The mod package is missing ' + name) from error
            if entry.file_size >= launcher_update.MAX_UPDATE_FILE_SIZE:
                raise ValueError(name + " exceeds GitHub's 100 MiB per-file limit")
            destination = _destination(feed_dir, FEED_FILES + '/' + name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                        prefix='.feed-', suffix='.tmp', dir=destination.parent, delete=False) as output:
                    temporary = Path(output.name)
                    digest = hashlib.sha256()
                    copied = 0
                    with package.open(entry) as source:
                        while True:
                            block = source.read(1024 * 1024)
                            if not block:
                                break
                            copied += len(block)
                            if copied > launcher_update.MAX_UPDATE_FILE_SIZE:
                                raise ValueError(name + ' exceeds the permitted update file size')
                            digest.update(block)
                            output.write(block)
                    if copied != entry.file_size or digest.hexdigest() != expected:
                        raise ValueError('The mod package checksum failed for ' + name)
                os.replace(temporary, destination)
            except Exception:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
                raise
            total_bytes += entry.file_size

    manifest_destination = feed_dir / FEED_MANIFEST
    manifest_destination.write_text(json.dumps(feed_manifest, indent=2) + '\n', encoding='utf-8')
    return len(files), total_bytes, feed_manifest['commit'], feed_manifest['version']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--feed-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        count, size, commit, version = publish(args.package, args.feed_dir)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    print('Prepared {} update-feed files ({} bytes) for {} ({})'.format(
        count, size, version, commit))


if __name__ == '__main__':
    main()
