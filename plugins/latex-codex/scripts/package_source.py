"""Build a source-only release; no documents, runtime data or demo media."""
import argparse
from pathlib import Path
import zipfile

PRIVATE_DIRS = {'.git', '.latex-codex', 'node_modules', '__pycache__', 'experiments', 'share'}
PRIVATE_NAMES = {'auth.json', 'projects.json', 'autodl.txt'}
PRIVATE_SUFFIXES = {'.tex', '.pdf', '.sqlite3', '.db', '.zip', '.log', '.pem', '.key', '.mp4', '.webm'}
ROOT_FILES = ('README.md', 'README.zh-CN.md', 'AGENTS.md', 'CHANGELOG.md', '.gitignore', '.agents/plugins/marketplace.json',
              'docs/FEATURES.md', 'docs/FEATURES.zh-CN.md', 'docs/INSTALL.md', 'docs/INSTALL.zh-CN.md')


def release_files(root):
    root = Path(root).resolve(strict=True)
    sources = [root / item for item in ROOT_FILES]
    sources.extend((root / 'plugins' / 'latex-codex').rglob('*'))
    for path in sorted(set(sources)):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in PRIVATE_DIRS for part in relative.parts) or path.name.lower() in PRIVATE_NAMES:
            continue
        if path.name.startswith('.env') or path.suffix.lower() in PRIVATE_SUFFIXES or '.sqlite3-' in path.name:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root) or path.resolve() != path.absolute():
            raise ValueError('Release source must not contain symlinks or junctions.')
        yield path, relative.as_posix()


def package(root, output):
    files = list(release_files(root))
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, name in files:
            archive.write(path, name)
    return len(files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    count = package(Path(__file__).resolve().parents[3], args.output)
    print(f'Packaged {count} source files: {args.output}')
