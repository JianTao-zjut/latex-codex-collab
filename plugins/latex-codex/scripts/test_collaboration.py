"""Invitation isolation, merge safety, authorship, comments and bounded files."""
import base64
from contextlib import closing
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

from collaboration import Collaboration, merge_text, CollaborationConflict, apply_authorship
from editor import make_server
from project_files import ProjectFiles
from history import History


class MergeTests(unittest.TestCase):
    def test_disjoint_and_unicode(self):
        self.assertEqual(merge_text('one two three', 'ONE two three', 'one two THREE'), 'ONE two THREE')
        self.assertEqual(merge_text('甲😀乙丙', '甲😀乙丁', '甲🌟乙丙'), '甲🌟乙丁')
        self.assertEqual(merge_text('ab', 'aYb', 'aXb'), 'aXYb')
        self.assertEqual(merge_text('ab', 'Zb', 'ab!'), 'Zb!')
        self.assertEqual(merge_text('abc', 'aXc', 'aXc'), 'aXc')

    def test_overlap_preserved(self):
        with self.assertRaises(CollaborationConflict):
            merge_text('abcdef', 'abXXef', 'abYYef')
        with self.assertRaises(CollaborationConflict):
            merge_text('abcdef', 'abef', 'abcZdef')

    def test_authorship_moves(self):
        actor = {'id': 'a', 'name': 'A', 'color': '#2563eb'}
        second = {'id': 'b', 'name': 'B', 'color': '#9333ea'}
        spans = apply_authorship([], 'ab', 'a😀b', actor)
        spans = apply_authorship(spans, 'a😀b', '!a😀b', second)
        self.assertEqual([(span['start'], span['end'], span['name']) for span in spans], [(0, 1, 'B'), (2, 3, 'A')])


class WorkspaceTests(unittest.TestCase):
    def test_upgrade_defaults_and_persists_permissions(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / 'main.tex'
            main.write_text('test', encoding='utf-8')
            folder = root / '.latex-codex'
            folder.mkdir()
            with closing(sqlite3.connect(folder / 'collaboration.sqlite3')) as db, db:
                db.execute('CREATE TABLE members(id TEXT PRIMARY KEY,name TEXT NOT NULL,color TEXT NOT NULL,role TEXT NOT NULL,token_hash TEXT UNIQUE NOT NULL,revoked INTEGER NOT NULL DEFAULT 0)')
                db.execute('INSERT INTO members VALUES (?,?,?,?,?,0)', ('legacy-editor', 'Legacy', '#2563eb', 'editor', Collaboration.digest('legacy-invitation')))
            workspace = Collaboration(root, main)
            self.assertFalse(next(member for member in workspace.members() if member['id'] == 'legacy-editor')['can_codex'])
            workspace.set_codex_permission({'role': 'owner'}, 'legacy-editor', True)
            reopened = Collaboration(root, main)
            self.assertTrue(next(member for member in reopened.members() if member['id'] == 'legacy-editor')['can_codex'])

    def test_members_files_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'project'
            root.mkdir()
            (Path(directory) / '.obsidian').mkdir()
            (Path(directory) / 'private.png').write_bytes(b'private image')
            (root / 'public.png').write_bytes(b'public image')
            (root / '.hidden').mkdir()
            (root / '.hidden' / 'private.png').write_bytes(b'hidden image')
            (root / '.secret.md').write_text('# private section', encoding='utf-8')
            main = root / 'main.md'
            main.write_bytes(b'one two three\r\n')
            # Old databases can already contain hidden-source records.
            History(main, root).record_sources({'.secret.md': '# private section'}, 'open')
            child = root / 'refs.bib'
            child.write_text('Reference.', encoding='utf-8')
            outside = Path(directory) / 'outside.md'
            outside.write_text('Outside.', encoding='utf-8')
            server = make_server(main, collaborate=True, owner_name='Owner', main_thread='', preferences_path=Path(directory) / 'prefs.sqlite3')
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f'http://127.0.0.1:{server.server_port}'
            direct = build_opener(ProxyHandler({}))

            def request(route, data=None, cookie='', client='one', origin=True):
                headers = {'Content-Type': 'application/json', 'Cookie': cookie, 'X-Latex-Client': client}
                if origin:
                    headers['Origin'] = base
                body = None if data is None else json.dumps(data).encode('utf-8')
                req = Request(base + route, body, headers)
                try:
                    with direct.open(req, timeout=10) as response:
                        raw = response.read()
                        return response.status, json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw, response.headers
                except HTTPError as error:
                    return error.code, json.loads(error.read()), error.headers

            def login(token, client):
                code, body, headers = request('/collaboration/join', {'token': token}, client=client)
                self.assertEqual(code, 200, body)
                self.assertIn('HttpOnly', headers['Set-Cookie'])
                return headers['Set-Cookie'].split(';')[0]

            try:
                self.assertEqual(request('/state')[0], 401)
                self.assertIn(b'Invitation', request('/')[1])
                owner = login(server.workspace.owner_token, 'owner')
                code, invitation, _ = request('/collaboration', {'action': 'invite', 'name': 'Alice'}, owner, 'owner')
                self.assertEqual(code, 200, invitation)
                alice = login(invitation['token'], 'alice')
                self.assertFalse(request('/collaboration', cookie=alice, client='alice')[1]['me']['can_codex'])
                self.assertEqual(request('/markdown-resource?path=public.png', cookie=alice, client='alice')[0], 200)
                for name in ('../private.png', 'private.png', '.hidden/private.png', '%2e%2e%2fprivate.png'):
                    self.assertEqual(request('/markdown-resource?path=' + name, cookie=alice, client='alice')[0], 404)
                current_boundary = request('/state', cookie=alice, client='alice')[1]
                self.assertEqual(request('/project', {'project_root': str(Path(directory)), 'main_file': str(outside), 'version': current_boundary['version']}, alice, 'alice')[0], 403)
                self.assertEqual(request('/open', {'path': str(outside)}, alice, 'alice')[0], 403)
                self.assertIn(request('/source', {'path': str(outside), 'version': current_boundary['version']}, alice, 'alice')[0], (400, 403))
                self.assertIn(request('/history?path=' + str(outside), cookie=alice, client='alice')[0], (400, 403, 409))
                history = request('/history?path=' + str(main), cookie=alice, client='alice')[1]
                self.assertNotIn('.secret.md', [row['file'] for row in history['revisions']])
                with patch('editor.chat_models', return_value=[]) as models, patch('editor.ChatJob') as jobs:
                    self.assertEqual(request('/chat/models', cookie=alice, client='alice')[0], 403)
                    models.assert_not_called()
                    self.assertEqual(request('/chat', {'can_codex': True, 'role': 'owner'}, alice, 'alice')[0], 403)
                    jobs.assert_not_called()
                    self.assertEqual(request('/history/summaries', {}, alice, 'alice')[0], 403)
                    permission = {'action': 'codex-permission', 'member': invitation['id'], 'allowed': True}
                    self.assertEqual(request('/collaboration', permission, alice, 'alice')[0], 403)
                    self.assertEqual(request('/collaboration', {**permission, 'allowed': 'true'}, owner, 'owner')[0], 400)
                    self.assertEqual(request('/collaboration', permission, owner, 'owner')[0], 200)
                    self.assertTrue(request('/collaboration', cookie=alice, client='alice')[1]['me']['can_codex'])
                    self.assertEqual(request('/chat/models', cookie=alice, client='alice')[0], 200)
                    models.assert_called_once()
                    cancellation = Mock()
                    job = SimpleNamespace(cancel=cancellation, id='f' * 32, result={'status': 'running'})
                    job.start = lambda: job
                    jobs.return_value = job
                    query = {'source': 'one two three', 'selection': 'one', 'messages': [{'role': 'user', 'content': 'A test question.'}]}
                    self.assertEqual(request('/chat', query, alice, 'alice')[0], 200)
                    jobs.assert_called_once()
                    self.assertEqual(server.chat.owner_id, invitation['id'])
                    _, bob_invite, _ = request('/collaboration', {'action': 'invite', 'name': 'Bob'}, owner, 'owner')
                    bob = login(bob_invite['token'], 'bob')
                    self.assertEqual(request('/collaboration', {'action': 'codex-permission', 'member': bob_invite['id'], 'allowed': True}, owner, 'owner')[0], 200)
                    self.assertEqual(request('/chat?id=' + job.id, cookie=bob, client='bob')[0], 403)
                    self.assertEqual(request('/chat/cancel', {'id': job.id}, bob, 'bob')[0], 403)
                    cancellation.assert_not_called()
                    self.assertEqual(request('/collaboration', {**permission, 'allowed': False}, owner, 'owner')[0], 200)
                    cancellation.assert_called_once()
                    self.assertIsNone(server.chat)
                    self.assertEqual(request('/chat/models', cookie=alice, client='alice')[0], 403)
                    self.assertEqual(request('/chat', {}, alice, 'alice')[0], 403)
                self.assertEqual(request('/collaboration', {'action': 'invite', 'name': 'No'}, alice, 'alice')[0], 403)
                initial = request('/collaboration', cookie=owner, client='owner')[1]['state']
                self.assertEqual(request('/source', {'path': str(child), 'version': initial['version']}, owner, 'owner')[0], 200)
                self.assertEqual(request('/state', cookie=owner, client='owner')[1]['path'], str(child))
                self.assertEqual(request('/state', cookie=alice, client='alice')[1]['path'], str(main))
                alice_state = request('/state', cookie=alice, client='alice')[1]
                code, result, _ = request('/collaboration', {'action': 'sync', 'version': alice_state['version'], 'source': 'ONE two three\n'}, alice, 'alice')
                self.assertEqual(code, 200, result)
                self.assertEqual(result['spans'][0]['name'], 'Alice')
                # Another owner tab still has the same original base; edits merge rather than overwrite.
                request('/collaboration', cookie=owner, client='owner-main')
                code, result, _ = request('/collaboration', {'action': 'sync', 'version': alice_state['version'], 'source': 'one two THREE\n'}, owner, 'owner-main')
                self.assertEqual(code, 200, result)
                self.assertEqual(main.read_bytes(), b'ONE two THREE\r\n')
                current = result['state']
                # A compile acknowledgement must carry the actual merged source and selected path.
                with patch('editor.compile_tex', return_value=(False, 'isolated compile check', 'xelatex')):
                    code, compiled, _ = request('/compile', {'source': current['source'], 'version': current['version'], 'preview': 'pdf'}, alice, 'alice')
                self.assertEqual(code, 200, compiled)
                self.assertEqual(compiled['source'], current['source'])
                self.assertEqual(compiled['path'], str(main))
                self.assertFalse(request('/collaboration', cookie=alice, client='alice')[1]['me']['can_codex'])
                self.assertEqual(request('/chat', {}, alice, 'alice')[0], 403)
                before_conflict = main.read_bytes()
                self.assertEqual(request('/collaboration', {'action': 'sync', 'version': alice_state['version'], 'source': 'OTHER two three\n'}, alice, 'alice')[0], 409)
                self.assertEqual(main.read_bytes(), before_conflict)
                _, viewer_invite, _ = request('/collaboration', {'action': 'invite', 'name': 'Reader', 'role': 'viewer'}, owner, 'owner-main')
                viewer = login(viewer_invite['token'], 'viewer')
                with patch('editor.compile_tex') as tex:
                    self.assertEqual(request('/compile', {'source': current['source'], 'version': current['version'], 'preview': 'pdf'}, viewer, 'viewer')[0], 403)
                    tex.assert_not_called()
                self.assertEqual(request('/collaboration', {'action': 'sync', 'source': 'overwrite', 'version': current['version']}, viewer, 'viewer')[0], 403)
                self.assertEqual(request('/save', {'source': 'overwrite', 'version': current['version']}, viewer, 'viewer')[0], 403)
                code, _, _ = request('/collaboration', {'action': 'comment', 'version': current['version'], 'start': 0, 'end': 3, 'text': 'Check this.'}, alice, 'alice')
                self.assertEqual(code, 200)
                comments = request('/collaboration', cookie=owner, client='owner-main')[1]['comments']
                self.assertEqual(comments[0]['name'], 'Alice')
                identity = comments[0]['id']
                self.assertFalse(request('/collaboration', cookie=alice, client='alice')[1]['me']['can_codex'])
                self.assertEqual(request('/collaboration', {'action': 'comment-reply', 'id': identity, 'text': 'No model needed.'}, alice, 'alice')[0], 200)
                self.assertEqual(request('/collaboration', {'action': 'comment-reply', 'id': identity, 'text': 'viewer reply'}, viewer, 'viewer')[0], 403)
                self.assertEqual(request('/collaboration', {'action': 'comment-reply', 'id': identity, 'path': str(child), 'text': 'wrong file'}, alice, 'alice')[0], 409)
                discussion = request('/collaboration', cookie=viewer, client='viewer')[1]['comments'][0]
                self.assertEqual(discussion['replies'][0]['name'], 'Alice')
                self.assertEqual(discussion['replies'][0]['text'], 'No model needed.')
                self.assertEqual(request('/collaboration', {'action': 'resolve', 'id': identity}, bob, 'bob')[0], 403)
                self.assertEqual(request('/collaboration', {'action': 'resolve', 'id': identity}, alice, 'alice')[0], 200)
                self.assertEqual(request('/collaboration', {'action': 'comment-reply', 'id': identity, 'text': 'late'}, alice, 'alice')[0], 409)
                self.assertEqual(request('/collaboration', {'action': 'resolve', 'id': identity, 'resolved': False}, owner, 'owner-main')[0], 200)
                self.assertEqual(request('/collaboration', {'action': 'comment-reply', 'id': identity, 'text': 'after reopen'}, alice, 'alice')[0], 200)
                self.assertEqual(request('/open', {'path': str(outside)}, owner, 'owner-main')[0], 403)
                self.assertEqual(request('/save', {'source': 'bad', 'version': current['version']}, alice, 'alice', origin=False)[0], 403)
                self.assertEqual(request('/files', {'action': 'create', 'path': '../outside.md'}, owner, 'owner-main')[0], 400)
                self.assertEqual(request('/files', {'action': 'create', 'path': 'new.tex'}, alice, 'alice')[0], 403)
                content = base64.b64encode(b'figure bytes').decode()
                self.assertEqual(request('/files', {'action': 'upload', 'path': 'figures/demo.png', 'content': content}, owner, 'owner-main')[0], 200)
                self.assertEqual(request('/files/download?path=figures/demo.png', cookie=alice, client='alice')[1], b'figure bytes')
                file_version = request('/files/version?path=figures/demo.png', cookie=owner, client='owner-main')[1]['version']
                self.assertEqual(request('/files', {'action': 'rename', 'path': 'figures/demo.png', 'new_path': 'figures/new.png', 'version': file_version}, owner, 'owner-main')[0], 200)
                self.assertEqual(request('/files', {'action': 'delete', 'path': 'figures/new.png', 'version': file_version}, owner, 'owner-main')[0], 200)
                self.assertTrue(list((root / '.latex-codex' / 'trash').iterdir()))
                history = request('/history?path=' + str(main), cookie=owner, client='owner-main')[1]
                self.assertTrue(any(row.get('author', {}).get('name') == 'Alice' for row in history['revisions']))
                self.assertEqual(request('/collaboration', {'action': 'revoke', 'member': invitation['id']}, owner, 'owner-main')[0], 200)
                collaboration = request('/collaboration', cookie=owner, client='owner-main')[1]
                self.assertNotIn(invitation['id'], [member['id'] for member in collaboration['members']])
                self.assertIn(bob_invite['id'], [member['id'] for member in collaboration['members']])
                self.assertIn(viewer_invite['id'], [member['id'] for member in collaboration['members']])
                self.assertEqual(collaboration['comments'][0]['name'], 'Alice')
                self.assertTrue(any(span['name'] == 'Alice' for span in collaboration['spans']))
                history = request('/history?path=' + str(main), cookie=owner, client='owner-main')[1]
                self.assertTrue(any(row.get('author', {}).get('name') == 'Alice' for row in history['revisions']))
                self.assertEqual(request('/state', cookie=alice, client='alice')[0], 401)
                self.assertEqual(request('/collaboration/join', {'token': invitation['token']}, client='alice')[0], 401)
            finally:
                server.shutdown()
                worker.join()
                server.server_close()
                server.build.cleanup()

    def test_file_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / 'main.tex'
            main.write_text('source', encoding='utf-8')
            files = ProjectFiles(root, main)
            for name in ('../secret.txt', '/etc/passwd', '.latex-codex/history.sqlite3', 'data/../secret', 'C:/secret', 'data/file:stream', 'CON.txt', 'trailing. '):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    files.path(name, existing=False)
            version = files.version(main)
            with self.assertRaises(ValueError):
                files.upload('bad.png', 'invalid base64!')
            secret = root / '.secret.txt'
            secret.write_text('private', encoding='utf-8')
            with self.assertRaises(ValueError):
                files.trash('main.tex', version)
            with self.assertRaises(ValueError):
                files.upload('main.tex', base64.b64encode(b'overwrite').decode())
            archive, _ = files.archive()
            import io, zipfile
            with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
                self.assertEqual(zipped.namelist(), ['main.tex'])


if __name__ == '__main__':
    unittest.main()
