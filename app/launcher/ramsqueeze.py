#!/usr/bin/env python3
"""起動のときに 1 回だけ，ほかのアプリの使う RAM を E: などのページファイルへ追い出して，専門家に回せる空き RAM を増やす（11/16 係 S4）．
アプリは閉じない．管理者の権限は要らない．設定 ram_squeeze が auto（既定）のときだけ．

Windows（作者の日常の squeeze_ram.py の考え方を移した物）:
  段 1  同じユーザー・同じ画面のプロセスの作業中の量を EmptyWorkingSet で下げる（除外: 下の EXCLUDE_*）．
  段 2  この処理が RAM を「ロック」して（working-set の最小＋VirtualLock），空きを使い切らせ，Windows にほかのアプリのページを
        ページファイルへ書き出させる．目標まで下がるか，1 区切りが遅いか，時間切れで，全部いっぺんに手放す．
        （段 2 は Windows が選ぶので，特定のプロセスを避けられない．触られたページは使うときに戻る）
  管理者でないと待機中のメモリ（standby）は捨てられない．ここでは捨てない（待機中の分は元から「空き」に数えられる）．
Linux: 空きにはファイルのキャッシュも入っている．drop_caches は root だけなので，書けるときだけ書く（普通は何もしない）．

試し用: 環境変数 SYNC_FAKE_SQUEEZE="前:後"（GiB．例 19.3:27.5）があれば，何も触らずその値を返す．
"""
import os, sys, time, ctypes, json, subprocess

GiB = 1024 ** 3
MiB = 1024 ** 2
IS_WIN = os.name == "nt"

# 段 1 の除外（名前は小文字・.exe なし）．Windows の大事なプロセスと，画面の部品．
EXCLUDE_NAMES = {
    "system", "registry", "smss", "csrss", "wininit", "winlogon", "services", "lsass", "lsm", "svchost", "fontdrvhost", "dwm", "sihost",
    "ctfmon", "audiodg", "explorer", "searchhost", "startmenuexperiencehost", "shellexperiencehost", "textinputhost", "securityhealthsystray",
    "memory compression", "vmmem", "vmmemwsl", "nvcontainer", "nvidia overlay", "strata", "sync", "dsh",
}
# 段 1 の除外（実行ファイルの場所か引数にこの文字が入っているプロセス）: Sync-Strata の入れた先と SYNC_HOME（エンジン・dsh・中継・画面の WebView2）
def _own_markers():
    ms = []
    try:
        import sync_home as H
        ms.append(os.path.abspath(H.home()).lower())
        ms.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))).lower())    # app\launcher の 2 つ上＝入れた先
    except Exception:
        pass
    ms += ["syncstrata", "sync-strata"]
    return [m for m in ms if m]


def mem_gib():
    """(全体, 空き) GiB．空きは OS の「使える」量（Windows は GlobalMemoryStatusEx＝待機中も含む．エンジンの memory guard と同じ見方）"""
    import oscompat
    return oscompat.mem_gib()


# ------------------------------------------------------------------ Windows
def _procs_ps():
    """段 1 の対象の一覧（PowerShell 1 回．名前・場所・引数・session）"""
    ps = ("$ErrorActionPreference='SilentlyContinue';"
          "$me=(Get-Process -Id $PID).SessionId;"
          "Get-CimInstance Win32_Process | Where-Object { $_.SessionId -eq $me } | "
          "ForEach-Object { @{ pid=$_.ProcessId; ppid=$_.ParentProcessId; name=$_.Name; exe=$_.ExecutablePath; cmd=$_.CommandLine; ws=$_.WorkingSetSize } } | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, timeout=30,
                         creationflags=0x08000000).stdout.decode("utf-8", "replace").strip()
    d = json.loads(out) if out else []
    return d if isinstance(d, list) else [d]


def _ancestors(procs, pid):
    by = {p["pid"]: p for p in procs}
    s, cur = set(), pid
    while cur in by and cur not in s:
        s.add(cur)
        cur = by[cur].get("ppid")
    return s


def excluded(p, own_pids, markers):
    """段 1 で触らないプロセスか"""
    name = (p.get("name") or "").lower()
    name = name[:-4] if name.endswith(".exe") else name
    if p["pid"] in own_pids or name in EXCLUDE_NAMES:
        return True
    hay = ((p.get("exe") or "") + " " + (p.get("cmd") or "")).lower()
    return any(m in hay for m in markers)


def trim_working_sets(procs=None, say=None):
    """段 1．戻り値: (触った数, 作業中の量の減り GiB の見込み)"""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    psapi.EmptyWorkingSet.argtypes = [ctypes.c_void_p]
    procs = procs if procs is not None else _procs_ps()
    me = os.getpid()
    own = _ancestors(procs, me) | {me}
    markers = _own_markers()
    n, ws = 0, 0
    for p in procs:
        if excluded(p, own, markers):
            continue
        h = k32.OpenProcess(0x0100 | 0x1000, 0, int(p["pid"]))      # PROCESS_SET_QUOTA | PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            continue
        try:
            if psapi.EmptyWorkingSet(h):
                n += 1
                ws += int(p.get("ws") or 0)
        finally:
            k32.CloseHandle(h)
    return n, ws / GiB


class _MS(ctypes.Structure):
    _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("x", ctypes.c_ulonglong)]


def _ms():
    m = _MS()
    m.l = ctypes.sizeof(_MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m


def lock_squeeze(target_others_gib, time_limit=30.0, slow_s=4.0, chunk_mib=256, hold_s=1.0, say=None):
    """段 2（squeeze_ram.py と同じ）．戻り値: (ロックした GiB, 止まった理由)"""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.VirtualAlloc.restype = ctypes.c_void_p
    k32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong]
    k32.VirtualLock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    k32.VirtualUnlock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    k32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    k32.SetProcessWorkingSetSizeEx.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_ulong]
    k32.GetProcessWorkingSetSizeEx.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_ulong)]
    proc = k32.GetCurrentProcess()
    # 11/16 エンジン 1 の調べ: 下限を上げたまま残すと，Windows がその分を固定に使える RAM として予約し続け，
    # 起動の道具（エンジンの親として生き続ける）の下でエンジンの固定（埋め込みの表の対応付け）が断られて落ちた．
    # 元の下限・上限を読んでおき，最後に必ず戻す（読めなければ 1 MiB・64 MiB．エンジン 1 が通るのを確かめた値）
    o_mn, o_mx, o_fl = ctypes.c_size_t(0), ctypes.c_size_t(0), ctypes.c_ulong(0)
    if not k32.GetProcessWorkingSetSizeEx(proc, ctypes.byref(o_mn), ctypes.byref(o_mx), ctypes.byref(o_fl)):
        o_mn, o_mx = ctypes.c_size_t(1 * MiB), ctypes.c_size_t(64 * MiB)
    chunk = chunk_mib * MiB
    m0 = _ms()
    total = m0.total
    # コミット（ページファイル＋RAM）の空きを使い切らない: ロックはコミットも食う．4 GiB は残す
    commit_cap = max(0, m0.ap - 4 * GiB)
    want = min(commit_cap, max(0, total - int(target_others_gib * GiB)))
    blocks, locked, why, t0 = [], 0, "最大", time.time()
    try:
        while locked + chunk <= want:
            if time.time() - t0 > time_limit:
                why = "時間切れ"
                break
            if total - locked - _ms().avail <= target_others_gib * GiB:
                why = "目標に届いた"
                break
            tc = time.time()
            if not k32.SetProcessWorkingSetSizeEx(proc, locked + chunk + 256 * MiB, locked + chunk + 512 * MiB, 0):
                why = f"working-set の下限を断られた（{ctypes.get_last_error()}）"
                break
            p = k32.VirtualAlloc(None, chunk, 0x3000, 0x04)
            if not p:
                why = f"VirtualAlloc 失敗（{ctypes.get_last_error()}）"
                break
            blocks.append(p)
            if not k32.VirtualLock(p, chunk):
                why = f"VirtualLock 失敗（{ctypes.get_last_error()}）"
                break
            locked += chunk
            if time.time() - tc > slow_s:
                why = f"1 区切りが {time.time() - tc:.1f} 秒かかった"
                break
        time.sleep(hold_s)
    finally:
        for p in blocks:
            k32.VirtualUnlock(p, chunk)
            k32.VirtualFree(p, 0, 0x8000)
        k32.SetProcessWorkingSetSizeEx(proc, ctypes.c_size_t(-1).value, ctypes.c_size_t(-1).value, 0)
        if not k32.SetProcessWorkingSetSizeEx(proc, o_mn.value, o_mx.value, 0):     # 下限を元に戻す（11/16 の直し）
            k32.SetProcessWorkingSetSizeEx(proc, 1 * MiB, 64 * MiB, 0)
    return locked / GiB, why


# ------------------------------------------------------------------ 入口
def run(mode="auto", target_others_gib=3.0, time_limit=30.0, say=None):
    """起動の前に 1 回．戻り値の辞書: ran（実際に追い出したか）・before_gib・after_gib・freed_gib・seconds・detail（日本語 1 行）・why（画面に出す 1 行）"""
    r = {"ran": False, "mode": mode, "before_gib": None, "after_gib": None, "freed_gib": 0.0, "seconds": 0.0, "detail": "", "why": None}
    if mode == "off":
        r["detail"] = "設定 ram_squeeze が off なので，ほかのアプリの RAM は追い出しません"
        return r
    fake = os.environ.get("SYNC_FAKE_SQUEEZE")
    t0 = time.time()
    if fake:
        b, a = (float(x) for x in fake.split(":"))
        r.update(ran=True, before_gib=b, after_gib=a, detail="試し用の値（SYNC_FAKE_SQUEEZE）")
    elif IS_WIN:
        try:
            _, b = mem_gib()
            n, _ws = trim_working_sets(say=say)
            lk, stopped = lock_squeeze(target_others_gib, time_limit, say=say)
            _, a = mem_gib()
            r.update(ran=True, before_gib=round(b, 2), after_gib=round(a, 2), detail=f"段 1: {n} 個の作業中の量を下げた．段 2: {lk:.1f} GiB をロックして押し出した（{stopped}）")
        except Exception as e:      # 追い出しは補助．失敗しても起動は続ける
            r["detail"] = f"追い出しに失敗しました（{type(e).__name__}: {e}）．そのまま続けます"
            return r
    else:
        try:
            _, b = mem_gib()
            p = "/proc/sys/vm/drop_caches"
            if os.access(p, os.W_OK):
                os.sync()
                open(p, "w").write("1\n")
                _, a = mem_gib()
                r.update(ran=True, before_gib=round(b, 2), after_gib=round(a, 2), detail="ページキャッシュを捨てた（root）")
            else:
                r["detail"] = "Linux では管理者でないと追い出せません．空きにはファイルのキャッシュも入っているので，そのまま続けます"
                return r
        except Exception as e:
            r["detail"] = f"追い出しに失敗しました（{type(e).__name__}: {e}）"
            return r
    r["seconds"] = round(time.time() - t0, 1)
    r["freed_gib"] = round(max(0.0, r["after_gib"] - r["before_gib"]), 2)
    if r["freed_gib"] >= 0.1:
        r["why"] = f"ほかのアプリから {r['freed_gib']:.1f} GiB を追い出しました（アプリは閉じていません．空き RAM {r['before_gib']:.1f} → {r['after_gib']:.1f} GiB）"
    else:
        r["why"] = f"追い出せる分はほとんどありませんでした（空き RAM {r['before_gib']:.1f} → {r['after_gib']:.1f} GiB）"
    return r


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    print(json.dumps(run(sys.argv[1] if len(sys.argv) > 1 else "auto"), ensure_ascii=False, indent=1))
