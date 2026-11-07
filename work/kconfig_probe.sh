#!/usr/bin/env bash
# Почему часть опций закалки не принята: ищем их определения в Kconfig и зависимости.
cd /root/linux-6.18.60 || exit 2
OUT=/mnt/c/111/herness/work/kconfig2.txt
: > "$OUT"
for o in X86_SMEP X86_SMAP RANDOMIZE_BASE SLAB_FREELIST_RANDOM SLAB_FREELIST_HARDENED \
         RANDOM_KMALLOC_CACHES SECURITY_PERF_EVENTS_RESTRICT; do
  printf '=== %s\n' "$o" >> "$OUT"
  grep -rn -A6 "^config $o\$" arch/ mm/ security/ kernel/ init/ 2>/dev/null >> "$OUT"
done
printf 'DONE\n' >> "$OUT"
