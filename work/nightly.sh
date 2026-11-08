#!/usr/bin/env bash
# Nightly-тулчейн для Kani: скачан через Windows, ставим install.sh.
OUT=/mnt/c/111/herness/work/nightly.txt
: > "$OUT"

echo '=== 1. Распаковка' >> "$OUT"
mkdir -p /opt/rust-nightly >> "$OUT" 2>&1
tar -xJf /mnt/c/111/herness/work/rust-nightly.tar.xz -C /opt/rust-nightly >> "$OUT" 2>&1
echo "tar: $?" >> "$OUT"
ls /opt/rust-nightly >> "$OUT" 2>&1

echo '=== 2. install.sh' >> "$OUT"
SRC=$(ls -d /opt/rust-nightly/rust-nightly* 2>/dev/null | head -1)
echo "src: $SRC" >> "$OUT"
if [ -x "$SRC/install.sh" ]; then
  "$SRC/install.sh" --prefix=/opt/rust-nightly/tc --disable-ldconfig >> "$OUT" 2>&1
  echo "install: $?" >> "$OUT"
fi

echo '=== 3. Проверка' >> "$OUT"
/opt/rust-nightly/tc/bin/rustc --version >> "$OUT" 2>&1
/opt/rust-nightly/tc/bin/cargo --version >> "$OUT" 2>&1
echo DONE >> "$OUT"
