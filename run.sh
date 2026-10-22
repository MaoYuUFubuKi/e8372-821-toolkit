#!/bin/sh
set -eu
cd "$(dirname "$0")"
# Windows Store 的 python3 别名不可用：优先 U15L_PYTHON，其次 python3，再退回 python。
if [ -z "${U15L_PYTHON:-}" ]; then
    if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys' 2>/dev/null; then
        U15L_PYTHON=python3
    else
        U15L_PYTHON=python
    fi
    export U15L_PYTHON
fi
if [ ! -d "$PWD/runtime/python" ]; then
    echo "缺少运行依赖。请先执行：python scripts/setup_runtime.py" >&2
    exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/runtime/python:$PWD/src"
exec "${U15L_PYTHON}" -m u15l "$@"
