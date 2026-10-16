#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/runtime/python:$PWD/src"
exec "${U15L_PYTHON:-python3}" -m u15l "$@"
