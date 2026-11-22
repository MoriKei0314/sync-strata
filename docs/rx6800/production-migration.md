# 本番移行結果（2026-11-22、winmain）— 27B → Sync 完全移行＋自動起動

## 結論
- **移行完了**: 本番のローカル生成は Sync（qwen3.8-flash-next-sync-s）が唯一の既定ローカルになった。27B は設定の無効化＋タスク Disabled で停止（削除せず温存し、ロールバック可能）。
- **判定 clef-flash は存続**: 提供元は Ollama（11434）で 27B とは無関係。移行後も実コールが成立し、RuleBasedJudge への後退はなし。
- **自動起動を設定し実証**: タスク `bantoh-sync-autostart`（ログオン45秒後＋10分間隔の冪等キープアライブ）を作成し、手動実行で Sync が実際に立ち上がることを確認した。
- **再起動テストも実証完了**: 02:08 の再起動後、ユーザーのログインを起点に自動起動が働き、Sync が healthy まで到達したことをログで確認した（11:16:23 起動開始 → 11:20:13 SUCCESS）。27B は戻らず、異常イベント・新規ダンプもなし（最終確認の詳細は末尾の再起動テスト節）。

## 前提確認（移行前に特定）
- **clef-flash（判定）の提供元**: Gateway ログ「bantoh judge: systemone (model clef-flash) via http://host.docker.internal:11434」のとおり **Ollama（11434）**。8081 の 27B とは同居していないため、27B を止めても判定は落ちない。したがって Ollama は移行後も止めない。
- **Ollama（11434）の役割**: clef-flash 判定に加え、埋め込みモデル nomic-embed-text を保持（他に qwen2.5-coder:7b、qwen3.5:9b）。判定・埋め込みの提供元として移行後も常駐が必要。要らないものはなし。
- **記憶抽出の経路**: ルーターのローカル経由であることを再確認。配線検証（production-wiring.md）で Sync 経由の提案生成は実証済みで、本移行でも再確認した（下記）。

## 移行内容
- **設定バックアップ**: `C:\Users\kesui\B.A.N.T.O.H\bantoh.config.json.bak-migration-20261122-015225`（変更前）。
- **Gateway 設定**: local（27B @ host.docker.internal:8081）を `enabled: false` に変更（削除ではなく無効化で残置）。sync は enabled: true のまま。Gateway コンテナを再起動して反映し、/health 200 と、/api/models で local 候補が消えることを確認した。コンテナ再起動時のログでも「judge: warmup ok (model loaded)」を確認（clef は Ollama 経由で生存）。
- **27B の停止**: タスク `bantoh-llama` と `bantoh-llama-watchdog` を Disabled 化（削除しない）。8081 の llama-server を停止し、ポートが閉じたことを確認した。残存した llama-server.exe は Ollama 配下の clef 用ランナーであり 27B 本体ではない（実行パスで切り分け）。

## 自動起動（Windows 再起動時）
- **スタータ**: `C:\Users\kesui\bantoh-sync-start.ps1`（冪等）。
  - 8080 が healthy なら即終了する。ロックファイル（12分）で多重起動を防ぐ。
  - SYNC_HOME=`D:\SyncStrata-trial\home`、STRATA_ALLOWED_HOSTS=`host.docker.internal` を設定し、最速構成（`sync up --api-only --vram-reserve-mib 768 --ram-max-gib 20 --env STRATA_PARTIAL_PIN_GIB=14 --preset speed --context 65536 --json`）を Start-Process で切り離して起動し、最大720秒ヘルスを監視する。結果は `C:\Users\kesui\bantoh-sync-start.log` に記録。
  - 防御処理: 退役した 27B（C:\llama.cpp\llama-server.exe）が 8081 を掴んでいたら停止する。
- **タスク**: `bantoh-sync-autostart`。トリガーはログオン（45秒遅延）＋10分間隔の繰り返し（旧 27B watchdog と同じキープアライブ方式で、クラッシュ時も次回間隔で復帰する）。MultipleInstances=IgnoreNew、実行時間上限1時間、RunLevel=Limited、対象ユーザー kesui の対話セッションで実行。
- **手動実行での実証**: 2026-11-22 01:56:43 にタスクを開始 → 01:59:05 にスタータが「SUCCESS: Sync API healthy. models: qwen3.8-flash-next-sync-s」を記録し、タスクは Ready に復帰した。過去にタスクスケジューラ経由で sync up が固まった事象は、ランチャーを Start-Process で切り離しヘルスをポーリングする方式では再現しなかった。エンジンは SSH セッションの開閉後も生存を継続し、セッション非依存を確認した。
- **Docker／Gateway の自動復帰**: Docker Desktop は AutoStart=true（HKCU Run 登録あり）、コンテナ3件（gateway／ntfy／redis）とも restart=unless-stopped を確認済み。不足なし。
- **Ollama の自動起動**: トレイはスタートアップ登録（Ollama.lnk）＋タスク `ollama-app-start` で従来どおり。判定・埋め込みに必要なため自動復活は維持し、止める対策は取らなかった。共存の実測: Sync 稼働＋clef ロード済みの状態で空き RAM は約4.9GB とタイトだが、下記の実ターンで clef コールと Sync 応答の両立を確認した。

## 移行後の動作確認（本番 Gateway 経由、テストセッション 3fd738f3-b63b-4bee-bd9d-c74a3b0e3db8）
- /api/models: 全130候補中、ローカル候補は `sync/qwen3.8-flash-next-sync-s@local` のみ。
- 通常ターン（ピン留め）: Sync が応答（47.5s）。turn.done の attempts は sync のみ。
- 事実提示ターン（ピン留め、ダミー事実）: Sync が応答（96.3s）。
- 機密モックターン（privacy、ピンなし）: Sync に振られ正常応答（84.9s）。端末外へ出ていない。
- 通常ターン（ピンなし）: judge.done が localJudge の短絡なしで ms=30003、つまり **clef-flash の実コールが移行後も成立**。そのうえでルーターは Sync を選択し応答した（73.1s）。
- **記憶抽出**: ターン後の自動抽出が実経路で走り、提案6件が生成された（ダミー事実: 氏名「テスト花子」、趣味「陶芸」、予定「来週の月曜日に図書館へ本を返す」×各2形式）。いずれも pending のままで、承認・却下は一切していない。提案総数 31→37（pending 16→22）。
- 判定の状態: 後退なし（clef 稼働継続）。

## 再起動テスト（実証完了・2026-11-22 ログイン後に最終確認）
- 再起動前スナップショット（2026-11-22 02:07）: LastBootUpTime は 2026-11-21 16:56:24。タスクは bantoh-llama／watchdog が Disabled、bantoh-sync-autostart が Ready・有効、ollama-app-start が Running。ポートは 8080／8788／11434 が Listen、8081 は閉。Minidump は4件。Docker は3コンテナ Up。設定は local=false・sync=true。
- 02:08 に `shutdown /r /t 15` を1回だけ発行した（追加の再起動はしていない）。OS 起動は 02:08:45。
- 02:10〜02:23 の SSH 試行は Tailscale 段階で全て接続不可（母艦の Tailscale はユーザーの現地ログインまで戻らない既知の構成）。ユーザーがログインした後に最終確認を再開し、以下をすべて実測で確認した。
- **自動起動の最終実証**: `bantoh-sync-start.log` に `[2026-11-22 11:16:23] === Sync start requested ===` → `[11:20:13] SUCCESS: Sync API healthy. models: qwen3.8-flash-next-sync-s` の記録あり。ログオントリガーでスタータが起動し、Sync が healthy まで到達した。タスク bantoh-sync-autostart は Ready・有効、LastTaskResult=0、11:28 のキープアライブ実行でも「already healthy; nothing to do」を確認。bantoh-llama／bantoh-llama-watchdog は Disabled のまま。
- **ポート／サービス**: 8080/v1/models = 200（qwen3.8-flash-next-sync-s、status=loaded、n_ctx=65536）。8788/health = 200。11434 = 200（Ollama 稼働、Gateway ログでも 02:19:40 UTC に「judge: warmup ok」を確認）。**8081 は接続不可・Listen なし**で、C:\llama.cpp の llama-server プロセスも存在しない（残る llama-server.exe は Ollama 配下の clef 用ランナーのみ）。27B は自動で戻っていない。
- **本番経由のテストターン**: 新規テストセッション f6a72c00-60bd-4fcc-9f2a-3b98dd1677fe で通常ターン1回を実施し、59.7秒で Sync が応答（「東京」）。レスポンスの candidateId は `sync/qwen3.8-flash-next-sync-s@local`、attempts は sync のみ。なお実施直前まで Gateway が vault 再検証（BULK 60,899件、02:37:23 UTC に完了）で高負荷だったため、セッション作成が一時的にタイムアウトしたが、再検証の完了後に正常実施できた。
- **異常の有無**: 2026-11-22 02:08 以降の Event 41／1001／6008 は **0件**。Minidump は4件のまま（最新は 2026-11-21 11:17:26 の 0x139 分）。LastBootUpTime = 2026-11-22 02:08:45 で一致。
- **空き RAM**: Sync 稼働中（clef ロード済み）の実測で空き 3.91GB / 全体 31.21GB。再起動前（約4.9GB）よりややタイトだが、実ターンと判定は両立している。
- 以上で再起動テストは **実証完了** とする。移行＋自動起動の一連の作業はすべて完了した。

## ロールバック手順（27B へ戻す場合）
1. 設定を戻す: `bantoh.config.json` をバックアップ `bantoh.config.json.bak-migration-20261122-015225` で上書きする（または local の enabled を true に戻す）。
2. `docker restart bantoh-gateway` で反映する。
3. Sync を止める: タスク `bantoh-sync-autostart` を Disabled にし（キープアライブで Sync が戻らないようにする）、SYNC_HOME を設定したうえで `sync.cmd down --all` を実行する。
4. 27B を戻す: `bantoh-llama` と `bantoh-llama-watchdog` を Enable-ScheduledTask し、`bantoh-llama` を Start-ScheduledTask する。8081/health が 200 になることを確認する。従来の切替手順（Stop-SyncMode.ps1）でも同じ状態に戻せる。

## 残る制約・申し送り
- 自動起動はログオントリガー方式のため、再起動後はユーザーのログオンが起点になる。Docker Desktop／Tailscale／Ollama トレイも同じ前提で、ログオン前は Gateway 自体が起動しないため、実用上の不整合はない。
- テストセッション 3fd738f3-… とダミー事実の提案6件が本番側に残っている。提案はユーザーの判断待ち（却下想定）。
- max_tokens 下限は従来どおりコード変更が必要な未対応事項（production-wiring.md 参照）。現行運用では実害なしと切り分け済み。
- RAM は Sync（上限20GiB）＋clef（約9GB）でタイト。空き約4.9GB で実動作は確認済みだが、大規模な並行作業時は注意。
