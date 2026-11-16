#!/bin/sh
# Sync-Strata setup (Linux): checks what is already installed and installs only what is missing, old or broken.
# The same one for the first install, a repair and a friend's PC. No root (sudo) needed. Safe to run again.
# Options are passed on (for example: ./setup.sh --app-dir ~/apps/SyncStrata  or  ./setup.sh --models-dir /data/models).
D="$(cd "$(dirname "$0")" && pwd)"
PY=""
if command -v python3 >/dev/null 2>&1 && python3 -c "import sys, zipfile, json; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
  PY=python3
else
  # No usable python3 on this PC: unpack the bundled Python (the python component) into a temporary folder and use it.
  Z="$(ls "$D"/feed/components/python-*.zip 2>/dev/null | head -n 1)"
  T="$(mktemp -d)"
  if [ -n "$Z" ] && command -v unzip >/dev/null 2>&1; then unzip -q "$Z" -d "$T"
  elif [ -n "$Z" ] && command -v bsdtar >/dev/null 2>&1; then bsdtar -xf "$Z" -C "$T"
  else echo "python3 (3.8 or later) or unzip is needed to run the setup. Install one (for example: sudo apt install python3) and run ./setup.sh again."; exit 1; fi
  chmod +x "$T"/bin/* 2>/dev/null
  PY="$T/bin/python3"
fi
"$PY" "$D/installer/installer.py" setup --source "$D/feed" "$@"
RC=$?
[ -n "$T" ] && rm -rf "$T"
exit $RC
