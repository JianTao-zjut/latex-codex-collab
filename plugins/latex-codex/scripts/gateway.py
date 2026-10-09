"""One listening port, project-scoped invitations, and a private local admin."""
import argparse
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import threading
import time
from urllib.parse import urlsplit

from editor import make_server
from project_routes import ROUTES


STYLE = '<style>body{font:16px system-ui;background:#f5f6f8;color:#18202c;max-width:920px;margin:7vh auto;padding:24px}h1{font-size:28px}p{line-height:1.7}section,article{background:white;border:1px solid #dde2e8;border-radius:14px;padding:20px;margin:18px 0}input,button{font:inherit;box-sizing:border-box;padding:10px 14px;border:1px solid #cbd3df;border-radius:8px}input{width:100%;margin:8px 0 14px}button{cursor:pointer;background:#185adb;color:white}button:disabled{opacity:.6}small{color:#64748b}label{display:block}#status{white-space:pre-wrap;color:#a12a30}</style>'
ADMIN_LOGIN = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>LaTeX Codex · 管理登录</title>' + STYLE + '''<h1>主管理员登录</h1><p>使用服务启动时提供的私人管理链接。协作者请使用自己的项目邀请链接。</p><section><form><label>管理令牌<input type="password" required autocomplete="off" aria-label="管理令牌"></label><button>登录管理</button></form><p id="status" role="status"></p></section><script>
const form=document.querySelector('form'),input=document.querySelector('input'),status=document.querySelector('#status');
const token=new URLSearchParams(location.hash.slice(1)).get('admin');history.replaceState(null,'',location.pathname);
async function login(token){try{const r=await fetch('/admin/join',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})}),data=await r.json();if(!r.ok)throw new Error(data.error);location.replace('/');}catch(e){status.textContent=e.message;}}
form.onsubmit=e=>{e.preventDefault();void login(input.value);};if(token)void login(token);
</script></html>''').encode('utf-8')
ADMIN_PAGE = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>LaTeX Codex · 项目管理</title>' + STYLE + '''<h1>项目管理</h1><p>选择要访问的项目。每个项目独立管理协作者和 Codex 权限。</p><div id="projects"></div><section><h2>添加本地文稿</h2><form><label>文稿完整路径<input name="file" required placeholder="本机 .tex / .md / .markdown 文件的完整路径"></label><label>项目名称<input name="name" maxlength="96" placeholder="可留空，使用文稿名称"></label><label>项目根目录<input name="root" placeholder="可留空，使用文稿所在目录"></label><button>添加项目</button></form><p id="status" role="status"></p></section><script>
const projects=document.querySelector('#projects'),form=document.querySelector('form'),status=document.querySelector('#status');
async function api(url,data){const r=await fetch(url,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:undefined),result=await r.json();if(!r.ok)throw new Error(result.error);return result;}
async function load(){const data=await api('/admin/projects');projects.replaceChildren();for(const project of data.projects){const card=document.createElement('article'),title=document.createElement('h2'),file=document.createElement('p'),open=document.createElement('button');title.textContent=project.name;file.textContent=project.file;open.textContent='打开项目';open.onclick=async()=>{open.disabled=true;try{const result=await api('/admin/projects/'+project.id+'/open',{});location.assign(result.url);}catch(e){status.textContent=e.message;open.disabled=false;}};card.append(title,file,open);projects.append(card);}}
form.onsubmit=async e=>{e.preventDefault();const button=form.querySelector('button');button.disabled=true;try{await api('/admin/projects',Object.fromEntries(new FormData(form)));form.reset();status.textContent='项目已添加';await load();}catch(e){status.textContent=e.message;}finally{button.disabled=false;}};
load().catch(e=>{status.textContent=e.message;});
</script></html>''').encode('utf-8')
PUBLIC_PAGE = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>LaTeX Codex</title>' + STYLE + '<h1>LaTeX Codex</h1><p>请通过你的个人邀请链接进入对应项目。</p></html>').encode('utf-8')


def cleanup_project(server):
    for name in ('chat', 'history_summary', 'translation'):
        job = getattr(server, name, None)
        if job:
            job.cancel()
    for cached in server.history_pdfs.values():
        if cached.get('directory'):
            cached['directory'].cleanup()
    server.build.cleanup()
    server.server_close()


class Projects:
    def __init__(self, server, public_urls, owner_name, registry_path, preferences_path, legacy_project):
        self.server, self.public_urls, self.owner_name = server, tuple(public_urls), owner_name
        self.registry_path, self.preferences_path, self.legacy_project = registry_path, preferences_path, legacy_project
        self.lock = threading.RLock()
        self.items = {}
        self.admin_token = secrets.token_urlsafe(32)
        self.admin_digest = self.digest(self.admin_token)
        self.sessions, self.failed_logins = {}, {}
        self.local_host = f'{server.server_address[0]}:{server.server_port}'
        self.origins = {'http://' + self.local_host}
        for url in public_urls:
            parsed = urlsplit(url)
            if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None
                    or parsed.password is not None or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
                raise ValueError('Public URL must be an http(s) origin without a path or credentials.')
            parsed.port
            self.origins.add(f'{parsed.scheme}://{parsed.netloc.lower()}')

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    def authorized_origin(self, handler):
        hosts, origins = handler.headers.get_all('Host', []), handler.headers.get_all('Origin', [])
        host = hosts[0].lower() if len(hosts) == 1 else ''
        matching = {origin for origin in self.origins if urlsplit(origin).netloc == host}
        return bool(matching) and len(origins) <= 1 and (not origins or origins[0] in matching)

    def local_admin(self, handler):
        if handler.headers['Host'].lower() != self.local_host:
            return False
        try:
            cookies = SimpleCookie()
            cookies.load(handler.headers.get('Cookie', ''))
            token = cookies['latex_gateway_admin'].value if 'latex_gateway_admin' in cookies else ''
        except CookieError:
            return False
        with self.lock:
            session = self.sessions.get(self.digest(token))
            return bool(session and session['host'] == self.local_host and session['expires'] > time.time())

    def login(self, handler, token):
        if handler.headers['Host'].lower() != self.local_host:
            raise PermissionError('主管理员请使用本机管理入口。')
        if not isinstance(token, str) or not 24 <= len(token) <= 128:
            token = ''
        identity = handler.client_address[0]
        with self.lock:
            failures = [stamp for stamp in self.failed_logins.get(identity, []) if stamp > time.time() - 60]
            if len(failures) >= 10:
                raise PermissionError('尝试次数过多，请一分钟后重试。')
            if not hmac.compare_digest(self.digest(token), self.admin_digest):
                self.failed_logins[identity] = failures + [time.time()]
                raise PermissionError('管理链接无效，请使用当前服务打印的私人链接。')
            session = secrets.token_urlsafe(32)
            self.sessions = {key: value for key, value in self.sessions.items() if value['expires'] > time.time()}
            self.sessions[self.digest(session)] = {'host': self.local_host, 'expires': time.time() + 43200}
        return f'latex_gateway_admin={session}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200'

    def register(self, entry, persist=True):
        if not isinstance(entry, dict) or not isinstance(entry.get('file'), str):
            raise ValueError('请提供文稿的完整路径。')
        file = Path(entry['file']).resolve(strict=True)
        root = Path(entry['root']).resolve(strict=True) if entry.get('root') else file.parent
        name = entry.get('name') or (root.name if file.stem.lower() == 'main' else file.stem)
        identity = entry.get('id') or hashlib.sha256(os.path.normcase(str(root)).encode('utf-8')).hexdigest()[:16]
        if not isinstance(identity, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', identity):
            raise ValueError('项目标识无效。')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 96 or any(ord(char) < 32 for char in name):
            raise ValueError('项目名称需为 1–96 字。')
        with self.lock:
            for item in self.items.values():
                if item['root'] == str(root):
                    if item['file'] == str(file):
                        return item
                    raise ValueError('该目录已有项目，请在现有项目中打开文件，或使用独立的项目目录。')
                other_root = Path(item['root'])
                if root.is_relative_to(other_root) or other_root.is_relative_to(root):
                    raise ValueError('项目目录不能互相包含，请选择彼此独立的目录。')
            if identity in self.items or len(self.items) >= 32:
                raise ValueError('项目标识重复或项目数量已达上限。')
            backend = make_server(file, port=self.server.server_port, host=self.server.server_address[0],
                project_root=root, public_urls=self.public_urls, collaborate=True, owner_name=self.owner_name,
                main_thread='', preferences_path=self.preferences_path, url_prefix=f'/p/{identity}/',
                bind_and_activate=False, legacy_cookie=identity == self.legacy_project)
            item = {'id': identity, 'name': name.strip(), 'file': str(file), 'root': str(root), 'server': backend}
            self.items[identity] = item
            try:
                if persist:
                    self.save()
            except OSError:
                self.items.pop(identity)
                cleanup_project(backend)
                raise
            return item

    def save(self):
        if self.registry_path is None:
            return
        target = Path(self.registry_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                         prefix='.projects-', suffix='.json', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'projects': self.list()}, stream, ensure_ascii=False, indent=2)
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def list(self):
        with self.lock:
            return [{key: item[key] for key in ('id', 'name', 'file', 'root')} for item in self.items.values()]

    def close(self):
        for item in self.items.values():
            cleanup_project(item['server'])


def make_gateway(projects=(), host='127.0.0.1', port='auto', public_urls=(), owner_name='Owner',
                 registry_path=None, preferences_path=None, legacy_project=''):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def log_message(self, *_):
            pass

        def reply(self, code, data, content_type='application/json; charset=utf-8', cookie=None):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'SAMEORIGIN')
            self.send_header('Referrer-Policy', 'same-origin')
            if cookie:
                self.send_header('Set-Cookie', cookie)
            try:
                self.end_headers()
                self.wfile.write(body)
            except (ConnectionError, TimeoutError):
                pass

        def data(self):
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192 or self.headers.get_content_type() != 'application/json':
                raise ValueError('请求数据无效。')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('请求数据无效。')
            return data

        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch()

        def dispatch(self):
            manager = self.server.projects
            parsed = urlsplit(self.path)
            route = parsed.path
            if (parsed.scheme or parsed.netloc or not route.startswith('/') or '\\' in route or '%' in route
                    or '//' in route or any(part in ('.', '..') for part in route.split('/'))
                    or any(ord(char) < 32 for char in route)):
                self.reply(400, {'error': '请求路径无效。'})
                return
            if not manager.authorized_origin(self):
                self.reply(403, {'error': 'Only same-origin requests to configured addresses are accepted.'})
                return
            if self.command == 'POST' and not self.headers.get('Origin'):
                self.reply(403, {'error': '写入需要同源请求。'})
                return
            try:
                if route.startswith('/admin'):
                    if self.headers['Host'].lower() != manager.local_host:
                        raise PermissionError('主管理员请使用本机管理入口。')
                    if route == '/admin/join':
                        if self.command == 'GET':
                            self.reply(200, ADMIN_LOGIN, 'text/html; charset=utf-8')
                        else:
                            cookie = manager.login(self, self.data().get('token'))
                            self.reply(200, {'ok': True}, cookie=cookie)
                        return
                    if not manager.local_admin(self):
                        raise PermissionError('请先通过私人管理链接登录。')
                    if route == '/admin/projects':
                        if self.command == 'POST':
                            data = self.data()
                            # IDs and backend addresses are controlled by the server.
                            manager.register({key: data.get(key) for key in ('file', 'name', 'root')})
                        self.reply(200, {'projects': manager.list()})
                        return
                    match = re.fullmatch(r'/admin/projects/([a-z0-9-]+)/open', route)
                    if match and self.command == 'POST':
                        self.data()
                        with manager.lock:
                            item = manager.items.get(match[1])
                        if item is None:
                            self.reply(404, {'error': '项目不存在。'})
                            return
                        backend = item['server']
                        cookie = backend.workspace.session_cookie(backend.workspace.owner_id, self.headers['Host'],
                            False, backend.collaboration_cookie, backend.url_prefix)
                        self.reply(200, {'url': backend.url_prefix}, cookie=cookie)
                        return
                    self.reply(404, {'error': '入口不存在。'})
                    return
                if route == '/' and self.command == 'GET':
                    local = self.headers['Host'].lower() == manager.local_host
                    page = ADMIN_PAGE if manager.local_admin(self) else ADMIN_LOGIN if local else PUBLIC_PAGE
                    self.reply(200, page, 'text/html; charset=utf-8')
                    return
                match = re.match(r'^/p/([a-z0-9-]+)/', route)
                identity = match[1] if match else manager.legacy_project
                with manager.lock:
                    item = manager.items.get(identity)
                if item is None or (not match and route.split('/')[1] not in ROUTES):
                    self.reply(404, {'error': '项目入口不存在，请使用完整的邀请链接。'})
                    return
                backend = item['server']
                # Reuse the editor's full authenticated handler, with its own state lock,
                # filesystem boundary and project DB. No secondary listener is started.
                delegated = backend.RequestHandlerClass.__new__(backend.RequestHandlerClass)
                delegated.__dict__.update(self.__dict__)
                delegated.server = backend
                delegated.gateway_admin = manager.local_admin(self)
                if match:
                    delegated.path = '/' + self.path[len(backend.url_prefix):]
                elif route == '/join' and self.command == 'GET':
                    page = ('<!doctype html><meta charset="utf-8"><script>location.replace(' +
                            json.dumps(backend.url_prefix + 'join') + '+location.hash)</script>').encode('utf-8')
                    self.reply(200, page, 'text/html; charset=utf-8')
                    return
                if self.command == 'GET':
                    delegated.do_GET()
                else:
                    delegated.do_POST()
                self.close_connection = delegated.close_connection
            except PermissionError as error:
                self.reply(403, {'error': str(error)})
            except (ValueError, OSError, TypeError, sqlite3.Error) as error:
                self.reply(400, {'error': str(error)})

    from network import listener
    gateway = listener(Handler, host, port)
    try:
        gateway.projects = Projects(gateway, public_urls, owner_name, registry_path, preferences_path, legacy_project)
        for project in projects:
            gateway.projects.register(project, persist=False)
        if legacy_project and legacy_project not in gateway.projects.items:
            raise ValueError('Legacy project is not registered.')
        if registry_path:
            gateway.projects.save()
    except Exception:
        if hasattr(gateway, 'projects'):
            gateway.projects.close()
        gateway.server_close()
        raise
    return gateway


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, default=Path.home() / '.latex-codex' / 'projects.json')
    parser.add_argument('--project', action='append', default=[], help='Add a local document; repeat for more projects')
    parser.add_argument('--host', default='127.0.0.1', help='IPv4 address or auto to detect a private LAN address')
    parser.add_argument('--port', default='auto', help='auto prefers the application port, then an unused port; explicit ports stay fixed')
    parser.add_argument('--public-url', action='append', default=[])
    parser.add_argument('--owner-name', default='Owner')
    parser.add_argument('--legacy-project', default='', help='Keep old unprefixed invitations/APIs for this project ID')
    args = parser.parse_args()
    try:
        projects = json.loads(args.registry.read_text(encoding='utf-8'))['projects'] if args.registry.exists() else []
        projects += [{'file': file} for file in args.project]
        server = make_gateway(projects, host=args.host, port=args.port, public_urls=args.public_url,
            owner_name=args.owner_name, registry_path=args.registry, legacy_project=args.legacy_project)
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as error:
        parser.exit(1, str(error) + '\n')
    base = f'http://{server.server_address[0]}:{server.server_port}'
    print(base + '/', flush=True)
    print('Private local administrator: ' + base + '/admin/join#admin=' + server.projects.admin_token, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.projects.close()
