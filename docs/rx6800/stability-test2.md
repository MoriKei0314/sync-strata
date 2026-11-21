# 最速構成 安定性試験（続き・3時間 soak）— 事前確認で停止（2026-11-21 00:48、winmain）

## 結論（先に）
- **試験は開始しなかった。** 手順0の事前確認で PendingReboot の指標の1つである **PendingFileRenameOperations が検出された（20件）** ため、定められた停止条件に従い開始を見送った。本番には一切手を入れていない（wuauserv の停止も未実施、Sync も未起動）。
- ただし実質的な内訳は次のとおりで、**Windows Update 起因の再起動が差し迫っている兆候はない**：
  - CBS `RebootPending` キー：**なし**
  - WU `Auto Update\RebootRequired` キー：**なし**
  - WU のインストール待ち更新：**0件**（Microsoft.Update.Session で実測）
  - PFRO の20件は**全てプリンタドライバのファイル差し替え予約**（`C:\Windows\System32\spool\drivers\...` の MXDWDRV.DLL / PJLMON.DLL / PS5UI.DLL / PSCRIPT5.DLL / UNIDRV.DLL / UNIDRVUI.DLL / UNIRES.DLL / PrintConfig.dll）。今夜の Windows Update でステージされたもので、次回起動時に処理されるだけで、**それ自体が再起動を引き起こすものではない**。
  - UpdateOrchestrator の次回スキャンは 2026-11-21 06:07（スキャンであり再起動ではない）。
- 停止は「PFRO が存在すれば保留中とみなす」という事前に定められた判定基準の文字どおりの適用による。実質リスクは低いとみられるため、続行可否は親側の判断に委ねる。続行する場合は、次回起動で PFRO が消化された後（＝一度再起動した後）に開始するのが最もクリーン。

## 事前確認の実測値（2026-11-21 00:48）
- LastBootUpTime: **2026-11-21 00:31:36**（前回報告どおり、Windows Update の計画済み再起動2回のうち2回目の起動時刻）
- 直近 Event 1074: 2026-11-21 00:29:22（MoUsoCoreWorker、計画済）と 00:31:14（TrustedInstaller、計画済）の2件のみ。それ以降なし。
- Event 41 / 1001 / 6008（2026-11-21 00:31 以降）: **なし**（クラッシュなし）
- 本番: 8081/health **200**（llama-server.exe PID 14392 = 27B 常駐）、11434 **200**、8788 **200**
- watchdog（bantoh-llama-watchdog）: **Ready・有効**
- Minidump: 3件のまま（060426 / 100426 / 112026、新規なし）
- never rang 累計: **1**（変化なし）
- 8080: DOWN（Sync 未起動、期待どおり）
- wuauserv: Running / Manual（開始前状態として記録。今回は停止操作を行っていない）
- UsoSvc: Running / Automatic

## 未実施事項
- 試験本体（3時間 soak）、wuauserv の一時停止、Sync 起動、本番停止・復帰のいずれも行っていない。本番は確認開始時点の正常状態のまま。
- 前回（約1.5時間・23リクエスト成功率100%）の結果については stability-test.md を参照。3時間 soak は依然として未達。
