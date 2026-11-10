#!/usr/bin/env bash
# e0179-run.sh — носитель H-0179: страж текста различает три исхода.
#
# Три плеча:
#   A. окружение без python и python3 → код 2 («не запускался»);
#   B. посаженное нарушение            → код 1 («нарушения есть»);
#   C. чистое дерево                   → код 0 («нарушений нет»).
#
# Плечо A делается PATH'ом без интерпретаторов: каталог с заглушками, где нет ни python, ни
# python3, а нужные утилиты приходят из /usr/bin. Это честнее, чем «переименовать python»:
# дерево не меняется.
set -u
cd "$(dirname "$0")/.." || exit 1
GUARD=lab/check-text-clean.sh
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
: > "$TMP/facts"
emit() { printf '%s\t%s\n' "$1" "$2" | tee -a "$TMP/facts"; }
bool_rc() { if [ "$1" -eq 0 ]; then echo 0; else echo 1; fi; }

# --- A: без интерпретатора -------------------------------------------------------------------
# Заглушка-каталог впереди PATH: там лежат только те утилиты, что нужны стражу, и ни одного
# python. Если страж всё же найдёт python где-то дальше в PATH — плечо недействительно.
STUB="$TMP/stub"
mkdir -p "$STUB"
for tool in bash env git mktemp rm cat sed grep awk head tail sort wc tr cut date dirname basename; do
  src=$(command -v "$tool" 2>/dev/null) && ln -sf "$src" "$STUB/$tool"
done
env -i PATH="$STUB" HOME="$HOME" bash "$GUARD" --all > "$TMP/a.log" 2>&1
rc_a=$?
emit TEXT_NO_PY_RC "$rc_a"
# Контроль плеча: интерпретатора в этом PATH действительно нет.
env -i PATH="$STUB" bash -c 'command -v python3 || command -v python' > /dev/null 2>&1
emit TEXT_NO_PY_ABSENT "$(bool_rc $?)"

# --- B: посаженное нарушение -----------------------------------------------------------------
# Нарушение — символ вне ASCII/кириллицы, то есть ровно то, что страж ищет. Файл создаётся во
# временном каталоге и передаётся аргументом: дерево не меняется.
BAD="$TMP/bad.txt"
printf 'строка с нарушением: \u4e2d\u6587\n' > "$BAD"
bash "$GUARD" "$BAD" > "$TMP/b.log" 2>&1
emit TEXT_BAD_RC "$?"

# --- C: чистое дерево ------------------------------------------------------------------------
bash "$GUARD" --all > "$TMP/c.log" 2>&1
emit TEXT_CLEAN_RC "$?"

# --- что не тронуто -------------------------------------------------------------------------
# Сверка с пином пре-регистрации, а не с HEAD: правка стража уже в HEAD, и diff с ним пуст.
PIN=$(git log --format=%H --reverse -- lab/hypotheses/H-0179-text-guard-three-outcomes.md | head -1)
emit TEXT_GUARD_ONLY "$(git diff --name-only "$PIN" | grep -q '^lab/check-text-clean.sh$' && echo 1 || echo 0)"

# --- сверка ----------------------------------------------------------------------------------
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
done < lab/expectations/e0179.tsv
echo "WORST_RC=$WORST"

SNAP="$(git rev-parse HEAD)|$(git status --porcelain | sha256sum | cut -c1-16)"
STABLE_FILE=/tmp/e0179-stable.txt
if [ -f "$STABLE_FILE" ] && [ "$(cat "$STABLE_FILE")" = "$SNAP" ]; then
  echo "STABLE=1"
else
  printf '%s' "$SNAP" > "$STABLE_FILE"
  echo "STABLE=0"
fi
