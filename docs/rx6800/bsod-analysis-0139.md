# BSOD 原因特定（第2件）— 2026-11-21 11:11 の bugcheck 0x139（winmain）

## 結論
**障害モジュールは Microsoft の USB 3.x ホストコントローラドライバ `USBXHCI.SYS`。前回の `rcbottom.sys`（AMD-RAID）とは無関係の、別系統のクラッシュ。**
母艦には少なくとも2系統のドライバ不安定性が存在する。

## 解析
- 手段: 母艦の WinDbg (cdb.exe 10.0.29680.1004) + Microsoft シンボルサーバ。前回と同一構成。
- 対象: `C:\WINDOWS\Minidump\112126-8546-01.dmp`。生ログ: 母艦 `C:\Users\kesui\analyze0139.log`。
- Event 1001: bugcheck `0x00000139 (0x0000000000000003, 0xffff9a8b02036ac0, 0xffff9a8b02036a18, 0x0)`、レポート ID c46e6eb2-4991-4acd-bb48-86d753fbc9dc。

## !analyze -v の要点
- Bugcheck: `KERNEL_SECURITY_CHECK_FAILURE (139)`、**Arg1 = 3 = CORRUPT_LIST_ENTRY**（LIST_ENTRY の二重削除＝double remove を検出して即時停止）。
- Failure Bucket: `0x139_3_CORRUPT_LIST_ENTRY_USBXHCI!Isoch_Stage_CompleteTD`
- `IMAGE_NAME: USBXHCI.SYS` / `SYMBOL_NAME: USBXHCI!Isoch_Stage_CompleteTD+294`
- スタック要約: `USBXHCI!Interrupter_WdfEvtInterruptDpc → Isoch_ProcessTransferEventWithED1 → Isoch_Stage_CompleteTD → Wdf01000!imp_WdfRequestUnmarkCancelable → FxIrpQueue::RemoveIrpFromListEntry → FatalListEntryError → nt!KiRaiseSecurityCheckFailure`。つまり USB のアイソクロナス転送（等時転送）の完了処理で、取り消し済みリクエストをキューから二重に外そうとして破損を検出した。
- スタックに rcbottom / rcraid / GPU 系は一切なし。PROCESS_NAME: System。

## 0x139 Arg1=3 の意味（平易に）
カーネル内の「リストのつなぎ直し」が壊れているのを Windows が検出し、被害が広がる前に強制停止した、という種類のエラー。今回は USB ドライバが転送リクエストの後片付けをする際、既に外したはずの項目をもう一度外そうとした（二重削除）ことが直接の引き金。

## ドライバの素性
- `C:\Windows\System32\drivers\USBXHCI.SYS`、**バージョン 10.0.26100.8972**、提供元 Microsoft Corporation、ファイル日付 **2026/11/20 08:13**（前日の Windows Update で差し替わった直後の版）。
- OS: Windows 11 Pro build 26300。
- コントローラ: AMD USB 3.10 eXtensible Host Controller（Microsoft ドライバで駆動）×2。

## 状況証拠と候補デバイス
- アイソクロナス転送を使う常駐 USB デバイスは2つ: **MOTU M Series**（USB オーディオインターフェース）と **Logicool StreamCam**（カメラ＋マイク）。どちらも等時転送の代表的な利用者。
- ダンプのスタックだけでは、どちらのデバイスの転送だったかまでは特定できない。
- 発生は Sync-Strata 停止中の通常運用下（11:11）。前後（11:00〜11:20）の System ログに前兆となる警告・エラーはなし（記録は 11:17 の起動時イベントから）。
- USBXHCI.SYS 自体が更新直後（11/20）の版である点は留意に値するが、それが原因と断定する材料はない。

## 前回の rcbottom 件との関係
- **無関係**。モジュール、スタック、契機（ディスク I/O 集中 vs USB 転送完了処理）がすべて異なる。
- 共通するのは「母艦のドライバ層が全体として盤石ではない」という点のみ。2日連続で異なる系統の BSOD が出ていることは、個別対策に加えて OS／ドライバ全体の健全性（更新チャネル、チップセットドライバ一式の版）を見る価値がある。

## 対策の選択肢（未実施・ユーザー判断待ち）
1. USB デバイス側の切り分け: MOTU M Series と StreamCam のどちらが契機か、片方ずつ外す／別ポート（別コントローラ）へ移す運用で再発有無を見る。MOTU のドライバ／ファームウェア更新の有無も確認候補。
2. USB の電源管理を切る（デバイスマネージャで XHCI と各デバイスの「電力節約のための停止」を無効化）: アイソクロナス転送の取消し競合は省電力遷移が契機になることがある。
3. チップセットドライバ（AMD 公式）の一括更新で USB コントローラ周りの土台を揃える。前回の RAID ドライバ更新と合わせて実施すると効率がよい。
4. Windows Update で USBXHCI.SYS が新しい版に差し替わるのを待つ（11/20 に更新されたばかりの版なので、修正が後続更新に含まれる可能性はある）。
5. 当面のリスク受容: 発生頻度が低いなら、再発時にデバイス構成を記録する運用でも可。ただし2日で2件の BSOD は頻度として低くない。
