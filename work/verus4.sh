#!/usr/bin/env bash
# Verus требует конкретный тулчейн 1.99.1. Качаем его через Windows (как nightly).
OUT=/mnt/c/111/herness/work/verus4.txt
: > "$OUT"

echo '=== 1. Что скачано' >> "$OUT"
ls -lh /mnt/c/111/herness/work/rust-1.99* 2>/dev/null >> "$OUT" 2>&1

echo '=== 2. Распаковка' >> "$OUT"
rm -rf /opt/rust-1.99
mkdir -p /opt/rust-1.99 >> "$OUT" 2>&1
for f in /mnt/c/111/herness/work/rust-1.99*.tar.xz; do
  [ -e "$f" ] || continue
  tar -xJf "$f" -C /opt/rust-1.99 >> "$OUT" 2>&1
  echo "tar: $?" >> "$OUT"
done
ls /opt/rust-1.99 >> "$OUT" 2>&1

echo '=== 3. install.sh' >> "$OUT"
SRC=$(ls -d /opt/rust-1.99/rust-1.99* 2>/dev/null | head -1)
echo "src: $SRC" >> "$OUT"
if [ -x "$SRC/install.sh" ]; then
  "$SRC/install.sh" --prefix=/opt/rust-1.99/tc --disable-ldconfig >> "$OUT" 2>&1
  echo "install: $?" >> "$OUT"
fi
/opt/rust-1.99/tc/bin/rustc --version >> "$OUT" 2>&1
echo DONE >> "$OUT"
