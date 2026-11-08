#!/usr/bin/env bash
# Rust в WSL: установщик скачан через Windows (в WSL сеть блокирует rustup.rs).
OUT=/mnt/c/111/herness/work/wsl-rust3.txt
: > "$OUT"

echo '=== 1. Установщик' >> "$OUT"
ls -l /mnt/c/111/herness/work/rustup-init >> "$OUT" 2>&1
cp /mnt/c/111/herness/work/rustup-init /tmp/rustup-init >> "$OUT" 2>&1
chmod +x /tmp/rustup-init >> "$OUT" 2>&1

echo '=== 2. Установка Rust' >> "$OUT"
/tmp/rustup-init -y --default-toolchain stable --profile minimal >> "$OUT" 2>&1
echo "rustup: $?" >> "$OUT"
. "$HOME/.cargo/env" 2>/dev/null
"$HOME/.cargo/bin/rustc" --version >> "$OUT" 2>&1
"$HOME/.cargo/bin/cargo" --version >> "$OUT" 2>&1
echo DONE >> "$OUT"
