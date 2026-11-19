# RX 6800 (gfx1030) 対応作業 — docs/rx6800

Sync-Strata を **RX 6800 (gfx1030) / Windows / RAM 32GB** 環境（winmain）で動かすための
作業リポジトリ。パッチ・ビルド／試走スクリプト・実測記録をここで管理する。

- 上流: https://github.com/hiruhiru2005/sync-strata （フォーク: MoriKei0314/sync-strata、作業ブランチ `rx6800-gfx1030`）
- 対象モデル: Sync-S（RAM 32GB 段）
- 母艦: Windows、Radeon RX 6800 16GB (gfx1030)、RAM 32GB、ドライバ 32.0.21042.62

## 故障の確定診断（2026-11-19、0.1.1 実機ログ D:\SyncStrata-trial\home\run\strata-auto.log）

起動引数に `--kv-grow` が入り、以下の順で落ちていた:

1. `hipMemMap failed: unspecified launch failure` / `hipMemSetAccess failed`
2. 以後 `hipMemAddressReserve failed: unspecified launch failure` が全リトライで再現
3. ExpertCache はこれを「VRAM 不足 (out of memory)」と誤認し、キャッシュを縮小しながら
   8.88 GiB → 0.89 GiB まで全滅。エンジン起動不可。

つまり VRAM 不足ではない。**gfx1030 + 現行 Windows ドライバで HIP VMM
(hipMemAddressReserve / hipMemMap / hipMemSetAccess) が実動作しない**のに、
デバイス属性 `VirtualMemoryManagementSupported` は「対応」と返すため、
エンジンが VMM 経路（弾性 K/V 用の ExpertCache マッピング）を選んでしまうのが根因。

副次症状: `prefill gemm: cublasGemmEx: cuBLAS status 6`（VMM 失敗で HIP コンテキストが
汚染された後の症状とみられ、単独では追わない）。

## 上流 0.1.2 の状況（2026-11-19 18:37 JST、51cde36）

0.1.1 試走の同日夜に 0.1.2 が出ており、Issue #2（RX 9070 XT / RX 9060 XT）の切り分けで
まさにこの VMM 故障への対策が入った（作者は Radeon Windows 実機なし・未検証）:

- Windows + Radeon 既定: `STRATA_HIP_VMM=0`（専門家の置き場は hipMalloc、K/V は固定割り当て）
- `AMD_SERIALIZE_KERNEL=0`、`STRATA_QL_DMA_GPUFLAG=0`、`--pcie-frac` 開始値 0.7→0.4
- `STRATA_HIP_ARENA=coherent` 既定

ただし対象は RDNA4/RDNA3 世代で、**gfx1030 (RDNA2) での実証はない**。ここが本プロジェクトの仕事。

## 作業計画

### Phase 0: 0.1.2 無改造での再試走（winmain、メンテ枠）
- D:\SyncStrata-trial のモデル（約62.5GB）は再利用可否を確認し、エンジン／ランチャーだけ 0.1.2 に更新
- 本番ローカルLLM (8081/Ollama) を止めるのは実測中のみ。終わったら復帰確認まで
- 測るもの: エンジン起動可否、decode / prefill、日本語、ツール呼び出し、返答破損の有無

### Phase 1: それでも VMM 経路が残る／別箇所で落ちる場合のパッチ（フォーク側）
上流の環境変数頼みにせず、コード側で自己防御させる:
1. `engine/src/core/vmm.cpp` — `api()` の初期化で **実プローブ** を追加:
   予約→生成→マップ→アクセス設定→解除を 1 チャンクで実際に行い、失敗したら
   「VMM 利用不可」として確定させる（属性の自己申告を信用しない）
2. `engine/src/core/expert_cache.cpp` — `ExpertCache::open()` の VMM 経路が失敗したら
   OOM と誤認して縮小リトライせず、**hipMalloc 経路へフォールバック** して起動を継続する
3. どちらも「VMM が正常な環境では挙動不変」をテストで担保する

### Phase 2: ビルドと配布
- winmain 上で HIP (RDNA2) エンジンをビルドし、0.1.2 のキットと差し替えて試走
- ビルド手順は `docs/build-winmain.md` に再現可能な形で残す（要: HIP SDK / VS / CMake の実測確認）

## 記録
- `docs/investigation-2026-11-19.md` — 診断の詳細と一次情報
- 試走のたびにログ要約と数値をこのリポジトリへコミットする
