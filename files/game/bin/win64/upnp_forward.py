"""Forward the CS2 listen-server port (27015) through the router with UPnP.

Standard library only (the bundled private Python has no third-party packages).
Discovers an Internet Gateway Device via SSDP, reads its WANIP/WANPPP service, and
adds a UDP+TCP port mapping so friends can connect over the internet without manual
router configuration. Run with ``--remove`` to delete the mapping again.

    python tools/upnp_forward.py            # add the mapping, print the external IP
    python tools/upnp_forward.py --remove   # remove the mapping
"""
import argparse
import http.client
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

SSDP_ADDR = ('239.255.255.250', 1900)
DISCOVER = ('M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n'
            'MAN: "ssdp:discover"\r\nMX: 2\r\nST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n')
WAN_SERVICES = ('urn:schemas-upnp-org:service:WANIPConnection:1',
                'urn:schemas-upnp-org:service:WANPPPConnection:1')
DESCRIPTION = 'CS2 GC listen server'


class UpnpError(RuntimeError):
    pass


def discover(timeout=3.0):
    """Return the IGD root-device description URL, or raise."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(timeout)
        sock.sendto(DISCOVER.encode('ascii'), SSDP_ADDR)
        while True:
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                break
            for line in data.decode('latin-1').split('\r\n'):
                if line.lower().startswith('location:'):
                    return line.split(':', 1)[1].strip()
    finally:
        sock.close()
    raise UpnpError('No UPnP router (Internet Gateway Device) answered. '
                    'Enable UPnP on the router or forward port 27015 manually.')


def _control_url(description_url):
    """Return (service_control_url, service_type, external_ip_query_url_base)."""
    with urllib.request.urlopen(description_url, timeout=5) as response:
        root = ET.fromstring(response.read())
    ns = {'u': 'urn:schemas-upnp-org:device-1-0'}
    for service in root.iter('{urn:schemas-upnp-org:device-1-0}service'):
        stype = service.findtext('u:serviceType', default='', namespaces=ns)
        if stype in WAN_SERVICES:
            control = service.findtext('u:controlURL', default='', namespaces=ns)
            if not control:
                break
            return urllib.parse.urljoin(description_url, control), stype
    raise UpnpError('The router did not offer a WAN IP/PPP connection service.')


def _soap(control_url, service_type, action, args):
    body = ('<?xml version="1.0"?>\r\n'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            '<s:Body><u:%s xmlns:u="%s">%s</u:%s></s:Body></s:Envelope>'
            % (action, service_type,
               ''.join('<%s>%s</%s>' % (k, v, k) for k, v in args), action))
    parsed = urllib.parse.urlparse(control_url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
    path = parsed.path or '/'
    if parsed.query:
        path += '?' + parsed.query
    conn.request('POST', path, body.encode('utf-8'),
                 {'Content-Type': 'text/xml; charset="utf-8"',
                  'SOAPAction': '"%s#%s"' % (service_type, action)})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    if response.status != 200:
        raise UpnpError('Router rejected %s (HTTP %d): %s' % (action, response.status, data[:200].decode('latin-1', 'replace')))
    return data


def _local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(('8.8.8.8', 80))
        return sock.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        sock.close()


def forward(port=27015, remove=False):
    return forward_details(port, remove)[0]


def forward_details(port=27015, remove=False):
    """Like forward(), also returning the router's external IP ('' when unknown or when removing)."""
    description_url = discover()
    control_url, service_type = _control_url(description_url)
    if remove:
        for protocol in ('UDP', 'TCP'):
            try:
                _soap(control_url, service_type, 'DeletePortMapping',
                      [('NewRemoteHost', ''), ('NewExternalPort', str(port)), ('NewProtocol', protocol)])
            except UpnpError:
                pass  # a mapping that was never added is fine to skip
        return 'removed port %d forwarding' % port, ''
    host = _local_ip()
    for protocol in ('UDP', 'TCP'):
        _soap(control_url, service_type, 'AddPortMapping',
              [('NewRemoteHost', ''), ('NewExternalPort', str(port)), ('NewInternalPort', str(port)),
               ('NewInternalClient', host), ('NewEnabled', '1'), ('NewPortMappingDescription', DESCRIPTION),
               ('NewLeaseDuration', '0'), ('NewProtocol', protocol)])
    external = ''
    try:
        data = _soap(control_url, service_type, 'GetExternalIPAddress', [])
        match = ET.fromstring(data).find('.//{*}NewExternalIPAddress')
        external = (match.text or '').strip() if match is not None else ''
    except (UpnpError, ET.ParseError):
        pass
    return 'forwarded port %d to %s%s' % (port, host, ('; external IP: ' + external) if external else ''), external


def record_external_ip(external, cfg_dir):
    """Hand a public external IP to the Play menu's connect line through native_network's owned cfg."""
    import native_network
    cfg_dir = Path(cfg_dir)
    if not cfg_dir.is_dir() or native_network.classify(external) != 'Public':
        return False
    (cfg_dir / native_network.EXTERNAL_CFG_NAME).write_text(native_network.external_config(external), encoding='utf-8')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=27015)
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    try:
        message, external = forward_details(args.port, args.remove)
        print(message)
        # Deployed beside cs2.exe in game/bin/win64, so the game's cfg folder is game/csgo/cfg.
        if external and record_external_ip(external, Path(__file__).resolve().parents[2] / 'csgo/cfg'):
            print('external IP recorded for the Play menu connect line')
        return 0
    except (UpnpError, socket.error, urllib.error.URLError, ET.ParseError, http.client.HTTPException) as error:
        print('UPnP port forwarding failed: ' + str(error))
        print('Forward UDP/TCP port %d to this PC manually, or use Hamachi/ZeroTier instead.' % args.port)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
