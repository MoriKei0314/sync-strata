#!/usr/bin/env python3
"""Windows と Linux の違いを 1 か所に（11/16 係 S2．Linux 版の配布のため）．

- Linux では subprocess の creationflags（Windows だけの引数）を外す．「窓なし・別のグループ」（0x08000000｜0x00000200）は
  start_new_session=True に読み替える（起こした端末を閉じても残る）．起動の道具のどのファイルもこれを最初に import する．
- プロセスの生まれた時刻（番号の使い回しの確かめ）・止め方・子の一覧・待ち受けている番号・RAM・CPU の機能を OS ごとに．
"""
import ctypes, os, signal, subprocess, sys, time

IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""

if not IS_WIN and not getattr(subprocess.Popen, "_s2_patched", False):
    _orig_init = subprocess.Popen.__init__

    def _init(self, *a, **kw):
        cf = kw.pop("creationflags", 0) or 0
        if cf & 0x00000208 and "start_new_session" not in kw:     # CREATE_NEW_PROCESS_GROUP / DETACHED_PROCESS
            kw["start_new_session"] = True
        _orig_init(self, *a, **kw)
    subprocess.Popen.__init__ = _init
    subprocess.Popen._s2_patched = True


# ---------------------------------------------------------------- プロセス
def proc_created(pid):
    """生まれた時刻（OS ごとの数．比べるだけに使う）．無い・終わったなら None"""
    if not pid:
        return None
    if IS_WIN:
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            return None
        try:
            c, e, kk, u = (ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong())
            if not k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kk), ctypes.byref(u)):
                return None
            code = ctypes.c_ulong()
            if k32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value != 259:
                return None
            return c.value
        finally:
            k32.CloseHandle(h)
    try:
        st = open(f"/proc/{int(pid)}/stat", encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    rest = st[st.rindex(")") + 2:].split()
    if rest[0] in ("Z", "X"):          # 終わって片づけ待ち
        return None
    return int(rest[19])              # starttime（起動からの clock tick）


def terminate(pid):
    if IS_WIN:
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x0001 | 0x1000, False, pid)
        if not h:
            return False
        ok = bool(k32.TerminateProcess(h, 1))
        k32.CloseHandle(h)
        return ok
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    for _ in range(30):                # 3 秒待って残っていれば SIGKILL
        time.sleep(0.1)
        if proc_created(pid) is None:
            return True
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    return True


def proc_pairs():
    """(番号, 親の番号) の一覧"""
    if IS_WIN:
        class PE(ctypes.Structure):
            _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong), ("th32ProcessID", ctypes.c_ulong),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
                        ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_ulong),
                        ("szExeFile", ctypes.c_wchar * 260)]
        k32 = ctypes.windll.kernel32
        k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        snap = k32.CreateToolhelp32Snapshot(0x2, 0)
        pairs = []
        try:
            e = PE()
            e.dwSize = ctypes.sizeof(PE)
            ok = k32.Process32FirstW(ctypes.c_void_p(snap), ctypes.byref(e))
            while ok:
                pairs.append((e.th32ProcessID, e.th32ParentProcessID))
                ok = k32.Process32NextW(ctypes.c_void_p(snap), ctypes.byref(e))
        finally:
            k32.CloseHandle(ctypes.c_void_p(snap))
        return pairs
    pairs = []
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                st = open(f"/proc/{d}/stat", encoding="utf-8", errors="replace").read()
                pairs.append((int(d), int(st[st.rindex(")") + 2:].split()[1])))
            except (OSError, ValueError, IndexError):
                continue
    return pairs


# ---------------------------------------------------------------- 待ち受け・RAM・CPU
def listen_ports():
    """待ち受けている TCP の番号の集まり（つなぎに行かずに OS に聞く）．読めなければ None"""
    out = set()
    if IS_WIN:
        try:
            ip = ctypes.windll.iphlpapi
        except (AttributeError, OSError):
            return None
        for af in (2, 23):
            size = ctypes.c_ulong(0)
            ip.GetExtendedTcpTable(None, ctypes.byref(size), False, af, 3, 0)
            if not size.value:
                continue
            buf = ctypes.create_string_buffer(size.value + 4096)
            size = ctypes.c_ulong(len(buf))
            if ip.GetExtendedTcpTable(buf, ctypes.byref(size), False, af, 3, 0) != 0:
                return None
            n = ctypes.c_ulong.from_buffer_copy(buf.raw[:4]).value
            rowlen, port_off = (24, 8) if af == 2 else (56, 20)
            for i in range(n):
                o = 4 + i * rowlen + port_off
                out.add(int.from_bytes(buf.raw[o:o + 2], "big"))
        return out
    try:
        for f in ("/proc/net/tcp", "/proc/net/tcp6"):
            if not os.path.exists(f):
                continue
            for line in open(f).read().splitlines()[1:]:
                p = line.split()
                if len(p) > 3 and p[3] == "0A":          # LISTEN
                    out.add(int(p[1].rsplit(":", 1)[1], 16))
        return out
    except OSError:
        return None


def mem_gib():
    """(全体, 空き) GiB"""
    if IS_WIN:
        class MS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                        ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("x", ctypes.c_ulonglong)]
        m = MS()
        m.l = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.total / 1024 ** 3, m.avail / 1024 ** 3
    kv = {}
    for line in open("/proc/meminfo"):
        k, _, v = line.partition(":")
        kv[k] = int(v.split()[0]) * 1024
    return kv.get("MemTotal", 0) / 1024 ** 3, kv.get("MemAvailable", kv.get("MemFree", 0)) / 1024 ** 3


def installed_mem_gib():
    """積んでいる RAM（GiB）．11/16: 内蔵 GPU が取る分（UMA）などで見える量が減っても，段はこれで決める．取れなければ None．
    Windows: GetPhysicallyInstalledSystemMemory（無ければ Win32_PhysicalMemory の Capacity の合計）．
    Linux: /sys/devices/system/memory のブロックの数×大きさ（取れなければ None．呼ぶ側が見える量の段にする）"""
    try:
        o = os.environ.get("SYNC_RAM_INSTALLED_GIB")            # 試し用
        if o:
            return float(o)
    except ValueError:
        pass
    if IS_WIN:
        try:
            kb = ctypes.c_ulonglong(0)
            if ctypes.windll.kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(kb)) and kb.value:
                return round(kb.value / 1024 ** 2, 1)
        except (AttributeError, OSError):
            pass
        try:
            out = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                                  "(Get-CimInstance Win32_PhysicalMemory | Measure-Object Capacity -Sum).Sum"],
                                 capture_output=True, text=True, timeout=30, creationflags=0x08000000).stdout.strip()
            return round(int(out) / 1024 ** 3, 1) if out.isdigit() and int(out) > 0 else None
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None
    base = "/sys/devices/system/memory"
    try:
        bs = int(open(os.path.join(base, "block_size_bytes")).read().strip(), 16)
        n = 0
        for d in os.listdir(base):
            if d.startswith("memory") and d[6:].isdigit():
                try:
                    if open(os.path.join(base, d, "online")).read().strip() != "1":
                        continue
                except OSError:
                    pass
                n += 1
        return round(n * bs / 1024 ** 3, 1) if n else None
    except (OSError, ValueError):
        return None


def cpu_flags():
    """(AVX2, AVX-512F)"""
    if IS_WIN:
        k32 = ctypes.windll.kernel32
        return bool(k32.IsProcessorFeaturePresent(40)), bool(k32.IsProcessorFeaturePresent(41))
    try:
        fl = next((l.split(":", 1)[1].split() for l in open("/proc/cpuinfo") if l.startswith("flags")), [])
    except OSError:
        fl = []
    return "avx2" in fl, "avx512f" in fl


def restrict(p):
    """このファイル（やフォルダー）を今の利用者だけが読めるようにする"""
    if IS_WIN:
        user = os.environ.get("USERNAME")
        if user:
            subprocess.run(["icacls", p, "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F" if os.path.isdir(p) else f"{user}:F"],
                           capture_output=True, creationflags=0x08000000)
    else:
        try:
            os.chmod(p, 0o700 if os.path.isdir(p) else 0o600)
        except OSError:
            pass


def open_url(url):
    """既定のブラウザーで開く"""
    if IS_WIN:
        os.startfile(url)
    else:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def default_home():
    """SYNC_HOME の既定（Windows: %LOCALAPPDATA%\\SyncStrata，Linux: $XDG_CONFIG_HOME/SyncStrata＝~/.config/SyncStrata）"""
    if IS_WIN:
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "SyncStrata")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "SyncStrata")


def default_models_dir(home):
    """モデルの置き場の既定（Windows: SYNC_HOME\\models，Linux: $XDG_DATA_HOME/SyncStrata/models＝~/.local/share/SyncStrata/models．
    大きいので設定の置き場（~/.config）には置かない）"""
    if IS_WIN:
        return os.path.join(home, "models")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "SyncStrata", "models")
