"""Package a Windows distribution of the toolkit for modifying another E8372-821.

The archive contains the source tree, the already-verified Windows runtime
(pyusb + libusb DLL + integrity manifest) and a Windows setup guide. It does
NOT contain local/ device backups, firmware components or any prepared
candidate images: each target machine must run backup -> prepare --method
local on its own matched device. Only files that already exist in this repo
are packed; nothing is downloaded here.
"""
from pathlib import Path
import argparse, hashlib, re, zipfile

ROOT = Path(__file__).resolve().parents[1]

ROOT_FILES = {'.gitignore', 'README.md', 'AGENTS.md', 'CLAUDE.md', 'LICENSE', 'run.sh'}
SOURCE_DIRS = {'src', 'scripts', 'tests', 'docs', 'assets', '.github'}
EXCLUDED = {'local', 'runtime', 'firmware', '.git', '__pycache__', 'dist'}
SUFFIXES = {'.py', '.sh', '.bat', '.cmd', '.md', '.json', '.yml', '.yaml',
            '.jpg', '.jpeg', '.png', '.webp', '.txt'}
# The verified runtime is packed as-is with its own SHA256SUMS; it is excluded
# from the generic source walk and added explicitly below.
RUNTIME = ROOT / 'runtime'


def source_paths():
    for p in sorted(ROOT.rglob('*')):
        rel = p.relative_to(ROOT)
        if any(part in EXCLUDED or part.startswith('.venv') for part in rel.parts):
            continue
        if p.name in {'.DS_Store'} or p.suffix in {'.pyc', '.pyo'}:
            continue
        if rel.parts[0] not in SOURCE_DIRS and rel.as_posix() not in ROOT_FILES:
            continue
        if p.is_symlink():
            raise RuntimeError('Source symlink is not allowed: ' + str(rel))
        if not p.is_file():
            continue
        if rel.as_posix() not in ROOT_FILES and p.suffix not in SUFFIXES:
            raise RuntimeError('Unexpected source file: ' + str(rel))
        if p.suffix == '.json' and rel.as_posix() not in {'docs/validation.json', 'assets/photos/manifest.json'}:
            raise RuntimeError('Unexpected JSON in source: ' + str(rel))
        yield p, rel.as_posix()


def check_source(files):
    for p, rel in files:
        if p.suffix in {'.py', '.sh', '.bat', '.cmd', '.md', '.json', '.yml', '.yaml'}:
            if re.search(r'/(?:Users|home)/[A-Za-z0-9_.-]+/', p.read_text(errors='replace')):
                raise RuntimeError('Local home path found: ' + rel)
    print('Source files:', len(files))


def runtime_paths():
    """Pack the verified runtime directory verbatim, including SHA256SUMS."""
    manifest = RUNTIME / 'SHA256SUMS'
    if not manifest.is_file():
        raise RuntimeError('runtime/SHA256SUMS missing; run scripts/setup_runtime.py first.')
    # Verify every runtime file before packing so the target machine's
    # verify_runtime() cannot fail on a corrupted copy.
    for line in manifest.read_text().splitlines():
        digest, name = line.split('  ', 1)
        p = (RUNTIME / name).resolve()
        if RUNTIME.resolve() not in p.parents or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Runtime integrity mismatch: ' + name)
    count = 0
    for p in sorted(RUNTIME.rglob('*')):
        if p.is_file():
            yield p, p.relative_to(ROOT).as_posix()
            count += 1
    print('Runtime files:', count)


def archive(path, entries):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for p, name in entries:
            z.write(p, 'u15l-asr1803-toolkit/' + name)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    Path(str(path) + '.sha256').write_text(digest + '  ' + path.name + '\n')
    print('Archive:', path.name, path.stat().st_size, 'bytes')
    print('SHA-256:', digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=ROOT.parent)
    args = parser.parse_args()
    files = list(source_paths())
    check_source(files)
    runtime = list(runtime_paths())
    if args.check_only:
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    archive(args.output_dir / 'u15l-asr1803-toolkit-windows.zip', files + runtime)


if __name__ == '__main__':
    main()
