#!/usr/bin/env bash
# Проверка: статический бинарник ядра работает без окружения и совпадает с Python по байтам.
set -u
cd "$HOME/work/herness/core-rs" || exit 1
B=target/x86_64-unknown-linux-musl/release/hs-core

echo "--- что за файл ---"
file "$B" | cut -c1-100
echo "--- размер ---"
stat -c '%s байт' "$B"

printf 'тело\n## Seal\nпечать\n' > /tmp/t.md
echo "--- Rust при пустом окружении ---"
env -i "$B" seal /tmp/t.md

echo "--- Python ---"
python3 - <<'PY'
import sys
sys.path.insert(0, '/mnt/c/111/herness')
from bin.seal import digest
from pathlib import Path
print(digest(Path('/tmp/t.md')))
PY

echo "--- динамические зависимости ---"
ldd "$B" 2>&1 | head -2

echo "--- запуск в новом namespace (mount+pid) ---"
unshare -m -p -f --mount-proc "$B" seal /tmp/t.md 2>&1 | head -3
