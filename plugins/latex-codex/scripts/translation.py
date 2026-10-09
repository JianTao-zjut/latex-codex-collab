"""Incremental, project-private reading translation; original files stay untouched."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
import uuid

from chat import ChatJob
from project_files import ProjectFiles


def blocks_for(source, file, markdown=True, offset=0):
    source = source.replace('\r\n', '\n')
    if markdown and source.startswith('---\n'):
        end = source.find('\n---', 4)
        if end >= 0:
            offset = end + 4
    if not markdown:
        start = re.search(r'\\begin\{document\}', source)
        if start:
            offset = start.end()
    fenced, references = False, False
    # Blank-line paragraphs stay independent; a long paragraph uses fixed-size pieces.
    for match in re.finditer(r'[^\n](?:[^\n]|\n(?![ \t]*\n))*', source[offset:]):
        begin, end = offset + match.start(), offset + match.end()
        text = source[begin:end].strip()
        if not text:
            continue
        if re.match(r'#+\s+(?:References|Bibliography)\b', text, re.I):
            references = True
        code = fenced or text.startswith(('```', '~~~'))
        if text.count('```') % 2 or text.count('~~~') % 2:
            fenced = not fenced
        if not markdown:
            text = re.sub(r'(?m)(?<!\\)%.*$', '', text).strip()
            if text == r'\end{document}':
                continue
        for start in range(0, len(text), 2000):
            part = text[start:start + 2000]
            readable = re.sub(r'\\(?:cite\w*|label|ref|eqref|bibliography|bibliographystyle)\*?(?:\[[^\]]*\])?\{[^}]*\}', '', part)
            readable = re.sub(r'\\(?:begin|end)\{[^}]*\}|\\[a-zA-Z]+\*?', '', readable)
            readable = re.sub(r'\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\$[^$]*\$|\\\([\s\S]*?\\\)', '', readable)
            needs = not code and not references and bool(re.search(r'[A-Za-z]{3,}', readable))
            key = hashlib.sha256(('zh-CN-v1\0' + ('md' if markdown else 'tex') + '\0' + part).encode()).hexdigest()
            yield {'key': key, 'file': file, 'from': begin + start, 'to': min(end, begin + start + len(part)),
                   'line': source.count('\n', 0, begin + start) + 1, 'source': part, 'translate': needs}


def collect_blocks(root, main):
    root, main = Path(root), Path(main)
    files = ProjectFiles(root, main)
    result, stack, size = [], set(), 0

    def visit(path):
        nonlocal size
        relative = path.relative_to(root).as_posix()
        path = files.path(relative, file_only=True)
        if path in stack or len(stack) >= 32:
            raise ValueError('翻译不支持循环引用或超过 32 层的引用。')
        stack.add(path)
        try:
            source = path.read_bytes().decode('utf-8').replace('\r\n', '\n')
            size += len(source)
            if size > 1_000_000:
                raise ValueError('翻译项目最多 1,000,000 字符。')
            markdown = path.suffix.lower() in ('.md', '.markdown')
            for block in blocks_for(source, relative, markdown):
                # Follow static TeX input/include references in document order, within the project.
                refs = [] if markdown else list(re.finditer(r'\\(?:input|include)\{([^{}]+)\}', block['source']))
                if refs:
                    position = 0
                    for match in refs:
                        prefix = block['source'][position:match.start()].strip()
                        if prefix:
                            result.extend(blocks_for(prefix, relative, False))
                        name = match[1] if Path(match[1]).suffix else match[1] + '.tex'
                        candidate = main.parent / name
                        visit(files.path(candidate.relative_to(root).as_posix(), file_only=True))
                        position = match.end()
                    suffix = block['source'][position:].strip()
                    if suffix:
                        result.extend(blocks_for(suffix, relative, False))
                else:
                    result.append(block)
                if len(result) > 2000:
                    raise ValueError('翻译项目最多 2,000 个段落。')
        finally:
            stack.remove(path)
    visit(main)
    return result


class Translation:
    def __init__(self, root, main, allowed, job_factory=ChatJob):
        self.root, self.main = Path(root), Path(main)
        self.allowed, self.job_factory = allowed, job_factory
        self.folder = self.root / '.latex-codex' / 'translations'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.database = self.folder / 'cache.sqlite3'
        self.output = self.folder / (self.main.stem + '.zh-CN.md')
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,text TEXT NOT NULL)')
        self.lock = threading.RLock()
        self.blocks, self.texts = [], {}
        self.enabled, self.actor, self.job, self.timer = False, None, None, None
        self.generation, self.revision, self.signature = 0, uuid.uuid4().hex, ''
        self.status, self.error = 'off', ''

    def connect(self):
        return sqlite3.connect(self.database, timeout=10)

    def touch(self):
        self.revision = uuid.uuid4().hex

    def catalog(self):
        blocks = collect_blocks(self.root, self.main)
        signature = hashlib.sha256(json.dumps(blocks, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if signature == self.signature:
            return False
        self.signature, self.blocks = signature, blocks
        with closing(self.connect()) as db:
            self.texts = {block['key']: row[0] for block in blocks
                          if (row := db.execute('SELECT text FROM cache WHERE key=?', (block['key'],)).fetchone())}
        for block in blocks:
            if not block['translate']:
                self.texts[block['key']] = block['source']
        self.touch()
        self.export()
        return True

    def export(self):
        content = '# 中文阅读译文\n\n> 自动生成，仅供对照阅读；待翻译部分保留原文。\n\n'
        content += '\n\n'.join(self.texts.get(block['key'], '> 待翻译\n\n' + block['source']) for block in self.blocks) + '\n'
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.folder, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        try:
            temporary.replace(self.output)
        finally:
            temporary.unlink(missing_ok=True)

    def enable(self, actor):
        if not self.allowed(actor):
            raise PermissionError('新翻译需要项目所有者授予 Codex 使用权限。')
        with self.lock:
            if self.enabled and self.actor != actor and self.status in ('queued', 'running'):
                return
            self.enabled, self.actor = True, actor
            self.refresh(actor, force=True)

    def refresh(self, actor, force=False):
        if not self.allowed(actor):
            return
        with self.lock:
            if not self.enabled:
                return
            changed = self.catalog()
            if not changed and not force:
                return
            self.generation += 1
            if self.timer:
                self.timer.cancel()
            if self.job:
                self.job.cancel()
            self.actor = actor
            self.status, self.error = 'queued', ''
            self.touch()
            self.timer = threading.Timer(2, self.run, (self.generation, actor))
            self.timer.daemon = True
            self.timer.start()

    def cancel(self, actor=None):
        with self.lock:
            if actor is not None and actor != self.actor:
                return
            self.enabled = False
            self.generation += 1
            if self.timer:
                self.timer.cancel()
            if self.job:
                self.job.cancel()
            self.status = 'off'
            self.touch()

    def run(self, generation, actor):
        try:
            while True:
                with self.lock:
                    if generation != self.generation or not self.enabled:
                        return
                    if not self.allowed(actor):
                        self.cancel(actor)
                        return
                    missing = list({block['key']: block for block in self.blocks if block['key'] not in self.texts}.values())
                    if not missing:
                        self.status = 'ready'
                        self.export()
                        self.touch()
                        return
                    batch, size = [], 0
                    for block in missing:
                        if len(batch) >= 12 or size + len(block['source']) > 12000:
                            break
                        batch.append({'id': block['key'], 'source': block['source']})
                        size += len(block['source'])
                    self.status = 'running'
                    self.touch()
                    job = self.job_factory({'task': 'translation', 'items': batch, 'effort': 'low'}).start()
                    self.job = job
                while job.result['status'] == 'running':
                    time.sleep(.2)
                    if not self.allowed(actor):
                        self.cancel(actor)
                    with self.lock:
                        if generation != self.generation:
                            job.cancel()
                            return
                with self.lock:
                    if generation != self.generation or not self.allowed(actor):
                        return
                    if job.result['status'] != 'done':
                        raise ValueError(job.result.get('error', '翻译已停止，可重新开启重试。'))
                    translated = job.result.get('translations')
                    expected = {item['id'] for item in batch}
                    if (not isinstance(translated, list) or len(translated) != len(expected)
                            or any(not isinstance(item, dict) or item.get('id') not in expected
                                   or not isinstance(item.get('text'), str) or not 1 <= len(item['text']) <= 16000 for item in translated)
                            or len({item['id'] for item in translated}) != len(expected)):
                        raise ValueError('翻译结果不完整，保留已有译文；请重试。')
                    with closing(self.connect()) as db, db:
                        for item in translated:
                            db.execute('INSERT OR REPLACE INTO cache VALUES (?,?)', (item['id'], item['text']))
                            self.texts[item['id']] = item['text']
                    self.export()
                    self.touch()
        except (OSError, ValueError, sqlite3.Error) as error:
            with self.lock:
                if generation == self.generation:
                    self.status, self.error = 'error', str(error)
                    self.touch()

    def state(self, revision=''):
        with self.lock:
            common = {'revision': self.revision, 'status': self.status, 'error': self.error,
                      'pending': sum(block['key'] not in self.texts for block in self.blocks), 'total': len(self.blocks)}
            if revision == self.revision:
                return {**common, 'unchanged': True}
            if not self.blocks:
                self.catalog()  # Reading cached translations never starts a Codex job.
                common['revision'], common['total'] = self.revision, len(self.blocks)
                common['pending'] = sum(block['key'] not in self.texts for block in self.blocks)
            return {**common, 'blocks': [{**block, 'text': self.texts.get(block['key'])} for block in self.blocks]}
