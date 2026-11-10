#!/usr/bin/env bash
# e0173-run.sh — носитель H-0173/E-0173: прибор, выводящий дату из истории, обязан отказываться на
# неполной истории, а не выносить вердикт по данным, которых в дереве нет.
#
# Почему здесь и worktree, и shallow-клон. Worktree пина (`git worktree add --detach`) даёт дерево пина
# на ПОЛНОЙ истории — это база сравнения: те же файлы, те же приборы, настоящая история. Shallow-клон
# пина (`git clone --no-local --depth 1` временной ветки на пин) даёт то же дерево на ИСТОРИИ В ОДИН
# КОММИТ — ровно то окружение, в котором CI на голове `bebc21c` напечатал `порог=2026-11-01 находок=88`
# (п. 132). Разница двух судов и есть измеряемый факт; ни одно число не берётся «по памяти о прошлом
# прогоне» и ни одно не снимается с дерева, которого нет в истории (собственный гейт печатается до замеров).
#
# Урок `E-0167`, исполненный буквально: отсутствие формы — отдельный названный факт, а не нуль, поэтому
# каждый ключ ниже либо извлечён из лога одним значением, либо назван `none`.
#
# ДИАГНОЗ носителя (правка после пина, таблица не тронута): логи четырёх приборов пишутся в отдельный
# каталог `$TMP/<режим>`, а не в измеряемое дерево. Первый вариант писал `gate.log`/`ef.log`/`cf.log`/
# `ddf.log` в каталог вызова, и прогон на HEAD оставил в репозитории три незапланированных файла — то
# есть носитель сам нарушал правило «дерево не править во время прогона», которое он обязан измерять.
set -u
cd "$(dirname "$0")/.."

ROOT=$(pwd -W 2>/dev/null || pwd)
PIN=$(git log --format=%H --reverse -- lab/hypotheses/H-0173-history-shallowness-refusal.md | head -1)
TMP=$(mktemp -d)
WT="$TMP/pin-full"
SHP="$TMP/pin-shallow"
SHH="$TMP/head-shallow"
: > "$TMP/facts"
cleanup() {
  git worktree remove --force "$WT" 2>/dev/null
  git worktree prune 2>/dev/null
  git branch -D e0173-pin 2>/dev/null
  rm -rf "$TMP"
}
trap cleanup EXIT

emit() { printf '%s\t%s\n' "$1" "$2" | tee -a "$TMP/facts"; }
bool_rc() { if [ "$1" -eq 0 ]; then echo 0; else echo 1; fi; }
has() { if grep -aq "$2" "$1" 2>/dev/null; then echo 1; else echo 0; fi; }
# Значение ключа из лога прибора; отсутствие формы — `none`, а не `0` (урок `E-0167`).
key() { local v; v=$(grep -aoE "^$2=[0-9]+" "$1" 2>/dev/null | head -1 | cut -d= -f2); echo "${v:-none}"; }
gate_findings() { local v; v=$(grep -a "AUDIT_MECH" "$1" 2>/dev/null | grep -oE "находок=[0-9]+" | head -1 | cut -d= -f2); echo "${v:-none}"; }
more() { # больше ли первого числа, чем второго (оба обязаны быть числами)
  [ "$1" != none ] && [ "$2" != none ] && [ "$1" -gt "$2" ] && echo 1 || echo 0
}

# --- класс: кто выводит дату появления файла из истории (одна функция для обеих веток) ---------
# Обязаны отказаться двое: те, кто выводит дату из истории (`--diff-filter=A`), и тот, кто владеет
# освобождением для вызывающего (`--require-git` / `--no-git`) и потому молчит вместо отказа.
in_scope() {
  grep -qE '"git"|git log' "$1" 2>/dev/null || return 1
  grep -q -- '--diff-filter=A' "$1" 2>/dev/null || return 1
  return 0
}
flag_owner() {
  grep -qE '"git"|git log' "$1" 2>/dev/null || return 1
  grep -q 'require-git' "$1" 2>/dev/null || return 1
  return 0
}
must_refuse() { in_scope "$1" || flag_owner "$1"; }
count_py_git()   { local n=0 f; for f in "$1"/lab/*.py; do [ -e "$f" ] || continue; grep -qE '"git"|git log' "$f" && n=$((n+1)); done; echo "$n"; }
count_in_scope() { local n=0 f; for f in "$1"/lab/*.py; do [ -e "$f" ] || continue; in_scope "$f" && n=$((n+1)); done; echo "$n"; }
count_class()    { local n=0 f; for f in "$1"/lab/*.py; do [ -e "$f" ] || continue; must_refuse "$f" && n=$((n+1)); done; echo "$n"; }
# «Знает про полноту истории» = ссылается на общий механизм, а не переписывает `git rev-parse` сам:
# проверка на `is-shallow-repository` в тексте прибора краснила бы как раз за пересчёт механизма.
count_helper()   { local n=0 f; for f in "$1"/lab/*.py; do [ -e "$f" ] || continue; must_refuse "$f" && grep -q 'historylib' "$f" && n=$((n+1)); done; echo "$n"; }
count_flag_only() { local n=0 f; for f in "$1"/lab/*.py; do [ -e "$f" ] || continue; flag_owner "$f" && n=$((n+1)); done; echo "$n"; }
# Сумма поведенческих отказов: сколько из четырёх приборов ПЕЧАТАЮТ строку отказа в shallow-клоне.
sum_refuses() { local p="$1" n=0 k v; for k in GATE EF CF DDF; do
  v=$(awk -F'\t' -v key="$p""_$k""_REFUSES" '$1==key{print $2}' "$TMP/facts" | tail -1)
  [ "$v" = 1 ] && n=$((n+1))
done; echo "$n"; }

# --- один и тот же набор вызовов в любом дереве; режим выбирает имена ключей --------------------
measure() {
  local mode="$1" D="$2" L="$3" rc
  mkdir -p "$L"
  (cd "$D" && python lab/cycle-gate.py audit --all)   > "$L/gate.log" 2>&1; rc=$?; echo "GATE_RC=$rc"   >  "$L/rc.gate"; echo "$rc" > "$L/rc.gate.v"
  (cd "$D" && python lab/check-expect-freeze.py)      > "$L/ef.log"   2>&1; rc=$?; echo "$rc" > "$L/rc.ef.v"
  (cd "$D" && python lab/check-claims-frozen.py)      > "$L/cf.log"   2>&1; rc=$?; echo "$rc" > "$L/rc.cf.v"
  (cd "$D" && python lab/check-date-domain.py check --require-git) > "$L/ddf.log" 2>&1; rc=$?; echo "$rc" > "$L/rc.ddf.v"
  case "$mode" in
    pre_shallow)
      emit PRE_GATE_RC "$(cat "$L/rc.gate.v")"
      emit PRE_GATE_REFUSES "$(has "$L/gate.log" AUDIT_SHALLOW)"
      emit PRE_EF_RC "$(cat "$L/rc.ef.v")"
      emit PRE_EF_REFUSES "$(has "$L/ef.log" EF_SHALLOW)"
      emit PRE_CF_RC "$(cat "$L/rc.cf.v")"
      emit PRE_CF_REFUSES "$(has "$L/cf.log" CF_SHALLOW)"
      emit PRE_DDF_RC "$(cat "$L/rc.ddf.v")"
      emit PRE_DDF_REFUSES "$(has "$L/ddf.log" DDF_SHALLOW)"
      ;;
    pre_full)
      emit PRE_FULL_GATE_FINDINGS "$(gate_findings "$L/gate.log")"
      emit PRE_FULL_EF_FINDINGS "$(key "$L/ef.log" EF_FINDINGS)"
      ;;
    post_shallow)
      emit POST_GATE_RC "$(cat "$L/rc.gate.v")"
      emit POST_GATE_REFUSES "$(has "$L/gate.log" AUDIT_SHALLOW)"
      emit POST_GATE_NO_VERDICT "$([ "$(has "$L/gate.log" AUDIT_MECH)" = 0 ] && echo 1 || echo 0)"
      emit POST_EF_RC "$(cat "$L/rc.ef.v")"
      emit POST_EF_REFUSES "$(has "$L/ef.log" EF_SHALLOW)"
      emit POST_EF_NO_VERDICT "$([ "$(has "$L/ef.log" EF_FINDINGS)" = 0 ] && echo 1 || echo 0)"
      emit POST_CF_RC "$(cat "$L/rc.cf.v")"
      emit POST_CF_REFUSES "$(has "$L/cf.log" CF_SHALLOW)"
      emit POST_CF_NO_VERDICT "$([ "$(has "$L/cf.log" CF_FINDINGS)" = 0 ] && echo 1 || echo 0)"
      emit POST_DDF_RC "$(cat "$L/rc.ddf.v")"
      emit POST_DDF_REFUSES "$(has "$L/ddf.log" DDF_SHALLOW)"
      emit POST_DDF_NO_VERDICT "$([ "$(has "$L/ddf.log" DDF_FINDINGS)" = 0 ] && echo 1 || echo 0)"
      ;;
    post_full)
      emit POST_FULL_GATE_RC "$(cat "$L/rc.gate.v")"
      emit POST_FULL_GATE_FINDINGS "$(gate_findings "$L/gate.log")"
      emit POST_FULL_EF_RC "$(cat "$L/rc.ef.v")"
      emit POST_FULL_CF_RC "$(cat "$L/rc.cf.v")"
      emit POST_FULL_DDF_RC "$(cat "$L/rc.ddf.v")"
      ;;
  esac
}

# --- собственный гейт: печатается ДО любого замера ---------------------------------------------
emit PIN_FOUND "$(git cat-file -e "$PIN^{commit}" 2>/dev/null && echo 1 || echo 0)"
emit PIN_HASEXPECT "$([ -n "$PIN" ] && [ "$(git log --format=%H --reverse -- lab/expectations/e0173.tsv | head -1)" = "$PIN" ] && echo 1 || echo 0)"
if git merge-base --is-ancestor "$PIN" HEAD 2>/dev/null; then emit PIN_IS_ANCESTOR 1; else emit PIN_IS_ANCESTOR 0; fi
if [ "$(awk -F'\t' '$1=="PIN_IS_ANCESTOR"{print $2}' "$TMP/facts")" != 1 ]; then
  echo "PRE_REFUSED=1 — пин не предок HEAD, PRE-факты не снимаются ни с какого дерева"
  while IFS=$'\t' read -r k _v; do
    [ -z "$k" ] && continue
    case "$k" in PRE_*|POST_*|PIN_*) printf '%s\tnone\n' "$k";; esac
  done < lab/expectations/e0173.tsv
  exit 1
fi

# --- PRE: дерево пина на полной истории (worktree) и на истории в один коммит (shallow-клон) ----
git worktree add --detach "$WT" "$PIN" >/dev/null 2>&1
emit PRE_WORKTREE "$([ -e "$WT/lab/hypotheses/H-0173-history-shallowness-refusal.md" ] && echo 1 || echo 0)"
git branch -f e0173-pin "$PIN"
git clone -q --no-local --depth 1 --branch e0173-pin "$ROOT" "$SHP" 2>/dev/null
emit PRE_CLONE_MADE "$([ -e "$SHP/lab/cycle-gate.py" ] && echo 1 || echo 0)"
emit PRE_CLONE_IS_SHALLOW "$( (cd "$SHP" 2>/dev/null && git rev-parse --is-shallow-repository) | grep -qx true && echo 1 || echo 0)"
emit PRE_CLONE_COMMITS "$(cd "$SHP" 2>/dev/null && git rev-list --count HEAD 2>/dev/null)"
emit PRE_TREE_MATCHES_PIN "$([ "$(cd "$SHP" 2>/dev/null && git rev-parse 'HEAD^{tree}')" = "$(git rev-parse "$PIN^{tree}")" ] && echo 1 || echo 0)"
emit PRE_PY_GIT "$(count_py_git "$SHP")"
emit PRE_IN_SCOPE "$(count_in_scope "$SHP")"
emit PRE_REFUSE_CLASS "$(count_class "$SHP")"
emit PRE_FLAG_ONLY "$(count_flag_only "$SHP")"
emit PRE_HELPER_CALLS "$(count_helper "$SHP")"
measure pre_full "$WT" "$TMP/pre-full"
measure pre_shallow "$SHP" "$TMP/pre-shallow"
emit PRE_REFUSING "$(sum_refuses PRE)"
# «Изобретает находки» — отношение двух замеров ОДНОГО дерева, а не абсолютное число: абсолют зависит
# от того, сколько карточек в круге, и заморозить его значило бы написать порог задним числом.
emit PRE_GATE_INVENTS "$(more "$(gate_findings "$TMP/pre-shallow/gate.log")" "$(gate_findings "$TMP/pre-full/gate.log")")"
emit PRE_EF_INVENTS "$(more "$(key "$TMP/pre-shallow/ef.log" EF_FINDINGS)" "$(key "$TMP/pre-full/ef.log" EF_FINDINGS)")"
# Молчание = провал: зелёный выход и ноль находок там, где прибор судит по несуществующей истории.
emit PRE_CF_SILENT "$([ "$(cat "$TMP/pre-shallow/rc.cf.v")" = 0 ] && [ "$(key "$TMP/pre-shallow/cf.log" CF_FINDINGS)" = 0 ] && [ "$(has "$TMP/pre-shallow/cf.log" CF_SHALLOW)" = 0 ] && echo 1 || echo 0)"
emit PRE_DDF_SILENT "$([ "$(cat "$TMP/pre-shallow/rc.ddf.v")" = 0 ] && [ "$(key "$TMP/pre-shallow/ddf.log" DDF_FINDINGS)" = 0 ] && [ "$(has "$TMP/pre-shallow/ddf.log" DDF_SHALLOW)" = 0 ] && echo 1 || echo 0)"

# --- POST: те же вызовы на дереве HEAD -------------------------------------------------------------
git clone -q --no-local --depth 1 "$ROOT" "$SHH" 2>/dev/null
emit POST_CLONE_MADE "$([ -e "$SHH/lab/cycle-gate.py" ] && echo 1 || echo 0)"
emit POST_CLONE_IS_SHALLOW "$( (cd "$SHH" 2>/dev/null && git rev-parse --is-shallow-repository) | grep -qx true && echo 1 || echo 0)"
emit POST_CLONE_COMMITS "$(cd "$SHH" 2>/dev/null && git rev-list --count HEAD 2>/dev/null)"
emit POST_PY_GIT "$(count_py_git "$SHH")"
emit POST_IN_SCOPE "$(count_in_scope "$SHH")"
emit POST_REFUSE_CLASS "$(count_class "$SHH")"
emit POST_HELPER_CALLS "$(count_helper "$SHH")"
measure post_shallow "$SHH" "$TMP/post-shallow"
emit POST_REFUSING "$(sum_refuses POST)"
measure post_full "." "$TMP/post-full"

# --- соседи: контур обязан остаться зелёным -------------------------------------------------------
python lab/check-guard-selftests.py > /dev/null 2>&1; emit GSE_EXIT "$(bool_rc $?)"
python lab/check-contour-parity.py > /dev/null 2>&1; emit PARITY_EXIT "$(bool_rc $?)"
python lab/check-contours.py > /dev/null 2>&1; emit CONTOURS_EXIT "$(bool_rc $?)"
python lab/check-expect-freeze.py > /dev/null 2>&1; emit EXPECT_FREEZE_EXIT "$(bool_rc $?)"
python lab/check-claims-frozen.py > /dev/null 2>&1; emit CLAIMS_FROZEN_EXIT "$(bool_rc $?)"
python lab/check-oq-numbering.py > /dev/null 2>&1; emit OQ_EXIT "$(bool_rc $?)"
python lab/check-artifact-refs.py > /dev/null 2>&1; emit ARTREF_EXIT "$(bool_rc $?)"
bash lab/check-text-clean.sh --all > /dev/null 2>&1; emit TEXT_EXIT "$(bool_rc $?)"
bash lab/check-spec-mirror.sh > /dev/null 2>&1; emit SPEC_MIRROR_EXIT "$(bool_rc $?)"
python lab/check-ci-numbers.py > /dev/null 2>&1; emit CIN_EXIT "$(bool_rc $?)"
python lab/check-inventory.py > /dev/null 2>&1; emit INV_EXIT "$(bool_rc $?)"
python lab/cycle-gate.py audit -n 200 > /dev/null 2>&1; emit AUDIT_RC "$(bool_rc $?)"
disk=$(bash lab/disk-report.sh 2>/dev/null | head -1)
case "$disk" in DISK_FREE_MB=*) emit DISK_READABLE 1;; *) emit DISK_READABLE 0;; esac
emit CRATES_TOUCHED_SINCE_PIN "$(git diff --name-only "$PIN" -- crates | wc -l | tr -d ' ')"

if [ "${MEASURE:-0}" = 1 ]; then
  echo "MEASURE_ONLY=1 фактов=$(cut -f1 "$TMP/facts" | sort -u | wc -l | tr -d ' ')"
  exit 0
fi

WORST=0
while IFS=$'\t' read -r k v; do
  [ -z "$k" ] && continue
  got=$(awk -F'\t' -v k="$k" '$1==k{print $2}' "$TMP/facts" | tail -1)
  if [ "$got" = "$v" ]; then
    echo "СВЕРКА $k=$got"
  else
    echo "РАСХОЖДЕНИЕ $k: ждали $v, получили ${got:-нет}"
    WORST=1
  fi
done < lab/expectations/e0173.tsv
echo "WORST_RC=$WORST"

SNAP="$(git rev-parse HEAD)|$(git status --porcelain | sha256sum | cut -c1-16)"
STABLE_FILE=/tmp/e0173-stable.txt
if [ -f "$STABLE_FILE" ] && [ "$(cat "$STABLE_FILE")" = "$SNAP" ]; then
  echo "STABLE=1"
else
  printf '%s' "$SNAP" > /tmp/e0173-stable.txt
  echo "STABLE=0"
fi
