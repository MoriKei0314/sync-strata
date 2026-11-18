#!/usr/bin/env python3
"""メモリの見える化（11/17 係 W5．本人「友人の PC で，裏のアプリがメモリを食っているのが分かりにくかった」）．標準ライブラリだけ．管理者の権限は要らない．

  sync.py mem [--json]     いまのメモリの様子を 1〜2 秒で調べて出す（画面の「メモリ」の欄が中継（GET /m/sysmem）経由で読む）

出す物（JSON．日本語の文は入れない．文は画面が作る）:
  ram     {total_gib, avail_gib, used_gib, reclaimable_gib, avail_effective_gib}
          reclaimable_gib: エンジンの作業セットのうち，ファイルが元のページ（WorkingSetSize − PrivateWorkingSetSize）．ほかのアプリが求めれば Windows が取り返す．
          エンジンがモデルをファイルのマッピングで読むと，空き（avail_gib）が 0.3〜0.7 GiB に見える．avail_effective_gib ＝ avail_gib ＋ reclaimable_gib（使える空き）．
          Windows でエンジンが動いていて読めたときだけ．Linux・止まっているときは null（Linux はページキャッシュが MemAvailable に入っている）
  commit  {limit_gib, used_gib, free_gib}      Windows だけ（RAM＋ページファイルの上限）．Linux は null
  vram    {name, total_gib, used_gib, free_gib}  最初の GPU（nvidia-smi）．無ければ null
  mine    {running, ram_gib, reclaimable_gib, commit_gib, vram_gib, parts[{name, ram_gib, commit_gib}]}   Sync-Strata 自身（エンジン・dsh・中継と，その子）
  others  {ram_gib, commit_gib, vram_gib}      ＝ 使用中 − mine（システム・カーネルの分も含む）
  apps    [{name, n, ram_gib, commit_gib, vram_gib, gain_gib}]   ほかのアプリ（名前ごとにまとめる）．Windows はコミットの多い順，Linux は RAM の多い順
          gain_gib: 閉じて Sync-Strata を起こし直すと，専門家をあと何 GiB RAM に載せられるか（0.25 刻み．SSD に残っている分まで）
  gpu_apps [{name, vram_gib}]                  GPU のメモリを多く使っているアプリ（Windows は typeperf の GPU Process Memory，Linux は nvidia-smi）
  last    直近の起動の記録（run\\last.json）の抜粋 {at, pack, budget_gib, budget_physical_gib, commit_limited, on_file_gib, on_file_pct, experts_gib, seats_gib, commit_free_gib}
  now     いま起こすと（見積もり）{budget_gib, binding: "commit"|"ram", on_file_gib}   last の pack があるときだけ
  alerts  [{key, level: "warn"|"bad", ...数, apps:[{name, gib}]}]   key: commit_cut（起動のとき枠をコミットで削った）／ssd_left（専門家が SSD に残る）／
          commit_tight（いま起こすとコミットで削られる見込み）／vram_taken（ほかのアプリが VRAM を 1 GiB 以上取っている）
数字の出どころ: RAM・コミットは GlobalMemoryStatusEx，アプリごとは GetProcessMemoryInfo（WorkingSetSize＝RAM，PrivateUsage＝コミット）．
読めないプロセス（保護されたもの）は一覧に出ず，others の「そのほか」に入る．
"""
import csv, ctypes, io, json, os, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import oscompat as OS  # noqa: E402
import wintune  # noqa: E402

IS_WIN = os.name == "nt"
G = 1024.0 ** 3
TOP_N = 8
OWN_NAMES = ("strata", "strata-vision")   # 起動の道具が覚えていなくても，この名前はエンジン（別の SYNC_HOME から起こした物も）．その親の server.py（python）も自身に数える
OWN_ROOTS = ("engine", "dsh", "proxy", "relay")
PRIVWS = {}      # pid → プライベートな作業セット（bytes）．_win_procs が埋める．ファイルが元のページ（取り戻せる）＝ WorkingSetSize − これ（11/18 係 W10）


# ---------------------------------------------------------------- Windows の調べ
def _win_mem():
    class MS(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                    ("tpf", ctypes.c_ulonglong), ("apf", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("x", ctypes.c_ulonglong)]
    m = MS()
    m.l = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    # ullTotalPageFile＝コミットの上限，ullAvailPageFile＝コミットの空き
    return {"ram_total": m.total / G, "ram_avail": m.avail / G, "commit_limit": m.tpf / G, "commit_free": m.apf / G}


def _win_procs():
    """[(pid, 名前, ws_bytes, private_bytes)]．読めないプロセスは入れない"""
    class PE(ctypes.Structure):
        _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong), ("th32ProcessID", ctypes.c_ulong),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
                    ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_ulong),
                    ("szExeFile", ctypes.c_wchar * 260)]

    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]
    class PMC2(ctypes.Structure):       # PROCESS_MEMORY_COUNTERS_EX2（Windows 10 1809 以降）
        _fields_ = PMC._fields_ + [("PrivateWorkingSetSize", ctypes.c_size_t), ("SharedCommitUsage", ctypes.c_ulonglong)]
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    gpm = k32.K32GetProcessMemoryInfo
    gpm.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    PRIVWS.clear()
    out, missed = [], []
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    try:
        e = PE()
        e.dwSize = ctypes.sizeof(PE)
        ok = k32.Process32FirstW(ctypes.c_void_p(snap), ctypes.byref(e))
        while ok:
            pid = e.th32ProcessID
            if pid > 4:
                got = False
                h = k32.OpenProcess(0x1000, False, pid)       # PROCESS_QUERY_LIMITED_INFORMATION（QUERY_INFORMATION＋VM_READ を求めると strata.exe は断る）
                if h:
                    pm = PMC2()
                    pm.cb = ctypes.sizeof(PMC2)
                    if gpm(h, ctypes.byref(pm), pm.cb):
                        PRIVWS[pid] = pm.PrivateWorkingSetSize
                        out.append((pid, e.szExeFile, pm.WorkingSetSize, pm.PrivateUsage))
                        got = True
                    else:       # 古い Windows は PMC2 の大きさを断る
                        pm = PMC()
                        pm.cb = ctypes.sizeof(PMC)
                        if gpm(h, ctypes.byref(pm), pm.cb):
                            out.append((pid, e.szExeFile, pm.WorkingSetSize, pm.PrivateUsage))
                            got = True
                    k32.CloseHandle(h)
                if not got:
                    missed.append((pid, e.szExeFile))
            ok = k32.Process32NextW(ctypes.c_void_p(snap), ctypes.byref(e))
    finally:
        k32.CloseHandle(ctypes.c_void_p(snap))
    if missed:      # 開けなかったプロセスは，番号を開かずに読める NtQuerySystemInformation で補う
        ntp = _win_nt_procs()
        for pid, nm in missed:
            if pid in ntp:
                out.append((pid, nm, ntp[pid][0], ntp[pid][1]))
                PRIVWS[pid] = ntp[pid][2]
    return out


def _win_nt_procs():
    """NtQuerySystemInformation(SystemProcessInformation)．pid → (WorkingSetSize, PrivatePageCount, WorkingSetPrivateSize)．プロセスを開かないので，開けない物も読める"""
    try:
        nt = ctypes.windll.ntdll
        nt.NtQuerySystemInformation.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
        size = 1 << 20
        for _ in range(6):
            buf = ctypes.create_string_buffer(size)
            need = ctypes.c_ulong(0)
            st = nt.NtQuerySystemInformation(5, buf, size, ctypes.byref(need))
            if st == 0:
                break
            if (st & 0xFFFFFFFF) != 0xC0000004:        # STATUS_INFO_LENGTH_MISMATCH 以外は諦める
                return {}
            size = max(size * 2, need.value + (1 << 16))
        else:
            return {}
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            return {}
        raw = buf.raw
        import struct
        res, off = {}, 0
        while True:
            nxt = struct.unpack_from("<I", raw, off)[0]
            pid = struct.unpack_from("<Q", raw, off + 80)[0]
            ws = struct.unpack_from("<Q", raw, off + 144)[0]       # WorkingSetSize
            priv = struct.unpack_from("<Q", raw, off + 200)[0]     # PrivatePageCount
            wsp = struct.unpack_from("<Q", raw, off + 8)[0]         # WorkingSetPrivateSize
            res[pid] = (ws, priv, wsp)
            if not nxt:
                break
            off += nxt
        return res
    except Exception:
        return {}


def _win_gpu_by_pid(box):
    """typeperf の GPU Process Memory（専用 VRAM の使用量）．pid → bytes．約 1.5 秒かかるので別のスレッドで"""
    try:
        p = subprocess.run(["typeperf", r"\GPU Process Memory(*)\Dedicated Usage", "-sc", "1"], capture_output=True, timeout=6,
                           creationflags=0x08000000)
        rows = list(csv.reader(io.StringIO(p.stdout.decode("utf-8", "replace"))))
        rows = [r for r in rows if r]
        if len(rows) < 2:
            return
        head, vals = rows[0], rows[1]
        res = {}
        for name, v in zip(head[1:], vals[1:]):
            i = name.find("pid_")
            if i < 0:
                continue
            j = name.find("_", i + 4)
            try:
                pid = int(name[i + 4:j])
                res[pid] = res.get(pid, 0.0) + float(v)
            except ValueError:
                continue
        box["gpu"] = res
    except Exception:
        pass


# ---------------------------------------------------------------- Linux の調べ
def _lin_mem():
    kv = {}
    for line in open("/proc/meminfo"):
        k, _, v = line.partition(":")
        kv[k] = int(v.split()[0]) * 1024
    return {"ram_total": kv.get("MemTotal", 0) / G, "ram_avail": kv.get("MemAvailable", kv.get("MemFree", 0)) / G}


def _lin_procs():
    out = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            st = open(f"/proc/{d}/status", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        nm = rss = None
        for line in st.splitlines():
            if line.startswith("Name:"):
                nm = line.split(":", 1)[1].strip()
            elif line.startswith("VmRSS:"):
                rss = int(line.split()[1]) * 1024
        if nm and rss is not None:
            out.append((int(d), nm, rss, rss))
    return out


# ---------------------------------------------------------------- GPU（nvidia-smi．1 回だけ）
def _smi(args, timeout=6):
    try:
        return subprocess.run(["nvidia-smi"] + args, capture_output=True, text=True, timeout=timeout,
                              creationflags=0x08000000 if IS_WIN else 0).stdout
    except Exception:
        return ""


def _vram():
    o = _smi(["--query-gpu=name,memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"]).strip().splitlines()
    if not o:
        return None
    v = [x.strip() for x in o[0].split(",")]
    try:
        return {"name": v[0], "total_gib": float(v[1]) / 1024, "used_gib": float(v[2]) / 1024, "free_gib": float(v[3]) / 1024}
    except (ValueError, IndexError):
        return None


def _lin_gpu_by_pid():
    res = {}
    for line in _smi(["--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"]).strip().splitlines():
        v = [x.strip() for x in line.split(",")]
        try:
            res[int(v[0])] = float(v[1]) * 1024 * 1024
        except (ValueError, IndexError):
            continue
    return res


# ---------------------------------------------------------------- Sync-Strata 自身の番号
def _own_pids(procs):
    """Sync-Strata（エンジン・dsh・会話の中継・会話の中継のもの）の番号の集まり．起動の道具が覚えている番号とその子孫＋名前が strata の物"""
    pids = {p for p, nm, _, _ in procs if nm.lower().removesuffix(".exe") in OWN_NAMES}
    try:
        import sync_home as H
        rec = H.procs()
        pairs = OS.proc_pairs()
        for name in OWN_ROOTS:
            r = rec.get(name)
            if not r or not r.get("pid") or H.alive(name) is False:
                continue
            todo = [r["pid"]]
            pids.add(r["pid"])
            while todo:
                par = todo.pop()
                for c, pp in pairs:
                    if pp == par and c != par and c not in pids:
                        pids.add(c)
                        todo.append(c)
    except Exception:
        pass
    try:       # エンジンの親の server.py（python）も自身に数える
        names = {p: nm.lower().removesuffix(".exe") for p, nm, _, _ in procs}
        pp = dict(OS.proc_pairs())
        for p in list(pids):
            par = pp.get(p)
            if par and par != os.getpid() and names.get(par, "").startswith(("python", "py")) and par not in pids:
                pids.add(par)
    except Exception:
        pass
    pids.discard(os.getpid())          # この調べ自身は数えない
    return pids


def _own_label(nm):
    n = nm.lower().removesuffix(".exe")
    return {"strata": "engine", "strata-vision": "vision", "node": "dsh", "python": "launcher", "py": "launcher"}.get(n, n)


# ---------------------------------------------------------------- 直近の起動の記録
def _last():
    try:
        import sync_home as H
        d = json.load(open(H.path("run", "last.json"), encoding="utf-8"))
    except Exception:
        return None
    pk = d.get("pick") or {}
    if not pk:
        return None
    lim = pk.get("limits") or {}
    return {"at": d.get("at"), "pack": pk.get("name"), "budget_gib": pk.get("budget"), "budget_physical_gib": pk.get("budget_physical"),
            "commit_limited": bool(pk.get("commit_limited")), "on_file_gib": pk.get("on_file_gib"), "on_file_pct": pk.get("on_file_pct"),
            "experts_gib": pk.get("experts_gib"), "seats_gib": pk.get("seats_gib"), "commit_free_gib": lim.get("commit_free_gib")}


def _budget(avail, cfree, experts, seats):
    """起動の道具の見積もり（wintune.preflight・sync_launch と同じ式）．戻り値 (枠 GiB, 効いているもの)"""
    phys = max(0.0, avail - wintune.ENGINE_RAM_GIB_WIN - wintune.SAFETY_GIB)
    com = None if cfree is None else max(0.0, cfree - wintune.ENGINE_COMMIT_GIB - wintune.COMMIT_HEADROOM_GIB)
    room = max(0.0, (experts or 1e9) - (seats or 0.0))
    b = min(room, phys, com if com is not None else 1e9)
    binding = "commit" if com is not None and com < min(room, phys) else "ram"
    return int(b * 4) / 4.0, binding


def r2(x, n=2):
    return None if x is None else round(x, n)


def probe():
    t0 = time.time()
    box = {}
    gt = None
    if IS_WIN:
        gt = threading.Thread(target=_win_gpu_by_pid, args=(box,), daemon=True)
        gt.start()
    vr = {}
    vt = threading.Thread(target=lambda: vr.update(v=_vram(), lin=(_lin_gpu_by_pid() if not IS_WIN else {})), daemon=True)
    vt.start()
    m = _win_mem() if IS_WIN else _lin_mem()
    procs = _win_procs() if IS_WIN else _lin_procs()
    own = _own_pids(procs)
    vt.join(8)
    if gt:
        gt.join(6)
    gpu_pid = box.get("gpu") or vr.get("lin") or {}
    have_gpu_pid = bool(gpu_pid)
    vram = vr.get("v")

    ram_used = m["ram_total"] - m["ram_avail"]
    commit = None
    if IS_WIN:
        commit = {"limit_gib": m["commit_limit"], "used_gib": m["commit_limit"] - m["commit_free"], "free_gib": m["commit_free"]}

    # 名前ごとにまとめる
    apps, mine_parts = {}, {}
    mine_ram = mine_com = mine_vram = 0.0
    mine_recl, recl_ok = 0.0, False      # エンジンの作業セットのうち，ファイルが元のページ（取り戻せる）．読めなければ None
    for pid, nm, ws, pv in procs:
        base = nm[:-4] if nm.lower().endswith(".exe") else nm
        v = gpu_pid.get(pid, 0.0) / G
        if pid in own:
            mine_ram += ws / G
            mine_com += pv / G
            mine_vram += v
            x = mine_parts.setdefault(_own_label(nm), {"name": _own_label(nm), "ram_gib": 0.0, "commit_gib": 0.0, "vram_gib": 0.0})
            x["ram_gib"] += ws / G
            x["commit_gib"] += pv / G
            x["vram_gib"] += v
            if IS_WIN and _own_label(nm) == "engine" and pid in PRIVWS:
                rc = max(0.0, (ws - PRIVWS[pid]) / G)
                x["reclaimable_gib"] = x.get("reclaimable_gib", 0.0) + rc
                mine_recl += rc
                recl_ok = True
            continue
        x = apps.setdefault(base, {"name": base, "n": 0, "ram_gib": 0.0, "commit_gib": 0.0, "vram_gib": 0.0})
        x["n"] += 1
        x["ram_gib"] += ws / G
        x["commit_gib"] += pv / G
        x["vram_gib"] += v
    running = any(pid in own and nm.lower().removesuffix(".exe") in OWN_NAMES for pid, nm, _w, _p in procs)
    key = (lambda a: -a["commit_gib"]) if IS_WIN else (lambda a: -a["ram_gib"])
    top = sorted(apps.values(), key=key)[:TOP_N]

    last = _last()
    seats = (last or {}).get("seats_gib")
    experts = (last or {}).get("experts_gib")
    # 起こし直すときの空き（動いている Sync-Strata の分は戻る）
    # 取り戻せる分（エンジンがファイルのマッピングで読んだページ）は Windows の空きに見えないが，ほかのアプリが求めれば戻る → 使える空き
    reclaim = mine_recl if (running and recl_ok) else None
    avail_usable = m["ram_avail"] + (reclaim or 0.0)
    avail_eff = avail_usable + ((mine_ram - (reclaim or 0.0)) if running else 0.0)
    cfree_eff = (m["commit_free"] + (mine_com if running else 0.0)) if IS_WIN else None
    now = None
    if last and experts:
        b, binding = _budget(avail_eff, cfree_eff, experts, seats)
        now = {"budget_gib": b, "binding": binding, "on_file_gib": r2(max(0.0, experts - (seats or 0.0) - b))}
    for a in top:      # 閉じたら専門家をあと何 GiB 載せられるか
        a["gain_gib"] = 0.0
        if last and experts:
            b1, _ = _budget(avail_eff + a["ram_gib"], None if cfree_eff is None else cfree_eff + a["commit_gib"], experts, seats)
            a["gain_gib"] = max(0.0, b1 - now["budget_gib"])

    alerts = []
    named = lambda lst, k: [{"name": a["name"], "gib": r2(a[k])} for a in lst if a[k] >= 0.3][:3]   # noqa: E731
    if running and last and last.get("commit_limited"):      # 起動の記録は，いま動いているエンジンのときだけ
        alerts.append({"key": "commit_cut", "level": "bad", "from_gib": last["budget_physical_gib"], "to_gib": last["budget_gib"],
                       "commit_free_gib": last.get("commit_free_gib"), "at": last.get("at"),
                       "apps": named(sorted(apps.values(), key=lambda a: -a["commit_gib"]), "commit_gib")})
    if running and last and (last.get("on_file_pct") or 0) > 3.0:
        alerts.append({"key": "ssd_left", "level": "warn", "gib": last["on_file_gib"], "pct": last["on_file_pct"], "at": last.get("at"),
                       "apps": named(sorted(apps.values(), key=(lambda a: -a["commit_gib"]) if IS_WIN and last.get("commit_limited") else (lambda a: -a["ram_gib"])),
                                     "commit_gib" if IS_WIN and last.get("commit_limited") else "ram_gib")})
    if now and now["on_file_gib"] >= 0.5 and not running:      # 止まっているとき: いま起こすと削られる見込み
        alerts.append({"key": "commit_tight" if now["binding"] == "commit" else "ram_tight", "level": "warn", "gib": now["on_file_gib"], "budget_gib": now["budget_gib"],
                       "free_gib": r2(cfree_eff if now["binding"] == "commit" else avail_eff),
                       "apps": named(sorted(apps.values(), key=(lambda a: -a["commit_gib"]) if now["binding"] == "commit" else (lambda a: -a["ram_gib"])),
                                     "commit_gib" if now["binding"] == "commit" else "ram_gib")})
    others_vram = None
    if vram and have_gpu_pid:
        others_vram = max(0.0, vram["used_gib"] - mine_vram)
    if others_vram is not None and others_vram >= 1.0:
        alerts.append({"key": "vram_taken", "level": "bad" if others_vram >= 2.0 else "warn", "gib": r2(others_vram),
                       "apps": named(sorted(list(apps.values()), key=lambda a: -a["vram_gib"]), "vram_gib")})
    gpu_apps = [{"name": a["name"], "vram_gib": r2(a["vram_gib"])} for a in sorted(apps.values(), key=lambda a: -a["vram_gib"]) if a["vram_gib"] >= 0.1][:5]

    def round_app(a):
        return {k: (r2(v) if isinstance(v, float) else v) for k, v in a.items()}
    return {
        "ok": True, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "os": "windows" if IS_WIN else "linux", "took_s": round(time.time() - t0, 2),
        "ram": {"total_gib": r2(m["ram_total"]), "avail_gib": r2(m["ram_avail"]), "used_gib": r2(ram_used),
                "reclaimable_gib": r2(reclaim), "avail_effective_gib": r2(avail_usable)},
        "commit": None if commit is None else {k: r2(v) for k, v in commit.items()},
        "vram": None if not vram else {"name": vram["name"], **{k: r2(v) for k, v in vram.items() if k != "name"}},
        "mine": {"running": running, "ram_gib": r2(mine_ram), "reclaimable_gib": r2(reclaim), "commit_gib": r2(mine_com) if IS_WIN else None,
                 "vram_gib": r2(mine_vram) if have_gpu_pid else None,
                 "parts": [round_app(x) for x in sorted(mine_parts.values(), key=lambda x: -x["ram_gib"])]},
        "others": {"ram_gib": r2(max(0.0, ram_used - mine_ram)), "commit_gib": r2(max(0.0, commit["used_gib"] - mine_com)) if commit else None,
                   "vram_gib": r2(others_vram)},
        "apps": [round_app(a) for a in top], "gpu_apps": gpu_apps, "last": last, "now": now, "alerts": alerts,
    }


def main(argv):
    try:
        d = probe()
    except Exception as e:      # 画面は ok:false を見て「調べられません」と出す
        d = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    print(json.dumps(d, ensure_ascii=True))
    return 0 if d.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
