#!/usr/bin/env bash
# Kani распакован: bin/kani-driver — это и есть kani. Проверяем и настраиваем.
OUT=/mnt/c/111/herness/work/kani4.txt
: > "$OUT"

KANI_ROOT=/opt/kani/kani-0.68.0
echo '=== 1. Версия' >> "$OUT"
chmod +x "$KANI_ROOT"/bin/* >> "$OUT" 2>&1
"$KANI_ROOT/bin/kani-driver" --version >> "$OUT" 2>&1
echo "версия: $?" >> "$OUT"

echo '=== 2. CBMC' >> "$OUT"
"$KANI_ROOT/bin/cbmc" --version >> "$OUT" 2>&1

echo '=== 3. Нужен rustc той же версии' >> "$OUT"
cat "$KANI_ROOT/rust-toolchain-version" >> "$OUT" 2>&1
cat "$KANI_ROOT/rustc-version" >> "$OUT" 2>&1

echo '=== 4. Симлинк в PATH' >> "$OUT"
ln -sf "$KANI_ROOT/bin/kani-driver" /usr/local/bin/kani >> "$OUT" 2>&1
ln -sf "$KANI_ROOT/bin/cbmc" /usr/local/bin/cbmc >> "$OUT" 2>&1
ln -sf "$KANI_ROOT/bin/kani-compiler" /usr/local/bin/kani-compiler >> "$OUT" 2>&1
kani --version >> "$OUT" 2>&1
echo DONE >> "$OUT"
