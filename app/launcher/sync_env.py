#!/usr/bin/env python3
"""対応環境の調べとエンジンの種類の決め方（11/15 夜．本人「GTX 10 と Radeon も配布の前に組んで」で範囲を広げた）．

  sync env [--json]      調べの結果（setup も最後にこれを流す．setup は結果の engine で入れるエンジンの部品を 1 つ選ぶ）
  status --json の env，up の前（blockers があれば起こさない），doctor の出力に使う．

決まり（エンジンの担当の見立て．変えるのは下の表だけ）:
  - NVIDIA（nvidia-smi の compute_cap）: ENGINE_BY_CC の表で engine を決める．
      7.5 以上＝cuda13（7.5＝RTX 20・GTX 16 と 12 以上＝RTX 50 は「動く見込み・未確認」の注意．TURING は 1 か所で断るに戻せる），
      6.0〜7.4＝cuda12（Tesla P100・GTX 10・V100・Titan V．試験的．P100 は 11/18 に入れた）．それ以外は対応外．
      P100 を入れるとき（CUDA 12 のキットに sm_60 が入ったら）: ENGINE_BY_CC の (6.1, 7.5, ...) を (6.0, 7.5, ...) に，setup.sh の NV_TABLE の 6.1 7.5 を 6.0 7.5 に（gpu_p100 の断りは cc 6.0 が表に無いときだけ出るので残してよい）．ドライバーの下限は engine ごと（DRIVER_MIN）．
  - NVIDIA が無いとき Radeon（表示アダプターの名前．レジストリの表示アダプターの欄＝管理者なしで読める）: RADEON の表で
      RX 9000＝hip-rx9070，RX 7000＝hip-rdna3，RX 6000＝hip-rdna2（どれも試験的）．古い世代は対応外．
    内蔵の Radeon は対応外（Windows は 11/16 に決定．HIP の decode の最初で GPU が落ちる．Strix Halo＝Radeon 8060S などだけ Windows・Linux とも対応）．
    単体の Radeon と内蔵の両方がある PC は単体を使う（HIP の装置の番号は strata-device --list-devices で選ぶ＝hip_ordinal）．
    NVIDIA と Radeon の両方があるときは対応する NVIDIA（11/18 W8: NVIDIA が全部対応外のときだけ Radeon を見る）．
    GPU が複数のときは，対応する物の中で，試験的でない物を先に，その中で VRAM の大きい物（同じなら新しい世代）を 1 枚使う（このアプリは VRAM が大きいほど席が増えて速い）．
  - CPU に AVX2 が無い → 止める．AVX-512 が無いのは対応（doctor に 1 行）．
  - VRAM・RAM が推奨より少ない → 止めずに注意．
出すのは鍵と値（文は画面の側で訳す．CLI と setup は下の TEXTS）．結果の engine＝入れる・使うエンジンの部品（engine-<engine>）．
試すとき: 環境変数 SYNC_ENV_OVERRIDE に JSON で調べの結果を差し替える．例
  {"gpus": [], "adapters": []}（GPU なし）  {"gpus": [{"name": "GTX 1080", "cc": 6.1, "driver": 581.0, "vram_gib": 8}]}
  {"gpus": [], "adapters": [{"name": "AMD Radeon RX 7800 XT", "vram_gib": 16}]}  {"avx2": false}
"""
import ctypes, json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oscompat as OS  # noqa: E402  11/16 S2: Linux でも同じ調べ（RAM・CPU の機能・Radeon の見分けは OS ごと）

# ---- 表（ここだけを直す）
TURING = "warn"               # RTX 20・GTX 16（compute_cap 7.5）: "warn"＝動く見込み・未確認として通す／"block"＝断る（エンジンの担当の読み取りで問題が出たら）
# compute_cap の範囲 → (engine, 種類)．種類: ok＝対応／untested＝動く見込み・未確認／experimental＝試験的
ENGINE_BY_CC = [
    (12.0, 99.0, "cuda13", "untested"),     # RTX 50
    (8.6, 12.0, "cuda13", "ok"),            # RTX 30・40
    (8.0, 8.6, "cuda13", "untested"),       # A100・A30 など（11/16: キットに PTX sm_75・86 があり JIT で動く見込み．未確認）
    (7.5, 7.6, "cuda13", "turing"),         # RTX 20・GTX 16（TURING で切り替え）
    (6.0, 7.5, "cuda12", "experimental"),   # Tesla P100（6.0．11/18 本人の決定で試し．実機での生成は未確認）・GTX 10（6.1）・V100・Titan V（7.0）．11/18 W8: Volta を足した（本家 NVIDIA_V100.md．CUDA 12 のエンジン）
]                                           # 6.0（Tesla P100）は入れない＝対応外（CUDA 12 のキットは sm_61 と sm_70 だけで，sm_60 のコードは無い見込み．未確認）
# ドライバーの下限（版は「.」で分けて数で比べる．足りない部分は 0）．Linux は係 L の setup.sh の DRIVER_MIN と同じ（11/16 エンジン 3 の答え）．
DRIVER_MIN_WIN = {"cuda13": "580", "cuda12": "576.57"}   # 11/16: cu12 のキットは toolkit 12.9.1 で組む（その toolkit driver が Windows 576.57．GTX 10 は R580 まで対応）
DRIVER_MIN_LINUX = {"cuda13": "580.95.05", "cuda12": "575.57.08"}
DRIVER_MIN = DRIVER_MIN_WIN if os.name == "nt" else DRIVER_MIN_LINUX


def _ver(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v)))


def driver_ok(have, need):
    a, b = _ver(have), _ver(need)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) >= b + (0,) * (n - len(b))
# Radeon の名前 → engine（上から順に見る．内蔵の「Radeon(TM) Graphics」などはどれにも当たらない＝対応外）
RADEON = [
    (r"\bRX\s*9\d{3}[MS]?\b", "hip-rx9070"),     # 11/18 W8: ノート用の M・S 付き（RX 7600M・RX 6700S・RX 7600M XT）も
    (r"\bRX\s*7\d{3}[MS]?\b", "hip-rdna3"),
    (r"\bRX\s*6\d{3}[MS]?\b", "hip-rdna2"),
]
# Radeon の device ID の範囲 → engine（名前より先に見る．古い pci.ids の PC で名前が出なくても見分けられる）．
# 係 L の setup.sh の RADEON_IDS・AMD_IGPU_IDS と同じ表（s2/check_gpu_tables.py が食い違いを見る）
RADEON_IDS = [
    (0x7550, 0x755f, "hip-rx9070"), (0x7590, 0x759f, "hip-rx9070"),
    (0x7440, 0x745f, "hip-rdna3"), (0x7470, 0x747f, "hip-rdna3"), (0x7480, 0x749f, "hip-rdna3"),
    (0x73a0, 0x73bf, "hip-rdna2"), (0x73c0, 0x73df, "hip-rdna2"), (0x73e0, 0x73ff, "hip-rdna2"), (0x7420, 0x743f, "hip-rdna2"),
    (0x1586, 0x1586, "hip-rdna3"),      # 11/16: Strix Halo（Ryzen AI Max の内蔵 Radeon．gfx1151．Windows・Linux とも対応＝本人の決定．rdna3 のキットに gfx1151 が入っている）
]
AMD_IGPU_IDS = {0x15d8, 0x15dd, 0x1636, 0x1638, 0x164c, 0x15e7, 0x1681, 0x164e, 0x15bf, 0x15c8, 0x150e, 0x1506, 0x163f, 0x13c0}
# 11/16 係 S3: Windows の内蔵 Radeon（本人の決定）．HIP の decode の最初で GPU が落ちる（ホストと旗でやり取りする所が，メモリを共有する内蔵 GPU では動かない．
# 上流 docs/AMD_HIP.md 134・140〜141 行）．対応する内蔵は Strix Halo（gfx1151．Radeon 8060S・8050S・8040S．rdna3 のキットに gfx1151 が入っている）だけ．
# 下の表は Windows だけ（Linux は setup.sh と同じ AMD_IGPU_IDS のまま．check_gpu_tables.py は AMD_IGPU_IDS だけ setup.sh と照らす）．Strix Halo は両 OS で対応（RADEON_IDS に入れた．IGPU_OK_* は内蔵の印と名前の見分け用）
AMD_IGPU_IDS_WIN_EXTRA = {0x164f, 0x1900, 0x1901, 0x1114, 0x1902}   # Phoenix・Hawk Point の別の型，Krackan Point（上の表にある物に足す）
IGPU_OK_WIN = {0x1586: "hip-rdna3"}                                 # Strix Halo
IGPU_OK_NAME = r"radeon\s*(\(tm\))?\s*80[456]0s"                    # ID が取れない PC 用
IGPU_NAME_RE = (r"radeon\s*(\(tm\))?\s*graphics|radeon graphics|vega \d+ graphics"
                r"|radeon\s*(\(tm\))?\s*\d{3}m\b")                      # 型番の無い名前，780M・890M・680M など
HIP_IGPU_ARCHS = {"gfx1035", "gfx1036", "gfx1037", "gfx1103", "gfx1150", "gfx1151", "gfx1152", "gfx90c"}   # strata-device の arch で内蔵と見る物
VRAM_WARN_GIB, RAM_WARN_GIB = 12, 32   # 11/15 本人: 推奨は RAM 32 GB・VRAM 12 GB．それ未満は注意
EXIT_UNSUPPORTED = 8          # up の終了コード（対応外）

TEXTS = {   # 鍵 → (英語, 日本語, 中国語)．{gpu} などは値で埋める
    "no_gpu": ("No supported GPU was found. An NVIDIA GTX 10 series or newer, or an AMD Radeon RX 6000 series or newer is needed.",
               "対応する GPU が見つかりません。NVIDIA の GTX 10 シリーズ以降か、Radeon の RX 6000 シリーズ以降が必要です。",
               "未找到支持的显卡。需要 NVIDIA GTX 10 系列或更新，或 AMD Radeon RX 6000 系列或更新。"),
    "gpu_too_old": ("This GPU ({gpu}) is not supported. An NVIDIA GTX 10 series or newer, or a Radeon RX 6000 series or newer is needed.",
                    "この GPU（{gpu}）には対応していません。NVIDIA の GTX 10 シリーズ以降か、Radeon の RX 6000 シリーズ以降が必要です。",
                    "不支持此显卡（{gpu}）。需要 NVIDIA GTX 10 系列或更新，或 Radeon RX 6000 系列或更新。"),
    "gpu_p100": ("This GPU ({gpu}) is not supported. The CUDA 12 engine has no code for the Tesla P100 (compute capability 6.0).",
                 "この GPU（{gpu}）には対応していません。CUDA 12 版のエンジンに Tesla P100（compute capability 6.0）向けのコードが入っていません。",
                 "不支持此显卡（{gpu}）。CUDA 12 版引擎不含面向 Tesla P100（compute capability 6.0）的代码。"),
    "igpu_only": ("Built-in graphics ({gpu}) are not supported. A separate NVIDIA or Radeon graphics card is needed.",
                  "内蔵の GPU（{gpu}）には対応していません。NVIDIA か Radeon のグラフィックボードが必要です。",
                  "不支持集成显卡（{gpu}）。需要 NVIDIA 或 Radeon 独立显卡。"),
    "gpu_turing_pending": ("Support for the RTX 20 series ({gpu}) is still being checked.",
                           "RTX 20 シリーズ（{gpu}）への対応は確認中です。",
                           "对 RTX 20 系列（{gpu}）的支持仍在确认中。"),
    "driver_old": ("Please update the NVIDIA driver (now {driver}; {need} or later is needed).",
                   "NVIDIA のドライバーを更新してください（今は {driver}、{need} 以降が必要です）。",
                   "请更新 NVIDIA 驱动（当前 {driver}，需要 {need} 或更高版本）。"),
    "no_avx2": ("This CPU does not support AVX2, which is required.",
                "この CPU は AVX2 に対応していないため使えません。",
                "此 CPU 不支持 AVX2，无法使用。"),
    "gpu_untested": ("This GPU ({gpu}) should work, but it has not been tested yet.",
                     "この GPU（{gpu}）は動く見込みですが、まだ確認していません。",
                     "此显卡（{gpu}）预计可以运行，但尚未经过验证。"),
    "gpu_experimental": ("Support for this GPU ({gpu}) is experimental. It has not been tested on a real PC.",
                         "この GPU（{gpu}）への対応は試験的な機能です。実機では確認していません。",
                         "对此显卡（{gpu}）的支持是实验性功能，尚未在实机上验证。"),
    "vram_too_small": ("The GPU has only {vram_gib} GB of memory, which is not enough to run the engine. A GPU with {need} GB or more is needed.",
                       "GPU のメモリが {vram_gib} GB しかなく、エンジンを動かせません。{need} GB 以上の GPU が必要です。",
                       "显卡显存只有 {vram_gib} GB，无法运行引擎。需要 {need} GB 以上的显卡。"),
    "vram_low": ("The GPU has only {vram_gib} GB of memory, so it may be slow (12 GB or more is recommended).",
                 "GPU のメモリが {vram_gib} GB と少ないため、遅くなることがあります（12 GB 以上を推奨）。",
                 "显卡显存只有 {vram_gib} GB，可能较慢（建议 12 GB 以上）。"),
    "vram_unknown": ("The amount of GPU memory could not be read. Settings will be on the safe side.",
                     "GPU のメモリの量を読めませんでした。設定は控えめにします。",
                     "无法读取显存容量，将使用保守的设置。"),
    "ram_low": ("This PC has only {ram_gib} GB of memory, so it may be slow (32 GB or more is recommended).",
                "PC のメモリが {ram_gib} GB と少ないため、遅くなることがあります（32 GB 以上を推奨）。",
                "电脑内存只有 {ram_gib} GB，可能较慢（建议 32 GB 以上）。"),
    "no_avx512": ("This CPU has no AVX-512. It works, but expect it to be about 10% slower.",
                  "この CPU は AVX-512 に対応していません。動きますが、1 割ほど遅くなる見込みです。",
                  "此 CPU 不支持 AVX-512。可以运行，但预计会慢约 10%。"),
}


def text(item, lang="ja"):
    t = TEXTS[item["key"]][{"en": 0, "ja": 1, "zh": 2}[lang]]
    try:
        return t.format(**item)
    except (KeyError, IndexError):
        return t


def _nvidia():
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=name,compute_cap,driver_version,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10, creationflags=0x08000000)
    except (OSError, subprocess.TimeoutExpired):
        return []
    gpus = []
    for i, l in enumerate(o.stdout.strip().splitlines()):     # 11/18: i は nvidia-smi の番号（GPU が複数のとき，選んだ GPU でエンジンを起こすため）
        p = [x.strip() for x in l.split(",")]
        if len(p) < 4:
            continue
        try:
            gpus.append({"name": p[0], "cc": float(p[1]), "driver": p[2],
                         "vram_gib": round(float(p[3]) / 1024, 1), "index": i})
        except ValueError:
            continue
    return gpus


def _adapters_linux():
    """Linux: /sys/class/drm/card*/device の vendor（0x1002＝AMD）と，名前（lspci か rocm-smi），VRAM（amdgpu の mem_info_vram_total）．
    どれも管理者なしで読める．読めない値は None（不明）"""
    out = []
    base = "/sys/class/drm"
    try:
        cards = sorted(d for d in os.listdir(base) if re.fullmatch(r"card\d+", d))
    except OSError:
        return out
    names = {}
    try:
        o = subprocess.run(["lspci", "-mm", "-D"], capture_output=True, text=True, timeout=8).stdout
        for l in o.splitlines():
            m = re.match(r'^(\S+)\s+"([^"]*)"\s+"([^"]*)"\s+"([^"]*)"', l)
            if m and re.search(r"VGA|Display|3D", m.group(2)):
                names[m.group(1).lower()] = f"{m.group(3)} {m.group(4)}"
    except (OSError, subprocess.TimeoutExpired):
        pass
    for c in cards:
        dev = os.path.join(base, c, "device")
        try:
            vendor = open(os.path.join(dev, "vendor")).read().strip().lower()
        except OSError:
            continue
        slot = os.path.basename(os.path.realpath(dev)).lower()
        name = names.get(slot)
        if not name:
            try:
                name = open(os.path.join(dev, "product_name")).read().strip()
            except OSError:
                name = None
        if vendor == "0x1002" and not name:
            try:
                o = subprocess.run(["rocm-smi", "--showproductname", "--json"], capture_output=True, text=True, timeout=8).stdout
                j = json.loads(o or "{}")
                name = next((v.get("Card series") or v.get("Card model") for v in j.values() if isinstance(v, dict)), None)
            except Exception:
                name = None
        vram = None
        try:
            vram = round(int(open(os.path.join(dev, "mem_info_vram_total")).read()) / 1024 ** 3, 1)
        except (OSError, ValueError):
            pass
        vend = {"0x1002": "AMD", "0x10de": "NVIDIA", "0x8086": "Intel"}.get(vendor, vendor)
        try:
            dev_id = int(open(os.path.join(dev, "device")).read().strip(), 16)
        except (OSError, ValueError):
            dev_id = None
        nm = name or f"{vend} GPU" + (f" ({dev_id:#06x})" if dev_id is not None else "")
        if vendor == "0x1002" and "radeon" not in nm.lower() and "amd" not in nm.lower():
            nm = "AMD " + nm
        out.append({"name": nm, "vram_gib": vram, "vendor_id": vendor, "device_id": dev_id})
    return out


def _adapters():
    """表示アダプターの名前と VRAM（Windows: レジストリの表示アダプターのクラスの欄．管理者なしで読める．VRAM は qwMemorySize，無ければ不明）"""
    if not OS.IS_WIN:
        return _adapters_linux()
    out = []
    try:
        import winreg
        cls = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cls) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                if not re.fullmatch(r"\d{4}", sub):
                    continue
                try:
                    with winreg.OpenKey(k, sub) as s:
                        name = winreg.QueryValueEx(s, "DriverDesc")[0]
                        dev_id, ven = None, None
                        try:
                            mid = winreg.QueryValueEx(s, "MatchingDeviceId")[0]
                            m = re.search(r"ven_([0-9a-f]{4}).*?dev_([0-9a-f]{4})", mid, re.I)
                            if m:
                                ven, dev_id = "0x" + m.group(1).lower(), int(m.group(2), 16)
                        except OSError:
                            pass
                        vram = None
                        try:
                            v = winreg.QueryValueEx(s, "HardwareInformation.qwMemorySize")[0]
                            vram = round(int.from_bytes(v, "little") / 1024 ** 3, 1) if isinstance(v, bytes) else round(int(v) / 1024 ** 3, 1)
                        except OSError:
                            pass
                        out.append({"name": name, "vram_gib": vram, "vendor_id": ven, "device_id": dev_id})
                except OSError:
                    continue
    except Exception:
        pass
    return out


def _ram_gib():
    return round(OS.mem_gib()[0], 1)


_cache = None


def probe():
    global _cache
    if _cache is not None and not os.environ.get("SYNC_ENV_OVERRIDE"):
        return _cache
    avx2, avx512 = OS.cpu_flags()
    facts = {"gpus": _nvidia(), "avx2": avx2, "avx512": avx512, "ram_gib": _ram_gib(), "os": "windows" if OS.IS_WIN else "linux"}
    try:
        ov = json.loads(os.environ.get("SYNC_ENV_OVERRIDE") or "{}")
    except ValueError:
        ov = {}
    if "ram_gib" not in ov:      # 11/17 G（項目 3）: 「32 GB」の PC は見える量が 30.9 GiB などになる．少ないかの判定は積んでいる量で（取れなければ見える量）
        try:
            inst = OS.installed_mem_gib()
            if inst:
                facts["ram_installed_gib"] = inst
        except Exception:
            pass
    facts.update(ov)
    if "adapters" not in facts:
        facts["adapters"] = _adapters()     # 11/18 W8: NVIDIA があっても Radeon を調べる（NVIDIA が全部対応外のとき Radeon を使うため．pick_gpu は対応する NVIDIA を先に選ぶ）
    _cache = facts
    return facts


def _dev_id(a):
    d = a.get("device_id")
    if isinstance(d, str):
        try:
            return int(d, 16)
        except ValueError:
            return None
    return d


def amd_class(a, win):
    """AMD の装置 1 つの見分け．返り値 (engine か None, 種類 experimental|igpu|too_old, 内蔵か)．
    device ID の表を先に（名前が出ない PC でも見分ける）→ 名前．Strix Halo は両 OS で対応，ほかの内蔵は対応外（Windows はさらに AMD_IGPU_IDS_WIN_EXTRA）．"""
    d, name = _dev_id(a), a.get("name", "")
    if d is not None:
        if d in IGPU_OK_WIN:                      # Strix Halo は内蔵の印を付けて対応（単体の Radeon があればそちらを先に使う）
            return IGPU_OK_WIN[d], "experimental", True
        for lo, hi, eng in RADEON_IDS:
            if lo <= d <= hi:
                return eng, "experimental", False
        if d in AMD_IGPU_IDS or (win and d in AMD_IGPU_IDS_WIN_EXTRA):
            return None, "igpu", True
    for pat, eng in RADEON:
        if re.search(pat, name, re.I):
            return eng, "experimental", False
    if re.search(IGPU_OK_NAME, name, re.I):
        return "hip-rdna3", "experimental", True
    if re.search(IGPU_NAME_RE, name, re.I):      # 型番の無い「AMD Radeon(TM) Graphics」は内蔵だけが使う名前．単体は「RX …」「PRO W…」「AI PRO …」
        return None, "igpu", True
    return None, "too_old", False                # 番号でも名前でも型が分からない AMD は一覧に出すが対応外


def _pick_nvidia(gpus):
    """NVIDIA の中で使う 1 枚．対応するか → 試験的でない物を先に → VRAM → 世代 cc の順（11/18 W8: 前は世代が先．このアプリは VRAM が大きいほど速い．
    試験的（GTX 10・V100 など）は，試験的でない物（RTX 20 以降）があればそちらを先に．試験的な物しか無ければ VRAM → cc）"""
    def rank(g):
        cc = float(g.get("cc", 0))
        kinds = [k for lo, hi, _, k in ENGINE_BY_CC if lo <= cc < hi]
        return (bool(kinds), bool(kinds) and kinds[0] != "experimental", float(g.get("vram_gib") or 0), cc)
    g = max(gpus, key=rank)
    cc = float(g.get("cc", 0))
    for lo, hi, eng, kind in ENGINE_BY_CC:
        if lo <= cc < hi:
            return dict(g, vendor="nvidia"), eng, kind
    return dict(g, vendor="nvidia"), None, "too_old"


def _pick_radeon(f):
    """Radeon の中で使う 1 枚（Radeon が無ければ None）"""
    ads = [a for a in f.get("adapters") or [] if a.get("vendor_id") == "0x1002" or re.search(r"radeon|\bamd\b", a.get("name", ""), re.I)]
    if not ads:
        return None
    # 11/16 係 S3: 装置ごとに見分けて，対応する物があればその中で単体（内蔵でない物）を先に，次に VRAM の大きい物．
    # 対応する物が無ければ，内蔵（対応外の理由は igpu_only）→ 分からない AMD（gpu_too_old）の順．前は内蔵が先に並ぶと単体を見ずに断っていた
    win = f.get("os", "windows" if os.name == "nt" else "linux") == "windows"
    cls = [(a,) + amd_class(a, win) for a in ads]
    ok = [c for c in cls if c[1]]
    if ok:
        a, eng, kind, integrated = max(ok, key=lambda c: (not c[3], float(c[0].get("vram_gib") or 0)))
        return dict(a, vendor="amd", integrated=integrated), eng, kind
    for want in ("igpu", "too_old"):
        for a, eng, kind, integrated in cls:
            if kind == want:
                return dict(a, vendor="amd", integrated=integrated), None, kind
    return dict(ads[0], vendor="amd"), None, "too_old"


def pick_gpu(f):
    """使う GPU と engine．返り値 (gpu の辞書, engine か None, 種類 ok|untested|turing|experimental|too_old|igpu|none)．
    11/18 W8: 対応する NVIDIA があればそれ（VRAM の大きい物）．NVIDIA が全部対応外のときは，対応する Radeon があればそれ．
    どちらも無ければ NVIDIA の断り（NVIDIA が無ければ Radeon の断り）"""
    gpus = f.get("gpus") or []
    nv = _pick_nvidia(gpus) if gpus else None
    if nv and nv[1]:
        return nv
    rd = _pick_radeon(f)
    if rd and rd[1]:
        return rd
    return nv or rd or (None, None, "none")


def parse_hip_devices(text):
    """`strata-device --list-devices` の出力 → [{index, name, arch, vram_gb, integrated, cannot_run}]（上流 serve/server.py の parse_hip_devices と同じ見方．
    形: 「device 0: 名前」の行の後ろに「arch gfx1036, 2.0 GiB[, integrated]」「cannot run: 理由」）"""
    found = []
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"device\s+(\d+):\s*(.*)$", s)
        if m:
            found.append({"index": int(m.group(1)), "name": m.group(2).strip(), "arch": "", "vram_gb": 0.0, "integrated": False, "cannot_run": None})
            continue
        if not found:
            continue
        a = re.match(r"arch\s+(gfx[0-9a-f]+)\s*,\s*([\d.]+)\s*GiB(.*)$", s)
        if a and not found[-1]["arch"]:
            found[-1]["arch"], found[-1]["vram_gb"] = a.group(1), float(a.group(2))
            found[-1]["integrated"] = "integrated" in a.group(3)
        elif s.startswith("cannot run:"):
            found[-1]["cannot_run"] = s[len("cannot run:"):].strip()
    for d in found:
        d["integrated"] = d["integrated"] or d["arch"] in HIP_IGPU_ARCHS
    return found


def pick_hip_ordinal(devices):
    """HIP の装置の番号（内蔵 Radeon があると内蔵が 0 で単体は 1 にずれる＝上流 #325）．動かせる物の中で単体（内蔵でない）を先に，次に VRAM の大きい物．
    返り値 None＝選べない（呼ぶ側は何も変えない）"""
    runnable = [d for d in devices if not d["cannot_run"]]
    if not runnable:
        return None
    pool = [d for d in runnable if not d["integrated"]] or runnable
    return max(pool, key=lambda d: (round(d["vram_gb"]), -d["index"]))["index"]


def hip_ordinal(engine_exe, lib_dirs=None):
    """キットの strata-device --list-devices を流して，使う HIP の装置の番号を返す（流せない・出力が読めないときは None）．軽い（GPU の計算はしない）"""
    probe = os.path.join(os.path.dirname(engine_exe), "strata-device.exe" if os.name == "nt" else "strata-device")
    if not os.path.isfile(probe):
        return None
    env = dict(os.environ)
    var = "PATH" if os.name == "nt" else "LD_LIBRARY_PATH"
    dirs = [d for d in (lib_dirs or []) if os.path.isdir(d)]
    if dirs:
        env[var] = os.pathsep.join(dirs + ([env[var]] if env.get(var) else []))
    try:
        r = subprocess.run([probe, "--list-devices"], capture_output=True, text=True, timeout=60, cwd=os.path.dirname(probe), env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return pick_hip_ordinal(parse_hip_devices(r.stdout)) if r.returncode == 0 else None


def _min_vram_gib():
    import wintune      # 固定の VRAM・席の大きさ・最小の席の数は wintune の値（約 7.04）
    return wintune.min_vram_gib()


def check(facts=None):
    f = facts or probe()
    blockers, warnings = [], []
    g, eng, kind = pick_gpu(f)
    name = (g or {}).get("name", "")
    if kind == "none":
        blockers.append({"key": "no_gpu"})
    elif kind == "igpu":
        blockers.append({"key": "igpu_only", "gpu": name})
    elif kind == "too_old" and (g or {}).get("vendor") == "nvidia" and 6.0 <= float(g.get("cc") or 0) < 6.1:
        blockers.append({"key": "gpu_p100", "gpu": name})      # 11/18 W8: Tesla P100（cc 6.0）は理由つきで断る
    elif kind == "too_old":
        blockers.append({"key": "gpu_too_old", "gpu": name})
    elif kind == "turing":
        if TURING == "block":
            blockers.append({"key": "gpu_turing_pending", "gpu": name})
        else:
            warnings.append({"key": "gpu_untested", "gpu": name})
    elif kind == "untested":
        warnings.append({"key": "gpu_untested", "gpu": name})
    elif kind == "experimental":
        warnings.append({"key": "gpu_experimental", "gpu": name})
    if g and g.get("vendor") == "nvidia" and eng and not driver_ok(g.get("driver", "0"), DRIVER_MIN.get(eng, "0")):
        blockers.append({"key": "driver_old", "driver": g.get("driver"), "need": DRIVER_MIN[eng]})
    if g and eng:
        if g.get("vram_gib") is None:
            warnings.append({"key": "vram_unknown"})
        elif float(g["vram_gib"]) < _min_vram_gib():      # 11/18 W7: 席が最小の数に届かない VRAM は，起動を試す前に止める
            blockers.append({"key": "vram_too_small", "vram_gib": g.get("vram_gib"), "need": int(-(-_min_vram_gib() // 1))})
        elif float(g["vram_gib"]) + 0.5 < VRAM_WARN_GIB:
            warnings.append({"key": "vram_low", "vram_gib": g.get("vram_gib")})
    if not f.get("avx2", True):
        blockers.append({"key": "no_avx2"})
    if float(f.get("ram_installed_gib") or (float(f.get("ram_gib") or 0) + 1)) < RAM_WARN_GIB:   # 11/17: 積んでいる量（無ければ見える量 + 1）
        warnings.append({"key": "ram_low", "ram_gib": f.get("ram_gib")})
    notes = [] if f.get("avx512", True) else [{"key": "no_avx512"}]
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "notes": notes,
            "engine": eng, "gpu": {"name": name, "vendor": (g or {}).get("vendor"), "kind": kind,
                                                              "vram_gib": (g or {}).get("vram_gib"), "engine": eng,
                                                              # 11/19 0.1.2: 選んだ NVIDIA の GPU の nvidia-smi の番号．前は返しておらず，
                                                              # sync_launch の「選んだ GPU を先頭に・エンジンをその番号で」が働かず，
                                                              # GPU が 2 枚の PC でいつも 0 番で動いた（4060＋3060 で 3060 を選んでも 4060）
                                                              "index": (g or {}).get("index") if (g or {}).get("vendor") == "nvidia" else None},
            "facts": f}


def cmd_env(argv):
    r = check()
    if "--json" in argv:
        for it in r["blockers"] + r["warnings"] + r["notes"]:
            it["text"] = text(it)          # 日本語の文（setup と CLI 用．画面は鍵で訳す）
        print(json.dumps(r, ensure_ascii="--ascii" in argv))
        return 0 if r["ok"] else EXIT_UNSUPPORTED
    print("この PC で使えます。" if r["ok"] else "この PC では使えません。")
    if r["engine"]:
        print(f"  エンジン: {r['engine']}（{r['gpu']['name']}）")
    for it in r["blockers"]:
        print("  × " + text(it))
    for it in r["warnings"] + r["notes"]:
        print("  ！ " + text(it))
    return 0 if r["ok"] else EXIT_UNSUPPORTED


if __name__ == "__main__":
    sys.exit(cmd_env(sys.argv[1:]))
