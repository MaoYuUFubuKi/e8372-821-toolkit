"""Install pinned USB dependencies locally; never opens a device or changes global Python."""
from pathlib import Path
import argparse,hashlib,os,platform,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
PACKAGES=('pyusb==1.3.1','libusb-package==1.0.30.0')
ADAPTER='# Standard-library adapter for libusb-package on Python 3.9+.\nfrom importlib.resources import files, as_file\n'

def build(root=ROOT,wheelhouse=None):
    tested=platform.system()=='Darwin' and platform.machine()=='arm64'
    if not tested:
        print('注意：本机为 %s / %s。此硬件流程仅在 macOS / Apple Silicon 验证；' % (platform.system(),platform.machine()),file=sys.stderr)
        print('其他平台可自行尝试，但不在作者验证范围内。',file=sys.stderr)
    if sys.version_info<(3,9):raise RuntimeError('需要 Python 3.9 或更新版本。')
    target=root/'runtime'
    if target.exists():raise RuntimeError('runtime 已存在；先运行 ./run.sh doctor，不覆盖现有环境。')
    (root/'local').mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='runtime-build-',dir=root/'local') as temporary:
        stage=Path(temporary);packages=stage/'python';licenses=stage/'licenses';licenses.mkdir()
        command=[sys.executable,'-m','pip','install','--disable-pip-version-check','--only-binary=:all:',
                 '--no-deps','--no-compile','--target',str(packages)]
        command+=['--no-index','--find-links',str(wheelhouse)] if wheelhouse else ['--index-url','https://pypi.org/simple']
        subprocess.run(command+list(PACKAGES),check=True)
        (packages/'importlib_resources.py').write_text(ADAPTER)
        for distribution in packages.glob('*.dist-info'):
            for p in distribution.rglob('*'):
                if p.is_file() and p.name.upper().startswith(('LICENSE','COPYING','NOTICE')):
                    dest=licenses/distribution.name/p.relative_to(distribution);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        if not any(licenses.rglob('LICENSE*')):raise RuntimeError('依赖许可证未找到。')
        (licenses/'libusb-origin.md').write_text('libusb 1.0.30 is LGPL-2.1-or-later. Upstream source and licensing: https://github.com/libusb/libusb/releases/tag/v1.0.30 . This directory is generated for private device recovery; it is not included in the source release.\n')
        # Load the backend in a child interpreter without enumerating/opening USB.
        env=dict(os.environ,PYTHONPATH=str(packages),PYTHONDONTWRITEBYTECODE='1')
        subprocess.run([sys.executable,'-c','import libusb_package; assert libusb_package.get_libusb1_backend() is not None'],env=env,check=True)
        entries=[]
        for p in sorted(stage.rglob('*')):
            if p.is_file():entries.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(stage).as_posix())
        (stage/'SHA256SUMS').write_text('\n'.join(entries)+'\n')
        stage.rename(target)
    print('依赖已安装到项目 runtime/，未访问设备。下一步：./run.sh doctor')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheelhouse',type=Path,help='Use an existing local wheel cache instead of downloading')
    args=parser.parse_args()
    try:build(wheelhouse=args.wheelhouse)
    except Exception as error:print('停止：'+str(error),file=sys.stderr);sys.exit(1)
