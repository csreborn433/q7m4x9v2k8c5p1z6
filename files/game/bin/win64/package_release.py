"""Build the complete drag-and-drop ZIP on Actions. No Valve files or player data."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from make_proxy_def import export_names, OVERRIDDEN
from launcher_update import PLAYER_DATA

PYTHON_URL = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
BIN = 'game/bin/win64/'
EXCLUDED_NAMES = {'items_game.txt','steam_api64_real.dll','steam_api64.dll',
                  'cs2_gc_inventory.txt','cs2_gc_finish_ids.json','cs2_gc.cfg','cs2_gc_gameplay.cfg'}
ADMIN_TOOLS = {'settings_editor.py', 'grant_custom_cases.py', 'grant_test_items.py',
               'reset_profile.py', 'cs2_gc_reset_profile.cmd', 'repair_inventory.cmd',
               'publish_update_feed.py', 'prime_karambit_port.py'}
COBBLESTONE_VPKS = {
    'map_assets/cobblewingman.vpk',
    'map_assets/cobblestone_resources/pak01_dir.vpk',
    'map_assets/cobblestone_resources/pak01_000.vpk',
}


def project_files(root):
    from native_default_music import BUNDLE as music_bundle, bundle_files as music_files
    tools = root/'tools'
    result = []
    for path in sorted(tools.rglob('*')):
        relative = path.relative_to(tools)
        if not path.is_file() or '__pycache__' in relative.parts or relative.parts[0] == music_bundle:
            continue
        if path.suffix.lower() not in ('.py','.png','.jpg','.cmd','.webm','.vpk'):
            continue
        if path.suffix.lower() == '.vpk' and relative.as_posix().casefold() not in COBBLESTONE_VPKS:
            continue
        if path.name in ADMIN_TOOLS or path.name.startswith('grant_'):
            continue
        if path.name in EXCLUDED_NAMES or 'cs2_gc_replay' in relative.parts:
            raise ValueError('Player or game data must never enter the release ZIP')
        result.append((path,BIN+relative.as_posix()))
    result.extend((p, BIN + music_bundle + '/' + p.name) for p in music_files(tools / music_bundle))
    from native_agents import BUNDLE, MANIFEST, read_manifest
    bundle = tools / BUNDLE
    if read_manifest(bundle) is not None:
        result += [(bundle / name, BIN + BUNDLE + '/' + name)
                   for name in (MANIFEST, 'pak01_dir.vpk', 'pak01_000.vpk')]
    import native_prime_karambit as prime
    bundle = tools / prime.BUNDLE
    if prime.read_bundle(bundle) is not None:
        result += [(bundle / name, BIN + prime.BUNDLE + '/' + name) for name in (prime.BUNDLE_MANIFEST, *prime.PACKS)]
    return result


def expected_exports(root):
    return sorted(line.strip().split('=')[0].strip() for line in
                  (root/'data/steam_api64_exports.def').read_text().splitlines()
                  if line.startswith('    '))


def career_payload(root):
    """Only our compiled plugin and hashes; server API/runtime binaries stay in the bot bundle."""
    folder=Path(root)/'build/career'
    if not (folder/'bundle.json').exists():return {}
    spec=json.loads((folder/'bundle.json').read_text())
    binary=(folder/'CS2GCCareerBridge.dll').read_bytes()
    if hashlib.sha256(binary).hexdigest()!=spec['sha256']:
        raise ValueError('Career plugin payload checksum mismatch')
    prefix=BIN+'cs2_gc_payload/career/'
    return {prefix+'CS2GCCareerBridge.dll':binary,prefix+'bundle.json':(json.dumps(spec,indent=2)+'\n').encode()}


def match_payload(root):
    """Only our compiled match-flow plugin and hashes; server API/runtime binaries stay in the bot bundle."""
    folder=Path(root)/'build/match'
    if not (folder/'bundle.json').exists():return {}
    spec=json.loads((folder/'bundle.json').read_text())
    binary=(folder/'CS2GCMatchBridge.dll').read_bytes()
    if hashlib.sha256(binary).hexdigest()!=spec['sha256']:
        raise ValueError('Match-flow plugin payload checksum mismatch')
    prefix=BIN+'cs2_gc_payload/match/'
    return {prefix+'CS2GCMatchBridge.dll':binary,prefix+'bundle.json':(json.dumps(spec,indent=2)+'\n').encode()}


def mod_version(root):
    """Release label shown by the CSReborn launcher; data/mod_version.txt unless CS2GC_VERSION overrides it."""
    if os.environ.get('CS2GC_VERSION'):
        return os.environ['CS2GC_VERSION']
    path = Path(root)/'data/mod_version.txt'
    return path.read_text().strip() if path.is_file() else ''


def source_commit(root):
    commit = os.environ.get('GITHUB_SHA', '').strip().lower()
    if not commit:
        commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=root, text=True, stderr=subprocess.PIPE
        ).strip().lower()
    if len(commit) != 40 or any(char not in '0123456789abcdef' for char in commit):
        raise ValueError('The source commit must be a full 40-character Git hash')
    return commit


def build_archive(root, runtime_data, bot_files, *, local_test=False):
    root = Path(root)
    build = root/'build/Release'
    proxy = build/'steam_api64.dll'
    names = export_names(proxy.read_bytes(),'steam_api64_real')
    if sorted(names) != expected_exports(root) or not set(OVERRIDDEN).issubset(names):
        raise ValueError('Proxy export validation failed')
    files = project_files(root)
    for name in ('cs2_gc_debug.exe','cs2_gc_profile.exe','cs2_gc_texture_decode.exe'):
        files.append((build/name,BIN+name))
    files += [(build/'cs2_gc_debug.exe','Launch CS2 GC.exe'),
              (proxy,BIN+'cs2_gc_payload/steam_api64.dll'),
              (root/'data/gold_pools.txt',BIN+'gold_pools.txt'),
              (root/'LICENSE','licenses/CS2-GC-LICENSE.txt'),
              (root/'data/CSGO-API-LICENSE','licenses/CSGO-API-LICENSE.txt')]
    manifest = {'format':1,'commit':source_commit(root),'version':mod_version(root),
                'supported_build':json.loads((root/'data/supported_build.json').read_text()),
                'python_source':PYTHON_URL,'python_archive_sha256':hashlib.sha256(runtime_data).hexdigest(),
                'files':{}}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        seen = set()
        def add(name,data):
            if name in seen:
                raise ValueError('Duplicate release path: '+name)
            if name.startswith(BIN) and name[len(BIN):].casefold() in PLAYER_DATA:
                raise ValueError('Player progress must never enter the release ZIP: '+name)
            seen.add(name)
            archive.writestr(name,data)
            if name.startswith(BIN) or name == 'Launch CS2 GC.exe':
                manifest['files'][name] = hashlib.sha256(data).hexdigest()
        for path,name in files:
            add(name,path.read_bytes())
        for name,data in bot_files.items():
            add(name,data)
        for name,data in career_payload(root).items():add(name,data)
        for name,data in match_payload(root).items():add(name,data)
        from save_shortcuts import files as save_files
        for name,data in save_files().items():add(name,data)
        with zipfile.ZipFile(io.BytesIO(runtime_data)) as runtime:
            for info in runtime.infolist():
                if info.is_dir():
                    continue
                if '/' in info.filename or '\\' in info.filename or info.filename.startswith('.'):
                    raise ValueError('Unexpected Python runtime archive path')
                if info.filename.endswith('._pth'):
                    continue
                add(BIN+'cs2_gc_python/'+info.filename,runtime.read(info))
        add(BIN+'cs2_gc_python/python312._pth',b'python312.zip\n.\n..\n')
        add('licenses/BCDEC-LICENSE.txt',(root/'third_party/bcdec.h').read_text().split('/* LICENSE:')[1].encode())
        add('licenses/BC7ENC-LICENSE.txt',(root/'third_party/BC7ENC-NOTICE.md').read_bytes())
        manifest['package_id'] = hashlib.sha256(
            json.dumps(manifest['files'],sort_keys=True,separators=(',',':')).encode()
        ).hexdigest()
        if local_test:
            manifest['local_test'] = True
            manifest['package_id'] = hashlib.sha256((manifest['package_id'] + ':local-test').encode()).hexdigest()
        archive.writestr(BIN+'cs2_gc_release.json',json.dumps(manifest,indent=2))
    return buffer.getvalue()


def smoke_test(archive_data):
    with tempfile.TemporaryDirectory(prefix='cs2gc-release-') as directory:
        root = Path(directory)
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            archive.extractall(root)
        bin_dir = root/BIN
        manifest = json.loads((bin_dir/'cs2_gc_release.json').read_text())
        for name,wanted in manifest['files'].items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest() != wanted:
                raise ValueError('ZIP hash mismatch: '+name)
        # The embedded runtime must work without any system Python or compiler DLLs.
        env = dict(os.environ)
        env.pop('PYTHONHOME',None)
        env.pop('PYTHONPATH',None)
        env['PATH'] = str(Path(os.environ['SystemRoot'])/'System32')
        subprocess.run([str(bin_dir/'cs2_gc_python/python.exe'),'-B','-c',
            'import launch_setup,prepare_native,gsi_rewards,bundled_bots,ctypes,lzma,ssl; print("Bundled runtime imports OK")'],
            cwd=bin_dir,env=env,check=True)
        profile = subprocess.run([str(bin_dir/'cs2_gc_profile.exe')],cwd=bin_dir,env=env)
        if profile.returncode != 1:
            raise ValueError('Profile helper did not start without compiler/runtime dependencies')
        subprocess.run([str(bin_dir/'cs2_gc_python/python.exe'),'-B','-c',
            'import compileall; assert compileall.compile_dir(".",quiet=1,force=True)'],
            cwd=bin_dir,env=env,check=True)


        # Install the REAL pinned addon archive offline in a disposable fake game.
        # VPK curation/mounts need Valve files and remain target-client checks.
        bot_check = """
from pathlib import Path
import shutil,tempfile
from unittest.mock import patch
import bundled_bots,bot_skins
with tempfile.TemporaryDirectory(prefix='cs2gc-bot-smoke-') as temp:
    game=Path(temp)/'game'
    proxy=game/'bin/win64'
    proxy.mkdir(parents=True)
    (game/'csgo').mkdir()
    (game/'csgo/gameinfo.gi').write_text('"GameInfo" {}')
    shutil.copytree(Path.cwd()/'cs2_gc_payload/bots',proxy/'cs2_gc_payload/bots')
    with patch.object(bot_skins,'_get',side_effect=AssertionError('Runtime download forbidden')), patch.object(bot_skins,'_mount'), patch.object(bot_skins,'recurate'), patch('fair_bot_policy.require_game_closed'):
        assert bundled_bots.ensure(proxy)
        assert (game/bot_skins.PLUGIN_DIR/'BotRandomizer.dll').is_file()
        assert all((proxy/'cs2_gc_bot_presets'/tier/'botprofile.db').is_file() for tier in bot_skins.PRESET_TIERS)
        assert not bundled_bots.ensure(proxy)
print('Real bundled bot payload installs offline and reuses its owned files.')
"""
        subprocess.run([str(bin_dir/'cs2_gc_python/python.exe'),'-B','-c',bot_check],
                       cwd=bin_dir,env=env,check=True)


def fetch_bytes(url, limit=128*1024*1024):
    request = urllib.request.Request(url,headers={'User-Agent':'cs2-gc-release'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request,timeout=120) as response:
                data = response.read(limit+1)
            if len(data)>limit:
                raise ValueError('Release dependency exceeds limit: '+url)
            return data
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
        except urllib.error.URLError:
            if attempt == 3:
                raise
        time.sleep(2**attempt)
    raise RuntimeError('Release dependency fetch retries exhausted: '+url)


def bot_payload(root, fetch=fetch_bytes):
    from bundled_bots import bundle_names
    metadata = json.loads((root/'data/bot_bundle.json').read_text())
    data = fetch(metadata['url'])
    if hashlib.sha256(data).hexdigest() != metadata['sha256']:
        raise ValueError('Upstream bot archive checksum mismatch')
    bundle_names(data)
    # Upstream also carries optional botprofile VPK overrides and stock mode
    # configs. Our generated name/profile pack supplies those; ship only addons.
    from bot_skins import _bundle_prefix
    selected = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(selected,'w',zipfile.ZIP_DEFLATED) as target:
        names = [n.replace('\\','/') for n in source.namelist()]
        prefix = _bundle_prefix(names)
        base = prefix+'/' if prefix else ''
        for info in source.infolist():
            name = info.filename.replace('\\','/')
            relative = name[len(base):] if name.startswith(base) else ''
            if not relative.startswith('addons/') or info.is_dir():
                continue
            if Path(relative).name.lower() in ('engine2.dll','client.dll','steam_api64.dll','steam_api64_real.dll') or relative.lower().endswith('.vpk'):
                raise ValueError('Unexpected game file inside bot addons: '+relative)
            target.writestr(relative,source.read(info))
    data = selected.getvalue()
    bundle_names(data)
    packaged = dict(metadata,upstream_sha256=metadata['sha256'],sha256=hashlib.sha256(data).hexdigest())
    base = BIN+'cs2_gc_payload/bots/'
    files = {base+'bot_improver.zip':data,
             base+'bundle.json':json.dumps(packaged,indent=2).encode()}
    raw = 'https://raw.githubusercontent.com/'+metadata['source_repo']+'/'+metadata['source_commit']+'/'
    resources = ['overrides/%s/botprofile.db'%tier for tier in ('Low','Medium','High')]
    resources += ['cfg/my_bot_%s_config_rules_unchanged.cfg'%mode for mode in ('normal','ffa')]
    for name in resources:
        files[base+'resources/'+name] = fetch(raw+name)
    files['licenses/CS2-Bot-Improver-LICENSE.txt'] = fetch(raw+'LICENSE')
    # Keep unchanged addon bytes and exact plugin source snapshots
    # alongside notices; third-party plugins retain their own licences.
    sources = [{'repo':metadata['source_repo'],'commit':metadata['source_commit']}]+metadata['plugin_sources']
    notices = ['Bundled bot components: CS2-Bot-Improver '+metadata['version']+' (addons only; bytes unchanged)',
               'Windows release: '+metadata['url'],
               'Framework/plugin licences inside cs2_gc_payload/bots/bot_improver.zip are retained.',
               'Exact source snapshots for the bot project and its pinned plugin submodules:','']
    for source in sources:
        repo,commit = source['repo'],source['commit']
        name = 'licenses/bot-sources/'+repo.replace('/','-')+'-'+commit+'.tar.gz'
        files[name] = fetch('https://codeload.github.com/'+repo+'/legacy.tar.gz/'+commit)
        notices.append('https://github.com/'+repo+'/tree/'+commit+' -> '+name)
    files['licenses/BOT-SOURCES.txt'] = ('\n'.join(notices)+'\n').encode()
    print('Validated bundled bot frameworks, plugins, presets and source notices.')
    return files


def build_launcher(root, mod_package):
    """Build the bundled CSReborn launcher and run its offline self-test."""
    mod_package = Path(mod_package).resolve()
    if not mod_package.is_file():
        raise ValueError('The validated mod package is missing: '+str(mod_package))
    candidates = [Path(os.environ['DOTNET_ROOT'])/'dotnet.exe'] if os.environ.get('DOTNET_ROOT') else []
    candidates += [root/'build/dotnet-sdk/dotnet.exe']
    dotnet = next((str(path) for path in candidates if path.is_file()), shutil.which('dotnet'))
    if not dotnet:
        raise ValueError('The .NET SDK is required to build the CSReborn launcher')
    out = root/'build/launcher-out'
    command = [dotnet,'build',str(root/'launcher/CSReborn/CSReborn.csproj'),'-c','Release','-o',str(out),
               '-p:CSRebornModPackage='+str(mod_package),'-nologo','-v','q']
    subprocess.run(command,check=True)
    exe = out/'CSReborn.exe'
    result = Path(tempfile.mkdtemp(prefix='csreborn-selftest-'))/'result.txt'
    env = dict(os.environ,CSREBORN_DATA=str(result.parent/'data'))
    if subprocess.run([str(exe),'--self-test',str(result)],env=env).returncode != 0:
        raise ValueError('CSReborn launcher self-test failed:\n'+(result.read_text() if result.exists() else 'no report'))
    shutil.rmtree(result.parent,ignore_errors=True)
    return exe


def publish_update_feed_to_github(package_path):
    repo = 'csreborn433/q7m4x9v2k8c5p1z6'
    gh = shutil.which('gh')
    if not gh:
        raise ValueError('GitHub CLI is required to publish the public update feed')
    with tempfile.TemporaryDirectory(prefix='cs2gc-update-feed-') as temporary:
        feed_dir = Path(temporary)/'feed'
        subprocess.run([gh,'repo','clone',repo,str(feed_dir)],check=True)
        subprocess.run(['git','-C',str(feed_dir),'config','core.autocrlf','false'],check=True)
        import publish_update_feed as feed_publisher
        count,size,commit,version = feed_publisher.publish(package_path,feed_dir)
        subprocess.run(['git','-C',str(feed_dir),'config','user.name','CSReborn Update Publisher'],check=True)
        subprocess.run(['git','-C',str(feed_dir),'config','user.email','updates@users.noreply.github.com'],check=True)

        subprocess.run(['git','-C',str(feed_dir),'add','files','.gitattributes'],check=True)
        payload_changes = subprocess.run(['git','-C',str(feed_dir),'diff','--cached','--quiet'])
        if payload_changes.returncode == 1:
            subprocess.run(['git','-C',str(feed_dir),'commit','-m',
                            'Publish mod payload {} ({})'.format(version,commit[:8])],check=True)
        elif payload_changes.returncode != 0:
            raise ValueError('Could not inspect staged update-feed payload changes')

        feed_commit = subprocess.check_output(
            ['git','-C',str(feed_dir),'rev-parse','HEAD'],text=True).strip()
        feed_publisher.set_feed_commit(feed_dir,feed_commit)
        subprocess.run(['git','-C',str(feed_dir),'add','latest.json'],check=True)
        manifest_changes = subprocess.run(['git','-C',str(feed_dir),'diff','--cached','--quiet'])
        if manifest_changes.returncode == 0:
            print('The public update feed is already current.')
            return
        if manifest_changes.returncode != 1:
            raise ValueError('Could not inspect staged update-feed manifest changes')
        subprocess.run(['git','-C',str(feed_dir),'commit','-m',
                        'Publish mod update {} ({})'.format(version,commit[:8])],check=True)
        subprocess.run(['git','-C',str(feed_dir),'push','origin','HEAD:main'],check=True)
        print('Published {} files ({} bytes) to the public update feed.'.format(count,size))


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-test', action='store_true',
                        help='keep this local test package from being replaced by the public update feed')
    parser.add_argument('--publish-update-feed', action='store_true',
                        help='publish the generated mod files to the public GitHub update source')
    args = parser.parse_args()
    if args.local_test and args.publish_update_feed:
        parser.error('Local test packages cannot be published to the public update feed.')
    print('Fetching the bundled Python runtime from '+PYTHON_URL)
    runtime = fetch_bytes(PYTHON_URL, limit=32*1024*1024)
    data = build_archive(root,runtime,bot_payload(root),local_test=args.local_test)
    smoke_test(data)
    with tempfile.TemporaryDirectory(prefix='csreborn-embedded-', dir=root/'build') as temporary:
        package = Path(temporary)/'CS2GC-Portable-25966348.zip'
        package.write_bytes(data)
        launcher = build_launcher(root, package)
    out = root/'dist'
    out.mkdir(exist_ok=True)
    (out/'CS2GC-Portable-25966348.zip').write_bytes(data)
    installer = out/'CSReborn.exe'
    shutil.copy2(launcher, installer)
    (out/(installer.name+'.sha256')).write_text(hashlib.sha256(installer.read_bytes()).hexdigest()+'  '+installer.name+'\n')
    if args.publish_update_feed:
        publish_update_feed_to_github(out/'CS2GC-Portable-25966348.zip')
    print(installer)


if __name__ == '__main__':
    main()
