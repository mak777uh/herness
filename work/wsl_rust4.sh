#!/usr/bin/env bash
# Rust в WSL без сети: тулчейн скачан через Windows и распакован вручную.
# rustup сам качает с static.rust-lang.org, а из WSL этот адрес недоступен.
OUT=/mnt/c/111/herness/work/wsl-rust4.txt
: > "$OUT"

echo '=== 1. Что скачано' >> "$OUT"
ls -lh /mnt/c/111/herness/work/rust-*.tar.* >> "$OUT" 2>&1

echo '=== 2. Распаковка в ~/.rustup/toolchains' >> "$OUT"
mkdir -p "$HOME/.rustup/toolchains" >> "$OUT" 2>&1
cd "$HOME/.rustup/toolchains" || exit 2
for f in /mnt/c/111/herness/work/rust-*.tar.*; do
  [ -e "$f" ] || continue
  echo "распаковываю $f" >> "$OUT"
  case "$f" in
    *.tar.xz) tar -xJf "$f" >> "$OUT" 2>&1 ;;
    *.tar.gz) tar -xzf "$f" >> "$OUT" 2>&1 ;;
  esac
  echo "tar: $?" >> "$OUT"
done
ls -d "$HOME"/.rustup/toolchains/* >> "$OUT" 2>&1

echo '=== 3. Проверка' >> "$OUT"
TC=$(ls -d "$HOME"/.rustup/toolchains/* 2>/dev/null | head -1)
echo "тулчейн: $TC" >> "$OUT"
"$TC/bin/rustc" --version >> "$OUT" 2>&1
"$TC/bin/cargo" --version >> "$OUT" 2>&1
echo DONE >> "$OUT"
