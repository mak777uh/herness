#!/usr/bin/env bash
# Проверка: какие опции закалки приняты ядром после olddefconfig.
cd /root/linux-6.18.60 || exit 2
OUT=/mnt/c/111/herness/work/check4.txt
: > "$OUT"
for o in X86_SMEP X86_SMAP RANDOMIZE_BASE SLAB_FREELIST_RANDOM SLAB_FREELIST_HARDENED \
         RANDOM_KMALLOC_CACHES SECURITY_PERF_EVENTS_RESTRICT RANDOMIZE_KSTACK_OFFSET \
         MITIGATION_PAGE_TABLE_ISOLATION STACKPROTECTOR_STRONG DEBUG_LIST STATIC_USERMODEHELPER; do
  line=$(grep -E "^CONFIG_${o}=" .config || true)
  if [ -z "$line" ]; then
    printf '%s: НЕТ\n' "$o" >> "$OUT"
  else
    printf '%s\n' "$line" >> "$OUT"
  fi
done
printf 'DONE\n' >> "$OUT"
