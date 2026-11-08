#!/usr/bin/env bash
# Verus на resource_matches: добавляем assume_specification для starts_with.
OUT=/mnt/c/111/herness/work/verus-rm.txt
: > "$OUT"

mkdir -p /tmp/verusrm
cat > /tmp/verusrm/main.rs <<'EOF'
use vstd::prelude::*;

verus! {

// Verus не знает спецификации starts_with: объявляем её как аксиому.
// Это доверенное предположение, и оно названо явно.
// starts_with обобщён по Pattern: спецификацию даём для частного случая &str.
// Вместо assume_specification используем обёртку с постусловием.
fn starts_with_str(s: &str, prefix: &str) -> (r: bool)
    ensures
        r == (s@.len() >= prefix@.len() && s@.subrange(0, prefix@.len() as int) =~= prefix@),
{
    s.starts_with(prefix)
}

/// Сравнение ресурса с шаблоном: литерально, без «любого хвоста» (F-0072).
pub fn resource_matches(pattern: &str, resource: &str) -> (r: bool)
    ensures
        // Точный шаблон совпадает только с равным ресурсом.
        (pattern@ != "**"@ && !pattern@.contains('/') && !pattern@.contains('*')) ==> (r == (pattern@ =~= resource@)),
{
    if pattern == "**" {
        return true;
    }
    if let Some(prefix) = pattern.strip_suffix("/**") {
        return resource == prefix || starts_with_str(resource, &format!("{prefix}/"));
    }
    pattern == resource
}

fn main() {}

} // verus!
EOF

echo '=== 1. Verus' >> "$OUT"
cd /tmp/verusrm || exit 2
timeout 600 /opt/verus/verus-run main.rs >> "$OUT" 2>&1
echo "exit: $?" >> "$OUT"
echo DONE >> "$OUT"
