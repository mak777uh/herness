#!/usr/bin/env bash
# Verus: обёртка rustup. Пишем файл через cat с одинарными кавычками (без подстановок),
# путь к тулчейну передаём через переменную окружения.
OUT=/mnt/c/111/herness/work/verus8.txt
: > "$OUT"

cat > /opt/rustup-shim/bin/rustup <<'SHIM'
#!/usr/bin/env bash
# Обёртка rustup для Verus: единственный тулчейн — тот, что в VERUS_TC.
TC="${VERUS_TC:-/opt/rust-1.99/tc}"
TCNAME=1.99.1-x86_64-unknown-linux-gnu

case "$1" in
  --version)
    echo "rustup 1.29.1 (shim)"
    exit 0
    ;;
  show)
    printf 'Default host: x86_64-unknown-linux-gnu\nrustup home:  /opt/rustup-shim\n\ninstalled toolchains\n--------------------\n%s (default)\n' "$TCNAME"
    exit 0
    ;;
  default)
    echo "$TCNAME (default)"
    exit 0
    ;;
  toolchain)
    shift
    if [ "$1" = "list" ]; then
      printf '%s (default)\n' "$TCNAME"
    else
      echo "$TCNAME"
    fi
    exit 0
    ;;
  which)
    shift
    [ "$1" = "$TCNAME" ] && shift
    echo "$TC/bin/$1"
    exit 0
    ;;
  run)
    shift
    [ "$1" = "$TCNAME" ] && shift
    [ "$1" = "--" ] && shift
    exec "$TC/bin/$@"
    ;;
  install|update|component|target)
    echo "shim: уже установлено"
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
SHIM
chmod +x /opt/rustup-shim/bin/rustup >> "$OUT" 2>&1

echo '=== 1. Формы вызова' >> "$OUT"
export PATH="/opt/rustup-shim/bin:/opt/rust-1.99/tc/bin:/usr/local/bin:$PATH"
export RUSTUP_HOME=/opt/rustup-shim
export VERUS_TC=/opt/rust-1.99/tc
rustup run 1.99.1-x86_64-unknown-linux-gnu rustc --version >> "$OUT" 2>&1
echo "run: $?" >> "$OUT"
rustup run 1.99.1-x86_64-unknown-linux-gnu -- rustc --version >> "$OUT" 2>&1
echo "run--: $?" >> "$OUT"
rustup toolchain list >> "$OUT" 2>&1

echo '=== 2. Verus' >> "$OUT"
verus --version >> "$OUT" 2>&1
echo "версия: $?" >> "$OUT"
echo DONE >> "$OUT"
