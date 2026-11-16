<!-- 案（11/15 係 D）: 係 P の利用者向けの説明（pack/src/README.md）の句読点を「、。」にした写し。元が変わったら作り直す。 -->

# Sync-Strata の入れ方・更新・消し方

この文書の 1〜6 は Windows の手順です。Linux は最後の「Linux」の節を読んでください。

## Windows

Sync-Strata は、自分の PC の GPU で動くローカルの LLM のアプリです。会話の画面（dsh）とエンジンが一緒に入っています。

## 1. 要る物

| 物 | 条件 |
|---|---|
| OS | Windows 10（1803 以降）か Windows 11、64 ビット |
| GPU | NVIDIA の RTX 30 系か 40 系（対応する GPU の全部は [README](../README.ja.md) の表）。ドライバーは R580 以上（CUDA 13.0 が動く版）。GTX 10 系（CUDA 12 版）は 576.57 以上 |
| CPU | AVX2 が要ります |
| RAM | モデルで違います。Sync-XS は 24 GB 以下の PC 向け、Sync-S は 32 GB、Sync-M は 48 GB 以上の PC 向け（アプリが積んでいる RAM の量で選びます） |
| 空き容量 | アプリ 約 2 GB（更新の間は前の版を 1 つ残すので、その分も）＋どのモデルにも要る共通の部品 約 35 GB ＋ モデル（Sync-XS 約 24 GB・Sync-S 約 28 GB・Sync-M 約 35 GB）。モデルは速い SSD（NVMe）に |
| 管理者の権限・PC の Python や Node | 要らない（全部アプリの中に入っています） |
| ネットワーク | 入れるときは要らない（zip の中に全部あります）。モデルを落とすときと更新のときだけ |

## 2. 入れる（初回・修復・別の PC、どれも同じ）

1. 落とした zip を展開する（例: 展開先のフォルダー `SyncStrata-0.1.0-1115`）。フォルダーの名前に日本語が入らない場所を勧めます。
2. 中の `setup.cmd` をダブルクリック。
   - すでに入っている物を調べ、**足りない物・古い物・壊れた物だけ**を入れます。何度流しても同じ結果になります。
   - 最後に、部品ごとに「入れた／直した／飛ばした」を 1 行ずつ出します。
   - アプリは `%LOCALAPPDATA%\Programs\SyncStrata` に入ります。別の場所にするときは、コマンドプロンプトで
     `setup.cmd -AppDir <入れる場所>` のように。
3. デスクトップの **Sync-Strata** をダブルクリック。モデルがまだ無いときは、最初の画面にモデルを入れる案内が出ます。

### モデルがもう手元にあるとき

計測キットなどで落としたモデル（`models\` の中に `sync-s-sb\` などがある並び）があれば、setup が探して見つけ、
**落とし直さずに**その場所を使います（展開した zip の隣、ドライブの直下から 2 段まで、ユーザーのフォルダーの中を探します）。
見つからないときや別の場所を使いたいときは `setup.cmd -ModelsDir <モデルのフォルダー>` のように指してください。

## 3. 更新する

スタートメニューの **Sync-Strata の更新**（入れた先の `update.cmd`）をダブルクリック。

- 新しい版の一覧を見て、**変わった部品だけ**を落として入れ替えます。
- **アプリが動いている間は入れ替えません**。アプリの画面を「全て閉じる」で閉じてから流してください。
- モデルと、設定・会話（`SYNC_HOME`）には触れません。
- 入れ替える前の版を 1 つ残します。新しい版で困ったら、スタートメニューの **Sync-Strata を前の版に戻す**（`rollback.cmd`）。
- 更新の置き場は設定（`settings.json` の `update_feed`）で替えられます。手元のフォルダーや URL を指すときは
  `update.cmd -Source <新しい版の feed のフォルダー>` のように。

## 4. 消す

スタートメニューの **Sync-Strata を消す**（入れた先の `uninstall.cmd`）。

- アプリと、setup が作ったアイコンを消します。
- モデルと、設定・会話（`SYNC_HOME`、既定 `%LOCALAPPDATA%\SyncStrata`）は、消すかどうかを聞きます（既定は残す）。

## 5. 置き場

| 置き場 | 中身 | 更新のとき |
|---|---|---|
| アプリ（`%LOCALAPPDATA%\Programs\SyncStrata`） | アプリの枠・起動の道具・会話の画面・エンジン・Python・Node・dsh | 入れ替える（前の版を 1 つ残す） |
| モデル（`settings.json` の `models_dir`） | モデルのファイル | 触らない |
| 利用者の物（`SYNC_HOME`、既定 `%LOCALAPPDATA%\SyncStrata`） | `settings.json`・dsh の設定と会話（`dsh-home\`） | 触らない |

## 6. 困ったとき

- 「動いているので入れ替えません」: アプリの画面を「全て閉じる」で閉じる。コマンドからなら `sync down --all`。
- 「sha256 が一覧と違う」: 落とした zip が壊れています。落とし直して `setup.cmd` をもう一度。
- 部品が壊れたかもしれないとき: `setup.cmd -Full` で全ファイルを計り直して、壊れた部品だけ入れ直します。

## Linux

1. Linux 用の配布物（`SyncStrata-<版>-linux.zip`）を落として展開し、端末で `./setup.sh` を流します。足りない物だけを入れ、何度流しても同じ結果になります。
2. アプリのメニュー（デスクトップにも置きます）の **Sync-Strata** から開きます。
3. コマンドは `sync.sh`（`./sync.sh up`・`./sync.sh down` など。中身は Windows の `sync` と同じ）。
4. アプリは `~/.local/share/SyncStrata`、設定と会話（`SYNC_HOME`）は `~/.config/SyncStrata` に入ります。モデルの置き場は `settings.json` の `models_dir` です。
5. 更新・削除は、アプリのメニューの「Sync-Strata の更新」「Sync-Strata を消す」（`~/.local/share/SyncStrata/update.sh`・`uninstall.sh`）です。前の版に戻す入口は〔要決定〕。
6. 要る物: 64 ビットの Linux（glibc 2.28 以降。作者の実機は Ubuntu 24.04 で、ほかのディストリビューションは未確認）、NVIDIA のドライバー R580 以上（Linux は 580.95.05 以上。GTX 10 系は 575.57.08 以上）。Radeon は HIP 版で、試験的な機能です（実機では未確認）。
