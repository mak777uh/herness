#!/usr/bin/env bash
# Своя минимальная система: ядро Linux + наш статический бинарник как PID 1.
# Ни дистрибутива, ни sh, ни libc-пакетов внутри образа нет.
set -eu
WORK="$HOME/work/boot"
KERNEL_URL="https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/netboot/vmlinuz-lts"

mkdir -p "$WORK/rootfs"
cd "$WORK"

if [ ! -f vmlinuz-lts ]; then
  echo "--- качаю ядро ---"
  curl -sS -o vmlinuz-lts "$KERNEL_URL"
fi
ls -l vmlinuz-lts | awk '{print "ядро:", $5, "байт"}'

echo "--- собираю наш бинарник в режиме init ---"
cd /home/ilya/work/herness/core-rs
cp /mnt/c/111/herness/core-rs/src/main.rs src/main.rs
~/.cargo/bin/cargo build --release --target x86_64-unknown-linux-musl 2>&1 | tail -1

ROOTFS="$WORK/rootfs"
rm -rf "$ROOTFS"
mkdir -p "$ROOTFS"
cp target/x86_64-unknown-linux-musl/release/hs-core "$ROOTFS/init"
printf 'гипотеза: система из ядра и харнесса\n## Seal\nпечать\n' > "$ROOTFS/method.md"
echo "--- содержимое образа ---"
ls -l "$ROOTFS" | grep -v '^total' | awk '{print $5, $9}'

cd "$ROOTFS"
find . -print0 | cpio --null -o -H newc 2>/dev/null | gzip -9 > "$WORK/initramfs.cpio.gz"
cd "$WORK"
echo "образ: $(stat -c '%s' initramfs.cpio.gz) байт"
