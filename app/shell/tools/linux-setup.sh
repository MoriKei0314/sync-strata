#!/usr/bin/env bash
# Linux 版の枠を組む道具をそろえる（係 T）．root は使わない．置き場はホーム（ext4）．
#   bash linux-setup.sh
# 入れる物: rustup（~/.cargo・~/.rustup），Node（~/.local/node），作業の木 ~/syncstrata-linux/shell と Tauri の CLI（npm）．
# apt の部品（webkit2gtk など）は root が要るので，ここでは入れない（足りなければ最後に一覧を出す）．
set -euo pipefail
NODE_VER=v24.19.0
WORK="$HOME/syncstrata-linux"
SRC="${SYNC_SHELL_SRC:-/mnt/e/QuantLab/release/app-1115/shell}"
mkdir -p "$WORK"

if [ ! -x "$HOME/.cargo/bin/cargo" ]; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o "$WORK/rustup-init.sh"
  sh "$WORK/rustup-init.sh" -y --profile minimal --default-toolchain stable --no-modify-path
fi
export PATH="$HOME/.cargo/bin:$PATH"
cargo --version

if [ ! -x "$HOME/.local/node/bin/node" ]; then
  mkdir -p "$HOME/.local"
  curl -sSfL "https://nodejs.org/dist/$NODE_VER/node-$NODE_VER-linux-x64.tar.xz" -o "$WORK/node.tar.xz"
  rm -rf "$HOME/.local/node" && mkdir -p "$HOME/.local/node"
  tar -xJf "$WORK/node.tar.xz" -C "$HOME/.local/node" --strip-components=1
fi
export PATH="$HOME/.local/node/bin:$PATH"
node --version

# 作業の木を E: の元から写す（target・node_modules・試しの物は写さない）
mkdir -p "$WORK/shell"
rsync -a --delete --exclude target --exclude target-dist --exclude node_modules --exclude test --exclude dist-win --exclude dist-linux \
  "$SRC/" "$WORK/shell/"
cd "$WORK/shell" && npm i --no-audit --no-fund >/dev/null && npx tauri --version

missing=""
for p in libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev libssl-dev libxdo-dev patchelf; do
  dpkg -s "$p" >/dev/null 2>&1 || missing="$missing $p"
done
if [ -n "$missing" ]; then echo "apt の部品が足りない:$missing"; else echo "apt の部品はそろっている"; fi
