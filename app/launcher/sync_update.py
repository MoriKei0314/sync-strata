#!/usr/bin/env python3
"""更新を画面から（11/18 係 W9．本人「今回入れよう」．本家 Strata は設定の中に更新の欄がある）．標準ライブラリだけ．

  sync.py update check [--json] [--local] [--source 置き場] [--lang ja|en|zh]
        落とさず入れ替えず，いまの版・新しい版・変わる部品と大きさ・リリースの説明を調べる（画面の「更新を確かめる」．中継 GET /m/update）．
        --local はネットを見ずにいまの版だけ．中身は入れた先の update.cmd・update.sh の中の update_core.py の --check（JSON 1 行）．
  sync.py update apply [--json] [--lang ja|en|zh]
        「閉じて更新する」．更新の係をこのアプリから切り離して起こして，すぐ戻る（画面の返事はこの後に消える．中継 POST /m/update/apply）．
        切り離された係（Windows は PowerShell，Linux は sh．窓か端末に様子が出る．記録は SYNC_HOME\\logs\\update-<日時>.log）が:
          3 秒待つ（画面への返事を済ませる）→ sync down --all（「全て閉じる」と同じ）→ アプリの枠（Sync-Strata.exe・sync-strata）を閉じる →
          アプリの下の物が全部止まるのを待つ → update.cmd・update.sh を流す（変わった部品だけ入れ替え，前の版を 1 つ残す）→ アプリを起こし直す．
        成功なら窓は 8 秒で閉じる．失敗なら Enter を待つ（読んでから閉じる）．
        テスト用: --root <入れた先> で入れた先を指す．--no-close（閉じる手順を飛ばす）・--no-relaunch（起こし直さない）・--dry（起こさず内容だけ）．

出す物（--json．日本語の文は入れない．画面が文を作る）: update_core.py の check の dict（kind: local／feed／zip／unreachable／not_installed／bad_manifest／
old_tool／error）．apply は {ok, started, log, window, tool}．
触らない物: 設定・会話（SYNC_HOME），モデル，保存済みのトークン．
"""
import json, os, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import oscompat as OS  # noqa: E402
import sync_home as H  # noqa: E402

IS_WIN = os.name == "nt"
MARK = "\n#PY" + "-BEGIN"
SNIP = ("import os; t = open(os.environ['SSU_SELF'], encoding='utf-8').read(); "
        "exec(compile(t[t.index(chr(10) + '#PY' + '-BEGIN') + 1:], os.environ['SSU_SELF'], 'exec'))")


def _opt(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def install_root(argv):
    """入れた先（update.cmd・update.sh のある所．<入れた先>\\app\\launcher の 2 つ上）．入れた先の並びでなければ None（--root で指せる）"""
    r = _opt(argv, "--root") or os.environ.get("SYNC_APP_ROOT")
    if r:
        return os.path.abspath(r)
    return os.path.dirname(H.APP) if H._installed() else None


def tool_path(root):
    name = "update.cmd" if IS_WIN else "update.sh"
    for p in (os.path.join(root, name), os.path.join(root, "app", "pack", name)):
        if os.path.isfile(p):
            return p
    return None


def _lang(argv):
    v = _opt(argv, "--lang") or os.environ.get("SYNC_LANG") or ""
    return v[:2] if v[:2] in ("ja", "en", "zh") else ""


def run_check(argv):
    """update_core の --check を流して dict を返す（落ちずに kind で返す）"""
    root = install_root(argv)
    if not root:
        return {"ok": False, "kind": "not_installed", "platform": "windows-x64" if IS_WIN else "linux-x64"}
    tool = tool_path(root)
    if not tool:
        return {"ok": False, "kind": "not_installed", "app": root}
    args = [sys.executable, "-s", "-X", "utf8", "-c", SNIP, "prepare", root, "--check", "--app-dir", root, "--sync-home", H.home()]
    if "--local" in argv:
        args.append("--local")
    if _opt(argv, "--source"):
        args += ["--source", _opt(argv, "--source")]
    lg = _lang(argv)
    if lg:
        args += ["--lang", lg]
    env = dict(os.environ, SSU_SELF=tool, PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=75,
                           stdin=subprocess.DEVNULL, creationflags=0x08000000 if IS_WIN else 0)
    except subprocess.TimeoutExpired:
        return {"ok": False, "kind": "unreachable", "detail": "timed out", "tool": tool}
    except OSError as e:
        return {"ok": False, "kind": "error", "detail": str(e)[:300], "tool": tool}
    for line in reversed((r.stdout or "").strip().splitlines()):
        if line.startswith("{"):
            try:
                d = json.loads(line)
                d["tool"] = tool
                return d
            except ValueError:
                break
    # JSON が無い: 入れた先の更新の道具が古く，--check を知らない（「分からない引数」で終わる）
    return {"ok": False, "kind": "old_tool", "tool": tool, "detail": ((r.stderr or r.stdout).strip().splitlines() or [""])[-1][:300]}


# ---------------------------------------------------------------- 切り離す係
PS1 = r'''# Sync-Strata update helper (11/18 W9). Made by launcher\sync_update.py. It runs apart from the app (the app is closed first).
param([string]$Root, [string]$Tool, [string]$Log, [string]$SyncHome, [string]$Lang = 'ja', [switch]$NoClose, [switch]$NoRelaunch)
$ErrorActionPreference = 'Continue'
$ja = $Lang -like 'ja*'
function Say([string]$j, [string]$e) { if ($ja) { Write-Host $j } else { Write-Host $e } }
try { Start-Transcript -LiteralPath $Log -Force | Out-Null } catch { }
try { $Host.UI.RawUI.WindowTitle = 'Sync-Strata update' } catch { }
[Environment]::CurrentDirectory = $env:TEMP; Set-Location -LiteralPath $env:TEMP     # a folder under the app held as the working folder would stop the update from moving it
$App = Join-Path $Root 'app'
$root2 = $App + '\'
function Get-AppProcs {
    @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($root2, [StringComparison]::OrdinalIgnoreCase) -and $_.ProcessId -ne $PID })
}
Say 'Sync-Strata を更新します。この窓は、更新が終わると閉じます。' 'Updating Sync-Strata. This window closes when it is done.'
Say ('  記録: ' + $Log) ('  log: ' + $Log)
Start-Sleep -Seconds 3
if (-not $NoClose) {
    $py = Join-Path $App 'python\python.exe'; $sy = Join-Path $App 'launcher\sync.py'
    if ((Test-Path -LiteralPath $py) -and (Test-Path -LiteralPath $sy)) {
        Say 'エンジンと dsh を止めています（「全て閉じる」と同じ）…' 'Stopping the engine and dsh (the same as "close everything")...'
        $env:SYNC_HOME = $SyncHome
        $o = & $py -s -X utf8 $sy down --all
        foreach ($l in @($o)) { Write-Host ('  ' + $l) }
    }
    # "down" does not close the app frame (Sync-Strata.exe) itself: the update replaces its file, so it is closed here
    $shellDir = (Join-Path $App 'shell') + '\'
    foreach ($p in @(Get-AppProcs | Where-Object { $_.ExecutablePath.StartsWith($shellDir, [StringComparison]::OrdinalIgnoreCase) })) {
        Say '  アプリの枠を閉じます。' '  Closing the app window.'
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    for ($i = 0; $i -lt 30 -and (Get-AppProcs).Count; $i++) { Start-Sleep -Seconds 1 }
    foreach ($p in @(Get-AppProcs)) {
        Say ('  まだ動いています: ' + $p.Name + '（番号 ' + $p.ProcessId + '）') ('  still running: ' + $p.Name + ' (id ' + $p.ProcessId + ')')
    }
}
Say '' ''
Say '更新の道具を流します。' 'Running the update tool.'
$env:SS_NOPAUSE = '1'
$env:SYNC_HOME = $SyncHome
& $Tool --lang $Lang
$rc = $LASTEXITCODE
Say '' ''
$shell = Join-Path $App 'shell\Sync-Strata.exe'
$py = Join-Path $App 'python\python.exe'; $sy = Join-Path $App 'launcher\sync.py'
function Start-App {
    if ($NoRelaunch) { return }
    if (Test-Path -LiteralPath $shell) { Start-Process -FilePath $shell -WorkingDirectory (Split-Path -Parent $shell) }
    elseif ((Test-Path -LiteralPath $py) -and (Test-Path -LiteralPath $sy)) { Start-Process -FilePath $py -ArgumentList @('-s', '-X', 'utf8', $sy, 'up', '--gui', '--open') -WindowStyle Hidden }
}
if ($rc -eq 0) {
    Say '更新が済みました。アプリを起こし直します。' 'The update is done. Starting the app again.'
    Start-App
    for ($i = 8; $i -gt 0; $i--) { Start-Sleep -Seconds 1 }
} else {
    Say ('更新は済みませんでした（終了コード ' + $rc + '）。上の行を読んでください。前の版のままです。') ('The update did not finish (exit ' + $rc + '). Read the lines above. The previous version stays.')
    Say '手で入れる方法や、前の版に戻す方法は INSTALL の「更新する」にあります。' 'To install by hand or go back, see "Update" in INSTALL.'
    try { [void](Read-Host ($(if ($ja) { 'Enter を押すと、アプリを起こし直してこの窓を閉じます' } else { 'Press Enter to start the app again and close this window' }))) } catch { }
    Start-App
}
try { Stop-Transcript | Out-Null } catch { }
try { if ((Split-Path -Leaf $PSScriptRoot) -like 'syncstrata-update-run-*') { Remove-Item -LiteralPath $PSScriptRoot -Recurse -Force -ErrorAction SilentlyContinue } } catch { }
exit $rc
'''

SH = r'''#!/bin/sh
# Sync-Strata update helper (11/18 W9). Made by launcher/sync_update.py. It runs apart from the app (the app is closed first).
# usage: sh helper.sh ROOT TOOL LOG SYNC_HOME LANG   (env: SU_NOCLOSE=1 SU_NORELAUNCH=1 SU_INTERACTIVE=1)
ROOT=$1; TOOL=$2; LOG=$3; SYNC_HOME=$4; LANGV=${5:-en}
export SYNC_HOME
cd "${TMPDIR:-/tmp}" 2>/dev/null   # a folder under the app held as the working folder would stop the update from moving it
say() { case $LANGV in ja*) printf '%s\n' "$1" ;; *) printf '%s\n' "$2" ;; esac; }
app_procs() {  # programs running from <ROOT>/app/ (the update refuses to replace files they use)
  for p in /proc/[0-9]*; do
    e=$(readlink "$p/exe" 2>/dev/null) || continue
    case $e in "$ROOT"/app/*) printf '%s %s\n' "${p#/proc/}" "$e" ;; esac
  done
}
start_app() {
  [ -n "$SU_NORELAUNCH" ] && return
  if [ -x "$ROOT/app/shell/sync-strata" ]; then nohup "$ROOT/app/shell/sync-strata" >/dev/null 2>&1 &
  elif [ -x "$ROOT/app/launcher/sync.sh" ]; then nohup "$ROOT/app/launcher/sync.sh" up --gui --open >/dev/null 2>&1 &
  fi
}
body() {
  say "Sync-Strata を更新します。" "Updating Sync-Strata."
  say "  記録: $LOG" "  log: $LOG"
  sleep 3
  if [ -z "$SU_NOCLOSE" ]; then
    PY=$ROOT/app/python/bin/python3; SY=$ROOT/app/launcher/sync.py
    if [ -x "$PY" ] && [ -f "$SY" ]; then
      say "エンジンと dsh を止めています（「全て閉じる」と同じ）…" "Stopping the engine and dsh (the same as \"close everything\")..."
      "$PY" -s -X utf8 "$SY" down --all
    fi
    # "down" does not close the app frame itself: close it here (also the AppImage, which runs from another place)
    for p in /proc/[0-9]*; do
      e=$(readlink "$p/exe" 2>/dev/null) || continue
      case $e in "$ROOT"/app/shell/*) say "  アプリの枠を閉じます。" "  Closing the app window."; kill "${p#/proc/}" 2>/dev/null ;; esac
    done
    pkill -x sync-strata 2>/dev/null
    i=0; while [ $i -lt 30 ] && [ -n "$(app_procs)" ]; do sleep 1; i=$((i + 1)); done
    app_procs | while read -r a b; do say "  まだ動いています: $b（番号 $a）" "  still running: $b (id $a)"; done
  fi
  echo
  say "更新の道具を流します。" "Running the update tool."
  SS_NOPAUSE=1 sh "$TOOL" --lang "$LANGV"
  rc=$?
  echo
  if [ $rc -eq 0 ]; then
    say "更新が済みました。アプリを起こし直します。" "The update is done. Starting the app again."
    start_app
    [ -n "$SU_INTERACTIVE" ] && sleep 8
  else
    say "更新は済みませんでした（終了コード $rc）。上の行を読んでください。前の版のままです。" "The update did not finish (exit $rc). Read the lines above. The previous version stays."
    say "手で入れる方法や、前の版に戻す方法は INSTALL の「更新する」にあります。" "To install by hand or go back, see \"Update\" in INSTALL."
    if [ -n "$SU_INTERACTIVE" ]; then
      say "Enter を押すと、アプリを起こし直してこの窓を閉じます" "Press Enter to start the app again and close this window"
      read -r _
    fi
    start_app
  fi
  return $rc
}
mkdir -p "$(dirname "$LOG")" 2>/dev/null
( body; echo $? > "$LOG.rc" ) 2>&1 | tee -a "$LOG"
rc=$(cat "$LOG.rc" 2>/dev/null || echo 6); rm -f "$LOG.rc"
case $(basename "$(dirname "$0")") in syncstrata-update-run-*) rm -rf "$(dirname "$0")" 2>/dev/null ;; esac
exit "$rc"
'''


def _terminal_cmd(helper_argv):
    """端末のエミュレーターで helper を流すコマンド（画面のある環境だけ．無ければ None）"""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    for name, sep in (("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"), ("xfce4-terminal", "-x"), ("xterm", "-e")):
        p = shutil.which(name)
        if p:
            return [p, sep] + helper_argv
    return None


def run_apply(argv):
    root = install_root(argv)
    if not root:
        return {"ok": False, "started": False, "kind": "not_installed"}
    tool = tool_path(root)
    if not tool:
        return {"ok": False, "started": False, "kind": "not_installed", "app": root}
    lg = _lang(argv) or "ja"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log = os.path.join(H.home(), "logs", f"update-{stamp}.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    # 係は入れた先の外（一時フォルダー）に置く．入れた先の下で動いていると，更新が「アプリが動いている」と数えて入れ替えない
    d = tempfile.mkdtemp(prefix="syncstrata-update-run-")
    window = True
    if IS_WIN:
        helper = os.path.join(d, "update-helper.ps1")
        with open(helper, "w", encoding="utf-8-sig", newline="\r\n") as f:      # BOM つき（Windows PowerShell 5.1 が日本語を読める）
            f.write(PS1)
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", helper, "-Root", root, "-Tool", tool, "-Log", log,
               "-SyncHome", H.home(), "-Lang", lg]
        if "--no-close" in argv:
            cmd.append("-NoClose")
        if "--no-relaunch" in argv:
            cmd.append("-NoRelaunch")
        flags = 0x00000010 | 0x00000200            # CREATE_NEW_CONSOLE（様子の見える窓）| CREATE_NEW_PROCESS_GROUP
        kw = {"cwd": d, "creationflags": flags | 0x01000000}  # CREATE_BREAKAWAY_FROM_JOB（呼んだ側が job に入っていて，閉じると道連れにされるのを避ける）
        env = None
    else:
        helper = os.path.join(d, "update-helper.sh")
        with open(helper, "w", encoding="utf-8", newline="\n") as f:
            f.write(SH)
        os.chmod(helper, 0o755)
        env = dict(os.environ)
        if "--no-close" in argv:
            env["SU_NOCLOSE"] = "1"
        if "--no-relaunch" in argv:
            env["SU_NORELAUNCH"] = "1"
        hargv = ["sh", helper, root, tool, log, H.home(), lg]
        term = _terminal_cmd(hargv)
        if term:
            cmd = term
            env["SU_INTERACTIVE"] = "1"
        else:
            cmd, window = hargv, False             # 端末が無い（SSH など）: 記録のファイルだけ
        kw = {"cwd": d, "start_new_session": True, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if "--dry" in argv:
        shutil.rmtree(d, ignore_errors=True)
        return {"ok": True, "started": False, "dry": True, "cmd": cmd, "helper": helper, "log": log, "window": window, "tool": tool}
    try:
        try:
            subprocess.Popen(cmd, env=env, **kw)
        except OSError:
            if IS_WIN:                              # job が breakaway を許さない: 外して起こす
                kw["creationflags"] = kw["creationflags"] & ~0x01000000
                subprocess.Popen(cmd, env=env, **kw)
            else:
                raise
    except OSError as e:
        return {"ok": False, "started": False, "kind": "error", "detail": str(e)[:300]}
    return {"ok": True, "started": True, "log": log, "window": window, "tool": tool}


def main(argv):
    if not argv or argv[0] not in ("check", "apply"):
        print("usage: sync update check [--json] [--local] [--source PLACE] | sync update apply [--json] [--source PLACE]")
        return 2
    d = run_check(argv[1:]) if argv[0] == "check" else run_apply(argv[1:])
    if "--json" in argv:
        print(json.dumps(d, ensure_ascii=True))
    else:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0 if d.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
