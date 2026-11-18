"""Make the local listen server joinable over LAN, Hamachi and the internet.

The mod starts a CS2 *listen* server (the host's client is the server). Friends join
it directly with ``connect <host-ip>:27015`` — over a LAN, over a Hamachi/ZeroTier
virtual LAN, or over the internet when the host forwards the port — and Steam party
members follow the host in through the native lobby. This helper writes an owned
``cs2_gc_network.cfg`` that the launcher executes at startup and the Play menu runs
again before every map, so the server accepts those connections, plus this PC's
current addresses for the Play menu's connect line. No original game file is edited;
delete the cfg (or set ``network_server = 0``) to revert.

Convar names verified against this build's engine2.dll / server.dll.
"""
import ipaddress
import socket
from pathlib import Path

from native_tradeups import atomic_write

OWNER = 'cs2-gc-network-v1'
CFG_NAME = 'cs2_gc_network.cfg'
# Written empty here each launch; upnp_forward.py fills in the router's external IP when forwarding works.
EXTERNAL_CFG_NAME = 'cs2_gc_network_external.cfg'

# engine2.dll describes sv_lan 1 as "no heartbeat, no authentication, no non-class C addresses",
# which refuses Hamachi (25.x) and internet players, so the server runs with sv_lan 0.
# Steam authentication remains at the game's default; online hosting does not require bypassing it.
# sv_hibernate_when_empty 0 keeps the listen server reachable while the host sits in the menu;
# generous rate limits suit internet play.
BODY = '''// CS2 GC network: joinable listen server (owned by native_network.py; delete to revert).
sv_lan 0
sv_hibernate_when_empty 0
sv_minrate 128000
sv_maxrate 0
sv_minupdaterate 20
sv_maxupdaterate 64
'''

HAMACHI = ipaddress.ip_network('25.0.0.0/8')
SHARED_VPN = ipaddress.ip_network('100.64.0.0/10')  # carrier-grade NAT range used by Tailscale-style VPNs
LABEL_ORDER = ('Hamachi', 'VPN', 'Public', 'LAN')


def classify(ip):
    """Label an IPv4 address for the connect line, or None when friends can never reach it."""
    try:
        address = ipaddress.IPv4Address(ip)
    except ValueError:
        return None
    if address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast:
        return None
    if address in HAMACHI:
        return 'Hamachi'
    if address in SHARED_VPN:
        return 'VPN'
    return 'LAN' if address.is_private else 'Public'


def host_addresses():
    """This PC's IPv4 addresses (every adapter, Hamachi included), labelled and ordered for friends."""
    found = []
    try:
        found.extend(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(('8.8.8.8', 80))  # picks the default-route adapter; UDP connect sends nothing
        found.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    labelled = []
    for ip in found:
        label = classify(ip)
        if label and all(ip != known for _, known in labelled):
            labelled.append((label, ip))
    return sorted(labelled, key=lambda entry: LABEL_ORDER.index(entry[0]))


def server_config(addresses=()):
    text = '// CS2 GC network: joinable listen server (owned by %s; delete to revert).\n' % OWNER + BODY.split('\n', 1)[1]
    # Panorama reads these with GameInterfaceAPI.GetSettingString for the Play menu's connect line.
    listed = ','.join('%s=%s' % (label, ip) for label, ip in addresses if classify(ip) == label)
    return text + 'setinfo cs2gc_host_addresses "%s"\nexec %s\n' % (listed, EXTERNAL_CFG_NAME[:-4])


def external_config(ip=''):
    return ('// CS2 GC network: router external IP from UPnP (owned by %s; rewritten every launch).\n'
            'setinfo cs2gc_host_external "%s"\n' % (OWNER, ip if classify(ip) == 'Public' else ''))


def prepare(directory, config, addresses=None):
    """Write the network cfg beside the game. Returns a status string."""
    proxy = Path(directory).resolve()
    game = proxy.parents[1]
    cfg_dir = game / 'csgo/cfg'
    if not cfg_dir.is_dir():
        return 'unavailable: installed csgo/cfg not found'
    enabled = bool(config.get('network_server', 1))
    addresses = (host_addresses() if addresses is None else addresses) if enabled else []
    shown = ', '.join('%s %s' % entry for entry in addresses) or 'no LAN/Hamachi address found'
    changed = False
    network_text = server_config(addresses) if enabled else (
        '// CS2 GC network: LAN-only preset (owned by %s).\n'
        'sv_lan 1\nsetinfo cs2gc_host_addresses ""\nexec cs2_gc_network_external\n' % OWNER)
    for name, text in ((CFG_NAME, network_text), (EXTERNAL_CFG_NAME, external_config())):
        target = cfg_dir / name
        if not (target.is_file() and target.read_text(encoding='utf-8') == text):
            atomic_write(target, text)
            changed = True
    if not enabled:
        return 'disabled'
    if not changed:
        return 'installed: joinable listen server config (%s)' % shown
    return 'prepared: joinable listen server config (Steam party, or connect <ip>:27015 over %s)' % shown
