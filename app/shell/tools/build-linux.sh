#!/usr/bin/env bash
# Linux 版の Sync-Strata（AppImage と deb）を WSL か Linux で組む（係 T）．札（gpulock）は呼ぶ側で取ってから流す．
#   bash build-linux.sh            （先に linux-setup.sh と apt の部品）
# 個人の道のりを残さないため，ホーム・cargo・rustup・作業の木の道のりを置き換える．できた物は OUT（既定 F: の dist-linux）へ．
set -euo pipefail
WORK="$HOME/syncstrata-linux"
SRC="${SYNC_SHELL_SRC:-/mnt/e/QuantLab/release/app-1115/shell}"
OUT="${SYNC_LINUX_OUT:-/mnt/f/SyncStrata-build/dist-linux}"
export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:$PATH"

rsync -a --delete --exclude target --exclude target-dist --exclude node_modules --exclude test --exclude dist-win --exclude dist-linux \
  "$SRC/" "$WORK/shell/"
cd "$WORK/shell"
[ -d node_modules ] || npm i --no-audit --no-fund >/dev/null

SEP=$'\x1f'
CARGO_HOME_DIR="${CARGO_HOME:-$HOME/.cargo}"
RUSTUP_HOME_DIR="${RUSTUP_HOME:-$HOME/.rustup}"
# 短い道のりを先に（rustc は最後に合った置き換えを使う）
export CARGO_ENCODED_RUSTFLAGS="--remap-path-prefix=${HOME}=~${SEP}--remap-path-prefix=${RUSTUP_HOME_DIR}=/rustup${SEP}--remap-path-prefix=${CARGO_HOME_DIR}=/cargo${SEP}--remap-path-prefix=${WORK}/shell=/sync-strata"
export CARGO_TARGET_DIR="$WORK/target-dist"
export CARGO_BUILD_JOBS=8   # 札の決まり（build の区分は -j 8 まで）
# AppImage の部品（linuxdeploy）は FUSE が無い所でも動くように展開して使う
export APPIMAGE_EXTRACT_AND_RUN=1
npx tauri build --bundles appimage,deb -- --locked

# 部品（app/shell/）の並び: sync-strata（起こす台本．.desktop の target）・Sync-Strata.AppImage・icon.png・THIRD-PARTY-NOTICES.txt
# deb は部品に入れず，別の置き場（OUT-deb）に置く．
rm -rf "$OUT" "$OUT-deb"
mkdir -p "$OUT" "$OUT-deb"
cp "$CARGO_TARGET_DIR"/release/bundle/appimage/*.AppImage "$OUT/Sync-Strata.AppImage"
chmod 755 "$OUT/Sync-Strata.AppImage"
cp "$CARGO_TARGET_DIR"/release/bundle/deb/*.deb "$OUT-deb"/
cp "$WORK/shell/src-tauri/icons/128x128@2x.png" "$OUT/icon.png"
cp "$SRC/dist-win/THIRD-PARTY-NOTICES.txt" "$OUT/"
cat > "$OUT/sync-strata" <<'WRAP'
#!/bin/sh
# Sync-Strata を起こす．FUSE 2（libfuse.so.2）が無い PC では，AppImage を展開して動かす．
HERE="$(dirname "$(readlink -f "$0")")"
if ! (ldconfig -p 2>/dev/null | grep -q 'libfuse\.so\.2'); then
  APPIMAGE_EXTRACT_AND_RUN=1
  export APPIMAGE_EXTRACT_AND_RUN
fi
exec "$HERE/Sync-Strata.AppImage" "$@"
WRAP
chmod 755 "$OUT/sync-strata"
ls -la "$OUT" "$OUT-deb"
