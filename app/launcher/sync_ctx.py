#!/usr/bin/env python3
"""コンテキストの設定（11/15 係 C．本人の指示: VRAM 8 GB のカードでは 262K の文脈が入らない見込み）．

設定 settings.json の 2 項目（どちらも値か "auto"．既定は auto）:
  context    最大コンテキスト長 32768・65536・131072・262144（"32k"・"64k"・"128k"・"256k" も受ける）
  kv_format  会話の記憶（K/V）の量子化．エンジンの名前 k8v4・int8・q4_0（画面と CLI の呼び名 k8v4・k8・k4 も受ける）
組（コンテキスト×量子化）ごとに ok・注意・選ばせないを決める（数字は「選べる／注意／選ばせない」の節の 1 か所．実測で替える）．自動は ok の中から選ぶ．K/V を RAM に置く --kv-streaming は自動でも選ばず，設定にも出さない．

この道具がすること（sync_home・sync_launch・sync.py への差し込みは呼び出しの数行だけ．install_ctx.py が入れる）:
  - install(H): sync_home.SCHEMA の context を差し替え，kv_format を足す（auto の値＝この PC の VRAM で resolve() が決める組）．effective・settings_set を包み，選ばせない組は断る．
  - エンジンへ: --max-context N・--kv FORMAT（sync_launch.make_config．--kv-grow はひな形のまま）．
  - dsh へ: cordis.patch.yml のモデルの maxTokens を DSH_TABLE に（fit_patch），要約の始まり（compaction-basic）は
    起動のたびに dsh の --dump-config から preset-* の塊を写して直した上書き（SYNC_HOME\\run\\dsh-ctx.patch.yml）を --patch で渡す（dsh_cmd）．
    本人の日常の dsh の設定（作業場の dsh の home）は読み書きしない（dsh_home は SYNC_HOME の下）．
  - 起動の記録から「WARNING: past N cells the K/V needs more VRAM than the cache can give」を拾い，N を「止まらずに使える長さ」として出す．
  - sync ctx [--json]: いまの設定・自動の値・選べる値・動いているエンジンの値・使える長さ（画面の「コンテキスト設定」が読む）．
"""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oscompat  # noqa: E402,F401  11/16 S2: Linux では creationflags を外す

CTX_CHOICES = (32768, 65536, 131072, 262144)
KV_CHOICES = ("k8v4", "int8", "q4_0")                 # エンジンの名前（設定に入る値）
KV_ALIAS = {"k8v4": "k8v4", "int8": "int8", "k8": "int8", "q4_0": "q4_0", "k4": "q4_0"}
KV_LABEL = {"k8v4": "k8v4", "int8": "k8", "q4_0": "k4"}   # 画面の呼び名

# dsh の表: context → (モデル 1 回の出力の上限 maxTokens, 要約の余白 headroomTokens, 要約 1 回の長さの上限)．
# 要約が始まる長さ＝min(context×THRESHOLD_RATIO, context − maxTokens − headroom)（dsh-compaction-basic の式）．
# 配布のひな形は余白が dsh の既定 65536 のままで，131072 以下では要約が設定エラーになる（context − maxTokens − 65536 ≤ 0）ため上書きする．
DSH_TABLE = {
    32768: (8192, 4096, 4096),      # 要約は 20480 から
    65536: (16384, 8192, 8192),     # 40960 から
    131072: (32768, 8192, 16384),   # 90112 から
    262144: (65536, 8192, 32768),   # 188416 から
}
THRESHOLD_RATIO = 0.9
KV_WARN = re.compile(r"WARNING: past (\d+) cells the K/V needs more VRAM than the cache can give")


# ------------------------------------------------------------------ 値の検め方
def parse_context(v):
    s = str(v).strip().lower()
    m = re.fullmatch(r"(\d+)k", s)
    x = int(m.group(1)) * 1024 if m else int(float(s))
    if x not in CTX_CHOICES:
        raise ValueError("・".join(str(c) for c in CTX_CHOICES) + " のどれか")
    return x


def parse_kv(v):
    k = KV_ALIAS.get(str(v).strip().lower())
    if not k:
        raise ValueError("k8v4・k8・k4 のどれか")
    return k


# ------------------------------------------------------------------ 選べる／注意／選ばせない（11/15 夜．8 GB 相当の実測から）
# 数字はここだけ．実測が出たら替える．
# K/V の大きさ（GiB）: k8v4 の値 × 量子化ごとの倍率（int8＝k8v4 の 1.3 倍，q4_0＝int8 の半分）
KV_GIB_K8V4 = {32768: 0.36, 65536: 0.68, 131072: 1.32, 262144: 2.65}
KV_FACTOR = {"k8v4": 1.0, "int8": 1.3, "q4_0": 0.65}
# その PC で K/V に回せる量の目安 room ≒ VRAM(GiB) − ROOM_MINUS_GIB（8 GB で約 1，12 GB で約 5．2 点からの仮の目安）
ROOM_MINUS_GIB = 7.0
OK_FRAC = 0.6        # K/V ≤ 0.6×room は ok
WARN_FRAC = 0.95     # ≤ 0.95×room は注意，それより大きいと選ばせない
FALLBACK = (32768, "k8v4")   # VRAM が分からないとき（判定はせず，全部を ok として出す）
KV_PREF = ("k8v4", "q4_0", "int8")   # 量子化を自動で選ぶときの順（コンテキストを決めたとき）


def kv_gib(ctx, kv):
    base = KV_GIB_K8V4.get(int(ctx)) or 2.65 * int(ctx) / 262144
    return round(base * KV_FACTOR[kv], 3)


def room_gib(vram):
    return None if not vram else round(float(vram) - ROOM_MINUS_GIB, 2)


def fit(ctx, kv, vram):
    """ok｜warn｜block（VRAM が分からなければ ok）"""
    room = room_gib(vram)
    if room is None:
        return "ok"
    g = kv_gib(ctx, kv)
    if g <= OK_FRAC * room:
        return "ok"
    if g <= WARN_FRAC * room:
        return "warn"
    return "block"


def combos(vram):
    return [{"context": c, "kv_format": k, "label": f"{c // 1024}K・{KV_LABEL[k]}", "kv_gib": kv_gib(c, k), "status": fit(c, k, vram)}
            for c in CTX_CHOICES for k in KV_CHOICES]


def resolve(ctx_set, kv_set, vram):
    """設定（値か "auto"）の組から，使う組を決める．
    両方 auto: ok の中で k8v4 のいちばん長いコンテキスト．それが 64K 未満なら 64K・k4 が ok のときそちら．ok が無ければ注意の中でいちばん短い組．
    片方だけ auto: 決まった方に合わせて，もう片方を（コンテキストは ok のいちばん長い物→注意のいちばん短い物，量子化は KV_PREF の順で ok→注意）"""
    if not vram:
        return (FALLBACK[0] if ctx_set == "auto" else int(ctx_set), FALLBACK[1] if kv_set == "auto" else kv_set)
    rank = lambda st: [(c, k) for c in CTX_CHOICES for k in KV_CHOICES if fit(c, k, vram) == st]
    ok, warn = rank("ok"), rank("warn")
    if ctx_set == "auto" and kv_set == "auto":
        k8 = [c for c, k in ok if k == "k8v4"]
        if k8 and max(k8) >= 65536:
            return max(k8), "k8v4"
        if (65536, "q4_0") in ok:
            return 65536, "q4_0"
        if k8:
            return max(k8), "k8v4"
        if ok:
            return min(ok)
        if warn:
            return min(warn)
        return CTX_CHOICES[0], "q4_0"
    if ctx_set == "auto":
        cs = [c for c, k in ok if k == kv_set]
        if cs:
            return max(cs), kv_set
        cs = [c for c, k in warn if k == kv_set]
        return (min(cs) if cs else CTX_CHOICES[0]), kv_set
    c = int(ctx_set)
    if kv_set == "auto":
        for st in ("ok", "warn"):
            for k in KV_PREF:
                if fit(c, k, vram) == st:
                    return c, k
        return c, "q4_0"
    return c, kv_set


def refuse_reason(ctx, kv, vram):
    """選ばせない組なら断る理由（CLI に出す）．選べるなら None"""
    if fit(ctx, kv, vram) != "block":
        return None
    return (f"{ctx // 1024}K・{KV_LABEL[kv]} はこの PC の VRAM（{vram:g} GiB）に入りません"
            f"（K/V 約 {kv_gib(ctx, kv):.2f} GiB，回せる目安 約 {max(0.0, room_gib(vram)):.1f} GiB）．" + ("短いコンテキストを選んでください" if kv == "q4_0" else "短いコンテキストか k4 を選んでください"))


# ------------------------------------------------------------------ 自動の値
def auto_choice(vram_gib):
    v = float(vram_gib or 0)
    ctx, kv = resolve("auto", "auto", v)
    rule = f"VRAM {v:g} GiB（K/V に回せる目安 約 {room_gib(v):.1f} GiB）→ {ctx // 1024}K・{KV_LABEL[kv]}" if v else \
        f"VRAM が分からない → {ctx // 1024}K・{KV_LABEL[kv]}"
    return {"context": ctx, "kv_format": kv, "rule": rule}


_VRAM = {}


def vram_gib(H):
    if "v" not in _VRAM:
        try:
            _VRAM["v"] = float(H.spec().get("vram_gib") or 0)
        except Exception:
            _VRAM["v"] = 0.0
    return _VRAM["v"]


_LAST = {"ctx": "auto", "kv": "auto"}   # 直近の effective() で使った設定（値か auto）．cli_kv が組を決め直すのに使う


def install(H):
    """sync_home の SCHEMA に 2 項目を入れ（context は差し替え．kv_format は context のすぐ後ろ），
    effective()・settings_set() を包んで「組」で決める（片方が auto なら決まった方に合わせる．選ばせない組は断る）"""
    a = auto_choice(vram_gib(H))
    new = {}
    for k, v in H.SCHEMA.items():
        if k == "kv_format":
            continue
        if k == "context":
            new[k] = ("最大コンテキスト長（トークン．32768・65536・131072・262144．auto: VRAM で決める）", parse_context, a["context"])
            new["kv_format"] = ("会話の記憶（K/V）の量子化 k8v4・k8・k4（auto: VRAM で決める）", parse_kv, a["kv_format"])
        else:
            new[k] = v
    if "context" not in new:
        new["context"] = ("最大コンテキスト長", parse_context, a["context"])
        new["kv_format"] = ("会話の記憶（K/V）の量子化", parse_kv, a["kv_format"])
    H.SCHEMA.clear()
    H.SCHEMA.update(new)
    if getattr(H, "_ctx_wrapped", False):
        return
    H._ctx_wrapped = True
    orig_eff, orig_set = H.effective, H.settings_set

    def effective(overrides=None):
        out = orig_eff(overrides)
        raw = H.settings_raw()
        ov = overrides or {}
        cs = ov.get("context") if ov.get("context") is not None else raw.get("context", "auto")
        ks = ov.get("kv_format") if ov.get("kv_format") is not None else raw.get("kv_format", "auto")
        cs = "auto" if cs == "auto" else parse_context(cs)
        ks = "auto" if ks == "auto" else parse_kv(ks)
        _LAST.update(ctx=cs, kv=ks)
        c, k = resolve(cs, ks, vram_gib(H))
        explicit = ov.get("context") not in (None, "auto") or ov.get("kv_format") not in (None, "auto")
        if explicit:                         # 引数で選ばせない組を指定したら断る（設定ファイルの値は status などを止めないよう断らない）
            why = refuse_reason(c, k, vram_gib(H))
            if why:
                raise ValueError(why)
        out["context"], out["kv_format"] = c, k
        return out

    def settings_set(name, value):
        if name in ("context", "kv_format") and value not in (None, "", "auto"):
            raw = H.settings_raw()
            cs = raw.get("context", "auto") if name != "context" else parse_context(value)
            ks = raw.get("kv_format", "auto") if name != "kv_format" else parse_kv(value)
            c, k = resolve("auto" if cs == "auto" else int(cs), ks, vram_gib(H))
            why = refuse_reason(c, k, vram_gib(H))
            if why:
                raise ValueError(why)
        return orig_set(name, value)

    H.effective, H.settings_set = effective, settings_set


def cli_kv(s, value, H):
    """sync up --kv の値を設定の上に重ねる（auto は自動）．組を決め直し，選ばせない組なら断る（ValueError）"""
    if value is None:
        return s
    ks = "auto" if value == "auto" else parse_kv(value)
    c, k = resolve(_LAST["ctx"], ks, vram_gib(H))
    why = refuse_reason(c, k, vram_gib(H)) if ks != "auto" or _LAST["ctx"] != "auto" else None
    if why:
        raise ValueError(why)
    s["context"], s["kv_format"] = c, k
    return s


def preview(raw, vram):
    """画面の選択肢ごとに「押したらどの組になるか」と，その組の ok｜warn｜block（もう片方は今の設定のまま）"""
    cs, ks = raw.get("context", "auto"), raw.get("kv_format", "auto")
    cs = "auto" if cs == "auto" else int(cs)

    def one(c, k):
        rc, rk = resolve(c, k, vram)
        return {"context": rc, "kv_format": rk, "status": fit(rc, rk, vram)}
    return {"context": {str(v): one(v, ks) for v in ["auto", *CTX_CHOICES]},
            "kv_format": {v: one(cs, v) for v in ["auto", *KV_CHOICES]}}


# ------------------------------------------------------------------ dsh
def dsh_numbers(ctx):
    ctx = int(ctx)
    if ctx in DSH_TABLE:
        mt, head, summ = DSH_TABLE[ctx]
    else:   # 表に無い長さ（手で書いた設定）: 同じ割合で
        mt, head, summ = min(65536, ctx // 4), min(8192, ctx // 8), min(32768, ctx // 8)
    thr = int(min(ctx * THRESHOLD_RATIO, ctx - mt - head))
    return {"max_tokens": mt, "headroom": head, "summary_max": summ, "compact_at": thr}


def fit_patch(text, ctx):
    """cordis.patch.yml のモデルの maxTokens を表の値に（contextWindow は sync_home._fit_patch が合わせる）"""
    mt = dsh_numbers(ctx)["max_tokens"]
    return re.sub(r"(?m)^(\s*maxTokens:\s*)(\d+)", lambda m: f"{m.group(1)}{mt}", text)


def _top_entries(text):
    """--dump-config の出力（YAML の並び）を最上位の塊に分ける: [(id, 行の並び)]"""
    out, cur = [], None
    for line in text.splitlines():
        if line.startswith("- id: "):
            cur = (line[6:].strip().strip("'\""), [line])
            out.append(cur)
        elif line.startswith("#") or (line and not line.startswith(" ")):
            cur = None
        elif cur is not None:
            cur[1].append(line)
    return out


def _fix_compaction(lines, n):
    """塊の中の compaction-basic の項目の config を表の値に替える．替えた数を返す（lines を直す）"""
    count, i = 0, 0
    while i < len(lines):
        m = re.match(r"^(\s*)- id: compaction-basic\s*$", lines[i])
        if not m:
            i += 1
            continue
        ind = len(m.group(1))
        j = i + 1
        keep = []
        while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > ind):
            keep.append(lines[j])
            j += 1
        # config の下を落とす（項目の段は ind+2）
        body, skip = [], False
        for x in keep:
            d = len(x) - len(x.lstrip())
            if x.strip() and d == ind + 2:
                skip = x.strip().startswith("config:")
            if not skip:
                body.append(x)
        sp = " " * (ind + 2)
        body += [f"{sp}config:", f"{sp}  headroomTokens: {n['headroom']}", f"{sp}  thresholdRatio: {THRESHOLD_RATIO}",
                 f"{sp}  maxTokens: {n['summary_max']}"]
        lines[i + 1:j] = body
        i += 1 + len(body)
        count += 1
    return count


def build_overlay(dump_text, ctx):
    n = dsh_numbers(ctx)
    blocks = []
    for eid, lines in _top_entries(dump_text):
        if not eid.startswith("preset-"):
            continue
        lines = list(lines)
        if _fix_compaction(lines, n):
            blocks.append("\n".join(lines))
    if not blocks:
        return None
    head = (f"# 起動の道具（sync_ctx.py）が起動のたびに作る上書き．最大コンテキスト {ctx} に合わせて要約の始まりを {n['compact_at']} トークンにする．\n"
            f"# dsh の --dump-config の preset-* の塊を写し，compaction-basic の config だけ替えた物（手で直さない．次の起動で作り直す）．\n")
    return head + "\n".join(blocks) + "\n"


def dsh_cmd(cmd, s, node, dsh_bin, env, say=print):
    """dsh を起こす命令に --patch <上書き> を足す（作れなければ元の命令のまま．要約は dsh の既定）"""
    ctx = int(s.get("context") or 262144)
    out_file = os.path.join(_home_run(), "dsh-ctx.patch.yml")
    try:
        r = subprocess.run([node, dsh_bin, "--profile", "web", "--dump-config"], env=env, capture_output=True, timeout=60,
                           creationflags=0x08000000)
        text = r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""
        ov = build_overlay(text, ctx) if text else None
    except Exception:
        ov = None
    if not ov:
        say("  （dsh の要約の始まりを合わせられませんでした．dsh の既定のまま起こします）")
        return cmd
    with open(out_file + ".tmp", "w", encoding="utf-8") as f:
        f.write(ov)
    os.replace(out_file + ".tmp", out_file)
    cmd = list(cmd)
    try:
        i = cmd.index("web", cmd.index(dsh_bin))
    except ValueError:
        return cmd
    return cmd[:i + 1] + ["--patch", out_file] + cmd[i + 1:]


def _home_run():
    import sync_home as H
    return os.path.dirname(H.path("run", "x"))


# ------------------------------------------------------------------ 起動の記録と，いまの値
def kv_limit(log_path, start=0):
    """エンジンの記録から「WARNING: past N cells ...」の N（止まらずに使える長さ）．無ければ None．最後の起動の分だけ見る"""
    try:
        with open(log_path, "rb") as f:
            if start > os.path.getsize(log_path):
                start = 0          # 記録が書き直された（起動のたびに新しくなる形）
            f.seek(start)
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    m = None
    for m in KV_WARN.finditer(text):
        pass
    return int(m.group(1)) if m else None


def running(H):
    """動いているエンジンの文脈と量子化（起こす直前に残した run/cfg/started.json から．--dry が書き直す auto.json は見ない）と，使える長さ"""
    port = H.effective()["api_port"]
    if not H.listening(port):
        return None
    try:
        rec = json.load(open(os.path.join(H.home(), "run", "cfg", "started.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {"context": None, "kv_format": None, "kv_limit": None}
    a = rec.get("args") or []
    get = lambda k: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None
    ctx = get("--max-context")
    # 記録はエンジンが起きるたびに足されるので，起こす直前の大きさより後の分だけ見る
    lim = kv_limit(rec.get("log") or os.path.join(H.home(), "run", "strata-auto.log"), int(rec.get("log_offset") or 0))
    return {"context": int(ctx) if ctx else None, "kv_format": get("--kv"), "kv_limit": lim}


def note_start(cfg_path, log_path):
    """エンジンを起こす直前に，その設定の引数と記録の大きさを run/cfg/started.json に残す（sync_launch の start_engine の前）"""
    try:
        c = json.load(open(cfg_path, encoding="utf-8"))
        off = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        out = os.path.join(os.path.dirname(cfg_path), "started.json")
        json.dump({"args": c.get("args") or [], "log": log_path, "log_offset": off, "config": cfg_path}, open(out + ".tmp", "w", encoding="utf-8"))
        os.replace(out + ".tmp", out)
    except (OSError, ValueError):
        pass


def info(H):
    """sync ctx --json と status --json の context の中身"""
    raw = H.settings_raw()
    eff = H.effective()
    a = auto_choice(vram_gib(H))
    run = running(H)
    n = dsh_numbers(eff["context"])
    return {
        "context": {"setting": raw.get("context", "auto"), "auto": a["context"], "effective": eff["context"],
                    "choices": list(CTX_CHOICES)},
        "kv_format": {"setting": raw.get("kv_format", "auto"), "auto": a["kv_format"], "effective": eff["kv_format"],
                      "choices": [{"value": k, "label": KV_LABEL[k]} for k in KV_CHOICES]},
        "vram_gib": vram_gib(H), "rule": a["rule"],
        # ok｜warn｜block: いま使う組の判定，全部の組（K/V の見積もり GiB つき），画面の選択肢ごとの「押したらこの組」
        "status": fit(eff["context"], eff["kv_format"], vram_gib(H)), "room_gib": room_gib(vram_gib(H)),
        "combos": combos(vram_gib(H)), "preview": preview(raw, vram_gib(H)),
        "dsh": {"context_window": eff["context"], **n},
        "running": run,
        # 「この設定だと約 N トークンまで」: 動いているエンジンが起動のときに出した WARNING の N（出ていなければ null）
        "kv_limit": run.get("kv_limit") if run else None,
    }


def cmd_ctx(argv, H):
    d = info(H)
    if "--json" in argv:
        print(json.dumps(d, ensure_ascii=False))
        return 0
    c, k = d["context"], d["kv_format"]
    print(f"  最大コンテキスト長  設定 {c['setting']}（いま使う値 {c['effective']}，自動なら {c['auto']}）")
    print(f"  K/V の量子化        設定 {KV_LABEL.get(k['setting'], k['setting'])}（いま使う値 {KV_LABEL.get(k['effective'], k['effective'])}，自動なら {KV_LABEL[k['auto']]}）")
    print(f"  自動の決め方: {d['rule']}．dsh の要約は {d['dsh']['compact_at']} トークンから")
    if d["room_gib"] is not None:
        mark = {"ok": "選べる", "warn": "注意", "block": "選ばせない"}
        print(f"  いまの組は「{mark[d['status']]}」．組ごと（K/V の見積もり GiB）:")
        for c in CTX_CHOICES:
            row = [x for x in d["combos"] if x["context"] == c]
            print("    " + f"{c // 1024}K".ljust(5) + "  ".join(f"{KV_LABEL[x['kv_format']]} {x['kv_gib']:.2f} {mark[x['status']]}" for x in row))
    if d["running"]:
        r = d["running"]
        print(f"  動いているエンジン: {r['context']}・{KV_LABEL.get(r['kv_format'], r['kv_format'])}"
              + (f"．この設定だと約 {r['kv_limit']} トークンまで（それより長いと遅くなり，やがて失敗します）" if r.get("kv_limit") else ""))
    print("（変えるのは sync settings set context <値|auto> ／ sync settings set kv_format <k8v4|k8|k4|auto>．次の起動から効く）")
    return 0
