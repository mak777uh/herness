#!/usr/bin/env bash
# Проверка SMEP/SMAP на живой комнате: это не опция конфига, а флаг процессора.
cd /root/linux-6.18.60 || exit 2
OUT=/mnt/c/111/herness/work/cpu-flags.txt
: > "$OUT"

echo '=== SMEP/SMAP в исходниках: как включаются' >> "$OUT"
sed -n '366,385p' arch/x86/kernel/cpu/common.c >> "$OUT"

echo '=== есть ли в сборке код, включающий SMEP' >> "$OUT"
grep -c 'X86_CR4_SMEP' arch/x86/kernel/cpu/common.c >> "$OUT"
grep -c 'X86_CR4_SMAP' arch/x86/kernel/cpu/common.c >> "$OUT"

echo '=== что видит QEMU: флаги CPU хоста' >> "$OUT"
grep -m1 'model name' /proc/cpuinfo >> "$OUT"
grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(smep|smap)$' >> "$OUT" || echo 'нет smep/smap в WSL' >> "$OUT"
echo DONE >> "$OUT"
