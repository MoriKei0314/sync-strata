# コマンドの一覧（CLI）

[English](CLI.md) | 日本語

`sync` のコマンドは、GUI でできることと、ほかのソフトからつなぐための入口を端末から使うためのものです。

- Windows: `sync …`（スタートメニューのコマンド、またはアプリの置き場の `sync.cmd`）。
- Linux: `./sync.sh …`（アプリの置き場の `sync.sh`）。中身は Windows の `sync` と同じです。
- 引数なしの `sync` は、番号で選ぶ簡単なメニューを出します（始める・API だけ・止める・状態・PC の調べ・使い方）。
- 一覧は `sync help`（`-h`・`--help`）でも出ます。
- どのコマンドにも `--lang en|ja` を付けると、表示の言葉を選べます（付けなければ日本語です。文字だけの端末 `TERM=linux` では英語です。環境変数 `SYNC_LANG` でも決められます）。

以下の例は Windows の書き方です。Linux は `sync` を `./sync.sh` に読み替えてください。

## コマンドの早見表

| コマンド | 何をするか |
|---|---|
| [`sync up`](#sync-up) | エンジンと dsh を起こします |
| [`sync down`](#sync-down) | 止めます |
| [`sync status`](#sync-status) | 動いているか、モデル、直近の速さ |
| [`sync settings`](#sync-settings) | 設定を見る・変える |
| [`sync ctx`](#sync-ctx) | コンテキストの設定と、使える長さ |
| [`sync gui-url`](#sync-gui-url) | 会話の画面の URL |
| [`sync api`](#sync-api) | ほかのソフトからのつなぎ方（番地・モデル名・例） |
| [`sync chat`](#sync-chat) | 端末で会話します |
| [`sync doctor`](#sync-doctor) | PC の状態と勧め |
| [`sync env`](#sync-env) | この PC で使えるかどうか |
| [`sync mem`](#sync-mem) | いまのメモリの様子 |
| [`sync remote-url` と `sync remote-apply`](#sync-remote-url-と-sync-remote-apply) | スマホの接続 |
| [`sync update`](#sync-update) | 更新を調べる・更新する |

## `sync up`

エンジンと dsh を起こします。設定は「`settings.json` → 引数」の順で決まり、`auto` の項目は PC を調べて決めます。何も付けなければ、エンジンと dsh（と会話の画面の中継）を起こします。窓は開きません。

```
sync up [--gui | --no-gui | --api-only] [--open] [--json]
        [--preset speed|quality|auto] [--tail-skip 4|7|10|auto]
        [--model auto|<モデルの名前>]   （別名 --pack）
        [--ram-max-gib N] [--vram-reserve-mib N] [--ram-squeeze auto|off]
        [--context N] [--kv k8v4|k8|k4|auto]   （別名 --kv-format）
        [--port N] [--host 番地] [--api-key 鍵]
        [--env 名前=値 ...] [--engine エンジンの exe] [--dry] [--stop]
```

| 引数 | 説明 |
|---|---|
| `--gui`・`--no-gui` | エンジンと dsh を起こします（窓は開きません）。2 つは同じ動きで、スマホから使う人向けに `--no-gui` の名前もあります。何も付けないときと同じです |
| `--api-only` | エンジンだけ起こします（dsh も会話の画面も起こしません）。ほかのソフトからつなぐ人向けです。`--gui`・`--no-gui` とは同時に使えません |
| `--open` | 起こした後に、会話の画面を窓で開きます |
| `--json` | 終わりに結果を 1 行の JSON で出します（途中の表示は標準エラーへ） |
| `--preset` | `quality`（tail skip R7）か `speed`（R4）。`--tail-skip` の別名です |
| `--tail-skip` | 起動時の tail skip。`4`・`7`・`10`（10 は省かない）か `auto`（PC に合わせて R4 か R7）。API を別のソフトから使うときだけ効きます（dsh の会話は会話ごとのモデルに従います） |
| `--model`（`--pack`） | `auto` か、一覧にあるモデルの名前（例: `sync-s`） |
| `--ram-max-gib` | モデルの写しに使う RAM の上限（GiB） |
| `--vram-reserve-mib` | ほかのアプリのために空けておく VRAM（MiB） |
| `--ram-squeeze` | 起動のときにほかのアプリの RAM を追い出すか。`auto`（既定。追い出す）か `off` |
| `--context` | 文脈の長さ（トークン） |
| `--kv`（`--kv-format`） | 会話の記憶（K/V）の量子化。`k8v4`・`k8`・`k4`・`auto` |
| `--port` | エンジン（API）の番号（設定 `api_port`） |
| `--host` | 待ち受ける番地（設定 `api_host`）。`127.0.0.1` 以外にするときは鍵が要ります（[API.ja.md](API.ja.md)） |
| `--api-key` | API の鍵。画面に残らないよう、環境変数 `STRATA_API_KEY` で渡すことを勧めます |
| `--env 名前=値` | エンジンに渡す環境変数を足します（何回でも書けます） |
| `--engine` | 起動するエンジンの実行ファイルを指定します（ふだんは要りません） |
| `--dry` | 起こさずに、決めた設定だけを出します |
| `--stop` | 前からある名前で、エンジンを止めます（`sync down --engine` と同じ） |

ふさがっている番号は、空いている番号に自動で替わります。既定の番号（エンジン 8080・中継 8081・dsh 3080・会話の画面 3081）をほかのプログラムが使っていると、近くの空いている番号を選んで `settings.json` に書き、「番号 8080（エンジン）はほかのプログラムが使っているので，8082 にしました．」のように出します。実際の番号は `sync api` と `sync status` で分かります。

終了コード: `0` 成功、`2` 設定や引数が正しくない（`127.0.0.1` 以外の待ち受けで鍵が無い場合も）、`3` PC を調べられなかった、`4` モデルか共通の部品がまだ無い、`6` dsh か会話の画面の中継が起きなかった、`8` この PC では使えない。それ以外の 0 でない値は、エンジンの起動の失敗です。

例:

```
sync up                          # エンジンと dsh を起こす
sync up --api-only               # API だけ
sync up --open --preset speed    # 速度重視で起こし、会話の画面を開く
sync up --model sync-s --context 131072
sync up --env 名前=値            # エンジンに環境変数を渡す
sync up --dry                    # 決めた設定だけを見る
```

## `sync down`

```
sync down [--all | --engine | --dsh] [--json]
```

| 引数 | 説明 |
|---|---|
| `--all` | エンジンと、自分で起こした dsh・中継を止めます（既定） |
| `--engine` | エンジンだけ止めます（dsh は残ります） |
| `--dsh` | dsh と中継だけ止めます（エンジンと API は残ります） |
| `--json` | 結果を 1 行の JSON で出します |

dsh は、`sync up` やアプリが自分で起こした物だけを止めます。そのほかの dsh には触れません。

## `sync status`

```
sync status [--json] [--port N]
```

動いているか、モデル、画像の可否、鍵の有無、直近の速さの様子を出します。止まっているときは「止まっています」と出して終了コード 1 を返します。`--json` は、エンジン・dsh・中継・入っているモデル・設定・初回かどうか・対応環境・コンテキストの 1 行の JSON です（番号もここにあります）。

## `sync settings`

```
sync settings get [--json]
sync settings set <名前> <値|auto> [--json]
```

設定（`settings.json`）を見る・変えます。変えた値は次の起動から効きます。名前の一覧と意味は [SETTINGS.ja.md](SETTINGS.ja.md) にあります。

```
sync settings get
sync settings set tail_skip 4
sync settings set context auto
sync settings set lan_remote lan
```

## `sync ctx`

```
sync ctx [--json]
```

コンテキストの長さ・K/V の量子化について、いまの設定・自動の値・実際に使っている値と、VRAM に入る組・「この設定だと約 N トークンまで」を出します。変えるのは `sync settings set context …` と `sync settings set kv_format …` です。

## `sync gui-url`

```
sync gui-url [--json]
```

会話の画面を開く URL を出します（自分で起こした dsh のときは、ログインを通す URL です）。`--json` は `{"url": "…"}` の形です。

## `sync api`

```
sync api [--port N] [--host 番地]
```

ほかのソフトからつなぐための案内を出します。番地とモデル名・鍵の送り方・環境変数の例・curl の例・Python（openai）の例です。番号は設定 `api_port` の実際の値（空いている番号に替わっていればそちら）が出ます。止まっているときは、`sync up --api-only` で起こせると知らせます。

## `sync chat`

```
sync chat [--system 文] [--preset speed|quality] [--tail-skip N] [--port N]
```

端末でそのまま会話します（エンジンの API に直接つなぎます。先に `sync up --api-only` か `sync up` が要ります）。終わるのは、空行か Ctrl-C です。`--system` で最初の指示文を入れられます。tail skip は既定が R7 で、`--preset speed` で R4、`--tail-skip` で数を直接指定できます。返事のあとに tok/s が出ます。

## `sync doctor`

```
sync doctor [--ssd]
```

PC の状態と勧めを出します。RAM・GPU・勧めるモデル・対応環境の注意・閉じると速くなるアプリ・いま CPU や GPU を使っているほかのアプリです。`--ssd` を付けると、モデルを置いた SSD の速さも調べます。

## `sync env`

```
sync env [--json [--ascii]]
```

この PC で使えるかどうか（使えない理由・注意）を出します。終了コードは、使えれば `0`、使えなければ `8` です。`--json` は結果を 1 行の JSON で、`--ascii` は日本語を `\u` の形にします。

## `sync mem`

```
sync mem
```

いまのメモリの様子（RAM・コミット・VRAM、ほかのアプリの上位、Sync-Strata 自身の分）を、1 行の JSON で出します。画面の「メモリ」の欄の元です。調べられなかったときは終了コード 1 です。

## `sync remote-url` と `sync remote-apply`

```
sync remote-url [--json] [--pair]
sync remote-apply
```

スマホの接続（設定 `lan_remote`。[REMOTE.ja.md](REMOTE.ja.md)）のためのコマンドです。

| コマンド | 説明 |
|---|---|
| `sync remote-url` | スマホで開く URL を出します |
| `sync remote-url --pair` | 1 回きりの QR を端末に出します（3 分で切れます）。スマホで初めて開くときに使います |
| `sync remote-url --json` | 同じ内容を JSON で |
| `sync remote-apply` | 自分で起こした dsh と中継を起こし直して、設定を今すぐ効かせます（エンジンと会話の中継はそのままです） |

## `sync update`

```
sync update check [--json] [--local] [--source 置き場] [--root アプリの置き場]
sync update apply [--json] [--root アプリの置き場] [--no-close] [--no-relaunch] [--dry]
```

| コマンド | 説明 |
|---|---|
| `sync update check` | 何も落とさずに、新しい版があるか、変わる部品は何かを調べます。`--local` は、ネットを見ずに、いまの版だけを調べます |
| `sync update apply` | 切り離した係が、全部閉じる → 更新 → 起こし直す、を行います。窓（Linux で端末が無いときは記録のファイルだけ）に様子が出ます。`--no-close` は閉じず、`--no-relaunch` は起こし直しません。`--dry` は何もせず、やることだけを出します |

結果は JSON で出ます。更新のしくみと前の版への戻し方は [INSTALL.ja.md](INSTALL.ja.md) にあります。

## 環境変数

| 名前 | 説明 |
|---|---|
| `STRATA_API_KEY` | API の鍵。`sync up --host 0.0.0.0` のように `127.0.0.1` 以外で待ち受けるときは必須です。`sync status`・`sync api`・`sync chat` も、これを使ってエンジンに問い合わせます |
| `SYNC_LANG` | 表示の言葉（`en`・`ja`）。`--lang` が先です |
