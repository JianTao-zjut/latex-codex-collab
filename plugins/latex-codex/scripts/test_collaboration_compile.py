"""Real local TeX: an editor without Codex access compiles the fixed main from a child tab."""
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from urllib.request import Request, ProxyHandler, build_opener
from editor import make_server


@unittest.skipUnless(shutil.which('xelatex') or shutil.which('pdflatex'), 'Requires existing local TeX')
class CompileAccessTests(unittest.TestCase):
    def test_editor_compiles_child_without_codex_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main, child = root / 'main.tex', root / 'body.tex'
            main.write_text(r'\documentclass{article}\begin{document}\input{body}\end{document}', encoding='utf-8')
            child.write_text('A collaborator can compile this child through the main file.', encoding='utf-8')
            before = (main.read_bytes(), child.read_bytes())
            server = make_server(main, collaborate=True, main_thread='', preferences_path=root / '.preferences.sqlite3')
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f'http://127.0.0.1:{server.server_port}'
            client = build_opener(ProxyHandler({}))

            def call(route, data=None, cookie='', page='editor'):
                req = Request(base + route, None if data is None else json.dumps(data).encode(),
                              {'Origin': base, 'Cookie': cookie, 'Content-Type': 'application/json', 'X-Latex-Client': page})
                with client.open(req, timeout=120) as response:
                    raw = response.read()
                    return (json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw), response.headers

            try:
                _, headers = call('/collaboration/join', {'token': server.workspace.owner_token}, page='owner')
                owner = headers['Set-Cookie'].split(';')[0]
                invitation, _ = call('/collaboration', {'action': 'invite', 'name': 'Editor'}, owner, 'owner')
                _, headers = call('/collaboration/join', {'token': invitation['token']})
                editor = headers['Set-Cookie'].split(';')[0]
                initial, _ = call('/collaboration', cookie=editor)
                self.assertFalse(initial['me']['can_codex'])
                selected, _ = call('/source', {'path': str(child), 'version': initial['state']['version']}, editor)
                result, _ = call('/compile', {'path': str(child), 'source': selected['source'], 'version': selected['version']}, editor)
                self.assertTrue(result['ok'], result.get('log', ''))
                self.assertEqual(result['path'], str(child))
                pdf, _ = call('/pdf', cookie=editor)
                shared, _ = call('/pdf', cookie=owner, page='owner')
                self.assertTrue(pdf.startswith(b'%PDF-'))
                self.assertEqual(pdf, shared)
                self.assertEqual((main.read_bytes(), child.read_bytes()), before)
                info, _ = call('/collaboration', cookie=editor)
                self.assertFalse(info['me']['can_codex'])
                self.assertEqual(info['state']['main_file'], str(main))
            finally:
                server.shutdown()
                worker.join()
                server.server_close()
                server.build.cleanup()


if __name__ == '__main__':
    unittest.main()
