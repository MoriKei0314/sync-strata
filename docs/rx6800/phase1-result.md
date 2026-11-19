# Phase 1 切り分け結果 — 通る構成が見つかった（2026-11-19 夜、winmain）

## 結論
**`--pcie-mode kernel` で生成が通った。** DMA 経路（既定）が gfx1030 の verify を殺していた。
Sync-S / RX 6800 / Windows / RAM 32GB で、日本語・マルチターン・ツール呼び出しまで実動作を確認。
decode は実測 22〜25 tok/s 級（バースト 34.7）、prefill は 2,646 トークンで約 91 tok/s。

## 実験結果（実施順）
| 実験 | 差分 | 結果 | 失敗/成功の署名 |
|---|---|---|---|
| A | AMD_SERIALIZE_KERNEL=2 | ✗ 悪化 | 温め（19トークン）が prefill で約80秒ハング → エンジンが 0xC0000374（ヒープ破損）でクラッシュ、2回再現。最終ログ行は verify グラフ capture 直後 |
| A1 | AMD_SERIALIZE_KERNEL=1 | ✗ | 温め22秒で `verify: launch: unspecified launch failure`、exit 1。=0 の never rang とも違う署名 |
| B | --spec/--mtp-max-t/--spec-min-p を除去 | ✗ 実行不能 | エンジンが exit 2 で起動拒否: "native (IQ) pack: it needs --native SHARD1, --spec T (T >= 2) and --prefill CHUNK"。**Sync パックでは投機オフは構造的に不可**（エンジン直接起動でも同じ検証で落ちる） |
| B2 | --spec 2 / --mtp-max-t 2（最小投機） | ✗ | 温め 8 トークン生成後 `verify: layer 22 never rang (graph finished)`。窓の大きさは無関係 |
| C1 | STRATA_QL_DMA_GPUFLAG=1（dma のまま） | ✗ 悪化 | 温めが61秒ハング → `verify: the window's GPU waits were released (#267)`、無進捗ウォッチドッグがエンジン自己終了（上流 Issue #2/#267 と同型） |
| C2 | **--pcie-mode kernel** | **◎ 成功** | 温め2回とも完結（44 tok/5s = 13.5 tok/s、46 tok/3s = 21.5 tok/s）。以降の全リクエスト成功、server.out に never rang 0件・異常終了 0件 |

## C2 構成の内容
- インストール先テンプレート `app\app\launcher\engine-template.json` の `--pcie-mode` を `dma` → `kernel` に変更（それ以外は既定どおり spec 6 / mtp-max-t 4）。
- 起動は `sync up --api-only --vram-reserve-mib 1536 --ram-max-gib 12.75`。この初期値で**ラダーなし一発起動**（23:00:12 engine started、reserve 1536 / budget 12.75 がそのまま採用）。
- env は 0.1.2 既定のまま（STRATA_HIP_VMM=0、AMD_SERIALIZE_KERNEL=0、STRATA_QL_DMA_GPUFLAG=0）。
- テンプレートは現在この動作構成のまま残置。原形バックアップ: 母艦 `D:\SyncStrata-trial\logs\engine-template-phase1-backup.json`。

## 本測定（C2 構成）
- 日本語 T1: 完結。返答「こんにちは。日本語での質問や文章作成、翻訳、要約、学習相談などをお手伝いできます。他のお手伝いも気軽にどうぞ。」破損・崩壊なし（130 tok、7.7秒）
- 長文 T2b（エンジン表示）: answering 安定 22〜23 tok/s、600 tok / 28秒 = 23.3 tok/s。返答（ソナーで海の深さを測る説明）は整った日本語 Markdown で破損なし
- 長文 T2 初回: 600 tok / 31秒 = 24.7 tok/s だが全て推論トークンで本文ゼロ（max_tokens を推論で使い切るモデル特性。エンジンの故障ではない）
- マルチターン T3: 正答「青」（283 tok / 8秒 = 34.7 tok/s、プロンプトキャッシュ 97/102 ヒット）
- Prefill T5: プロンプト 2,646 トークンを約29秒で読了 ≒ 91 tok/s、正答「猫」
- ツール T4: **成功**。finish_reason=tool_calls、get_weather(city=東京) を正しく発行（314 tok のツール付きプロンプト、62 tok / 21秒）
- /v1/models: 正常に `qwen3.8-flash-next-sync-s` を返す（Phase 0 の空リストは再現せず。エンジン未ロード状態での応答だった可能性）

## 本番影響
- 停止 22:33:42 〜 23:06:42（33分）。復帰確認: 8081/health 200 + Qwen3.8-27B-UD-Q3_K_XL 常駐、Ollama 11434 200、Gateway 8788 200、watchdog Ready。試走用タスクは登録解除、strata プロセス 0、8080 解放。
- ドライバ更新・モデル再DL・コードパッチは一切なし。

## 次段（コードパッチ）への絞り込み
1. **本丸は DMA 経路の verify フラグ待ち**：pcie-mode dma では、verify ウィンドウの完了フラグ（A/B/M）が gfx1030 + WDDM で永遠に立たない／待ちが解放される。kernel モードはこの待ちを使わないため通る。恒常対策は「gfx1030（RDNA2）では既定を kernel にする」ランチャー側の小さなパッチが最短で、フォーク側の正式化候補（テンプレート直編集は暫定）。
2. エンジン側を直すなら verify.cpp の DMA flag raise / window wait 周り（STRATA_QL_DMA_GPUFLAG と set_flag カーネル、#267 の waits released 経路）。ただし効果対工数では 1 が圧倒的に有利。
3. serialize は全値（0/1/2）で失敗様相が変わるだけで救済にならないことを確認済み。もう触らない。
4. 速度の伸びしろ: kernel モードは専門家の 17〜28% が PCIe 越し、キャッシュヒット 94〜97%。著者値（RTX 3080、Sync-S chat 104 tok/s）との差は主にこの経路差とみられ、DMA が直れば伸びる余地がある。

## 生ログ（母艦）
`D:\SyncStrata-trial\logs\phase1-{a,a1,b,b2,c1,c2}-up.log`、`C:\Users\kesui\phase1-c2-probe.txt`、`phase1-measure2.txt`、`home\run\server.out`（C2 セッション分）、`home\run\strata-auto.log`
