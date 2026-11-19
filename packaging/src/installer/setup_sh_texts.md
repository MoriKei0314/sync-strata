# setup.sh（Linux）の画面の文の一覧

`pack/src/installer/setup.sh` の文の表（関数 `tx`）から作った一覧です（係 L，11/16）．文を直すときは setup.sh の表を直し，この一覧を作り直します．
言葉は環境変数 `LANG`（`LC_ALL`・`LC_MESSAGES` が先．`SYNC_LANG` か `--lang ja|en` で上書き）が `ja` で始まれば日本語，ほかは英語．
`%s` には値（部品の名前・版・道のり・GPU の名前など）が入ります．

## 結果の行の頭の札（[入れた] など）

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `tag_installed` | installed | 入れた |
| `tag_repaired` | repaired | 直した |
| `tag_skipped` | skipped | 飛ばした |
| `tag_stopped` | not done | 止めた |
| `tag_failed` | failed | 失敗 |
| `tag_created` | created | 作った |
| `tag_found` | found | 見つけた |
| `tag_chosen` | chosen | 選んだ |
| `tag_none` | none | なし |
| `tag_note` | note | 注意 |
| `tag_engine` | engine | エンジン |
| `tag_ok` | supported | 対応 |
| `tag_ng` | not supported | 対応外 |
| `tag_removed` | removed | 消した |
| `tag_kept` | kept | 残した |
| `tag_rolledback` | rolled back | 戻した |
| `tag_optional` | optional | 任意 |
| `tag_st_ok` | ok | そろっている |
| `tag_st_broken` | broken | 壊れている |
| `tag_st_missing` | missing | ない |

## 部品ごとの理由

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `why_new` | new | 新規 |
| `why_repair` | reinstalling, %s file(s) were broken | 壊れていた %s ファイルを入れ直す |
| `why_broken_upgrade` | %s was broken, installing %s | 壊れていた %s を %s に |
| `why_newer_installed` | the installed %s is newer | 入っている %s の方が新しい |
| `why_rolled_back` | %s was rolled back, so it is not installed (use --force) | %s は戻した版なので入れない（--force で入れる） |
| `why_upgrade` | %s -> %s | %s → %s |
| `why_rebuild` | rebuild of the same version %s | 同じ版 %s の作り直し |
| `why_same` | up to date | そろっている |

## 結果の行（部品）

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `line_skip` | %s %s (%s, checked in %s s) | %s %s（%s、調べ %s 秒） |
| `line_done` | %s %s (%s, %s file(s), %s MB, %s s) | %s %s（%s、%s ファイル、%s MB、%s 秒） |
| `line_fail` | %s %s: %s (the previous version is kept) | %s %s: %s（前の版のまま） |
| `line_stopped` | %s %s (%s) | %s %s（%s） |

## 進み具合の見出し

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `hdr_comp` | == %s (%s): %s | == %s（%s）: %s |
| `hdr_setup` | Sync-Strata setup: installing to %s | Sync-Strata の setup: 入れる先 %s |
| `hdr_update` | Sync-Strata update: from %s | Sync-Strata の update: 置き場 %s |

## 結果の見出し

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `result_head` | Result (%s, %s s): | 結果（%s、%s 秒）: |

## 進み具合

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `say_fetch` |    %s is not here, so it is downloaded from the update place (%s MB). |    %s は手元にないので、更新の置き場から取ります（%s MB）。 |

## 動いているので止めたとき

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `running_head` | Sync-Strata is running, so nothing was changed (files in use cannot be replaced): | Sync-Strata が動いているので、何も変えませんでした（使っているファイルは入れ替えられません）: |
| `running_item` |      pid %s  %s |      番号 %s  %s |
| `running_hint` |    Close the app with "Close all", or run: %s down --all. Then run this again. |    アプリを「全て閉じる」で閉じるか、%s down --all を流してから、もう一度流してください。 |

## エンジン

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `engine_none` | engine (no engine fits the GPU of this PC; see "not supported" below) | エンジン（この PC の GPU に合う物がありません。下の「対応外」を見てください） |

## 対応環境の調べ（最後に出す．env_ok・env_ng が結論の 1 行）

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `env_ok` | This PC can run Sync-Strata. | この PC で使えます。 |
| `env_ng` | This PC cannot run Sync-Strata. | この PC では使えません。 |
| `env_engine` | %s (%s) | %s（%s） |
| `env_app_only` | The app was installed, but no engine was installed. | アプリは入れましたが、エンジンは入れていません。 |
| `env_no_gpu` | No supported GPU was found. An NVIDIA GTX 10 series or newer, or an AMD Radeon RX 6000 series or newer is needed. | 対応する GPU が見つかりません。NVIDIA の GTX 10 シリーズ以降か、Radeon の RX 6000 シリーズ以降が必要です。 |
| `env_gpu_too_old` | This GPU (%s) is not supported. An NVIDIA GTX 10 series or newer, or a Radeon RX 6000 series or newer is needed. | この GPU（%s）には対応していません。NVIDIA の GTX 10 シリーズ以降か、Radeon の RX 6000 シリーズ以降が必要です。 |
| `env_igpu_only` | Built-in graphics (%s) are not supported. A separate NVIDIA or Radeon graphics card is needed. | 内蔵の GPU（%s）には対応していません。NVIDIA か Radeon のグラフィックボードが必要です。 |
| `env_gpu_turing_pending` | Support for the RTX 20 series (%s) is still being checked. | RTX 20 シリーズ（%s）への対応は確認中です。 |
| `env_driver_old` | Please update the NVIDIA driver (now %s; %s or later is needed). | NVIDIA のドライバーを更新してください（今は %s、%s 以降が必要です）。 |
| `env_nvidia_no_driver` | An NVIDIA GPU (%s) was found, but its driver is not working (nvidia-smi gives no answer). Install the NVIDIA driver 580 or later. | NVIDIA の GPU（%s）はありますが、ドライバーが動いていません（nvidia-smi が答えません）。NVIDIA のドライバー 580 以降を入れてください。 |
| `env_amdgpu_missing` | The Radeon is not using the amdgpu driver (now: %s). The amdgpu driver is needed. | Radeon が amdgpu のドライバーで動いていません（今: %s）。amdgpu のドライバーが必要です。 |
| `env_kfd_missing` | /dev/kfd was not found, so the Radeon cannot be used for computing. A newer kernel with the amdgpu driver is needed. | /dev/kfd がないため、Radeon で計算できません。amdgpu のドライバーが入った新しいカーネルが必要です。 |
| `env_kfd_denied` | You have no access to the Radeon (/dev/kfd). Run: sudo usermod -aG render,video %s  then log out and log in again. | Radeon（/dev/kfd）を使う許可がありません。sudo usermod -aG render,video %s を流し、ログインし直してください。 |
| `env_no_avx2` | This CPU does not support AVX2, which is required. | この CPU は AVX2 に対応していないため使えません。 |
| `env_glibc_old` | This Linux is too old (glibc %s). glibc 2.28 or later is needed (Ubuntu 20.04, Debian 10, RHEL 8 or later). | この Linux は古いため使えません（glibc %s）。glibc 2.28 以降が必要です（Ubuntu 20.04、Debian 10、RHEL 8 以降）。 |
| `env_no_glibc` | glibc was not found. Linux without glibc (such as Alpine) is not supported. | glibc が見つかりません。glibc のない Linux（Alpine など）には対応していません。 |
| `env_gpu_untested` | This GPU (%s) should work, but it has not been tested yet. | この GPU（%s）は動く見込みですが、まだ確認していません。 |
| `env_gpu_experimental` | Support for this GPU (%s) is experimental. It has not been tested on a real PC. | この GPU（%s）への対応は試験的な機能です。実機では確認していません。 |
| `env_vram_low` | The GPU has only %s GB of memory, so it may be slow (12 GB or more is recommended). | GPU のメモリが %s GB と少ないため、遅くなることがあります（12 GB 以上を推奨）。 |
| `env_vram_unknown` | The amount of GPU memory could not be read. Settings will be on the safe side. | GPU のメモリの量を読めませんでした。設定は控えめにします。 |
| `env_ram_low` | This PC has only %s GB of memory, so it may be slow (32 GB or more is recommended). | PC のメモリが %s GB と少ないため、遅くなることがあります（32 GB 以上を推奨）。 |
| `env_no_avx512` | This CPU has no AVX-512. It works, but expect it to be about 10% slower. | この CPU は AVX-512 に対応していません。動きますが、1 割ほど遅くなる見込みです。 |
| `env_no_downloader` | Neither curl nor wget was found. Updates and some engines cannot be downloaded. | curl も wget も見つかりません。更新と一部のエンジンは落とせません。 |
| `env_launcher_engine` | The app picks the engine %s (setup picked %s). %s was installed. | アプリはエンジン %s を選びます（setup の見立ては %s）。%s を入れました。 |
| `env_check_failed` | Could not check this PC. | この PC を調べられませんでした。 |

## モデルの置き場

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `models_kept` | models folder (as set: %s, packs: %s) | モデルの置き場（設定のまま %s。pack: %s） |
| `models_given_empty` | the models folder %s has no models yet (saved, so the app can download them there) | 指したモデルの置き場 %s にはまだモデルがありません（書いておくので、アプリの案内で落とせます） |
| `models_nosearch` | searching for models (--no-model-search) | モデルの置き場を探す（--no-model-search） |
| `models_found` | models folder %s (packs: %s%s; saved in settings.json, nothing is downloaded again) | モデルの置き場 %s（pack: %s%s。settings.json に書きました。落とし直しません） |
| `models_missing_shared` | ; missing shared parts: %s | 。足りない共通の部品: %s |
| `models_notfound` | no models found (looked at %s places in %s s). The first screen of the app downloads them. | モデルは見つかりませんでした（%s か所を %s 秒で見ました）。アプリの最初の画面の案内で落とします。 |
| `models_default_ok` | models will be downloaded to %s (%s GB free) | モデルは %s に落とします（空き %s GB） |
| `models_chosen` | models folder %s (%s GB free; the default place has only %s GB free). Saved in settings.json. | モデルの置き場 %s（空き %s GB。既定の置き場は空き %s GB で足りないため）。settings.json に書きました。 |
| `models_no_space` | not enough free space for the models (about %s GB is needed; the most is %s GB at %s) | モデルを入れる空きが足りません（約 %s GB 要ります。いちばん多いのは %s GB（%s）） |

## dsh の設定

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `dsh_made` | dsh settings %s (%s) | dsh の設定 %s（%s） |
| `dsh_kept` | dsh settings (already there, left as is) | dsh の設定（もうあるので触りません） |

## 入口（update.sh など）

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `stubs_made` | commands %s | 入口 %s |

## アイコン（.desktop．名前は英語と日本語の両方を書き，デスクトップの言葉で出る）

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `sc_made` | %s shortcut(s): %s | アイコン %s 個: %s |
| `sc_missing` | shortcut "%s" (its target %s is not there yet) | アイコン「%s」（行き先 %s がまだありません） |
| `sc_main_name` | Sync-Strata | Sync-Strata |
| `sc_main_comment` | Local LLM on this PC | この PC で動くローカルの LLM |
| `sc_update_name` | Update Sync-Strata | Sync-Strata の更新 |
| `sc_rollback_name` | Sync-Strata: back to the previous version | Sync-Strata を前の版に戻す |
| `sc_uninstall_name` | Uninstall Sync-Strata | Sync-Strata を消す |

## 入口の中の文（英語と日本語を並べて出す）

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `stub_missing` | The setup is missing. Run setup.sh in the downloaded folder again. | setup がありません。落としたフォルダーの setup.sh をもう一度流してください。 |
| `stub_pause` | Press Enter to close. | Enter で閉じます。 |

## CPU の優先度の許可（任意）

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `nice_ok` | CPU priority permission: yes (ulimit -e is %s) | CPU の優先度を上げる許可: あり（ulimit -e が %s） |
| `nice_hint` | Keeps the speed when other apps use the CPU (needs sudo). Run these commands; they work after a restart: | ほかのアプリが CPU を使っているときの速さの落ちを抑えます（sudo が要ります）。次のコマンドを流すと、PC の起動し直しの後に効きます: |
| `nice_check` | Check after the restart: ulimit -e shows 30. Or run: %s --apply-nice | 確かめ: 起動し直した後に ulimit -e が 30 になります。%s --apply-nice でも書けます。 |
| `nice_applied` | CPU priority permission written. It works after a restart (check: ulimit -e shows 30). | CPU の優先度の許可を書きました。PC を起動し直すと効きます（確かめ: ulimit -e が 30）。 |
| `nice_failed` | could not write the CPU priority permission (%s) | CPU の優先度の許可を書けませんでした（%s） |

## rollback

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `rb_nothing` | Nothing to roll back (the last update replaced nothing). | 戻せる物がありません（直前の update で入れ替えた部品がありません）。 |
| `rb_fail` | %s: the previous version is missing or broken (%s) | %s: 前の版が残っていないか、壊れています（%s） |
| `rb_done` | %s %s -> %s (%s s). The next update will not install %s again; use update --force for that. | %s %s → %s（%s 秒）。%s は次の update でも入れません。入れるときは update --force。 |

## update

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `up_not_installed` | Sync-Strata is not installed (%s). Run setup.sh first. | Sync-Strata が入っていません（%s）。先に setup.sh を流してください。 |
| `up_no_feed` | No update place is set. Put a folder or URL in update_feed of settings.json, or run: update.sh --source <place> | 更新の置き場が決まっていません。settings.json の update_feed にフォルダーか URL を書くか、update.sh --source <置き場> で流してください。 |

## uninstall

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `un_no_state` | The record of Sync-Strata (state/state.json) was not found, so nothing was removed: %s | Sync-Strata の記録（state/state.json）がないので、消しません: %s |
| `un_unsafe` | %s is not a Sync-Strata folder, so it was not removed. | %s は Sync-Strata の置き場ではないので、消しません。 |
| `un_ask_models` | Also remove the models (%s)? You will need to download them again. [y/N]  | モデル（%s）も消しますか？ 消すと次は落とし直しになります。[y/N]  |
| `un_ask_home` | Also remove the settings and chats (%s)? [y/N]  | 設定と会話（%s）も消しますか？ [y/N]  |
| `un_shortcuts` | %s shortcut(s) | アイコン %s 個 |
| `un_app` | app %s | アプリ %s |
| `un_models` | models %s | モデル %s |
| `un_home` | settings and chats %s | 設定と会話 %s |

## status

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `st_line` | %s %s (%s file(s)%s) | %s %s（%s ファイル%s） |
| `st_prev` | , keeping the previous version %s | 。前の版 %s を残しています |
| `st_none` | Nothing is installed (%s). | 何も入っていません（%s）。 |

## 失敗の理由

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `err_zip_size` | %s: the zip size differs from the list (%s, list %s) | %s: zip の大きさが一覧と違います（%s、一覧 %s） |
| `err_zip_sha` | %s: the zip sha256 differs from the list | %s: zip の sha256 が一覧と違います |
| `err_zip_missing` | zip not found: %s (no update place is set) | 部品の zip がありません: %s（更新の置き場も決まっていません） |
| `err_zip_outside` | the list points outside its folder: %s | 一覧が置き場の外を指しています: %s |
| `err_content` | %s: the contents do not match the list (%s, %s files differ) | %s: 中身が一覧と合いません（%s、違うファイル %s） |
| `err_unzip` | %s: could not unpack the zip | %s: zip を展開できませんでした |
| `err_badpath` | %s: the zip has a bad path: %s | %s: zip の中の道のりがおかしいです: %s |
| `err_download` | could not download %s | %s を取れませんでした |
| `err_no_downloader` | curl or wget is needed to download %s | %s を取るには curl か wget が要ります |
| `err_move` | could not replace %s (a file may be in use) | %s を入れ替えられませんでした（使われているファイルがあるかもしれません） |
| `err_no_source` | No release list was found next to setup.sh. Run setup.sh in the unpacked folder, or give --source <place>. | setup.sh の隣に版の一覧がありません。展開したフォルダーの setup.sh を流すか、--source <置き場> を付けてください。 |
| `err_no_manifest` | release list not found: %s | 版の一覧がありません: %s |
| `err_bad_manifest` | this is not a Sync-Strata release list: %s | Sync-Strata の版の一覧ではありません: %s |
| `err_platform` | this release list is for %s. Use the setup of that package. | この一覧は %s 用です。その配布物の setup を使ってください。 |
| `err_no_unzip` | unzip or python3 is needed to unpack the files. Install one (for example: sudo apt install unzip) and run setup.sh again. | 展開に unzip か python3 が要ります。どちらかを入れて（例: sudo apt install unzip）、もう一度 setup.sh を流してください。 |
| `err_tool` | this command is needed but was not found: %s | このコマンドが要りますが、見つかりません: %s |
| `err_locked` | another setup is running (pid %s). | ほかの setup が動いています（番号 %s）。 |
| `err_args` | unknown option: %s (see: setup.sh --help) | 知らないオプションです: %s（setup.sh --help を見てください） |
| `err_home` | HOME is not set. | HOME が決まっていません。 |

## 使い方（--help）

| 鍵 | 英語 | 日本語 |
|---|---|---|
| `usage` | Usage: setup.sh [setup\|update\|rollback\|uninstall\|status] [options]<br>  setup      install only what is missing, old or broken (safe to run again)<br>  update     replace only the changed parts (keeps the previous version)<br>  rollback   go back to the version before the last update<br>  uninstall  remove the app and shortcuts (asks about models and settings)<br>  status     show the installed parts<br>Options: --source PLACE  --app-dir DIR  --sync-home DIR  --models-dir DIR  --no-shortcuts<br>         --no-model-search  --full  --force  --yes  --remove-data  --apply-nice  --report FILE  --lang ja\|en<br> | 使い方: setup.sh [setup\|update\|rollback\|uninstall\|status] [オプション]<br>  setup      足りない物・古い物・壊れた物だけ入れます（何度流しても同じ）<br>  update     変わった部品だけ入れ替えます（前の版を残します）<br>  rollback   直前の update の前の版に戻します<br>  uninstall  アプリとアイコンを消します（モデルと設定は聞きます）<br>  status     入っている部品を出します<br>オプション: --source 置き場  --app-dir DIR  --sync-home DIR  --models-dir DIR  --no-shortcuts<br>         --no-model-search  --full  --force  --yes  --remove-data  --apply-nice  --report FILE  --lang ja\|en<br> |
