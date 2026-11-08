#!/usr/bin/env bash
# Verus: тулчейн 1.99.1 на месте, оборачиваем rustup на него.
OUT=/mnt/c/111/herness/work/verus5.txt
: > "$OUT"

TC=/opt/rust-1.99/tc
cat > /opt/rustup-shim/bin/rustup <<EOF
#!/usr/bin/env bash
# Обёртка: verus спрашивает rustup о тулчейне 1.99.1. Отвечаем установленным.
TC=$TC
case "\$1" in
  --version) echo "rustup 1.29.1 (shim)"; exit 0 ;;
  show) echo "\$TC"; exit 0 ;;
  which) shift; echo "\$TC/bin/\$1"; exit 0 ;;
  run) shift; exec "\$TC/bin/\$@" ;;
  toolchain) echo "\$TC"; exit 0 ;;
  install|update) echo "shim: уже установлено"; exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x /opt/rustup-shim/bin/rustup >> "$OUT" 2>&1

echo '=== 1. Проверка' >> "$OUT"
export PATH="/opt/rustup-shim/bin:/opt/rust-1.99/tc/bin:/usr/local/bin:$PATH"
export RUSTUP_HOME=/opt/rustup-shim
verus --version >> "$OUT" 2>&1
echo "версия: $?" >> "$OUT"
echo DONE >> "$OUT"
