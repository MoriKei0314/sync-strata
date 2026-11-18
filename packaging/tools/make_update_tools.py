#!/usr/bin/env python3
"""11/17 H（strata-engine2-desktop）: pack/src/update/update_core.py（更新の中身．Python）を包んで，1 本で流せる
update.cmd（Windows）と update.sh（Linux）を作る．中身を直したらこれを流す（包みは手で直さない）．

  py -3 -X utf8 make_update_tools.py [--check]     --check: 今の update.cmd・update.sh が中身と合っているかだけ見る（違えば 1）

包みの形: 前半は cmd・sh の数行（入れた先の Python を探し，自分のファイルの「#PY-BEGIN」の行より後を Python で流す），
後半が update_core.py そのもの．update.cmd は 1 つの括弧の中で全部を読んでから流す（更新が自分を書き換えても乱れない）．
update.sh は自分を一時の置き場に写してから流す．どちらも入れた先（app/pack/）とリリースの置き場に同じ物を置く．
流れは 3 つ: Python の prepare（一覧・新しい配布の道具・止める・run.ps1／run.sh を書く）→ 包みが run を流す（配布の道具が
入れ替える．このあいだ app/ の Python は動いていない．配布の道具は app/ の下で動いている物を「アプリが動いている」と数えるため．
11/17 の試しで見つけた）→ Python の report（版を出す・後片付け）．
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UPD = os.path.join(os.path.dirname(HERE), 'src', 'update')
MARK = '#PY' + '-BEGIN'

CMD_HEAD = r'''@echo off
rem Sync-Strata: update (only the changed parts; the previous version is kept for rollback.cmd).
rem Made by pack\tools\make_update_tools.py from pack\src\update\update_core.py: edit that file, not this one.
rem Usage: update.cmd [-Source <release zip | unpacked folder | URL>] [-AppDir DIR] [-SyncHome DIR] [-NoStop]
rem Everything runs in one block: cmd has read it all before the update replaces this file.
setlocal EnableDelayedExpansion
(
  set "SSU_TMP=%TEMP%\SyncStrata-update-%RANDOM%%RANDOM%"
  mkdir "!SSU_TMP!" >nul 2>nul
  copy /y "%~f0" "!SSU_TMP!\update.cmd" >nul
  set "SSU_SELF=!SSU_TMP!\update.cmd"
  set "SSU_PY="
  if exist "%~dp0app\python\python.exe" set "SSU_PY=%~dp0app\python\python.exe"
  if not defined SSU_PY if defined SYNC_APP_DIR if exist "%SYNC_APP_DIR%\app\python\python.exe" set "SSU_PY=%SYNC_APP_DIR%\app\python\python.exe"
  if not defined SSU_PY if exist "%LOCALAPPDATA%\Programs\SyncStrata\app\python\python.exe" set "SSU_PY=%LOCALAPPDATA%\Programs\SyncStrata\app\python\python.exe"
  if not defined SSU_PY (
    echo Sync-Strata update: the app's Python was not found. Is Sync-Strata installed? Run setup.cmd from the download first.
    set "SSU_RC=2"
  ) else (
    rem Step 1 prepare by Python: manifest, the new installer, stop the app, write run.ps1.  Step 2 run.ps1 replaces the parts
    rem while no Python runs from the app: the installer counts any exe under app\ as the app running.  Step 3 report by Python.
    "!SSU_PY!" -s -X utf8 -c "import os; t = open(os.environ['SSU_SELF'], encoding='utf-8').read(); exec(compile(t[t.index(chr(10) + '#PY' + '-BEGIN') + 1:], os.environ['SSU_SELF'], 'exec'))" prepare "%~dp0." %*
    set "SSU_RC=!ERRORLEVEL!"
    if exist "!SSU_TMP!\run.ps1" (
      powershell.exe -NoProfile -ExecutionPolicy Bypass -File "!SSU_TMP!\run.ps1"
      set "SSU_RC=!ERRORLEVEL!"
      "!SSU_PY!" -s -X utf8 -c "import os; t = open(os.environ['SSU_SELF'], encoding='utf-8').read(); exec(compile(t[t.index(chr(10) + '#PY' + '-BEGIN') + 1:], os.environ['SSU_SELF'], 'exec'))" report "%~dp0." !SSU_RC! %*
      set "SSU_RC=!ERRORLEVEL!"
    )
  )
  cd /d "%TEMP%"
  rmdir /s /q "!SSU_TMP!" >nul 2>nul
  if not "%SS_NOPAUSE%"=="1" pause
  exit /b !SSU_RC!
)
'''

SH_HEAD = r'''#!/bin/sh
# Sync-Strata: update (only the changed parts; the previous version is kept for rollback.sh).
# Made by pack/tools/make_update_tools.py from pack/src/update/update_core.py: edit that file, not this one.
# Usage: sh update.sh [--source <release zip | unpacked folder | URL>] [--app-dir DIR] [--sync-home DIR] [--no-stop] [--pause]
# First run: copy this file to a temporary folder and run the copy (the update may replace this file).
if [ -z "${SSU_TMP:-}" ]; then
  SSU_TMP=$(mktemp -d "${TMPDIR:-/tmp}/syncstrata-update.XXXXXX") || exit 1
  if ! cp "$0" "$SSU_TMP/update.sh"; then rm -rf "$SSU_TMP"; exit 1; fi
  SSU_HERE=$(cd "$(dirname "$0")" && pwd)
  export SSU_TMP SSU_HERE
  exec sh "$SSU_TMP/update.sh" "$@"
fi
D=$SSU_HERE
PY=
for p in "$D/app/python/bin/python3" "${SYNC_APP_DIR:+$SYNC_APP_DIR/app/python/bin/python3}" \
         "${XDG_DATA_HOME:-$HOME/.local/share}/SyncStrata/app/python/bin/python3" "$(command -v python3 2>/dev/null)"; do
  if [ -n "$p" ] && [ -x "$p" ]; then PY=$p; break; fi
done
if [ -z "$PY" ]; then echo "Sync-Strata update: Python 3 was not found (the app's own Python or python3)."; rm -rf "$SSU_TMP"; exit 2; fi
core() { SSU_SELF="$SSU_TMP/update.sh" "$PY" -s -X utf8 -c 'import os; t = open(os.environ["SSU_SELF"], encoding="utf-8").read(); exec(compile(t[t.index(chr(10) + "#PY" + "-BEGIN") + 1:], os.environ["SSU_SELF"], "exec"))' "$@"; }
# 1) prepare (Python): manifest, the new setup.sh, stop the app, write run.sh.  2) run.sh replaces the parts with no Python
# running from the app (setup.sh counts any program under app/ as "the app is running").  3) report (Python).
core prepare "$D" "$@"; RC=$?
if [ -f "$SSU_TMP/run.sh" ]; then
  sh "$SSU_TMP/run.sh"; RC=$?
  core report "$D" "$RC" "$@"; RC=$?
fi
rm -rf "$SSU_TMP"
exit $RC
'''


def build():
    core = open(os.path.join(UPD, 'update_core.py'), encoding='utf-8').read().replace('\r\n', '\n')
    if MARK in core:
        raise SystemExit('update_core.py に印の文字列がある（包みの区切りと紛れる）')
    cmd = (CMD_HEAD + MARK + '\n' + core).replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')
    sh = (SH_HEAD + MARK + '\n' + core).encode('utf-8')
    head_ascii = all(ord(ch) < 128 for ch in CMD_HEAD + SH_HEAD)
    if not head_ascii:
        raise SystemExit('包みの前半は ASCII だけにする（cmd が読む所）')
    return {'update.cmd': cmd, 'update.sh': sh}


def main():
    out = build()
    bad = 0
    for n, data in out.items():
        p = os.path.join(UPD, n)
        same = os.path.exists(p) and open(p, 'rb').read() == data
        if '--check' in sys.argv:
            print(f'{n}: {"合っている" if same else "中身と違う（make_update_tools.py を流す）"}')
            bad += not same
            continue
        if not same:
            with open(p, 'wb') as f:
                f.write(data)
        print(f'{n}: {"書いた" if not same else "同じ"}（{len(data):,} バイト）')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
