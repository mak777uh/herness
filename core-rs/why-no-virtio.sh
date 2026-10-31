#!/usr/bin/env bash
# Почему VIRTIO не включается: проверяем зависимости символов в 6.18.60.
set -u
cd /root/linux-6.18.60
make -s tinyconfig
echo "--- до ---"
grep -c '^CONFIG_VIRTIO' .config || echo "VIRTIO нет"

./scripts/config --enable CONFIG_PCI
make -s olddefconfig
echo "PCI: $(grep '^CONFIG_PCI=' .config || echo нет)"

./scripts/config --enable CONFIG_VIRTIO
./scripts/config --enable CONFIG_VIRTIO_PCI
./scripts/config --enable CONFIG_VIRTIO_BLK
make -s olddefconfig
echo "--- после olddefconfig ---"
grep '^CONFIG_VIRTIO' .config || echo "VIRTIO всё ещё нет"

echo "--- есть ли символ в Kconfig ---"
grep -rn 'config VIRTIO$' drivers/virtio/Kconfig 2>/dev/null | head -3
grep -rn 'VIRTIO_MENU' drivers/virtio/Kconfig 2>/dev/null | head -3
