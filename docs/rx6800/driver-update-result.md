# ドライバ対策 最終結果（winmain）— 2026-11-21

対象: ①AMD チップセット＋RAID ドライバ更新（BSOD 0xD1 / rcbottom.sys 対策）②USB 省電力の無効化（BSOD 0x139 / USBXHCI.SYS 対策）
環境: ASUSTeK PRIME B650-PLUS（B650 / AM5、BIOS 2613）、Ryzen 7 7700、Windows 11 Pro build 26300

## 導入パッケージ（すべて AMD 公式、署名 Valid・AMD 名義を確認）
- AMD Chipset Drivers 8.09.28.1124（2026-10-21、B650 最新）
- AMD RAID Software 8.03.24.733（2026-04-16）— 内包 RAID ドライバ 9.3.3.00291

## ドライバ版：更新前 → 更新後（実効版を実測確認済み）
| ドライバ | 更新前 | 更新後（実効） | 確認方法 |
|---|---|---|---|
| rcbottom.sys（AMD-RAID Bottom） | 9.3.3-00057（2024-08-13） | **9.3.3-00291** | System32\drivers ファイル版＋デバイスバインド 9.3.3.291 |
| rcraid.sys（AMD-RAID Controller） | 9.3.3-00057 | **9.3.3-00291** | 同上 |
| rccfg.sys（AMD-RAID Config） | 9.3.3-00057 | **9.3.3-00291** | 同上 |
| AMD GPIO Controller | 2.2.0.121 | **2.2.0.137** | デバイスバインド。サービスは DriverStore の新パッケージ（amdgpio2.inf_amd64_487ee5525dcee517）を直接ロード |
| AMD I2C Controller | 1.2.0.99 | **1.2.0.133** | デバイスバインド。サービスは DriverStore の新パッケージ（amdi2c.inf_amd64_87478ae9faa4e3e9）を直接ロード |
| AMD PSP 11.0 Device | （旧） | **5.46.0.0** | System32\drivers\amdpsp.sys ファイル版＋バインド |
| AMD SMBus | （旧） | **2.0.0.29** | デバイスバインド |
| AMD Provisioning Packages | （旧） | **8.0.0.65** | デバイスバインド |

- 注: System32\drivers\amdgpio2.sys／amdi2c.sys のファイル版は旧版のまま残っているが、両サービスの ImagePath は DriverStore の新パッケージを指しており、実効ロードは新版。未使用の旧コピーである。
- 全対象デバイスの ConfigManagerErrorCode = 0（problem code なし）。Non-OK デバイスなし。
- 意図的に除外したもの: USBFILTER、USB4CM、APPCOMPATDB、CACHEOPT（3D V-Cache 用、7700 は非 X3D）、PPkgOEM、PMF の他シリーズ用変種。

## USB 省電力の変更一覧
- 電源プラン（バランス、381b4222-f694-41f0-9685-ff5bb260df2e）の USB セレクティブサスペンド: AC 1（有効）→ **0（無効）**、DC 1 → **0**。2026-11-21 17:31 にレジストリ実測でも ACSettingIndex=0／DCSettingIndex=0 を再確認。
- 「電力の節約のためにコンピューターでこのデバイスの電源をオフにできるようにする」（MSPower_DeviceEnable）True → False:
  - AMD USB 3.10 XHCI ×2（15B6/15B7）、USB 3.10 XHCI（43F7）、USB 2.0 XHCI（15B8）
  - USB ルートハブ（USB 3.0）×5
  - Logicool StreamCam の HID 子インターフェース（MI_05）
- 変更対象が存在しなかったもの: MOTU M Series 本体／StreamCam の映像・音声インターフェースはドライバが省電力設定項目を公開していないため変更不可（ハブ／コントローラ側で無効化済みのため実効面はカバー）。

## 復元ポイント
- 「Before AMD chipset RAID driver update 2026-11-21」を 2026-11-21 16:43 に作成成功（先行作業で確認）。他に同日 04:04 の Windows Update のもの。
- 注: 本検証セッション（非昇格 SSH）では Get-ComputerRestorePoint の列挙が 0 件を返したが、これは列挙に管理者昇格が要るための見かけであり、作成自体は先行作業で確認済み。

## 再起動の記録と #2 の要否判定
- 再起動 #1: 2026-11-21 16:55 発行 → OS 起動完了 16:56:24（LastBootUpTime で確認）。ただし Tailscale はユーザーのログインまで戻らず、検証はユーザーのログイン（17:24 頃）後に再開した。Tailscale はログオンで起動する構成の可能性が高い。
- **再起動 #2 は不要と判定**（2026-11-21 17:26〜17:31 実測）。根拠:
  - PendingFileRenameOperations の実エントリ 0 件（値は空文字列のみ）
  - CBS RebootPending = false、WU RebootRequired = false
  - 全デバイス CME=0 で「再起動が必要」状態のデバイスなし
  - RAID 3点の実ファイルが既に 9.3.3-00291、GPIO／I2C も DriverStore 新パッケージを実効ロード済み（AMD リリースノートの「連続2回再起動」は一般規定であり、本機では1回で全ドライバの有効化が実測完了）

## 本番復帰確認（2026-11-21 17:26〜17:31）
- LastBootUpTime: 2026-11-21 16:56:24（想定どおり）
- Minidump: 4 件のまま、最新は 112126-8546-01.dmp @ 11:17:26（今朝の 0x139）。新規なし
- Event 41／1001／6008: 16:55 以降 0 件
- 8081/health: **200**、モデルは Qwen3.8-27B-UD-Q3_K_XL（llama-server PID 17924）。注: 起動直後は bantoh-llama が未起動で 8081 が閉じていたため、タスクを手動開始して復帰させた（従来の復帰手順どおり）
- 11434（Ollama）: 200
- 8788（Gateway）: 200、Docker は bantoh-gateway／bantoh-ntfy／bantoh-redis の3コンテナ Up
- watchdog（bantoh-llama-watchdog）: Ready・Enabled=True、bantoh-llama: Ready・Enabled=True
- D:（RAID）: Healthy／NTFS、空き 1,321.5GB、読み書きテスト OK

## 残る注意点
- 次に BSOD が出たら `C:\WINDOWS\Minidump` の最新ダンプ時刻と Event 1001 を確認する。rcbottom 系なら本日更新分 9.3.3.291 での再発、USBXHCI 系なら今回の省電力無効化でも止まらなかったことになる。切り分けの起点は変わらずこの2系統。
- Tailscale は再起動後にユーザーのログインまで戻らない構成の可能性が高い。今後メンテ再起動を行う際は、復帰確認の前に現地ログインが要る前提で計画すること。
- MOTU M Series と StreamCam の切り分け（片方ずつの切り離し／別コントローラへの移設、MOTU のドライバ・ファームウェア更新確認）は未実施。0x139 が再発したら次の一手。
