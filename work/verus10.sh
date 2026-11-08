#!/usr/bin/env bash
# Verus: rust_verify — rustc-плагин, ему нужны библиотеки тулчейна 1.99.1.
OUT=/mnt/c/111/herness/work/verus10.txt
: > "$OUT"

cat > /opt/verus/verus-run <<'WRAP'
#!/usr/bin/env bash
# Обёртка: выставляет окружение и запускает verus.
export PATH="/opt/rustup-shim/bin:/opt/rust-1.99/tc/bin:/opt/verus:/usr/local/bin:$PATH"
export RUSTUP_HOME=/opt/rustup-shim
export VERUS_TC=/opt/rust-1.99/tc
export LD_LIBRARY_PATH="/opt/rust-1.99/tc/lib:/opt/rust-1.99/tc/lib/rustlib/x86_64-unknown-linux-gnu/lib:$LD_LIBRARY_PATH"
export VERUS_Z3_PATH=/opt/verus/z3
exec /opt/verus/verus "$@"
WRAP
chmod +x /opt/verus/verus-run >> "$OUT" 2>&1
ln -sf /opt/verus/verus-run /usr/local/bin/verus >> "$OUT" 2>&1

echo '=== 1. Версия' >> "$OUT"
/opt/verus/verus-run --version >> "$OUT" 2>&1
echo "версия: $?" >> "$OUT"
echo DONE >> "$OUT"
