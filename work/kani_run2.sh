#!/usr/bin/env bash
# Kani не находит librustc_driver: нужен LD_LIBRARY_PATH на nightly-тулчейн.
OUT=/mnt/c/111/herness/work/kani-run2.txt
: > "$OUT"

export PATH="/opt/rust-nightly/tc/bin:/opt/kani/kani-0.68.0/bin:$PATH"
export KANI_HOME=/opt/kani/kani-0.68.0
# Библиотеки rustc лежат в lib/ тулчейна.
export LD_LIBRARY_PATH="/opt/rust-nightly/tc/lib:/opt/rust-nightly/tc/lib/rustlib/x86_64-unknown-linux-gnu/lib:$LD_LIBRARY_PATH"

echo '=== 1. Где librustc_driver' >> "$OUT"
find /opt/rust-nightly/tc -name "librustc_driver*" 2>/dev/null | head -3 >> "$OUT"

echo '=== 2. Kani' >> "$OUT"
cd /tmp/kanicheck || exit 2
for h in number_word_never_panics normalize_token_never_panics resource_matches_never_panics deny_outside_prefix; do
  echo "--- $h" >> "$OUT"
  kani src/main.rs --harness "$h" >> "$OUT" 2>&1
  echo "$h: $?" >> "$OUT"
done
echo DONE >> "$OUT"
