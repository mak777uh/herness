#!/usr/bin/env bash
# e0178-run.sh — носитель H-0178: NODE_READY объявляет адрес, по которому узел принимает входящие.
#
# PIN — коммит, внёсший карточку H-0178 (пре-регистрация). По нему берутся старые service.rs и
# node_cmd.rs для PRE_FIX. Возврат — trap'ом, поэтому правка обязана быть закоммичена ДО прогона:
# иначе trap вернёт дерево на HEAD и сотрёт её (как в E-0163/E-0164/E-0165).
#
# Требует Linux-бинарь: Windows-бинарь не читает POSIX-пути `/mnt/...` и на этом стенде даёт
# «Не удается найти указанный файл» на существующем members.txt. Поэтому носитель проверяет
# платформу и отказывает с причиной, а не падает молча.
set -u
cd "$(dirname "$0")/.." || exit 1
export RUSTUP_HOME="${RUSTUP_HOME:-/root/.rustup2}"

PIN=$(git log --format=%H --reverse -- lab/hypotheses/H-0178-node-ready-address.md | head -1)
SVC=crates/vecdht-net/src/service.rs
NODE=crates/vecdht-cli/src/node_cmd.rs
TEST=crates/vecdht-cli/tests/node_listen_advertise.rs
CLI=target/release/vecdht-cli
TMP=$(mktemp -d)
trap 'git checkout -q HEAD -- "$SVC" "$NODE"; git checkout -q HEAD -- "$TEST" 2>/dev/null; rm -rf "$TMP"' EXIT
: > "$TMP/facts"
emit() { printf '%s\t%s\n' "$1" "$2" | tee -a "$TMP/facts"; }
bool_rc() { if [ "$1" -eq 0 ]; then echo 0; else echo 1; fi; }
ok_bool() { if [ "$1" -eq 0 ]; then echo 1; else echo 0; fi; }

# Платформа: носитель мерит Linux-бинарь. Windows-бинарь на этом стенде не читает `/mnt/...`.
case "$(uname -s)" in
  Linux) emit PLATFORM_OK 1 ;;
  *)     emit PLATFORM_OK 0 ;;
esac
[ -x "$CLI" ] || { echo "нет $CLI: соберите cargo build --release -p vecdht-cli"; exit 2; }

# --- PRE_FIX: на пине при --listen 0.0.0.0 объявляется loopback ------------------------------
git checkout -q "$PIN" -- "$SVC" "$NODE"
# Тест на пине не существует, и удалять его не нужно: cargo соберёт только те цели, что есть в
# дереве. Удаление через `rm -f` оставляло у cargo кэш целей без теста, и следующий
# `cargo test --test node_listen_advertise` отказывал «no test target named», то есть
# проверка не запускалась, а выглядела как провал. Это и был ложный красный первого прогона.
cargo build --release -p vecdht-cli > "$TMP/pre-build.log" 2>&1
emit PRE_BUILD_RC "$(bool_rc $?)"
D="$TMP/pre"
mkdir -p "$D"
bash lab/two-hosts.sh ceremony "$D" > "$D/ceremony.log" 2>&1
emit PRE_CEREMONY_RC "$(bool_rc $?)"
STATUS_SEC=5 RUN_SECONDS=20 bash lab/two-hosts.sh serve-bg "$D" 0 \
  /ip4/0.0.0.0/udp/7771/quic-v1 "$D/node0.log" > /dev/null 2>&1 &
pid=$!
for _ in $(seq 1 40); do grep -q NODE_READY "$D/node0.log" 2>/dev/null && break; sleep 1; done
pre_addr=$(sed -n 's/.*NODE_READY .*listen=\([^ ]*\).*/\1/p' "$D/node0.log" 2>/dev/null | head -1)
kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
case "$pre_addr" in
  *127.0.0.1*) emit PRE_FIX_WILDCARD_LOOPBACK 1 ;;
  *)           emit PRE_FIX_WILDCARD_LOOPBACK 0 ;;
esac

# --- POST_FIX: на HEAD при --listen 0.0.0.0 loopback не объявляется --------------------------
git checkout -q HEAD -- "$SVC" "$NODE"
cargo build --release -p vecdht-cli > "$TMP/post-build.log" 2>&1
emit POST_BUILD_RC "$(bool_rc $?)"
D="$TMP/post"
mkdir -p "$D"
bash lab/two-hosts.sh ceremony "$D" > "$D/ceremony.log" 2>&1
emit POST_CEREMONY_RC "$(bool_rc $?)"
STATUS_SEC=5 RUN_SECONDS=20 bash lab/two-hosts.sh serve-bg "$D" 0 \
  /ip4/0.0.0.0/udp/7771/quic-v1 "$D/node0.log" > /dev/null 2>&1 &
pid=$!
for _ in $(seq 1 40); do grep -q NODE_READY "$D/node0.log" 2>/dev/null && break; sleep 1; done
post_addr=$(sed -n 's/.*NODE_READY .*listen=\([^ ]*\).*/\1/p' "$D/node0.log" 2>/dev/null | head -1)
kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
case "$post_addr" in
  *127.0.0.1*) emit POST_FIX_WILDCARD_LOOPBACK 1 ;;
  *)           emit POST_FIX_WILDCARD_LOOPBACK 0 ;;
esac

# --- отрицательный контроль: явный loopback обязан остаться объявленным ----------------------
# Каталог узла обязан содержать церемонию: без artifact/cert/genesis узел не стартует, и
# «адрес пуст» выглядело бы как «loopback не объявлен» — то есть как провал правки, хотя это
# провал носителя. Копируем церемонию, а не создаём пустой каталог.
D="$TMP/loop"
cp -r "$TMP/post/." "$D/"
rm -f "$D"/node0.log
STATUS_SEC=5 RUN_SECONDS=20 bash lab/two-hosts.sh serve-bg "$D" 0 \
  /ip4/127.0.0.1/udp/7797/quic-v1 "$D/node0.log" > /dev/null 2>&1 &
pid=$!
for _ in $(seq 1 40); do grep -q NODE_READY "$D/node0.log" 2>/dev/null && break; sleep 1; done
loop_addr=$(sed -n 's/.*NODE_READY .*listen=\([^ ]*\).*/\1/p' "$D/node0.log" 2>/dev/null | head -1)
kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
case "$loop_addr" in
  *127.0.0.1*) emit POST_FIX_LOOPBACK_KEPT 1; emit POST_FIX_LOOPBACK_IS_LOOPBACK 1 ;;
  *)           emit POST_FIX_LOOPBACK_KEPT 0; emit POST_FIX_LOOPBACK_IS_LOOPBACK 0 ;;
esac

# --- тесты ----------------------------------------------------------------------------------
# Логи копируются в lab/logs/ до trap: иначе причина красного исчезает вместе с $TMP, и
# разбирать её приходится догадками (так и случилось на первом прогоне).
mkdir -p lab/logs
# Метаданные целей пересобираются явно: дерево успело побывать на пине без теста, и без этого
# cargo продолжает считать, что цели `node_listen_advertise` нет.
cargo clean -p vecdht-cli > /dev/null 2>&1
cargo test -q -p vecdht-cli --test node_listen_advertise > "$TMP/listen.log" 2>&1
listen_rc=$?
if [ "$listen_rc" -ne 0 ]; then cp "$TMP/listen.log" "lab/logs/e0178-listen-$(date +%s).log" 2>/dev/null; fi
emit LISTEN_TEST_RC "$(bool_rc $listen_rc)"
emit LISTEN_TEST_CASES "$(grep -c 'tokio::test' "$TEST" 2>/dev/null || echo 0)"
cargo test -q -p vecdht-net --test transport > "$TMP/transport.log" 2>&1
emit TRANSPORT_RC "$(bool_rc $?)"
bash lab/two-hosts.sh selfcheck > "$TMP/selfcheck.log" 2>&1
if grep -q '^HOSTS_OK=1' "$TMP/selfcheck.log"; then emit SELFCHECK_OK 1; else emit SELFCHECK_OK 0; fi
bash lab/two-hosts.sh remote "$TMP/remote" 127.0.0.1 \
  /ip4/0.0.0.0/udp/7781/quic-v1 /ip4/0.0.0.0/udp/7782/quic-v1 \
  /ip4/0.0.0.0/udp/7783/quic-v1 > "$TMP/remote.log" 2>&1
if grep -q '^HOSTS_REMOTE_OK=1' "$TMP/remote.log"; then emit REMOTE_OK 1; else emit REMOTE_OK 0; fi

# --- что не тронуто -------------------------------------------------------------------------
emit WIRE_TOUCHED "$(git diff --name-only "$PIN" | grep -q '^crates/vecdht-wire/' && echo 1 || echo 0)"
emit SPEC_TOUCHED "$(git diff --name-only "$PIN" | grep -c '^docs/VecDHT-SPEC-v8.md')"
emit PRODUCT_TOUCHED "$(git diff --name-only "$PIN" | grep -q '^crates/vecdht-net/src/\|^crates/vecdht-cli/src/' && echo 1 || echo 0)"
python3 lab/check-expect-freeze.py > /dev/null 2>&1; emit EXPECT_FREEZE_EXIT "$(bool_rc $?)"
PATH="$PATH:/usr/bin:/bin" bash lab/check-text-clean.sh --all > /dev/null 2>&1; emit TEXT_EXIT "$(bool_rc $?)"

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
done < lab/expectations/e0178.tsv
echo "WORST_RC=$WORST"

SNAP="$(git rev-parse HEAD)|$(git status --porcelain --untracked-files=no | sha256sum | cut -c1-16)"
STABLE_FILE=/tmp/e0178-stable.txt
if [ -f "$STABLE_FILE" ] && [ "$(cat "$STABLE_FILE")" = "$SNAP" ]; then
  echo "STABLE=1"
else
  printf '%s' "$SNAP" > "$STABLE_FILE"
  echo "STABLE=0"
fi


