"""Project-bounded file operations; hidden data and symlinks are never exposed."""
import base64
import binascii
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile
import io

EDITABLE_EXTENSIONS = ('.tex', '.md', '.markdown', '.bib', '.sty', '.cls', '.txt', '.csv', '.json')
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_PROJECT_BYTES = 128 * 1024 * 1024


class ProjectFiles:
    def __init__(self, root, main_file):
        self.root = Path(root).resolve(strict=True)
        self.main_file = Path(main_file).resolve(strict=True)

    def path(self, name, *, existing=True, file_only=False):
        if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
            raise ValueError('请选择项目内的相对路径。')
        relative = PurePosixPath(name)
        if relative.is_absolute() or name != relative.as_posix() or any(
                part in ('', '.', '..') or part.startswith('.') or ':' in part
                or part.endswith((' ', '.')) or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part)
                for part in relative.parts):
            raise ValueError('不允许隐藏目录、系统名称或项目外路径。')
        cursor = self.root
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink() or cursor.resolve() != cursor.absolute():
                raise ValueError('文件管理不访问符号链接或目录联接。')
        target = cursor.resolve()
        if not target.is_relative_to(self.root) or target == self.root:
            raise ValueError('路径必须位于当前项目内。')
        if existing and not target.exists():
            raise FileNotFoundError('项目文件不存在。')
        if file_only and target.exists() and not target.is_file():
            raise ValueError('请选择文件。')
        return target

    @staticmethod
    def version(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def tree(self):
        entries, total = [], 0
        for folder, directories, files in os.walk(self.root, followlinks=False):
            directories[:] = sorted(name for name in directories if not name.startswith('.')
                                     and name not in ('node_modules', '__pycache__')
                                     and not (Path(folder) / name).is_symlink()
                                     and (Path(folder) / name).resolve() == (Path(folder) / name).absolute())
            for name in directories:
                path = Path(folder) / name
                entries.append({'path': path.relative_to(self.root).as_posix(), 'directory': True})
            for name in sorted(files):
                if name.startswith('.'):
                    continue
                path = Path(folder) / name
                if path.is_symlink():
                    continue
                size = path.stat().st_size
                total += size
                entries.append({'path': path.relative_to(self.root).as_posix(), 'directory': False,
                                'size': size, 'editable': path.suffix.lower() in EDITABLE_EXTENSIONS,
                                'main': path.resolve() == self.main_file})
            if len(entries) > 5000:
                raise ValueError('项目文件过多，请选择更具体的项目目录。')
        return {'files': sorted(entries, key=lambda item: item['path']), 'total_bytes': total,
                'main_file': self.main_file.relative_to(self.root).as_posix()}

    def upload(self, name, encoded, expected=None):
        path = self.path(name, existing=False, file_only=True)
        if not isinstance(encoded, str) or len(encoded) > MAX_FILE_BYTES * 4 // 3 + 4:
            raise ValueError('每个上传文件最多 16 MiB。')
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('上传文件数据无效。') from None
        if len(content) > MAX_FILE_BYTES:
            raise ValueError('每个上传文件最多 16 MiB。')
        if path.suffix.lower() in EDITABLE_EXTENSIONS:
            try:
                content.decode('utf-8-sig')
            except UnicodeError:
                raise ValueError('可编辑的文本文件必须使用 UTF-8 编码。') from None
        if path.exists():
            if expected is None or self.version(path) != expected:
                raise ValueError('同名文件已存在或发生修改；请刷新后明确选择替换。')
        elif expected is not None:
            raise ValueError('原文件已被移走，请刷新后重试。')
        if self.tree()['total_bytes'] - (path.stat().st_size if path.exists() else 0) + len(content) > MAX_PROJECT_BYTES:
            raise ValueError('文件管理上传上限为每项目 128 MiB。')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                output.write(content)
            if path.exists() and (expected is None or self.version(path) != expected):
                raise ValueError('保存期间原文件发生修改，未覆盖。')
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {'path': name, 'version': self.version(path)}

    def mkdir(self, name):
        path = self.path(name, existing=False)
        path.mkdir(parents=True, exist_ok=False)

    def rename(self, name, new_name, expected, protected=()):
        path = self.path(name, file_only=True)
        target = self.path(new_name, existing=False, file_only=True)
        if path == self.main_file or path in protected:
            raise ValueError('主编译文件或正在编辑的文件不能重命名，请先切换其他文件。')
        if target.exists() or expected != self.version(path):
            raise ValueError('文件已变化或目标已存在，请刷新后重试。')
        target.parent.mkdir(parents=True, exist_ok=True)
        path.rename(target)

    def trash(self, name, expected, protected=()):
        path = self.path(name)
        if path == self.main_file or path in protected:
            raise ValueError('主编译文件或正在编辑的文件不能删除，请先切换其他文件。')
        if path.is_dir():
            path.rmdir()  # Only empty folders: never recursively remove unknown files.
            return
        if expected != self.version(path):
            raise ValueError('文件已变化，请刷新后重试。')
        folder = self.root / '.latex-codex' / 'trash'
        folder.mkdir(parents=True, exist_ok=True)
        import secrets
        path.rename(folder / (secrets.token_hex(12) + '-' + path.name))

    def download(self, name):
        path = self.path(name, file_only=True)
        if path.stat().st_size > MAX_PROJECT_BYTES:
            raise ValueError('文件过大，无法通过浏览器下载。')
        return path.read_bytes(), path.name

    def archive(self):
        entries = self.tree()['files']
        if sum(item.get('size', 0) for item in entries) > MAX_PROJECT_BYTES:
            raise ValueError('项目超过 128 MiB，请分别下载文件。')
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for item in entries:
                if not item['directory']:
                    archive.write(self.path(item['path'], file_only=True), item['path'])
        return output.getvalue(), self.root.name + '.zip'
