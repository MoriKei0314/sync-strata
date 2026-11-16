# Sync-Strata（Linux）の入れ方・更新・消し方

Sync-Strata は，自分の PC の GPU で動くローカルの LLM のアプリです．会話の画面（dsh）とエンジンが一緒に入っています．

## 1. 要る物

| 物 | 条件 |
|---|---|
| OS | 64 ビットの Linux（Ubuntu 22.04 以降で確かめる予定） |
| GPU | NVIDIA の RTX 30・40（RTX 20・50 は動く見込み），GTX 10 と Radeon RX 6000〜9000 は試験的．NVIDIA はドライバー 580 以降 |
| RAM | 32 GB を勧める |
| 空き容量 | アプリ約 2 GB（更新の間は前の版を 1 つ残す）＋モデル約 82 GB（Sync-S）．モデルは速い SSD（NVMe）に |
| 管理者の権限（sudo） | 要らない |
| 道具 | unzip か python3 のどちらか．curl か wget は落とすときだけ |
| ネットワーク | 入れるときは要らない（GTX 10・Radeon 用のエンジンだけは，zip の外なので落とす）．モデルを落とすときと更新のときだけ |

## 2. 入れる（初回・修復・別の PC，どれも同じ）

1. 落とした zip を展開する（例: `~/Downloads/SyncStrata-0.1.0-1115-linux/`）．
2. 端末でそのフォルダーに入り `./setup.sh`（実行できないときは `sh setup.sh`）．`./setup.sh --help` で使い方．
   - すでに入っている物を調べ，**足りない物・古い物・壊れた物だけ**を入れます．何度流しても同じ結果になります．
   - アプリは `~/.local/share/SyncStrata` に，設定と会話は `~/.config/SyncStrata` に入ります．別の場所にするときは `./setup.sh --app-dir ~/apps/SyncStrata`．
   - この PC の GPU に合うエンジンを 1 つだけ入れます．GTX 10・Radeon 用のエンジンは，zip の隣に手で置いた物があればそれを，無ければ更新の置き場から落とします．
3. アプリの一覧（またはデスクトップ）の **Sync-Strata** を開く．モデルがまだ無いときは，最初の画面にモデルを入れる案内が出ます．

### モデルがもう手元にあるとき

`models/` の中に `sync-s-sb/` などがある並びがあれば，setup が探して見つけ，**落とし直さずに**使います（zip の隣，`~/.local/share/SyncStrata/models`，ホームの下，`/mnt`・`/media` の下を探します）．
別の場所は `./setup.sh --models-dir /data/models`．

## 3. 更新する・前の版に戻す・消す

- 更新: `~/.local/share/SyncStrata/update.sh`（アプリの一覧の「Sync-Strata の更新」）．**アプリが動いている間は入れ替えません**．
- 前の版に戻す: `rollback.sh`．消す: `uninstall.sh`（モデルと設定・会話は聞いてから．既定は残す）．
- 端末から使う: `~/.local/share/SyncStrata/app/launcher/sync.sh up --gui --open`（起こして画面を開く），`sync.sh down --all`（止める），`sync.sh status`．

## 4. 困ったとき

- 「動いているので入れ替えません」: アプリを「全て閉じる」で閉じるか，`sync.sh down --all`．
- 「sha256 が一覧と違う」: 落とした zip が壊れています．落とし直して `./setup.sh` をもう一度．
- スマホからつながらない: ファイアウォール（ufw など）で中継の番号が LAN から許可されているか．
