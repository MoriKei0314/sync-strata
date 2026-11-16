<!-- 案（11/15 係 D）．<account> は新しいアカウントの名前に置き換える．〔要決定〕〔測定中〕の印は公開前に消す． -->

# Sync-Strata

[English](README.md) | 日本語

Sync-Strata は、Qwen3.8-Flash-Next（125B の MoE）を家庭の PC 1 台で動かすアプリです。
エンジンは [Strata](https://github.com/Niko1221/Strata) のフォークで、モデルは本家の Gyro より速く動くように量子化し直した **Sync-XS・Sync-S・Sync-M** を使います。
会話の画面（[dsh](https://www.npmjs.com/package/@deepseek-ai/dsh)）とエンジンが一緒に入っていて、GUI・スマホ・CLI・OpenAI 互換の API から使えます。

> **試験版です。** Windows と Linux、NVIDIA の RTX 30・40 系に対応しています（ほかの GPU は下の表）。モデルとエンジンの形式は本家 Strata や llama.cpp とは互換がありません。

## 要る PC

| 物 | 条件 |
|---|---|
| OS | Windows 11、Windows 10（1803 以降）、または 64 ビットの Linux（glibc 2.28 以降。Ubuntu 20.04・Debian 10・RHEL 8 以降など。作者の実機は Ubuntu 24.04 で、ほかのディストリビューションは未確認） |
| GPU | 下の「対応する GPU」の表 |
| NVIDIA のドライバー | R580 以上（CUDA 13。Linux は 580.95.05 以上）。GTX 10 系（CUDA 12 版）は Windows 576.57 以上・Linux 575.57.08 以上 |
| CPU | AVX2 が要ります。AVX-512 が無い CPU でも動きますが、会話の速さが 1 割ほど落ちます（作者の PC で AVX-512 を使わずに測った値） |
| RAM・VRAM | 〔要決定: 下限〕（モデルの選び方は下の表） |
| 空き容量 | アプリ 約 2 GB ＋ どのモデルにも要る共通の部品 約 35 GB ＋ モデル（Sync-XS 約 24 GB・Sync-S 約 28 GB・Sync-M 約 35 GB）。モデルは NVMe の SSD に置くことを勧めます |
| 管理者の権限・Python・Node | 要りません（アプリの中に入っています） |

### 対応する GPU

setup が PC の GPU を調べて、合うエンジンだけを落とします（Windows・Linux とも）。

| GPU | 状態 |
|---|---|
| NVIDIA RTX 30 系・40 系 | 対応 |
| NVIDIA RTX 20 系・GTX 16 系・RTX 50 系、A100 などのデータセンター向け（Ampere） | 動く見込み（実機では未確認） |
| NVIDIA GTX 10 系（CUDA 12 版のエンジン） | 試験的な機能（実機では未確認） |
| AMD Radeon RX 6000・7000・9000 系（HIP 版のエンジン） | 試験的な機能（実機では未確認） |
| AMD Ryzen AI Max の内蔵 Radeon（Strix Halo。8060S・8050S・8040S）。Windows・Linux とも | 試験的な機能（実機では未確認） |
| 上のほかの内蔵 GPU・Intel の GPU | 非対応（Windows の内蔵 Radeon は、文章の生成の最初で GPU が止まります。Linux でも、Strix Halo のほかの内蔵 Radeon は対応外です） |

## 入れ方

### Windows

1. [Releases](https://github.com/hiruhiru2005/sync-strata/releases) から `SyncStrata-<版>.zip` を落として展開します（道のりに日本語が入らない場所を勧めます）。
2. 中の `setup.cmd` をダブルクリックします。足りない物だけを入れるので、何度流しても同じ結果になります。
3. デスクトップの **Sync-Strata** を開きます。最初はモデルを入れる案内が出るので、勧められたモデルを選んでください（Hugging Face から落とします）。

### Linux

1. [Releases](https://github.com/hiruhiru2005/sync-strata/releases) から `SyncStrata-<版>-linux.zip` を落として展開します。
2. 端末で `./setup.sh` を流します。Windows と同じく、足りない物だけを入れます。
3. アプリのメニュー（デスクトップにも置きます）の **Sync-Strata** を開きます。アプリは `~/.local/share/SyncStrata`、設定と会話は `~/.config/SyncStrata` に入ります。

細かい選択肢（入れる場所・モデルの置き場・修復）は [docs/INSTALL.ja.md](docs/INSTALL.ja.md) にあります。

## 使い方

- **GUI**: デスクトップのアイコンから。窓を閉じるときに「GUI だけ閉じる／GUI と dsh を閉じる／全部閉じる」を選べます。GUI だけ閉じても、エンジンと dsh は動き続けます。
- **スマホ**: PC の画面の設定で「スマホからの接続」を「同じ Wi-Fi」にし、出てきた QR を同じ Wi-Fi のスマホで読み取ります。外出先からは [Tailscale](https://tailscale.com/) を使います。QR は 3 分・1 回きりの合い言葉で、長く使える鍵は PC の外に出ません。スマホのログインは QR を読んだ日から 30 日で切れ、残りが 7 日以内になるとスマホの画面と PC の「接続中の端末」に警告が出ます。端末は PC の「接続中の端末」から取り消せます。同じ Wi-Fi の中では通信は暗号化されません（[docs/REMOTE.ja.md](docs/REMOTE.ja.md)）。
- **CLI**: 入れた先の `sync`（Linux では `sync.sh`）から。
  ```
  sync up              # エンジンと dsh を起こす（窓は開かない）
  sync up --api-only   # API だけ
  sync status          # 動いているか・モデル・速さ
  sync chat            # 端末で会話する
  sync down            # 全部止める
  ```
- **API**: `http://127.0.0.1:8080/v1`（OpenAI 互換の `/v1/chat/completions`・`/v1/responses`・`/v1/models`、Anthropic 互換の `/v1/messages`）。モデル名とつなぎ方の例は `sync api` で表示されます。ほかの PC からつなぐときは鍵が要ります（[docs/API.ja.md](docs/API.ja.md)）。

## モデルの選び方

| PC に積んでいる RAM | 勧めるモデル |
|---|---|
| 24 GB 以下 | **Sync-XS** |
| 32 GB | **Sync-S** |
| 48 GB 以上 | **Sync-M** |

設定が「自動」（既定）なら、アプリが積んでいる RAM の量を調べて、この表の段のモデルを選びます。そのときの空き RAM が足りなくても、小さいモデルには替えません。代わりに、モデルの一部が SSD に残って遅くなること、閉じると RAM が戻るアプリがあることを注意として出します。モデルの中身と大きさは Hugging Face の各ページにあります: [Sync-XS](https://huggingface.co/hiru2005/Sync-XS)・[Sync-S](https://huggingface.co/hiru2005/Sync-S)・[Sync-M](https://huggingface.co/sync-strata/Sync-M)。

## 設定

どの項目も「自動」が既定です。GUI（PC・スマホ）の「起動の設定」か、`sync settings set <名前> <値|auto>` で変えられます。次の起動から効きます。

| 項目 | 選べる値 | 説明 |
|---|---|---|
| tail skip（`tail_skip`） | 自動・R4・R7・R10 | 1 トークンごとに使う専門家の数を減らして速くします。R4 が最も速く、R10 は省きません（品質は R10 が最も高い）。自動は PC に合わせて R4 か R7 |
| 最大コンテキスト長（`context`） | 自動・32K・64K・128K・256K | 一度に扱える長さ。長いほど VRAM を使います。自動の値は下の表 |
| 量子化（`kv_format`） | 自動・k8v4・k8・k4 | 会話の記憶（K/V）の圧縮。ふだんは k8v4、k4 は VRAM がいちばん少なく済みます |
| RAM の上限（`ram_max_gib`） | 自動・数（GiB） | モデルの写しに使う RAM の上限。ほかのアプリを並べて使うときに下げます |
| VRAM の空け（`vram_reserve_mib`） | 自動・数（MiB） | ほかのアプリのために空けておく VRAM |

自動のときのコンテキストと量子化は、VRAM で次のように決まります。

| VRAM | 最大コンテキスト長 | 量子化 |
|---|---|---|
| 12 GB 以上 | 256K | k8v4 |
| 10〜11 GB | 128K | k8v4 |
| 8〜9 GB | 64K | k4 |
| 6 GB | 〔測定中〕 | 〔測定中〕 |

dsh の会話の要約は、文脈が 262,144 のとき 188,416 トークンから始まります（文脈の 9 割と、「文脈 － 返事の上限 65,536 － 余白 8,192」の小さい方）。この値は設定に合わせて起動のたびに決まり、会話の画面の「要約が始まる長さ」にも同じ値が出ます。

GUI では「起動の設定」→「コンテキスト設定」で選べ、「この設定だと約 N トークンまで」が出ます（`sync ctx` でも見られます）。VRAM に入らない組は選べません。会話がこの長さを超えて VRAM が足りなくなると、遅くなってから止まり、エンジンが起こし直されます。ほかの項目と、速さを出すための OS の設定は [docs/SETTINGS.ja.md](docs/SETTINGS.ja.md) にあります。

## 起動と会話のしくみ

- **メモリの追い出し**: 起動のとき、そしてモデルを切り替えるときに 1 回だけ、ほかのアプリが使っている RAM を追い出して、モデルに回します（既定で入）。アプリは閉じません。追い出した量は起動の理由の欄に出ます。設定 `ram_squeeze` で切れます。
- **会話の控え**: 会話の続きを速く始めるための控え（K/V）は、モデルと同じドライブに置きます。合計の上限は、既定で 20 GiB と、そのドライブの空きの 1 割の小さい方です。超えると古い物から消えます。置き場と上限は設定 `sessions_dir`・`sessions_max_gib` で変えられます。
- **ウェブ検索**: 会話の画面から検索を使えます。検索エンジンの [RustXNG](https://github.com/sahenjp/RustXNG)（AGPL-3.0）は配布物に入れず、初めて検索するときに本家から取得します。dsh への差し込み [dsh-rustxng](https://github.com/kgmkm/dsh-rustxng) は MIT です。

## 更新と削除

- **更新**: Windows はスタートメニューの「Sync-Strata の更新」、Linux はアプリのメニューの「Sync-Strata の更新」（`~/.local/share/SyncStrata/update.sh` でも同じ）。変わった部品だけを入れ替え、前の版を 1 つ残します（「前の版に戻す」で戻せます）。アプリを「全部閉じる」で閉じてから流してください。
- **削除**: Windows はスタートメニューの「Sync-Strata を消す」、Linux はアプリのメニューの「Sync-Strata を消す」（`~/.local/share/SyncStrata/uninstall.sh`）。モデルと設定・会話を消すかは、その場で聞きます（既定は残す）。

モデル・設定・会話は、更新でも削除でも、聞かれない限り消えません。

## 測り

下の表は作者の PC で測った値です。〔最後のエンジンで測り直す。いまの値は 11/15〜16 の rel-1115 の版〕

- PC: Ryzen 7 7800X3D・RAM 32 GB（DDR5）・RTX 3080 12 GB（画面も同じ GPU）・NVMe SSD。OS は Windows 11 と Linux（Ubuntu 24.04）の両方
- エンジン: Sync-Strata 0.1.0（Gyro-S・Gyro-M は本家 Strata 0.2.13.1）
- **jbench**: 本家 Strata の速さの物差し（tok/s）。decode は決まった 10 本の頼み（英語と日本語の文・コード・JSON・写し × 温度 0 と 0.7）の幾何平均、prefill は約 1,000 トークンの頼みを読む速さです。思考は切り、seed を変えた 3 回の中央の値です。
- **dsh の会話**: dsh を通した日本語の会話（思考は low・温度は既定）の平均 tok/s（トークンの合計 ÷ 時間の合計）。雑談 6 会話（1 会話 3〜4 ターン、返事は約 18 本）を seed を変えて 2〜3 回流した値です。dsh の指示文と道具の説明（約 5,600 トークン）が毎回前に付きます。

| OS | モデル | tail skip | jbench decode | jbench prefill | dsh の会話 |
|---|---|---|---:|---:|---:|
| Windows | Sync-XS | R4 | 〔測定中〕 | | |
| Windows | Sync-XS | R7 | 〔測定中〕 | | |
| Windows | Sync-XS | R10 | 〔測定中〕 | | |
| Windows | Sync-S | R4 | 144.0 | 597 | 104.1 |
| Windows | Sync-S | R7 | 127.5 | 648 | 90.7 |
| Windows | Sync-S | R10 | 104.6 | 593 | 80.1 |
| Windows | Sync-M | R4 | 124.6 | 316 | 92.2 |
| Windows | Sync-M | R7 | 93.6 | 322 | 75.7 |
| Windows | Sync-M | R10 | 69.1 | 322 | 59.1 |
| Windows | Gyro-S（本家・既定） | 7 | 72.6 | 241 | 〔測定中〕 |
| Windows | Gyro-S（本家・最速の設定） | | | | |
| Windows | Gyro-M（本家・既定） | 7 | 43.2 | 93 | 〔測定中〕 |
| Windows | Gyro-M（本家・最速の設定） | 4 | 67.8 | 102 | 〔測定中〕 |
| Linux | Sync-S | R4 | 測定予定 | 測定予定 | 測定予定 |
| Linux | Sync-S | R7 | 測定予定 | 測定予定 | 測定予定 |
| Linux | Sync-S | R10 | 測定予定 | 測定予定 | 測定予定 |
| Linux | Sync-M | R4 | 測定予定 | 測定予定 | 測定予定 |
| Linux | Sync-M | R7 | 測定予定 | 測定予定 | 測定予定 |
| Linux | Sync-M | R10 | 測定予定 | 測定予定 | 測定予定 |
| Linux | Gyro-S（本家・既定） | | 測定予定 | 測定予定 | 測定予定 |
| Linux | Gyro-S（本家・最速の設定） | | 測定予定 | 測定予定 | 測定予定 |
| Linux | Gyro-M（本家・既定） | | 測定予定 | 測定予定 | 測定予定 |
| Linux | Gyro-M（本家・最速の設定） | | 測定予定 | 測定予定 | 測定予定 |
| ― | GTX 10 系（CUDA 12 版） | ― | 実機なし。測れていない | | |
| ― | Radeon RX 6000・7000・9000 系（HIP 版） | ― | 実機なし。測れていない | | |

品質（元のモデルとの差）は各モデルのページに載せます。Sync-XS の品質は、Colab の本番 eval_v4 で測りました。元の Sync-XS（表引きの形）と同等で（物差し B で +0.60%、95% の幅は −0.23〜+1.34%）、Gyro-S より 16.1% 良く、Sync-S より 34.8% 悪い値です（物差し B の KL の比。表は [Sync-XS のページ](https://huggingface.co/hiru2005/Sync-XS)）。速さは PC（とくに RAM の量・SSD・裏で動くアプリ）で大きく変わります。

## 制限と既知の問題

- 対応を確かめた GPU は NVIDIA の RTX 30・40 系だけです。RTX 20・GTX 16・RTX 50 系、GTX 10 系、Radeon は実機で確かめていません（上の表）。Mac・Intel の GPU・内蔵 GPU には対応していません（Ryzen AI Max の内蔵 Radeon〔Strix Halo。8060S など〕だけは Windows・Linux とも試験的に対応します）。Windows の内蔵 Radeon は、文章の生成の最初で GPU が止まります。単体の Radeon と内蔵 Radeon の両方がある PC では、単体の Radeon を使います。
- 画像は CPU で読むため、1 枚に十数秒かかります（どの配布物にも画像の読み取りが入っています）。
- ほかのアプリが GPU やメモリ帯域を多く使うと、速さが大きく落ちます（CPU の取り合いには自動で対処します）。`sync doctor` で、いま使っているアプリが分かります。
- 画面を描く GPU と同じ GPU で動かすと、使える VRAM が減ります。
- 量子化の較正に使った文章の一部は、作者自身の会話の記録から作りました（下の「較正について」）。
- 〔要決定: 公開時点で残る問題を足す〕

## 較正について

モデルの量子化の較正には、公開されている文章（コード・文書・百科事典・多言語の文・エージェントの記録）と、作者自身の会話の記録から作った文章の一部を使いました。較正に使った文章は配布しません。

## 謝辞

- [Strata](https://github.com/Niko1221/Strata)（Niko1221 と Strata の貢献者、MIT）: エンジンとアプリはこのフォークです。
- ウェブ検索には [RustXNG](https://github.com/sahenjp/RustXNG)（AGPL-3.0）を使います。本体は配布物に入れず、初めて検索するときに本家の固定の版（v0.27.0）を取得して確かめます。dsh への差し込み [dsh-rustxng](https://github.com/kgmkm/dsh-rustxng) は MIT です。
- [agentionai](https://huggingface.co/agentionai): Gyro の形式とカーネル、Gyro-S の重み（共通の部品はここから切り出しています）。
- [Qwen](https://huggingface.co/Qwen/Qwen3.8-Flash-Next): 元のモデル Qwen3.8-Flash-Next。
- [dsh](https://www.npmjs.com/package/@deepseek-ai/dsh)（DeepSeek、MIT）: 会話の画面。
- [llama.cpp / ggml](https://github.com/ggml-org/llama.cpp)（MIT）、[Project Maya](https://github.com/mw00/project-maya)（MIT）、[Tauri](https://tauri.app/)（MIT／Apache-2.0）、[Zen Kaku Gothic New](https://github.com/googlefonts/zen-kakugothic)（SIL OFL 1.1）。
- 同梱するすべての部品とライセンスは [LICENSES.md](LICENSES.md) にあります。

## ライセンス

- Sync-Strata のコード: [MIT](LICENSE)（本家 Strata と同じ）。
- モデル（Sync-XS・Sync-S・Sync-M と共通の部品）: 元のモデルに合わせて [Qwen Community License 1.0](https://huggingface.co/Qwen/Qwen3.8-Flash-Next)。月間 1 億人か月 2,000 万ドルを超える商用の製品での表示の義務と、Model as a Service や AI のコーディング・事務の助手の事業での商用には Qwen の別の許諾が要る、という条件があります。全文は各モデルのページの `LICENSE` を読んでください。
- 同梱の部品: それぞれのライセンス（[LICENSES.md](LICENSES.md)）。
