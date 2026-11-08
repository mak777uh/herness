#!/usr/bin/env bash
# Rust в WSL: sh.rustup.rs недоступен из этой сети. Пробуем apt и зеркала.
OUT=/mnt/c/111/herness/work/wsl-rust2.txt
: > "$OUT"

echo '=== 1. apt: есть ли rustc/cargo' >> "$OUT"
apt-cache policy rustc cargo 2>&1 | head -12 >> "$OUT"

echo '=== 2. пробую apt-get install' >> "$OUT"
DEBIAN_FRONTEND=noninteractive apt-get install -y rustc cargo >> "$OUT" 2>&1
echo "apt: $?" >> "$OUT"
command -v rustc >> "$OUT" 2>&1
command -v cargo >> "$OUT" 2>&1
rustc --version >> "$OUT" 2>&1
cargo --version >> "$OUT" 2>&1
echo DONE >> "$OUT"
