#!/usr/bin/env bash
# Verus: замена Kani. Главное отличие — Verus умеет рассуждать о строках
# (vstd::string, is_ascii, substring_ascii), а Kani на to_lowercase упирается в цикл.
OUT=/mnt/c/111/herness/work/verus.txt
: > "$OUT"

echo '=== 1. Распаковка' >> "$OUT"
rm -rf /opt/verus
mkdir -p /opt/verus >> "$OUT" 2>&1
cd /opt/verus || exit 2
unzip -q /mnt/c/111/herness/work/verus.zip >> "$OUT" 2>&1
echo "unzip: $?" >> "$OUT"
ls /opt/verus >> "$OUT" 2>&1

echo '=== 2. Что внутри' >> "$OUT"
find /opt/verus -maxdepth 2 -name "verus" -type f >> "$OUT" 2>&1
find /opt/verus -maxdepth 2 -name "*.sh" >> "$OUT" 2>&1

echo '=== 3. Проверка' >> "$OUT"
V=$(find /opt/verus -maxdepth 3 -type f -name verus | head -1)
echo "verus: $V" >> "$OUT"
if [ -n "$V" ]; then
  chmod +x "$V" >> "$OUT" 2>&1
  "$V" --version >> "$OUT" 2>&1
fi
echo DONE >> "$OUT"
