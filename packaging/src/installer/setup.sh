#!/bin/sh
# Sync-Strata の setup（Linux．係 L，11/16）．Windows の installer/installer.ps1 と同じ働きを sh だけで持つ．
#
#   ./setup.sh [setup]   入っている物を調べ，無い物・古い物・壊れた物だけ入れる（初回・修理・別の PC のどれも同じ 1 つ）
#   ./setup.sh update    更新の置き場の新しい一覧を見て，変わった部品だけ入れ替える（前の版を 1 つ残す）
#   ./setup.sh rollback  直前の update で入れ替えた部品を前の版に戻す
#   ./setup.sh uninstall アプリとアイコンを消す（モデルと SYNC_HOME は聞いてから．既定は残す）
#   ./setup.sh status    入っている部品と版
#   オプション: --source <置き場> --app-dir DIR --sync-home DIR --models-dir DIR --shortcut-dir DIR --no-shortcuts
#              --no-model-search --full --force --yes --remove-data --apply-nice --report FILE --lang ja|en
#
# 置き場（INTERFACE.md の 8「Linux 版」）:
#   アプリ   --app-dir（既定 $SYNC_APP_DIR，無ければ $XDG_DATA_HOME/SyncStrata＝~/.local/share/SyncStrata）の app/<部品>/
#   利用者   SYNC_HOME（--sync-home，$SYNC_HOME，無ければ $XDG_CONFIG_HOME/SyncStrata＝~/.config/SyncStrata）．update・rollback は触らない
#   モデル   settings.json の models_dir（setup が探して書く．既定は ~/.local/share/SyncStrata/models）．落とし直さない・消さない
# 部品の zip の中: _pkg/component.json（id・版・files_sha256），_pkg/files.tsv（道のり \ 区切り・大きさ・sha256），_pkg/exec.txt（chmod +x）．
# 世代ごとのエンジン（一覧の variant）は，下の表で GPU を見分けて合う 1 つだけ入れる（起動の道具の sync env とも照らす）．
# 手元に無い zip は，setup の隣（展開したフォルダーかその 1 つ上）→ 一覧の update_feed（URL）の順に探す．
# 要る物: sh・awk・find・sha256sum（どれも標準），展開に unzip か python3（どちらか），落とすときだけ curl か wget．root は要らない．
# 終了コード: 0＝済んだ（何もすることが無かったも含む），5＝一覧と合わない zip を断った，6＝失敗（前の版のまま），7＝動いているので入れ替えなかった，2＝引数の誤り．
# 試すときの入口: SYNC_ENV_OVERRIDE（GPU などの調べを差し替える JSON．起動の道具の sync_env.py と同じ形＋Linux の鍵 glibc・kfd・amdgpu・adapters[].device），
#   SYNC_SETUP_UNZIP（unzip｜py｜bsdtar），SYNC_SETUP_DOWNLOADER（curl｜wget｜python｜none），SYNC_SETUP_AWK，SYNC_SETUP_SUDO・SYNC_SETUP_ETC_ROOT（--apply-nice の試し）．
# shellcheck disable=SC3043,SC2059
#   SC3043: local（dash・bash・busybox の sh は持つ）．SC2059: printf の書式は下の文の表から取る．

# ============================================================================ 表（変えるのはここだけ）
# NVIDIA: compute_cap の範囲 [下, 上) → エンジン 種類．launcher/sync_env.py の ENGINE_BY_CC と同じ（変えるときは両方）
NV_TABLE='12.0 99.0 cuda13 untested
8.6 12.0 cuda13 ok
8.0 8.6 cuda13 untested
7.5 7.6 cuda13 turing
6.0 7.0 cuda12 experimental'
TURING=warn            # RTX 20・GTX 16（7.5）: warn＝動く見込みとして通す／block＝断る
# NVIDIA のドライバーの下限（Linux．11/16 エンジン 3）: driver_version を「.」で分けて数で比べる（575.51.03 ＜ 575.57.08）
DRIVER_MIN='cuda13 580.95.05
cuda12 575.57.08'
# Radeon: PCI の device ID の範囲 → エンジン（古い pci.ids で名前が出ない PC でも見分けられるよう，名前より先に見る）
#   rdna2 のキットは gfx1030〜1032・gfx1034（11/16 エンジン 3 が gfx1032・gfx1034 を足して組む）
RADEON_IDS='0x7550 0x755f hip-rx9070 RX-9070系-Navi48-gfx1201
0x7590 0x759f hip-rx9070 RX-9060系-Navi44-gfx1200
0x7440 0x745f hip-rdna3 RX-7900系-Navi31-gfx1100
0x7470 0x747f hip-rdna3 RX-7800・7700系-Navi32-gfx1101
0x7480 0x749f hip-rdna3 RX-7600系-Navi33-gfx1102
0x73a0 0x73bf hip-rdna2 RX-6800・6900系-Navi21-gfx1030
0x73c0 0x73df hip-rdna2 RX-6700系-Navi22-gfx1031
0x73e0 0x73ff hip-rdna2 RX-6600・6650系-Navi23-gfx1032
0x7420 0x743f hip-rdna2 RX-6500・6400系-Navi24-gfx1034
0x1586 0x1586 hip-rdna3 Ryzen-AI-Max-Strix-Halo-gfx1151'
# 名前（ID が表に無いとき．sync_env.py の RADEON と同じ見方．小文字にして照らす）: エンジン 拡張正規表現
RADEON_NAMES='hip-rx9070 rx.?9[0-9][0-9][0-9]
hip-rdna3 rx.?7[0-9][0-9][0-9]
hip-rdna2 rx.?6[0-9][0-9][0-9]
hip-rdna3 radeon *(\(tm\))? *80[456]0s'
# 内蔵の Radeon（対応外の理由を「内蔵」にする）: device ID と名前
AMD_IGPU_IDS='0x15d8 0x15dd 0x1636 0x1638 0x164c 0x15e7 0x1681 0x164e 0x15bf 0x15c8 0x150e 0x1506 0x163f 0x13c0'
IGPU_NAME_RE='radeon *\(tm\) *graphics|radeon graphics|vega [0-9]+ graphics'
VRAM_WARN_GIB=12       # これ未満は注意（sync_env.py と同じ）
RAM_WARN_GIB=32
GLIBC_MIN=2.28         # エンジンのキット・Node 24 の下限
NICE_LIMIT=-10         # CPU の優先度の許可（--apply-nice）

# ============================================================================ 文（英語と日本語．setup_sh_texts.md はここから作る）
# 1 行 1 つ: 鍵) E='英語'; J='日本語' ;;   %s は値．日本語の句読点は「、。」．
tx() {
  case $1 in
    tag_installed) E='installed'; J='入れた' ;;
    tag_repaired) E='repaired'; J='直した' ;;
    tag_skipped) E='skipped'; J='飛ばした' ;;
    tag_stopped) E='not done'; J='止めた' ;;
    tag_failed) E='failed'; J='失敗' ;;
    tag_created) E='created'; J='作った' ;;
    tag_found) E='found'; J='見つけた' ;;
    tag_chosen) E='chosen'; J='選んだ' ;;
    tag_none) E='none'; J='なし' ;;
    tag_note) E='note'; J='注意' ;;
    tag_engine) E='engine'; J='エンジン' ;;
    tag_ok) E='supported'; J='対応' ;;
    tag_ng) E='not supported'; J='対応外' ;;
    tag_removed) E='removed'; J='消した' ;;
    tag_kept) E='kept'; J='残した' ;;
    tag_rolledback) E='rolled back'; J='戻した' ;;
    tag_optional) E='optional'; J='任意' ;;
    tag_st_ok) E='ok'; J='そろっている' ;;
    tag_st_broken) E='broken'; J='壊れている' ;;
    tag_st_missing) E='missing'; J='ない' ;;
    why_new) E='new'; J='新規' ;;
    why_repair) E='reinstalling, %s file(s) were broken'; J='壊れていた %s ファイルを入れ直す' ;;
    why_broken_upgrade) E='%s was broken, installing %s'; J='壊れていた %s を %s に' ;;
    why_newer_installed) E='the installed %s is newer'; J='入っている %s の方が新しい' ;;
    why_rolled_back) E='%s was rolled back, so it is not installed (use --force)'; J='%s は戻した版なので入れない（--force で入れる）' ;;
    why_upgrade) E='%s -> %s'; J='%s → %s' ;;
    why_rebuild) E='rebuild of the same version %s'; J='同じ版 %s の作り直し' ;;
    why_same) E='up to date'; J='そろっている' ;;
    line_skip) E='%s %s (%s, checked in %s s)'; J='%s %s（%s、調べ %s 秒）' ;;
    line_done) E='%s %s (%s, %s file(s), %s MB, %s s)'; J='%s %s（%s、%s ファイル、%s MB、%s 秒）' ;;
    line_fail) E='%s %s: %s (the previous version is kept)'; J='%s %s: %s（前の版のまま）' ;;
    line_stopped) E='%s %s (%s)'; J='%s %s（%s）' ;;
    hdr_comp) E='== %s (%s): %s'; J='== %s（%s）: %s' ;;
    hdr_setup) E='Sync-Strata setup: installing to %s'; J='Sync-Strata の setup: 入れる先 %s' ;;
    hdr_update) E='Sync-Strata update: from %s'; J='Sync-Strata の update: 置き場 %s' ;;
    result_head) E='Result (%s, %s s):'; J='結果（%s、%s 秒）:' ;;
    say_fetch) E='   %s is not here, so it is downloaded from the update place (%s MB).'; J='   %s は手元にないので、更新の置き場から取ります（%s MB）。' ;;
    err_zip_size) E='%s: the zip size differs from the list (%s, list %s)'; J='%s: zip の大きさが一覧と違います（%s、一覧 %s）' ;;
    err_zip_sha) E='%s: the zip sha256 differs from the list'; J='%s: zip の sha256 が一覧と違います' ;;
    err_zip_missing) E='zip not found: %s (no update place is set)'; J='部品の zip がありません: %s（更新の置き場も決まっていません）' ;;
    err_zip_outside) E='the list points outside its folder: %s'; J='一覧が置き場の外を指しています: %s' ;;
    err_content) E='%s: the contents do not match the list (%s, %s files differ)'; J='%s: 中身が一覧と合いません（%s、違うファイル %s）' ;;
    err_unzip) E='%s: could not unpack the zip'; J='%s: zip を展開できませんでした' ;;
    err_badpath) E='%s: the zip has a bad path: %s'; J='%s: zip の中の道のりがおかしいです: %s' ;;
    err_download) E='could not download %s'; J='%s を取れませんでした' ;;
    err_no_downloader) E='curl or wget is needed to download %s'; J='%s を取るには curl か wget が要ります' ;;
    err_move) E='could not replace %s (a file may be in use)'; J='%s を入れ替えられませんでした（使われているファイルがあるかもしれません）' ;;
    err_no_source) E='No release list was found next to setup.sh. Run setup.sh in the unpacked folder, or give --source <place>.'; J='setup.sh の隣に版の一覧がありません。展開したフォルダーの setup.sh を流すか、--source <置き場> を付けてください。' ;;
    err_no_manifest) E='release list not found: %s'; J='版の一覧がありません: %s' ;;
    err_bad_manifest) E='this is not a Sync-Strata release list: %s'; J='Sync-Strata の版の一覧ではありません: %s' ;;
    err_platform) E='this release list is for %s. Use the setup of that package.'; J='この一覧は %s 用です。その配布物の setup を使ってください。' ;;
    err_no_unzip) E='unzip or python3 is needed to unpack the files. Install one (for example: sudo apt install unzip) and run setup.sh again.'; J='展開に unzip か python3 が要ります。どちらかを入れて（例: sudo apt install unzip）、もう一度 setup.sh を流してください。' ;;
    err_tool) E='this command is needed but was not found: %s'; J='このコマンドが要りますが、見つかりません: %s' ;;
    err_locked) E='another setup is running (pid %s).'; J='ほかの setup が動いています（番号 %s）。' ;;
    err_args) E='unknown option: %s (see: setup.sh --help)'; J='知らないオプションです: %s（setup.sh --help を見てください）' ;;
    err_home) E='HOME is not set.'; J='HOME が決まっていません。' ;;
    running_head) E='Sync-Strata is running, so nothing was changed (files in use cannot be replaced):'; J='Sync-Strata が動いているので、何も変えませんでした（使っているファイルは入れ替えられません）:' ;;
    running_item) E='     pid %s  %s'; J='     番号 %s  %s' ;;
    running_hint) E='   Close the app with "Close all", or run: %s down --all. Then run this again.'; J='   アプリを「全て閉じる」で閉じるか、%s down --all を流してから、もう一度流してください。' ;;
    engine_none) E='engine (no engine fits the GPU of this PC; see "not supported" below)'; J='エンジン（この PC の GPU に合う物がありません。下の「対応外」を見てください）' ;;
    stubs_made) E='commands %s'; J='入口 %s' ;;
    sc_made) E='%s shortcut(s): %s'; J='アイコン %s 個: %s' ;;
    sc_missing) E='shortcut "%s" (its target %s is not there yet)'; J='アイコン「%s」（行き先 %s がまだありません）' ;;
    sc_main_name) E='Sync-Strata'; J='Sync-Strata' ;;
    sc_main_comment) E='Local LLM on this PC'; J='この PC で動くローカルの LLM' ;;
    sc_update_name) E='Update Sync-Strata'; J='Sync-Strata の更新' ;;
    sc_rollback_name) E='Sync-Strata: back to the previous version'; J='Sync-Strata を前の版に戻す' ;;
    sc_uninstall_name) E='Uninstall Sync-Strata'; J='Sync-Strata を消す' ;;
    stub_missing) E='The setup is missing. Run setup.sh in the downloaded folder again.'; J='setup がありません。落としたフォルダーの setup.sh をもう一度流してください。' ;;
    stub_pause) E='Press Enter to close.'; J='Enter で閉じます。' ;;
    dsh_made) E='dsh settings %s (%s)'; J='dsh の設定 %s（%s）' ;;
    dsh_kept) E='dsh settings (already there, left as is)'; J='dsh の設定（もうあるので触りません）' ;;
    models_kept) E='models folder (as set: %s, packs: %s)'; J='モデルの置き場（設定のまま %s。pack: %s）' ;;
    models_given_empty) E='the models folder %s has no models yet (saved, so the app can download them there)'; J='指したモデルの置き場 %s にはまだモデルがありません（書いておくので、アプリの案内で落とせます）' ;;
    models_nosearch) E='searching for models (--no-model-search)'; J='モデルの置き場を探す（--no-model-search）' ;;
    models_found) E='models folder %s (packs: %s%s; saved in settings.json, nothing is downloaded again)'; J='モデルの置き場 %s（pack: %s%s。settings.json に書きました。落とし直しません）' ;;
    models_missing_shared) E='; missing shared parts: %s'; J='。足りない共通の部品: %s' ;;
    models_notfound) E='no models found (looked at %s places in %s s). The first screen of the app downloads them.'; J='モデルは見つかりませんでした（%s か所を %s 秒で見ました）。アプリの最初の画面の案内で落とします。' ;;
    models_default_ok) E='models will be downloaded to %s (%s GB free)'; J='モデルは %s に落とします（空き %s GB）' ;;
    models_chosen) E='models folder %s (%s GB free; the default place has only %s GB free). Saved in settings.json.'; J='モデルの置き場 %s（空き %s GB。既定の置き場は空き %s GB で足りないため）。settings.json に書きました。' ;;
    models_no_space) E='not enough free space for the models (about %s GB is needed; the most is %s GB at %s)'; J='モデルを入れる空きが足りません（約 %s GB 要ります。いちばん多いのは %s GB（%s））' ;;
    env_ok) E='This PC can run Sync-Strata.'; J='この PC で使えます。' ;;
    env_ng) E='This PC cannot run Sync-Strata.'; J='この PC では使えません。' ;;
    env_engine) E='%s (%s)'; J='%s（%s）' ;;
    env_app_only) E='The app was installed, but no engine was installed.'; J='アプリは入れましたが、エンジンは入れていません。' ;;
    env_no_gpu) E='No supported GPU was found. An NVIDIA GTX 10 series or newer, or an AMD Radeon RX 6000 series or newer is needed.'; J='対応する GPU が見つかりません。NVIDIA の GTX 10 シリーズ以降か、Radeon の RX 6000 シリーズ以降が必要です。' ;;
    env_gpu_too_old) E='This GPU (%s) is not supported. An NVIDIA GTX 10 series or newer, or a Radeon RX 6000 series or newer is needed.'; J='この GPU（%s）には対応していません。NVIDIA の GTX 10 シリーズ以降か、Radeon の RX 6000 シリーズ以降が必要です。' ;;
    env_igpu_only) E='Built-in graphics (%s) are not supported. A separate NVIDIA or Radeon graphics card is needed.'; J='内蔵の GPU（%s）には対応していません。NVIDIA か Radeon のグラフィックボードが必要です。' ;;
    env_gpu_turing_pending) E='Support for the RTX 20 series (%s) is still being checked.'; J='RTX 20 シリーズ（%s）への対応は確認中です。' ;;
    env_driver_old) E='Please update the NVIDIA driver (now %s; %s or later is needed).'; J='NVIDIA のドライバーを更新してください（今は %s、%s 以降が必要です）。' ;;
    env_nvidia_no_driver) E='An NVIDIA GPU (%s) was found, but its driver is not working (nvidia-smi gives no answer). Install the NVIDIA driver 580 or later.'; J='NVIDIA の GPU（%s）はありますが、ドライバーが動いていません（nvidia-smi が答えません）。NVIDIA のドライバー 580 以降を入れてください。' ;;
    env_amdgpu_missing) E='The Radeon is not using the amdgpu driver (now: %s). The amdgpu driver is needed.'; J='Radeon が amdgpu のドライバーで動いていません（今: %s）。amdgpu のドライバーが必要です。' ;;
    env_kfd_missing) E='/dev/kfd was not found, so the Radeon cannot be used for computing. A newer kernel with the amdgpu driver is needed.'; J='/dev/kfd がないため、Radeon で計算できません。amdgpu のドライバーが入った新しいカーネルが必要です。' ;;
    env_kfd_denied) E='You have no access to the Radeon (/dev/kfd). Run: sudo usermod -aG render,video %s  then log out and log in again.'; J='Radeon（/dev/kfd）を使う許可がありません。sudo usermod -aG render,video %s を流し、ログインし直してください。' ;;
    env_no_avx2) E='This CPU does not support AVX2, which is required.'; J='この CPU は AVX2 に対応していないため使えません。' ;;
    env_glibc_old) E='This Linux is too old (glibc %s). glibc 2.28 or later is needed (Ubuntu 20.04, Debian 10, RHEL 8 or later).'; J='この Linux は古いため使えません（glibc %s）。glibc 2.28 以降が必要です（Ubuntu 20.04、Debian 10、RHEL 8 以降）。' ;;
    env_no_glibc) E='glibc was not found. Linux without glibc (such as Alpine) is not supported.'; J='glibc が見つかりません。glibc のない Linux（Alpine など）には対応していません。' ;;
    env_gpu_untested) E='This GPU (%s) should work, but it has not been tested yet.'; J='この GPU（%s）は動く見込みですが、まだ確認していません。' ;;
    env_gpu_experimental) E='Support for this GPU (%s) is experimental. It has not been tested on a real PC.'; J='この GPU（%s）への対応は試験的な機能です。実機では確認していません。' ;;
    env_vram_low) E='The GPU has only %s GB of memory, so it may be slow (12 GB or more is recommended).'; J='GPU のメモリが %s GB と少ないため、遅くなることがあります（12 GB 以上を推奨）。' ;;
    env_vram_unknown) E='The amount of GPU memory could not be read. Settings will be on the safe side.'; J='GPU のメモリの量を読めませんでした。設定は控えめにします。' ;;
    env_ram_low) E='This PC has only %s GB of memory, so it may be slow (32 GB or more is recommended).'; J='PC のメモリが %s GB と少ないため、遅くなることがあります（32 GB 以上を推奨）。' ;;
    env_no_avx512) E='This CPU has no AVX-512. It works, but expect it to be about 15-30%% slower.'; J='この CPU は AVX-512 に対応していません。動きますが、15〜30%% ほど遅くなる見込みです。' ;;
    env_no_downloader) E='Neither curl nor wget was found. Updates and some engines cannot be downloaded.'; J='curl も wget も見つかりません。更新と一部のエンジンは落とせません。' ;;
    env_launcher_engine) E='The app picks the engine %s (setup picked %s). %s was installed.'; J='アプリはエンジン %s を選びます（setup の見立ては %s）。%s を入れました。' ;;
    env_check_failed) E='Could not check this PC.'; J='この PC を調べられませんでした。' ;;
    nice_ok) E='CPU priority permission: yes (ulimit -e is %s)'; J='CPU の優先度を上げる許可: あり（ulimit -e が %s）' ;;
    nice_hint) E='Keeps the speed when other apps use the CPU (needs sudo). Run these commands; they work after a restart:'; J='ほかのアプリが CPU を使っているときの速さの落ちを抑えます（sudo が要ります）。次のコマンドを流すと、PC の起動し直しの後に効きます:' ;;
    nice_check) E='Check after the restart: ulimit -e shows 30. Or run: %s --apply-nice'; J='確かめ: 起動し直した後に ulimit -e が 30 になります。%s --apply-nice でも書けます。' ;;
    nice_applied) E='CPU priority permission written. It works after a restart (check: ulimit -e shows 30).'; J='CPU の優先度の許可を書きました。PC を起動し直すと効きます（確かめ: ulimit -e が 30）。' ;;
    nice_failed) E='could not write the CPU priority permission (%s)'; J='CPU の優先度の許可を書けませんでした（%s）' ;;
    rb_nothing) E='Nothing to roll back (the last update replaced nothing).'; J='戻せる物がありません（直前の update で入れ替えた部品がありません）。' ;;
    rb_fail) E='%s: the previous version is missing or broken (%s)'; J='%s: 前の版が残っていないか、壊れています（%s）' ;;
    rb_done) E='%s %s -> %s (%s s). The next update will not install %s again; use update --force for that.'; J='%s %s → %s（%s 秒）。%s は次の update でも入れません。入れるときは update --force。' ;;
    up_not_installed) E='Sync-Strata is not installed (%s). Run setup.sh first.'; J='Sync-Strata が入っていません（%s）。先に setup.sh を流してください。' ;;
    up_no_feed) E='No update place is set. Put a folder or URL in update_feed of settings.json, or run: update.sh --source <place>'; J='更新の置き場が決まっていません。settings.json の update_feed にフォルダーか URL を書くか、update.sh --source <置き場> で流してください。' ;;
    un_no_state) E='The record of Sync-Strata (state/state.json) was not found, so nothing was removed: %s'; J='Sync-Strata の記録（state/state.json）がないので、消しません: %s' ;;
    un_unsafe) E='%s is not a Sync-Strata folder, so it was not removed.'; J='%s は Sync-Strata の置き場ではないので、消しません。' ;;
    un_ask_models) E='Also remove the models (%s)? You will need to download them again. [y/N] '; J='モデル（%s）も消しますか？ 消すと次は落とし直しになります。[y/N] ' ;;
    un_ask_home) E='Also remove the settings and chats (%s)? [y/N] '; J='設定と会話（%s）も消しますか？ [y/N] ' ;;
    un_shortcuts) E='%s shortcut(s)'; J='アイコン %s 個' ;;
    un_app) E='app %s'; J='アプリ %s' ;;
    un_models) E='models %s'; J='モデル %s' ;;
    un_home) E='settings and chats %s'; J='設定と会話 %s' ;;
    st_line) E='%s %s (%s file(s)%s)'; J='%s %s（%s ファイル%s）' ;;
    st_prev) E=', keeping the previous version %s'; J='。前の版 %s を残しています' ;;
    st_none) E='Nothing is installed (%s).'; J='何も入っていません（%s）。' ;;
    usage) E='Usage: setup.sh [setup|update|rollback|uninstall|status] [options]\n  setup      install only what is missing, old or broken (safe to run again)\n  update     replace only the changed parts (keeps the previous version)\n  rollback   go back to the version before the last update\n  uninstall  remove the app and shortcuts (asks about models and settings)\n  status     show the installed parts\nOptions: --source PLACE  --app-dir DIR  --sync-home DIR  --models-dir DIR  --no-shortcuts\n         --no-model-search  --full  --force  --yes  --remove-data  --apply-nice  --report FILE  --lang ja|en\n'; J='使い方: setup.sh [setup|update|rollback|uninstall|status] [オプション]\n  setup      足りない物・古い物・壊れた物だけ入れます（何度流しても同じ）\n  update     変わった部品だけ入れ替えます（前の版を残します）\n  rollback   直前の update の前の版に戻します\n  uninstall  アプリとアイコンを消します（モデルと設定は聞きます）\n  status     入っている部品を出します\nオプション: --source 置き場  --app-dir DIR  --sync-home DIR  --models-dir DIR  --no-shortcuts\n         --no-model-search  --full  --force  --yes  --remove-data  --apply-nice  --report FILE  --lang ja|en\n' ;;
    *) E=$1; J=$1 ;;
  esac
}

# ============================================================================ 下回り
US=$(printf '\037')        # 中の表の区切り（空の欄を潰さないよう，空白でない文字）
AWK=${SYNC_SETUP_AWK:-awk}
case "${SYNC_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in ja*|JA*) LJ=1 ;; *) LJ=0 ;; esac
TO=; TO_LONG=
if command -v timeout >/dev/null 2>&1; then TO="timeout 20"; TO_LONG="timeout 180"; fi

t() { # 鍵 値… → 今の言葉の文（%s の数より値が多いと printf は書式を繰り返すので，数をそろえて渡す）
  local k="$1" f r c=0; shift; tx "$k"
  if [ "$LJ" = 1 ]; then f=$J; else f=$E; fi
  r=$f; while :; do case $r in *%s*) r=${r#*%s}; c=$((c + 1)) ;; *) break ;; esac; done
  case $c in
    0) printf "$f" ;; 1) printf "$f" "${1-}" ;; 2) printf "$f" "${1-}" "${2-}" ;; 3) printf "$f" "${1-}" "${2-}" "${3-}" ;;
    4) printf "$f" "${1-}" "${2-}" "${3-}" "${4-}" ;; 5) printf "$f" "${1-}" "${2-}" "${3-}" "${4-}" "${5-}" ;;
    *) printf "$f" "${1-}" "${2-}" "${3-}" "${4-}" "${5-}" "${6-}" ;;
  esac
}
say() { printf '%s\n' "$*"; }
add() { printf '  [%s] %s\n' "$(t "tag_$1")" "$2" >> "$RES"; }        # 最後に出す結果の 1 行
addraw() { printf '%s\n' "$1" >> "$RES"; }
now() { date +%s.%N 2>/dev/null || date +%s; }
elapsed() { LC_ALL=C $AWK -v a="$1" -v b="$(now)" 'BEGIN { printf "%.1f", b - a }'; }
fsize() { stat -c %s "$1" 2>/dev/null || wc -c < "$1" | tr -d ' '; }
sha256() { sha256sum "$1" 2>/dev/null | cut -d ' ' -f 1; }
mb() { LC_ALL=C $AWK -v b="${1:-0}" 'BEGIN { printf "%.0f", b / 1048576 }'; }
jstr() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }          # JSON の文字列の中身
abspath() { case $1 in /*) printf '%s' "${1%/}" ;; *) printf '%s/%s' "$(pwd)" "${1%/}" ;; esac; }
is_url() { case $1 in http://*|https://*) return 0 ;; esac; return 1; }
die() { add failed "$1"; [ "$EXIT" = 0 ] && EXIT=${2:-6}; finish; }

# JSON → 1 行 1 葉「道のり<TAB>型<TAB>値」（道のりの区切りは \034，型 s n b z(null) o(空の物) a(空の並び)）．
# 文字列の \uXXXX は UTF-8 に，制御文字は空白に（値はいつも 1 行）．壊れた JSON は終了コード 3．
AWK_JFLAT='
function ws(   c) { while (i <= n) { c = substr(s, i, 1); if (c == " " || c == "\t" || c == "\n" || c == "\r") i++; else return } }
function hexv(h,   k, v, c) { v = 0; h = tolower(h); for (k = 1; k <= length(h); k++) { c = index("0123456789abcdef", substr(h, k, 1)); if (c == 0) return -1; v = v * 16 + c - 1 } return v }
function u8(cp) {
  if (cp < 128) return sprintf("%c", cp)
  if (cp < 2048) return sprintf("%c%c", 192 + int(cp / 64), 128 + cp % 64)
  if (cp < 65536) return sprintf("%c%c%c", 224 + int(cp / 4096), 128 + int(cp / 64) % 64, 128 + cp % 64)
  return sprintf("%c%c%c%c", 240 + int(cp / 262144), 128 + int(cp / 4096) % 64, 128 + int(cp / 64) % 64, 128 + cp % 64)
}
function pstr(   o, c, j, cp, lo) {
  i++; o = ""
  while (i <= n) {
    c = substr(s, i, 1)
    if (c == "\"") { i++; return o }
    if (c == "\\") {
      c = substr(s, i + 1, 1)
      if (c == "u") {
        cp = hexv(substr(s, i + 2, 4)); i += 6
        if (cp >= 55296 && cp < 56320 && substr(s, i, 2) == "\\u") { lo = hexv(substr(s, i + 2, 4)); if (lo >= 56320 && lo < 57344) { cp = 65536 + (cp - 55296) * 1024 + (lo - 56320); i += 6 } }
        if (cp < 32) cp = 32
        o = o u8(cp); continue
      }
      if (c == "n" || c == "r" || c == "t" || c == "b" || c == "f") c = " "
      o = o c; i += 2; continue
    }
    j = i
    while (j <= n) { c = substr(s, j, 1); if (c == "\"" || c == "\\") break; j++ }
    o = o substr(s, i, j - i); i = j
  }
  err = 1; return o
}
function emit(p, ty, v) { printf "%s\t%s\t%s\n", p, ty, v }
function sub_(p, k) { if (p == "") return k; return p SEP k }
function pval(p,   c, key, idx, st) {
  ws(); if (i > n) { err = 1; return }
  c = substr(s, i, 1)
  if (c == "{") {
    i++; ws()
    if (i <= n && substr(s, i, 1) == "}") { i++; emit(p, "o", ""); return }
    while (i <= n) {
      ws(); if (substr(s, i, 1) != "\"") { err = 1; return }
      key = pstr(); ws()
      if (substr(s, i, 1) != ":") { err = 1; return }
      i++; pval(sub_(p, key)); if (err) return
      ws(); c = substr(s, i, 1); i++
      if (c == "}") return
      if (c != ",") { err = 1; return }
    }
    err = 1; return
  }
  if (c == "[") {
    i++; ws()
    if (i <= n && substr(s, i, 1) == "]") { i++; emit(p, "a", ""); return }
    idx = 0
    while (i <= n) {
      pval(sub_(p, idx)); if (err) return
      idx++; ws(); c = substr(s, i, 1); i++
      if (c == "]") return
      if (c != ",") { err = 1; return }
    }
    err = 1; return
  }
  if (c == "\"") { emit(p, "s", pstr()); return }
  if (substr(s, i, 4) == "true") { i += 4; emit(p, "b", "true"); return }
  if (substr(s, i, 5) == "false") { i += 5; emit(p, "b", "false"); return }
  if (substr(s, i, 4) == "null") { i += 4; emit(p, "z", ""); return }
  st = i
  while (i <= n && index("+-0123456789.eE", substr(s, i, 1)) > 0) i++
  if (i == st) { err = 1; return }
  emit(p, "n", substr(s, st, i - st))
}
BEGIN { SEP = "\034" }
{ s = s $0 "\n" }
END { n = length(s); i = 1; if (substr(s, 1, 3) == "\357\273\277") i = 4; ws(); if (i > n) exit 3; pval(""); if (err) exit 3 }
'
jflat() { LC_ALL=C $AWK "$AWK_JFLAT" "$1"; }
# 平らにした JSON から 1 つ取る（道のりは . 区切り．鍵に . を含まない物だけ）
jget() { LC_ALL=C $AWK -F '\t' -v p="$2" 'BEGIN { gsub(/\./, "\034", p) } $1 == p { print $3; exit }' "$1"; }
# 頭の段の鍵があるか
jhas() { LC_ALL=C $AWK -F '\t' -v k="$2" '{ split($1, q, "\034"); if (q[1] == k) { f = 1; exit } } END { exit !f }' "$1"; }

# JSON のファイルの頭の段の鍵 K の値を V（JSON の値の文字列）にする．ほかの鍵・並び・書き方は触らない．無ければ足す．
AWK_SETTOP='
function skipstr() { i++; while (i <= n) { c = substr(s, i, 1); if (c == "\\") { i += 2; continue } i++; if (c == "\"") return } }
function skipval(   d) {
  c = substr(s, i, 1)
  if (c == "\"") { skipstr(); return }
  if (c == "{" || c == "[") { d = 0; while (i <= n) { c = substr(s, i, 1); if (c == "\"") { skipstr(); continue } if (c == "{" || c == "[") d++; else if (c == "}" || c == "]") { d--; if (d == 0) { i++; return } } i++ } return }
  while (i <= n && index(",}] \t\r\n", substr(s, i, 1)) == 0) i++
}
function isws(x) { return x == " " || x == "\t" || x == "\r" || x == "\n" }
{ s = s $0 "\n" }
END {
  key = ENVIRON["SK"]; val = ENVIRON["SV"]
  n = length(s); i = 1; depth = 0; found = 0; first = 0
  while (i <= n) {
    c = substr(s, i, 1)
    if (c == "\"") {
      st = i; skipstr()
      if (depth == 1) {
        tok = substr(s, st + 1, i - st - 2); j = i
        while (j <= n && isws(substr(s, j, 1))) j++
        if (j <= n && substr(s, j, 1) == ":" && tok == key) { j++; while (j <= n && isws(substr(s, j, 1))) j++; vs = j; i = j; skipval(); ve = i; found = 1; break }
      }
      continue
    }
    if (c == "{" || c == "[") { depth++; if (depth == 1 && c == "{" && !first) first = i }
    else if (c == "}" || c == "]") depth--
    i++
  }
  if (found) { printf "%s%s%s", substr(s, 1, vs - 1), val, substr(s, ve); exit }
  if (first) {
    j = first + 1; while (j <= n && isws(substr(s, j, 1))) j++
    if (j <= n && substr(s, j, 1) == "}") printf "%s\n \"%s\": %s\n%s", substr(s, 1, first), key, val, substr(s, j)
    else printf "%s\n \"%s\": %s,%s", substr(s, 1, first), key, val, substr(s, first + 1)
    exit
  }
  printf "{\n \"%s\": %s\n}\n", key, val
}
'
json_set_top() { # ファイル 鍵 値（文字列）
  local f="$1"
  mkdir -p "$(dirname "$f")" || return 1
  [ -f "$f" ] || : > "$f"
  SK=$2 SV="\"$(jstr "$3")\"" LC_ALL=C $AWK "$AWK_SETTOP" "$f" > "$f.tmp" && mv -f "$f.tmp" "$f"
}

# ============================================================================ 引数と置き場
CMD=setup
case ${1:-} in
  setup|update|rollback|uninstall|status) CMD=$1; shift ;;
esac
SRC='' O_APP='' O_HOME='' O_MODELS='' O_SCDIR='' O_REPORT='' NO_SC=0 NO_MS=0 FULL=0 FORCE=0 YES=0 RMDATA=0 APPLY_NICE=0 PAUSE=0
while [ $# -gt 0 ]; do
  a=$1; v=
  case $a in --*=*) v=${a#*=}; a=${a%%=*} ;; esac
  case $a in
    --source|--app-dir|--sync-home|--models-dir|--shortcut-dir|--report|--lang)
      if [ -z "$v" ]; then
        if [ $# -lt 2 ]; then t err_args "$a"; echo; exit 2; fi
        v=$2; shift
      fi
      case $a in
        --source) SRC=$v ;; --app-dir) O_APP=$v ;; --sync-home) O_HOME=$v ;; --models-dir) O_MODELS=$v ;;
        --shortcut-dir) O_SCDIR=$v ;; --report) O_REPORT=$v ;; --lang) case $v in ja*) LJ=1 ;; *) LJ=0 ;; esac ;;
      esac ;;
    --no-shortcuts) NO_SC=1 ;; --no-model-search) NO_MS=1 ;; --full) FULL=1 ;; --force) FORCE=1 ;;
    --yes|-y) YES=1 ;; --remove-data) RMDATA=1 ;; --apply-nice) APPLY_NICE=1 ;; --pause) PAUSE=1 ;;
    -h|--help|help) t usage; exit 0 ;;
    *) t err_args "$a"; echo; exit 2 ;;
  esac
  shift
done

LSEP=", "; [ "$LJ" = 1 ] && LSEP="、"        # 並びの区切り（画面の日本語は「、」）
[ -n "${HOME:-}" ] || { t err_home; echo; exit 2; }
SELF_DIR=$(cd "$(dirname "$0")" && pwd)
SELF="$SELF_DIR/$(basename "$0")"
XDG_DATA=${XDG_DATA_HOME:-$HOME/.local/share}
XDG_CONF=${XDG_CONFIG_HOME:-$HOME/.config}
APP=$(abspath "${O_APP:-${SYNC_APP_DIR:-$XDG_DATA/SyncStrata}}")
BIN=$APP/app                     # 部品ごとに app/<id>/
PREV=$BIN/.prev                  # 入れ替える前の版（部品ごとに 1 つ）
STAGE=$BIN/.stage                # 展開と確かめの作業場（確かめてから名前を変えて入れる）
STATE_DIR=$APP/state
STATE_PATH=$STATE_DIR/state.json
DEFAULT_MODELS=$XDG_DATA/SyncStrata/models     # 起動の道具の既定（oscompat.default_models_dir と同じ）
CHECK_MODE=scan; [ "$FULL" = 1 ] && CHECK_MODE=full

TMPD=$(mktemp -d "${TMPDIR:-/tmp}/syncstrata-setup.XXXXXX") || exit 6
RES=$TMPD/results.txt; COMPREC=$TMPD/comps.txt; ST=$TMPD/state.tsv; ENVF=$TMPD/env.tsv; LUACC=$TMPD/lu.txt
: > "$RES"; : > "$COMPREC"; : > "$ST"; : > "$ENVF"; : > "$LUACC"
EXIT=0; REFUSED=0; ENGINE=; LOCKED=0; T_START=$(now); ENV_DONE=0
trap 'rm -rf "$TMPD"; [ "$LOCKED" = 1 ] && rm -rf "$STATE_DIR/setup.lock"' EXIT
trap 'exit 130' INT TERM

# ============================================================================ 記録（state.json．installer.py と同じ形）
AWK_STATE_IN='
BEGIN { US = "\037" }
{ n = split($1, k, "\034"); ty = $2; v = $3 }
k[1] == "product" { prod = v }
n == 1 && (k[1] == "release" || k[1] == "feed" || k[1] == "sync_home") { out = out k[1] US v "\n" }
n == 3 && k[1] == "components" { if (!(k[2] in cid)) { cid[k[2]] = 1; cord[++nc] = k[2] } c[k[2], k[3]] = v }
n == 3 && k[1] == "prev" { if (!(k[2] in pid)) { pid[k[2]] = 1; pord[++np] = k[2] } p[k[2], k[3]] = v }
n == 2 && k[1] == "skip" { out = out "skip" US k[2] US v "\n" }
n == 2 && k[1] == "shortcuts" && ty == "s" { out = out "short" US v "\n" }
k[1] == "last_update" {
  if (n == 2 && (k[2] == "at" || k[2] == "command")) lu[k[2]] = v
  else if (n == 3 && k[2] == "ids") luids[++nl] = v
  else if (n == 3 && (k[2] == "from" || k[2] == "to")) lu[k[2], k[3]] = v
}
END {
  if (prod != "sync-strata") exit
  printf "%s", out
  for (j = 1; j <= nc; j++) { id = cord[j]; print "comp" US id US c[id, "version"] US c[id, "files_sha256"] US c[id, "sha256"] US c[id, "at"] }
  for (j = 1; j <= np; j++) { id = pord[j]; print "prev" US id US p[id, "version"] US p[id, "files_sha256"] }
  if (nl > 0) { print "lu" US lu["at"] US lu["command"]; for (j = 1; j <= nl; j++) print "luid" US luids[j] US lu["from", luids[j]] US lu["to", luids[j]] }
}
'
AWK_ESC='
function esc(x,   m, q, k, o) {
  m = split(x, q, "\\"); o = q[1]; for (k = 2; k <= m; k++) o = o "\\\\" q[k]; x = o
  m = split(x, q, "\""); o = q[1]; for (k = 2; k <= m; k++) o = o "\\\"" q[k]; x = o
  m = split(x, q, "\t"); o = q[1]; for (k = 2; k <= m; k++) o = o "\\t" q[k]
  return o
}
function qq(x) { return "\"" esc(x) "\"" }
function join(a, m, sep,   o, k) { o = ""; for (k = 1; k <= m; k++) o = o (k > 1 ? sep : "") a[k]; return o }
'
AWK_STATE_OUT="$AWK_ESC"'
BEGIN { FS = "\037" }
$1 == "release" { rel = $2 }
$1 == "feed" { feed = $2 }
$1 == "sync_home" { sh = $2; hassh = 1 }
$1 == "comp" { nc++; c[nc] = qq($2) ": {\"version\": " qq($3) ", \"files_sha256\": " qq($4) ", \"sha256\": " qq($5) ", \"at\": " qq($6) "}" }
$1 == "prev" { np++; p[np] = qq($2) ": {\"version\": " qq($3) ", \"files_sha256\": " qq($4) "}" }
$1 == "skip" { ns++; sk[ns] = qq($2) ": " qq($3) }
$1 == "short" { nh++; h[nh] = qq($2) }
$1 == "lu" { luat = $2; lucmd = $3; haslu = 1 }
$1 == "luid" { nl++; li[nl] = qq($2); lf[nl] = qq($2) ": " qq($3); lt[nl] = qq($2) ": " qq($4) }
END {
  print "{"
  print " \"product\": \"sync-strata\","
  print " \"schema\": 1,"
  print " \"release\": " qq(rel) ","
  print " \"components\": {" (nc ? "\n  " join(c, nc, ",\n  ") "\n " : "") "},"
  print " \"prev\": {" (np ? "\n  " join(p, np, ",\n  ") "\n " : "") "},"
  if (haslu && nl) print " \"last_update\": {\"at\": " qq(luat) ", \"ids\": [" join(li, nl, ", ") "], \"from\": {" join(lf, nl, ", ") "}, \"to\": {" join(lt, nl, ", ") "}, \"command\": " qq(lucmd) "},"
  else print " \"last_update\": null,"
  print " \"skip\": {" join(sk, ns, ", ") "},"
  print " \"shortcuts\": [" join(h, nh, ", ") "],"
  if (hassh) print " \"sync_home\": " qq(sh) ","
  print " \"feed\": " qq(feed)
  print "}"
}
'
st_load() {
  : > "$ST"
  if [ -f "$STATE_PATH" ] && jflat "$STATE_PATH" > "$TMPD/state.flat" 2>/dev/null; then
    LC_ALL=C $AWK -F '\t' "$AWK_STATE_IN" "$TMPD/state.flat" > "$ST"
  fi
}
st_save() { mkdir -p "$STATE_DIR" && LC_ALL=C $AWK "$AWK_STATE_OUT" "$ST" > "$STATE_PATH.tmp" && mv -f "$STATE_PATH.tmp" "$STATE_PATH"; }
st_get() { LC_ALL=C $AWK -F "$US" -v ty="$1" -v id="$2" '$1 == ty && $2 == id { print $3; exit }' "$ST"; }
st_get1() { LC_ALL=C $AWK -F "$US" -v ty="$1" '$1 == ty { print $2; exit }' "$ST"; }
st_del() { # 型 [id]（id を省くとその型を全部）
  LC_ALL=C $AWK -F "$US" -v ty="$1" -v id="${2-}" -v all="${2+x}" '!($1 == ty && (all == "" || $2 == id))' "$ST" > "$ST.tmp" && mv -f "$ST.tmp" "$ST"
}
st_put() { st_del "$1" "$2"; printf '%s\n' "$1$US$2${3:+$US$3}" >> "$ST"; }       # 型 id 残り（US 区切り）
st_set1() { st_del "$1"; printf '%s\n' "$1$US$2" >> "$ST"; }

# ============================================================================ 版の一覧（manifest.json）
AWK_COMPS='
BEGIN { US = "\037" }
{ n = split($1, k, "\034") }
n == 3 && k[1] == "components" { v[k[2], k[3]] = $3; if (k[2] + 1 > cnt) cnt = k[2] + 1 }
END { for (j = 0; j < cnt; j++) print j US v[j, "id"] US v[j, "version"] US v[j, "files_sha256"] US v[j, "archive"] US v[j, "size"] US v[j, "sha256"] US v[j, "files"] US v[j, "installed_bytes"] US v[j, "variant"] US v[j, "name"] }
'
open_feed() { # 置き場（フォルダー・manifest.json・URL）→ FEED_URL FEED_BASE FEED_FLAT COMPS REL UPDATE_FEED
  local src="$1" mp
  FEED_FLAT=$TMPD/manifest.flat; COMPS=$TMPD/comps.tsv
  if is_url "$src"; then
    FEED_URL=1
    case $src in *.json) mp=$src ;; *) mp=${src%/}/manifest.json ;; esac
    FEED_BASE=${mp%/*}/
    fetch "$mp" "$TMPD/manifest.json" || die "$(t err_download "$mp")"
    mp=$TMPD/manifest.json
  else
    FEED_URL=0
    case $src in *.json) mp=$src ;; *) mp=${src%/}/manifest.json ;; esac
    [ -f "$mp" ] || die "$(t err_no_manifest "$mp")"
    FEED_BASE=$(cd "$(dirname "$mp")" && pwd)
    mp=$FEED_BASE/$(basename "$mp")
  fi
  jflat "$mp" > "$FEED_FLAT" 2>/dev/null || { REFUSED=1; die "$(t err_bad_manifest "$src")" 5; }
  if [ "$(jget "$FEED_FLAT" product)" != sync-strata ] || [ "$(jget "$FEED_FLAT" schema)" != 1 ]; then REFUSED=1; die "$(t err_bad_manifest "$src")" 5; fi
  case $(jget "$FEED_FLAT" platform) in ''|linux-x64) ;; *) die "$(t err_platform "$(jget "$FEED_FLAT" platform)")" 5 ;; esac
  # 部品 python を先に（PC に python3 が無いとき，残りの展開に同梱の Python を使えるように）
  LC_ALL=C $AWK -F '\t' "$AWK_COMPS" "$FEED_FLAT" | LC_ALL=C $AWK -F "$US" '$2 == "python" { print; next } { r = r $0 "\n" } END { printf "%s", r }' > "$COMPS"
  REL=$(jget "$FEED_FLAT" release)
  UPDATE_FEED=$(jget "$FEED_FLAT" update_feed)
  # 置き場の 2 つの形（GitHub のリリースは版ごとに平ら）: この版の zip は版の名前の入った置き場（FEED_THIS），
  # update が見るのは版の名前の入っていない最新の置き場（FEED_LATEST＝…/releases/latest/download．state の feed に書く）．
  # 一覧の update_feed がどちらの形でも，もう片方を作る．release_feed（任意）があれば FEED_THIS はそれ
  FEED_THIS=$(jget "$FEED_FLAT" release_feed)
  FEED_LATEST=$(latest_of "$UPDATE_FEED")
  if [ -z "$FEED_THIS" ]; then
    case ${UPDATE_FEED%/} in
      */releases/latest/download) FEED_THIS="${UPDATE_FEED%/releases/latest/download*}/releases/download/v$REL" ;;
      *) FEED_THIS=$UPDATE_FEED ;;
    esac
  fi
}
latest_of() { # 版の名前の入った GitHub のリリースの置き場 → 最新の置き場（ほかはそのまま）
  case $1 in
    */releases/download/*) printf '%s' "${1%/releases/download/*}/releases/latest/download" ;;
    *) printf '%s' "$1" ;;
  esac
}

# ============================================================================ 展開と取り寄せの道具
# 展開の道具: python3 の zipfile（日本語などの名前を正しく扱う）→ unzip → bsdtar．
# Debian・Ubuntu の unzip は Windows で作った zip の UTF-8 の名前を CP437 として読んで化かすので，-O UTF-8 が使えれば付ける．
# PC に python3 が無いときは，同梱の Python（部品 python．先に入れる）が入った後はそれを使う（py_ok で確かめる）．
py_ok() { [ -x "$1" ] && [ "$("$1" -I -c 'import sys, zipfile; print("ok" if sys.version_info >= (3, 4) else "old")' 2>/dev/null)" = ok ]; }
pick_unzip() {
  local p
  UNZIP_O=''
  if command -v unzip >/dev/null 2>&1 && unzip -h 2>&1 | grep -q 'O CHARSET'; then UNZIP_O='-O UTF-8'; fi
  case ${SYNC_SETUP_UNZIP:-} in
    unzip) UNZIP=unzip; return 0 ;; bsdtar) UNZIP=bsdtar; return 0 ;;
  esac
  for p in python3 /usr/libexec/platform-python python; do
    [ -n "${SYNC_SETUP_NO_SYSPY:-}" ] && break              # 試し: PC に python3 が無い場合
    p=$(command -v "$p" 2>/dev/null) || continue
    if py_ok "$p"; then UNZIP=py; PYX=$p; return 0; fi
  done
  if py_ok "$BIN/python/bin/python3"; then UNZIP=py; PYX=$BIN/python/bin/python3; return 0; fi    # 前に入れた同梱の Python
  [ "${SYNC_SETUP_UNZIP:-}" = py ] && return 1
  if command -v unzip >/dev/null 2>&1; then UNZIP=unzip; return 0; fi
  if command -v bsdtar >/dev/null 2>&1; then UNZIP=bsdtar; return 0; fi
  return 1
}
use_bundled_python() { # 部品 python を入れた後: PC の python3 が無くて unzip などで展開していたなら，同梱の Python に替える
  [ "$UNZIP" = py ] && return 0
  [ -n "${SYNC_SETUP_UNZIP:-}" ] && return 0
  if py_ok "$BIN/python/bin/python3"; then UNZIP=py; PYX=$BIN/python/bin/python3; fi
  [ -n "${PYX:-}" ] || return 0
  [ "$DL" = none ] && DL=python
  return 0
}
zip_names() {
  case $UNZIP in
    unzip) unzip -Z1 "$1" ;;
    py) "$PYX" -I -c 'import sys, zipfile
for n in zipfile.ZipFile(sys.argv[1]).namelist(): print(n)' "$1" ;;
    bsdtar) bsdtar -tf "$1" ;;
  esac
}
# shellcheck disable=SC2086
unpack() { # zip 先（$UNZIP_O は引用しない: 空か「-O UTF-8」）
  local rc
  case $UNZIP in
    unzip) unzip $UNZIP_O -qq -o "$1" -d "$2" < /dev/null; rc=$?; [ "$rc" -le 1 ] ;;
    py) "$PYX" -I -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$1" "$2" < /dev/null ;;
    bsdtar) bsdtar -xf "$1" -C "$2" < /dev/null ;;
  esac
}
pick_downloader() {
  DL=${SYNC_SETUP_DOWNLOADER:-}
  [ -n "$DL" ] && return 0
  if command -v curl >/dev/null 2>&1; then DL=curl
  elif command -v wget >/dev/null 2>&1; then DL=wget
  elif [ -n "${PYX:-}" ] || PYX=$(command -v python3 2>/dev/null); then DL=python
  else DL=none; fi
}
fetch() { # URL 先（途中の物は .part．済んだら名前を変える）
  local tmp="$2.part" prog=-sS
  mkdir -p "$(dirname "$2")" || return 1
  rm -f "$tmp"
  [ -t 2 ] && prog=-#
  case $DL in
    curl) curl -fL --retry 2 --connect-timeout 30 $prog -o "$tmp" "$1" < /dev/null ;;
    wget) wget -q -O "$tmp" "$1" < /dev/null ;;
    python) "$PYX" -I -c 'import shutil, sys, urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=120) as r, open(sys.argv[2], "wb") as f: shutil.copyfileobj(r, f, 1 << 23)' "$1" "$tmp" < /dev/null ;;
    *) return 2 ;;
  esac || { rm -f "$tmp"; return 1; }
  mv -f "$tmp" "$2"
}

# ============================================================================ 部品を調べる
# 部品のフォルダー（app/<id>）の _pkg/files.tsv と照らす．入れた直後の大きさと時刻を state/<id>.scan.tsv に控え，
# 次からは大きさか時刻が変わったファイルだけ sha256 を計る（--full で全部．sizes は展開した直後: zip は sha256 と CRC で確かめ済み）．
AWK_TC='
BEGIN { FS = "\t" }
function ns(t,   q, f) { split(t, q, "."); f = substr(q[2] "000000000", 1, 9); return q[1] f }
FILENAME == ARGV[1] { as[$1] = $2; am[$1] = ns($3); next }
FILENAME == ARGV[2] { sc[$1] = $2 "\t" $3; next }
{
  rel = $1; gsub(/\\/, "/", rel); files++
  if (!(rel in as) || as[rel] != $2) { print rel > badf; bad++; next }
  bytes += $2
  if (mode == "sizes") next
  if (mode == "scan" && (rel in sc) && sc[rel] == $2 "\t" am[rel]) next
  hashed++; print $3 "  " rel > listf
}
END { printf "%d %d %d %.0f\n", files, bad, hashed, bytes }
'
test_component() { # フォルダー 控え 方式（full|scan|sizes）→ TC_STATE TC_VERSION TC_FSHA TC_FILES TC_BAD TC_HASHED
  local d="$1" scan="$2" mode="$3" h r
  TC_STATE=missing TC_VERSION='' TC_FSHA='' TC_FILES=0 TC_BAD=0 TC_HASHED=0
  : > "$TMPD/bad.txt"; : > "$TMPD/hash.lst"
  [ -d "$d" ] || return 0
  if [ ! -f "$d/_pkg/component.json" ] || [ ! -f "$d/_pkg/files.tsv" ]; then TC_STATE=broken; TC_BAD=1; return 0; fi
  if ! jflat "$d/_pkg/component.json" > "$TMPD/cj.flat" 2>/dev/null; then TC_STATE=broken; TC_BAD=1; return 0; fi
  TC_VERSION=$(jget "$TMPD/cj.flat" version); TC_FSHA=$(jget "$TMPD/cj.flat" files_sha256)
  h=$(sha256 "$d/_pkg/files.tsv")
  if [ "$h" != "$TC_FSHA" ]; then TC_STATE=broken; TC_BAD=1; return 0; fi
  find "$d" -type f -printf '%P\t%s\t%T@\n' > "$TMPD/actual.tsv" 2>/dev/null
  [ "$mode" = scan ] && [ -f "$scan" ] || scan=/dev/null
  r=$(LC_ALL=C $AWK -v mode="$mode" -v listf="$TMPD/hash.lst" -v badf="$TMPD/bad.txt" "$AWK_TC" "$TMPD/actual.tsv" "$scan" "$d/_pkg/files.tsv")
  # shellcheck disable=SC2086
  set -- $r
  TC_FILES=${1:-0} TC_BAD=${2:-0} TC_HASHED=${3:-0}
  if [ "$TC_HASHED" -gt 0 ]; then
    (cd "$d" && LC_ALL=C sha256sum -c --quiet "$TMPD/hash.lst" 2>/dev/null) | sed -n 's/: FAILED.*$//p' >> "$TMPD/bad.txt"
    TC_BAD=$(wc -l < "$TMPD/bad.txt" | tr -d ' ')
  fi
  if [ "$TC_BAD" -gt 0 ]; then TC_STATE=broken; else TC_STATE=ok; fi
}
write_scan() { # フォルダー 控え（files.tsv にある物の「道のり 大きさ 時刻(ns)」）
  mkdir -p "$(dirname "$2")"
  find "$1" -type f -printf '%P\t%s\t%T@\n' > "$TMPD/ws.tsv" 2>/dev/null
  LC_ALL=C $AWK -F '\t' '
    function ns(t,   q, f) { split(t, q, "."); f = substr(q[2] "000000000", 1, 9); return q[1] f }
    FILENAME == ARGV[1] { a[$1] = $2 "\t" ns($3); next }
    { rel = $1; gsub(/\\/, "/", rel); if (rel in a) print rel "\t" a[rel] }' "$TMPD/ws.tsv" "$1/_pkg/files.tsv" > "$2"
}
cmp_version() { # "0.2.0-rc.2" のような版を数の並びで比べる（1・0・-1．installer.ps1 と同じ決まり）
  LC_ALL=C $AWK -v a="$1" -v b="$2" 'function isn(x) { return x ~ /^[0-9]+$/ }
    BEGIN { na = split(a, pa, /[.+-]/); nb = split(b, pb, /[.+-]/); m = na > nb ? na : nb
      for (k = 1; k <= m; k++) { x = (k <= na) ? pa[k] : ""; y = (k <= nb) ? pb[k] : ""
        if (x == y) continue
        if (isn(x) && isn(y)) { print (x + 0 > y + 0) ? 1 : -1; exit }
        if (x == "") { print 1; exit }
        if (y == "") { print -1; exit }
        print (x "" > y "") ? 1 : -1; exit }
      print 0 }'
}
plan_for() { # id 版 files_sha256（TC_* を見て PL_ACT PL_WHY）
  local c sk
  case $TC_STATE in
    missing) PL_ACT=install; PL_WHY=$(t why_new); return ;;
    broken)
      if [ "$TC_VERSION" = "$2" ]; then PL_ACT=repair; PL_WHY=$(t why_repair "$TC_BAD")
      else PL_ACT=install; PL_WHY=$(t why_broken_upgrade "${TC_VERSION:-?}" "$2"); fi
      return ;;
  esac
  c=$(cmp_version "$TC_VERSION" "$2")
  if [ "$c" -gt 0 ]; then PL_ACT=skip; PL_WHY=$(t why_newer_installed "$TC_VERSION"); return; fi
  if [ "$c" -lt 0 ]; then
    sk=$(st_get skip "$1")
    if [ "$sk" = "$2" ] && [ "$FORCE" != 1 ]; then PL_ACT=skip; PL_WHY=$(t why_rolled_back "$2"); return; fi
    PL_ACT=install; PL_WHY=$(t why_upgrade "$TC_VERSION" "$2"); return
  fi
  if [ "$TC_FSHA" != "$3" ]; then PL_ACT=install; PL_WHY=$(t why_rebuild "$2"); return; fi
  PL_ACT=skip; PL_WHY=$(t why_same)
}

# ============================================================================ 部品を入れる
# 部品の zip を手元に用意して大きさと sha256 を確かめる（C_ID C_ARCH C_SIZE C_SHA を使う）→ ZIP ZIP_TMP．だめなら FAIL を書いて 1
get_archive() {
  local name="${C_ARCH##*/}" dl="$STATE_DIR/download" p dd uf u ok
  ZIP='' ZIP_TMP=0
  if [ "$FEED_URL" = 1 ]; then
    p=$dl/$name
    u=$FEED_BASE$name; is_url "$C_ARCH" && u=$C_ARCH        # 一覧が URL で指していればそれ．ほかは一覧の隣（リリースは平ら）
    if ! { [ -f "$p" ] && [ "$(fsize "$p")" = "$C_SIZE" ] && [ "$(sha256 "$p")" = "$C_SHA" ]; }; then
      [ "$DL" = none ] && { FAIL=$(t err_no_downloader "$name"); return 1; }
      fetch "$u" "$p" || { FAIL=$(t err_download "$u"); return 1; }
    fi
    ZIP_TMP=1
  else
    case "/$C_ARCH/" in */../*) FAIL=$(t err_zip_outside "$C_ARCH"); REFUSED=1; return 1 ;; esac
    p=$FEED_BASE/$C_ARCH
    if [ ! -f "$p" ]; then
      # 手で落とした zip を setup の隣（展開したフォルダーか，その 1 つ上）に置けば，それを使う
      for dd in "$DIST_ROOT" "$(dirname "$DIST_ROOT")"; do
        if [ -n "$DIST_ROOT" ] && [ -f "$dd/$name" ]; then p=$dd/$name; break; fi
      done
    fi
    if [ ! -f "$p" ]; then
      { is_url "$FEED_THIS" || is_url "$FEED_LATEST"; } || { FAIL=$(t err_zip_missing "$p"); return 1; }
      p=$dl/$name
      say "$(t say_fetch "$C_ID" "$(mb "$C_SIZE")")"
      if [ -f "$p" ] && [ "$(fsize "$p")" = "$C_SIZE" ] && [ "$(sha256 "$p")" != "$C_SHA" ]; then rm -f "$p"; fi
      if ! { [ -f "$p" ] && [ "$(fsize "$p")" = "$C_SIZE" ]; }; then
        [ "$DL" = none ] && { FAIL=$(t err_no_downloader "$name"); return 1; }
        ok=0
        for uf in "$FEED_THIS" "$FEED_LATEST"; do          # この版の置き場 → 最新の置き場（同じ版の zip が残っていれば）
          is_url "$uf" || continue
          if fetch "${uf%/}/$name" "$p"; then ok=1; break; fi
        done
        [ "$ok" = 1 ] || { FAIL=$(t err_download "${FEED_THIS%/}/$name"); return 1; }
      fi
      ZIP_TMP=1        # 入れたら消す（エンジンは 1 GB 近い）
    fi
  fi
  if [ "$(fsize "$p")" != "$C_SIZE" ]; then REFUSED=1; FAIL=$(t err_zip_size "$C_ID" "$(fsize "$p")" "$C_SIZE"); [ "$ZIP_TMP" = 1 ] && rm -f "$p"; return 1; fi
  if [ "$(sha256 "$p")" != "$C_SHA" ]; then REFUSED=1; FAIL=$(t err_zip_sha "$C_ID"); [ "$ZIP_TMP" = 1 ] && rm -f "$p"; return 1; fi
  ZIP=$p
}
# 確かめてから入れる: 作業場に展開 → 一覧の版・files_sha256 と全ファイルの大きさ → 実行の印 → 前の版を .prev へ（同じ版の修理なら捨てる）→ 名前を変えて入れる
install_component() { # id 版 files_sha256 zip 前を残す(0|1)
  local cid="$1" stage="$STAGE/$1" dest="$BIN/$1" bad l
  rm -rf "$stage"; mkdir -p "$stage" || { FAIL=$(t err_move "$stage"); return 1; }
  bad=$(zip_names "$4" | LC_ALL=C $AWK '/^\// || /(^|\/)\.\.(\/|$)/ { print; exit }')
  if [ -n "$bad" ]; then rm -rf "$stage"; REFUSED=1; FAIL=$(t err_badpath "$cid" "$bad"); return 1; fi
  unpack "$4" "$stage" || { rm -rf "$stage"; FAIL=$(t err_unzip "$cid"); return 1; }
  test_component "$stage" "" sizes
  if [ "$TC_STATE" != ok ] || [ "$TC_FSHA" != "$3" ] || [ "$TC_VERSION" != "$2" ]; then
    rm -rf "$stage"; REFUSED=1; FAIL=$(t err_content "$cid" "$TC_STATE" "$TC_BAD"); return 1
  fi
  if [ -f "$stage/_pkg/exec.txt" ]; then
    while IFS= read -r l || [ -n "$l" ]; do
      [ -n "$l" ] && [ -f "$stage/$l" ] && chmod +x "$stage/$l"
    done < "$stage/_pkg/exec.txt"
  fi
  if [ -e "$dest" ]; then
    if [ "$5" = 1 ]; then
      mkdir -p "$PREV"; rm -rf "${PREV:?}/$cid"
      mv "$dest" "$PREV/$cid" || { rm -rf "$stage"; FAIL=$(t err_move "$dest"); return 1; }
      [ -f "$STATE_DIR/$cid.scan.tsv" ] && mv -f "$STATE_DIR/$cid.scan.tsv" "$STATE_DIR/prev-$cid.scan.tsv"
    else
      rm -rf "$dest"
      [ -e "$dest" ] && { rm -rf "$stage"; FAIL=$(t err_move "$dest"); return 1; }
    fi
  fi
  mv "$stage" "$dest" || { FAIL=$(t err_move "$dest"); return 1; }
  write_scan "$dest" "$STATE_DIR/$cid.scan.tsv"
}

# 入れた先の app/ の下の実行ファイルで動いているプロセス（エンジン・dsh・中継・アプリの枠・同梱の Python）
app_processes() {
  local real p e
  [ -d "$BIN" ] || return 0
  real=$(cd "$BIN" && pwd -P)
  find /proc -mindepth 2 -maxdepth 2 -name exe -lname "$real/*" 2>/dev/null | while IFS= read -r p; do
    e=$(readlink "$p" 2>/dev/null) || continue
    p=${p#/proc/}; printf '%s %s\n' "${p%/exe}" "${e#"$real"/}"
  done
}
assert_not_running() {
  local ps pid exe
  ps=$(app_processes)
  [ -z "$ps" ] && return 0
  say ""
  say "!! $(t running_head)"
  printf '%s\n' "$ps" | while read -r pid exe; do say "$(t running_item "$pid" "$exe")"; done
  say "$(t running_hint "$BIN/launcher/sync.sh")"
  EXIT=7
  return 1
}

comp_rec() { printf '%s\n' "$1$US$2$US$3$US$4$US$5$US$6$US$7$US$8$US$9" >> "$COMPREC"; }   # id 何をした 前 後 調べ秒 計った数 ファイル数 大きさ 入れ秒

# ============================================================================ 部品をそろえる（setup と update が共有する）
# 1 回目は variant の無い部品（起動の道具・Python を含む）．2 回目は GPU に合う variant（engine-<種類>）だけ．
sync_components() { # base|variant
  local pass="$1" plan="$TMPD/plan.$1" todo=0 t0 chk chk2 keep tag at
  local idx cid ver fsha arch size sha nfiles ibytes variant cname act why hst hver hfsha hh
  : > "$plan"
  while IFS=$US read -r idx cid ver fsha arch size sha nfiles ibytes variant cname <&3; do
    [ -n "$cid" ] || continue
    if [ "$pass" = variant ]; then { [ -n "$variant" ] && [ "$variant" = "$ENGINE" ]; } || continue
    else [ -z "$variant" ] || continue; fi
    t0=$(now)
    test_component "$BIN/$cid" "$STATE_DIR/$cid.scan.tsv" "$CHECK_MODE"
    plan_for "$cid" "$ver" "$fsha"
    chk=$(elapsed "$t0")
    [ "$PL_ACT" = skip ] || todo=1
    printf '%s\n' "$idx$US$cid$US$ver$US$fsha$US$arch$US$size$US$sha$US$nfiles$US$ibytes$US$variant$US$cname$US$PL_ACT$US$PL_WHY$US$TC_STATE$US$TC_VERSION$US$TC_FSHA$US$TC_HASHED$US$chk" >> "$plan"
  done 3< "$COMPS"
  if [ "$todo" = 1 ] && ! assert_not_running; then
    while IFS=$US read -r idx cid ver fsha arch size sha nfiles ibytes variant cname act why hst hver hfsha hh chk <&3; do
      if [ "$act" = skip ]; then add skipped "$(t line_stopped "$cid" "$ver" "$why")"; else add stopped "$(t line_stopped "$cid" "$ver" "$why")"; fi
    done 3< "$plan"
    return
  fi
  while IFS=$US read -r idx cid ver fsha arch size sha nfiles ibytes variant cname act why hst hver hfsha hh chk <&3; do
    if [ "$act" = skip ]; then
      add skipped "$(t line_skip "$cid" "$ver" "$why" "$chk")"
      comp_rec "$cid" skip "$hver" "$ver" "$chk" "$hh" "$nfiles" "$ibytes" 0
      continue
    fi
    t0=$(now); FAIL=
    say "$(t hdr_comp "$cid" "$cname" "$why")"
    keep=0; [ "$act" = install ] && [ "$hst" != missing ] && keep=1      # 版が変わるときだけ前の版を残す
    C_ID=$cid C_ARCH=$arch C_SIZE=$size C_SHA=$sha
    if get_archive && install_component "$cid" "$ver" "$fsha" "$ZIP" "$keep"; then
      [ "$ZIP_TMP" = 1 ] && rm -f "$ZIP"
      if [ "$keep" = 1 ]; then
        st_put prev "$cid" "$hver$US$hfsha"
        printf '%s\n' "$cid$US$hver$US$ver" >> "$LUACC"
      fi
      at=$(date +%Y-%m-%dT%H:%M:%S)
      st_put comp "$cid" "$ver$US$fsha$US$sha$US$at"
      [ "$cid" = python ] && use_bundled_python
      tag=installed; [ "$act" = repair ] && tag=repaired
      chk2=$(elapsed "$t0")
      add "$tag" "$(t line_done "$cid" "$ver" "$why" "$nfiles" "$(mb "$ibytes")" "$chk2")"
      comp_rec "$cid" "$act" "$hver" "$ver" "$chk" "$hh" "$nfiles" "$ibytes" "$chk2"
    else
      add failed "$(t line_fail "$cid" "$ver" "$FAIL")"
      if [ "$EXIT" = 0 ]; then if [ "$REFUSED" = 1 ]; then EXIT=5; else EXIT=6; fi; fi
      comp_rec "$cid" failed "$hver" "$ver" "$chk" "$hh" "$nfiles" "$ibytes" "$(elapsed "$t0")"
    fi
  done 3< "$plan"
  [ -n "$REL" ] && st_set1 release "$REL"
  rm -rf "$STAGE"
}
# このコマンドで版を入れ替えた部品を last_update に（1 回目と 2 回目の両方．rollback が戻す物）
commit_last_update() {
  [ -s "$LUACC" ] || return 0
  st_del lu; st_del luid
  printf '%s\n' "lu$US$(date +%Y-%m-%dT%H:%M:%S)$US$CMD" >> "$ST"
  LC_ALL=C $AWK -F "$US" -v US="$US" '!s[$1]++ { print "luid" US $0 }' "$LUACC" >> "$ST"
}

# ============================================================================ 対応環境の調べ（GPU とエンジンの選び方・依存）
# 調べは起動の道具の sync_env.py と同じ鍵．SYNC_ENV_OVERRIDE（JSON）があれば，その鍵の値で置き換える（gpus・adapters・avx2・avx512・ram_gib・glibc・kfd・amdgpu）．
AWK_PICK='
BEGIN { FS = "\037"; US = "\037"
  nt = split(ENVIRON["NV_TABLE"], L, "\n"); for (j = 1; j <= nt; j++) { split(L[j], f, " "); lo[j] = f[1]; hi[j] = f[2]; en[j] = f[3]; kd[j] = f[4] }
  nr = split(ENVIRON["RADEON_IDS"], L, "\n"); for (j = 1; j <= nr; j++) { split(L[j], f, " "); rlo[j] = hex(f[1]); rhi[j] = hex(f[2]); ren[j] = f[3] }
  nn = split(ENVIRON["RADEON_NAMES"], L, "\n"); for (j = 1; j <= nn; j++) { split(L[j], f, " "); nen[j] = f[1]; nre[j] = substr(L[j], length(f[1]) + 2) }
  ni = split(ENVIRON["AMD_IGPU_IDS"], f, " "); for (j = 1; j <= ni; j++) igid[hex(f[j])] = 1
  igre = ENVIRON["IGPU_NAME_RE"]
}
function hex(h,   k, v, c) { h = tolower(h); sub(/^0x/, "", h); if (h == "") return -1; v = 0; for (k = 1; k <= length(h); k++) { c = index("0123456789abcdef", substr(h, k, 1)); if (!c) return -1; v = v * 16 + c - 1 } return v }
function intable(cc,   m) { for (m = 1; m <= nt; m++) if (cc + 0 >= lo[m] + 0 && cc + 0 < hi[m] + 0) return m; return 0 }
FILENAME == ARGV[1] { ng++; gn[ng] = $1; gc[ng] = $2; gd[ng] = $3; gv[ng] = $4; next }
{ na++; an[na] = $1; av[na] = $2; adev[na] = $3; adrv[na] = $4; aven[na] = $5 }
END {
  if (ng) {
    best = 0
    for (j = 1; j <= ng; j++) { it = intable(gc[j]) > 0
      if (!best || it > bit || (it == bit && (gc[j] + 0 > bc + 0 || (gc[j] + 0 == bc + 0 && gv[j] + 0 > bv + 0)))) { best = j; bit = it; bc = gc[j]; bv = gv[j] } }
    j = best; m = intable(gc[j])
    if (m) print en[m] US kd[m] US gn[j] US "nvidia" US gv[j] US gd[j] US "" US ""
    else print "" US "too_old" US gn[j] US "nvidia" US gv[j] US gd[j] US "" US ""
    exit
  }
  first = 0
  for (j = 1; j <= na; j++) {
    ln = tolower(an[j]); vend = tolower(aven[j])
    if (!(vend == "0x1002" || (vend == "" && ln ~ /radeon|(^|[^a-z])amd([^a-z]|$)/))) continue
    if (!first) first = j
    d = hex(adev[j])
    if (d >= 0) for (m = 1; m <= nr; m++) if (d >= rlo[m] && d <= rhi[m]) { print ren[m] US "experimental" US an[j] US "amd" US av[j] US "" US adev[j] US adrv[j]; exit }
    for (m = 1; m <= nn; m++) if (ln ~ nre[m]) { print nen[m] US "experimental" US an[j] US "amd" US av[j] US "" US adev[j] US adrv[j]; exit }
  }
  if (first) { j = first; d = hex(adev[j]); k = ((d >= 0 && (d in igid)) || tolower(an[j]) ~ igre) ? "igpu" : "too_old"
    print "" US k US an[j] US "amd" US av[j] US "" US adev[j] US adrv[j]; exit }
  for (j = 1; j <= na; j++) if (tolower(aven[j]) == "0x10de") { print "" US "nodriver" US an[j] US "nvidia" US av[j] US "" US adev[j] US adrv[j]; exit }
  print "" US "none" US "" US "" US "" US "" US "" US ""
}
'
ov_get() { [ -s "$OVF" ] && jget "$OVF" "$1"; }
ov_has() { [ -s "$OVF" ] && jhas "$OVF" "$1"; }
probe_nvidia() { # → 名前 US cc US ドライバー US VRAM(GiB)
  local smi=nvidia-smi c
  if ! command -v nvidia-smi >/dev/null 2>&1; then          # PATH に無くても決まった場所（WSL は /usr/lib/wsl/lib）
    smi=
    for c in /usr/bin/nvidia-smi /usr/lib/wsl/lib/nvidia-smi /usr/local/bin/nvidia-smi /opt/bin/nvidia-smi; do [ -x "$c" ] && { smi=$c; break; }; done
    [ -n "$smi" ] || return 0
  fi
  $TO "$smi" --query-gpu=name,compute_cap,driver_version,memory.total --format=csv,noheader,nounits 2>/dev/null < /dev/null |
    LC_ALL=C $AWK -F ', *' -v US="$US" 'NF >= 4 && $2 ~ /^[0-9]+\.[0-9]+$/ { v = ($4 ~ /^[0-9]/) ? sprintf("%.1f", $4 / 1024) : ""; print $1 US $2 US $3 US v }'
}
probe_adapters() { # /sys/class/drm の表示アダプター → 名前 US VRAM US device US ドライバー US vendor
  local c dev vendor device drv slot vram name
  for c in /sys/class/drm/card[0-9]*; do
    case ${c##*/} in *-*) continue ;; esac
    dev=$c/device
    [ -r "$dev/vendor" ] || continue
    vendor=$(cat "$dev/vendor" 2>/dev/null); device=$(cat "$dev/device" 2>/dev/null)
    drv=$(readlink "$dev/driver" 2>/dev/null); drv=${drv##*/}
    slot=$(readlink -f "$dev" 2>/dev/null); slot=${slot##*/}
    vram=
    [ -r "$dev/mem_info_vram_total" ] && vram=$(LC_ALL=C $AWK '{ printf "%.1f", $1 / 1073741824 }' "$dev/mem_info_vram_total" 2>/dev/null)
    name=
    command -v lspci >/dev/null 2>&1 && name=$(lspci -mm -s "$slot" 2>/dev/null | LC_ALL=C $AWK -F '"' 'NR == 1 { print $4 " " $6 }')
    [ -z "$name" ] && [ -r "$dev/product_name" ] && name=$(cat "$dev/product_name" 2>/dev/null)
    [ -z "$name" ] && case $vendor in 0x1002) name="AMD Radeon ($device)" ;; 0x10de) name="NVIDIA GPU ($device)" ;; *) name="GPU $vendor:$device" ;; esac
    printf '%s\n' "$name$US$vram$US$device$US$drv$US$vendor"
  done
}
env_add() { printf '%s\n' "$1$US$2$US${3:-}$US${4:-}$US${5:-}" >> "$ENVF"; }   # 型(B 止める|W 注意|N 覚え) 鍵 値…
driver_min() { printf '%s\n' "$DRIVER_MIN" | LC_ALL=C $AWK -v e="$1" '$1 == e { print $2 }'; }
detect_env() {
  local ov="${SYNC_ENV_OVERRIDE:-}" g x avx2 avx512 ram glibc kfd need user
  OVF=$TMPD/ov.flat; : > "$OVF"; : > "$ENVF"
  if [ -n "$ov" ]; then printf '%s' "$ov" > "$TMPD/ov.json"; jflat "$TMPD/ov.json" > "$OVF" 2>/dev/null || : > "$OVF"; fi
  # GPU
  if ov_has gpus; then
    LC_ALL=C $AWK -F '\t' -v US="$US" '{ n = split($1, k, "\034") } n == 3 && k[1] == "gpus" { v[k[2], k[3]] = $3; if (k[2] + 1 > c) c = k[2] + 1 }
      END { for (j = 0; j < c; j++) print v[j, "name"] US v[j, "cc"] US v[j, "driver"] US v[j, "vram_gib"] }' "$OVF" > "$TMPD/gpus.tsv"
  else probe_nvidia > "$TMPD/gpus.tsv"; fi
  if ov_has adapters; then
    LC_ALL=C $AWK -F '\t' -v US="$US" '{ n = split($1, k, "\034") } n == 3 && k[1] == "adapters" { v[k[2], k[3]] = $3; if (k[2] + 1 > c) c = k[2] + 1 }
      END { for (j = 0; j < c; j++) print v[j, "name"] US v[j, "vram_gib"] US v[j, "device"] US v[j, "driver"] US v[j, "vendor"] }' "$OVF" > "$TMPD/ads.tsv"
  elif [ -s "$TMPD/gpus.tsv" ]; then : > "$TMPD/ads.tsv"
  else probe_adapters > "$TMPD/ads.tsv"; fi
  g=$(NV_TABLE=$NV_TABLE RADEON_IDS=$RADEON_IDS RADEON_NAMES=$RADEON_NAMES AMD_IGPU_IDS=$AMD_IGPU_IDS IGPU_NAME_RE=$IGPU_NAME_RE \
      LC_ALL=C $AWK "$AWK_PICK" "$TMPD/gpus.tsv" "$TMPD/ads.tsv")
  IFS=$US read -r G_ENGINE G_KIND G_NAME G_VENDOR G_VRAM G_DRIVER G_DEVICE G_ADRV <<EOF
$g
EOF
  [ -n "$G_KIND" ] || { G_KIND=unknown; env_add W check_failed; }
  if [ -z "$G_NAME" ] && [ "$G_VENDOR" = amd ]; then G_NAME="AMD Radeon ($G_DEVICE)"; fi
  ENGINE=$G_ENGINE
  case $G_KIND in
    none) env_add B no_gpu ;;
    igpu) env_add B igpu_only "$G_NAME" ;;
    too_old) env_add B gpu_too_old "$G_NAME" ;;
    nodriver) env_add B nvidia_no_driver "$G_NAME" ;;
    turing) if [ "$TURING" = block ]; then env_add B gpu_turing_pending "$G_NAME"; else env_add W gpu_untested "$G_NAME"; fi ;;
    untested) env_add W gpu_untested "$G_NAME" ;;
    experimental) env_add W gpu_experimental "$G_NAME" ;;
  esac
  if [ "$G_VENDOR" = nvidia ] && [ -n "$ENGINE" ]; then
    need=$(driver_min "$ENGINE")
    if [ -n "$need" ] && LC_ALL=C $AWK -v d="${G_DRIVER:-0}" -v n="$need" 'BEGIN {
          a = split(d, x, "."); b = split(n, y, "."); m = a > b ? a : b; lt = 0
          for (k = 1; k <= m; k++) { p = (k <= a) ? x[k] + 0 : 0; q = (k <= b) ? y[k] + 0 : 0; if (p != q) { lt = (p < q); break } }
          exit !lt }'; then env_add B driver_old "${G_DRIVER:-?}" "$need"; fi
  fi
  if [ "$G_VENDOR" = amd ] && [ -n "$ENGINE" ]; then
    x=$G_ADRV; [ -z "$x" ] && [ "$(ov_get amdgpu)" = false ] && x=none
    if [ -n "$x" ] && [ "$x" != amdgpu ]; then env_add B amdgpu_missing "$x"; fi
    kfd=$(ov_get kfd)
    if [ -z "$kfd" ]; then
      if [ ! -e /dev/kfd ]; then kfd=missing; elif [ -r /dev/kfd ] && [ -w /dev/kfd ]; then kfd=ok; else kfd=denied; fi
    fi
    user=$(id -un 2>/dev/null || echo "$USER")
    case $kfd in missing) env_add B kfd_missing ;; denied) env_add B kfd_denied "$user" ;; esac
  fi
  if [ -n "$ENGINE" ]; then
    if [ -z "$G_VRAM" ]; then env_add W vram_unknown
    elif LC_ALL=C $AWK -v v="$G_VRAM" -v w="$VRAM_WARN_GIB" 'BEGIN { exit !(v + 0.5 < w) }'; then env_add W vram_low "$G_VRAM"; fi
  fi
  # CPU・RAM・glibc
  avx2=$(ov_get avx2); avx512=$(ov_get avx512); ram=$(ov_get ram_gib); glibc=$(ov_get glibc)
  if [ -z "$avx2" ]; then if grep -qw avx2 /proc/cpuinfo 2>/dev/null; then avx2=true; else avx2=false; fi; fi
  if [ -z "$avx512" ]; then if grep -qw avx512f /proc/cpuinfo 2>/dev/null; then avx512=true; else avx512=false; fi; fi
  [ -z "$ram" ] && ram=$(LC_ALL=C $AWK '/^MemTotal:/ { printf "%.1f", $2 / 1048576 }' /proc/meminfo 2>/dev/null)
  if ! ov_has glibc; then glibc=$(getconf GNU_LIBC_VERSION 2>/dev/null | LC_ALL=C $AWK '{ print $2 }'); fi
  [ "$avx2" = false ] && env_add B no_avx2
  if [ -z "$glibc" ]; then env_add B no_glibc
  elif LC_ALL=C $AWK -v g="$glibc" -v m="$GLIBC_MIN" 'BEGIN { split(g, a, "."); split(m, b, "."); exit !((a[1] + 0) * 1000 + a[2] < (b[1] + 0) * 1000 + b[2]) }'; then env_add B glibc_old "$glibc"; fi
  if [ -n "$ram" ] && LC_ALL=C $AWK -v r="$ram" -v w="$RAM_WARN_GIB" 'BEGIN { exit !(r + 1 < w) }'; then env_add W ram_low "$ram"; fi
  [ "$avx512" = false ] && env_add N no_avx512
  [ "$DL" = none ] && env_add W no_downloader
  ENV_DONE=1
}
# 起動の道具（sync env）がいれば照らす．起動の道具の見立てが動くときに使われるので，違えばそちらのエンジンを入れる
launcher_check() {
  local sy="$BIN/launcher/sync.py" py le
  [ -f "$sy" ] || return 0
  py=$BIN/python/bin/python3
  [ -x "$py" ] || py=$(command -v python3 2>/dev/null) || return 0
  SYNC_HOME=$SYNC_HOME $TO_LONG "$py" -s -X utf8 "$sy" env --json --ascii 2>/dev/null < /dev/null | tail -n 1 > "$TMPD/le.json"
  [ -s "$TMPD/le.json" ] || return 0
  le=$(jflat "$TMPD/le.json" 2>/dev/null | LC_ALL=C $AWK -F '\t' '$1 == "engine" && $2 == "s" { print $3 }')
  if [ -n "$le" ] && [ "$le" != "$ENGINE" ]; then
    env_add N launcher_engine "$le" "${ENGINE:-none}" "$le"
    ENGINE=$le
  fi
}
env_report() {
  local ty key a b c n_b
  n_b=$(LC_ALL=C $AWK -F "$US" '$1 == "B"' "$ENVF" | wc -l | tr -d ' ')
  if [ "$n_b" = 0 ]; then add ok "$(t env_ok)"; else add ng "$(t env_ng)"; fi
  if [ -n "$ENGINE" ]; then add engine "$(t env_engine "$ENGINE" "${G_NAME:-?}")"; elif [ "$CMD" = setup ]; then add ng "$(t env_app_only)"; fi
  for ty in B W N; do
    while IFS=$US read -r x key a b c <&4; do
      [ "$x" = "$ty" ] || continue
      if [ "$ty" = B ]; then add ng "$(t "env_$key" "$a" "$b" "$c")"; else add note "$(t "env_$key" "$a" "$b" "$c")"; fi
    done 4< "$ENVF"
  done
}

# ============================================================================ アイコン（.desktop）・入口（update.sh など）・dsh の設定のひな形
desktop_dir() {
  local d
  d=$(xdg-user-dir DESKTOP 2>/dev/null)
  [ -n "$d" ] && [ "$d" != "$HOME" ] && [ -d "$d" ] && { printf '%s' "$d"; return; }
  [ -d "$HOME/Desktop" ] && printf '%s' "$HOME/Desktop"
}
dq() { printf '"%s"' "$(printf '%s' "$1" | sed 's/[\\"`$]/\\&/g; s/%/%%/g')"; }    # .desktop の Exec の引用
AWK_SHORTCUTS='
BEGIN { US = "\037" }
{ n = split($1, k, "\034") }
n == 3 && k[1] == "shortcuts" { v[k[2], k[3]] = $3; if (k[2] + 1 > c) c = k[2] + 1 }
n == 4 && k[1] == "shortcuts" && k[3] == "where" { w[k[2]] = w[k[2]] " " $3; if (k[2] + 1 > c) c = k[2] + 1 }
END { for (j = 0; j < c; j++) print v[j, "name"] US v[j, "file"] US v[j, "target"] US v[j, "fallback"] US v[j, "args"] US w[j] US v[j, "description"] US v[j, "terminal"] US v[j, "target_args"] US v[j, "fallback_args"] }
'
# 一覧に shortcuts が無いとき（古い版）の既定．sources.json の shortcuts_linux と同じ
DEFAULT_SHORTCUTS="Sync-Strata${US}sync-strata${US}app/shell/sync-strata${US}app/launcher/sync.sh${US}up --gui --open${US} desktop startmenu${US}${US}${US}${US}
Sync-Strata の更新${US}sync-strata-update${US}update.sh${US}${US}${US} startmenu${US}${US}true${US}${US}
Sync-Strata を前の版に戻す${US}sync-strata-rollback${US}rollback.sh${US}${US}${US} startmenu${US}${US}true${US}${US}
Sync-Strata を消す${US}sync-strata-uninstall${US}uninstall.sh${US}${US}${US} startmenu${US}${US}true${US}${US}"
set_shortcuts() {
  local list="$TMPD/shortcuts.tsv" dk ap made='' n=0 name file target fb args where desc term targs fargs exe argv ic w dir f nk en ja cm cmj
  LC_ALL=C $AWK -F '\t' "$AWK_SHORTCUTS" "$FEED_FLAT" > "$list"
  [ -s "$list" ] || printf '%s\n' "$DEFAULT_SHORTCUTS" > "$list"
  if [ -n "$O_SCDIR" ]; then dk=$O_SCDIR/Desktop; ap=$O_SCDIR/applications; mkdir -p "$dk" "$ap"
  else dk=$(desktop_dir); ap=$XDG_DATA/applications; fi
  ic=
  for f in "$BIN/shell/icon.png" "$BIN/shell/sync-strata.png" "$BIN/launcher/icon.png" "$BIN/pack/icon.png"; do [ -f "$f" ] && { ic=$f; break; }; done
  while IFS=$US read -r name file target fb args where desc term targs fargs <&4; do
    [ -n "$name" ] || continue
    [ -n "$file" ] || file=$(printf '%s' "$name" | LC_ALL=C tr -c 'A-Za-z0-9._-' '-')
    # 行き先: 一覧の target（アプリの枠）→ app/shell/*.AppImage → fallback（sync.sh up --gui --open）
    exe=$APP/$target; argv=$targs; [ -z "$fb" ] && argv=$args
    if [ ! -e "$exe" ] && [ -n "$fb" ]; then
      for f in "$BIN"/shell/*.AppImage; do [ -f "$f" ] && { exe=$f; break; }; done
    fi
    if [ ! -e "$exe" ] && [ -n "$fb" ]; then exe=$APP/$fb; argv=${fargs:-$args}; fi
    if [ ! -e "$exe" ]; then add skipped "$(t sc_missing "$name" "$target")"; continue; fi
    [ -x "$exe" ] || chmod +x "$exe" 2>/dev/null
    [ "$term" = true ] && argv="${argv:+$argv }--pause"
    case $file in
      sync-strata) nk=sc_main_name ;; sync-strata-update) nk=sc_update_name ;; sync-strata-rollback) nk=sc_rollback_name ;;
      sync-strata-uninstall) nk=sc_uninstall_name ;; *) nk= ;;
    esac
    if [ -n "$nk" ]; then tx "$nk"; en=$E; ja=$J; else en=$name; ja=$name; fi
    tx sc_main_comment; cm=$E; cmj=${desc:-$J}
    for w in $where; do
      case $w in desktop) dir=$dk ;; startmenu) dir=$ap ;; *) dir= ;; esac
      [ -n "$dir" ] || continue
      mkdir -p "$dir" 2>/dev/null || continue
      f=$dir/$file.desktop
      {
        printf '[Desktop Entry]\nType=Application\nVersion=1.0\n'
        printf 'Name=%s\nName[ja]=%s\n' "$en" "$ja"
        printf 'Comment=%s\nComment[ja]=%s\n' "$cm" "$cmj"
        printf 'Exec=%s%s\n' "$(dq "$exe")" "${argv:+ $argv}"
        printf 'Terminal=%s\n' "$([ "$term" = true ] && echo true || echo false)"
        [ -n "$ic" ] && printf 'Icon=%s\n' "$ic"
        printf 'Categories=Utility;\nStartupNotify=true\n'
      } > "$f.tmp" && mv -f "$f.tmp" "$f" || continue
      chmod 755 "$f"
      [ "$w" = desktop ] && command -v gio >/dev/null 2>&1 && gio set "$f" metadata::trusted true >/dev/null 2>&1
      st_put short "$f"
      made="${made:+$made$LSEP}${f##*/}"; n=$((n + 1))
    done
  done 4< "$list"
  command -v update-desktop-database >/dev/null 2>&1 && [ -z "$O_SCDIR" ] && update-desktop-database "$ap" >/dev/null 2>&1
  [ "$n" -gt 0 ] && add created "$(t sc_made "$n" "$made")"
}
# 入れた先の update.sh・rollback.sh・uninstall.sh: 入れ替えの途中で自分が書き換わらないよう，setup の写しを一時フォルダーに置いて流す
make_stub() { # 命令 説明
  tx stub_missing; m1="$E / $J"; tx stub_pause; m2="$E / $J"
  cat <<EOF
#!/bin/sh
# Sync-Strata: $2. Runs a copy of the setup from a temporary folder, so that it can replace (or remove) this folder.
D="\$(cd "\$(dirname "\$0")" && pwd)"
S="\$D/app/pack/setup.sh"; [ -f "\$S" ] || S="\$D/state/setup.sh"
P=0; if [ "\${1:-}" = "--pause" ]; then P=1; shift; fi
T="\$(mktemp -d)" || exit 1
if ! cp "\$S" "\$T/setup.sh" 2>/dev/null; then echo "$m1"; rm -rf "\$T"; [ "\$P" = 1 ] && { printf '%s' "$m2"; read -r _; }; exit 1; fi
sh "\$T/setup.sh" $1 --app-dir "\$D" "\$@"
RC=\$?
rm -rf "\$T"
if [ "\$P" = 1 ]; then printf '\n%s' "$m2"; read -r _; fi
exit \$RC
EOF
}
set_stubs() {
  local made='' c p d
  for c in update rollback uninstall; do
    p=$APP/$c.sh
    case $c in update) d='update (only the changed parts)' ;; rollback) d='go back to the version before the last update' ;; uninstall) d='uninstall' ;; esac
    make_stub "$c" "$d" > "$TMPD/stub"
    if [ -f "$p" ] && cmp -s "$TMPD/stub" "$p"; then continue; fi
    cp "$TMPD/stub" "$p" && chmod 755 "$p" && made="${made:+$made$LSEP}$c.sh"
  done
  # 入口が流す setup の写し（部品 pack に setup.sh が入れば，そちらが先に使われる）
  if [ -f "$SELF" ] && ! cmp -s "$SELF" "$STATE_DIR/setup.sh" 2>/dev/null; then
    cp "$SELF" "$STATE_DIR/setup.sh.tmp" && mv -f "$STATE_DIR/setup.sh.tmp" "$STATE_DIR/setup.sh"
  fi
  [ -n "$made" ] && add created "$(t stubs_made "$made")"
}
set_dsh_profile() {
  local tpl="$BIN/pack/dsh-profile" dst="$SYNC_HOME/dsh-home/profiles/web" made='' f name
  [ -d "$tpl" ] || return 0
  for f in "$tpl"/*; do
    [ -f "$f" ] || continue
    name=${f##*/}; name=${name%.template}
    [ -e "$dst/$name" ] && continue
    mkdir -p "$dst" && cp "$f" "$dst/$name" && made="${made:+$made$LSEP}$name"
  done
  if [ -n "$made" ]; then add created "$(t dsh_made "$made" "$dst")"; else add skipped "$(t dsh_kept)"; fi
}

# ============================================================================ モデルの置き場
# 並びは入れた chat の部品の models/models.dist.json から読む（pack は models の local_dir．pending は除く．MANIFEST.json の大きさまで確かめる．
# 共通の部品は shared の任意でないファイル）．一覧が無いときは既定の並び．
AWK_LAYOUT='
BEGIN { US = "\037" }
{ n = split($1, k, "\034") }
k[1] == "models" && n == 3 && k[3] == "local_dir" { md[k[2]] = $3; if (k[2] + 1 > nm) nm = k[2] + 1 }
k[1] == "models" && n == 3 && k[3] == "pending" { pend[k[2]] = ($3 == "true") }
k[1] == "models" && n == 5 && k[3] == "files" && k[5] == "bytes" { mb[k[2]] += $3 }
k[1] == "shared" && n == 3 && k[3] == "id" { sid[k[2]] = $3; if (k[2] + 1 > ns) ns = k[2] + 1 }
k[1] == "shared" && n == 3 && k[3] == "local_dir" { sld[k[2]] = $3 }
k[1] == "shared" && n == 3 && k[3] == "optional" { sopt[k[2]] = ($3 == "true") }
k[1] == "shared" && n == 5 && k[3] == "files" && k[5] == "path" { sp[k[2], k[4]] = $3; if (k[4] + 1 > sn[k[2]]) sn[k[2]] = k[4] + 1 }
k[1] == "shared" && n == 5 && k[3] == "files" && k[5] == "bytes" { sb[k[2]] += $3 }
END {
  small = -1
  for (j = 0; j < nm; j++) if (!pend[j] && md[j] != "") { print "pack" US md[j] US sprintf("%.0f", mb[j]); if (small < 0 || mb[j] < small) small = mb[j] }
  tot = 0
  for (j = 0; j < ns; j++) { if (sopt[j]) continue; tot += sb[j]
    for (m = 0; m < sn[j]; m++) { p = sp[j, m]; d = sld[j]; if (d != "" && d != ".") p = d "/" p; sub(/^\.\//, "", p); print "shared" US sid[j] US p } }
  if (small < 0) small = 0
  print "need" US sprintf("%.0f", small + tot)
}
'
DEFAULT_LAYOUT="pack${US}sync-s-sb${US}0
pack${US}sync-r1q2-sb${US}0
shared${US}native-gguf${US}native-gguf/Qwen3.8-Flash-Next-Sync-common.gguf
shared${US}mtp-rt${US}mtp-rt/experts.bin
shared${US}mtp-rt${US}mtp-rt/dense.bin
shared${US}mtp-rt${US}mtp-rt/draft_vocab.bin
shared${US}tokenizer${US}tokenizer/vocab.json
need${US}64424509440"
load_layout() {
  LAYOUT=$TMPD/layout.tsv
  if [ -f "$BIN/chat/models/models.dist.json" ] && jflat "$BIN/chat/models/models.dist.json" > "$TMPD/cat.flat" 2>/dev/null; then
    LC_ALL=C $AWK -F '\t' "$AWK_LAYOUT" "$TMPD/cat.flat" > "$LAYOUT"
  fi
  grep -q "^pack$US" "$LAYOUT" 2>/dev/null || printf '%s\n' "$DEFAULT_LAYOUT" > "$LAYOUT"
}
pack_ok() { # pack のフォルダー: MANIFEST.json の files が全部あり，bytes があれば大きさも合う
  jflat "$1/MANIFEST.json" > "$TMPD/pm.flat" 2>/dev/null || return 1
  find "$1" -type f -printf '%P\t%s\n' > "$TMPD/pm.act" 2>/dev/null
  LC_ALL=C $AWK -F '\t' 'FILENAME == ARGV[1] { a[$1] = $2; next }
    { n = split($1, k, "\034"); if (k[1] != "files" || n < 2) next; need[k[2]] = 1
      if (n == 3 && k[3] == "bytes" && (!(k[2] in a) || a[k[2]] != $3)) bad = 1 }
    END { for (x in need) if (!(x in a)) bad = 1; exit bad }' "$TMPD/pm.act" "$TMPD/pm.flat"
}
test_models_dir() { # フォルダー → TM_PACKS TM_MISSING（読点区切り）
  local kind x y
  TM_PACKS='' TM_MISSING=''
  [ -d "$1" ] || return 1
  while IFS=$US read -r kind x y <&4; do
    case $kind in
      pack) [ -f "$1/$x/MANIFEST.json" ] && pack_ok "$1/$x" && TM_PACKS="${TM_PACKS:+$TM_PACKS$LSEP}$x" ;;
      shared) if [ ! -e "$1/$y" ]; then case "$LSEP$TM_MISSING$LSEP" in *"$LSEP$x$LSEP"*) ;; *) TM_MISSING="${TM_MISSING:+$TM_MISSING$LSEP}$x" ;; esac; fi ;;
    esac
  done 4< "$LAYOUT"
  [ -n "$TM_PACKS" ]
}
looks_models() { # 速い下見: どれかの pack の MANIFEST.json がある
  local kind x y
  [ -d "$1" ] || return 1
  while IFS=$US read -r kind x y <&4; do [ "$kind" = pack ] && [ -f "$1/$x/MANIFEST.json" ] && return 0; done 4< "$LAYOUT"
  return 1
}
real_mounts() { # 実の置き場（ext4・xfs・btrfs・NTFS など）のマウント先．/proc・/sys・/boot などは外す
  LC_ALL=C $AWK '$3 ~ /^(ext[234]|xfs|btrfs|f2fs|zfs|ntfs|ntfs3|fuseblk|exfat|vfat|bcachefs|jfs|reiserfs|nilfs2)$/ {
      m = $2; gsub(/\\040/, " ", m); gsub(/\\011/, "\t", m)
      if (m ~ /^\/(proc|sys|dev|run|boot|snap|efi|var\/lib\/(docker|snapd|containers))(\/|$)/) next
      if (!s[m]++) print m }' /proc/self/mounts 2>/dev/null
}
ROOT_SKIP=' bin boot dev etc lib lib32 lib64 libx32 lost+found proc root run sbin snap sys tmp usr var home efi '
model_candidates() {
  local b x y m
  [ -n "${SYNC_MODELS:-}" ] && printf '%s\n' "$SYNC_MODELS"
  [ -n "$DIST_ROOT" ] && printf '%s\n%s\n' "$DIST_ROOT/models" "$(dirname "$DIST_ROOT")/models"
  printf '%s\n%s\n%s\n' "$DEFAULT_MODELS" "$SYNC_HOME/models" "$APP/models"
  for b in "$HOME/Downloads" "$HOME/Desktop" "$HOME/Documents" "$HOME"; do
    printf '%s\n' "$b/models"
    for x in "$b"/*/; do [ -d "$x" ] && printf '%s\n' "${x%/}/models"; done
  done
  real_mounts | while IFS= read -r m; do
    m=${m%/}
    printf '%s\n' "$m/models"
    for x in "$m"/*/; do
      [ -d "$x" ] || continue
      if [ -z "$m" ]; then case $ROOT_SKIP in *" $(basename "$x") "*) continue ;; esac; fi
      printf '%s\n' "${x%/}/models"
      for y in "$x"*/; do [ -d "$y" ] && printf '%s\n' "${y%/}/models"; done
    done
  done
}
free_gib() { # 置き場（無ければ在る親）の空き（GiB）
  local p="$1"
  while [ ! -e "$p" ] && [ "$p" != / ]; do p=$(dirname "$p"); done
  df -Pk "$p" 2>/dev/null | LC_ALL=C $AWK 'NR == 2 { printf "%.0f", $4 / 1048576 }'
}
find_models() {
  local cur found='' n=0 t0 d need fr bestm='' bestf=0 m f msg
  t0=$(now)
  load_layout
  cur=; [ -f "$SETTINGS" ] && jflat "$SETTINGS" > "$TMPD/set.flat" 2>/dev/null && cur=$(jget "$TMPD/set.flat" models_dir)
  [ "$cur" = auto ] && cur=
  if [ -n "$O_MODELS" ]; then
    found=$(abspath "$O_MODELS")
    test_models_dir "$found" || add note "$(t models_given_empty "$found")"
  elif [ -n "$cur" ] && test_models_dir "$cur"; then
    add skipped "$(t models_kept "$cur" "$TM_PACKS")"; return
  elif [ "$NO_MS" = 1 ]; then
    add skipped "$(t models_nosearch)"; return
  else
    model_candidates | LC_ALL=C $AWK '!s[$0]++' > "$TMPD/cand.txt"
    while IFS= read -r d <&4; do
      n=$((n + 1))
      looks_models "$d" || continue
      if test_models_dir "$d"; then found=$d; break; fi
    done 4< "$TMPD/cand.txt"
    if [ -z "$found" ]; then
      add none "$(t models_notfound "$n" "$(elapsed "$t0")")"
      # 見つからないとき: 既定の置き場の空きが足りなければ，空きのいちばん大きい置き場を選ぶ
      need=$(LC_ALL=C $AWK -F "$US" '$1 == "need" { printf "%.0f", $2 / 1073741824 + 5 }' "$LAYOUT")
      [ -n "$need" ] || need=65
      fr=$(free_gib "$DEFAULT_MODELS"); fr=${fr:-0}
      if [ "$fr" -ge "$need" ]; then add note "$(t models_default_ok "$DEFAULT_MODELS" "$fr")"; return; fi
      real_mounts > "$TMPD/mounts.txt"
      while IFS= read -r m <&4; do
        [ "$m" = / ] && continue
        [ -w "$m" ] || continue
        f=$(free_gib "$m"); f=${f:-0}
        [ "$f" -gt "$bestf" ] && { bestf=$f; bestm=$m; }
      done 4< "$TMPD/mounts.txt"
      if [ -n "$bestm" ] && [ "$bestf" -ge "$need" ] && mkdir -p "$bestm/SyncStrata/models" 2>/dev/null; then
        json_set_top "$SETTINGS" models_dir "$bestm/SyncStrata/models"
        add chosen "$(t models_chosen "$bestm/SyncStrata/models" "$bestf" "$fr")"
      elif [ "$bestf" -gt "$fr" ]; then add note "$(t models_no_space "$need" "$bestf" "$bestm")"
      else add note "$(t models_no_space "$need" "$fr" "$DEFAULT_MODELS")"; fi
      return
    fi
  fi
  [ "$cur" != "$found" ] && json_set_top "$SETTINGS" models_dir "$found"
  msg=; [ -n "$TM_MISSING" ] && msg=$(t models_missing_shared "$TM_MISSING")
  [ -n "$TM_PACKS" ] && add found "$(t models_found "$found" "$TM_PACKS" "$msg")"
}

# ============================================================================ CPU の優先度の許可（任意．sudo が要る．効くのは起動し直しの後）
nice_files() { # 道のり 中身（\n は printf の書式）
  printf '%s\n' "/etc/systemd/system/user@.service.d/90-sync-strata-nice.conf${US}[Service]\nLimitNICE=$NICE_LIMIT\n"
  printf '%s\n' "/etc/systemd/user.conf.d/90-sync-strata-nice.conf${US}[Manager]\nDefaultLimitNICE=$NICE_LIMIT\n"
  printf '%s\n' "/etc/security/limits.d/90-sync-strata.conf$US$1 - nice $NICE_LIMIT\n"
}
nice_hint() {
  local lim user p body root="${SYNC_SETUP_ETC_ROOT:-}" sudo="${SYNC_SETUP_SUDO-sudo}" ok=1
  lim=$(LC_ALL=C $AWK '/^Max nice priority/ { print $4 }' /proc/self/limits 2>/dev/null)
  if [ "$APPLY_NICE" != 1 ] && [ -n "$lim" ] && [ "$lim" != unlimited ] && [ "$lim" -ge $((20 - NICE_LIMIT)) ] 2>/dev/null; then
    add optional "$(t nice_ok "$lim")"; return
  fi
  user=$(id -un 2>/dev/null || echo "$USER")
  nice_files "$user" > "$TMPD/nice.tsv"
  if [ "$APPLY_NICE" = 1 ]; then
    while IFS=$US read -r p body <&4; do
      # shellcheck disable=SC2016
      $sudo sh -c 'mkdir -p "$(dirname "$1")" && printf "$2" > "$1"' _ "$root$p" "$body" || { ok=0; add failed "$(t nice_failed "$root$p")"; break; }
    done 4< "$TMPD/nice.tsv"
    [ "$ok" = 1 ] && add optional "$(t nice_applied)"
    return
  fi
  add optional "$(t nice_hint)"
  while IFS=$US read -r p body <&4; do
    addraw "      sudo mkdir -p $(dirname "$p") && printf '$body' | sudo tee $p >/dev/null"
  done 4< "$TMPD/nice.tsv"
  addraw "      $(t nice_check "$DIST_ROOT_SETUP")"
}

# ============================================================================ 終わり（結果・報告）
AWK_REPORT="$AWK_ESC"'
BEGIN { FS = "\037" }
FILENAME == ARGV[1] { nl++; L[nl] = qq($0); next }
{ nc++; C[nc] = "{\"id\": " qq($1) ", \"action\": " qq($2) ", \"from\": " qq($3) ", \"to\": " qq($4) ", \"check_s\": " ($5 + 0) ", \"hashed_on_check\": " ($6 + 0) ", \"files\": " ($7 + 0) ", \"bytes\": " sprintf("%.0f", $8 + 0) ", \"install_s\": " ($9 + 0) "}" }
END {
  printf "{\"command\": %s, \"exit\": %d, \"seconds\": %s, \"engine\": %s, \"env_ok\": %s, \"blockers\": [%s], \"warnings\": [%s], \"unzip\": %s,\n \"lines\": [\n  %s\n ],\n \"components\": [\n  %s\n ]\n}\n", qq(ENVIRON["R_CMD"]), ENVIRON["R_EXIT"], ENVIRON["R_SEC"], (ENVIRON["R_ENGINE"] == "" ? "null" : qq(ENVIRON["R_ENGINE"])), ENVIRON["R_OK"], ENVIRON["R_B"], ENVIRON["R_W"], qq(ENVIRON["R_UNZIP"]), join(L, nl, ",\n  "), join(C, nc, ",\n  ")
}
'
finish() {
  local sec okv b w
  sec=$(elapsed "$T_START")
  say ""
  say "$(t result_head "$CMD" "$sec")"
  cat "$RES"
  if [ -n "$O_REPORT" ]; then
    okv=null; b=; w=
    if [ "$ENV_DONE" = 1 ]; then
      okv=true; LC_ALL=C $AWK -F "$US" '$1 == "B" { f = 1 } END { exit !f }' "$ENVF" && okv=false
      b=$(LC_ALL=C $AWK -F "$US" '$1 == "B" { printf "%s\"%s\"", (n++ ? ", " : ""), $2 }' "$ENVF")
      w=$(LC_ALL=C $AWK -F "$US" '$1 != "B" { printf "%s\"%s\"", (n++ ? ", " : ""), $2 }' "$ENVF")
    fi
    mkdir -p "$(dirname "$O_REPORT")" 2>/dev/null
    R_CMD=$CMD R_EXIT=$EXIT R_SEC=$sec R_ENGINE=$ENGINE R_OK=$okv R_B=$b R_W=$w R_UNZIP="${UNZIP:-} ${PYX:-}" LC_ALL=C $AWK "$AWK_REPORT" "$RES" "$COMPREC" > "$O_REPORT"
  fi
  if [ "$PAUSE" = 1 ] && [ -t 0 ]; then tx stub_pause; printf '\n%s / %s' "$E" "$J"; read -r _; fi
  exit "$EXIT"
}

lock() {
  local pid
  mkdir -p "$STATE_DIR" || die "$(t err_move "$STATE_DIR")"
  if ! mkdir "$STATE_DIR/setup.lock" 2>/dev/null; then
    pid=$(cat "$STATE_DIR/setup.lock/pid" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then die "$(t err_locked "$pid")"; fi
    rm -rf "$STATE_DIR/setup.lock"; mkdir "$STATE_DIR/setup.lock" 2>/dev/null || die "$(t err_locked "?")"
  fi
  echo $$ > "$STATE_DIR/setup.lock/pid"; LOCKED=1
}
need_tools() {
  local c
  for c in "$AWK" find sha256sum mktemp; do command -v "$c" >/dev/null 2>&1 || die "$(t err_tool "$c")"; done
  find /dev/null -maxdepth 0 -printf '' >/dev/null 2>&1 || die "$(t err_tool "GNU find")"
}

# ============================================================================ 命令
st_load
H=${O_HOME:-${SYNC_HOME:-}}                       # --sync-home → 環境変数 SYNC_HOME → 入れたときの記録 → 既定
[ -n "$H" ] || H=$(st_get1 sync_home)
[ -n "$H" ] || H=$XDG_CONF/SyncStrata
SYNC_HOME=$(abspath "$H")
SETTINGS=$SYNC_HOME/settings.json
DIST_ROOT=; DIST_ROOT_SETUP=$SELF
case $CMD in
  setup)
    need_tools
    if [ -z "$SRC" ]; then
      if [ -f "$SELF_DIR/feed/manifest.json" ]; then SRC=$SELF_DIR/feed
      elif [ -f "$SELF_DIR/../feed/manifest.json" ]; then SRC=$(cd "$SELF_DIR/.." && pwd)/feed
      else die "$(t err_no_source)" 2; fi
    fi
    if ! is_url "$SRC"; then SRC=$(abspath "$SRC"); d=$SRC; case $d in *.json) d=$(dirname "$d") ;; esac; DIST_ROOT=$(dirname "$d"); fi
    pick_unzip || die "$(t err_no_unzip)"
    pick_downloader
    say "$(t hdr_setup "$APP")"
    lock
    open_feed "$SRC"; use_bundled_python
    mkdir -p "$BIN" "$STATE_DIR"
    detect_env
    sync_components base
    if [ "$EXIT" != 7 ]; then
      launcher_check
      if [ -n "$ENGINE" ]; then sync_components variant; else add skipped "$(t engine_none)"; fi
    fi
    commit_last_update
    if [ "$EXIT" != 7 ]; then
      set_stubs
      st_set1 feed "$FEED_LATEST"
      [ "$NO_SC" = 1 ] || set_shortcuts
      mkdir -p "$SYNC_HOME"
      set_dsh_profile
      find_models
      env_report
      nice_hint
    fi
    st_set1 sync_home "$SYNC_HOME"
    st_save
    ;;
  update)
    need_tools
    [ -f "$STATE_PATH" ] || die "$(t up_not_installed "$APP")"
    if [ -z "$SRC" ]; then
      if [ -f "$SETTINGS" ] && jflat "$SETTINGS" > "$TMPD/set.flat" 2>/dev/null; then SRC=$(jget "$TMPD/set.flat" update_feed); fi
      [ "$SRC" = auto ] && SRC=
      [ -n "$SRC" ] || SRC=$(st_get1 feed)
      SRC=$(latest_of "$SRC")         # 記録が版の名前の入った置き場（古い setup）でも，最新の置き場を見る（--source で指したときはそのまま）
    fi
    [ -n "$SRC" ] || die "$(t up_no_feed)"
    is_url "$SRC" || SRC=$(abspath "$SRC")
    pick_unzip || die "$(t err_no_unzip)"
    pick_downloader
    say "$(t hdr_update "$SRC")"
    lock
    open_feed "$SRC"; use_bundled_python
    detect_env
    sync_components base
    if [ "$EXIT" != 7 ]; then
      launcher_check
      [ -n "$ENGINE" ] && sync_components variant
      set_stubs
    fi
    commit_last_update
    st_save
    ;;
  rollback)
    [ -f "$STATE_PATH" ] || die "$(t up_not_installed "$APP")"
    lock
    if ! grep -q "^luid$US" "$ST"; then say "$(t rb_nothing)"
    elif assert_not_running; then
      LC_ALL=C $AWK -F "$US" '$1 == "luid" { print $2 }' "$ST" > "$TMPD/rb.txt"
      while IFS= read -r cid <&4; do
        t0=$(now)
        test_component "$PREV/$cid" "" full
        if [ "$TC_STATE" != ok ]; then add failed "$(t rb_fail "$cid" "$TC_STATE")"; EXIT=6; continue; fi
        p_ver=$TC_VERSION; p_fsha=$TC_FSHA
        test_component "$BIN/$cid" "$STATE_DIR/$cid.scan.tsv" scan
        n_ver=$TC_VERSION; n_fsha=$TC_FSHA
        mkdir -p "$STAGE"; rm -rf "$STAGE/swap-$cid"
        if mv "$BIN/$cid" "$STAGE/swap-$cid" && mv "$PREV/$cid" "$BIN/$cid" && mv "$STAGE/swap-$cid" "$PREV/$cid"; then
          write_scan "$BIN/$cid" "$STATE_DIR/$cid.scan.tsv"; write_scan "$PREV/$cid" "$STATE_DIR/prev-$cid.scan.tsv"
          st_put skip "$cid" "$n_ver"
          st_put prev "$cid" "$n_ver$US$n_fsha"
          st_put comp "$cid" "$p_ver$US$p_fsha$US$US$(date +%Y-%m-%dT%H:%M:%S)"
          s=$(elapsed "$t0")
          comp_rec "$cid" rollback "$n_ver" "$p_ver" 0 0 0 0 "$s"
          add rolledback "$(t rb_done "$cid" "$n_ver" "$p_ver" "$s" "$n_ver")"
        else
          add failed "$(t err_move "$cid")"; EXIT=6
        fi
      done 4< "$TMPD/rb.txt"
      st_del lu; st_del luid
      rm -rf "$STAGE"
      st_save
    fi
    ;;
  uninstall)
    if [ ! -f "$STATE_PATH" ] || [ "$(jflat "$STATE_PATH" 2>/dev/null | LC_ALL=C $AWK -F '\t' '$1 == "product" { print $3 }')" != sync-strata ]; then die "$(t un_no_state "$APP")"; fi
    case $APP in /|"$HOME"|"$XDG_DATA"|"$XDG_CONF") die "$(t un_unsafe "$APP")" ;; esac
    if assert_not_running; then
      # モデルの置き場: 設定の models_dir と既定の置き場（~/.local/share/SyncStrata/models）の在る物
      md=; [ -f "$SETTINGS" ] && jflat "$SETTINGS" > "$TMPD/set.flat" 2>/dev/null && md=$(jget "$TMPD/set.flat" models_dir)
      [ "$md" = auto ] && md=
      [ -n "$md" ] && [ ! -d "$md" ] && md=
      md2=; [ -d "$DEFAULT_MODELS" ] && [ "$DEFAULT_MODELS" != "$md" ] && md2=$DEFAULT_MODELS
      drop_m=$RMDATA; drop_h=$RMDATA
      if [ "$RMDATA" != 1 ] && [ "$YES" != 1 ] && [ -t 0 ]; then
        if [ -n "$md$md2" ]; then t un_ask_models "$md${md:+${md2:+$LSEP}}$md2"; read -r ans; case $ans in y*|Y*) drop_m=1 ;; esac; fi
        if [ -d "$SYNC_HOME" ]; then t un_ask_home "$SYNC_HOME"; read -r ans; case $ans in y*|Y*) drop_h=1 ;; esac; fi
      fi
      unsafe() { case ${1%/} in ''|/|"$HOME"|"$XDG_DATA"|"$XDG_CONF"|/mnt|/media|/home|/data|/srv|/opt) return 0 ;; esac; return 1; }
      n=0
      LC_ALL=C $AWK -F "$US" '$1 == "short" { print $2 }' "$ST" > "$TMPD/short.txt"
      while IFS= read -r f <&4; do
        [ -f "$f" ] && rm -f "$f" && n=$((n + 1))
      done 4< "$TMPD/short.txt"
      add removed "$(t un_shortcuts "$n")"
      # 消すのはこの setup が作った物だけ（既定のモデルの置き場 ~/.local/share/SyncStrata/models は同じフォルダーの中にあるので残す）
      rm -rf "$BIN" "$STATE_DIR" "$APP/update.sh" "$APP/rollback.sh" "$APP/uninstall.sh"
      rmdir "$APP" 2>/dev/null
      add removed "$(t un_app "$APP")"
      for d in "$md" "$md2"; do
        [ -n "$d" ] || continue
        if [ "$drop_m" = 1 ] && ! unsafe "$d"; then rm -rf "$d"; rmdir "$APP" 2>/dev/null; add removed "$(t un_models "$d")"
        elif [ "$drop_m" = 1 ]; then add kept "$(t un_unsafe "$d")"
        else add kept "$(t un_models "$d")"; fi
      done
      if [ "$drop_h" = 1 ] && ! unsafe "$SYNC_HOME"; then rm -rf "$SYNC_HOME"; add removed "$(t un_home "$SYNC_HOME")"
      elif [ -d "$SYNC_HOME" ]; then add kept "$(t un_home "$SYNC_HOME")"; fi
      LOCKED=0
    fi
    ;;
  status)
    n=0
    for d in "$BIN"/*/; do
      [ -d "$d" ] || continue
      cid=$(basename "$d")
      test_component "$BIN/$cid" "$STATE_DIR/$cid.scan.tsv" "$CHECK_MODE"
      pv=$(st_get prev "$cid"); x=; [ -n "$pv" ] && x=$(t st_prev "$pv")
      add "st_$TC_STATE" "$(t st_line "$cid" "$TC_VERSION" "$TC_FILES" "$x")"
      n=$((n + 1))
    done
    [ "$n" = 0 ] && say "$(t st_none "$APP")"
    ;;
esac
finish
