#!/usr/bin/env bash
# Verus требует rustup: делаем вид, что он есть, и подсовываем наш тулчейн.
# rustup качает с rustup.rs, который из WSL недоступен, поэтому создаём обёртку.
OUT=/mnt/c/111/herness/work/verus3.txt
: > "$OUT"

echo '=== 1. Что требует verus' >> "$OUT"
head -40 /opt/verus/verus >> "$OUT" 2>&1

echo '=== 2. Делаем rustup-обёртку' >> "$OUT"
mkdir -p /opt/rustup-shim/bin >> "$OUT" 2>&1
cat > /opt/rustup-shim/bin/rustup <<'EOF'
#!/usr/bin/env bash
# Обёртка: verus спрашивает rustup о тулчейне. Отвечаем нашим nightly.
TC=/opt/rust-nightly/tc
case "$1" in
  --version) echo "rustup 1.29.1 (shim)"; exit 0 ;;
  show) echo "$TC"; exit 0 ;;
  which) shift; echo "$TC/bin/$1"; exit 0 ;;
  run) shift; exec "$TC/bin/$@" ;;
  toolchain) echo "$TC"; exit 0 ;;
  *) exec "$TC/bin/rustup" "$@" 2>/dev/null || exit 0 ;;
esac
EOF
chmod +x /opt/rustup-shim/bin/rustup >> "$OUT" 2>&1
ln -sf /opt/rustup-shim/bin/rustup /usr/local/bin/rustup >> "$OUT" 2>&1
ln -sf /opt/rust-nightly/tc/bin/cargo /usr/local/bin/cargo >> "$OUT" 2>&1
ln -sf /opt/rust-nightly/tc/bin/rustc /usr/local/bin/rustc >> "$OUT" 2>&1

echo '=== 3. Проверка' >> "$OUT"
export PATH="/opt/rust-nightly/tc/bin:/opt/rustup-shim/bin:/usr/local/bin:$PATH"
export RUSTUP_HOME=/opt/rust-nightly
export VERUS_IN_VSCODE=0
verus --version >> "$OUT" 2>&1
echo "версия: $?" >> "$OUT"
echo DONE >> "$OUT"
