#!/usr/bin/env python3
"""起動の道具の出力の言語（11/17 I-10）．文字だけの画面（Linux の TERM=linux のコンソール）は日本語を描けず全部化けるので，英語にする．

判定（use_en）: 環境変数 SYNC_LANG=en|ja が最優先．無ければ，Windows 以外で TERM が linux・dumb・vt100・vt220・cons25 のとき英語．
              それ以外（普通の端末・Windows）は日本語のまま．コマンドの引数 --lang en|ja（sync.py が先に読んで SYNC_LANG に入れる）でも切り替えられる．
英語の文: 作りは「日本語の行 → 英語の行」の正規表現の表（RULES）．書いたコードの日本語の文はそのまま残し，出す直前（say・print）にここを通す．
          表に無い行は，ASCII の部分（コマンド・数字・パス）だけ残して先頭に [ja only] を付ける（化けた文字を出さない）．
          新しい日本語の文を足したら，ここの RULES に英語を 1 行足す（足さなくても動く）．
"""
import os, re

IS_WIN = os.name == "nt"
_TERMS = ("linux", "dumb", "vt100", "vt220", "cons25")


def use_en():
    v = (os.environ.get("SYNC_LANG") or "").strip().lower()
    if v.startswith("en"):
        return True
    if v.startswith("ja"):
        return False
    return (not IS_WIN) and (os.environ.get("TERM") or "").strip().lower() in _TERMS


def lang():
    return "en" if use_en() else "ja"


def set_from_argv(argv):
    """--lang en|ja（無ければ何もしない）を SYNC_LANG に入れる．引数の並びは変えない"""
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            os.environ["SYNC_LANG"] = argv[i + 1]
        elif a.startswith("--lang="):
            os.environ["SYNC_LANG"] = a.split("=", 1)[1]


N = r"(-?[\d.,]+)"          # 数
S = r"(.+?)"                # 文字（短く）
# (日本語の行の全体に合う正規表現, 英語)．英語の \1 \2 は取った部分．行頭の空白と記号（・！×）は，外してから照らして，付け直す
RULES = [
    (r"1/5 PC を調べています（10 秒ほど）\.\.\.", r"1/5 Checking this PC (about 10 s)..."),
    (r"2/5 dsh は起こしません（--api-only）", r"2/5 Not starting dsh (--api-only)"),
    (r"2/5 dsh を起こしています\.\.\.", r"2/5 Starting dsh..."),
    (r"dsh: 動いています", r"dsh: running"),
    (r"dsh: 起きませんでした", r"dsh: did not start"),
    (r"3/5 (.+) を読み込んでいます（30 秒〜2 分）\.\.\.", r"3/5 Loading \1 (30 s to 2 min)..."),
    (r"4/5 落ち着くのを待って，温めています\.\.\.", r"4/5 Waiting for things to settle, then warming up..."),
    (r"読み込み " + N + r" 秒，RAM の写し " + N + r" GiB（GPU から読める固定 " + N + r" GiB）", r"Loaded in \1 s, RAM copy \2 GiB (pinned for GPU \3 GiB)"),
    (r"読み込み " + N + r" 秒", r"Loaded in \1 s"),
    (r"5/5 API だけ起こしました．止めるのは: (.+)", r"5/5 The API is up (engine only). To stop: \1"),
    (r"5/5 起きました．会話の画面: (\S+)（窓は開いていません．開くのは --open か sync gui-url の URL）", r"5/5 Up. Chat page: \1 (no window opened; use --open or the URL from sync gui-url)"),
    (r"5/5 会話の画面を (.+) で開きました", r"5/5 Opened the chat page in \1"),
    (r"起動できませんでした．記録: (.+)", r"The engine did not start. Log: \1"),
    (r"Strata はもう動いています．", r"Strata is already running."),
    # 11/18 W12: ふさがっている番号の付け替え
    (r"番号 (\d+)（エンジン）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (engine) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（エンジン）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (engine) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（会話の中継）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (chat proxy) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（会話の中継）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (chat proxy) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（dsh）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (dsh) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（dsh）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (dsh) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（会話の画面の中継）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (chat page relay) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（会話の画面の中継）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (chat page relay) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（エンジン）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (engine) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（エンジン）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (engine) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（会話の中継）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (chat proxy) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（会話の中継）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (chat proxy) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（dsh）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (dsh) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（dsh）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (dsh) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（会話の画面の中継）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (chat page relay) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（会話の画面の中継）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (chat page relay) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（エンジン）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (engine) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（エンジン）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (engine) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（会話の中継）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (chat proxy) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（会話の中継）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (chat proxy) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（dsh）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (dsh) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（dsh）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (dsh) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（会話の画面の中継）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (chat page relay) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（会話の画面の中継）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (chat page relay) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（エンジン）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (engine) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（エンジン）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (engine) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（会話の中継）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (chat proxy) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（会話の中継）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (chat proxy) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（dsh）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (dsh) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（dsh）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (dsh) overlaps another part, so \2 is used instead."),
    (r"番号 (\d+)（会話の画面の中継）はほかのプログラムが使っているので，(\d+) にしました．", r"Port \1 (chat page relay) is used by another program, so \2 is used instead."),
    (r"番号 (\d+)（会話の画面の中継）がほかの部品と重なっているので，(\d+) にしました．", r"Port \1 (chat page relay) overlaps another part, so \2 is used instead."),
    (r"ヒント: この PC は RAM が 32 GB 以下です．.*", r"Tip: this PC has 32 GB of RAM or less. Open the chat page from a phone or tablet (a browser on this PC uses RAM and the GPU)."),
    (r"空き RAM " + N + r" GiB（エンジンに " + N + r"，余白 " + N + r" を除くと専門家に " + N + r" GiB），VRAM の席 約 " + N + r" GiB，画面は(この GPU|別／なし)（予約 (\d+) MiB）",
     r"Free RAM \1 GiB (\4 GiB for experts after \2 for the engine and \3 margin), about \5 GiB of VRAM for expert slots, display on \6 (VRAM reserve \7 MiB)"),
    (r"pack は指定どおり (.+)", r"Model as requested: \1"),
    (r"積んでいる RAM (\d+) GB（見える量 " + N + r" GiB） なので (.+)（RAM (\d+) GB 向け）", r"Installed RAM \1 GB (visible \2 GiB), so \3 (meant for RAM \4 GB)"),
    (r"見える RAM " + N + r" GiB（積んでいる量は読めなかった） なので (.+)（RAM (\d+) GB 向け）", r"Visible RAM \1 GiB (installed amount unknown), so \2 (meant for RAM \3 GB)"),
    (r"積んでいる RAM (\d+) GB（見える量 " + N + r" GiB），VRAM " + N + r" GiB（(.+) は VRAM (\d+) GB 以上向け） なので (.+)（RAM (\d+) GB 向け）",
     r"Installed RAM \1 GB (visible \2 GiB), VRAM \3 GiB (\4 needs VRAM \5 GB or more), so \6 (meant for RAM \7 GB)"),
    (r"見える RAM " + N + r" GiB（積んでいる量は読めなかった），VRAM " + N + r" GiB（(.+) は VRAM (\d+) GB 以上向け） なので (.+)（RAM (\d+) GB 向け）",
     r"Visible RAM \1 GiB (installed amount unknown), VRAM \2 GiB (\3 needs VRAM \4 GB or more), so \5 (meant for RAM \6 GB)"),
    (r"(.+) に合う段のモデルが手元に無いので，手元のいちばん小さい (.+)", r"No model on this PC fits (\1); using the smallest one, \2"),
    (r"速度重視なので 1 つ小さい (.+)", r"Speed preset: one size smaller, \1"),
    (r"(.+) は全部 RAM と VRAM に載る（SSD に残る " + N + r"%）", r"\1 fits in RAM and VRAM (\2% left on the SSD)"),
    (r"いまは空き RAM が足りず，(.+) の専門家の " + N + r"%（" + N + r" GiB）が SSD に残る（.*", r"Not enough free RAM now: \2% of \1's experts (\3 GiB) stay on the SSD (conversations wait on the SSD and get slower). Closing apps frees RAM. Not switching to a smaller model."),
    (r"RAM の枠は設定どおり " + N + r" GiB まで", r"RAM budget capped at \1 GiB by your setting"),
    (r"VRAM の予約は設定どおり " + N + r" MiB", r"VRAM reserve set to \1 MiB by your setting"),
    (r"RAM の枠 " + N + r" GiB，輪なし", r"RAM budget \1 GiB, no ring"),
    (r"起動時の tail skip は R(\d+)(?:（省かない）)?（.*）．API を別のソフトから使うときだけ効く.*", r"Tail skip at start: R\1 (matters only when another program uses the API; dsh chats follow the per-chat model)"),
    (r"ほかのアプリの RAM を追い出しています（10〜30 秒ほど．アプリは閉じません）\.\.\.", r"Pushing other apps' RAM out to disk (10-30 s; no app is closed)..."),
    (r"ほかのアプリの RAM は追い出していません（設定 ram_squeeze が off）", r"Other apps' RAM was not pushed out (setting ram_squeeze is off)"),
    (r"1 窓 " + N + r" ms = GPU の待ち " + N + r" \+ CPU 側 " + N + r"（計画 " + N + r"・量子化 " + N + r"・SSD の待ち " + N + r"・専門家 " + N + r"）\s*\+ 下書き " + N + r" \+ ほか " + N + r"．1 窓で " + N + r" トークン（下書きの当たり " + N + r"%）→ " + N + r" tok/s．",
     r"1 window \1 ms = GPU wait \2 + CPU side \3 (plan \4, quantize \5, SSD wait \6, experts \7) + draft \8 + other \9. \10 tokens per window (draft hit \11%) -> \12 tok/s."),
    (r"API: (\S+)   モデル名: (\S+)", r"API: \1   model name: \2"),
    (r"OpenAI 互換: (.+)", r"OpenAI-compatible: \1"),
    (r"Anthropic 互換: (.+)", r"Anthropic-compatible: \1"),
    (r"鍵: なし（何を入れても通る）．送り方は (.+)", r"Key: none (anything is accepted). Send it as \1"),
    (r"鍵: 起動のときに渡した鍵（環境変数 STRATA_API_KEY）．送り方は (.+)", r"Key: the one given at start (environment variable STRATA_API_KEY). Send it as \1"),
    (r"多くのハーネスは環境変数で: (.+)", r"Most harnesses take environment variables: \1"),
    (r"curl の例: (.+)", r"curl example: \1"),
    (r"日本語を curl で送るとき.*", r"Sending Japanese with curl (Windows): put the body in a UTF-8 file and use --data-binary @body.json."),
    (r"速さと品質を依頼ごとに変える: 本文に (.+)", r"Per-request speed/quality: put \1 in the body (4 = speed, 7 = quality, 0 = off; default is the preset at start)"),
    (r"まだ入っていない物があります（モデル: (.+)，足りない共通の部品: (.+)）．", r"Some parts are not installed yet (models: \1; missing shared parts: \2)."),
    (r"手元にモデルがありません", r"No model on this PC"),
    (r"設定が正しくありません: (.+)", r"Invalid setting: \1"),
    (r"この PC では使えません: (.+)", r"This PC is not supported: \1"),
    (r"調べられませんでした: (.+)", r"Could not check this PC: \1"),
    (r"学習した専門家の並びで起きなかったので，それを退けて（(.+)）本家の並びで起こし直します", r"Did not start with the learned expert order; set it aside (\1) and restarting with the default order"),
    (r"（--dry: 起動しません．設定は (.+)）", r"(--dry: not starting. Config: \1)"),
    (r"127\.0\.0\.1 以外で待ち受けるには鍵が要ります.*", r"A key is required to listen on anything other than 127.0.0.1 (--api-key or environment variable STRATA_API_KEY)."),
    # 11/17 G・F（画面の文．design-GF-1117.md の 4 章）
    (r"メモリの枠を " + N + r" GiB から " + N + r" GiB に下げました。Windows のメモリの上限（コミット）の空きが " + N + r" GiB しかないためです。",
     r"Lowered the memory budget from \1 GiB to \2 GiB: only \3 GiB is left under the Windows commit limit (RAM plus page file)."),
    (r"専門家の " + N + r"% が SSD に残ります。会話が遅くなることがあります。", r"\1% of the experts stay on the SSD. Conversations may be slower."),
    (r"ページファイルを「システム管理」にすると、枠を戻せます。(?:（いまは " + N + r" GiB）)?", r"Setting the page file to 'System managed' lets the budget go back up. (now \1 GiB)"),
    (r"コミットの多いアプリを閉じても戻せます。(.+)。", r"Closing apps that use a lot of commit also helps: \1."),
    (r"会話を預ける場所が取れないため、別の会話から戻ると、最初から読み直します。",   # 11/18 E1
     r"There is no room to keep conversations, so going back from another conversation reads it again from the start."),
    (r"Windows のメモリの上限（コミット）が足りないため、会話を預ける場所を空けて、もう一度起動します。",   # 11/18 E1
     r"The Windows commit limit is short, so starting again with room kept for parked conversations."),
    (r"VRAM が少ないので、予約を " + N + r" MiB にしました。", r"VRAM is small, so the reserve is now \1 MiB."),
    (r"文脈の長さが前回の (\d+) から (\d+) に変わっています。", r"The context length changed from \1 (last time) to \2."),
    (r"エンジンの警告: コミットの上限に近づいています。ページファイルを大きくしてください。", r"Engine warning: close to the commit limit. Please enlarge the page file."),
    (r"エンジンの警告: GPU のメモリの空きがありません。VRAM の予約を増やすと安定します。", r"Engine warning: no GPU memory is free. A larger VRAM reserve is more stable."),
    (r"メモリの枠は " + N + r" GiB を頼みましたが、エンジンは " + N + r" GiB しか取れませんでした。", r"Asked for a \1 GiB memory budget, but the engine got only \2 GiB."),
    (r"席が (\d+) 個です。このまま使いますが、遅くなります。", r"Only \1 GPU slots. Using it as is; it will be slow."),
    (r"(遅い起動（GPU の席 \S+ 個）|起動に失敗)（(\d+)/(\d+)）。(もう一度やり直します。|GPU のメモリが空くのを待ちます。)",
     r"\1 (\2/\3). \4"),
    (r"GPU のメモリの空きは " + N + r" MiB です（" + N + r" 秒待ちました）。", r"GPU memory free: \1 MiB (waited \2 s)."),
    (r"GPU のメモリの空きは調べられませんでした。", r"Could not read the GPU memory free."),
    (r"設定を少し緩めて、もう一度起動します。(.*)", r"Loosening the settings a little and starting again. \1"),
    (r"(\d+) 回やっても起動できませんでした。試した内容: (.+)。", r"Could not start after \1 tries. Tried: \2."),
    # wintune の勧め
    (r"RAM が 32 GB 以下: 会話の画面は.*", r"RAM is 32 GB or less: open the chat page from a phone or tablet. A browser on this PC uses 1-3 GiB of RAM, and drawing on the same GPU slows decode."),
    (r"閉じると RAM が戻るもの: (.+)", r"Closing these gives RAM back: \1"),
    (r"ページファイルがモデルと同じ SSD にある.*", r"The page file is on the same SSD as the model: when RAM runs short, model reads and paging fight for that SSD."),
    (r"画面をこの GPU が映している.*?VRAM の予約は ([\d,]+) MiB.*", r"This GPU also drives the display: VRAM reserve is \1 MiB, and browser drawing uses the same GPU as decode."),
    (r"内蔵 GPU がある: .*", r"An integrated GPU exists: plug the monitor into the motherboard to free 0.5-1 GiB of VRAM and stop drawing from competing with decode."),
    (r"PCIe の幅が x(\d+): .*", r"PCIe width is x\1: the path for the GPU to read RAM experts is narrow (the automatic split sends more work to the CPU)."),
    (r"いまページの読み込みが毎秒 (\d+) 回ある.*", r"Page reads are \1 per second now (quiet is about 10): wait until it settles before starting or measuring."),
    (r"モデルの置き場が HDD: .*", r"The model folder is on an HDD: experts read from the disk make it slow. Putting the model on an SSD makes it faster."),
    # sync.py
    (r"止まっています（sync up で起こす）", r"Stopped (start with: sync up)"),
    (r"動いています: (\S+)  モデル (\S+)  画像 (可|不可)  鍵 (あり|なし)", r"Running: \1  model \2  images \3  key \4"),
    (r"エンジンを止めました．", r"Engine stopped."),
    (r"エンジンを止められませんでした（(.+)）", r"Could not stop the engine (\1)"),
    (r"止めました: (.+)", r"Stopped: \1"),
    (r"止めた dsh はありません（自分で起こした物が無い）", r"No dsh to stop (none was started by this tool)"),
    (r"止まっています．先に sync up --api-only（または sync up）", r"Stopped. Run sync up --api-only (or sync up) first."),
    (r"（空行か Ctrl-C で終わり）", r"(An empty line or Ctrl-C ends)"),
    (r"（いまは止まっています．sync up --api-only で API だけ起こせます）", r"(Stopped now. sync up --api-only starts just the API.)"),
    (r"Python（openai の部品）の例:", r"Python (openai package) example:"),
    (r"勧める pack: (.+)", r"Recommended model: \1"),
    (r"RAM (\S+) GiB（空き (\S+) GiB）／GPU (.+)（VRAM の空き (\S+) MiB，画面 (.+)）", r"RAM \1 GiB (\2 GiB free) / GPU \3 (VRAM free \4 MiB, display \5)"),
    (r"(\S+) = (.+)（次の起動から効きます）", r"\1 = \2 (takes effect from the next start)"),
    (r"使い方: sync settings get \[--json\] ／ sync settings set <名前> <値\|auto>", r"Usage: sync settings get [--json] / sync settings set <name> <value|auto>"),
    (r"Sync: Qwen3\.8-Flash-Next をこの PC で動かす（11/15 の試作）", r"Sync: run Qwen3.8-Flash-Next on this PC"),
    (r"1  始める（品質重視．会話の画面まで開く）", r"1  Start (quality; also opens the chat page)"),
    (r"2  始める（速度重視．会話の画面まで開く）", r"2  Start (speed; also opens the chat page)"),
    (r"3  API だけ始める（自分のハーネスをつなぐ人向け）", r"3  Start the API only (for your own harness)"),
    (r"4  止める（エンジンと，自分で起こした dsh）", r"4  Stop (the engine and the dsh this tool started)"),
    (r"5  状態を見る（動いているか・直近の速さ）", r"5  Status (running? recent speed)"),
    (r"6  PC の調べと勧め", r"6  Check this PC and advice"),
    (r"7  コマンドの使い方", r"7  How to use the commands"),
    (r"1〜7 の番号を入れてください．", r"Enter a number from 1 to 7."),
    (r"あなた> ", r"you> "),
]
PHRASES = [(r"遅い起動（GPU の席 (\S+) 個）", r"Slow start (\1 GPU slots)"), (r"起動に失敗", "Start failed"), (r"もう一度やり直します。", "Trying again."),
           (r"GPU のメモリが空くのを待ちます。", "Waiting for GPU memory to free up."), (r"VRAM の予約を (\d+) MiB から (\d+) MiB に", r"VRAM reserve \1 MiB -> \2 MiB"),
           (r"メモリの枠を ([\d.]+) GiB から ([\d.]+) GiB に", r"memory budget \1 GiB -> \2 GiB"), (r"設定は同じです。", "Same settings."),
           (r"(\d+) 回目 ", r"try \1: "), (r"同じ設定", "same settings"), (r"、", ", "), (r" ０ ", " "), (r" ／ ", "; "), (r"。$", "."), (r"<鍵>", "<key>"), (r" か ", " or "), (r"（stream 可）", " (streaming OK)"), (r"，(POST|GET) ", r", \1 "),
           (r"（Anthropic 形式なら (.+?)）", r" (for the Anthropic format: \1)"), (r"別／なし", "another GPU or none"), (r"この GPU", "this GPU")]
_PHR = [(re.compile(a), b) for a, b in PHRASES]
_RULES = [(re.compile(p + r"\Z", re.S), e) for p, e in RULES]
_JA = re.compile(r"[　-ヿ㐀-鿿＀-￯]")
_LEAD = re.compile(r"^(\s*(?:[・！×]\s*)?)(.*?)(\s*)$", re.S)
_BULLET = {"・": "* ", "！": "! ", "×": "x "}


def tr(s):
    """英語にする．日本語を含まない行・日本語の画面のときはそのまま返す（複数行は 1 行ずつ）"""
    if not isinstance(s, str) or not _JA.search(s):
        return s
    if "\n" in s.rstrip("\n"):
        return "\n".join(tr(x) for x in s.split("\n"))
    m = _LEAD.match(s)
    lead, body, tail = m.group(1), m.group(2), m.group(3)
    lead = re.sub(r"[・！×]\s*", lambda x: _BULLET[x.group(0)[0]], lead)
    for rx, en in _RULES:
        mm = rx.match(body)
        if mm:
            out = mm.expand(en)
            for pr, rep in _PHR:
                out = pr.sub(rep, out)
            if _JA.search(out):          # 取った部分に日本語（アプリの説明など）が残るとき: 日本語の（）を落とし，まだ残れば残りの日本語を落とす
                out = re.sub(r"\s*（[^）]*）", "", out)
                out = re.sub(r"\s+", " ", _JA.sub("", out)).strip()
            return lead + out + tail
    # 表に無い行: 日本語の部分を落とし，ASCII の部分（コマンド・数字・パス）だけ残す
    skel = re.sub(r"\s+", " ", _JA.sub(" ", body)).strip(" .,;:()")
    if re.search(r"[A-Za-z0-9]{3,}", skel):
        return lead + "[ja only] " + skel + tail
    return lead + "[message in Japanese; set SYNC_LANG=ja on a terminal that can show it]" + tail


def t(s):
    """say・print の入口．日本語の画面なら何もしない"""
    return tr(s) if use_en() else s
