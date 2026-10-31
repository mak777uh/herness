#!/usr/bin/env bash
# Проверка: работает ли наше ядро в пустом корне, где нет ни одного пакета дистрибутива.
set -u
CORE=/home/ilya/work/herness/core-rs/target/x86_64-unknown-linux-musl/release/hs-core
ROOT=/tmp/miniroot

rm -rf "$ROOT"
mkdir -p "$ROOT"

cp "$CORE" "$ROOT/hs-core"
printf 'гипотеза: минимум\n## Seal\nпечать\n' > "$ROOT/method.md"

echo "--- что лежит в корне ---"
ls -la "$ROOT" | grep -v '^\\.\\.$'

echo "--- запуск в пустом корне (chroot) ---"
chroot "$ROOT" /hs-core seal /method.md
echo "код: $?"

echo "--- то же через Python-эталон ---"
python3 - <<'PY'
import sys
sys.path.insert(0, '/mnt/c/111/herness')
from bin.seal import digest
from pathlib import Path
print(digest(Path('/tmp/miniroot/method.md')))
PY
