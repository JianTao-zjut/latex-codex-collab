"""Check configurable listening addresses and same-origin access without TeX."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from editor import make_server


class ListeningAddressTests(unittest.TestCase):
    def test_default_and_explicit_address(self):
        public_origin = 'https://editor.example.com'
        for host, public_urls in ((None, ()), ('127.0.0.2', ()), ('127.0.0.2', (public_origin + '/',))):
            with self.subTest(host=host, public_urls=public_urls), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = root / 'note.md'
                path.write_bytes(b'# Original\r\n')
                options = {'public_urls': public_urls}
                if host is not None:
                    options['host'] = host
                server = make_server(path, preferences_path=root / 'preferences.sqlite3', **options)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                expected_host = host or '127.0.0.1'
                base = f'http://{expected_host}:{server.server_port}'
                direct = build_opener(ProxyHandler({}))

                def request(route, data=None, headers=None):
                    body = None if data is None else json.dumps(data).encode('utf-8')
                    req = Request(base + route, body, {'Content-Type': 'application/json', **(headers or {})})
                    try:
                        with direct.open(req, timeout=5) as response:
                            return response.status, response.read()
                    except HTTPError as error:
                        return error.code, error.read()

                try:
                    self.assertEqual(server.server_address[0], expected_host)
                    self.assertEqual(request('/')[0], 200)
                    code, body = request('/state', headers={'Origin': base})
                    self.assertEqual(code, 200)
                    state = json.loads(body)
                    self.assertEqual(state['path'], str(path.resolve()))
                    payload = {'source': state['source'], 'version': state['version']}
                    self.assertEqual(request('/save', payload, {'Origin': base})[0], 200)
                    self.assertEqual(request('/save', payload, {'Origin': 'https://example.com'})[0], 403)
                    self.assertEqual(request('/state', headers={'Host': 'example.com'})[0], 403)
                    if host is not None:
                        self.assertEqual(request('/state', headers={'Host': f'127.0.0.1:{server.server_port}'})[0], 403)
                    public_headers = {'Host': 'editor.example.com', 'Origin': public_origin}
                    if public_urls:
                        self.assertEqual(request('/')[0], 200)
                        self.assertEqual(request('/state', headers={'Host': public_headers['Host']})[0], 200)
                        self.assertEqual(request('/state', headers=public_headers)[0], 200)
                        self.assertEqual(request('/save', payload, public_headers)[0], 200)
                        self.assertEqual(request('/save', payload, {**public_headers, 'Origin': 'http://editor.example.com'})[0], 403)
                        self.assertEqual(request('/save', payload, {**public_headers, 'Origin': base})[0], 403)
                        self.assertEqual(request('/save', payload, {**public_headers, 'Host': 'evil.example'})[0], 403)
                    else:
                        self.assertEqual(request('/state', headers=public_headers)[0], 403)
                    self.assertEqual(path.read_bytes(), b'# Original\r\n')
                finally:
                    server.shutdown()
                    worker.join()
                    server.server_close()
                    server.build.cleanup()

    def test_invalid_public_urls(self):
        for url in ('ftp://example.com', 'https://example.com/path', 'https://user@example.com',
                    'https://example.com?token=secret', 'https://example.com#fragment', 'https://example.com:99999'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                make_server(Path('not-opened.tex'), public_urls=(url,))


if __name__ == '__main__':
    unittest.main()
