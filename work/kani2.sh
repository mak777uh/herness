#!/usr/bin/env bash
# Kani: сначала проверяем, доступен ли crates.io из WSL.
OUT=/mnt/c/111/herness/work/kani2.txt
: > "$OUT"

export PATH="/root/.rustup/toolchains/stable-x86_64-unknown-linux-gnu/bin:$PATH"
echo '=== 1. crates.io доступен?' >> "$OUT"
curl -s -m 20 -o /dev/null -w "crates.io: %{http_code}\n" https://crates.io >> "$OUT" 2>&1
curl -s -m 20 -o /dev/null -w "static.crates.io: %{http_code}\n" https://static.crates.io >> "$OUT" 2>&1
curl -s -m 20 -o /dev/null -w "github.com: %{http_code}\n" https://github.com >> "$OUT" 2>&1

echo '=== 2. cargo install kani-verifier' >> "$OUT"
cargo install --locked kani-verifier >> "$OUT" 2>&1
echo "install: $?" >> "$OUT"
command -v kani >> "$OUT" 2>&1
kani --version >> "$OUT" 2>&1
echo DONE >> "$OUT"
