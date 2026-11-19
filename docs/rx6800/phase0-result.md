# Phase 0 実測結果 — 0.1.2 無改造（2026-11-19 夜、winmain）

## 結論
**VMM の壁は突破した。だが生成が新しい壁で全滅した。**
0.1.2 の対策は gfx1030 でも有効で、エンジン起動と API の立ち上がりまで到達した。
しかし実際の生成はすべて、投機検証グラフの完了フラグが立たないエラー
`verify: layer N never rang` で数トークン以内に死んだ。
Phase 1 の標的は VMM ではなく、この verify 経路に移る。

## 更新
- `SyncStrata-0.1.2.zip` (923.9MB) を取得し `app\update.cmd -Source <zip> -SyncHome D:\SyncStrata-trial\home` でアプリのみ更新（29.5秒、rc=0）。モデル・home は無傷、再DLなし。
- pack / launcher / chat: 0.1.1 → 0.1.2。engine-hip-rdna2: 0.2.7-win1118r3 → 0.2.7-win1119r2。state.json の release = 0.1.2。
- 0.1.2 既定を実ファイルで確認: sync_launch.py 476行 `STRATA_HIP_VMM=0`、475行 `AMD_SERIALIZE_KERNEL=0`、468行 `STRATA_HIP_ARENA=coherent`、486行 `STRATA_QL_DMA_GPUFLAG=0`。`--pcie-frac 0.4` が実際に渡った。

## 起動
- strata-auto.log 新規分に `hipMemAddressReserve/Map/SetAccess failed` は **0件**。
- `--kv-grow` は引数に残るが `STRATA_HIP_VMM=0` で弾性 K/V が無効化され（ログ: "the elastic K/V stays off: CUDA virtual memory: NOT available"）、ExpertCache は hipMalloc 経路で確保: `expert cache 4887 slots, 5.22 GiB of VRAM`、`pre-filled 4887 of 4887 slots in 15.7 s; slot 0 verified`、`session is up`。
- ただし起動は一発で通らない。試行1〜3はランチャーが「GPUメモリの空きが調整されませんでした」で失敗扱いになり、自動緩和（VRAM予約 512→1024→1536MiB、予算 16.0→12.75GiB）の4試行目で API ready（約5分の浪費）。`sync status` = http://127.0.0.1:8080、モデル名 `qwen3.8-flash-next-sync-s`。

## 生成（全滅）
サーバはリクエストごとにエンジンを再起動する作りで、生成5回すべて同じ死に方:
- 温め1: 11 tokens → `verify: layer 42 never rang (graph finished)`、exit 1
- 温め2: 9 tokens → `verify: layer 43 never rang`
- 日本語 T1: 6 tokens → `verify: layer 4 never rang`
- マルチターン T3: 30 tokens → `verify: layer 12 never rang (unspecified launch failure)`（瞬間表示 19.2 tok/s）
- tools T4: HTTP 503（エンジン再起動中に到達）

- decode: 持続生成は一度も成立せず。死ぬまでの平均 0.4〜1.7 tok/s（エラー処理込み）。
- prefill: 小プロンプトの読みのみ（69トークン/2秒、102トークン/6〜8秒、オーバーヘッド込み）。本測定不能。
- 日本語・返答破損: **未測定**（完結した返答が1つも返らなかった）。
- ツール呼び出し: 未確認。副次所見: 起動直後の `GET /v1/models` が `{"data": []}`（status 表示と不一致）。

## 本番復帰
- Sync-Strata 完全停止、試走用タスク syncstrata-phase0 は登録解除。
- 復帰確認 20:33:28: 8081/health 200（Qwen3.8-27B-UD-Q3_K_XL 常駐確認）、Ollama 11434 200、Gateway 8788 200、watchdog Ready。
- 本番停止時間: 20:13:03〜20:33:28 の約20分。ドライバ更新・コードパッチ・モデル再DLは一切なし。
- 生ログ: 母艦 `D:\SyncStrata-trial\logs\phase0-update.log`、`phase0-up.log`、`home\run\server.out`、`home\run\strata-auto.log`（旧 0.1.1 ログは `logs\strata-auto-011.log` に退避）。

## Phase 1 の標的
1. **本丸: verify グラフの層完了フラグが gfx1030 で立たない。** 層番号が 4/12/42/43 と毎回ばらつくため特定層のバグではなく競合・順序の問題が濃厚。
   - 候補A: `AMD_SERIALIZE_KERNEL=2` の上書き実験（Linux HIP では 2 が決定性と安定をもたらした設定。Windows 既定 0 との対比が最安の切り分け）
   - 候補B: DMA フラグ経路。上流 Issue #2 の `verify: timed out at layer 1 (#267)` と同系統。verify.cpp の flag raise 周り（3929付近）がコード側の主戦場
   - 候補C: `--spec` / MTP を切った素の decode が通るか（通れば verify 回避で「使える化」を先行できる）
2. 副次: ランチャーの VRAM 空き待ち緩和ラダーの初期値を gfx1030/16GB 向けに見直す。
3. 副次: `/v1/models` が空リストを返すサーバ側バグ。
