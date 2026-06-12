#!/usr/bin/env bash
set -u
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
elif command -v py >/dev/null 2>&1; then PY="py -3"
else
  PY=""
  shopt -s nullglob 2>/dev/null || true
  for cand in /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    [ -x "$cand" ] && { PY="$cand"; break; }
  done
  shopt -u nullglob 2>/dev/null || true
  [ -n "$PY" ] || exit 0
fi
exec $PY "$@"
