"""Compile the CS2GCMatchBridge server plugin into build/match/ for packaging.

The release packages only our compiled DLL plus a bundle.json checksum (the
CounterStrikeSharp API/runtime ship in the bot bundle, like the career bridge).
This needs a .NET 10 SDK and the CounterStrikeSharp.API.dll the game installs
(from the pinned Bot Improver bundle). Both are located automatically when the
game's server plugins are installed, or can be passed explicitly.

    python tools/build_match_plugin.py --proxy-dir "C:/path/to/game/bin/win64"
    python tools/build_match_plugin.py --dotnet "C:/dotnet/dotnet.exe" --api "C:/.../CounterStrikeSharp.API.dll"
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'plugins' / 'CS2GCMatchBridge.cs'
RULES = ROOT / 'plugins' / 'MatchFlowRules.cs'
VISUALS = ROOT / 'plugins' / 'GameplayVisualRules.cs'
CAMERA = ROOT / 'plugins' / 'FirstPersonDeathCamera.cs'
OUT = ROOT / 'build' / 'match'
PLUGIN = 'CS2GCMatchBridge'

CSPROJ = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>disable</ImplicitUsings>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <EnableDefaultItems>false</EnableDefaultItems>
    <AssemblyName>__NAME__</AssemblyName>
    <AppendTargetFrameworkToOutputPath>false</AppendTargetFrameworkToOutputPath>
    <GenerateAssemblyInfo>false</GenerateAssemblyInfo>
    <GenerateTargetFrameworkAttribute>false</GenerateTargetFrameworkAttribute>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="__SOURCE__" />
    <Compile Include="__RULES__" />
    <Compile Include="__VISUALS__" />
__CAMERA__
__REFS__
  </ItemGroup>
</Project>
'''


def find_dotnet(explicit):
    for candidate in ([explicit] if explicit else []) + [os.environ.get('DOTNET'),
                       ROOT / 'build' / 'dotnet-sdk' / 'dotnet.exe', 'dotnet']:
        if not candidate:
            continue
        exe = str(candidate)
        try:
            result = subprocess.run([exe, '--list-sdks'], capture_output=True, text=True)
            if result.returncode == 0 and any(line.split('[')[0].strip().startswith('10.') for line in result.stdout.splitlines()):
                return exe
        except OSError:
            continue
    raise SystemExit('A .NET 10 SDK is required. Install one or pass --dotnet / set DOTNET.')


def find_api(explicit, proxy_dir):
    candidates = [explicit] if explicit else []
    if proxy_dir:
        game = Path(proxy_dir).resolve().parents[1]
        candidates.append(game / 'csgo/addons/counterstrikesharp/api/CounterStrikeSharp.API.dll')
    candidates.append(ROOT / 'build' / 'css-api' / 'reference' / 'CounterStrikeSharp.API.dll')
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise SystemExit('CounterStrikeSharp.API.dll not found. Install the local server plugins (bot bundle) '
                     'into the game first, or pass --api / --proxy-dir.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy-dir', type=Path, help='game/bin/win64; the installed CounterStrikeSharp API is read from the game')
    parser.add_argument('--dotnet', help='path to a .NET 10 SDK dotnet executable')
    parser.add_argument('--api', type=Path, help='path to CounterStrikeSharp.API.dll to compile against')
    args = parser.parse_args()
    dotnet = find_dotnet(args.dotnet)
    api = find_api(args.api, args.proxy_dir)
    # Only the API plus the two abstractions it needs; referencing every sibling causes type conflicts.
    refs = [api]
    for name in ('Microsoft.Extensions.DependencyInjection.Abstractions.dll',
                 'Microsoft.Extensions.Logging.Abstractions.dll'):
        extra = api.parent / name
        if extra.is_file():
            refs.append(extra)
    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        ref_xml = '\n'.join('    <Reference Include="%s"><HintPath>%s</HintPath></Reference>' % (p.stem, p.resolve()) for p in refs)
        proj = scratch / 'match.csproj'
        proj.write_text(CSPROJ.replace('__NAME__', PLUGIN).replace('__SOURCE__', str(SOURCE))
                        .replace('__RULES__', str(RULES)).replace('__VISUALS__', str(VISUALS))
                        .replace('__CAMERA__', '    <Compile Include="%s" />' % CAMERA).replace('__REFS__', ref_xml),
                        encoding='utf-8')
        result = subprocess.run([str(Path(dotnet).resolve()), 'build', str(proj), '-c', 'Release'], capture_output=True, text=True)
        if result.returncode != 0:
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            raise SystemExit('Match plugin build failed')
        built = scratch / 'bin' / 'Release' / (PLUGIN + '.dll')
        if not built.is_file():
            built = scratch / 'bin' / 'Release' / 'net10.0' / (PLUGIN + '.dll')
        binary = built.read_bytes()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / (PLUGIN + '.dll')
    tmp = target.with_suffix('.dll.tmp')
    tmp.write_bytes(binary)
    tmp.replace(target)
    spec = {'sha256': hashlib.sha256(binary).hexdigest(),
            'api_sha256': hashlib.sha256(api.read_bytes()).hexdigest()}
    (OUT / 'bundle.json').write_text(json.dumps(spec, indent=2) + '\n', encoding='utf-8')
    print('Built %s (%d bytes) against %s' % (target, len(binary), api))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
