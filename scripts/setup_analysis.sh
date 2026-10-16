#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p local/analysis-wheels local/emulation-x86
python3 -m venv local/analysis-env
local/analysis-env/bin/python -m pip install 'capstone==5.0.6'
local/analysis-env/bin/python -m pip download --only-binary=:all: --no-deps --platform macosx_10_9_x86_64 --python-version 39 --implementation cp --abi abi3 'unicorn==2.1.4' -d local/analysis-wheels
python3 - <<'PY'
from pathlib import Path
import hashlib,zipfile
p=Path('local/analysis-wheels/unicorn-2.1.4-cp37-abi3-macosx_10_9_x86_64.whl')
expected='2a6f738fab5fabffa56af1e7bbf16ea1e91466c342f8dc64f125bd70f36c6b80'
if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise SystemExit('Unicorn wheel hash mismatch')
with zipfile.ZipFile(p) as z:z.extractall('local/emulation-x86')
print('离线分析环境已准备；尚未访问设备。Rosetta 和兼容的 x86 Python 需要由用户安装。')
PY
