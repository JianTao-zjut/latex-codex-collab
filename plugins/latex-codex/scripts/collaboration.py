"""Invitation identities, project collaboration, authorship and shared comments."""
from contextlib import closing
from difflib import SequenceMatcher
import hashlib
from http.cookies import SimpleCookie, CookieError
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid
from urllib.parse import urlsplit

COLORS = ('#2563eb', '#9333ea', '#c2410c', '#047857', '#be123c', '#0e7490', '#a16207', '#4338ca')
LOGIN_PAGE = b'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>LaTeX Codex</title><style>body{font:16px system-ui;max-width:440px;margin:12vh auto;padding:24px}input,button{box-sizing:border-box;width:100%;padding:12px;margin:10px 0}p{line-height:1.6}</style><h1>LaTeX Codex</h1><p>Open your personal invitation link to join this project.</p><form><input type="password" required aria-label="Invitation token" placeholder="Invitation token"><button>Join project</button></form><p id="error" role="status"></p><script>const form=document.querySelector('form'),input=document.querySelector('input'),error=document.querySelector('#error');const token=new URLSearchParams(location.hash.slice(1)).get('invite');history.replaceState(null,'',location.pathname);async function join(value){try{const r=await fetch('/collaboration/join',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:value})}),data=await r.json();if(!r.ok)throw new Error(data.error);location.replace('/');}catch(e){error.textContent=e.message;}}form.onsubmit=e=>{e.preventDefault();join(input.value);};if(token)join(token);</script></html>'''


class CollaborationConflict(ValueError):
    pass


def changes(before, after):
    return [{'start': a, 'end': b, 'text': after[c:d]} for kind, a, b, c, d
            in SequenceMatcher(None, before, after, autojunk=len(before) > 20000).get_opcodes()
            if kind != 'equal']


def merge_text(base, proposed, current):
    """Merge disjoint edits; simultaneous inserts survive; overlapping replacements never overwrite."""
    if proposed == base:
        return current
    if current == base or proposed == current:
        return proposed
    remote, local = changes(base, current), changes(base, proposed)
    pending = []
    for edit in local:
        identical = False
        for other in remote:
            if edit == other:
                identical = True
                break
            overlap = max(edit['start'], other['start']) < min(edit['end'], other['end'])
            inserted_inside = (edit['start'] == edit['end'] and other['start'] < edit['start'] < other['end']
                               or other['start'] == other['end'] and edit['start'] < other['start'] < edit['end'])
            if overlap or inserted_inside:
                raise CollaborationConflict('两人修改了同一段内容；你的草稿已保留，请比较后再确认。')
        if identical:
            continue

        def mapped(position, right):
            shift = sum(len(other['text']) - (other['end'] - other['start']) for other in remote
                        if other['end'] < position or other['end'] == position
                        and (other['start'] < other['end'] or right))
            return position + shift

        insertion = edit['start'] == edit['end']
        pending.append((mapped(edit['start'], True), mapped(edit['end'], insertion), edit['text']))
    for start, end, text in reversed(pending):
        current = current[:start] + text + current[end:]
    return current


def apply_authorship(spans, before, after, actor):
    for edit in reversed(changes(before, after)):
        start, end, text = edit['start'], edit['end'], edit['text']
        delta, updated = len(text) - (end - start), []
        for span in spans:
            left, right = span['start'], span['end']
            if right <= start:
                updated.append(span)
            elif left >= end:
                updated.append({**span, 'start': left + delta, 'end': right + delta})
            else:
                if left < start:
                    updated.append({**span, 'end': start})
                if right > end:
                    updated.append({**span, 'start': start + len(text), 'end': right + delta})
        if text:
            updated.append({'start': start, 'end': start + len(text), 'author': actor['id'],
                            'name': actor['name'], 'color': actor['color']})
        spans = sorted(updated, key=lambda span: span['start'])
    return spans


class Collaboration:
    def __init__(self, root, main_file, owner_name='Owner'):
        self.root, self.main_file = Path(root).resolve(), Path(main_file).resolve()
        folder = self.root / '.latex-codex'
        folder.mkdir(exist_ok=True)
        self.database = folder / 'collaboration.sqlite3'
        self.clients = {}
        self.failed_logins = {}
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY,name TEXT NOT NULL,color TEXT NOT NULL,role TEXT NOT NULL,token_hash TEXT UNIQUE NOT NULL,revoked INTEGER NOT NULL DEFAULT 0)')
            if 'can_codex' not in {row['name'] for row in db.execute('PRAGMA table_info(members)')}:
                db.execute('ALTER TABLE members ADD COLUMN can_codex INTEGER NOT NULL DEFAULT 0')
            db.execute('CREATE TABLE IF NOT EXISTS sessions(digest TEXT PRIMARY KEY,member TEXT NOT NULL,host TEXT NOT NULL,expires REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS versions(file TEXT NOT NULL,version TEXT NOT NULL,source TEXT NOT NULL,PRIMARY KEY(file,version))')
            db.execute('CREATE TABLE IF NOT EXISTS documents(file TEXT PRIMARY KEY,version TEXT NOT NULL,source TEXT NOT NULL,spans TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS comments(id TEXT PRIMARY KEY,file TEXT NOT NULL,author TEXT NOT NULL,name TEXT NOT NULL,color TEXT NOT NULL,selection TEXT NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL,text TEXT NOT NULL,created REAL NOT NULL,resolved INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS comment_replies(id TEXT PRIMARY KEY,comment TEXT NOT NULL,author TEXT NOT NULL,name TEXT NOT NULL,color TEXT NOT NULL,text TEXT NOT NULL,created REAL NOT NULL)')
            owner = db.execute("SELECT id FROM members WHERE role='owner' AND revoked=0 LIMIT 1").fetchone()
            owner_id = owner['id'] if owner else uuid.uuid4().hex
            self.owner_id = owner_id
            self.owner_token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO members(id,name,color,role,token_hash,revoked) VALUES (?,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET token_hash=excluded.token_hash',
                       (owner_id, owner_name, COLORS[0], 'owner', self.digest(self.owner_token)))

    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def session_cookie(self, member, host, secure=False, name='latex_collaboration', path='/'):
        session = secrets.token_urlsafe(32)
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                       (self.digest(session), member, host.lower(), time.time() + 43200))
        return f'{name}={session}; Path={path}; HttpOnly; SameSite=Strict; Max-Age=43200' + ('; Secure' if secure else '')

    def authorize(self, handler):
        route = urlsplit(handler.path).path
        if handler.command == 'POST' and route == '/collaboration/join':
            if not handler.headers.get('Origin'):
                handler.reply(403, {'error': '请从邀请页面登录。'})
                return None
            identity = handler.client_address[0]
            failures = [stamp for stamp in self.failed_logins.get(identity, []) if stamp > time.time() - 60]
            if len(failures) >= 10:
                handler.reply(429, {'error': '尝试次数过多，请一分钟后重试。'})
                return None
            try:
                size = int(handler.headers.get('Content-Length', '0'))
                if not 0 < size <= 2048 or handler.headers.get_content_type() != 'application/json':
                    raise ValueError('邀请数据无效。')
                token = json.loads(handler.rfile.read(size)).get('token')
                if not isinstance(token, str) or not 24 <= len(token) <= 128:
                    raise ValueError('邀请链接无效。')
                with closing(self.connect()) as db, db:
                    member = db.execute('SELECT * FROM members WHERE token_hash=? AND revoked=0', (self.digest(token),)).fetchone()
                    if member is None:
                        raise ValueError('邀请链接无效或已撤销。')
                handler.extra_headers = {'Set-Cookie': self.session_cookie(member['id'], handler.headers['Host'],
                    handler.headers['Origin'].startswith('https://'),
                    getattr(handler.server, 'collaboration_cookie', 'latex_collaboration'),
                    getattr(handler.server, 'url_prefix', '/'))}
                handler.reply(200, {'ok': True})
            except (ValueError, TypeError, AttributeError):
                failures.append(time.time())
                self.failed_logins[identity] = failures
                handler.reply(401, {'error': '邀请链接无效或已撤销。'})
            return None
        try:
            cookies = SimpleCookie()
            cookies.load(handler.headers.get('Cookie', ''))
            name = getattr(handler.server, 'collaboration_cookie', 'latex_collaboration')
            token = cookies[name].value if name in cookies else ''
            if not token and getattr(handler.server, 'legacy_cookie', False) and 'latex_collaboration' in cookies:
                token = cookies['latex_collaboration'].value
        except CookieError:
            token = ''
        with closing(self.connect()) as db:
            member = db.execute('SELECT m.id,m.name,m.color,m.role,m.can_codex FROM sessions s JOIN members m ON m.id=s.member WHERE s.digest=? AND s.host=? AND s.expires>? AND m.revoked=0',
                                (self.digest(token), handler.headers['Host'].lower(), time.time())).fetchone()
        if member is None or route == '/join':
            if handler.command == 'GET' and route in ('/', '/join'):
                handler.reply(200, LOGIN_PAGE, 'text/html; charset=utf-8')
            else:
                handler.reply(401, {'error': '请通过个人邀请链接登录此项目。'})
            return None
        if handler.command == 'POST' and not handler.headers.get('Origin'):
            handler.reply(403, {'error': '协作写入需要同源请求。'})
            return None
        actor = dict(member)
        actor['can_codex'] = actor['role'] == 'owner' or bool(actor['can_codex'])
        client = handler.headers.get('X-Latex-Client', 'default')
        if not re.fullmatch(r'[a-zA-Z0-9-]{1,64}', client):
            handler.reply(400, {'error': '页面标识无效。'})
            return None
        actor['client'] = client
        key = (actor['id'], client)
        self.clients[key] = {**self.clients.get(key, {'path': self.main_file}), 'seen': time.time(), 'actor': actor}
        self.clients = {key: value for key, value in self.clients.items() if value['seen'] > time.time() - 43200}
        return actor

    def selected(self, actor):
        return self.clients[(actor['id'], actor['client'])]['path']

    def select(self, actor, path):
        self.clients[(actor['id'], actor['client'])]['path'] = Path(path)

    def active_paths(self):
        return {item['path'] for item in self.clients.values() if item['seen'] > time.time() - 20}

    def members(self):
        with closing(self.connect()) as db:
            members = [dict(row) for row in db.execute('SELECT id,name,color,role,revoked,can_codex FROM members WHERE revoked=0')]
        online = {item['actor']['id'] for item in self.clients.values() if item['seen'] > time.time() - 20}
        return [{**member, 'can_codex': member['role'] == 'owner' or bool(member['can_codex']), 'online': member['id'] in online} for member in members]

    def invite(self, actor, name, role='editor'):
        if actor['role'] != 'owner':
            raise PermissionError('只有项目所有者可以邀请协作者。')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 48 or any(ord(char) < 32 for char in name):
            raise ValueError('请输入 1–48 字的姓名。')
        if role not in ('editor', 'viewer'):
            raise ValueError('协作者权限无效。')
        token, identity = secrets.token_urlsafe(32), uuid.uuid4().hex
        with closing(self.connect()) as db, db:
            count = db.execute('SELECT COUNT(*) FROM members WHERE revoked=0').fetchone()[0]
            if count >= 32:
                raise ValueError('每项目最多 32 位协作者。')
            color = COLORS[count % len(COLORS)]
            db.execute('INSERT INTO members(id,name,color,role,token_hash,revoked) VALUES (?,?,?,?,?,0)', (identity, name.strip(), color, role, self.digest(token)))
        return {'id': identity, 'name': name.strip(), 'color': color, 'role': role, 'token': token}

    def revoke(self, actor, member):
        if actor['role'] != 'owner':
            raise PermissionError('只有项目所有者可以撤销邀请。')
        with closing(self.connect()) as db, db:
            db.execute("UPDATE members SET revoked=1 WHERE id=? AND role!='owner'", (member,))
            db.execute('DELETE FROM sessions WHERE member=? AND member!=?', (member, actor['id']))

    def set_codex_permission(self, actor, member, allowed):
        if actor['role'] != 'owner':
            raise PermissionError('只有项目所有者可以分配 Codex 使用权限。')
        if type(allowed) is not bool:
            raise ValueError('Codex 权限必须为开启或关闭。')
        with closing(self.connect()) as db, db:
            target = db.execute('SELECT role,revoked FROM members WHERE id=?', (member,)).fetchone()
            if target is None or target['revoked'] or target['role'] != 'editor':
                raise ValueError('只能为有效的编辑协作者分配 Codex 权限。')
            db.execute('UPDATE members SET can_codex=? WHERE id=?', (int(allowed), member))

    def remember(self, path, state, actor=None):
        file = Path(path).relative_to(self.root).as_posix()
        source = state['source'].replace('\r\n', '\n')
        with closing(self.connect()) as db, db:
            row = db.execute('SELECT * FROM documents WHERE file=?', (file,)).fetchone()
            spans = json.loads(row['spans']) if row else []
            if row and row['version'] != state['version']:
                spans = apply_authorship(spans, row['source'], source, actor or {'id': 'external', 'name': '外部修改', 'color': '#64748b'})
            db.execute('INSERT OR IGNORE INTO versions VALUES (?,?,?)', (file, state['version'], source))
            db.execute('INSERT INTO documents VALUES (?,?,?,?) ON CONFLICT(file) DO UPDATE SET version=excluded.version,source=excluded.source,spans=excluded.spans',
                       (file, state['version'], source, json.dumps(spans, ensure_ascii=False)))
            # Retain a bounded set of merge bases; permanent history remains in History.
            db.execute('DELETE FROM versions WHERE file=? AND rowid NOT IN (SELECT rowid FROM versions WHERE file=? ORDER BY rowid DESC LIMIT 256)', (file, file))
        return spans

    def merge(self, path, current, version, proposed):
        if not isinstance(version, str) or not isinstance(proposed, str) or len(proposed) > 250000:
            raise ValueError('协作文稿最多 250,000 字符；请求数据无效。')
        self.remember(path, current)
        if version == current['version']:
            return proposed.replace('\r\n', '\n')
        file = Path(path).relative_to(self.root).as_posix()
        with closing(self.connect()) as db:
            base = db.execute('SELECT source FROM versions WHERE file=? AND version=?', (file, version)).fetchone()
        if base is None:
            raise CollaborationConflict('同步基线已过期；你的草稿已保留，请比较后再确认。')
        return merge_text(base['source'], proposed.replace('\r\n', '\n'), current['source'].replace('\r\n', '\n'))

    def state(self, actor, path, state):
        spans = self.remember(path, state)
        file = Path(path).relative_to(self.root).as_posix()
        with closing(self.connect()) as db:
            comments = [dict(row) for row in db.execute('SELECT * FROM comments WHERE file=? ORDER BY created', (file,))]
            replies = db.execute('SELECT r.* FROM comment_replies r JOIN comments c ON c.id=r.comment WHERE c.file=? ORDER BY r.created,r.id', (file,)).fetchall()
            threads = {item['id']: item for item in comments}
            for item in comments:
                item['replies'] = []
            for row in replies:
                threads[row['comment']]['replies'].append(dict(row))
        return {'enabled': True, 'me': {key: actor[key] for key in ('id', 'name', 'color', 'role', 'can_codex')},
                'members': self.members(), 'spans': spans, 'comments': comments, 'state': state}

    def comment(self, actor, path, state, data):
        if actor['role'] == 'viewer':
            raise PermissionError('只读协作者不能添加批注。')
        source = state['source'].replace('\r\n', '\n')
        start, end, text = data.get('start'), data.get('end'), data.get('text')
        if (data.get('version') != state['version'] or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(source) or not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000):
            raise CollaborationConflict('批注选区已变化；请先同步，再重新选择。')
        with closing(self.connect()) as db, db:
            db.execute('INSERT INTO comments VALUES (?,?,?,?,?,?,?,?,?,?,0)',
                       (uuid.uuid4().hex, Path(path).relative_to(self.root).as_posix(), actor['id'], actor['name'], actor['color'], source[start:end], start, end, text.strip(), time.time()))

    def reply_comment(self, actor, path, identity, text):
        if actor['role'] == 'viewer':
            raise PermissionError('只读协作者不能回复注释。')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
            raise ValueError('注释回复须为1至4000字。')
        file = Path(path).relative_to(self.root).as_posix()
        with closing(self.connect()) as db, db:
            row = db.execute('SELECT resolved FROM comments WHERE id=? AND file=?', (identity, file)).fetchone()
            if row is None or row['resolved']:
                raise CollaborationConflict('注释不存在或已解决，请刷新注释列表。')
            db.execute('INSERT INTO comment_replies VALUES (?,?,?,?,?,?,?)',
                       (uuid.uuid4().hex, identity, actor['id'], actor['name'], actor['color'], text.strip(), time.time()))

    def resolve_comment(self, actor, identity, resolved=True):
        if type(resolved) is not bool:
            raise ValueError('注释状态无效。')
        with closing(self.connect()) as db, db:
            row = db.execute('SELECT author FROM comments WHERE id=?', (identity,)).fetchone()
            if row is None or actor['role'] != 'owner' and row['author'] != actor['id']:
                raise PermissionError('只能处理自己添加的批注。')
            db.execute('UPDATE comments SET resolved=? WHERE id=?', (int(resolved), identity))
