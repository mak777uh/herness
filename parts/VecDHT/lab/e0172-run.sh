#!/usr/bin/env bash
# e0172-run.sh — носитель H-0172/E-0172: пин обязан быть предком HEAD, иначе PRE-факты не снимаются.
#
# Почему здесь worktree, а не посадка. Посадка `git checkout $PIN -- <файл>` годится, когда предмет —
# байты продукта. Здесь предмет — ПОВЕДЕНИЕ НОСИТЕЛЕЙ над классом файлов: их число, наличие гейта,
# наличие прибора и реестра, поэтому ветки обязаны отличаться деревом, а не версией одного файла. Пин
# разворачивается отдельным worktree (`git worktree add --detach`), и обе ветки считаются одними и теми
# же счётчиками — функциями `in_scope`/`count_*` из тела этого носителя. Так PRE не «память о прошлом
# прогоне» и не суррогатное дерево, а исполненное измерение над коммитом, который действительно является
# предком HEAD (собственный гейт носителя печатает это до всякого замера).
#
# Урок `E-0167`, ради которого написан этот цикл: замороженное `PRE_FIX_BAD=10` было снято с
# суррогатного пина, собранного `commit-tree` ДО пре-регистрационного коммита, — на настоящем пине тот же
# прибор печатает 9, и круг закрыт `refutes`. Отсюда правило: любое PRE-число замораживается только по
# дереву, предковость которого проверена.
#
# Урок `E-0166` учтён: `grep -c` считает СТРОКИ, поэтому каждое число либо снято счётчиком класса по
# одному файлу, либо сведено к паре 0/1. Отсутствие формы — отдельный названный факт, а не нуль.
set -u
cd "$(dirname "$0")/.."

PIN=$(git log --format=%H --reverse -- lab/hypotheses/H-0172-pin-must-be-ancestor.md | head -1)
E7=lab/e0172-run.sh
O7=lab/e0167-run.sh
PA=lab/check-pin-ancestry.py
EX=lab/pin-ancestry-exceptions.tsv
YML=.github/workflows/verify.yml
WV=lab/workspace-verify.sh
TMP=$(mktemp -d)
WT="$TMP/pin"
: > "$TMP/facts"
trap 'git worktree remove --force "$WT" 2>/dev/null; git worktree prune 2>/dev/null; rm -rf "$TMP"' EXIT

emit() { printf '%s\t%s\n' "$1" "$2" | tee -a "$TMP/facts"; }
bool_rc() { if [ "$1" -eq 0 ]; then echo 0; else echo 1; fi; }
line_val() {
  local v
  v=$(grep "^$2" "$1" 2>/dev/null | head -1 | grep -oE "$3=[0-9]+" | head -1 | cut -d= -f2)
  echo "${v:-0}"
}

# --- собственный гейт: печатается ДО любого замера ---------------------------------------------
emit PIN_FOUND "$(git cat-file -e "$PIN^{commit}" 2>/dev/null && echo 1 || echo 0)"
emit PIN_HASEXPECT "$([ -n "$PIN" ] && [ "$(git log --format=%H --reverse -- lab/expectations/e0172.tsv | head -1)" = "$PIN" ] && echo 1 || echo 0)"
if git merge-base --is-ancestor "$PIN" HEAD 2>/dev/null; then emit PIN_IS_ANCESTOR 1; else emit PIN_IS_ANCESTOR 0; fi

# --- класс носителей (одна и та же функция для обеих веток) ------------------------------------
# В классе тот, кто вычисляет пин (`PIN=`/`pin=` в начале строки) И печатает хоть один PRE-факт.
in_scope() {
  grep -qE '^[[:space:]]*(PIN|pin)=' "$1" 2>/dev/null || return 1
  grep -q 'PRE_FIX_' "$1" 2>/dev/null || return 1
  return 0
}
count_all()   { ls "$1"/lab/e*-run.sh 2>/dev/null | wc -l | tr -d ' '; }
count_scope() { local n=0 f; for f in "$1"/lab/e*-run.sh; do [ -e "$f" ] || continue; in_scope "$f" && n=$((n+1)); done; echo "$n"; }
count_gated() { local n=0 f; for f in "$1"/lab/e*-run.sh; do [ -e "$f" ] || continue; in_scope "$f" && grep -q PIN_IS_ANCESTOR "$f" && n=$((n+1)); done; echo "$n"; }
count_exempt() { local n=0 f; for f in "$1"/lab/e*-run.sh; do [ -e "$f" ] || continue; in_scope "$f" && ! grep -q PIN_IS_ANCESTOR "$f" && n=$((n+1)); done; echo "$n"; }
# «Принимает внешний пин» = строка присваивания пина читает значение из `PIN_OVERRIDE`. Определение
# якорится на присваивание специально: иначе носитель красил бы сам себя собственным grep-паттерном.
count_override() { grep -lE '^[[:space:]]*PIN=\$\{PIN_OVERRIDE' "$1"/lab/e*-run.sh 2>/dev/null | wc -l | tr -d ' '; }
registry_rows() { grep -cE '^lab/e[0-9]{4}-run\.sh' "$1" 2>/dev/null | tr -d ' ' | sed 's/^$/0/'; }

# --- PRE: worktree существующего пина ----------------------------------------------------------
git worktree add --detach "$WT" "$PIN" > "$TMP/wt.log" 2>&1
emit PRE_FIX_WORKTREE "$([ -e "$WT/$E7" ] && echo 1 || echo 0)"
SCOPE_PIN=$(count_scope "$WT")
GATED_PIN=$(count_gated "$WT")
emit PRE_FIX_TOTAL_CARRIERS "$(count_all "$WT")"
emit PRE_FIX_IN_SCOPE "$SCOPE_PIN"
emit PRE_FIX_GATED "$GATED_PIN"
emit PRE_FIX_NONCOMPLIANT "$(( SCOPE_PIN - GATED_PIN ))"
emit PRE_FIX_OVERRIDE "$(count_override "$WT")"
emit PRE_FIX_INSTRUMENT "$([ -e "$WT/$PA" ] && echo 1 || echo 0)"
emit PRE_FIX_EXCEPTIONS "$([ -e "$WT/$EX" ] && echo 1 || echo 0)"
emit PRE_FIX_E0167_GATE "$(grep -q PIN_IS_ANCESTOR "$WT/$O7" 2>/dev/null && echo 1 || echo 0)"
emit PRE_FIX_E0172_GATE "$(grep -q PIN_IS_ANCESTOR "$WT/$E7" 2>/dev/null && echo 1 || echo 0)"
git worktree remove --force "$WT" 2>/dev/null; git worktree prune 2>/dev/null

# --- POST: живое дерево HEAD -------------------------------------------------------------------
SCOPE_HEAD=$(count_scope .)
GATED_HEAD=$(count_gated .)
emit POST_TOTAL_CARRIERS "$(count_all .)"
emit POST_IN_SCOPE "$SCOPE_HEAD"
emit POST_GATED "$GATED_HEAD"
emit POST_NONCOMPLIANT "$(( SCOPE_HEAD - GATED_HEAD ))"
emit POST_OVERRIDE "$(count_override .)"
emit POST_INSTRUMENT "$([ -e "$PA" ] && echo 1 || echo 0)"
emit POST_EXCEPTIONS "$([ -e "$EX" ] && echo 1 || echo 0)"
emit POST_EXEMPT_ROWS "$(registry_rows "$EX")"
emit POST_E0167_GATE "$(grep -q PIN_IS_ANCESTOR "$O7" 2>/dev/null && echo 1 || echo 0)"
emit POST_E0172_GATE "$(grep -q PIN_IS_ANCESTOR "$E7" 2>/dev/null && echo 1 || echo 0)"
python "$PA" > "$TMP/pa.log" 2>&1; emit POST_INSTRUMENT_RC "$(bool_rc $?)"
emit POST_INSTRUMENT_FINDINGS "$(line_val "$TMP/pa.log" 'PIN_ANCESTRY' findings)"
python "$PA" --selftest > "$TMP/pas.log" 2>&1; emit POST_SELFTEST_RC "$(bool_rc $?)"
emit POST_PLANTED_DETECTED "$(line_val "$TMP/pas.log" 'PIN_ANCESTRY_SELFTEST' planted)"
emit POST_PLANTED_TOTAL "$(line_val "$TMP/pas.log" 'PIN_ANCESTRY_SELFTEST' total)"

# --- посадка суррогата: носитель с внешним пином обязан отказаться от PRE-фактов ---------------
# Коммит строится тем же способом, которым был построен суррогат `E-0167`: `commit-tree` поверх HEAD,
# объекта достаточно, чтобы `merge-base --is-ancestor` сказал «нет». Здесь это посадка, а не замер.
SURR=$(git commit-tree "$(git rev-parse HEAD^{tree})" -p HEAD -m "pin-ancestry planting" 2>/dev/null)
PIN_OVERRIDE="$SURR" bash "$O7" > "$TMP/surr.log" 2>&1
emit SURROGATE_REFUSED "$(grep -qE '^PRE_REFUSED[[:space:]]+1' "$TMP/surr.log" && echo 1 || echo 0)"
emit SURROGATE_NO_NUMBERS "$(grep -qE '^PRE_FIX_[A-Z0-9_]+[[:space:]]*=[[:space:]]*[0-9]' "$TMP/surr.log" && echo 0 || echo 1)"

# --- вызовы прибора в обоих контурах -----------------------------------------------------------
emit POST_CI_CALLS "$(grep -c 'check-pin-ancestry' "$YML" 2>/dev/null | tr -d ' ')"
emit POST_WV_CALLS "$(grep -c 'check-pin-ancestry' "$WV" 2>/dev/null | tr -d ' ')"
emit CRATES_TOUCHED_SINCE_PIN "$(git diff --name-only "$PIN" -- crates | wc -l | tr -d ' ')"

# --- соседи: контур обязан остаться зелёным -----------------------------------------------------
python lab/check-guard-selftests.py > /dev/null 2>&1; emit GSE_EXIT "$(bool_rc $?)"
python lab/check-contour-parity.py > /dev/null 2>&1; emit PARITY_EXIT "$(bool_rc $?)"
python lab/check-contours.py > /dev/null 2>&1; emit CONTOURS_EXIT "$(bool_rc $?)"
python lab/check-expect-freeze.py > /dev/null 2>&1; emit EXPECT_FREEZE_EXIT "$(bool_rc $?)"
python lab/check-claims-frozen.py > /dev/null 2>&1; emit CLAIMS_FROZEN_EXIT "$(bool_rc $?)"
python lab/check-none-owners.py > /dev/null 2>&1; emit NONE_OWNERS_EXIT "$(bool_rc $?)"
bash lab/check-text-clean.sh --all > /dev/null 2>&1; emit TEXT_EXIT "$(bool_rc $?)"
bash lab/check-spec-mirror.sh > /dev/null 2>&1; emit SPEC_MIRROR_EXIT "$(bool_rc $?)"
python lab/check-ci-numbers.py > /dev/null 2>&1; emit CIN_EXIT "$(bool_rc $?)"
python lab/check-inventory.py > /dev/null 2>&1; emit INV_EXIT "$(bool_rc $?)"
python lab/cycle-gate.py audit -n 200 > /dev/null 2>&1; emit AUDIT_RC "$(bool_rc $?)"
disk=$(bash lab/disk-report.sh 2>/dev/null | head -1)
case "$disk" in DISK_FREE_MB=*) emit DISK_READABLE 1;; *) emit DISK_READABLE 0;; esac

if [ "${MEASURE:-0}" = 1 ]; then
  echo "MEASURE_ONLY=1 фактов=$(grep -c . "$TMP/facts")"
  exit 0
fi

WORST=0
while IFS=$'\t' read -r k v; do
  [ -z "$k" ] && continue
  got=$(awk -F'\t' -v k="$k" '$1==k{print $2}' "$TMP/facts")
  if [ "$got" = "$v" ]; then
    echo "СВЕРКА $k=$got"
  else
    echo "РАСХОЖДЕНИЕ $k: ждали $v, получили ${got:-нет}"
    WORST=1
  fi
done < lab/expectations/e0172.tsv
echo "WORST_RC=$WORST"

SNAP="$(git rev-parse HEAD)|$(git status --porcelain | sha256sum | cut -c1-16)"
STABLE_FILE=/tmp/e0172-stable.txt
if [ -f "$STABLE_FILE" ] && [ "$(cat "$STABLE_FILE")" = "$SNAP" ]; then
  echo "STABLE=1"
else
  printf '%s' "$SNAP" > /tmp/e0172-stable.txt
  echo "STABLE=0"
fi
