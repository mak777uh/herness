#!/usr/bin/env bash
# Verus: распакован через Windows (в WSL нет unzip). Ставим и проверяем.
OUT=/mnt/c/111/herness/work/verus2.txt
: > "$OUT"

echo '=== 1. Копирование' >> "$OUT"
rm -rf /opt/verus
mkdir -p /opt/verus >> "$OUT" 2>&1
cp -r /mnt/c/111/herness/work/verus-extract/verus-x86-linux/* /opt/verus/ >> "$OUT" 2>&1
echo "cp: $?" >> "$OUT"
ls /opt/verus >> "$OUT" 2>&1

echo '=== 2. Права' >> "$OUT"
chmod +x /opt/verus/verus /opt/verus/rust_verify /opt/verus/z3 /opt/verus/cargo-verus >> "$OUT" 2>&1
ln -sf /opt/verus/verus /usr/local/bin/verus >> "$OUT" 2>&1

echo '=== 3. Проверка' >> "$OUT"
verus --version >> "$OUT" 2>&1
echo "версия: $?" >> "$OUT"
echo DONE >> "$OUT"
