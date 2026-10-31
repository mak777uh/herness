#!/usr/bin/env bash
# Проверяем доступность ядра Alpine и наличие инструментов для initramfs.
set -u
for url in \
  "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/netboot/vmlinuz-lts" \
  "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/netboot/vmlinuz-lts" \
  "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/netboot/initramfs-lts"
do
  code=$(curl -s -o /dev/null -w '%{http_code}' -I "$url")
  echo "$code  $url"
done
echo "--- инструменты ---"
for tool in cpio gzip qemu-system-x86_64; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "есть: $tool"
  else
    echo "НЕТ: $tool"
  fi
done
