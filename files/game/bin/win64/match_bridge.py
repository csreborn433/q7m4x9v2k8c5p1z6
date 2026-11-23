"""Install the owned FACEIT-style local match-flow server plugin (CS2GCMatchBridge).

Mirrors combat_events.py: the compiled plugin ships in cs2_gc_payload/match and is
installed into the local CounterStrikeSharp plugins folder, only when the local
server plugins (Metamod/CounterStrikeSharp from the bot bundle) are present and
not disabled. Never touches a foreign or externally edited plugin folder.
"""
import hashlib, json
from pathlib import Path

OWNER = 'cs2-gc-match-flow-v1'
PLUGIN = 'CS2GCMatchBridge'


def prepare(directory, config):
    proxy = Path(directory).resolve(); game = proxy.parents[1]
    payload = proxy / 'cs2_gc_payload/match'
    if not (payload / 'bundle.json').is_file():
        return 'unavailable: match-flow payload missing'
    api = game / 'csgo/addons/counterstrikesharp/api/CounterStrikeSharp.API.dll'
    if (proxy / 'cs2_gc_bot_plugins_disabled').exists() or not api.is_file():
        return 'unavailable: local server plugins are disabled or missing'
    spec = json.loads((payload / 'bundle.json').read_text()); binary = (payload / (PLUGIN + '.dll')).read_bytes()
    sha = lambda b: hashlib.sha256(b).hexdigest()
    if sha(binary) != spec['sha256'] or sha(api.read_bytes()) != spec['api_sha256']:
        raise ValueError('Match-flow payload/API mismatch; no plugin was changed')
    target = game / 'csgo/addons/counterstrikesharp/plugins' / PLUGIN
    marker = target / 'cs2_gc_owner.json'; dll = target / (PLUGIN + '.dll')
    prior = json.loads(marker.read_text()) if marker.exists() else {}
    if target.is_symlink() or (target.exists() and any(target.iterdir()) and prior.get('owner') != OWNER):
        raise ValueError('Unowned match-flow plugin folder; leaving it unchanged')
    if dll.exists() and sha(dll.read_bytes()) not in (prior.get('sha256'), spec['sha256']):
        raise ValueError('Match-flow plugin was edited externally; leaving it unchanged')
    from fair_bot_policy import require_game_closed
    require_game_closed()
    from launch_setup import atomic_bytes
    target.mkdir(parents=True, exist_ok=True)
    if not dll.exists() or sha(dll.read_bytes()) != spec['sha256']:
        atomic_bytes(dll, binary)
    atomic_bytes(marker, (json.dumps(dict(owner=OWNER, sha256=spec['sha256'])) + '\n').encode())
    return ('installed: FACEIT-style local match flow (ready-up warmup, knife round, side pick, '
            'tactical timeouts, knife drop, 5v5 wingman)')
