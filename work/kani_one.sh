#!/usr/bin/env bash
# Kani: создаём проект заново и проверяем один harness.
OUT=/mnt/c/111/herness/work/kani-one.txt
: > "$OUT"

export PATH="/opt/rust-nightly/tc/bin:/opt/kani/kani-0.68.0/bin:$PATH"
export KANI_HOME=/opt/kani/kani-0.68.0
export LD_LIBRARY_PATH="/opt/rust-nightly/tc/lib:/opt/rust-nightly/tc/lib/rustlib/x86_64-unknown-linux-gnu/lib"

echo '=== окружение' >> "$OUT"
kani --version >> "$OUT" 2>&1

echo '=== проект' >> "$OUT"
rm -rf /tmp/kanicheck
mkdir -p /tmp/kanicheck/src
cat > /tmp/kanicheck/src/main.rs <<'EOF'
fn number_word(token: &str) -> Option<&'static str> {
    let lower = token.to_lowercase();
    Some(match lower.as_str() {
        "один" | "одна" | "одно" => "1",
        "два" | "две" => "2",
        "три" => "3",
        "четыре" => "4",
        "пять" => "5",
        "шесть" => "6",
        "семь" => "7",
        "восемь" => "8",
        "девять" => "9",
        "десять" => "10",
        _ => return None,
    })
}

fn main() {}

#[cfg(kani)]
mod proofs {
    use super::*;

    #[kani::proof]
    fn number_word_never_panics() {
        let s: String = kani::any();
        kani::assume(s.len() < 100);
        let _ = number_word(&s);
    }
}
EOF
ls -R /tmp/kanicheck >> "$OUT" 2>&1

echo '=== прогон' >> "$OUT"
cd /tmp/kanicheck || { echo 'нет каталога' >> "$OUT"; exit 2; }
timeout 400 kani src/main.rs --harness number_word_never_panics >> "$OUT" 2>&1
echo "exit: $?" >> "$OUT"
echo DONE >> "$OUT"
