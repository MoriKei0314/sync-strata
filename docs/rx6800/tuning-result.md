# Sync-Strata (Sync-S) 速度チューニング結果（2026-11-20 夜、winmain / RX 6800）

## 結論
**decode 23.5 → 58.6 tok/s（約2.5倍、+149%）、prefill 132 → 242〜298 tok/s（約1.8〜2.3倍）。**
最速構成は CLI 引数と環境変数だけで到達でき、**テンプレート（engine-template.json）は原形のまま**（恒常構成の原則を維持）。
`D:\SyncStrata-trial\switch\Start-SyncMode.ps1` の起動行を最速構成に更新済み（バックアップ: 同フォルダ `Start-SyncMode.ps1.bak-tuning-20261120` と `D:\SyncStrata-trial\logs\tuning-backup-20261120\` 一式）。

### 最速構成（Start-SyncMode.ps1 反映済み）
```
sync up --api-only --vram-reserve-mib 768 --ram-max-gib 20 --env STRATA_PARTIAL_PIN_GIB=14 --preset speed --context 65536
```
エンジン実引数（自動決定の結果）: `--resident-budget-gib 16.25 --vram-reserve-mib 768 --max-context 65536 --kv k8v4 --spec 6 --mtp-max-t 4 --pcie-frac 0.4 --lookup-max-t 12 --pcie-mode kernel --adapt-async 1`、env `STRATA_ROUTE_TAIL_SKIP=4`、`STRATA_PARTIAL_PIN_GIB=14`。

### 何が効いたか（因果）
1. **RAM 常駐予算の拡大**（12.75 → 実効 16.25〜17.0 GiB）: 専門家のファイル段（SSD読み）が 6.2 GiB → 0.7〜1.9 GiB に縮小。ドライブ 1.5 GB/s の読みが律速だった。
2. **ピンの分離**（`STRATA_PARTIAL_PIN_GIB=14`）: 予算 17 では既定のピン（予算+1=18 GiB）が Windows のページロック上限を超え `verify: mapped staging allocation failed [pinned-memory-exhausted]` で起動失敗する。ピンを 14 に抑えると予算 17 でも一発起動する。ピン 16 でも枯渇した（上限は 14〜16 の間）。
3. **VRAM 予約 1536 → 768 MiB**: GPU 側の席（キャッシュ）が増え、予算の実効も 16.25 に。ただしエンジンが「WDDM の verify バッファ余地が小さい」と警告する水準。これ以上の削減は未検証。
4. **tail skip 4（--preset speed）**: decode が安定化（52.2/52.3 とばらつき減）。
5. **context 262144 → 65536**: decode 52.3 → 58.6。KV が小さくなりキャッシュに余地が出た分とみられる。実用上 64K で足りる用途向け（長い文脈が要る場合は戻す）。

## 計測方法
- 固定プロンプト。decode: 四季の説明を 1000 トークン生成（ストリーミングの到着間隔から算出、エンジンの serve 行と一致を確認）。prefill: 約3,420 トークンの固定長文＋短い質問、TTFT と serve 行の tok/s。
- 各構成: 温め1回 → decode 2回・prefill 2回、中央値で比較。生データ: `tuning-bench.jsonl`（同フォルダ）。

## 構成ごとの結果
| 構成 | 変更点（前段比） | decode tok/s (2回) | prefill | 起動 (up) | 成否 |
|---|---|---|---|---|---|
| C0 基準 | ram 12.75 / reserve 1536 / tail 7 / ctx 262K | 27.5 / 19.6（中央 23.5） | TTFT 26.0s（serve 131〜133） | 139.7s | ◎ |
| C1 | ram-max 20（実効はラダーで 13.5 / reserve 2048） | 29.4 / 41.2（35.3） | TTFT 24.2s（141〜142） | 400s（失敗3回） | △ 予算17はピン枯渇で起動不可 |
| C2 | C1 + PIN=14（予算 17.0 / reserve 1536） | 47.4 / 51.0（49.2） | TTFT 15.1s（serve 228 相当） | 160.8s（一発） | ◎ |
| C3 | PIN=16 | （落着した 13.5/2048 で 29.9 / 38.2） | TTFT 32.5s | 378.5s（失敗3回） | ✕ ピン16も枯渇 |
| C4 | reserve 768（予算 16.25） | 45.7 / 57.0（51.4） | TTFT 14.9s | 163.7s | ◎ |
| C5 | C4 + preset speed (tail 4) | 52.2 / 52.3（52.3） | TTFT 14.8s | 140.2s | ◎ |
| C6 | C5 + context 65536 | 59.0 / 58.3（58.6） | （C6b 再測 TTFT 14.1s、約242） | 134.9s | ◎ **最速** |
| C7 | C6 + テンプレート spec 8 / mtp-max-t 6 | 55.4 / 55.1（55.2） | TTFT 13.0s（約263） | 136.3s | △ decode 微減で不採用 |
| C8 | C6 + テンプレート pcie-frac 1.0 | 計測不可 | 計測不可 | 433.6s（ラダー落着 13/1792） | ✕ 初回起動が繰り返し失敗、落着構成でも chat が 503 |
| C9 | C6 + kv k4（実引数 q4_0） | 計測不可 | 計測不可 | エンジン再起動を繰り返し死亡 | ✕ `native embedding: cannot pin 497 MiB: unspecified launch failure` |
| FINAL2 | C6 と同一（新規エンジンで再測） | 58.2 / 56.6 | serve 296.7 / 298.3 | ― | ◎ 再現確認 |

## 最速構成での安定性確認（FINAL2 のエンジンで実施）
- 日本語会話: ◎ 2.6秒で完結（「質問への回答や解説／文章の要約・翻訳・校正／アイデア出し…」）。
- マルチターン: ◎ 「青空や猫のまなざし秋の風」（色=青・動物=猫の文脈を保持）。※ max_tokens 800 では推論が上限を食い本文ゼロになった（既知のモデル特性。上限は 2500 級が必要）。
- 長文生成: ◎ 2600 トークンを 46.7 秒（55.7 tok/s）で生成、本文は四季の説明として完結した文章。
- ツール呼び出し: ◎ get_weather(city=東京) を正しく発行（3.7秒）。
- `verify: layer N never rang`: **1件**。検証の最初のリクエスト（エンジン起動直後）が HTTP 400 で失敗した際に発生したとみられる。以後の全リクエスト（検証4種＋ベンチ5本＋追加2本）は成功し、再発なし。Phase 1 以来の kernel 構成では初回に1件出たのは今回が初めて。要観察。

## 洗い出したノブ（実在確認済み）
- `sync up` CLI: `--ram-max-gib`、`--vram-reserve-mib`、`--context`、`--kv`（k8v4/k8/k4→q4_0）、`--preset speed|quality`、`--tail-skip`、`--env K=V`（テンプレート/AUTO env を上書き可）、`--ram-squeeze`、`--model`、`--port/--host`。
- テンプレート args（ランチャーが一部を上書き）: `--expert-cache auto`、`--prefill auto`、`--spec`、`--mtp-max-t`、`--spec-min-p`、`--lookup-max-t`、`--pcie-frac`（0.7 のときだけ 0.4 に書換え）、`--adapt-async`、`--conversation-cache-min-free-mib`、`--kv-grow`、`--prompt-cache-spread`。
- テンプレート env の主なもの: `STRATA_PARTIAL_PIN_GIB`（ランチャーが予算+1 で上書き、--env で再上書き可）、`STRATA_RESIDENT_HEADROOM_GIB=2`、`STRATA_QL_REFILL_PAR=8`、`STRATA_DMA_BATCH=2`、`STRATA_QL_PCIE_GROUP_ROWS=16`、`STRATA_QL_PCIE_AUTO=1`（AUTO_ENV、pcie-frac を 0.199〜1.0 で自動調整）、`STRATA_QL_RAM_ROTATE=1`、`STRATA_HIP_ARENA=coherent`、`STRATA_HIP_VMM=0`、`AMD_SERIALIZE_KERNEL=0`、`STRATA_QL_DMA_GPUFLAG=0`。
- 未検証のまま残したノブ: `STRATA_QL_REFILL_PAR` 増、`STRATA_DMA_BATCH` 増、PIN=15、`--tail-skip` の他値、reserve 512。いずれも追加の実験枠があれば候補。

## 運用メモ・事故と対処（正直な記録）
- `sync up` は **タスクスケジューラ経由だと sync.py 内で固まる**事象を2回確認（18:27 と 20:15 の試行）。SSH セッション内で保持する方式（ドライバ/ホルダー）では10回以上正常。Start-SyncMode.ps1 の実行は従来どおり対話セッション/ドライバ方式が安全。原因の特定までは至っていない。
- 復帰時、llama.cpp (Vulkan) が `ggml_vulkan: device lost / ErrorDeviceLost` で起動失敗。**RX 6800 のデバイス再起動（pnputil /restart-device）で回復**し、その後は 8081 が即時復帰した。エンジンの強制終了を繰り返した後は GPU の状態が残ることがある、という知見。
- SSH（Tailscale プロキシ 3130）が 20:40 頃から一時的に不通になり、最終復帰確認の一部が遅れた。

## 本番影響
- 停止窓1: 18:23〜20:26（約2時間3分。計測反復と GPU device lost の復旧を含む）。Gateway 8788 は全期間稼働、止めたのは 8081 (27B) と Ollama のみ。
- 窓1の復帰確認（20:26 時点で全項目実測）: 8081/health 200 + Qwen3.8-27B-UD-Q3_K_XL 常駐、Ollama 11434 200、Gateway 8788 200、watchdog Ready（再有効化済み）。
- 停止窓2（最終検証）: 20:26〜。20:38 に Sync 停止（8080 DOWN）と bantoh-llama タスクの起動トリガまで確認済み。**その直後から Tailscale トンネル（egress proxy 3130）が不通になり、窓2の最終復帰確認（8081/health、watchdog 再有効化、私設タスク syncstrata-tune* の登録解除）が未確認のまま残った**。窓1で同じ手順（GPU リセット後の bantoh-llama 起動）が即時成功しているため復帰している可能性は高いが、実測はできていない。SSH 回復後に要確認: ①8081/health 200 とモデル常駐 ②watchdog が Ready（Disabled のままなら Enable-ScheduledTask） ③タスク syncstrata-tune / syncstrata-tune-restore / syncstrata-tune-start の登録解除。

## GitHub への記録
- 本ファイルと `tuning-bench.jsonl` をフォーク（MoriKei0314/sync-strata, rx6800-gfx1030）の `docs/rx6800/tuning-result.md` へ push する件は**承認待ち**（本報告時点では未実施）。
