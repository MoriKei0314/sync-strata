#!/usr/bin/env bash
# 配布用の Sync-Strata.exe を作り，dist-win\ に置く（11/15 係 T）．札（gpulock）は呼ぶ側で取ってから流す．
#   bash build-dist.sh
# exe に個人の道のりを残さないため，cargo のホーム・rustup のホーム・作業場の道のりを置き換え，PDB の道のりはファイル名だけにする．
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SHELL_DIR="$(cd "$HERE/.." && pwd)"
W_SHELL="$(cygpath -w "$SHELL_DIR")"
W_CARGO="$(cygpath -w "${CARGO_HOME:-$USERPROFILE/.cargo}")"
W_RUSTUP="$(cygpath -w "${RUSTUP_HOME:-$USERPROFILE/.rustup}")"
W_HOME="$(cygpath -w "$USERPROFILE")"
export PATH="$(cygpath -u "$W_CARGO")/bin:$PATH"
# 長い道のりから先に置き換える（rustc は最後に合った物を使うので，短い物を前に並べる）．
SEP=$'\x1f'
export CARGO_ENCODED_RUSTFLAGS="--remap-path-prefix=${W_HOME}=~${SEP}--remap-path-prefix=${W_RUSTUP}=/rustup${SEP}--remap-path-prefix=${W_CARGO}=/cargo${SEP}--remap-path-prefix=${W_SHELL}=/sync-strata${SEP}-Clink-arg=/PDBALTPATH:%_PDB%"
# 配布用は別の target に作る（開発用の差分ビルドと混ぜない）．
# 置き場は環境変数で替えられる（E: の空きが少ないときは F: に．11/16）．
export CARGO_TARGET_DIR="${SYNC_WIN_TARGET:-$SHELL_DIR/src-tauri/target-dist}"
DIST_DIR="${SYNC_WIN_DIST:-$SHELL_DIR/dist-win}"
cd "$SHELL_DIR/src-tauri"
cargo build --release --locked
mkdir -p "$DIST_DIR"
cp "$CARGO_TARGET_DIR/release/Sync-Strata.exe" "$DIST_DIR/Sync-Strata.exe" 2>/dev/null || cp "$CARGO_TARGET_DIR/release/sync-strata.exe" "$DIST_DIR/Sync-Strata.exe"
cp "$SHELL_DIR/dist-win/THIRD-PARTY-NOTICES.txt" "$DIST_DIR/" 2>/dev/null || true
echo "$DIST_DIR に置いた"
