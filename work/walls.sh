#!/usr/bin/env bash
# Итог: какие стены можно включить, а какие нельзя и почему.
# SMEP/SMAP в этой версии ядра не опции конфига — они включаются автоматически, если CPU умеет.
cd /root/linux-6.18.60 || exit 2
OUT=/mnt/c/111/herness/work/walls-final.txt
: > "$OUT"

echo '=== SMEP/SMAP: это не опции конфига, а проверка CPU' >> "$OUT"
grep -rn 'cr4_set_bits.*SMEP\|X86_CR4_SMEP\|setup_smep' arch/x86/kernel/cpu/common.c 2>/dev/null | head -4 >> "$OUT"
grep -rn 'X86_FEATURE_SMEP\|X86_FEATURE_SMAP' arch/x86/include/asm/cpufeatures.h 2>/dev/null | head -3 >> "$OUT"

echo '=== SLUB_TINY отключает рандомизацию кучи: выключаем' >> "$OUT"
sed -i 's/^CONFIG_SLUB_TINY=y/# CONFIG_SLUB_TINY is not set/' .config
for o in SLAB_FREELIST_RANDOM SLAB_FREELIST_HARDENED RANDOM_KMALLOC_CACHES; do
  sed -i "s/^# CONFIG_${o} is not set/CONFIG_${o}=y/" .config
  grep -q "^CONFIG_${o}=" .config || echo "CONFIG_${o}=y" >> .config
done

echo '=== RELOCATABLE и KASLR' >> "$OUT"
sed -i 's/^# CONFIG_RELOCATABLE is not set/CONFIG_RELOCATABLE=y/' .config
grep -q '^CONFIG_RELOCATABLE=' .config || echo 'CONFIG_RELOCATABLE=y' >> .config
sed -i 's/^# CONFIG_RANDOMIZE_BASE is not set/CONFIG_RANDOMIZE_BASE=y/' .config
grep -q '^CONFIG_RANDOMIZE_BASE=' .config || echo 'CONFIG_RANDOMIZE_BASE=y' >> .config

echo '=== PERF_EVENTS_RESTRICT: в этой версии нет опции, есть sysctl' >> "$OUT"
grep -rn 'perf_event_paranoid' kernel/events/core.c 2>/dev/null | head -2 >> "$OUT"

make -s olddefconfig >> "$OUT" 2>&1
echo '=== после olddefconfig' >> "$OUT"
for o in SLUB_TINY SLAB_FREELIST_RANDOM SLAB_FREELIST_HARDENED RANDOM_KMALLOC_CACHES RELOCATABLE RANDOMIZE_BASE; do
  printf '%s: ' "$o" >> "$OUT"
  grep -E "^CONFIG_${o}=" .config >> "$OUT" || echo 'НЕТ' >> "$OUT"
done
echo DONE >> "$OUT"
