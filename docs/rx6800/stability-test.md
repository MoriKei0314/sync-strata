# 最速構成 安定性試験 結果（2026-11-20 夜〜11-21 未明、winmain）

## 結論（先に）
- 試験は **計画の約半分（36サイクル中 20サイクル、Sync 稼働 約1時間32分）で外部要因により中断**した。中断原因は Sync でも GPU でも RAID でもなく、**Windows Update の計画済み再起動が2回連続で発動したこと**（イベント 1074 で確定）。クラッシュ（bugcheck）は発生していない。
- 中断までの全区間で **Sync 起因の異常はゼロ**：生成失敗 0/23、never rang 増加 0、新規ダンプ 0、API 応答 20/20。
- したがって「最速構成を常用してよいか」への答えは **条件付きで可**。否定的な証拠は今回得られなかったが、3時間の soak は未達成であり、ステップ1で判明した AMD-RAID ドライバ（rcbottom.sys 9.3.3-00057）の潜在バグは残っている。再試験や常用開始の前には、Windows Update の再起動予定（pending restart）の有無を確認することを強く推奨する。

## 試験条件
- 構成: `sync up --api-only --vram-reserve-mib 768 --ram-max-gib 20 --env STRATA_PARTIAL_PIN_GIB=14 --preset speed --context 65536`（Start-SyncMode.ps1 の最速構成、テンプレート原形のまま）。
- 起動方式: Start-SyncMode.ps1 で本番停止後、SSH セッション保持型ホルダー（syncstrata-tune-holder.ps1）で `sync up` を実行。※Start-SyncMode.ps1 の SSH セッション終了と同時に Sync が落ちる事象を最初に確認したためホルダー方式に切り替えた（チューニング時と同じ既知の挙動）。
- 監視: 5分ごとに ①/v1/models ②短い生成（max_tokens 2500）③LastBootUpTime ④Minidump 一覧 ⑤strata-auto.log の never rang 累計。30分ごとに 3000 トークン級の長文生成。
- 開始前ベースライン（22:47）: LastBootUpTime = 2026-11-20 20:38:32、ダンプ3件（060426 / 100426 / 112026）、never rang 累計 = 1（チューニング時の初回分）、本番 8081/11434/8788 = 200、watchdog Ready・有効。

## 時系列
| 時刻 | 出来事 |
|---|---|
| 22:47 | ベースライン記録 |
| 22:50 | Start-SyncMode.ps1 で 27B／Ollama 停止、Sync 起動（温め 59.6 tok/s）。ただし SSH セッション終了で Sync が停止したため、ホルダー方式で再起動 |
| 22:57頃 | ホルダー経由で Sync 再起動完了（温め 52.6 tok/s、モデル loaded、n_ctx 65536 を確認） |
| 22:54〜00:09 | 監視サイクル 1〜16、全て正常 |
| 00:10頃 | **助手 VM 側のランタイム再起動**で監視が約1.5分途絶（母艦は無影響）。監視を cycle 17 から再開 |
| 00:11〜00:26 | サイクル 17〜20、全て正常 |
| 00:29:22 | **Windows Update（MoUsoCoreWorker）が計画済み再起動を開始**（Event 1074、理由: Service pack (計画済)、0x80020010）→ 00:30:36 起動 |
| 00:31:14 | **2回目の計画済み再起動**（Event 1074、TrustedInstaller、理由: アップグレード (計画済)、0x80020003）→ 00:31:36 起動（最終 LastBootUpTime） |
| 00:31〜00:36 | 母艦到達不能（再起動中）。監視サイクル 21・22 が接続失敗し、設計どおり監視は「API FAILURE x2」で ABORT（真因は上記再起動） |
| 00:37 | SSH 復旧。状態確認：8081 は自動復帰済み、Docker コンテナ群は起動中 |
| 00:39 | Stop-SyncMode.ps1 で正規復帰、全項目確認完了 |

## 計測結果（サイクル 1〜20、監視ログ stability-monitor.log より）
- 生成リクエスト: 短文 20回 + 長文 3回 = **23回、全て成功（成功率 100%）**。
- /v1/models: 20/20 で HTTP 200。
- 長文生成（各 3000 completion tokens）の実効速度:
  - cycle 6（23:20）: 67.0秒 → **44.8 tok/s**
  - cycle 12（23:50）: 51.6秒 → **58.1 tok/s**
  - cycle 18（00:17）: 54.9秒 → **54.7 tok/s**
  - チューニング時の公称 58.6 tok/s と同水準を維持。劣化傾向なし。
- 短文生成の実効 tok/s は 21〜57 の範囲（推論トークンを含む実効値であり、本文はいずれも正常）。
- `verify: layer N never rang`: **試験中の増加 0**（累計 1 のまま。最終確認でも 1）。
- 再起動: **2回、いずれも Windows Update の計画済み再起動**。11-21 分の Event 41／1001／6008 は **なし**（＝クラッシュではないことの確認済み）。
- 新規 Minidump: **なし**（3件のまま）。

## 復帰確認（00:39:24 時点、全て実測）
- 8081/health: **200**（body `{"status":"ok"}`、llama-server.exe PID 14392 稼働 = 27B 常駐）
- Ollama 11434: **200**
- Gateway 8788: **200**（bantoh-gateway / bantoh-ntfy / bantoh-redis コンテナ Up）
- watchdog（bantoh-llama-watchdog）: **Ready・有効**（Stop-SyncMode が再有効化）
- 8080: DOWN（Sync 停止済み）
- LastBootUpTime: 開始前 2026-11-20 20:38:32 → 終了時 2026-11-21 00:31:36。**変化したが、原因は Windows Update の計画済み再起動2回であり、異常終了ではない**（Event 1074 ×2 で証明、41/1001/6008 なし）。
- Windows Update の PendingReboot: 終了時点で検出なし。

## 判定と残件
- 最速構成の要素（VRAM 予約 768MiB、PIN 14、preset speed、context 64K、RAM 予算 20）の中で、今回の証拠から **緩めるべきものは特定されなかった**。約1.5時間の実負荷でエラーは皆無だった。
- ただし次は「未達」である: ①3時間 soak の残り約1.5時間分 ②チューニング時のような「起動を繰り返し GB 単位の読み直しを連続させる」高 I/O パターンでの長時間観察（rcbottom バグの契機クラス）。
- 次回再試験の前提条件（提案）: 開始前に Windows Update の pending restart が無いことを確認する（今回はこれで潰れた）。可能なら更新の一時停止期間中に実施する。
- 恒常対策の候補（ユーザー判断待ち、未実施）: AMD-RAID ドライバの更新、Sync モデル配置の C:（NVMe 直結）への移行。詳細は bsod-analysis.md の提案節を参照。
