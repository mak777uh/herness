#!/usr/bin/env bash
# e0166-run.sh — носитель R2/H-0166: `PublishAck` привязан к запросу и подписан.
# PIN — коммит, внёсший карточку H-0166 (пре-регистрация): по нему берутся старые продуктовые
# файлы. PRE_FIX — `git checkout <пин> -- …` с trap-возвратом на HEAD. Как и в E-0163/E-0164/E-0165:
# правка обязана быть закоммичена ДО прогона, иначе trap вернёт дерево на HEAD и сотрёт её.
#
# Формат кадра меняется — это и есть предмет карточки, поэтому `WIRE_TOUCHED` здесь равен 1, а не 0:
# заморожен нулём только durable-формат WAL (`WAL_FORMAT_TOUCHED`).
# Урок E-0165 учтён: `grep -c` считает СТРОКИ, поэтому каждый факт, построенный на нём, либо
# сведён к паре 0/1, либо измеряется по диапазону, где имя обязано встретиться ровно на одной
# строке.
set -u
cd "$(dirname "$0")/.."
PIN=$(git log --format=%H --reverse -- lab/hypotheses/H-0166-publish-ack-binding.md | head -1)
WIRE=crates/vecdht-wire/src/messages.rs
FRAME=crates/vecdht-wire/src/frame.rs
IDS=crates/vecdht-crypto/src/ids.rs
NODE=crates/vecdht-node/src/node.rs
AGENT=crates/vecdht-net/src/agent.rs
CLIW=crates/vecdht-cli/src/wire_cmd.rs
PRODUCT="$WIRE $FRAME $IDS $NODE $AGENT $CLIW"
TEST_NODE=crates/vecdht-node/tests/r2_publish_ack_binding.rs
TEST_NET=crates/vecdht-net/tests/r2_stale_ack.rs
GOLDEN=crates/vecdht-wire/tests/golden_vectors.rs
TMP=$(mktemp -d)
trap 'git checkout -q HEAD -- $PRODUCT; rm -rf "$TMP"' EXIT
: > "$TMP/facts"
emit() { printf '%s\t%s\n' "$1" "$2" | tee -a "$TMP/facts"; }
bool_rc() { if [ "$1" -eq 0 ]; then echo 0; else echo 1; fi; }

# Поле привязки: только объявление в структуре `PublishAck`. Диапазон awk ограничен телом
# структуры, поэтому «1» означает ровно одно поле, а не «имя встретилось в файле N раз».
digest_field() { awk '/pub struct PublishAck/,/^}$/' "$1" | grep -c 'publish_digest'; }
# Число обязательных подписанных видов: список матчится по телу `signature_required`,
# `sort -u` снимает дубли (имя вида могло встретиться в комментарии внутри тела).
sig_arms() { awk '/pub fn signature_required/,/^    }$/' "$1" \
  | grep -oE 'Kind::[A-Za-z]+' | sort -u | wc -l; }
# Как выпускается ack: внутри `publish_ack_frame` обязана быть ровно одна строка с `encode_signed`.
ack_signed_emit() { awk '/fn publish_ack_frame/,/^    }$/' "$1" | grep -c 'encode_signed'; }
# Переснят ли вектор `PublishAck`: изменённая не-комментарная строка файла векторов, содержащая
# имя нового поля. Число изменённых строк таблицей не заморожено — оно зависит от формы записи.
golden_ack_reshot() {
  n=$(git diff -U0 "$PIN" -- "$GOLDEN" | grep -E '^[+-]' | grep -vE '^\+\+\+|^---' \
      | grep -vE '^[+-][[:space:]]*//' | grep -icE 'publish_digest' | head -1)
  if [ "$n" -ge 1 ]; then echo 1; else echo 0; fi
}
# Устаревшее утверждение о числе подписанных видов: «подписанных 13» обязано исчезнуть из кода.
sig13_claim() { grep -rn 'подписанных 13' crates --include='*.rs' | wc -l; }

emit PIN_FOUND "$(git cat-file -e "$PIN^{commit}" 2>/dev/null && echo 1 || echo 0)"
# Таблица и карточка обязаны войти одним коммитом: иначе порог цикла поднят после пре-регистрации.
emit PIN_HASEXPECT "$([ "$(git log --format=%H --reverse -- lab/expectations/e0166.tsv | head -1)" = "$PIN" ] && echo 1 || echo 0)"

git checkout -q "$PIN" -- $PRODUCT
emit PRE_FIX_DIGEST_FIELD "$(digest_field "$WIRE")"
emit PRE_FIX_SIGNED_ARMS "$(sig_arms "$FRAME")"
emit PRE_FIX_ACK_SIGNED_EMIT "$(ack_signed_emit "$NODE")"
cargo test -q -p vecdht-node --test r2_publish_ack_binding > "$TMP/pre_node.log" 2>&1; r=$?
emit PRE_FIX_NODE_TEST_RC "$(bool_rc $r)"
cargo test -q -p vecdht-net --test r2_stale_ack > "$TMP/pre_net.log" 2>&1; r=$?
emit PRE_FIX_NET_TEST_RC "$(bool_rc $r)"
git checkout -q HEAD -- $PRODUCT

emit POST_FIX_DIGEST_FIELD "$(digest_field "$WIRE")"
emit POST_FIX_SIGNED_ARMS "$(sig_arms "$FRAME")"
emit POST_FIX_ACK_SIGNED_EMIT "$(ack_signed_emit "$NODE")"
cargo test -q -p vecdht-node --test r2_publish_ack_binding > "$TMP/post_node.log" 2>&1; r=$?
emit ACK_TEST_RC "$(bool_rc $r)"
emit ACK_CASES "$(grep -c '#\[test\]' "$TEST_NODE")"
emit ACK_PASS "$(grep -oE 'test result: ok\. [0-9]+ passed' "$TMP/post_node.log" | grep -oE '[0-9]+' | head -1)"
cargo test -q -p vecdht-net --test r2_stale_ack > "$TMP/post_net.log" 2>&1; r=$?
emit NET_TEST_RC "$(bool_rc $r)"
emit NET_CASES "$(grep -c '#\[test\]' "$TEST_NET")"
emit NET_PASS "$(grep -oE 'test result: ok\. [0-9]+ passed' "$TMP/post_net.log" | grep -oE '[0-9]+' | head -1)"

cargo test -q -p vecdht-net --test transport > "$TMP/transport.log" 2>&1; r=$?
emit TRANSPORT_RC "$(bool_rc $r)"
cargo test -q -p vecdht-node --test s94_tail > "$TMP/s94.log" 2>&1; r=$?
emit S94_TAIL_RC "$(bool_rc $r)"
cargo test -q -p vecdht-node --test gates_p4 > "$TMP/p4.log" 2>&1; r=$?
emit GATES_P4_RC "$(bool_rc $r)"
cargo test -q -p vecdht-node --test w2r3_stale_read > "$TMP/w2r3.log" 2>&1; r=$?
emit W2R3_RC "$(bool_rc $r)"
cargo test -q -p vecdht-wire --test golden_vectors > "$TMP/golden.log" 2>&1; r=$?
emit GOLDEN_VECTORS_RC "$(bool_rc $r)"
cargo test -q -p vecdht-wire --test fuzz_decode > "$TMP/fuzz.log" 2>&1; r=$?
emit FUZZ_DECODE_RC "$(bool_rc $r)"
cargo test -q -p vecdht-cli --lib > "$TMP/cli_lib.log" 2>&1; r=$?
emit CLI_LIB_RC "$(bool_rc $r)"
cargo test -q -p vecdht-cli --test cli > "$TMP/cli_integ.log" 2>&1; r=$?
emit CLI_INTEG_RC "$(bool_rc $r)"

emit GOLDEN_ACK_RESHOT "$(golden_ack_reshot)"
emit SIG13_CLAIM "$(sig13_claim)"
emit WIRE_TOUCHED "$(git diff --name-only "$PIN" | grep -q '^crates/vecdht-wire/' && echo 1 || echo 0)"
emit WAL_FORMAT_TOUCHED "$(git diff --name-only "$PIN" | grep -c '^crates/vecdht-index/src/wal.rs')"
emit SPEC_TOUCHED "$(git diff --name-only "$PIN" | grep -c '^docs/VecDHT-SPEC-v8.md')"
emit PRODUCT_TOUCHED "$(git diff --name-only "$PIN" | grep -q '^crates/vecdht-node/src/' && echo 1 || echo 0)"
emit SPEC_RULE "$(grep -cF 'привязано к телу принятого' docs/VecDHT-SPEC-v8.md)"

python lab/check-guard-selftests.py > /dev/null 2>&1; emit GSE_EXIT "$(bool_rc $?)"
python lab/check-contour-parity.py > /dev/null 2>&1; emit PARITY_EXIT "$(bool_rc $?)"
python lab/check-contours.py > /dev/null 2>&1; emit CONTOURS_EXIT "$(bool_rc $?)"
python lab/check-expect-freeze.py > /dev/null 2>&1; emit EXPECT_FREEZE_EXIT "$(bool_rc $?)"
bash lab/check-text-clean.sh --all > /dev/null 2>&1; emit TEXT_EXIT "$(bool_rc $?)"
python lab/check-claims.py > /dev/null 2>&1; emit CLAIMS_EXIT "$(bool_rc $?)"
bash lab/check-spec-mirror.sh > /dev/null 2>&1; emit SPEC_MIRROR_EXIT "$(bool_rc $?)"
python lab/check-ci-numbers.py > /dev/null 2>&1; emit CIN_EXIT "$(bool_rc $?)"
disk=$(bash lab/disk-report.sh 2>/dev/null | head -1)
case "$disk" in DISK_FREE_MB=*) emit DISK_READABLE 1;; *) emit DISK_READABLE 0;; esac

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
done < lab/expectations/e0166.tsv
echo "WORST_RC=$WORST"

SNAP="$(git rev-parse HEAD)|$(git status --porcelain | sha256sum | cut -c1-16)"
STABLE_FILE=/tmp/e0166-stable.txt
if [ -f "$STABLE_FILE" ] && [ "$(cat "$STABLE_FILE")" = "$SNAP" ]; then
  echo "STABLE=1"
else
  printf '%s' "$SNAP" > "$STABLE_FILE"
  echo "STABLE=0"
fi
