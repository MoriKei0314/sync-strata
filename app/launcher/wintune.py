#!/usr/bin/env python3
"""Windows の自動チューニングの下ごしらえ（11/15 夜．本人の計画 ③A・D）．標準ライブラリだけ．管理者の権限は要らない．

  py -3 -X utf8 wintune.py preflight [--pack DIR] [--json OUT] [--no-ssd]      起動の前: PC の状態を調べ，設定と「閉じると効くもの」を出す
  py -3 -X utf8 wintune.py diagnose --log <エンジンのログ> [--from-byte N]      動かした後: 1 窓の内訳から，どこで待っているかを言葉で出す
  py -3 -X utf8 wintune.py ssd --pack DIR                                       専門家のファイルの読みの速さだけ測る（約 120 MB を読む）
  py -3 -X utf8 wintune.py watch [--sec 3]                                      いま CPU・GPU を使っているほかのプロセスを名前つきで出す

preflight が調べるもの（＝ 11/14 の夜に手で調べたこと）:
  RAM（全体・空き・コミットの余裕），ページファイルの場所（モデルと同じ SSD か），RAM を食っているアプリ（閉じると戻る GiB），
  裏で SSD を読み続けるもの・GPU に重ねて描くもの（VS のダウンロード，Afterburner／RTSS など），ページの読み込み（回/秒），
  GPU（名前・VRAM の空き・画面をつないでいるか・クロック・PCIe の世代と幅・HAGS），内蔵 GPU の有無，SSD の読みの速さ（1 件あたり）．
出すもの: pack ごとの「RAM の枠」「VRAM の予約」「ファイルに残る専門家の割合」，勧める pack，勧め（閉じる・スマホから使う など）．
数字の出どころは 11/14〜15 のこの PC（7800X3D・32 GB・3080 12 GB）の実測．ほかの PC では起動後の diagnose で確かめる前提．
"""
import argparse, ctypes, json, os, random, re, subprocess, sys, time

IS_WIN = os.name == "nt"
ENGINE_RAM_GIB_WIN = 2.7      # エンジンの専門家の写し以外の RAM【確認 11/15: 起動前の空き 25.5 → 後 3.3 GiB，写し 19】
SAFETY_GIB = 2.25             # エンジンが写す前に残す分（STRATA_RESIDENT_HEADROOM_GIB 2＋余白 0.25）【確認 11/15: 9 本の起動で，写し＝写す直前の空き − 2.25．起動前の空きからは約 5 GiB 引いた値】
DISPLAY_RESERVE_MIB = 768     # 画面あり・VRAM 10 GiB 以上【11/18 静かな測り: Windows 12 GB の Sync-S・XS で 768 が LOW の出ない最小（512 は LOW・止まり，256 は空き 0）．R4 は 1,024 より 3〜4% 速い】
DISPLAY_RESERVE_SMALL_MIB = 512   # 画面あり・VRAM 10 GiB 未満【11/18 静かな測り: 8 GB の真似の Sync-XS で 512 が LOW の出ない最小（256 は LOW 1 回）．1,024 より decode 13〜15% 速い】
HEADLESS_RESERVE_MIB = 512
# 11/17 G: Windows のコミット（メモリ＋ページファイルの上限）で RAM の枠が削られる．エンジンの行 `exceeds available commit (X GiB minus 2 GiB headroom and a 0.25 GiB margin)`
ENGINE_COMMIT_GIB = 2.0       # エンジンが専門家を写す前に取るコミット【推測: 起動の道具の記録 17.2 とエンジンが見た 15.21 の差．知り合いの PC 1 台】
COMMIT_HEADROOM_GIB = 2.25    # エンジンが残す分（headroom 2 ＋ 余白 0.25）【確認: 3 回の起動の行で 枠＝コミットの空き − 2.25】
# 参考【確認】8 GB で予約 1,024 のとき依頼の始まりの空きが 0〜675 MiB，エンジンは 1,536 を勧めたが，本人の方針（性能優先）で予約は増やさない（11/17）
SLOT_MIB = 1.54               # 専門家の席 1 つの大きさ【推測: 記録 `2.21 GiB free, 1024 reserved, +153 draft -> 706 slots` から】
VRAM_ENGINE_GIB = 6.1         # 席の外の VRAM（稠密部・MTP・頭・CUDA）【計算: Linux 側の自動設定と同じ値】
MIN_SLOTS = 461               # エンジンが起動に要る席の最小の数【確認: 知り合いの PC の記録 `needs at least 461 slots`（706 MiB）．pack によって変わるかは未確認】
RESERVE_FLOOR_MIB = 256       # 起動のやり直しで予約を下げられる下限（sync_launch.loosen と同じ）
def min_vram_gib():
    """11/18 W7: この VRAM（GiB）に届かない GPU では，予約を下限まで下げ，GPU が空でも，席が最小の数に届かず起動できない．
    固定の VRAM ＋ 予約の下限 ＋ 最小の席の大きさ（下書きの分は入れない＝ぎりぎりの PC は止めずに起動を試す）"""
    return VRAM_ENGINE_GIB + RESERVE_FLOOR_MIB / 1024 + MIN_SLOTS * SLOT_MIB / 1024


PACKS = [   # 専門家の大きさ（GiB）．名前は配る名前
    {"id": "sync-m", "name": "Sync-M", "experts_gib": 30.08},
    {"id": "sync-s", "name": "Sync-S", "experts_gib": 24.07},
    {"id": "sync-xs", "name": "Sync-XS", "experts_gib": 20.47},
]
# 名前で分かる「閉じると効くもの」．kind: ram（RAM を食う）／io（裏で SSD を読む）／gpu（モデルと同じ GPU に重ねて描く・負荷を足す）
KNOWN = {
    "chrome": ("ram+gpu", "Chrome（タブが多いと数 GiB．描画が GPU を使う）"),
    "msedge": ("ram+gpu", "Edge"),
    "firefox": ("ram+gpu", "Firefox"),
    "msedgewebview2": ("ram", "WebView2（Teams・ウィジェットなどの中身）"),
    "slack": ("ram", "Slack"), "discord": ("ram+gpu", "Discord"), "teams": ("ram", "Teams"), "ms-teams": ("ram", "Teams"),
    "code": ("ram", "VS Code"), "devenv": ("ram", "Visual Studio"), "unity": ("ram+gpu", "Unity"), "unity hub": ("ram", "Unity Hub"),
    "vmmemwsl": ("ram", "WSL（wsl --shutdown で戻る）"), "vmmem": ("ram", "WSL・仮想マシン"),
    "backgrounddownload": ("io", "Visual Studio のインストーラーの裏のダウンロード（毎秒 約 19 MB を読み，ページの読み込みを増やした）"),
    "msiafterburner": ("gpu", "MSI Afterburner（GPU の監視．止めると揺れが減った）"), "rtss": ("gpu", "RivaTuner（画面に重ねる表示）"),
    "onedrive": ("io", "OneDrive の同期"), "searchindexer": ("io", "Windows の検索の索引づくり"),
    "steam": ("ram", "Steam"), "steamwebhelper": ("ram+gpu", "Steam の画面"), "obs64": ("gpu", "OBS（録画・配信）"),
    "wallpaper32": ("gpu", "動く壁紙"), "wallpaper64": ("gpu", "動く壁紙"), "lghub": ("ram", "Logicool G HUB"),
    "nvidia overlay": ("gpu", "NVIDIA のオーバーレイ"),
}

PS_PROBE = """
$ErrorActionPreference = 'SilentlyContinue'
$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$pf = @(Get-CimInstance Win32_PageFileUsage | ForEach-Object { @{ path = $_.Name; alloc_mb = $_.AllocatedBaseSize; used_mb = $_.CurrentUsage } })
$mem = @(Get-CimInstance Win32_PhysicalMemory | ForEach-Object { @{ gb = [math]::Round($_.Capacity/1GB); speed = $_.ConfiguredClockSpeed } })
$vc = @(Get-CimInstance Win32_VideoController | ForEach-Object { @{ name = $_.Name; hz = $_.CurrentRefreshRate; w = $_.CurrentHorizontalResolution; h = $_.CurrentVerticalResolution; status = $_.Status } })
$disks = @(Get-PhysicalDisk | ForEach-Object { @{ id = [string]$_.DeviceId; name = $_.FriendlyName; bus = [string]$_.BusType; media = [string]$_.MediaType; gb = [math]::Round($_.Size/1GB) } })
$parts = @(Get-Partition | Where-Object DriveLetter | ForEach-Object { @{ letter = [string]$_.DriveLetter; disk = [string]$_.DiskNumber } })
$procs = @(Get-Process | Group-Object Name | ForEach-Object { @{ name = $_.Name; n = $_.Count; ws = (($_.Group | Measure-Object WorkingSet64 -Sum).Sum); priv = (($_.Group | Measure-Object PrivateMemorySize64 -Sum).Sum) } } | Sort-Object { $_.priv } -Descending | Select-Object -First 40)
$c = Get-Counter '\\Memory\\Page Reads/sec','\\Memory\\Available MBytes','\\Memory\\Committed Bytes','\\Memory\\Commit Limit','\\PhysicalDisk(_Total)\\Disk Read Bytes/sec','\\Processor(_Total)\\% Processor Time' -SampleInterval 3 -MaxSamples 1
$cnt = @{}
foreach ($s in $c.CounterSamples) { $cnt[$s.Path] = $s.CookedValue }
$hags = (Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers' -Name HwSchMode).HwSchMode
$plan = (powercfg /getactivescheme) -join ' '
@{ os = $os.Caption; build = $os.BuildNumber; ram_total_kb = $os.TotalVisibleMemorySize; ram_free_kb = $os.FreePhysicalMemory;
   cpu = $cpu.Name; cores = $cpu.NumberOfCores; threads = $cpu.NumberOfLogicalProcessors; pagefiles = $pf; dimms = $mem; video = $vc;
   disks = $disks; parts = $parts; procs = $procs; counters = $cnt; hags = $hags; power_plan = $plan } | ConvertTo-Json -Depth 5 -Compress
"""


def reserve_for(vram_total_gib, display):
    """VRAM の予約（MiB）．画面あり VRAM 10 GiB 以上 768・10 GiB 未満 512，画面なし 512．
    11/17 本人の方針（性能優先．起動できるギリギリ＝LOW にならない最小）で，11/18 の静かな測り（autoconfig-grid-1117・msq-1118）から決めた．
    画面なしは測っていないので今のまま（512）．8 GB の値は，エンジンの塊の決め方の直しの後に測り直す"""
    if not display:
        return HEADLESS_RESERVE_MIB
    return DISPLAY_RESERVE_MIB if float(vram_total_gib or 0) >= 10.0 else DISPLAY_RESERVE_SMALL_MIB


def run_ps(script, timeout=120):
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + script], capture_output=True, timeout=timeout)
    return p.stdout.decode("utf-8", "replace")


def nvidia():
    q = ("name,memory.total,memory.used,memory.free,clocks.gr,power.draw,power.limit,temperature.gpu,"
         "pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,display_active,display_mode,driver_version,utilization.gpu")
    try:
        o = subprocess.run(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    out = []
    for line in o.strip().splitlines():
        v = [x.strip() for x in line.split(",")]
        if len(v) < 15:
            continue

        def f(x):
            try:
                return float(x)
            except ValueError:
                return None
        out.append({"name": v[0], "vram_total_mib": f(v[1]), "vram_used_mib": f(v[2]), "vram_free_mib": f(v[3]), "clock_mhz": f(v[4]),
                    "power_w": f(v[5]), "power_limit_w": f(v[6]), "temp_c": f(v[7]), "pcie_gen": f(v[8]), "pcie_gen_max": f(v[9]),
                    "pcie_width": f(v[10]), "display_active": v[11], "display_mode": v[12], "driver": v[13], "util_pct": f(v[14])})
    return out


def ssd_probe(pack, n=96, seed=1):
    """専門家のファイルを，OS の控えを通さずに（FILE_FLAG_NO_BUFFERING），1 件 1.25 MiB で n 回，ばらばらの場所から読む．
    1 件ずつ（待ち行列 1）の時間の中央値・90% 点と，8 件同時の速さ（GB/s）を返す．エンジンの冷たい読みと同じ読み方の物差し．"""
    path = None
    for nm in ("experts.v2.bin", "experts.bin"):
        p = os.path.join(pack, nm)
        if os.path.exists(p):
            path = p
            break
    if path is None or not IS_WIN:
        return {"error": "専門家のファイルが見つからない" if path is None else "Windows だけ"}
    import threading
    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = ctypes.c_void_p
    k32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    k32.VirtualAlloc.restype = ctypes.c_void_p
    k32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
    k32.SetFilePointerEx.argtypes = [ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint32]
    k32.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    size = os.path.getsize(path)
    blob = 1310720      # 1.25 MiB（4096 の倍数）
    rnd = random.Random(seed)
    offs = [rnd.randrange(0, (size - blob) // 4096) * 4096 for _ in range(n)]

    def open_h():
        return k32.CreateFileW(path, 0x80000000, 0x7, None, 3, 0x20000000, None)   # GENERIC_READ, 共有, OPEN_EXISTING, NO_BUFFERING

    def read_at(h, buf, off):
        got = ctypes.c_uint32(0)
        k32.SetFilePointerEx(h, off, None, 0)
        return bool(k32.ReadFile(h, buf, blob, ctypes.byref(got), None)) and got.value == blob

    h = open_h()
    if not h or h == ctypes.c_void_p(-1).value:
        return {"error": "開けない"}
    buf = k32.VirtualAlloc(None, blob, 0x3000, 0x04)
    ts = []
    for o in offs[: n // 2]:
        t0 = time.perf_counter()
        if read_at(h, buf, o):
            ts.append((time.perf_counter() - t0) * 1000)
    k32.CloseHandle(h)
    ts.sort()
    rest = offs[n // 2:]

    def worker(lst):
        hh = open_h()
        bb = k32.VirtualAlloc(None, blob, 0x3000, 0x04)
        for o in lst:
            read_at(hh, bb, o)
        k32.CloseHandle(hh)
    th = [threading.Thread(target=worker, args=(rest[i::8],)) for i in range(8)]
    t0 = time.perf_counter()
    for t in th:
        t.start()
    for t in th:
        t.join()
    dt = time.perf_counter() - t0
    if not ts:
        return {"error": "読めない", "file": path}
    return {"file": path, "blob_bytes": blob, "qd1_ms_median": round(ts[len(ts) // 2], 3), "qd1_ms_p90": round(ts[int(len(ts) * 0.9)], 3),
            "qd1_ms_min": round(ts[0], 3), "qd1_gbps": round(blob / 1e9 / (ts[len(ts) // 2] / 1000), 2),
            "qd8_gbps": round(len(rest) * blob / 1e9 / dt, 2), "reads": len(ts) + len(rest)}


def preflight(pack_dir=None, do_ssd=True):
    d = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "platform": sys.platform}
    if IS_WIN:
        raw = run_ps(PS_PROBE)
        try:
            p = json.loads(raw[raw.index("{"):])
        except Exception as e:
            return {"error": f"PowerShell の調べが読めない: {e}", "raw": raw[:400]}
    else:       # 11/16 S2: Linux は lintune.probe() が同じ形の辞書を作る（/proc と /sys）
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import lintune
        p = lintune.probe()
        d["linux"] = p.get("linux")
    G = 1024.0 ** 3
    ram_total = p["ram_total_kb"] / 1024 / 1024
    cnt = {k.lower(): v for k, v in (p.get("counters") or {}).items()}

    def c(name):
        for k, v in cnt.items():
            if k.endswith(name):
                return v
        return None
    avail = (c("available mbytes") or p["ram_free_kb"] / 1024) / 1024
    d["os"] = f"{p.get('os')} {p.get('build')}"
    d["cpu"] = {"name": (p.get("cpu") or "").strip(), "cores": p.get("cores"), "threads": p.get("threads"), "busy_pct": round(c("% processor time") or 0, 1)}
    try:      # 11/16: 積んでいる量（段はこれで決める．取れなければ None）
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import oscompat
        installed = oscompat.installed_mem_gib()
    except Exception:
        installed = None
    d["ram"] = {"total_gib": round(ram_total, 2), "installed_gib": installed, "avail_gib": round(avail, 2),
                "commit_free_gib": round(((c("commit limit") or 0) - (c("committed bytes") or 0)) / G, 1) if c("commit limit") else None,   # 11/17: Linux は None
                "commit_limit_gib": round(c("commit limit") / G, 1) if c("commit limit") else None,
                "dimms": p.get("dimms"), "page_reads_per_s": round(c("page reads/sec") or 0), "disk_read_mb_s": round((c("disk read bytes/sec") or 0) / 1e6, 1)}
    disk_of = {x["letter"].upper(): x["disk"] for x in p.get("parts") or []}
    disks = {x["id"]: x for x in p.get("disks") or []}
    pfs = p.get("pagefiles") or []
    d["pagefiles"] = [{"path": x["path"], "alloc_gib": round((x.get("alloc_mb") or 0) / 1024, 1), "used_gib": round((x.get("used_mb") or 0) / 1024, 1)} for x in pfs]
    model_letter = os.path.abspath(pack_dir)[0].upper() if pack_dir else None
    if model_letter and IS_WIN:
        dk = disks.get(disk_of.get(model_letter, ""), {})
        d["model_drive"] = {"letter": model_letter, "disk": dk.get("name"), "bus": dk.get("bus"), "media": dk.get("media")}
        d["pagefile_on_model_disk"] = any(disk_of.get(x["path"][0].upper()) == disk_of.get(model_letter) for x in pfs if x.get("path"))
    gp = nvidia()
    d["gpus"] = gp
    d["video_adapters"] = p.get("video")
    names = [(v.get("name") or "") for v in p.get("video") or []]
    d["igpu_present"] = any(re.search(r"Radeon\(TM\) Graphics|Intel\(R\).*(UHD|Iris|HD) Graphics|AMD Radeon Graphics", n) for n in names)
    d["hags"] = {2: "on", 1: "off"}.get(p.get("hags"), "不明")
    d["power_plan"] = p.get("power_plan")
    apps = []
    for x in p.get("procs") or []:
        nm = (x.get("name") or "").lower()
        kind, label = KNOWN.get(nm, (None, None))
        priv = (x.get("priv") or 0) / G
        if kind or priv >= 0.3:
            apps.append({"name": x.get("name"), "n": x.get("n"), "private_gib": round(priv, 2), "kind": kind, "label": label})
    d["apps"] = apps
    # 11/17 G: コミットの多いアプリ（PrivateMemorySize64＝コミットした量．RAM の多い順ではない）．閉じればコミットが戻る
    d["commit_top"] = [{"name": a["name"], "label": a["label"], "private_gib": a["private_gib"]} for a in sorted((x for x in apps if (x["name"] or "").lower() != "strata"), key=lambda a: -a["private_gib"])[:5]] if IS_WIN else []
    d["pagefile_total_gib"] = round(sum(x["alloc_gib"] for x in d["pagefiles"]), 1) if IS_WIN else None
    # Strata が動いているときは，その分を空きに足して考える（止めてから調べるのが確か）
    eng = [x for x in p.get("procs") or [] if (x.get("name") or "").lower() == "strata"]
    d["strata_running"] = bool(eng)
    if eng:
        eng_ws = sum((x.get("ws") or 0) for x in eng) / G
        d["ram"]["strata_working_set_gib"] = round(eng_ws, 2)
        avail += eng_ws
        d["ram"]["avail_if_stopped_gib"] = round(avail, 2)
    closable = [a for a in apps if a["kind"]]
    d["closable_gib"] = round(sum(a["private_gib"] for a in closable if "ram" in (a["kind"] or "")), 2)
    if pack_dir and do_ssd:
        d["ssd"] = ssd_probe(pack_dir)
    g0 = gp[0] if gp else {}
    display = (g0.get("display_active") or "").lower().startswith("enabled")
    reserve = reserve_for((g0.get("vram_total_mib") or 0) / 1024, display)    # 11/17 G: 8 GB で画面ありは 1,536
    vram_free = (g0.get("vram_free_mib") or 0) / 1024
    if eng and gp:      # 動いている Strata の VRAM は分けて見えない（WDDM）: 全体から画面の分（推測 0.9 GiB）を引いた値で考える
        vram_free = (g0.get("vram_total_mib") or 0) / 1024 - (0.9 if display else 0.1)
        d["vram_free_assumed_gib"] = round(vram_free, 2)
    seats_gib = max(0.0, vram_free - VRAM_ENGINE_GIB - reserve / 1024) if gp else 0.0
    pin_cap = ram_total / 2 - 2.1 if IS_WIN else None      # WDDM: GPU から読める固定は RAM の半分まで【確認: 31.6 GiB で 13.5〜13.65】
    recs = []
    for avail_case, label in ((avail, "今のまま"), (avail + d["closable_gib"], "上のアプリを閉じたら")):
        for pk in PACKS:
            budget = max(0.0, min(pk["experts_gib"] - seats_gib, avail_case - ENGINE_RAM_GIB_WIN - SAFETY_GIB))
            cf = d["ram"].get("commit_free_gib")
            if IS_WIN and cf is not None:      # 11/17 G: コミットの枠（閉じる場合は，閉じたアプリのコミットも戻る）
                budget = min(budget, max(0.0, cf + (d["closable_gib"] if avail_case != avail else 0) - ENGINE_COMMIT_GIB - COMMIT_HEADROOM_GIB))
            budget = int(budget * 4) / 4.0
            on_file = max(0.0, pk["experts_gib"] - seats_gib - budget)
            recs.append({"case": label, "pack": pk["name"], "resident_budget_gib": budget, "vram_reserve_mib": reserve,
                         "seats_gib": round(seats_gib, 2), "on_file_gib": round(on_file, 2),
                         "on_file_pct": round(100 * on_file / pk["experts_gib"], 1),
                         "pinned_gib": round(min(budget, pin_cap), 1) if pin_cap else budget})
    d["settings"] = recs
    d["pin_cap_gib"] = round(pin_cap, 1) if pin_cap else None
    adv = []
    now = {r["pack"]: r for r in recs if r["case"] == "今のまま"}
    aft = {r["pack"]: r for r in recs if r["case"] != "今のまま"}
    pick = next((r for r in (now.get("Sync-M"), now.get("Sync-S"), now.get("Sync-XS")) if r and r["on_file_pct"] <= 3.0), None)
    d["recommended_pack"] = pick["pack"] if pick else "Sync-XS"
    if now.get("Sync-M", {}).get("on_file_pct", 0) > 3.0:
        m = now["Sync-M"]
        adv.append(f"Sync-M は専門家の {m['on_file_pct']}%（{m['on_file_gib']} GiB）が SSD に残る．会話のたびに SSD を読んで待つので，"
                   f"この PC では {d['recommended_pack']} が速い（SSD に残らない）．")
        if aft.get("Sync-M", {}).get("on_file_pct", 100) <= 3.0:
            adv.append(f"ただし，下のアプリを閉じれば（約 {d['closable_gib']} GiB 戻る）Sync-M も全部 RAM に載る．")
    if ram_total <= 33:
        adv.append("RAM が 32 GB 以下: 会話の画面は PC のブラウザーでなく，スマホ・タブレットから開く（リモート）のがよい．"
                   "PC のブラウザーは RAM を 1〜3 GiB 使い，画面を映す GPU がモデルと同じだと描画が decode を遅くする．")
    for a in apps:
        if a["kind"] and "io" in a["kind"]:
            adv.append(f"{a['label']}（{a['name']}）が動いている: 測り・会話の間は止める．")
        if a["kind"] == "gpu":
            adv.append(f"{a['label']}（{a['name']}）が動いている: 止めると速さの揺れが減る．")
    big = sorted([a for a in closable if "ram" in (a["kind"] or "") and a["private_gib"] >= 0.3], key=lambda a: -a["private_gib"])
    if big:
        adv.append("閉じると RAM が戻るもの: " + "，".join(f"{a['label'] or a['name']} {a['private_gib']} GiB" for a in big[:6]))
    if d.get("pagefile_on_model_disk"):
        adv.append("ページファイルがモデルと同じ SSD にある: RAM が足りなくなると，モデルの読みとページの読み書きが同じ SSD を取り合う．"
                   "RAM の枠は「起動後に 1 GiB 残る」より大きくしない．")
    md = d.get("model_drive") or {}
    if (md.get("media") or "").upper() == "HDD" and any(r["on_file_gib"] > 0 for r in recs if r["case"] == "今のまま"):   # 11/18 W7
        adv.append("モデルの置き場が HDD: 専門家が SSD（HDD）から読まれるので遅くなる．SSD に置くと速い．")
    if d["ram"]["page_reads_per_s"] > 300:
        adv.append(f"いまページの読み込みが毎秒 {d['ram']['page_reads_per_s']} 回ある（静かなときは 10 回前後）: 落ち着くまで待ってから起動・測定する．")
    if display and d["igpu_present"]:
        adv.append("内蔵 GPU がある: モニターをマザーボード側の端子につなぐと，VRAM が約 0.5〜1 GiB 空き，描画が decode と取り合わなくなる．")
    elif display:
        adv.append(f"画面をこの GPU が映している（内蔵 GPU は見つからない／無効）: VRAM の予約は {reserve_for(float(g0.get('vram_total_mib') or 0) / 1024 if g0 else 0, True):,} MiB．ブラウザーの描画は decode と同じ GPU を使う．")
    if g0 and g0.get("pcie_width") and g0["pcie_width"] < 16:
        adv.append(f"PCIe の幅が x{g0['pcie_width']:.0f}: RAM の専門家を GPU が読む道（PCIe）が細い → CPU に多く回す（自動の分担に任せる）．")
    s = d.get("ssd") or {}
    if s.get("qd1_ms_median"):
        adv.append(f"SSD の読み: 専門家 1 人分（1.25 MiB）が 1 件ずつで中央 {s['qd1_ms_median']} ms（90% 点 {s['qd1_ms_p90']}），8 件同時で {s['qd8_gbps']} GB/s．"
                   + ("1 件 0.6 ms を超える: SSD に残る専門家があると 1 窓に数 ms 待つ．" if s["qd1_ms_median"] > 0.6 else ""))
    if eng:
        adv.insert(0, "Strata が動いている最中の調べ: RAM は Strata の分を足し戻し，VRAM は画面の分を 0.9 GiB と置いた見積もり．確かな値は止めてから．")
    d["advice"] = adv
    return d


TIMING = re.compile(
    r"strata decode timing: (\d+) windows, avg T ([\d.]+), ([\d.]+) tokens/window, ([\d.]+) ms/window = adapt wait ([\d.]+) "
    r"\+ verify ([\d.]+) \(GPU-reach wait ([\d.]+) \+ per-layer host ([\d.]+) \[plan ([\d.]+) actq ([\d.]+) jobs ([\d.]+) "
    r"CPU ([\d.]+)\] \+ stage ([\d.]+)\) \+ commit/emit ([\d.]+) \+ draft ([\d.]+).*?"
    r"per layer-window: CPU experts ([\d.]+) \(([\d.]+) entries\), VRAM hits ([\d.]+), PCIe ([\d.]+); ([\d.]+) swaps/window")
TK = ["T", "tok_w", "ms_w", "adapt", "verify", "gpu", "host", "plan", "actq", "ssd", "cpu", "stage", "commit", "draft", "cpu_exp", "cpu_ent", "hits", "pcie", "swaps"]
LAG = re.compile(r"strata ql lag \(ms/window\): the GPU waited for the CPU rows ([\d.]+).*?for the plan ([\d.]+), for the PCIe share ([\d.]+).*?"
                 r"to the next router ([\d.]+).*?the CPU waited for the GPU's experts about ([\-\d.]+)")
COLD = re.compile(r"cold reads .*?\((\d+) such experts.*?total waited ([\d.]+) ms")
GEN = re.compile(r"(\d+) generated in \d+ ms \(([\d.]+) tok/s\), drafts accepted (\d+) of (\d+)")


def diagnose(log, start=0):
    """エンジンのログ（STRATA_DECODE_TIMING=1）から，1 窓の時間の内訳を窓の数で重みづけて出し，待ちの原因を言葉にする．
    11/14 の夜に手でやった読み方（GPU の待ちの下限と比べる・SSD の待ち・CPU 側・1 窓で進むトークン）をそのまま規則にした．"""
    text = open(log, "rb").read()[start:].decode("utf-8", "replace")
    W = 0
    acc = [0.0] * len(TK)
    lag = [0.0] * 5
    lagW = 0
    cold_n = cold_ms = 0.0
    toks = 0
    ms = 0.0
    da = dn = 0
    pend_w = 0
    for line in text.splitlines():
        m = TIMING.search(line)
        if m:
            w = int(m.group(1))
            W += w
            pend_w = w
            for i, v in enumerate(m.groups()[1:]):
                acc[i] += float(v) * w
            continue
        m = LAG.search(line)
        if m and pend_w:
            for i, v in enumerate(m.groups()):
                lag[i] += float(v) * pend_w
            lagW += pend_w
            continue
        m = COLD.search(line)
        if m:
            cold_n += int(m.group(1))
            cold_ms += float(m.group(2))
            continue
        m = GEN.search(line)
        if m:
            n = int(m.group(1))
            toks += n
            ms += n / max(float(m.group(2)), 1e-6) * 1000
            da += int(m.group(3))
            dn += int(m.group(4))
    if not W:
        return {"error": "strata decode timing の行が無い（STRATA_DECODE_TIMING=1 で起動する）"}
    w = {k: round(acc[i] / W, 3) for i, k in enumerate(TK)}
    out = {"windows": W, "tok_s": round(toks / ms * 1000, 1) if ms else None, "window": w, "draft_accept_pct": round(100 * da / dn, 1) if dn else None,
           "cold_reads_per_window": round(cold_n / W, 2), "cold_wait_ms_per_window": round(cold_ms / W, 2)}
    if lagW:
        out["lag"] = dict(zip(["gpu_waited_cpu_rows", "gpu_waited_plan", "gpu_waited_pcie", "dense_ms", "cpu_waited_gpu_experts"], [round(x / lagW, 3) for x in lag]))
    find = []
    other = w["ms_w"] - w["gpu"] - w["host"] - w["draft"]
    find.append(f"1 窓 {w['ms_w']} ms = GPU の待ち {w['gpu']} + CPU 側 {w['host']}（計画 {w['plan']}・量子化 {w['actq']}・SSD の待ち {w['ssd']}・専門家 {w['cpu']}）"
                f"+ 下書き {w['draft']} + ほか {other:.2f}．1 窓で {w['tok_w']} トークン（下書きの当たり {out['draft_accept_pct']}%）→ {out['tok_s']} tok/s．")
    if w["ssd"] >= 0.8:
        find.append(f"【SSD】冷たい読みで 1 窓 {w['ssd']} ms 待っている（{out['cold_reads_per_window']} 件/窓）．無くせば約 {1000 * w['tok_w'] / (w['ms_w'] - w['ssd']):.0f} tok/s．"
                    "手: RAM の枠を増やす（ほかのアプリを閉じる）／小さい pack にする／RAM の写しを会話に合わせて育てる（STRATA_QL_RAM_ROTATE）．")
    if out.get("lag"):
        L = out["lag"]
        if L["cpu_waited_gpu_experts"] > 1.5 and L["cpu_waited_gpu_experts"] > L["gpu_waited_cpu_rows"] + 0.8:
            find.append(f"【分担】CPU が GPU の専門家を 1 窓 {L['cpu_waited_gpu_experts']} ms 待っている（GPU が CPU を待ったのは {L['gpu_waited_cpu_rows']}）: "
                        "PCIe に回しすぎ → --pcie-frac を下げる（自動なら STRATA_QL_PCIE_AUTO=1）．")
        elif L["gpu_waited_cpu_rows"] > 1.5 and L["gpu_waited_cpu_rows"] > L["cpu_waited_gpu_experts"] + 0.8:
            find.append(f"【分担】GPU が CPU の行を 1 窓 {L['gpu_waited_cpu_rows']} ms 待っている（CPU が GPU を待ったのは {L['cpu_waited_gpu_experts']}）: "
                        "CPU に回しすぎか，SSD の読み待ち → --pcie-frac を上げる・冷たい読みを減らす．")
        else:
            find.append(f"【分担】CPU と GPU の待ち合いはほぼ釣り合い（GPU が CPU を {L['gpu_waited_cpu_rows']} ms，CPU が GPU を {L['cpu_waited_gpu_experts']} ms）．")
        find.append(f"【GPU の下限】専門家以外（稠密部など）が 1 窓 {L['dense_ms']} ms．これは CPU と並べられない足し算の分で，GPU のクロックと画面の描画で動く．")
    elif w["gpu"] > 12:
        find.append(f"【GPU】GPU の待ちが {w['gpu']} ms（RTX 3080 の下限は 9〜10 ms）: PCIe に回しすぎか，画面の描画・ほかのアプリが GPU を使っている．")
    if w["plan"] + w["actq"] > 2.5:
        find.append(f"【CPU の取り合い】計画＋量子化が {w['plan'] + w['actq']:.2f} ms（静かなときは 1.8 前後）: ほかの処理が CPU を使っている疑い（組み立て・ウイルス対策の走査など）．")
    if w["tok_w"] < 1.6:
        find.append(f"【下書き】1 窓で進むのが {w['tok_w']} トークンと少ない（当たり {out['draft_accept_pct']}%）: 下書きを短くする・切るほうが速いかを比べる価値がある．")
    out["findings"] = find
    return out


PS_WATCH = r"""
$ErrorActionPreference = 'SilentlyContinue'
$sec = __SEC__
$a = @{}; Get-Process | ForEach-Object { $a[$_.Id] = @{ n = $_.Name; c = $_.CPU } }
$g = Get-Counter '\GPU Engine(*)\Utilization Percentage' -SampleInterval 1 -MaxSamples $sec
$b = Get-Process
$cores = [Environment]::ProcessorCount
$cpu = @{}
foreach ($p in $b) { if ($a.ContainsKey($p.Id) -and $p.CPU -ne $null -and $a[$p.Id].c -ne $null) {
  $d = ($p.CPU - $a[$p.Id].c) / $sec
  if ($d -gt 0.02) { if (-not $cpu.ContainsKey($p.Name)) { $cpu[$p.Name] = 0.0 }; $cpu[$p.Name] += $d } } }
$gpu = @{}
foreach ($smp in $g) { foreach ($s in $smp.CounterSamples) {
  if ($s.InstanceName -match 'pid_(\d+)_.*engtype_(\w+)') {
    $k = $Matches[1] + '|' + $Matches[2]
    if (-not $gpu.ContainsKey($k)) { $gpu[$k] = 0.0 }
    $gpu[$k] += $s.CookedValue / $sec } } }
$names = @{}; foreach ($p in $b) { $names[[string]$p.Id] = $p.Name }
$gl = @(); foreach ($k in $gpu.Keys) { if ($gpu[$k] -ge 1.0) { $pp = $k.Split('|'); $gl += @{ pid = $pp[0]; name = $names[$pp[0]]; engine = $pp[1]; pct = [math]::Round($gpu[$k], 1) } } }
$cl = @(); foreach ($k in $cpu.Keys) { $cl += @{ name = $k; cores = [math]::Round($cpu[$k], 2) } }
@{ sec = $sec; logical = $cores; cpu = $cl; gpu = $gl } | ConvertTo-Json -Depth 4 -Compress
"""


def watch(sec=3):
    """いま CPU・GPU を使っているプロセスを見る（strata 自身は別に出す）．管理者なし．Linux は lintune.watch．
    CPU は「コア何個分か」（プロセスの CPU 時間の増え方），GPU は Windows のカウンター（GPU Engine の使用率．3D・Cuda・Copy などの種類つき）．"""
    if not IS_WIN:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import lintune
        return lintune.watch(sec)
    raw = run_ps(PS_WATCH.replace("__SEC__", str(int(sec))), timeout=60 + int(sec) * 3)
    try:
        d = json.loads(raw[raw.index("{"):])
    except Exception as e:
        return {"error": f"読めない: {e}", "raw": raw[:300]}
    mine = ("strata", "python", "powershell", "conhost", "claude", "node", "pwsh", "bash")
    cpu = sorted(d.get("cpu") or [], key=lambda x: -x["cores"])
    gpu = sorted(d.get("gpu") or [], key=lambda x: -x["pct"])
    others_cpu = [x for x in cpu if (x["name"] or "").lower() not in mine and (x["name"] or "") != "Idle"]
    others_gpu = [x for x in gpu if (x.get("name") or "").lower() != "strata"]
    out = {"sec": d.get("sec"), "logical": d.get("logical"),
           "strata_cpu_cores": next((x["cores"] for x in cpu if (x["name"] or "").lower() == "strata"), 0.0),
           "strata_gpu": [x for x in gpu if (x.get("name") or "").lower() == "strata"],
           "others_cpu": others_cpu[:6], "others_gpu": others_gpu[:6],
           "others_cpu_cores": round(sum(x["cores"] for x in others_cpu), 2),
           "others_gpu_pct": round(sum(x["pct"] for x in others_gpu if x.get("engine") in ("3D", "Cuda", "Compute_0", "Compute_1", "VideoDecode", "VideoEncode")), 1)}
    say = []
    if out["others_cpu_cores"] >= 1.0:
        say.append("ほかのアプリが CPU を約 " + f"{out['others_cpu_cores']:.1f} コア分使っている: " + "，".join(f"{x['name']} {x['cores']}" for x in others_cpu[:3]))
    if out["others_gpu_pct"] >= 5.0:
        say.append("ほかのアプリが GPU を使っている: " + "，".join(f"{x.get('name')}（{x.get('engine')}）{x['pct']}%" for x in others_gpu[:3]))
    out["say"] = say or ["CPU・GPU を大きく使っているほかのアプリは見当たらない"]
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a4 = sub.add_parser("watch")
    a4.add_argument("--sec", type=int, default=3)
    a1 = sub.add_parser("preflight")
    a1.add_argument("--pack", default="")
    a1.add_argument("--json", default="")
    a1.add_argument("--no-ssd", action="store_true")
    a2 = sub.add_parser("diagnose")
    a2.add_argument("--log", required=True)
    a2.add_argument("--from-byte", type=int, default=0)
    a2.add_argument("--json", default="")
    a3 = sub.add_parser("ssd")
    a3.add_argument("--pack", required=True)
    a = ap.parse_args()
    if a.cmd == "watch":
        d = watch(a.sec)
        if "error" in d:
            print(json.dumps(d, ensure_ascii=False))
        else:
            for line in d["say"]:
                print(line)
            print(json.dumps({k: d[k] for k in ("strata_cpu_cores", "strata_gpu", "others_cpu", "others_gpu")}, ensure_ascii=False))
        return 0
    if a.cmd == "ssd":
        print(json.dumps(ssd_probe(a.pack), ensure_ascii=False))
        return 0
    if a.cmd == "diagnose":
        d = diagnose(a.log, a.from_byte)
        if a.json:
            json.dump(d, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n".join(d.get("findings") or [d.get("error", "")]))
        return 0
    d = preflight(a.pack or None, not a.no_ssd)
    if a.json:
        json.dump(d, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if "error" in d:
        print(d["error"], d.get("raw", ""))
        return 3
    g = (d.get("gpus") or [{}])[0]
    print(f"CPU {d['cpu']['name']}（{d['cpu']['cores']} コア，いま {d['cpu']['busy_pct']}% 使用）／RAM {d['ram']['total_gib']} GiB・空き {d['ram']['avail_gib']} GiB"
          f"／GPU {g.get('name')}・VRAM の空き {g.get('vram_free_mib')} MiB・画面 {g.get('display_active')}・クロック {g.get('clock_mhz')} MHz・PCIe Gen{g.get('pcie_gen')} x{g.get('pcie_width')}")
    print(f"ページの読み込み {d['ram']['page_reads_per_s']} 回/秒，ディスクの読み {d['ram']['disk_read_mb_s']} MB/s，GPU から読める固定の上限 約 {d.get('pin_cap_gib')} GiB，HAGS {d['hags']}")
    print("設定の案:")
    for r in d["settings"]:
        print(f"  [{r['case']}] {r['pack']}: RAM の枠 {r['resident_budget_gib']} GiB・予約 {r['vram_reserve_mib']} MiB → SSD に残る {r['on_file_gib']} GiB（{r['on_file_pct']}%）")
    print(f"勧める pack: {d['recommended_pack']}")
    for x in d["advice"]:
        print(" ・" + x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
