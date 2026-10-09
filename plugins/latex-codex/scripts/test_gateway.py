"""Project invitation routing, admin isolation, legacy links and independent locks."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

from gateway import make_gateway
from project_routes import scope_text, scope_response


class GatewayTests(unittest.TestCase):
    def test_routes_sessions_admin_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for identity in ('paper', 'note'):
                folder = root / identity
                folder.mkdir()
                path = folder / 'main.md'
                path.write_bytes((f'# {identity}\r\nQuoted "/state" and /pdf stay verbatim.\r\n').encode())
                paths.append(path)
            registry = root / 'private-projects.json'
            public = 'https://public.example:8443'
            server = make_gateway([{'id': identity, 'name': identity, 'file': str(path)}
                for identity, path in zip(('paper', 'note'), paths)], port=0, public_urls=(public,),
                registry_path=registry, preferences_path=root / 'prefs.sqlite3', legacy_project='paper')
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f'http://127.0.0.1:{server.server_port}'
            client = build_opener(ProxyHandler({}))

            def request(route, data=None, cookie='', headers=None, origin=True):
                values = {'Content-Type': 'application/json', 'Cookie': cookie, 'X-Latex-Client': 'test'}
                if origin:
                    values['Origin'] = base
                values.update(headers or {})
                req = Request(base + route, None if data is None else json.dumps(data).encode(), values)
                try:
                    response = client.open(req, timeout=8)
                except HTTPError as error:
                    response = error
                with response:
                    body = response.read()
                    result = json.loads(body) if response.headers.get_content_type() == 'application/json' else body
                    return response.code, result, response.headers

            def join(identity, token, headers=None):
                code, body, values = request(f'/p/{identity}/collaboration/join', {'token': token}, headers=headers)
                self.assertEqual(code, 200, body)
                self.assertIn(f'Path=/p/{identity}/', values['Set-Cookie'])
                self.assertIn('HttpOnly; SameSite=Strict', values['Set-Cookie'])
                return values['Set-Cookie'].split(';')[0]

            try:
                for route in ('/admin/projects', '/p/paper/state', '/p/note/pdf', '/state', '/vendor/latex-chat.mjs'):
                    self.assertIn(request(route)[0], (401, 403))
                self.assertNotIn(str(paths[0]).encode(), request('/')[1])
                self.assertEqual(request('/admin/join', {'token': server.projects.admin_token}, origin=False)[0], 403)
                self.assertEqual(request('/admin/join', {'token': server.projects.admin_token},
                    headers={'Host': 'public.example:8443', 'Origin': public})[0], 403)
                self.assertEqual(request('/admin/projects', headers={'Host': 'evil.example'})[0], 403)
                self.assertEqual(request('/admin/join', {'token': server.projects.admin_token},
                    headers={'Origin': 'http://evil.example'})[0], 403)
                code, _, values = request('/admin/join', {'token': server.projects.admin_token})
                self.assertEqual(code, 200)
                admin = values['Set-Cookie'].split(';')[0]
                self.assertEqual(len(request('/admin/projects', cookie=admin)[1]['projects']), 2)
                self.assertEqual(request('/p/paper/state', cookie=admin)[0], 401, 'An admin cookie alone is not a project session.')
                code, opened, values = request('/admin/projects/paper/open', {}, admin)
                self.assertEqual(code, 200)
                self.assertEqual(opened['url'], '/p/paper/')
                owner = values['Set-Cookie'].split(';')[0]
                self.assertEqual(request('/p/paper/collaboration', cookie=owner)[1]['me']['role'], 'owner')
                self.assertEqual(request('/admin/projects', cookie=owner)[0], 403, 'Project owners cannot become global admins.')
                self.assertEqual(request('/p/note/state', cookie=owner)[0], 401)
                code, invitation, _ = request('/p/paper/collaboration', {'action': 'invite', 'name': 'Alice'}, owner)
                self.assertEqual(code, 200, invitation)
                self.assertTrue(invitation['url'].startswith(public + '/p/paper/join#invite='))
                alice = join('paper', invitation['token'])
                self.assertEqual(request('/p/note/collaboration/join', {'token': invitation['token']})[0], 401)
                self.assertEqual(request('/p/note/state', cookie=alice.replace('latex_project_paper=', 'latex_project_note='))[0], 401)
                self.assertEqual(request('/admin/projects', cookie=alice)[0], 403)
                self.assertEqual(request('/admin/projects', {'file': str(paths[1])}, alice)[0], 403)
                _, _, values = request('/admin/projects/note/open', {}, admin)
                note_owner = values['Set-Cookie'].split(';')[0]
                _, note_invitation, _ = request('/p/note/collaboration', {'action': 'invite', 'name': 'Alice'}, note_owner)
                note_alice = join('note', note_invitation['token'])
                both = alice + '; ' + note_alice
                paper_state = request('/p/paper/state', cookie=both)[1]
                note_state = request('/p/note/state', cookie=both)[1]
                self.assertEqual(paper_state['source'], paths[0].read_bytes().decode())
                self.assertEqual(note_state['source'], paths[1].read_bytes().decode())
                with patch('editor.chat_models') as models:
                    self.assertEqual(request('/p/paper/chat/models', cookie=both)[0], 403)
                    models.assert_not_called()
                self.assertEqual(request('/p/paper/collaboration', {'action': 'codex-permission',
                    'member': invitation['id'], 'allowed': True}, owner)[0], 200)
                self.assertTrue(request('/p/paper/collaboration', cookie=both)[1]['me']['can_codex'])
                self.assertFalse(request('/p/note/collaboration', cookie=both)[1]['me']['can_codex'])
                self.assertIn(request('/p/paper/source', {'path': str(paths[1]), 'version': paper_state['version']}, both)[0], (400, 403))
                updated = paper_state['source'].replace('# paper', '# Updated paper')
                self.assertEqual(request('/p/paper/save', {'source': updated, 'version': paper_state['version']}, both)[0], 200)
                self.assertIn(b'# Updated paper\r\n', paths[0].read_bytes())
                self.assertIn(b'# note\r\n', paths[1].read_bytes())
                page = request('/p/paper/', cookie=admin + '; ' + owner)[1].decode()
                self.assertIn('/p/paper/vendor/', page)
                self.assertIn("request('/p/paper/state'", page)
                self.assertTrue('href="/" target="_blank"' in page, 'The admin must have a return-to-project-list link.')
                login = request('/p/note/join')[1].decode()
                self.assertIn("fetch('/p/note/collaboration/join'", login)
                self.assertIn("location.replace('/p/note/')", login)
                module = request('/p/paper/vendor/latex-project-files.mjs', cookie=owner)[1].decode()
                self.assertIn("zip.href='/p/paper/files/archive'", module)
                self.assertIn("'/p/paper/files/download?path='", module)
                legacy = request('/join')[1].decode()
                self.assertIn('/p/paper/join', legacy)
                self.assertIn('+location.hash', legacy)
                backend = server.projects.items['paper']['server']
                old_session = backend.workspace.session_cookie(invitation['id'], base.split('//')[1]).split(';')[0]
                self.assertEqual(request('/state', cookie=old_session)[0], 200)
                self.assertEqual(request('/p/note/state', cookie=old_session)[0], 401)
                https_cookie = join('paper', invitation['token'], {'Host': 'public.example:8443', 'Origin': public})
                self.assertEqual(request('/p/paper/state', cookie=https_cookie)[0], 401, 'Sessions are bound to the login Host.')
                self.assertEqual(request('/p/paper/state', cookie=https_cookie,
                    headers={'Host': 'public.example:8443', 'Origin': public})[0], 200)
                self.assertEqual(request('/p/paper/state', cookie=https_cookie,
                    headers={'Host': 'public.example:8443', 'Origin': 'http://public.example:8443'})[0], 403)
                for route in ('/p/paper/../note/state', '/p/paper/%2e%2e/note/state', '/p/paper//state', '/p/paper\\note/state'):
                    self.assertEqual(request(route, cookie=both)[0], 400)
                self.assertEqual(request('/p/missing/state', cookie=both)[0], 404)
                third = root / 'third'
                third.mkdir()
                third_file = third / 'new.md'
                third_file.write_text('# New', encoding='utf-8')
                self.assertEqual(request('/admin/projects', {'file': str(third_file), 'name': 'Third'}, admin)[0], 200)
                self.assertEqual(request('/admin/projects', {'file': str(third_file), 'root': str(root)}, admin)[0], 400)
                persisted = json.loads(registry.read_text(encoding='utf-8'))['projects']
                self.assertEqual(len(persisted), 3)
                self.assertNotIn(server.projects.admin_token, registry.read_text(encoding='utf-8'))
                self.assertTrue(all('server' not in project and 'token' not in project for project in persisted))
                self.assertEqual(request('/p/paper/collaboration', {'action': 'revoke', 'member': invitation['id']}, owner)[0], 200)
                self.assertEqual(request('/p/paper/state', cookie=both)[0], 401)
                self.assertEqual(request('/p/note/state', cookie=both)[0], 200)
                # A long compile in one project cannot hold the other project's lock.
                entered, release, finished = threading.Event(), threading.Event(), threading.Event()
                def compile_stub(*args, **kwargs):
                    entered.set()
                    self.assertTrue(release.wait(5))
                    return False, 'isolated compile', 'xelatex'
                def compile_request():
                    state = request('/p/paper/state', cookie=owner)[1]
                    request('/p/paper/compile', {'source': state['source'], 'version': state['version'], 'preview': 'pdf'}, owner)
                    finished.set()
                with patch('editor.compile_tex', side_effect=compile_stub):
                    compiling = threading.Thread(target=compile_request)
                    compiling.start()
                    self.assertTrue(entered.wait(5))
                    try:
                        self.assertEqual(request('/p/note/state', cookie=note_alice)[0], 200)
                        self.assertFalse(finished.is_set())
                    finally:
                        release.set()
                        compiling.join(8)
                self.assertTrue(finished.is_set())
            finally:
                server.shutdown()
                worker.join()
                server.projects.close()
                server.server_close()

            reopened = make_gateway(json.loads(registry.read_text(encoding='utf-8'))['projects'],
                port=server.server_port, registry_path=registry, preferences_path=root / 'prefs.sqlite3')
            try:
                self.assertEqual(set(reopened.projects.items), {project['id'] for project in persisted})
                paper_members = reopened.projects.items['paper']['server'].workspace.members()
                self.assertFalse(any(member['id'] == invitation['id'] for member in paper_members))
                note_members = reopened.projects.items['note']['server'].workspace.members()
                self.assertTrue(any(member['name'] == 'Alice' and not member['can_codex'] for member in note_members))
            finally:
                reopened.projects.close()
                reopened.server_close()

    def test_scoping_preserves_json_and_document_text(self):
        html = b'''<script id="prefs" type="application/json">{"prompt":"/state"}</script><script>fetch('/state');location.replace('/')</script>'''
        scoped = scope_text(html, '/p/test/').decode()
        self.assertIn('"prompt":"/state"', scoped)
        self.assertIn("fetch('/p/test/state')", scoped)
        self.assertIn("location.replace('/p/test/')", scoped)
        source = {'source': '/history/pdf/test', 'before': '/history/pdf/a?v=1', 'pdf_url': '/proofread/pdf'}
        scoped = scope_response(source, '/p/test/')
        self.assertEqual(scoped['source'], source['source'])
        self.assertEqual(scoped['before'], '/p/test/history/pdf/a?v=1')
        self.assertEqual(scoped['pdf_url'], '/p/test/proofread/pdf')
        cached = {'images': True, 'changes': [{'kind': 'replace', 'before': [{'page': 1,
            'image': '/history/images/key/0-before-0.png'}], 'after': []}], 'source': '/history/images/verbatim'}
        scoped = scope_response(cached, '/p/test/')
        self.assertEqual(scoped['changes'][0]['before'][0]['image'], '/p/test/history/images/key/0-before-0.png')
        self.assertEqual(scoped['source'], cached['source'])
        self.assertEqual(cached['changes'][0]['before'][0]['image'], '/history/images/key/0-before-0.png')


if __name__ == '__main__':
    unittest.main()

