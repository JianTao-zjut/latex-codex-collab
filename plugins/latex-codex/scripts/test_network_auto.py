import socket
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler
from network import lan_address, listener
from package_source import release_files


class AutomaticNetworkTests(unittest.TestCase):
    def test_port_reserved_by_the_server(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            with patch('network.DEFAULT_PORT', port):
                server = listener(BaseHTTPRequestHandler, '127.0.0.1', 'auto')
                try:
                    self.assertNotEqual(server.server_port, port)
                    with socket.socket() as second:
                        with self.assertRaises(OSError):
                            second.bind(server.server_address)
                finally:
                    server.server_close()
                with self.assertRaises(OSError):
                    listener(BaseHTTPRequestHandler, '127.0.0.1', port)

    def test_lan_detection_rejects_virtual_non_lan_routes(self):
        with patch('network.socket.socket') as probe, patch('network.socket.getaddrinfo') as lookup:
            probe.return_value.__enter__.return_value.getsockname.return_value = ('198.18.0.1', 0)
            lookup.return_value = [(None, None, None, None, ('127.0.0.1', 0)), (None, None, None, None, ('192.168.0.10', 0))]
            self.assertEqual(lan_address(), '192.168.0.10')
            lookup.return_value = []
            with self.assertRaises(ValueError):
                lan_address()

    def test_package_excludes_private_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plugin = root / 'plugins' / 'latex-codex'
            plugin.mkdir(parents=True)
            for name in ('source.py', 'paper.tex', 'paper.pdf', 'history.sqlite3', 'history.sqlite3-wal', '.env', 'auth.json'):
                (plugin / name).write_text('fixture', encoding='utf-8')
            private = plugin / '.latex-codex'
            private.mkdir()
            (private / 'private.md').write_text('private', encoding='utf-8')
            self.assertEqual([name for _, name in release_files(root)], ['plugins/latex-codex/source.py'])


if __name__ == '__main__':
    unittest.main()
