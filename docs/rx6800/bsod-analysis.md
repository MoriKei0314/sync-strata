# BSOD 原因特定 — 2026-11-20 20:30:54 の bugcheck 0xD1（2026-11-20 夜、winmain）

## 結論
**障害モジュールは AMD の GPU ドライバではなく、AMD-RAID のストレージ系ドライバ `rcbottom.sys`。**
WinDbg の `!analyze -v` が一意に特定した（Failure Bucket: `AV_rcbottom!unknown_function`）。
GPU ドライバ（amdkmdag 等）はスタックに一切現れていない。

## 解析手段
- 母艦へ winget で Microsoft.WinDbg 1.2611.4001.0 を導入し、同梱の cdb.exe (amd64, Debugger 10.0.29680.1004) を使用。
- シンボル: `srv*C:\symbols*https://msdl.microsoft.com/download/symbols`。
- 対象: `C:\WINDOWS\Minidump\112026-9000-01.dmp`（3,259,859 bytes、Mini Kernel Dump）。
- 生ログ: 母艦 `C:\Users\kesui\analyze.log`。

## !analyze -v の要点
- Bugcheck: `DRIVER_IRQL_NOT_LESS_OR_EQUAL (d1)`
  - Arg1: `0000000000000000`（参照先アドレス = NULL）
  - Arg2: `0000000000000002`（IRQL = DISPATCH_LEVEL）
  - Arg3: `0000000000000001`（書き込み）
  - Arg4: `fffff807657974f3`（障害命令アドレス = イベント 1001 の第4パラメータと一致）
- 障害命令: `rcbottom+74f3` — `mov qword ptr [rsi+rdx*8],r8`（NULL ベースのポインタへの書き込み）
- `IMAGE_NAME: rcbottom.sys` / `MODULE_NAME: rcbottom` / `SYMBOL_NAME: rcbottom+74f3`
- スタックは `nt!KeBugCheckEx → nt!KiBugCheckDispatch → nt!KiPageFault → rcbottom+0x74f3` のみ（GPU 系モジュールなし）。
- `PROCESS_NAME: System`、System Uptime は 8日20時間（長期稼働中の初回クラッシュ、CUSTOMER_CRASH_COUNT: 1）。
- Debug session time: 2026-11-20 20:38:08（UTC+9、ダンプ生成時刻）。

## ドライバの素性
- `C:\Windows\System32\drivers\rcbottom.sys`、**バージョン 9.3.3-00057**、提供元 Advanced Micro Devices, Inc.、説明 "AMD-RAID rcbottom"、ファイル日付 2024/08/13。
- 同一スタックの兄弟ドライバも同版: `rcraid.sys`（AMD-RAID StorPort）、`rccfg.sys`（AMD-RAID Configuration driver）、いずれも 9.3.3-00057。
- サービス rcbottom は Running / Boot 開始。PnP 上は "AMD-RAID Bottom Device" / "AMD-RAID Controller [storport]"。
- 参考: GPU は Radeon RX 6800、ドライバ 32.0.21042.62（本件とは無関係と判定）。

## なぜチューニング中に起きたか（状況証拠）
- 母艦の **D: ドライブ（1,862GB）は AMD-RAID Array 1 の上**にある（C: は WD Green SN350 NVMe で別系統）。
- Sync のホーム `D:\SyncStrata-trial` は D: 上にあり、Sync のエキスパート読み込み（チューニング基準構成ではファイル段の SSD 読み 6.2 GiB 級、起動のたびに GB 単位の読み込み）は **全て rcbottom を含む AMD-RAID スタックを経由する**。
- 当日はエンジン再起動の反復（構成 C0〜C9＋最終確認、各回 GB 単位の読み直し）、GPU デバイス再起動、起動失敗構成の試行など、ストレージ I/O が異常に集中した。
- したがって本件は「GPU 計算負荷によるクラッシュ」ではなく、**2024 年版 AMD-RAID ドライバ 9.3.3-00057 の潜在バグ（DISPATCH_LEVEL での NULL ポインタ書き込み）が、チューニングに伴う集中的なディスク I/O を契機に顕在化した**とみるのが最も整合的。
- ただし、Sync の通常利用でも D: からのストリーミング読み込みは発生するため、「Sync を使えば必ず落ちる」ではないものの、再発契機になりうる点は否定できない。

## 提案（未実施。ドライバの再インストール・更新は今回の指示範囲外）
1. AMD-RAID ドライバの更新版の有無を確認し、9.3.3-00057 より新しい版があれば更新を検討する（要ユーザー判断）。
2. Sync のモデル配置先を RAID 配下の D: から、NVMe 直結の C: 側へ移すことも再発回避の選択肢（容量と速度のトレードオフあり）。
3. 当面は最速構成の安定性試験（ステップ2）で再発有無を観察する。
