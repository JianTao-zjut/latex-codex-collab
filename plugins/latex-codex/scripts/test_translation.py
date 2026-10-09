"""Incremental caching, cancellation, source boundaries and API permission checks."""
import json
from contextlib import closing
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

from editor import make_server
from translation import Translation, collect_blocks


class TranslationTests(unittest.TestCase):
    def test_incremental_restart_move_delete_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / 'note.md'
            file.write_bytes(b'# Introduction\r\n\r\nFirst English paragraph.\r\n\r\nSecond English paragraph.\r\n')
            calls, permitted = [], {'owner': True}
            class Job:
                def __init__(self, context):
                    self.context = context
                    self.result = {'status': 'running'}
                def start(self):
                    calls.append(self.context['items'])
                    self.result = {'status': 'done', 'translations': [
                        {'id': item['id'], 'text': '译文：' + item['source']} for item in self.context['items']]}
                    return self
                def cancel(self):
                    self.result = {'status': 'cancelled'}
            manager = Translation(root, file, lambda actor: permitted.get(actor, False), Job)
            def finish():
                manager.timer.cancel()
                manager.run(manager.generation, 'owner')
            original = file.read_bytes()
            self.assertEqual(manager.state()['pending'], 3)
            self.assertFalse(calls, 'Reading the cache must never start AI.')
            with self.assertRaises(PermissionError):
                manager.enable('editor')
            manager.enable('owner'); finish()
            self.assertEqual(len(calls[0]), 3)
            self.assertEqual(manager.status, 'ready')
            self.assertEqual(file.read_bytes(), original)
            self.assertTrue(manager.output.exists())
            manager.refresh('owner'); self.assertEqual(len(calls), 1)
            file.write_bytes(original.replace(b'Second', b'Changed'))
            manager.refresh('owner'); finish()
            self.assertEqual(len(calls[1]), 1)
            self.assertIn('Changed', calls[1][0]['source'])
            file.write_text('Changed English paragraph.\n\n# Introduction\n', encoding='utf-8')
            manager.refresh('owner'); finish()
            self.assertEqual(len(calls), 2, 'Moving and deleting cached paragraphs costs no AI calls.')
            self.assertNotIn('First English', manager.output.read_text(encoding='utf-8'))
            manager.cancel()
            restored = Translation(root, file, lambda _: True, Job)
            restored.enable('owner'); restored.timer.cancel(); restored.run(restored.generation, 'owner')
            self.assertEqual(len(calls), 2, 'Restart reuses the disk cache.')
            self.assertTrue(restored.state(restored.revision)['unchanged'])
            restored.cancel()

    def test_include_boundaries_and_no_code_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main, child = root / 'main.tex', root / 'section.tex'
            main.write_text('\\documentclass{article}\n\\begin{document}\n\nMain English text.\n\n\\input{section}\n\n\\end{document}', encoding='utf-8')
            child.write_text('Child English text.\n\n$x+y$', encoding='utf-8')
            blocks = collect_blocks(root, main)
            self.assertEqual([block['source'] for block in blocks], ['Main English text.', 'Child English text.', '$x+y$'])
            self.assertFalse(blocks[-1]['translate'])
            main.write_text('\\begin{document}\n\n\\input{../outside}', encoding='utf-8')
            with self.assertRaises(ValueError): collect_blocks(root, main)
            main.write_text('\\begin{document}\n\n\\input{main}', encoding='utf-8')
            with self.assertRaises(ValueError): collect_blocks(root, main)
            note = root / 'note.md'
            note.write_text('```python\n\nprint("English text")\n\n```\n\nReal prose.', encoding='utf-8')
            blocks = collect_blocks(root, note)
            self.assertTrue(all(not block['translate'] for block in blocks[:-1]))

    def test_revocation_and_stale_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root, jobs = Path(directory), []
            file = root / 'note.md'; file.write_text('English paragraph.', encoding='utf-8')
            allowed = {'editor': True}
            class Job:
                def __init__(self, context): self.result = {'status': 'running'}; jobs.append(self)
                def start(self): return self
                def cancel(self): self.result = {'status': 'cancelled'}
            manager = Translation(root, file, lambda actor: allowed.get(actor, False), Job)
            manager.enable('editor'); manager.timer.cancel()
            worker = threading.Thread(target=manager.run, args=(manager.generation, 'editor')); worker.start()
            for _ in range(100):
                if jobs: break
                threading.Event().wait(.01)
            self.assertTrue(jobs)
            allowed['editor'] = False
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(jobs[0].result['status'], 'cancelled')
            self.assertFalse(manager.texts)
            self.assertFalse(manager.enabled)

    def test_invalid_batch_preserves_completed_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); file = root / 'note.md'
            file.write_text('First paragraph.\n\nSecond paragraph.', encoding='utf-8')
            class Job:
                def __init__(self, context): self.context = context
                def start(self):
                    self.result = {'status':'done', 'translations':[{'id':'wrong','text':'invalid'}]}
                    return self
                def cancel(self): pass
            manager = Translation(root, file, lambda _: True, Job)
            manager.catalog()
            key = manager.blocks[0]['key']
            with closing(manager.connect()) as db, db:
                db.execute('INSERT INTO cache VALUES (?,?)', (key, '已经完成的译文'))
            manager.texts[key] = '已经完成的译文'
            manager.enable('owner'); manager.timer.cancel(); manager.run(manager.generation,'owner')
            self.assertEqual(manager.status,'error')
            self.assertEqual(manager.texts[key],'已经完成的译文')
            self.assertEqual(manager.state()['pending'],1)
            self.assertEqual(file.read_text(encoding='utf-8'),'First paragraph.\n\nSecond paragraph.')
            manager.cancel()

    def test_http_codex_permission_and_shared_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); file = root / 'note.md'
            file.write_text('A paragraph.', encoding='utf-8')
            server = make_server(file, collaborate=True, preferences_path=root / 'prefs.sqlite3')
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
            base = f'http://127.0.0.1:{server.server_port}'
            client = build_opener(ProxyHandler({}))
            def call(route, data=None, cookie=''):
                req = Request(base+route, None if data is None else json.dumps(data).encode(),
                    {'Origin': base, 'Content-Type':'application/json', 'Cookie':cookie})
                try: response = client.open(req, timeout=8)
                except HTTPError as error: response = error
                with response:
                    raw = response.read()
                    return response.code, json.loads(raw) if response.headers.get_content_type()=='application/json' else raw, response.headers
            try:
                _, _, headers = call('/collaboration/join', {'token':server.workspace.owner_token})
                owner = headers['Set-Cookie'].split(';')[0]
                _, invite, _ = call('/collaboration', {'action':'invite','name':'Reader'}, owner)
                _, _, headers = call('/collaboration/join', {'token':invite['token']})
                editor = headers['Set-Cookie'].split(';')[0]
                self.assertEqual(call('/translation')[0], 401)
                self.assertFalse(call('/translation', cookie=editor)[1]['can_translate'])
                self.assertEqual(call('/translation', {'action':'enable'}, editor)[0], 403)
                self.assertEqual(call('/translation/download', cookie=editor)[0], 200)
                call('/collaboration', {'action':'codex-permission','member':invite['id'],'allowed':True}, owner)
                self.assertEqual(call('/translation', {'action':'enable'}, editor)[0], 200)
                server.translation.timer.cancel()
                call('/collaboration', {'action':'codex-permission','member':invite['id'],'allowed':False}, owner)
                self.assertFalse(server.translation.enabled)
            finally:
                if server.translation: server.translation.cancel()
                server.shutdown(); worker.join(); server.server_close(); server.build.cleanup()


if __name__ == '__main__': unittest.main()
