"""Explicit LAN detection and race-free automatic HTTP port selection."""
import errno
from http.server import ThreadingHTTPServer
import ipaddress
import os
import socket

DEFAULT_PORT = 8765
LAN_RANGES = tuple(ipaddress.ip_network(value) for value in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def lan_address():
    candidates = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            # UDP connect selects a local route; no packet/data is sent.
            probe.connect(('192.0.2.1', 9))
            candidates.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        candidates.extend(item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    for candidate in dict.fromkeys(candidates):
        address = ipaddress.ip_address(candidate)
        if any(address in network for network in LAN_RANGES):
            return candidate
    raise ValueError('No private LAN IPv4 address found; specify --host explicitly.')


def listener(handler, host, port, *, bind_and_activate=True):
    host = lan_address() if host == 'auto' else host
    automatic = port == 'auto'
    try:
        number = DEFAULT_PORT if automatic else int(port)
    except (ValueError, TypeError):
        raise ValueError('--port must be auto or an integer from 0 to 65535.') from None
    if not 0 <= number <= 65535 or isinstance(port, bool):
        raise ValueError('--port must be auto or an integer from 0 to 65535.')
    try:
        return LocalHTTPServer((host, number), handler, bind_and_activate=bind_and_activate)
    except OSError as error:
        # Only an occupied automatic port falls back. Explicit ports never silently change.
        if not automatic or error.errno != errno.EADDRINUSE and getattr(error, 'winerror', None) not in (10048, 10013):
            raise
        return LocalHTTPServer((host, 0), handler, bind_and_activate=bind_and_activate)
