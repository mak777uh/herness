#!/usr/bin/env bash
# Verus: rustup-обёртка должна понимать `run <toolchain> <cmd> <args>`.
# Verus вызывает: rustup run 1.99.1-x86_64-unknown-linux-gnu rustc ...
OUT=/mnt/c/111/herness/work/verus6.txt
: > "$OUT"

TC=/opt/rust-1.99/tc
cat > /opt/rustup-shim/bin/rustup <<EOF
#!/usr/bin/env bash
# Обёртка rustup для Verus: единственный тулчейн — $TC.
TC=$TC
case "\$1" in
  --version) echo "rustup 1.29.1 (shim)"; exit 0 ;;
  show)
    echo "Default host: x86_64-unknown-linux-gnu"
    echo "rustup home:  /opt/rustup-shim"
    echo ""
    echo "installed toolchains"
    echo "--------------------"
    echo "1.99.1-x86_64-unknown-linux-gnu (default)"
    exit 0 ;;
  default) echo "1.99.1-x86_64-unknown-linux-gnu (default)"; exit 0 ;;
  which)
    shift
    [ "\$1" = "1.99.1-x86_64-unknown-linux-gnu" ] && shift
    echo "\$TC/bin/\$1"
    exit 0 ;;
  run)
    shift
    # Первый аргумент — имя тулчейна, его пропускаем.
    [ "\$1" = "1.99.1-x86_64-unknown-linux-gnu" ] && shift
    exec "\$TC/bin/\$@"
    ;;
  toolchain) echo "\$TC"; exit 0 ;;
  install|update) echo "shim: уже установлено"; exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x /opt/rustup-shim/bin/rustup >> "$OUT" 2>&1

echo '=== 1. Проверка обёртки' >> "$OUT"
export PATH="/opt/rustup-shim/bin:/opt/rust-1.99/tc/bin:/usr/local/bin:$PATH"
export RUSTUP_HOME=/opt/rustup-shim
rustup run 1.99.1-x86_64-unknown-linux-gnu rustc --version >> "$OUT" 2>&1
echo "run: $?" >> "$OUT"

echo '=== 2. Verus' >> "$OUT"
verus --version >> "$OUT" 2>&1
echo "версия: $?" >> "$OUT"
echo DONE >> "$OUT"
