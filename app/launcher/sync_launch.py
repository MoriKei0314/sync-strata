#!/usr/bin/env python3
"""ダブルクリック 1 回の起動の試作（11/15 夜．本人の計画 ⑧A）．この PC の日常の起動（作業場の *.ps1）と設定は変えない．

  py -3 -X utf8 sync_launch.py [--preset speed|quality] [--pack auto|sync-m|sync-s] [--dry] [--no-gui] [--engine EXE] [--env K=V ...]
                               [--stop]

流れ（利用者が選ぶのは preset だけ．ほかは自動）:
  1. もう動いていれば，画面を開くだけ．
  2. PC を調べる（tools/night/wintune.py preflight）: RAM の空き，VRAM の空き，画面をつないでいるか，裏で SSD を読むもの，RAM を食うアプリ．
  3. pack を選ぶ: 品質重視＝「SSD に残る専門家が 3% 以下」で入るいちばん大きい pack．速度重視＝ 1 段小さい pack でも全部 RAM に載るほう．
     手元に無い pack は選ばない（公開版ではここでダウンロード．download_plan() に手順だけ書いてある）．
     11/15 S2: pack の一覧はモデルの一覧（models.json か配布の一覧）から作る．pending（pack がまだ無い）は選ばない．
     Sync-XS が選ばれるのは大きい pack が全部は載らないとき（RAM 不足・VRAM 不足）だけ．速度重視でも Sync-XS へは下げない（11/15 16:55 本人）．
  4. 設定を作る: RAM の枠（空き − エンジン 2.7 − 余白 1.0 GiB，上限は pack − VRAM の席），VRAM の予約（画面あり 1,024・なし 512 MiB），
     tail skip（速度 R4・品質 R7），輪なし，固定は枠＋1．分担（--pcie-frac）と RAM の写しの育て方は，エンジンの自動の旗（--env で渡す）に任せる．
  5. dsh を起こし（動いていれば何もしない），Strata を起こし，/health とページの読み込みが静まるのを待ち，短い 1 本で温める．
  6. 会話の画面を Edge の独立した窓（--app）で開く．RAM が 32 GB 以下なら「スマホ・タブレットから開くほうが速い」と出す．
     11/15: dsh と中継（3081）が答えるのを待ってから開く．もう開いていれば前に出すだけ（gui_window.ps1）．Edge が無ければ既定のブラウザー．
  7. 起動後の調子（1 窓の内訳）を wintune.py diagnose で 1 行出す．
記録: SYNC_HOME\\run\\last.json（選んだ pack・設定・理由・勧め）と，設定 run\\cfg\\auto.json．
部品の置き場（エンジン・Python・起動の設定のひな形）は sync_home.LAYOUT（入れた先の並びか layout.dev.json）．
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)     # 11/15 S2: wintune.py も同じフォルダーに置く（配布物の launcher の部品に入る）
import wintune  # noqa: E402
import ramsqueeze  # noqa: E402  11/16 係 S4: 起動・モデルの切り替えのとき 1 回，ほかのアプリの RAM を追い出す
import sync_home as H  # noqa: E402  11/15 app1115: 設定・置き場・dsh

ROOT = os.path.join(H.home(), "run").replace("\\", "/")   # 11/15 app1115: SYNC_HOME\run（前は results\night-1115\launcher）
LAY = H.LAYOUT
PY = LAY["python"] or sys.executable                  # エンジンの入口（serve の server.py）を流す Python
TEMPLATE = LAY["engine_template"]                     # 起動の設定のひな形（読むだけ）．入れた先では道のりの無いひな形 engine-template.json
ENGINE = LAY["engine_exe"]
# 走りながらエンジンが自分で直す旗（11/15 の夜に測って採ったもの）: RAM の写しを育てる／CPU と GPU の分担を実測の待ちで寄せる／CPU の優先度を「通常以上」に
# 起動の値に足すエンジンの旗は，ここ 1 か所（11/15 夜．例: "STRATA_QL_ACTQ_CPU_ROWS": "…"，"STRATA_QL_FLAGB_SKIP0": "1" は照合と測りの後に）
AUTO_ENV = {"STRATA_QL_RAM_ROTATE": "1", "STRATA_QL_PCIE_AUTO": "1", "STRATA_QL_PRIO_CPU": "above",
            "STRATA_QL_RAM_ELASTIC": "1",
            "STRATA_QL_ACTQ_CPU_ROWS": "1", "STRATA_QL_FLAGB_SKIP0": "1"}   # 11/15 夜: ELASTIC＝メモリの枠の動的化．ACTQ・FLAGB は温度 0 の返事が一致，Sync-S R4 +2〜3%・R7 +1%
GUI_URL = "http://127.0.0.1:3081/m/"
SERVER_PY = LAY["server_py"]
MIN_GAIN = {"sync-m": "4"}         # VRAM の入れ替えの下限（pack ごと．無ければ 3．Windows で測った値）
# 11/15 16:55 本人: Sync-XS が選ばれるのは，大きい pack が全部は載らないとき（RAM 不足でも VRAM 不足でも．on_file_pct の判定）だけ．
# 速度重視で 1 つ小さい pack へ下げるときも Sync-XS へは下げない
NO_SPEED_DOWN_TO = ("sync-xs",)


def load_packs():
    """手元の pack の候補（大きい順．同じ大きさなら表引きなし bih3 が先）．モデルの一覧の models から作る．
    kernel: bih3＝表引きなし（速い），lut＝表引き（作者の PC の layout.dev.json の packs_extra だけ）．pending は入れない"""
    out = []
    for m in H.catalog().get("models", []):
        if m.get("pending") or not m.get("local_dir") or not m.get("experts_gib"):
            continue
        out.append({"id": m["id"], "name": m.get("name", m["id"]), "experts_gib": float(m["experts_gib"]), "kernel": "bih3",
                    "dir": m["local_dir"], "repo": (m.get("hf") or {}).get("repo") or None, "min_gain": MIN_GAIN.get(m["id"], "3"),
                    "fits_ram_gib": float(m.get("fits_ram_gib") or 0)})
    fits = {c["id"]: c["fits_ram_gib"] for c in out}
    for x in LAY.get("packs_extra") or []:
        out.append({**x, "dir": os.path.normpath(x["dir"]), "min_gain": x.get("min_gain", MIN_GAIN.get(x["id"], "3")),
                    "fits_ram_gib": float(x.get("fits_ram_gib") or fits.get(x["id"], 0))})
    out.sort(key=lambda c: (-c["experts_gib"], c["kernel"] != "bih3"))
    return out


PACKS = load_packs()


def save_choice(pick, relay_port=3081):
    """起動したら choice.json に pack と tail skip を残す（画面が「いま動いているのは Sync-S R4」と出せるように）．
    作者の PC で日常の番号（3081）のときは，日常の中継の choice.json にも残す（layout.dev.json の daily_choice）"""
    rec = {"model": pick["id"], "r": pick["R"], "at": int(time.time() * 1000), "by": "sync_launch"}
    daily = [LAY["daily_choice"]] if LAY.get("daily_choice") and relay_port == 3081 else []
    for f in [H.path("models-state", "choice.json")] + daily:
        try:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            json.dump(rec, open(f, "w", encoding="utf-8"))
        except OSError:
            pass


ON_FILE_OK_PCT = 3.0
TIER_SLACK_GIB = 1.0
# 11/16: 積んでいる量が読めないときの見える量の段（内蔵 GPU の UMA で 2〜4 GiB 減ることがあるので広く）．一覧の fits_ram_gib → 見える量の下限
VISIBLE_TIER_GIB = {24: 0, 32: 27, 48: 43}     # 11/16: RAM の段の余裕（「32 GB」の PC は 約 31.6 GiB と出る．中継の modelsView の fitsOf と同じ 1 GiB）
R_OF = {"speed": 4, "quality": 7}


def say(s):
    print(s, flush=True, file=sys.stderr if JSON_OUT else sys.stdout)


PORT = 8080          # API の待ち受け（--port で変える）


def health(port=None):
    port = port or PORT
    if not H.listening(port):     # 11/15 S2: 待ち受けが無ければ聞かない（断られるまでの待ちを省く）
        return False
    try:
        return urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2).status == 200
    except Exception:
        return False


def listening(port):
    return H.listening(port)      # 11/15 S2: OS の表で見る（つなぎに行かない）


def page_reads():
    if not H.OS.IS_WIN:       # 11/16 S2: Linux は /proc/vmstat の pgmajfault
        import lintune
        return lintune.page_reads(5.0)
    o = wintune.run_ps("$m = Get-Counter '\\Memory\\Page Reads/sec','\\Memory\\Available MBytes' -SampleInterval 5 -MaxSamples 1; "
                       "($m.CounterSamples | ForEach-Object { [math]::Round($_.CookedValue,0) }) -join ' '", 60).split()
    try:
        return float(o[0]), float(o[1])
    except (IndexError, ValueError):
        return None, None


def download_plan(pack):
    """公開版でここに入る手順（今夜は実行しない: 非公開の置き場の鍵を扱わないため）．
    huggingface_hub.snapshot_download(repo_id=pack['repo'], local_dir=<モデルの置き場>/<id>, max_workers=8) → MANIFEST.json の sha256 で確かめる →
    GGUF（語彙・射影）・下書きの層・トークナイザーも同じ形で．途中で切れたら同じ呼び出しで続きから．空きの確かめ（pack＋2 GiB）を先に．"""
    return {"repo": pack.get("repo"), "needs_gib": round(pack["experts_gib"] * 1.08 + 2.5, 1)}


def choose(pre, preset, want, ram_max=None, reserve_mib=None):
    """pack と設定を決める．理由を日本語の行で返す"""
    g0 = (pre.get("gpus") or [{}])[0]
    display = (g0.get("display_active") or "").lower().startswith("enabled")
    reserve = wintune.DISPLAY_RESERVE_MIB if display else wintune.HEADLESS_RESERVE_MIB
    if reserve_mib is not None:      # 11/15 app1115: 設定 vram_reserve_mib
        reserve = int(reserve_mib)
    avail = pre["ram"].get("avail_if_stopped_gib") or pre["ram"]["avail_gib"]
    vram_free = pre.get("vram_free_assumed_gib") or (g0.get("vram_free_mib") or 0) / 1024
    seats = max(0.0, vram_free - wintune.VRAM_ENGINE_GIB - reserve / 1024)
    room = avail - wintune.ENGINE_RAM_GIB_WIN - wintune.SAFETY_GIB
    cands = []
    for p in PACKS:
        if not os.path.exists(os.path.join(p["dir"], "experts.v2.bin")):
            continue
        budget = int(max(0.0, min(p["experts_gib"] - seats, room)) * 4) / 4.0
        if ram_max is not None:      # 11/15 app1115: 設定 ram_max_gib（RAM の写しの上限）
            budget = int(max(0.0, min(p["experts_gib"] - seats, float(ram_max))) * 4) / 4.0
        on_file = max(0.0, p["experts_gib"] - seats - budget)
        cands.append({**p, "budget": budget, "on_file_gib": round(on_file, 2), "on_file_pct": round(100 * on_file / p["experts_gib"], 1)})
    why = [f"空き RAM {avail:.1f} GiB（エンジンに {wintune.ENGINE_RAM_GIB_WIN}，余白 {wintune.SAFETY_GIB} を除くと専門家に {room:.1f} GiB），VRAM の席 約 {seats:.1f} GiB，画面は{'この GPU' if display else '別／なし'}（予約 {reserve} MiB）"]
    if not cands:
        return None, why + ["手元に pack が無い（公開版ではここでダウンロード）"]
    if want != "auto":
        pool = [c for c in cands if c["id"] == want] or cands
        pick = pool[0]
        why.append(f"pack は指定どおり {pick['name']}")
    else:
        # 11/16 本人の決定: 積んでいる RAM（物理の合計）の段で選ぶ（画面の説明「Sync-XS RAM 24GB 以下向け／Sync-S RAM 32GB 向け／
        # Sync-M RAM 48GB 以上向け」と同じ．一覧の fits_ram_gib．「32 GB」の PC は 約 31.6 GiB と出るので 1 GiB の余裕＝中継の modelsView と同じ）．
        # 空き RAM が足りないときも小さいモデルには落とさない（SSD に残る割合と，閉じると戻る RAM を出す）
        ram_total = float(pre["ram"].get("total_gib") or 0)          # 見える量（内蔵 GPU の UMA などの分だけ減る）
        ram_inst = pre["ram"].get("installed_gib")                     # 積んでいる量（11/16: 段はこれで）
        if ram_inst:
            tier = [c for c in cands if c.get("fits_ram_gib", 0) <= float(ram_inst) + TIER_SLACK_GIB]
            seen = f"積んでいる RAM {float(ram_inst):.0f} GB（見える量 {ram_total:.1f} GiB）"
        else:   # 積んでいる量が取れないとき: 見える量で，余裕を広く（S は 27 GiB・M は 43 GiB から）
            tier = [c for c in cands if VISIBLE_TIER_GIB.get(int(c.get("fits_ram_gib", 0)), c.get("fits_ram_gib", 0) - 5) <= ram_total]
            seen = f"見える RAM {ram_total:.1f} GiB（積んでいる量は読めなかった）"
        if tier:
            pick = tier[0]          # 大きい順に並んでいるので，段に合ういちばん大きい物
            why.append(f"{seen} なので {pick['name']}（RAM {pick.get('fits_ram_gib', 0):.0f} GB 向け）")
        else:
            pick = min(cands, key=lambda c: (c["experts_gib"], c["kernel"] != "bih3"))
            why.append(f"{seen} に合う段のモデルが手元に無いので，手元のいちばん小さい {pick['name']}")
        if preset == "speed":       # 速度重視: 1 つ小さい物（同じ段の中．Sync-XS へは下げない＝11/15 16:55 本人）
            smaller = [c for c in tier if c["experts_gib"] < pick["experts_gib"] and c["kernel"] == "bih3" and c["id"] not in NO_SPEED_DOWN_TO]
            if smaller:
                pick = smaller[0]
                why.append(f"速度重視なので 1 つ小さい {pick['name']}")
        if pick["on_file_pct"] > ON_FILE_OK_PCT:
            why.append(f"いまは空き RAM が足りず，{pick['name']} の専門家の {pick['on_file_pct']}%（{pick['on_file_gib']} GiB）が SSD に残る"
                       f"（会話のたびに SSD を待つので遅くなる．閉じられるアプリを閉じると 約 {pre.get('closable_gib')} GiB 戻る）．小さいモデルには替えない")
        else:
            why.append(f"{pick['name']} は全部 RAM と VRAM に載る（SSD に残る {pick['on_file_pct']}%）")
    pick = dict(pick)
    pick.update(reserve=reserve, R=R_OF.get(preset, 7), seats_gib=round(seats, 2))
    if ram_max is not None:
        why.append(f"RAM の枠は設定どおり {ram_max} GiB まで")
    if reserve_mib is not None:
        why.append(f"VRAM の予約は設定どおり {reserve_mib} MiB")
    why.append(f"RAM の枠 {pick['budget']} GiB，輪なし")
    return pick, why


def apply_squeeze(s, dry=False, say_=None):
    """11/16 係 S4（本人の決定）: 設定 ram_squeeze が auto（既定）なら，エンジンが止まっている今（起動の前，または画面からモデルを切り替えるとき＝
    中継が down --engine の後に up --gui --model を呼ぶ道で，前のエンジンを止めた後・新しいのを起こす前）に 1 回だけ追い出す．
    アプリは閉じない．off なら何もしない．--dry は試し用の値（SYNC_FAKE_SQUEEZE）があるときだけ流す．戻り値は ramsqueeze.run の辞書"""
    mode = s.get("ram_squeeze") or "auto"
    if mode == "off":
        return ramsqueeze.run("off")
    if dry and not os.environ.get("SYNC_FAKE_SQUEEZE"):
        return {"ran": False, "mode": mode, "freed_gib": 0.0, "why": None, "detail": "--dry なので追い出しません"}
    (say_ or say)("  ほかのアプリの RAM を追い出しています（10〜30 秒ほど．アプリは閉じません）...")
    tg = os.environ.get("SYNC_RAM_SQUEEZE_TARGET_GIB")
    return ramsqueeze.run(mode, float(tg) if tg else 3.0)


def api_info(host, port, key_set):
    """ほかのハーネス・自作の道具からつなぐための案内（OpenAI 互換・Anthropic 互換）"""
    base = f"http://{host if host not in ('0.0.0.0', '::') else '<この PC の番地>'}:{port}"
    model = "strata"
    try:
        hdr = {"Authorization": "Bearer " + os.environ.get("STRATA_API_KEY", "")} if key_set else {}
        m = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/v1/models", headers=hdr), timeout=5).read())
        model = (m.get("data") or [{}])[0].get("id", model)
    except Exception:
        pass
    key = "起動のときに渡した鍵（環境変数 STRATA_API_KEY）" if key_set else "なし（何を入れても通る）"
    # 例は英字だけにする: Windows の端末から日本語を -d に直接書くと，端末の文字コード（cp932）のまま送られて server に断られる（11/15 に実際に起きた）
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "Hello"}]}).replace('"', '\\"')
    return [
        f"API: {base}/v1   モデル名: {model}",
        f"  OpenAI 互換: POST {base}/v1/chat/completions（stream 可），POST /v1/responses，GET /v1/models",
        f"  Anthropic 互換: POST {base}/v1/messages（stream 可）",
        f"  鍵: {key}．送り方は Authorization: Bearer <鍵> か x-api-key: <鍵>",
        f"  多くのハーネスは環境変数で: OPENAI_BASE_URL={base}/v1  OPENAI_API_KEY=<鍵>（Anthropic 形式なら ANTHROPIC_BASE_URL={base}）",
        f'  curl の例: curl {base}/v1/chat/completions -H "Content-Type: application/json" -d "{body}"',
        "  日本語を curl で送るとき（Windows）: 本文を UTF-8 のファイルに書いて --data-binary @body.json（端末に直接書くと文字コードが合わず断られる）",
        '  速さと品質を依頼ごとに変える: 本文に "strata_tune": {"tail_skip": 4}（速度重視）／7（品質重視）／0（切）．無ければ起動のときの preset',
    ]


# 11/16: RAM の写しのうち固定する量（STRATA_PARTIAL_PIN_GIB）．Windows は「枠＋1」（今のまま）．Linux は「枠 − 帯」，
# 帯＝min(BAND_MAX_GIB, 枠 × BAND_FRAC)（メモリの枠の動的化を Linux でも働かせるため．本人の答え次第で変わるので，値はこの表の 1 か所）
PIN_RULE = {"windows": {"plus_gib": 1}, "linux": {"band_max_gib": 4.0, "band_frac": 0.2}}


def pin_gib(budget):
    if H.OS.IS_WIN:
        return str(int(budget + PIN_RULE["windows"]["plus_gib"]))
    r = PIN_RULE["linux"]
    band = min(r["band_max_gib"], budget * r["band_frac"])
    return f"{max(0.0, budget - band):.2f}".rstrip("0").rstrip(".") or "0"


def learned_profile(model_id):
    """学習した専門家の並びの置き場（11/16．モデルごと）"""
    return H.path("engine-data", f"expert-profile-{model_id}.bin")


def make_config(pick, engine, extra_env, context=None):
    c = json.load(open(TEMPLATE, encoding="utf-8"))
    args = list(c["args"])
    # 11/15 S2: 入れた先のひな形（engine-template.json）は道のりを持たない．置き場はここで入れる
    if LAY.get("engine_lib_dirs"):
        c["lib_dirs"] = LAY["engine_lib_dirs"]
    if LAY.get("engine_cwd"):
        c["cwd"] = LAY["engine_cwd"]
    if LAY.get("expert_profile"):
        if "--expert-profile" in args:
            args[args.index("--expert-profile") + 1] = LAY["expert_profile"]
        else:
            args += ["--expert-profile", LAY["expert_profile"]]
    sp0 = H.shared_paths()
    if LAY.get("vision_exe") and "vision.mmproj" in sp0 and not isinstance(c.get("vision"), dict):
        # 11/15 夜: 入れた先のキットに画像の読み取りのエンジンがあり，mmproj が手元にあれば画像を読む（無ければ下で外す）
        c["vision"] = {"exe": LAY["vision_exe"], "mmproj": sp0["vision.mmproj"], "model": sp0.get("vision.model") or sp0.get("--native"),
                       "gpu": False, "max_tokens": 1024, "threads": 8, "elastic": True, "elastic_idle_s": 120}
        if "--vision" not in args:
            args.append("--vision")
    vis = c.get("vision")
    if isinstance(vis, dict) and not (vis.get("exe") and os.path.exists(vis["exe"])):
        c.pop("vision", None)           # 画像の読み取りのエンジンが無い並び（配布物の今の版）では画像を読まない
        args = [x for x in args if x != "--vision"]

    def setarg(k, v):
        if k in args:
            args[args.index(k) + 1] = v
        else:
            args.extend([k, v])
    setarg("--pack", pick["dir"])
    setarg("--resident-budget-gib", str(pick["budget"]))
    setarg("--vram-reserve-mib", str(pick["reserve"]))
    setarg("--adapt-min-gain", str(pick.get("min_gain", "3")))
    if context:
        setarg("--max-context", str(int(context)))   # 11/15 app1115: 設定 context
    if pick.get("kv_format"):
        setarg("--kv", pick["kv_format"])   # 11/15 係 C: 設定 kv_format（--kv-grow はひな形のまま．--kv-streaming は使わない）
    sp = H.shared_paths()                            # 11/15 app1115: 一覧の共通の部品があれば，その置き場を使う
    for flag in ("--native", "--ple-gguf", "--mtp"):
        if flag in sp:                               # 11/15 S2: ひな形に無い旗（道のりの無いひな形）も足す
            setarg(flag, sp[flag])
    if "tokenizer" in sp:
        c["tokenizer"] = sp["tokenizer"]
    if "vision.model" in sp and isinstance(c.get("vision"), dict):
        c["vision"]["model"] = sp["vision.model"]     # 11/15 夜: 画像の読み取りの --model も共通の部品の GGUF（切り出した物）
    if "vision.mmproj" in sp and isinstance(c.get("vision"), dict):
        c["vision"]["mmproj"] = sp["vision.mmproj"]   # 11/15: VRAM の入れ替えの下限（既定 1.5）．pack ごとの値（PACKS の min_gain．無ければ 3）
    try:                                             # 11/16 係 S3: Windows の Radeon（HIP）は backend=hip と，単体の装置の番号（内蔵があると単体は 1 にずれる＝上流 #325）を渡す
        import sync_env as _SE
        _ev = _SE.check()
        if _ev["gpu"].get("vendor") == "amd" and _ev["engine"] and _ev["facts"].get("os") == "windows":
            c["backend"] = "hip"
            # 11/16 エンジン 1: ひな形の "gpu": 0 が残ると，番号が取れなかったとき HIP_VISIBLE_DEVICES=0（内蔵）で起きて落ち，
            # server.py の起動ごとの自動の選び（hip_auto_devices）も働かない．HIP では外し，番号が取れたときだけ渡す
            c.pop("gpu", None)
            c.pop("gpus_asked", None)
            _ord = _SE.hip_ordinal(engine, c.get("lib_dirs"))
            if _ord is not None:
                c["hip_ordinal"] = _ord
    except Exception:
        pass
    env = dict(c.get("env") or {})
    env.update(STRATA_ROUTE_TAIL_SKIP=str(H.engine_tail(pick["R"])), STRATA_QL_DYN_TIER_GIB="0", STRATA_UNBUFFERED_LOAD="1",
               STRATA_PARTIAL_PIN_GIB=pin_gib(pick["budget"]))
    env.update(AUTO_ENV)
    for kv in extra_env:
        k, _, v = kv.partition("=")
        env[k] = v
    os.makedirs(f"{ROOT}/cfg", exist_ok=True)
    log = os.path.normpath(f"{ROOT}/strata-auto.log")    # 11/16: Windows は「\」，Linux は「/」のまま（前は Linux でも「\」に替えて 1 つのファイル名になっていた）
    c["model_name"] = "qwen3.8-flash-next-" + pick["id"]      # API の /v1/models に出る名前を，実際に読み込む pack に合わせる
    # 11/16: 会話の中継の SESSION_DIR と同じ置き場（前は別で，中継が古い控えを消せなかった）．新しい sync_home が無ければ前のまま
    slots = H.effective().get("sessions_dir") or LAY.get("slot_save_path") or os.path.dirname(H.path("engine-sessions", "x"))
    os.makedirs(slots, exist_ok=True)
    c.update(args=args, env=env, exe=engine, log=log, port=PORT, slot_save_path=slots,
             note="起動の道具（launcher/sync_launch.py）が作った設定")
    # 11/16 本人の決定: 専門家の並びを各自の PC で学習させる．保存はモデルごとに SYNC_HOME の下（配布物には入らない）．
    # server.py（#477）が，保存した物が同じモデルの形ならそれを読み，そうでなければ --expert-profile（本家の物）を読む
    # 11/16 測りの後: 学習した並びは速くならなかったので既定は off（設定 expert_learning＝on のときだけ学習・保存する）
    if "--expert-profile" in args and (H.effective().get("expert_learning") or "off") == "on":
        c["expert_profile_save"] = learned_profile(pick["id"])
        c["expert_profile_save_every"] = 10
    # 11/16 夜 本人の決定（エンジン 1 の切り分け）: 取り出しの値を送らない依頼（dsh は温度も送らない＝greedy）に，
    # 繰り返しの罰則の既定を入れる．dsh の長い文脈＋greedy＋R4 で名詞の並びが輪に落ちた（同じ文 101 回・思考 51,000 字）のが，
    # repetition 1.05（直前 256）で消え，decode は揺れの内．依頼が自分の値を送れば，そちらが勝つ（server.py sampling_defaults_from_config）
    # モデルごとの強さ（11/16 20:2x: Sync-XS は 1.05 で効ききらず，1.10 を試して決める．決まるまでは全部 1.05）
    REP_PENALTY = {"sync-xs": 1.05, "sync-s": 1.05, "sync-m": 1.05}
    samp = dict(c.get("sampling") or {})
    samp.setdefault("repetition_penalty", REP_PENALTY.get(pick["id"], 1.05))
    samp.setdefault("penalty_last_n", 256)
    c["sampling"] = samp

    path = f"{ROOT}/cfg/auto.json"
    json.dump(c, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return path, log


def find_edge():
    """Edge の場所: いつもの 2 か所，無ければレジストリの App Paths"""
    pf = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles")]   # 11/15 夜: ドライブの道のりを書かない
    for edge in [os.path.join(x, "Microsoft", "Edge", "Application", "msedge.exe") for x in pf if x]:
        if os.path.exists(edge):
            return edge
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as k:
                    p = winreg.QueryValue(k, None)
                    if p and os.path.exists(p.strip('"')):
                        return p.strip('"')
            except OSError:
                pass
    except ImportError:
        pass
    return None


def gui_window(focus=False):
    """会話の画面の窓（題名が dsh のブラウザーの窓）が開いていれば True．focus なら最小化を戻して前に出す（gui_window.ps1）"""
    if not H.OS.IS_WIN:
        return False        # 11/16 S2: Linux では窓を探さない（開くたびに既定のブラウザーへ渡す）
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(HERE, "gui_window.ps1")]
    if focus:
        cmd.append("-Focus")
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=0x08000000).stdout.decode("utf-8", "replace")
    except Exception:
        return False
    return out.strip().startswith("found")


def open_gui(dry=False, url=None):
    url = url or GUI_URL
    """会話の画面を開く．11/15 の直し: もう開いていれば前に出すだけ（二重に開かない），Edge を App Paths でも探す，
    Edge が無ければ既定のブラウザー．Edge はいつものプロファイル（ふだんのタブと同じログインのクッキーを使う）の独立した窓（--app）．
    返すのは何をしたかの 1 行．dry: 開かずに，何をするかだけ返す"""
    if gui_window(focus=not dry):
        return "会話の画面はもう開いています（前に出しました）" if not dry else "会話の画面はもう開いている（前に出すだけ）"
    edge = find_edge() if H.OS.IS_WIN else None
    if dry:
        return f"Edge の窓で開く（{edge}）" if edge else f"既定のブラウザーで開く（{url}）"
    if edge:
        subprocess.Popen([edge, f"--app={url}", "--window-size=1280,860", "--no-first-run", "--no-default-browser-check"],
                         creationflags=0x00000008, close_fds=True)   # DETACHED_PROCESS
        return "会話の画面を Edge の窓で開きました"
    H.OS.open_url(url)
    return "会話の画面を既定のブラウザーで開きました" + ("（Edge が見つかりませんでした）" if H.OS.IS_WIN else "")


LOGIN_HINT = ("  ログインを求められたら: dsh の黒い窓の http://127.0.0.1:3080/?token=… の頭を http://127.0.0.1:3081 に替えて，"
              "Edge のふつうのタブで 1 回開く（30 日もつ．同じ Edge の窓にも効く）")


def warm(R, key=""):
    body = {"model": "strata", "stream": False, "max_tokens": 48, "temperature": 0.7, "reasoning_effort": "none",
            "chat_template_kwargs": {"enable_thinking": False}, "strata_tune": {"tail_skip": H.engine_tail(R)},
            "messages": [{"role": "user", "content": "こんにちは．準備はできましたか？"}]}
    hdr = {"Content-Type": "application/json"}
    if key:
        hdr["Authorization"] = "Bearer " + key
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", data=json.dumps(body).encode(), headers=hdr)
    try:
        urllib.request.urlopen(req, timeout=300).read()
        return True
    except Exception:
        return False


def stop_engine(port):
    """エンジンを止める（11/15 app1115）．自分で起こした偽物・ほかの物（procs.json の engine）は番号で，
    本物（serve\\server.py）は stop-strata.ps1 で（-Port を渡す）．止めたら 0"""
    rec = H.procs().get("engine")
    if rec and H.alive("engine") and not rec.get("real"):
        H.stop("engine")
        for _ in range(40):
            if not listening(port):
                return 0
            time.sleep(0.25)
        return 1
    if not listening(port):
        H.stop("engine")
        return 0
    if LAY.get("stop_ps1") and os.path.exists(LAY["stop_ps1"]):
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", LAY["stop_ps1"], "-Port", str(port)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
        H.stop("engine")
        return r.returncode
    # 11/15 S2: 入れた先（stop-strata.ps1 が無い）: 会話の中継に途中の会話を残させてから，記録した server.py とその子を番号で止める
    try:
        pp = H.effective()["proxy_port"]
        if listening(pp):
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{pp}/proxy/save-live", data=b"", method="POST"), timeout=150).read()
    except Exception:
        pass
    if not H.alive("engine"):
        return 1          # 自分で起こした物ではない（ほかの Strata）．止めない
    H.stop_tree("engine")
    for _ in range(120):
        if not listening(port):
            return 0
        time.sleep(0.25)
    return 1


def start_engine(cfg, s, key):
    """エンジンを起こす．試しのときは環境変数 SYNC_ENGINE_CMD（{port} と {config} を差し込む命令．偽の Strata など）を代わりに起こす"""
    port = s["api_port"]
    fake = os.environ.get("SYNC_ENGINE_CMD")
    child_env = dict(os.environ)
    if key:
        child_env["STRATA_API_KEY"] = key          # 引数に書かない（プロセスの一覧に出さない）
    if fake:
        import shlex
        cmd = [x.replace("{port}", str(port)).replace("{config}", os.path.normpath(cfg)) for x in shlex.split(fake, posix=False)]
        cmd = [x[1:-1] if len(x) > 1 and x[0] == x[-1] == '"' else x for x in cmd]
        sv = H.spawn("engine", cmd, env=child_env, log=f"{ROOT}/server.out", port=port)
        return sv
    cmd = [PY, "-s", "-X", "utf8", SERVER_PY, "--engine", "strata", "--config", os.path.normpath(cfg), "--port", str(port)]
    if s["api_host"] not in ("127.0.0.1", "localhost"):
        cmd += ["--host", s["api_host"]]
    sv = subprocess.Popen(cmd, cwd=os.path.dirname(os.path.dirname(SERVER_PY)), stdout=open(f"{ROOT}/server.out", "w"), stderr=subprocess.STDOUT,
                          env=child_env, creationflags=0x00000200 | 0x08000000)
    H.remember("engine", sv.pid, port, real=True)
    return sv


JSON_OUT = False


def main(argv=None):
    """sync up の本体（11/15 app1115 で INTERFACE.md の 3 に合わせた）．
    窓は --open のときだけ開く（窓を開くのはアプリの枠の仕事）．設定は settings.json → 引数の順で上書き，auto は PC を調べて決める"""
    ap = argparse.ArgumentParser(prog="sync up")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--gui", action="store_true", help="エンジン＋dsh（既定．窓は開かない）")
    mode.add_argument("--no-gui", action="store_true", help="エンジン＋dsh（--gui と同じ．スマホから使う人向けの名前）")
    mode.add_argument("--api-only", action="store_true", help="エンジンだけ（dsh も会話の画面も起こさない）")
    ap.add_argument("--open", action="store_true", help="起こした後に会話の画面を Edge の窓で開く（端末から直接使う人向け）")
    ap.add_argument("--json", action="store_true", help="終わりに結果を 1 行の JSON で（途中の表示は標準エラーへ）")
    ap.add_argument("--preset", default=None, choices=("speed", "quality", "auto"), help="quality＝--tail-skip 7，speed＝--tail-skip 4 の別名")
    ap.add_argument("--tail-skip", default=None, help="起動時の tail skip 4・7・10（10＝省かない）か auto（PC のスペックで推奨の方）")
    ap.add_argument("--model", "--pack", dest="model", default=None, help="auto か一覧のモデルの id")
    ap.add_argument("--ram-max-gib", default=None)
    ap.add_argument("--vram-reserve-mib", default=None)
    ap.add_argument("--ram-squeeze", default=None, choices=("auto", "off"), help="起動・切り替えのときにほかのアプリの RAM を追い出すか（11/16 係 S4．auto＝追い出す）")
    ap.add_argument("--context", default=None)
    ap.add_argument("--kv", "--kv-format", dest="kv_format", default=None, help="会話の記憶（K/V）の量子化 k8v4・k8・k4 か auto（11/15 係 C）")
    ap.add_argument("--port", default=None, help="エンジン（API）の番号（設定 api_port）")
    ap.add_argument("--host", default=None, help="待ち受ける番地．127.0.0.1 以外には --api-key か環境変数 STRATA_API_KEY が要る")
    ap.add_argument("--api-key", default="", help="API の鍵（環境変数 STRATA_API_KEY で渡すのを勧める）")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--engine", default=ENGINE)
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--stop", action="store_true", help="（前からの名前）エンジンを止める．sync down --engine と同じ")
    a = ap.parse_args(argv)
    global PORT, JSON_OUT
    JSON_OUT = a.json
    try:
        s = H.effective({"preset": a.preset, "tail_skip": a.tail_skip, "model": a.model, "ram_max_gib": a.ram_max_gib, "vram_reserve_mib": a.vram_reserve_mib,
                         "context": a.context, "api_port": a.port, "api_host": a.host, "ram_squeeze": a.ram_squeeze})
        H._sync_ctx.cli_kv(s, a.kv_format, H)   # 11/15 係 C: --kv
    except (ValueError, KeyError) as e:
        say(f"設定が正しくありません: {e}")
        return 2
    PORT = s["api_port"]
    want = "auto" if s["model"] in (None, "auto") else s["model"]
    gui = not a.api_only
    key = a.api_key or os.environ.get("STRATA_API_KEY", "")
    result = {"ok": False, "mode": "api-only" if a.api_only else "gui", "settings": s}

    def done(code, **more):
        result.update(more, ok=code == 0, code=code)
        if JSON_OUT:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        return code

    import sync_env      # 11/15 夜: 対応外の PC では起こさずに理由を返す（終了コード 8．アプリの枠の「起動の失敗」に出る）
    ev = sync_env.check()
    if not ev["ok"]:
        for it in ev["blockers"]:
            say("この PC では使えません: " + sync_env.text(it))
        envj = {k: ev[k] for k in ("ok", "blockers", "warnings")}
        if gui and not a.no_gui and not a.dry:
            # 11/15 夜: --gui は dsh と中継だけ起こし，会話の画面（/m/env）で理由を見せる（エンジンは起こさない．初回のモデルなしと同じ扱い）
            ok = H.start_dsh(s, say)
            url = f"http://127.0.0.1:{s['relay_port']}/m/"
            if ok and a.open:
                say("  " + open_gui(url=H.gui_url(s)))
            return done(0 if ok else 6, unsupported=True, engine=None, engine_started=False, env=envj, url=url,
                        **({} if ok else {"error": H.DSH_ERROR or "dsh か会話の画面の中継が起きませんでした"}))
        return done(sync_env.EXIT_UNSUPPORTED, error="unsupported", env=envj)
    for it in ev["warnings"]:
        say("  ！" + sync_env.text(it))
    if s["api_host"] not in ("127.0.0.1", "localhost", "::1") and not key:
        say("127.0.0.1 以外で待ち受けるには鍵が要ります（--api-key か 環境変数 STRATA_API_KEY）．")
        return done(2)
    os.makedirs(ROOT, exist_ok=True)
    if a.stop:
        return done(stop_engine(PORT))
    if health() and not a.dry:
        say("Strata はもう動いています．")
        for line in api_info(s["api_host"], PORT, bool(key)):
            say(line)
        if gui:
            if not H.start_dsh(s, say):
                return done(6, error=H.DSH_ERROR or "dsh か会話の画面の中継が起きませんでした")
            if a.open:
                say("  " + open_gui(url=H.gui_url(s)))
        return done(0, engine="already-up", url=f"http://127.0.0.1:{s['relay_port']}/m/" if gui else None)
    # 11/15 app1115: はじめて（モデルか共通の部品が無い）: GUI なら dsh と会話の画面だけ起こす（画面がダウンロードの案内を出す）
    ms = H.models_state()
    if not ms["installed"] or ms["missing_shared"]:
        say(f"まだ入っていない物があります（モデル: {', '.join(ms['installed']) or 'なし'}，足りない共通の部品: {', '.join(ms['missing_shared']) or 'なし'}）．")
        if gui and not a.dry:
            ok = H.start_dsh(s, say)
            url = f"http://127.0.0.1:{s['relay_port']}/m/"
            if ok and a.open:
                say("  " + open_gui(url=H.gui_url(s)))
            say(f"  会話の画面（{url}）でダウンロードしてから，起動してください．" if ok else "  dsh が起きませんでした．")
            return done(0 if ok else 6, first_run=True, engine=None, missing=ms, url=url,
                        **({} if ok else {"error": H.DSH_ERROR or "dsh か会話の画面の中継が起きませんでした"}))
        return done(4, first_run=True, error="モデルか共通の部品がまだありません（sync up --gui で画面を開いてダウンロード）", missing=ms)
    sq = apply_squeeze(s, a.dry)       # 11/16 係 S4: 追い出した後の空き RAM で，下の PC の調べ（RAM の枠）が決まる
    result["squeeze"] = {k: sq.get(k) for k in ("ran", "before_gib", "after_gib", "freed_gib", "seconds", "detail")}
    say("1/5 PC を調べています（10 秒ほど）...")
    pre = wintune.preflight(PACKS[0]["dir"] if PACKS else None, do_ssd=False)
    if "error" in pre:
        say("調べられませんでした: " + pre["error"])
        return done(3, error=pre["error"])
    if not pre.get("gpus") and ev["gpu"].get("vendor") == "amd":
        # 11/15 夜: Radeon には nvidia-smi が無い．VRAM は表示アダプターの欄の大きさから，空きは 1.5 GiB 引いた見込み（不明なら 0＝全部 RAM に），
        # 画面はこの GPU につないでいる（予約を多めに）と見て，控えめな側に決める
        vg = ev["gpu"].get("vram_gib")
        pre["gpus"] = [{"name": ev["gpu"].get("name"), "display_active": "Enabled", "vram_free_mib": max(0, (float(vg) - 1.5) * 1024) if vg else 0,
                        "assumed": True}]
        say(f"  ・Radeon（{ev['gpu'].get('name')}）: VRAM {vg if vg else '不明'} GiB として控えめに決めます")
    pick, why = choose(pre, s["preset"] or "quality", want, s["ram_max_gib"], s["vram_reserve_mib"])
    # 11/15: 起動時の tail skip: 設定・引数の tail_skip → preset（7・4 の別名）→ PC のスペックで推奨（R4 か R7）
    sp = None
    if s["tail_skip"]:
        R, rwhy = int(s["tail_skip"]), "指定どおり"
    elif s["preset"]:
        R, rwhy = R_OF[s["preset"]], f"preset {s['preset']} の別名"
    else:
        sp = H.spec()
        R, rwhy = sp["recommended_r"], sp["reason"]
    if pick:
        pick["R"] = R
    why.append(f"起動時の tail skip は R{R}{'（省かない）' if R == 10 else ''}（{rwhy}）．API を別のソフトから使うときだけ効く（dsh の会話は会話ごとのモデルに従う）")
    if sq.get("why"):
        why.insert(1, sq["why"])
    elif sq.get("detail") and s.get("ram_squeeze") == "off":
        why.insert(1, "ほかのアプリの RAM は追い出していません（設定 ram_squeeze が off）")
    for w in why:
        say("  ・" + w)
    notes = [x for x in pre.get("advice", []) if not x.startswith("Sync-M は") and not x.startswith("ただし")]
    for x in notes:
        say("  ！" + x)
    rec = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "preset": s["preset"], "pick": pick, "why": why, "advice": notes,
           "ram": pre.get("ram"), "gpu": (pre.get("gpus") or [{}])[0], "settings": s}
    if pick is None:
        json.dump(rec, open(f"{ROOT}/last.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return done(4, error="手元にモデルがありません", why=why, first_run=True)
    pick["kv_format"] = s.get("kv_format")   # 11/15 係 C
    cfg, log = make_config(pick, a.engine, a.env, s["context"])
    rec.update(config=cfg, download_if_missing=download_plan(pick))
    json.dump(rec, open(f"{ROOT}/last.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    picked = {"model": pick["id"], "r": pick["R"], "ram_budget_gib": pick["budget"], "vram_reserve_mib": pick["reserve"], "why": why}
    if a.dry:
        say(f"（--dry: 起動しません．設定は {cfg}）")
        if gui:
            say(f"  dsh {'動いている' if listening(s['dsh_port']) else '止まっている'}，会話の画面の中継（{s['relay_port']}）"
                f"{'動いている' if listening(s['relay_port']) else '止まっている'}．--open なら: {open_gui(dry=True, url=H.gui_url(s))}")
        return done(0, dry=True, pick=picked, config=cfg)
    save_choice(pick, s["relay_port"])
    say("2/5 dsh は起こしません（--api-only）" if not gui else "2/5 dsh を起こしています...")
    if gui:
        ok = H.start_dsh(s, say)
        say("  dsh: " + ("動いています" if ok else "起きませんでした"))
        if not ok:      # 11/16: dsh が起きない（番号を別のプログラムが使っているなど）ならエンジンは起こさずに理由を返す
            return done(6, error=H.DSH_ERROR or "dsh か会話の画面の中継が起きませんでした", pick=picked)
    say(f"3/5 {pick['name']} を読み込んでいます（30 秒〜2 分）...")
    t0 = time.time()
    H._sync_ctx.note_start(cfg, log)   # 11/15 係 C: 起こす設定と記録の大きさ（この起動の K/V の WARNING を探すため）
    sv = start_engine(cfg, s, key)
    while time.time() - t0 < 420 and not health():
        if sv.poll() is not None:
            break
        time.sleep(1)
    lp = learned_profile(pick["id"])
    if not health() and os.path.exists(lp) and not os.environ.get("SYNC_NO_PROFILE_RETRY"):
        # 11/16: 学習した並びでエンジンが起きなかった．その物を退けて，本家の並びでもう 1 回だけ起こす
        bad = lp + time.strftime(".bad-%m%d-%H%M%S")
        try:
            H.stop("engine")
            os.replace(lp, bad)
            say(f"  学習した専門家の並びで起きなかったので，それを退けて（{os.path.basename(bad)}）本家の並びで起こし直します")
            t0 = time.time()
            sv = start_engine(cfg, s, key)
            while time.time() - t0 < 420 and not health():
                if sv.poll() is not None:
                    break
                time.sleep(1)
        except OSError:
            pass
    if not health():
        say("  起動できませんでした．記録: " + log)
        return done(5, error="エンジンが起きませんでした", log=log, pick=picked)
    fake = bool(os.environ.get("SYNC_ENGINE_CMD"))
    text = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    m = re.search(r"resident ([\d.]+) GiB, pinned ([\d.]+) GiB", text)
    say(f"  読み込み {time.time() - t0:.0f} 秒" + (f"，RAM の写し {m.group(1)} GiB（GPU から読める固定 {m.group(2)} GiB）" if m else ""))
    if not fake:
        say("4/5 落ち着くのを待って，温めています...")
        ts = time.time()
        pr = av = None
        while time.time() - ts < 120:
            pr, av = page_reads()
            if pr is not None and pr < 300:
                break
        start = os.path.getsize(log)
        warm(pick["R"], key)
        warm(pick["R"], key)
        d = wintune.diagnose(log, start)
        say("  " + (d.get("findings") or [d.get("error", "")])[0])
        rec.update(after={"page_reads_s": pr, "avail_mib": av, "diagnose": d})
        json.dump(rec, open(f"{ROOT}/last.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for line in api_info(s["api_host"], PORT, bool(key)):
        say(line)
    if not gui:
        say("5/5 API だけ起こしました．止めるのは: sync down --engine")
        return done(0, pick=picked)
    url = f"http://127.0.0.1:{s['relay_port']}/m/"
    if not listening(s["relay_port"]):
        say(f"  会話の画面の中継（{s['relay_port']}）が動いていません．")
        return done(6, error="会話の画面の中継が動いていません", pick=picked)
    if a.open:
        say("5/5 " + open_gui(url=H.gui_url(s)))
    else:
        say(f"5/5 起きました．会話の画面: {url}（窓は開いていません．開くのは --open か sync gui-url の URL）")
    if pre["ram"]["total_gib"] <= 33:
        say("  ヒント: この PC は RAM が 32 GB 以下です．会話の画面はスマホ・タブレットから開くほうが速くなります（PC のブラウザーが RAM と GPU を使うため）．")
    return done(0, pick=picked, url=url)


if __name__ == "__main__":
    sys.exit(main())
