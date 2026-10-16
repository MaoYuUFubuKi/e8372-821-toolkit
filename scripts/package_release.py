"""Package source code, documentation and photos only."""
from pathlib import Path
import argparse,hashlib,json,re,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES={'.gitignore','README.md','AGENTS.md','CLAUDE.md','LICENSE','run.sh'}
SOURCE_DIRS={'src','scripts','tests','docs','assets','.github'}
EXCLUDED={'local','runtime','firmware','.git','__pycache__','dist'}
SUFFIXES={'.py','.sh','.md','.json','.yml','.yaml','.jpg','.jpeg','.png','.webp'}

def source_paths():
    for p in sorted(ROOT.rglob('*')):
        rel=p.relative_to(ROOT)
        if any(part in EXCLUDED or part.startswith('.venv') for part in rel.parts):continue
        if p.name=='.DS_Store' or p.suffix in {'.pyc','.pyo'}:continue
        if rel.parts[0] not in SOURCE_DIRS and rel.as_posix() not in ROOT_FILES:continue
        if p.is_symlink():raise RuntimeError('Source symlink is not allowed: '+str(rel))
        if not p.is_file():continue
        if rel.as_posix() not in ROOT_FILES and p.suffix not in SUFFIXES:
            raise RuntimeError('Unexpected source file: '+str(rel))
        # JSON is restricted to the two public summaries, not arbitrary logs.
        if p.suffix=='.json' and rel.as_posix() not in {'docs/validation.json','assets/photos/manifest.json'}:
            raise RuntimeError('Unexpected JSON in source: '+str(rel))
        yield p,rel.as_posix()

def check_source(files):
    for p,rel in files:
        if p.suffix in {'.py','.sh','.md','.json','.yml','.yaml'}:
            if re.search(r'/(?:Users|home)/[A-Za-z0-9_.-]+/',p.read_text()):
                raise RuntimeError('Local home path found: '+rel)
    photos=json.loads((ROOT/'assets/photos/manifest.json').read_text())
    for item in photos:
        photo=ROOT/'assets/photos'/item['file']
        if hashlib.sha256(photo.read_bytes()).hexdigest()!=item['sha256']:
            raise RuntimeError('Photo manifest needs updating: '+item['file'])
    pending=[item['file'] for item in photos if not item.get('redacted')]
    if pending:print('Photos await author masking:',len(pending))
    print('Source files:',len(files))

def archive(path,entries,prefix=''):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for p,name in entries:z.write(p,prefix+name)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix('.zip.sha256').write_text(digest+'  '+path.name+'\n')
    print(path.name)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--output-dir',type=Path,default=ROOT.parent)
    args=parser.parse_args();files=list(source_paths());check_source(files)
    if args.check_only:return
    args.output_dir.mkdir(parents=True,exist_ok=True)
    archive(args.output_dir/'u15l-asr1803-toolkit-source-only.zip',files,'u15l-asr1803-toolkit/')

if __name__=='__main__':main()
