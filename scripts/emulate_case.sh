#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
case "$1" in ''|*[!a-zA-Z0-9_-]*) echo 'Invalid case name'; exit 1;; esac
case_dir="$PWD/local/$1/prepared"
test -f "$case_dir/manifest.json"
test -d local/emulation-x86/unicorn || { echo '先运行 scripts/setup_analysis.sh'; exit 1; }
# The actually tested workaround on the original Apple Silicon host.
PYTHONPATH="$PWD/local/emulation-x86:$case_dir/work/device" /usr/bin/arch -x86_64 /usr/bin/python3 "$case_dir/work/device/verify_u15l_patch_emulated.py"
