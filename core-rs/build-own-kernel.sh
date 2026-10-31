#!/usr/bin/env bash
# Своя минимальная сборка ядра 6.18.60: tinyconfig + только то, что нужно харнессу.
set -eu
cd /root
if [ ! -f linux.tar.xz ]; then
  wget -q https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.18.60.tar.xz -O linux.tar.xz
fi
echo "исходник: $(stat -c %s linux.tar.xz) байт"

rm -rf linux-6.18.60
tar -xf linux.tar.xz
cd linux-6.18.60

echo "--- конфиг: tinyconfig + необходимое ---"
make -s tinyconfig
for opt in \
  CONFIG_64BIT=y \
  CONFIG_X86_64=y \
  CONFIG_PRINTK=y \
  CONFIG_BINFMT_ELF=y \
  CONFIG_BINFMT_SCRIPT=n \
  CONFIG_MULTIUSER=y \
  CONFIG_TTY=y \
  CONFIG_SERIAL_8250=y \
  CONFIG_SERIAL_8250_CONSOLE=y \
  CONFIG_BLK_DEV_INITRD=y \
  CONFIG_RD_GZIP=y \
  CONFIG_SECURITY=y \
  CONFIG_SECURITY_LANDLOCK=y \
  CONFIG_SECCOMP=y \
  CONFIG_PROC_FS=y \
  CONFIG_SYSFS=y \
  CONFIG_SMP=n \
  CONFIG_MODULES=n \
  CONFIG_DEBUG_INFO=n
do
  ./scripts/config --set-val "${opt%%=*}" "${opt##*=}" 2>/dev/null || \
    ./scripts/config --enable "${opt%%=*}"
done
make -s olddefconfig

echo "--- сборка ---"
make -s -j"$(nproc)" bzImage 2>&1 | tail -3

ls -l arch/x86/boot/bzImage | awk '{print "bzImage:", $5, "байт"}'
echo "включённых опций (=y): $(grep -c '=y' .config)"
echo "модулей (=m): $(grep -c '=m' .config)"
cp arch/x86/boot/bzImage /mnt/c/111/herness/core-rs/boot/vmlinuz-own-6.18.60
echo "скопировано в Windows"
