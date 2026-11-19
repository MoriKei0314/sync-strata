# 保存先を変える（Windows）

[English](STORAGE.md) | 日本語

Sync-Strata が使う場所は 3 つです。どれもコマンドで変えられます（画面からはまだ変えられません）。

| 置き場 | 既定の場所 | 大きさ | 変え方 |
|---|---|---|---|
| アプリ本体 | `%LOCALAPPDATA%\Programs\SyncStrata` | 約 2 GB | `setup.cmd -AppDir` |
| モデル | `%LOCALAPPDATA%\SyncStrata\models` | 60〜100 GB | `setup.cmd -ModelsDir`・`sync settings set models_dir` |
| 設定と会話（`SYNC_HOME`） | `%LOCALAPPDATA%\SyncStrata` | 小さい | （変えずに使ってください） |

- 会話のキャッシュ（1 つ 0.4〜0.5 GB、合計で最大 20 GB）は、モデルを別のドライブにすると、自動でそのドライブの `SyncStrata-sessions` に置かれます。
- フォルダーの名前は短く、日本語を含まない場所をおすすめします。
- 以下のコマンドは、コマンドプロンプトで実行します。`setup.cmd` は、展開した zip のフォルダーで実行してください。

## アプリ本体の場所を変える

### これからインストールする

```
setup.cmd -AppDir E:\SyncStrata
```

### インストールした後に移す

1. アプリを「全て閉じる」で終了します。
2. 今のアプリをアンインストールします。モデルと、設定・会話を消すか聞かれたら、そのまま Enter を押してください（残します）。

   ```
   "%LOCALAPPDATA%\Programs\SyncStrata\uninstall.cmd"
   ```

3. 展開した zip のフォルダーで、新しい場所にインストールします。

   ```
   setup.cmd -AppDir E:\SyncStrata
   ```

- 設定とモデルはそのまま引き継がれます。デスクトップとスタートメニューのアイコンは、新しい場所を指します。
- **順番を逆にしないでください。** 先に新しい場所へインストールしてから前のアプリをアンインストールすると、新しいアイコンも消えます。
- 場所を変えた後は、`sync.cmd` が `E:\SyncStrata\app\launcher\sync.cmd` になります。

## モデルの保存先を変える

### これからインストールする

```
setup.cmd -ModelsDir E:\SyncStrata\models
```

アプリ本体と一緒に変えるときは、`setup.cmd -AppDir E:\SyncStrata -ModelsDir E:\SyncStrata\models` のように並べます。

### インストールした後、モデルをまだダウンロードしていない

```
"%LOCALAPPDATA%\Programs\SyncStrata\app\launcher\sync.cmd" settings set models_dir E:\SyncStrata\models
```

実行してから、アプリを開き、案内に沿ってダウンロードしてください。

### もうダウンロードしたモデルを移す

1. アプリを「全て閉じる」で終了します。
2. `%LOCALAPPDATA%\SyncStrata\models` フォルダーを、丸ごと `E:\SyncStrata\models` に移動します。
3. 上と同じ `sync.cmd settings set models_dir E:\SyncStrata\models` を実行して、アプリを開きます。

- ダウンロードし直す必要はありません。
- 移した後は、モデルの欄の「検査済み」の表示が消えます。動作は同じです。気になるときは、モデルの欄の「ファイルを検査」で確かめ直せます。

## 確認した環境

0.1.1 を Windows 11 にインストールし、上の手順をすべて試しました（新しくインストール、インストールした後に移す、モデルの保存先の指定、ダウンロード済みのモデルを移して起動）。
