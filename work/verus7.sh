#!/usr/bin/env bash
# Verus проверяет тулчейн через `rustup run <tc> rustc --version` и `rustup toolchain list`.
# Наша обёртка должна отвечать на ВСЕ формы, включая `run --` и `toolchain list`.
OUT=/mnt/c/111/herness/work/verus7.txt
: > "$OUT"

TC=/opt/rust-1.99/tc
cat > /opt/rustup-shim/bin/rustup <<EOF
#!/usr/bin/env bash
# Обёртка rustup для Verus: единственный тулчейн — 1.99.1.
TC=$TC
TCNAME=1.99.1-x86_64-unknown-linux-gnu

strip_tc() {
  # Пропускаем имя тулчейна и ведущие дефисы.
  while [ \$# -gt 0 ]; do
    case "\$1" in
      "\$TCNAME"|--|--) shift ;;
      *) break ;;
    esac
  done
}

case "\$1" in
  --version) echo "rustup 1.29.1 (shim)"; exit 0 ;;
  show)
    printf 'Default host: x86_64-unknown-linux-gnu\nrustup home:  /opt/rustup-shim\n\ninstalled toolchains\n--------------------\n%s (default)\n' "\$TCNAME"
    exit 0 ;;
  default) echo "\$TCNAME (default)"; exit 0 ;;
  toolchain)
    shift
    case "\$1" in
      list) printf '%s (default)\n' "\$TCNAME"; exit 0 ;;
      *) echo "\$TCNAME"; exit 0 ;;
    esac ;;
  which)
    shift; strip_tc; echo "\$TC/bin/\$1"; exit 0 ;;
  run)
    shift; strip_tc; exec "\$TC/bin/\$@" ;;
  install|update|component|target) echo "shim: уже установлено"; exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x /opt/rustup-shim/bin/rustup >> "$OUT" 2>&1

echo '=== 1. Формы вызова' >> "$OUT"
export PATH="/opt/rustup-shim/bin:/opt/rust-1.99/tc/bin:/usr/local/bin:$PATH"
export RUSTUP_HOME=/opt/rustup-shim
rustup run 1.99.1-x86_64-unknown-linux-gnu rustc --version >> "$OUT" 2>&1
rustup run 1.99.1-x86_64-unknown-linux-gnu -- rustc --version >> "$OUT" 2>&1
rustup toolchain list >> "$OUT" 2>&1
rustup which rustc >> "$OUT" 2>&1

echo '=== 2. Verus' >> "$OUT"
verus --version >> "$OUT" 2>&1
echo "версия: $?" >> "$OUT"
echo DONE >> "$OUT"
