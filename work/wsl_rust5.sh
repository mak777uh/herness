#!/usr/bin/env bash
# Тулчейн распакован, но лежит как установщик: внутри каталог rustc/, а не bin/.
# Ставим его штатным install.sh — он разложит по местам без сети.
OUT=/mnt/c/111/herness/work/wsl-rust5.txt
: > "$OUT"

TC=/root/.rustup/toolchains/rust-1.85.0-x86_64-unknown-linux-gnu
echo '=== 1. Что внутри' >> "$OUT"
ls "$TC" >> "$OUT" 2>&1

echo '=== 2. install.sh' >> "$OUT"
if [ -x "$TC/install.sh" ]; then
  "$TC/install.sh" --prefix=/root/.rustup/toolchains/stable-x86_64-unknown-linux-gnu \
    --disable-ldconfig >> "$OUT" 2>&1
  echo "install: $?" >> "$OUT"
else
  echo 'install.sh нет' >> "$OUT"
fi

echo '=== 3. Проверка' >> "$OUT"
/root/.rustup/toolchains/stable-x86_64-unknown-linux-gnu/bin/rustc --version >> "$OUT" 2>&1
/root/.rustup/toolchains/stable-x86_64-unknown-linux-gnu/bin/cargo --version >> "$OUT" 2>&1
echo DONE >> "$OUT"
