"""Project paths and private per-device workspaces; never embed a donor image."""
from pathlib import Path
import datetime, hashlib, json, os, re, sys
from .profiles import L01
ROOT=Path(__file__).resolve().parents[2]
ENGINE=Path(__file__).resolve().parent/'device'
RUNTIME=ROOT/'runtime'
sys.path[:0]=[str(RUNTIME/'python'),str(ENGINE)]
# Compatibility aliases for callers of the original L01-only public API.
PROFILE=L01.id
BOARD=L01.board
SOC=L01.soc
FIRMWARE=L01.firmware
SOURCE_PLAIN_SHA=L01.plain_sha256
OBM_SHA='34a56247fa26e5c359930e43fef76ce30f5b95d2ce8ddd3f3fafcdab87f2e9f4'
PREFIX_SHA='a03e30e27c254666ea35881a25096723c38f3087eb8b40d230d6ea892f93b78f'
START,END=0x480000,0x5c0000

def sha(data):return hashlib.sha256(data).hexdigest()
def now():return datetime.datetime.now().astimezone().isoformat()
def case_path(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',name):
        raise ValueError('设备目录名只允许字母、数字、下划线和短横线，最多 64 字符。')
    return ROOT/'local'/name

def save_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w') as f:
        os.chmod(path,0o600);json.dump(data,f,ensure_ascii=False,indent=2)
        f.write('\n');f.flush();os.fsync(f.fileno())

class Recorder:
    def __init__(self,path):self.path=path;self.state={'started':now(),'events':[]}
    def log(self,kind='event',**values):
        self.state['events'].append({'kind':kind,**values});save_json(self.path,self.state)


def verify_runtime():
    manifest=RUNTIME/'SHA256SUMS'
    if not manifest.is_file():
        raise RuntimeError('缺少运行依赖。请先运行 python3 scripts/setup_runtime.py。')
    for line in manifest.read_text().splitlines():
        digest,name=line.split('  ',1);p=(RUNTIME/name).resolve()
        if RUNTIME.resolve() not in p.parents or sha(p.read_bytes())!=digest:
            raise RuntimeError('运行依赖校验失败：'+name)
