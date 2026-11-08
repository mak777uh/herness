#!/usr/bin/env bash
# Kani: релиз скачан через Windows (в WSL crates.io недоступен).
OUT=/mnt/c/111/herness/work/kani3.txt
: > "$OUT"

echo '=== 1. Распаковка' >> "$OUT"
mkdir -p /opt/kani >> "$OUT" 2>&1
tar -xzf /mnt/c/111/herness/work/kani-0.68.0-x86_64-unknown-linux-gnu.tar.gz -C /opt/kani >> "$OUT" 2>&1
echo "tar: $?" >> "$OUT"
ls /opt/kani >> "$OUT" 2>&1

echo '=== 2. Что внутри' >> "$OUT"
find /opt/kani -maxdepth 2 -name "kani*" >> "$OUT" 2>&1
find /opt/kani -maxdepth 3 -name "cbmc*" >> "$OUT" 2>&1

echo '=== 3. Проверка' >> "$OUT"
KANI=$(find /opt/kani -maxdepth 3 -type f -name kani | head -1)
echo "kani: $KANI" >> "$OUT"
if [ -n "$KANI" ]; then
  chmod +x "$KANI" >> "$OUT" 2>&1
  "$KANI" --version >> "$OUT" 2>&1
fi
echo DONE >> "$OUT"
