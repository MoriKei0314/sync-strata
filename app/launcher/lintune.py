#!/usr/bin/env python3
"""wintune.py の Linux の部分（11/16 係 S2．Linux 版の配布のため）．管理者の権限は要らない．

wintune.preflight は Windows では PowerShell の調べ（PS_PROBE）の結果を読む．Linux ではこの probe() が同じ形の辞書を作り，
その先（pack ごとの枠の見積もり・勧め）は wintune の同じコードを通る．
  - RAM: /proc/meminfo（MemAvailable を空きに．ページキャッシュ Cached・hugepages も記録）
  - ページの読み込み: /proc/vmstat の pgmajfault の 1 秒あたり（Windows の Page Reads/sec に当たる）
  - スワップ: /proc/swaps（Windows のページファイルに当たる）
  - プロセス: /proc/*/status の VmRSS（名前ごとにまとめる．閉じると戻る RAM の見積もり）
  - CPU の使用率: /proc/stat を 1 秒あけて 2 回
  - 表示アダプター: sync_env の Linux の調べ（/sys/class/drm と lspci）
watch(): いま CPU を使っているほかのプロセス（/proc/*/stat の utime＋stime の増え方）．GPU はプロセスごとの使用率を読まない．
page_reads(): (ページの読み込みの回数/秒, 空き MiB)．
"""
import os, re, time

HZ = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def _meminfo():
    kv = {}
    for line in open("/proc/meminfo"):
        k, _, v = line.partition(":")
        kv[k] = int(v.split()[0])          # kB
    return kv


def _vmstat(key):
    for line in open("/proc/vmstat"):
        k, v = line.split()
        if k == key:
            return int(v)
    return 0


def page_reads(sec=1.0):
    a = _vmstat("pgmajfault")
    time.sleep(sec)
    b = _vmstat("pgmajfault")
    return (b - a) / sec, _meminfo().get("MemAvailable", 0) / 1024


def _cpu_busy(sec=1.0):
    def snap():
        p = [int(x) for x in open("/proc/stat").readline().split()[1:]]
        return sum(p), p[3] + (p[4] if len(p) > 4 else 0)
    t0, i0 = snap()
    time.sleep(sec)
    t1, i1 = snap()
    return 100.0 * (1 - (i1 - i0) / max(1, t1 - t0))


def _procs():
    agg = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            st = open(f"/proc/{d}/status", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        name = re.search(r"^Name:\s*(.+)$", st, re.M)
        rss = re.search(r"^VmRSS:\s*(\d+)", st, re.M)
        if not name or not rss:
            continue
        n = name.group(1).strip()
        x = agg.setdefault(n, {"name": n, "n": 0, "ws": 0, "priv": 0})
        x["n"] += 1
        x["ws"] += int(rss.group(1)) * 1024
        x["priv"] += int(rss.group(1)) * 1024
    return sorted(agg.values(), key=lambda x: -x["priv"])[:40]


def probe():
    """wintune の PS_PROBE と同じ形の辞書"""
    mi = _meminfo()
    pr0 = _vmstat("pgmajfault")
    busy = _cpu_busy(1.0)
    pr = _vmstat("pgmajfault") - pr0
    cpu, threads, cores = "", os.cpu_count(), None
    try:
        txt = open("/proc/cpuinfo").read()
        m = re.search(r"^model name\s*:\s*(.+)$", txt, re.M)
        cpu = m.group(1) if m else ""
        cores = len({(a, b) for a, b in re.findall(r"physical id\s*:\s*(\d+).*?core id\s*:\s*(\d+)", txt, re.S)}) or None
    except OSError:
        pass
    swaps = []
    try:
        for l in open("/proc/swaps").read().splitlines()[1:]:
            p = l.split()
            swaps.append({"path": p[0], "alloc_mb": int(p[2]) // 1024, "used_mb": int(p[3]) // 1024})
    except OSError:
        pass
    video = []
    try:
        import sync_env
        video = [{"name": a.get("name")} for a in sync_env._adapters_linux()]
    except Exception:
        pass
    osname = ""
    try:
        osname = re.search(r'^PRETTY_NAME="?([^"\n]+)', open("/etc/os-release").read(), re.M).group(1)
    except (OSError, AttributeError):
        pass
    G = 1024 ** 3
    counters = {"\\memory\\page reads/sec": pr, "\\memory\\available mbytes": mi.get("MemAvailable", 0) / 1024,
                "\\memory\\committed bytes": mi.get("Committed_AS", 0) * 1024, "\\memory\\commit limit": mi.get("CommitLimit", 0) * 1024,
                "\\physicaldisk(_total)\\disk read bytes/sec": 0, "\\processor(_total)\\% processor time": busy}
    return {"os": osname or "Linux", "build": os.uname().release, "ram_total_kb": mi.get("MemTotal", 0), "ram_free_kb": mi.get("MemFree", 0),
            "cpu": cpu, "cores": cores, "threads": threads, "pagefiles": swaps, "dimms": [], "video": video, "disks": [], "parts": [],
            "procs": _procs(), "counters": counters, "hags": None, "power_plan": None,
            "linux": {"page_cache_gib": round(mi.get("Cached", 0) * 1024 / G, 2), "hugepages_total": mi.get("HugePages_Total", 0),
                      "hugepages_free": mi.get("HugePages_Free", 0), "hugepage_kb": mi.get("Hugepagesize", 0),
                      "swappiness": _read("/proc/sys/vm/swappiness"), "thp": _read("/sys/kernel/mm/transparent_hugepage/enabled")}}


def _read(p):
    try:
        return open(p).read().strip()
    except OSError:
        return None


def watch(sec=3):
    def snap():
        out = {}
        for d in os.listdir("/proc"):
            if d.isdigit():
                try:
                    st = open(f"/proc/{d}/stat", encoding="utf-8", errors="replace").read()
                    name = st[st.index("(") + 1:st.rindex(")")]
                    f = st[st.rindex(")") + 2:].split()
                    out[int(d)] = (name, int(f[11]) + int(f[12]))
                except (OSError, ValueError, IndexError):
                    continue
        return out
    a = snap()
    time.sleep(sec)
    b = snap()
    cpu = {}
    for pid, (name, t) in b.items():
        if pid in a and a[pid][0] == name:
            d = (t - a[pid][1]) / HZ / sec
            if d > 0.02:
                cpu[name] = cpu.get(name, 0.0) + d
    mine = ("strata", "python", "python3", "bash", "sh", "node", "dsh-node", "claude")
    others = sorted(({"name": k, "cores": round(v, 2)} for k, v in cpu.items() if k.lower() not in mine), key=lambda x: -x["cores"])
    out = {"sec": sec, "logical": os.cpu_count(), "strata_cpu_cores": round(cpu.get("strata", 0.0), 2), "strata_gpu": [],
           "others_cpu": others[:6], "others_gpu": [], "others_cpu_cores": round(sum(x["cores"] for x in others), 2), "others_gpu_pct": 0.0}
    say = []
    if out["others_cpu_cores"] >= 1.0:
        say.append(f"ほかのアプリが CPU を約 {out['others_cpu_cores']:.1f} コア分使っている: " + "，".join(f"{x['name']} {x['cores']}" for x in others[:3]))
    out["say"] = say or ["CPU を大きく使っているほかのアプリは見当たらない（GPU のプロセスごとの使用率は Linux では読まない）"]
    return out
