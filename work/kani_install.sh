#!/usr/bin/env bash
# Установка Rust и Kani в WSL. Всё логируется в файл, потому что stdout через PowerShell
# приходит искажённым (UTF-16).
OUT=/mnt/c/111/herness/work/kani-install.txt
: > "$OUT"

echo '=== 1. Rust' >> "$OUT"
if [ -x "$HOME/.cargo/bin/cargo" ]; then
  echo 'rust уже есть' >> "$OUT"
else
  echo 'ставлю rust через rustup' >> "$OUT"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/rustup.sh >> "$OUT" 2>&1
  echo "curl: $?" >> "$OUT"
  sh /tmp/rustup.sh -y --default-toolchain stable >> "$OUT" 2>&1
  echo "rustup: $?" >> "$OUT"
fi
"$HOME/.cargo/bin/cargo" --version >> "$OUT" 2>&1

echo '=== 2. Kani' >> "$OUT"
export PATH="$HOME/.cargo/bin:$PATH"
if command -v kani >/dev/null 2>&1; then
  echo 'kani уже есть' >> "$OUT"
else
  cargo install --locked kani-verifier >> "$OUT" 2>&1
  echo "install: $?" >> "$OUT"
fi
kani --version >> "$OUT" 2>&1

echo '=== 3. Kani setup' >> "$OUT"
kani setup --yes >> "$OUT" 2>&1
echo "setup: $?" >> "$OUT"
kani --version >> "$OUT" 2>&1
echo DONE >> "$OUT"
