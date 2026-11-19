# タスク1: フォーク版パッチの最終確認（2026-11-20 朝、winmain）

## 結論
**パッチ単体で再現できた。** テンプレートを原形 (dma) に戻し手編集を一切しない状態で、
パッチ版ランチャーだけで起動→生成まで通った。
母艦の恒常構成は「テンプレート＝原形のまま、ランチャー＝パッチ版」になった。

## 手順と確認
- テンプレート: `engine-template-phase1-backup.json` から復元し `--pcie-mode dma` に戻ったことを確認。
- ランチャー: 0.1.2 純正2ファイルを `D:\SyncStrata-trial\logs\launcher-012-original\` へ退避してからパッチ版を配置。
  - sync_launch.py SHA256 `4CA62A07…E343D`（フォーク正本と一致）
  - sync_env.py SHA256 `503810F7…20734`（同）
  - 同梱 Python で py_compile rc=0。パッチ本体 (sync_launch.py の `setarg("--pcie-mode", "kernel")`、sync_env.py の `hip_picked_device`) の存在を確認。
- 起動: `sync up --api-only --vram-reserve-mib 1536 --ram-max-gib 12.75`（テンプレート無編集）→ ラダーなし一発起動、ExpertCache 4877 slots / 5.21 GiB。
- エンジン起動引数に `--pcie-mode kernel` が自動で入った（strata-auto.log の engine started 行で確認）。テンプレートは dma のままなので、これはパッチの自動適用の証拠。
- `verify: layer N never rang` は 0 件。

## 生成
- 日本語 T1: 完結・破損なし（163トークン）。
- マルチターン: 正答「青」、プロンプトキャッシュ 97/102 ヒット、`done: 359 tokens in 10 s (35.5 tok/s)`、`sync status` 表示 23.6 tok/s（Phase 1 実測と整合）。
- /v1/models は `qwen3.8-flash-next-sync-s` (loaded) を正常返却。

## 本番影響
- 停止 07:39:34〜07:46:05 の約6.5分（Phase 0 の20分／Phase 1 の33分から大幅短縮）。
- 復帰確認: 8081/health 200 + Qwen3.8-27B-UD-Q3_K_XL 常駐、Ollama 11434 200、Gateway 8788 200、watchdog Ready。
- 生ログ: 母艦 `D:\SyncStrata-trial\logs\phase-task1-up.log`、`phase-task1-restore.log`、`home\run\strata-auto.log`。

## 残件
- 上流 (hiruhiru2005/sync-strata) への PR は、ユーザーの指示により行わない。
