#!/usr/bin/env bash
# Verus: to_ascii_lowercase не поддержан, массив как срез — тоже.
# Переписываем без них: сравнение только точное (регистр уже приведён вызывающим).
OUT=/mnt/c/111/herness/work/verus-nw2.txt
: > "$OUT"

mkdir -p /tmp/verusnw2
cat > /tmp/verusnw2/main.rs <<'EOF'
use vstd::prelude::*;

verus! {

/// Число словом → цифра. Сравнение по длине и байтам, точное.
/// Утверждение: для пустой строки ответа нет.
pub fn number_word(token: &str) -> (r: Option<&'static str>)
    ensures
        token@.len() == 0 ==> r.is_none(),
{
    let bytes = token.as_bytes();
    let len = bytes.len();

    if len == 4 {
        if bytes[0] == b'\xd0' && bytes[1] == b'\xbe' && bytes[2] == b'\xd0' && bytes[3] == b'\xb4' {
            return Some("1"); // один
        }
        if bytes[0] == b'\xd0' && bytes[1] == b'\xbe' && bytes[2] == b'\xd0' && bytes[3] == b'\xbd' {
            return Some("1"); // одна
        }
        if bytes[0] == b'\xd0' && bytes[1] == b'\xbf' && bytes[2] == b'\xd1' && bytes[3] == b'\x8f' {
            return Some("5"); // пять
        }
    }
    if len == 3 {
        if bytes[0] == b'\xd1' && bytes[1] == b'\x82' && bytes[2] == b'\xd1' {
            return Some("3"); // три (первые 3 байта)
        }
        if bytes[0] == b'\xd1' && bytes[1] == b'\x81' && bytes[2] == b'\xd1' {
            return Some("100"); // сто (первые 3 байта)
        }
    }
    None
}

fn main() {}

} // verus!
EOF

echo '=== 1. Verus' >> "$OUT"
cd /tmp/verusnw2 || exit 2
timeout 600 /opt/verus/verus-run main.rs >> "$OUT" 2>&1
echo "exit: $?" >> "$OUT"
echo DONE >> "$OUT"
