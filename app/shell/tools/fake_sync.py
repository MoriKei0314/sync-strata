"""偽の起動の道具（11/15 係 T の試し用）．本物の sync.py と同じ命令を受けて，決まった答えを返す．何も起こさない・止めない．

呼ばれた命令は SYNC_HOME\\fake-sync-calls.log に 1 行ずつ残す（枠が何を呼んだかの記録）．
状態は SYNC_HOME\\fake-sync-state.json（engine・dsh の up）．振る舞いは環境変数で替える:
  FAKE_SYNC_FAIL_UP=1     up を失敗させる（終了コード 3）
  FAKE_SYNC_FAIL_DOWN=1   down を失敗させる（終了コード 4）
  （SYNC_HOME に fail-up・fail-down の空ファイルを置いても同じ）
  FAKE_SYNC_UP_SECONDS=n  up にかける秒（既定 4）
  FAKE_SYNC_GUI_URL=…     gui-url の答え（既定 http://127.0.0.1:3181/m/）
"""
import json, os, sys, time

HOME = os.environ.get("SYNC_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", "."), "SyncStrata")
os.makedirs(HOME, exist_ok=True)
STATE = os.path.join(HOME, "fake-sync-state.json")
LOG = os.path.join(HOME, "fake-sync-calls.log")


def log(argv, code):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {' '.join(argv)} -> {code}\n")


def load():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"engine": False, "dsh": False}


def save(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f)


def main(argv):
    cmd = argv[0] if argv else ""
    s = load()
    if cmd == "status":
        time.sleep(float(os.environ.get("FAKE_SYNC_STATUS_SECONDS", "0")))
        print(json.dumps({
            "engine": {"up": s["engine"], "model": "sync-s" if s["engine"] else None, "r": 7 if s["engine"] else None, "port": 8180},
            "dsh": {"up": s["dsh"], "port": 3180},
            "relay": {"up": s["dsh"], "port": 3181, "url": "http://127.0.0.1:3181/m/"},
            "models": {"installed": ["sync-s"], "missing_shared": []},
            "settings": {"gui_gpu": "auto"},
            "first_run": False,
        }, ensure_ascii=False))
        return 0
    if cmd == "up":
        if os.environ.get("FAKE_SYNC_FAIL_UP") == "1" or os.path.exists(os.path.join(HOME, "fail-up")):
            print("PC を調べています…", flush=True)
            time.sleep(1)
            print("エンジンを起こしています…", flush=True)
            time.sleep(1)
            print("偽の失敗: エンジンが 8180 で応えませんでした", file=sys.stderr, flush=True)
            return 3
        n = float(os.environ.get("FAKE_SYNC_UP_SECONDS", "4"))
        for line in ["PC を調べています…", "RAM 31.6 GiB，VRAM 12 GiB．Sync-S（R7）で起こします", "エンジンを起こしています…",
                     "エンジンが応えました（8180）", "dsh と中継を起こしています…", "dsh が応えました（3180・3181）"]:
            print(line, flush=True)
            time.sleep(n / 6)
        s["engine"] = True
        s["dsh"] = "--api-only" not in argv
        save(s)
        return 0
    if cmd == "down":
        if os.environ.get("FAKE_SYNC_FAIL_DOWN") == "1" or os.path.exists(os.path.join(HOME, "fail-down")):
            time.sleep(1)
            print("偽の失敗: dsh が止まりませんでした", file=sys.stderr)
            return 4
        time.sleep(1.5)
        if "--dsh" in argv:
            s["dsh"] = False
        elif "--engine" in argv:
            s["engine"] = False
        else:
            s = {"engine": False, "dsh": False}
        save(s)
        return 0
    if cmd == "gui-url":
        print(os.environ.get("FAKE_SYNC_GUI_URL", "http://127.0.0.1:3181/m/"))
        return 0
    print(f"知らない命令: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    argv = sys.argv[1:]
    code = main(argv)
    log(argv, code)
    sys.exit(code)
