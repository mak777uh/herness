#!/usr/bin/env bash
# e0167-run.sh — носитель H-0167/E-0167: освобождение прибора — список с датой, а не отсутствие ключа.
#
# Почему здесь worktree, а не посадка. Посадка `git checkout $PIN -- <файл>` из E-0163…E-0166
# годится, когда предмет — байты продукта: посадил файл, прогнал тест, вернул. Здесь предмет —
# ПОВЕДЕНИЕ ПРИБОРОВ над кругом целиком (160 карточек, снимок счётчиков, таблица доменов), поэтому
# ветки обязаны отличаться деревом, а не только версией одного файла. Пин разворачивается
# отдельным worktree (`git worktree add --detach`), и обе ветки считаются ОДНИМИ И ТЕМИ ЖЕ
# приборами HEAD: у `check-inventory.py` и `check-domain-table.py` есть `--root`, у `cycle-gate.py`
# — `VEC_DHT_ROOT`. Так PRE не «память о прошлом прогоне», а исполненное измерение, а POST не
# спорит с PRE о том, что такое дерево.
#
# Урок E-0166 учтён: `grep -c` считает СТРОКИ, поэтому каждое число либо снято с одной помеченной
# строки (`line_val` берёт первую строку с префиксом и вынимает токен `имя=число`), либо сведено
# к паре 0/1. Пустой вывод означает 0 — это и есть форма «прибора на дереве нет», и она названа
# отдельным фактом (`PRE_FIX_*_EXISTS`), а не спрятана в нуле счётчика.
#
# PIN_OVERRIDE нужен ровно один раз — для замера фактов ДО пре-регистрационного коммита, когда
# файл карточки ещё не имеет истории git. Официальные прогоны его не ставят: без него пин —
# первый коммит, внёсший `lab/hypotheses/H-0167-….md`, и `PIN_HASEXPECT` проверяет, что таблица
# ожиданий вошла тем же коммитом.
set -u
cd "$(dirname "$0")/.."

PIN=${PIN_OVERRIDE:-$(git log --format=%H --reverse -- lab/hypotheses/H-0167-explicit-instrument-exemptions.md | head -1)}
CG=lab/cycle-gate.py
WV=lab/workspace-verify.sh
YML=.github/workflows/verify.yml
INV=lab/check-inventory.py
DOM=lab/check-domain-table.py
LEG=lab/cycle-gate-legacy.tsv
DEF=lab/cycle-gate-defects.tsv
TMP=$(mktemp -d)
WT="$TMP/pin"
: > "$TMP/facts"
trap 'git worktree remove --force "$WT" 2>/dev/null; git worktree prune 2>/dev/null; rm -rf "$TMP"' EXIT

emit() { printf '%s\t%s\n' "$1" "$2" | tee -a "$TMP/facts"; }
bool_rc() { if [ "$1" -eq 0 ]; then echo 0; else echo 1; fi; }
# line_val <лог> <префикс строки> <токен> — число с первой строки, начинающейся с префикса; 0,
# если такой строки нет (отсутствие формы — тоже измерение, но названное отдельным фактом).
line_val() {
  local v
  v=$(grep "^$2" "$1" 2>/dev/null | head -1 | grep -oE "$3=[0-9]+" | head -1 | cut -d= -f2)
  echo "${v:-0}"
}
# form_lines <файл> — сколько новых замороженных форм печатает прибор на этом дереве.
new_forms() { grep -cE '^AUDIT_(LIST|SHAPKA|DEFECTS|MECH)' "$1"; }
labels() { grep -oE '[A-Z][A-Z_0-9]*_EXIT' "$1" | sort -u | wc -l | tr -d ' '; }

emit PIN_FOUND "$(git cat-file -e "$PIN^{commit}" 2>/dev/null && echo 1 || echo 0)"
# Таблица и карточка обязаны войти одним коммитом: иначе порог цикла поднят после пре-регистрации.
emit PIN_HASEXPECT "$([ "$(git log --format=%H --reverse -- lab/expectations/e0167.tsv | head -1)" = "$PIN" ] && echo 1 || echo 0)"

# Гейт предковости пина (`ADR-0078`, следствие закрытия этого же круга): PRE-факты снимаются только с
# дерева, которое реально предшествует HEAD. `PIN_OVERRIDE` легитимен ровно до появления
# пре-регистрационного коммита — после него подставное дерево обязано напечатать отказ, а не число:
# именно так `E-0167` потерял круг на одном замороженном факте (`PRE_FIX_BAD`: ждали 10, на пине 9).
if git merge-base --is-ancestor "$PIN" HEAD 2>/dev/null; then
  emit PIN_IS_ANCESTOR 1
else
  emit PIN_IS_ANCESTOR 0
  emit PRE_REFUSED 1
  echo "PRE_REFUSED=1: пин ${PIN:-пуст} не является предком HEAD — ни один PRE-факт не снимается"
  exit 2
fi

git worktree add --detach "$WT" "$PIN" > "$TMP/wt.log" 2>&1
emit PRE_FIX_WORKTREE "$([ -e "$WT/$CG" ] && echo 1 || echo 0)"
# Дерево пина не должно ничего знать о новых списках: иначе «освобождение по отсутствию»
# превратилось бы в «освобождение по файлу, которого ещё нет».
emit PRE_FIX_LEGACY_LIST "$([ -f "$WT/$LEG" ] && echo 1 || echo 0)"
emit PRE_FIX_DEFECTS_LIST "$([ -f "$WT/$DEF" ] && echo 1 || echo 0)"
emit PRE_FIX_INV_EXISTS "$([ -f "$WT/$INV" ] && echo 1 || echo 0)"
emit PRE_FIX_DOM_EXISTS "$([ -f "$WT/$DOM" ] && echo 1 || echo 0)"

# --- PRE: приборы пина над деревом пина -------------------------------------------------------
VEC_DHT_ROOT="$WT" python "$WT/$CG" audit -n 200 > "$TMP/pre_audit.log" 2>&1
pre_audit_rc=$?
emit PRE_FIX_CARDS "$(line_val "$TMP/pre_audit.log" 'AUDIT ' карточек)"
emit PRE_FIX_HIST "$(line_val "$TMP/pre_audit.log" 'AUDIT ' исторических)"
emit PRE_FIX_RULE "$(line_val "$TMP/pre_audit.log" 'AUDIT ' под_правилом)"
emit PRE_FIX_BAD "$(line_val "$TMP/pre_audit.log" 'AUDIT_BAD' карточек_с_нарушениями)"
emit PRE_FIX_AUDIT_FORM "$(new_forms "$TMP/pre_audit.log")"
emit PRE_FIX_AUDIT_RC "$(bool_rc $pre_audit_rc)"
# Дверь «отсутствие ключа = историческая»: H-0165 освобождена именно ею.
emit PRE_FIX_H0165_EXEMPT "$(grep -cE '^КАРТОЧКА H-0165: историческая' "$TMP/pre_audit.log")"
# Сколько карточек освобождено молча (строкой «историческая» в отчёте пина).
emit PRE_FIX_SILENT_EXEMPT "$(grep -cE '^КАРТОЧКА .*: историческая' "$TMP/pre_audit.log")"
VEC_DHT_ROOT="$WT" python "$WT/$CG" selftest > "$TMP/pre_st.log" 2>&1
emit PRE_FIX_SELFTEST_TOTAL "$(line_val "$TMP/pre_st.log" 'CYCLEGATE_SELFTEST' total)"
emit PRE_FIX_SELFTEST_PASSED "$(line_val "$TMP/pre_st.log" 'CYCLEGATE_SELFTEST' passed)"
emit PRE_FIX_REGISTRY_CASES "$(grep -cE '^CYCLEGATE_REGISTRY_CASES' "$TMP/pre_st.log")"
emit PRE_FIX_HOST_AUDIT "$(grep -c "$CG audit" "$WT/$WV")"
emit PRE_FIX_CI_AUDIT_ALL "$(grep -c 'audit --all' "$WT/$YML")"
emit PRE_FIX_CI_AUDIT_WINDOW "$(grep -cE "$CG audit( |$)" "$WT/$YML")"
emit PRE_FIX_GUARD_CALLS "$(grep -cE '^\s*call\s+[A-Z][A-Z_0-9]*\s' "$WT/$YML")"
emit PRE_FIX_DYNAMIC_LABEL "$(grep -cF '${name}_EXIT' "$WT/$YML")"
emit PRE_FIX_SUMMARY_LABEL "$(grep -cE 'echo "GUARD_SELFTESTS_EXIT' "$WT/$YML")"
# Снимок и таблица доменов считаются прибором HEAD над деревом пина — та же функция счёта.
python "$INV" --root "$WT" > "$TMP/pre_inv.log" 2>&1; r=$?
emit PRE_INV_KEYS "$(line_val "$TMP/pre_inv.log" 'INVENTORY_KEYS' INVENTORY_KEYS)"
emit PRE_INV_ROWS "$(line_val "$TMP/pre_inv.log" 'INVENTORY_ROWS' INVENTORY_ROWS)"
emit PRE_INV_DIFF "$(line_val "$TMP/pre_inv.log" 'INVENTORY_DIFF' INVENTORY_DIFF)"
emit PRE_INV_RC "$(bool_rc $r)"
python "$DOM" --root "$WT" > "$TMP/pre_dom.log" 2>&1; r=$?
emit PRE_DOMAIN_DECLS "$(line_val "$TMP/pre_dom.log" 'DOMAIN_DECLS' DOMAIN_DECLS)"
emit PRE_DOMAIN_TABLE_READS "$(line_val "$TMP/pre_dom.log" 'DOMAIN_TABLE_READS' DOMAIN_TABLE_READS)"
emit PRE_DOMAIN_SITES "$(line_val "$TMP/pre_dom.log" 'DOMAIN_SITES' DOMAIN_SITES)"
emit PRE_DOMAIN_UNRESOLVED "$(line_val "$TMP/pre_dom.log" 'DOMAIN_UNRESOLVED' DOMAIN_UNRESOLVED)"
emit PRE_DOMAIN_MISMATCH "$(line_val "$TMP/pre_dom.log" 'DOMAIN_MISMATCH' DOMAIN_MISMATCH)"
emit PRE_DOMAIN_SITES_MISMATCH "$(line_val "$TMP/pre_dom.log" 'DOMAIN_SITES_MISMATCH' DOMAIN_SITES_MISMATCH)"
emit PRE_DOMAIN_FINDINGS "$(line_val "$TMP/pre_dom.log" 'DOMAIN_FINDINGS' DOMAIN_FINDINGS)"
emit PRE_DOMAIN_RC "$(bool_rc $r)"

# --- POST: приборы HEAD над деревом HEAD ------------------------------------------------------
python "$CG" audit -n 200 > "$TMP/post_audit.log" 2>&1
post_audit_rc=$?
emit POST_CARDS "$(line_val "$TMP/post_audit.log" 'AUDIT ' карточек)"
emit POST_HIST "$(line_val "$TMP/post_audit.log" 'AUDIT ' исторических)"
emit POST_RULE "$(line_val "$TMP/post_audit.log" 'AUDIT ' под_правилом)"
emit POST_BAD "$(line_val "$TMP/post_audit.log" 'AUDIT_BAD' карточек_с_нарушениями)"
emit POST_AUDIT_FORM "$(new_forms "$TMP/post_audit.log")"
emit POST_AUDIT_RC "$(bool_rc $post_audit_rc)"
emit POST_LIST_ROWS "$(line_val "$TMP/post_audit.log" 'AUDIT_LIST' строк)"
emit POST_LIST_DIFF "$(line_val "$TMP/post_audit.log" 'AUDIT_LIST' расхождений)"
emit POST_DEFECTS_ROWS "$(line_val "$TMP/post_audit.log" 'AUDIT_DEFECTS' строк)"
emit POST_DEFECTS_DIFF "$(line_val "$TMP/post_audit.log" 'AUDIT_DEFECTS' расхождений)"
emit POST_SHAPKA "$(line_val "$TMP/post_audit.log" 'AUDIT_SHAPKA' не_разобранных)"
emit POST_MECH_FINDINGS "$(line_val "$TMP/post_audit.log" 'AUDIT_MECH' находок)"
# Та же карточка, то же дерево: освобождение больше не следует из отсутствия ключа, а нарушение
# обязано стоять строкой снимка с числом и человеческой причиной.
emit POST_H0165_EXEMPT "$(grep -cE '^КАРТОЧКА H-0165: историческая' "$TMP/post_audit.log")"
emit POST_H0165_DEFECTS_ROW "$(awk -F'\t' '$1=="H-0165"{print $2}' "$DEF")"
emit POST_SILENT_EXEMPT "$(grep -cE '^КАРТОЧКА .*: историческая' "$TMP/post_audit.log")"
python "$CG" selftest > "$TMP/post_st.log" 2>&1
emit POST_SELFTEST_TOTAL "$(line_val "$TMP/post_st.log" 'CYCLEGATE_SELFTEST' total)"
emit POST_SELFTEST_PASSED "$(line_val "$TMP/post_st.log" 'CYCLEGATE_SELFTEST' passed)"
emit POST_REGISTRY_CASES "$(line_val "$TMP/post_st.log" 'CYCLEGATE_REGISTRY_CASES' отбито)"
python "$CG" selftest > /dev/null 2>&1; emit SELFTEST_RC "$(bool_rc $?)"
python "$INV" > "$TMP/post_inv.log" 2>&1; r=$?
emit POST_INV_DIFF "$(line_val "$TMP/post_inv.log" 'INVENTORY_DIFF' INVENTORY_DIFF)"
emit POST_INV_RC "$(bool_rc $r)"
python "$INV" --selftest > "$TMP/inv_st.log" 2>&1; r=$?
emit INV_SELFTEST_RC "$(bool_rc $r)"
emit INV_SELFTEST_PASSED "$(grep -oE 'INVENTORY_SELFTEST=[0-9]+/[0-9]+' "$TMP/inv_st.log" | tail -1 | cut -d/ -f2)"
python "$DOM" > "$TMP/post_dom.log" 2>&1; r=$?
emit POST_DOMAIN_FINDINGS "$(line_val "$TMP/post_dom.log" 'DOMAIN_FINDINGS' DOMAIN_FINDINGS)"
emit POST_DOMAIN_DECLS "$(line_val "$TMP/post_dom.log" 'DOMAIN_DECLS' DOMAIN_DECLS)"
emit POST_DOMAIN_SITES "$(line_val "$TMP/post_dom.log" 'DOMAIN_SITES' DOMAIN_SITES)"
emit POST_DOMAIN_MISMATCH "$(line_val "$TMP/post_dom.log" 'DOMAIN_MISMATCH' DOMAIN_MISMATCH)"
emit POST_DOMAIN_RC "$(bool_rc $r)"
python "$DOM" --selftest > "$TMP/dom_st.log" 2>&1; r=$?
emit DOM_SELFTEST_RC "$(bool_rc $r)"
# Цепь стражей: поприборные коды и боевой аудит всего круга.
emit POST_HOST_AUDIT "$(grep -c "$CG audit" "$WV")"
emit POST_CI_AUDIT_ALL "$(grep -c 'audit --all' "$YML")"
emit POST_GUARD_CALLS "$(grep -cE '^\s*call\s+[A-Z][A-Z_0-9]*\s' "$YML")"
emit POST_DYNAMIC_LABEL "$(grep -cF '${name}_EXIT' "$YML")"
emit POST_SUMMARY_LABEL "$(grep -cE 'echo "GUARD_SELFTESTS_EXIT' "$YML")"
# Продукт этого цикла — приборы; байты протокола не тронуты ни на пин, ни на HEAD.
emit CRATES_TOUCHED_SINCE_PIN "$(git diff --name-only "$PIN" | grep -c '^crates/' | tr -d ' ')"
emit REGISTRY_ROWS "$(( $(grep -cE '^H-[0-9]{4}' "$LEG") + $(grep -cE '^H-[0-9]{4}' "$DEF") ))"

# --- соседи: контур обязан остаться зелёным ---------------------------------------------------
python lab/check-guard-selftests.py > /dev/null 2>&1; emit GSE_EXIT "$(bool_rc $?)"
python lab/check-contour-parity.py > /dev/null 2>&1; emit PARITY_EXIT "$(bool_rc $?)"
python lab/check-contours.py > /dev/null 2>&1; emit CONTOURS_EXIT "$(bool_rc $?)"
python lab/check-expect-freeze.py > /dev/null 2>&1; emit EXPECT_FREEZE_EXIT "$(bool_rc $?)"
python lab/check-claims-frozen.py > /dev/null 2>&1; emit CLAIMS_FROZEN_EXIT "$(bool_rc $?)"
python lab/check-none-owners.py > /dev/null 2>&1; emit NONE_OWNERS_EXIT "$(bool_rc $?)"
bash lab/check-text-clean.sh --all > /dev/null 2>&1; emit TEXT_EXIT "$(bool_rc $?)"
bash lab/check-spec-mirror.sh > /dev/null 2>&1; emit SPEC_MIRROR_EXIT "$(bool_rc $?)"
python lab/check-ci-numbers.py > /dev/null 2>&1; emit CIN_EXIT "$(bool_rc $?)"
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
done < lab/expectations/e0167.tsv
echo "WORST_RC=$WORST"

SNAP="$(git rev-parse HEAD)|$(git status --porcelain | sha256sum | cut -c1-16)"
STABLE_FILE=/tmp/e0167-stable.txt
if [ -f "$STABLE_FILE" ] && [ "$(cat "$STABLE_FILE")" = "$SNAP" ]; then
  echo "STABLE=1"
else
  printf '%s' "$SNAP" > /tmp/e0167-stable.txt
  echo "STABLE=0"
fi
