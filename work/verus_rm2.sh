#!/usr/bin/env bash
# Verus на resource_matches: без strip_suffix и starts_with (их нет в vstd).
# Переписываем на сравнение байтов.
OUT=/mnt/c/111/herness/work/verus-rm2.txt
: > "$OUT"

mkdir -p /tmp/verusrm2
cat > /tmp/verusrm2/main.rs <<'EOF'
use vstd::prelude::*;

verus! {

/// Сравнение ресурса с шаблоном: литерально, без «любого хвоста» (F-0072).
/// Утверждение: точный шаблон совпадает только с равным ресурсом.
pub fn resource_matches(pattern: &str, resource: &str) -> (r: bool)
    ensures
        // Точный шаблон (без звёздочек) совпадает только при равенстве.
        // Точный шаблон: без звёздочек и не «**».
        (forall|i: int| 0 <= i < pattern@.len() ==> pattern@[i] != '*')
            ==> (r == (pattern@ =~= resource@)),
        // Шаблон «**» совпадает со всем.
        (pattern@ =~= "**"@) ==> r,
{
    let p = pattern.as_bytes();
    let r = resource.as_bytes();

    // Шаблон «**» совпадает со всем.
    if p.len() == 2 && p[0] == b'*' && p[1] == b'*' {
        return true;
    }

    // Шаблон «.../**»: совпадает с префиксом или префиксом со слэшем.
    if p.len() >= 3
        && p[p.len() - 3] == b'/'
        && p[p.len() - 2] == b'*'
        && p[p.len() - 1] == b'*'
    {
        let prefix_len = p.len() - 3;
        if r.len() == prefix_len {
            let mut i: usize = 0;
            let mut same: bool = true;
            while i < prefix_len
                invariant
                    i <= prefix_len,
                    prefix_len < p.len(),
                    r.len() == prefix_len,
                decreases prefix_len - i,
            {
                if p[i] != r[i] {
                    same = false;
                    break;
                }
                i = i + 1;
            }
            if same {
                return true;
            }
        }
        if r.len() == prefix_len + 1 {
            let mut i: usize = 0;
            let mut same: bool = true;
            while i < prefix_len
                invariant
                    i <= prefix_len,
                    prefix_len < p.len(),
                    r.len() == prefix_len + 1,
                decreases prefix_len - i,
            {
                if p[i] != r[i] {
                    same = false;
                    break;
                }
                i = i + 1;
            }
            if same && r[prefix_len] == b'/' {
                return true;
            }
        }
        return false;
    }

    // Точное сравнение.
    if p.len() != r.len() {
        return false;
    }
    let mut i: usize = 0;
    while i < p.len()
        invariant
            i <= p.len(),
            p.len() == r.len(),
        decreases p.len() - i,
    {
        if p[i] != r[i] {
            return false;
        }
        i = i + 1;
    }
    true
}

fn main() {}

} // verus!
EOF

echo '=== 1. Verus' >> "$OUT"
cd /tmp/verusrm2 || exit 2
timeout 600 /opt/verus/verus-run main.rs >> "$OUT" 2>&1
echo "exit: $?" >> "$OUT"
echo DONE >> "$OUT"
