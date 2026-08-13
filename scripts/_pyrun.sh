#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
set -u

PY=""

# Ưu tiên Python 3.11 thật trên máy Windows này
WIN_PY="/c/Users/Admin/AppData/Local/Programs/Python/Python311/python.exe"

if [ -x "$WIN_PY" ]; then
  PY="$WIN_PY"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  CANDIDATE="$(command -v python)"

  # Bỏ qua Microsoft Store execution alias
  if [[ "$CANDIDATE" != *"/Microsoft/WindowsApps/"* ]]; then
    PY="$CANDIDATE"
  fi
elif command -v py >/dev/null 2>&1; then
  exec py -3 "$@"
fi

# Nếu vẫn chưa tìm thấy, dò các vị trí Python phổ biến
if [ -z "$PY" ]; then
  shopt -s nullglob 2>/dev/null || true

  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python311/python.exe \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do

    if [ -x "$cand" ]; then
      PY="$cand"
      break
    fi
  done

  shopt -u nullglob 2>/dev/null || true
fi

if [ -z "$PY" ]; then
  echo "[ai-log] Python not found." >&2
  exit 0
fi

exec "$PY" "$@"