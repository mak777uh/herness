//! R2 / H-0166: `PublishAck` привязан к тому запросу, на который он отвечает.
//!
//! Узел подтверждает durable-запись кадром, в котором нет ни `query_id`, ни отпечатка запроса:
//! агент различает ответы только парой `(shard, epoch)` (`wait_publish_result`), а две попытки
//! одного агента на одном шарде в одной эпохе под этот фильтр попадают одинаково. Значит
//! опоздавшее подтверждение первой попытки может быть принято за подтверждение второй — агент
//! объявит durable запись, которую не писал.
//!
//! Контракт здесь формулирует сам тест, и он сформулирован байтами, а не новым полем: тело
//! `PublishAck` обязано заканчиваться 32-байтным отпечатком канонического тела того `Publish`,
//! на который это ответ, — `blake3(b"vecdht/v8/publish_body" ‖ body)`. Отпечаток считается на
//! месте, из байтов, и ни один новый символ продукта тесту не нужен: он краснеет на пине и
//! зеленеет после правки, не меняясь.
//!
//! Второй обязательный признак — подпись. Подтверждение выдаёт узел, и агент обязан проверить
//! её ключом пира, а не принять неподписанный кадр: до правки `PublishAck` в матрице §5.3
//! числится неподписанным.
//!
//! Кворум собирается вручную, как в `future_epoch_lease_freeze.rs`: `W=2` из `R=3`, доставка
//! адресованная, таймеров нет.

use std::collections::BTreeMap;
use std::path::PathBuf;

use blake3::Hasher;
use vecdht_crypto::{verify_body, Identity};
use vecdht_index::testing::{dir, remove};
use vecdht_node::candidates;
use vecdht_node::net::{Addr, Envelope};
use vecdht_node::{testing, Clock, ShardNode};
use vecdht_wire::frame::{decode_frame, Kind};
use vecdht_wire::messages::{domain, Codec, Publish, PublishAck};

const SHARD: u16 = 7;
const CLUSTER: u16 = 112;
const SEEDS: [u8; 3] = [1, 2, 3];
const POW: u32 = 8;
const TTL: u16 = 225;

/// Домен отпечатка тела — тот же стиль, что у `DOMAIN_INTENT` и `DOMAIN_ENTRY_KEY` (§6.5):
/// без домена один и тот же байтовый вход давал бы тот же дайджест в другом смысле.
const BODY_DOMAIN: &[u8] = b"vecdht/v8/publish_body";

/// Длина канонического тела `PublishAck` до правки: `u16+u64+u64+u32+u8+string("OK")+u32`
/// = 2+8+8+4+1+4+4 = 31; золотой вектор `frame.publish_ack` несёт `0x1f`. Правка добавляет
/// одно поле в конце — 32 байта, и ничего больше.
const PIN_BODY_LEN: usize = 31;

/// Отпечаток, который обязан нести хвост тела `PublishAck`.
fn expected_digest(publish_body: &[u8]) -> [u8; 32] {
    let mut h = Hasher::new();
    h.update(BODY_DOMAIN);
    h.update(publish_body);
    *h.finalize().as_bytes()
}

// --- каркас: три держателя шарда и ручная доставка ------------------------------

struct Trio {
    nodes: BTreeMap<Addr, ShardNode>,
    dirs: Vec<PathBuf>,
    /// Primary эпохи 1 по детерминированному порядку (§9.3) и две реплики.
    p: Addr,
    q: Addr,
    r: Addr,
}

impl Trio {
    /// Три узла с принятым genesis эпохи 1. Роль primary тест не назначает: узел выводит её
    /// из ростера, и публикация не-owner получила бы `NOT_OWNER` — отказ маршрута вместо замера.
    fn open(tag: &str) -> Trio {
        let params = testing::params(POW);
        let mut nodes = BTreeMap::new();
        let mut by_key: BTreeMap<[u8; 32], Addr> = BTreeMap::new();
        let mut dirs = Vec::new();
        for seed in SEEDS {
            let d = dir(&format!("{tag}-{seed}"));
            dirs.push(d.clone());
            let n = testing::node(&d, SHARD, seed, params, &SEEDS);
            by_key.insert(testing::identity(seed).pubkey(), n.me());
            nodes.insert(n.me(), n);
        }
        let genesis = testing::signed_frame(&testing::genesis_update(SHARD, &SEEDS, 0));
        let carrier = testing::identity(9).pubkey();
        let addrs: Vec<Addr> = nodes.keys().copied().collect();
        for a in addrs {
            nodes
                .get_mut(&a)
                .expect("узел из карты")
                .on_frame(carrier, &genesis, testing::clock(0))
                .expect("genesis эпохи 1 принимается каждым узлом");
        }
        let owners: Vec<[u8; 32]> = candidates::ordered(1, SHARD, &testing::holders(&SEEDS))
            .iter()
            .map(|c| c.owner_ed25519)
            .collect();
        let p = *by_key.get(&owners[0]).expect("primary эпохи 1 — один из тестовых сидов");
        let q = *by_key.get(&owners[1]).expect("второй держатель — один из тестовых сидов");
        let r = *by_key.get(&owners[2]).expect("третий держатель — один из тестовых сидов");
        assert!(nodes[&p].is_primary(), "P обязан быть primary эпохи 1");
        assert!(!nodes[&q].is_primary(), "Q — реплика");
        Trio { nodes, dirs, p, q, r }
    }

    fn node(&self, addr: Addr) -> &ShardNode {
        self.nodes.get(&addr).expect("узел из карты")
    }

    fn node_mut(&mut self, addr: Addr) -> &mut ShardNode {
        self.nodes.get_mut(&addr).expect("узел из карты")
    }

    /// Разнести ответы по адресатам; кадр, адресованный не члену тройки, — авария теста.
    fn route(&mut self, from: Addr, envs: &[Envelope], now: Clock) -> Vec<Envelope> {
        let mut out = Vec::new();
        for e in envs {
            let kind = kind_of(e);
            let node = self
                .nodes
                .get_mut(&e.to)
                .unwrap_or_else(|| panic!("кадр {kind:?} адресован узлу, которого нет в тройке"));
            match node.on_frame(from, &e.frame, now) {
                Ok(replies) => out.extend(replies),
                Err(err) => panic!("{kind:?} сломал узел: {err}"),
            }
        }
        out
    }

    fn clean(mut self) {
        // Сначала закрываем store, потом каталоги: на Windows удаление файла с открытым handle
        // молча не срабатывает, и temp забивается после прогона.
        self.nodes.clear();
        for d in &self.dirs {
            remove(d);
        }
    }
}

fn kind_of(e: &Envelope) -> Kind {
    decode_frame(&e.frame).expect("узел обязан отдавать разбираемые кадры").header.kind
}

fn ack_envs(envs: &[Envelope]) -> Vec<Envelope> {
    envs.iter().filter(|e| kind_of(e) == Kind::PublishAck).cloned().collect()
}

/// Подписанный кадр `Publish` по готовой структуре.
fn publish_frame(agent: &Identity, msg: &Publish) -> Vec<u8> {
    let sig = agent.sign_body(domain::PUBLISH, Kind::Publish, &msg.body_bytes());
    msg.encode_signed(&sig)
}

/// Одна попытка публикации до кворума: `Publish` на primary, `ReplicateOp` репликам,
/// `ReplicateAck` обратно — и ровно один `PublishAck` адресату. Возвращает конверт с байтами
/// подтверждения; всё остальное в сцене — средство.
fn publish_to_quorum(t: &mut Trio, agent: &Identity, msg: &Publish, bucket: u32) -> Envelope {
    let (p, q, r) = (t.p, t.q, t.r);
    let now = testing::clock(bucket);
    let out = t.node_mut(p).on_frame(agent.pubkey(), &publish_frame(agent, msg), now).expect(
        "Publish принят primary",
    );
    assert!(out.iter().all(|e| kind_of(e) == Kind::ReplicateOp), "fsync — ещё не кворум: {out:?}");
    assert_eq!(out.len(), 2, "по одному `ReplicateOp` каждой реплике");
    let to_q: Vec<Envelope> = out.iter().filter(|e| e.to == q).cloned().collect();
    let to_r: Vec<Envelope> = out.iter().filter(|e| e.to == r).cloned().collect();
    let ack_q = t.route(p, &to_q, now);
    let ack_r = t.route(p, &to_r, now);
    assert_eq!(ack_q.len(), 1, "реплика Q ответила primary");
    assert_eq!(ack_r.len(), 1, "реплика R ответила primary");
    let delivered = t.route(q, &ack_q, now);
    let late = t.route(r, &ack_r, now);
    assert!(late.is_empty(), "второе подтверждение не порождает второго ack: {late:?}");
    let acks = ack_envs(&delivered);
    assert_eq!(acks.len(), 1, "кворум W=2 обязан выдать ровно один `PublishAck`: {delivered:?}");
    assert_eq!(acks[0].to, agent.pubkey(), "подтверждение идёт адресату запроса");
    acks[0].clone()
}

/// Сцена: один агент, вектор по `seed`, бакет `bucket`, эпоха 1.
fn attempt(agent: &Identity, seed: u8, bucket: u32) -> Publish {
    let vec_q = testing::vector(seed);
    testing::PublishSpec {
        agent,
        vec_q: &vec_q,
        cluster_id: CLUSTER,
        shard: SHARD,
        epoch: 1,
        published_bucket: bucket,
        ttl_buckets: TTL,
        bits: POW,
    }
    .msg(Vec::new())
}

/// Тело подтверждения — байты кадра после заголовка.
fn body_of(env: &Envelope) -> Vec<u8> {
    decode_frame(&env.frame).expect("кадр разбирается").body.to_vec()
}

/// Хвост тела — 32 байта предполагаемого отпечатка.
fn tail_of(env: &Envelope) -> [u8; 32] {
    let body = body_of(env);
    assert!(
        body.len() >= 32,
        "тело подтверждения длиной {} короче отпечатка: привязки нет",
        body.len()
    );
    let mut d = [0u8; 32];
    d.copy_from_slice(&body[body.len() - 32..]);
    d
}

// --- замер ---------------------------------------------------------------------

/// (а) Подтверждение подписано ключом узла, а не идёт голым кадром.
#[test]
fn the_quorum_ack_is_signed_by_the_node() {
    let agent = testing::identity(60);
    let mut t = Trio::open("r2-signed");
    let msg = attempt(&agent, 3, 1);
    let ack = publish_to_quorum(&mut t, &agent, &msg, 1);
    let frame = decode_frame(&ack.frame).expect("PublishAck разбирается");
    assert!(frame.header.signed(), "`PublishAck` обязан нести флаг подписанности");
    let sig: [u8; 64] = frame
        .signature
        .expect("подпись обязательна")
        .try_into()
        .expect("подпись Ed25519 — 64 байта");
    let node_key = t.node(t.p).me();
    assert!(
        verify_body(&node_key, domain::PUBLISH_ACK, Kind::PublishAck, frame.body, &sig)
            .unwrap_or(false),
        "подтверждение обязано сходиться с ключом узла, который его выпустил"
    );
    let decoded = PublishAck::decode(&ack.frame).expect("тело подтверждения разбирается");
    assert_eq!(decoded.error_code, "OK", "успех — литерал \"OK\", а не пустой код (§5.5)");
    t.clean();
}

/// (б) Хвост тела — отпечаток тела того самого `Publish`, на который отвечают.
#[test]
fn the_ack_carries_the_digest_of_the_request_body() {
    let agent = testing::identity(61);
    let mut t = Trio::open("r2-digest");
    let msg = attempt(&agent, 4, 1);
    let body = msg.body_bytes();
    let ack = publish_to_quorum(&mut t, &agent, &msg, 1);
    let ack_body = body_of(&ack);
    assert_eq!(
        ack_body.len(),
        PIN_BODY_LEN + 32,
        "к прежним {PIN_BODY_LEN} байтам тела добавляется ровно 32-байтный отпечаток"
    );
    assert_eq!(
        &ack_body[ack_body.len() - 32..],
        &expected_digest(&body)[..],
        "отпечаток обязан считаться от канонического тела запроса, а не от пришедших байтов"
    );
    // Новое поле не меняет смысл прежних: те же `shard`/`epoch`/`seq`.
    let decoded = PublishAck::decode(&ack.frame).expect("PublishAck с отпечатком разбирается");
    assert_eq!((decoded.shard, decoded.epoch, decoded.seq), (SHARD, 1, 1));
    t.clean();
}

/// (в) Две попытки одного агента — два разных отпечатка: привязка обязательна к попытке,
/// а не к интенту и не к паре `(shard, epoch)`.
#[test]
fn two_attempts_of_the_same_agent_get_two_different_digests() {
    let agent = testing::identity(62);
    let mut t = Trio::open("r2-attempts");
    // Тот же owner, тот же шард, та же эпоха и тот же вектор: `intent_id` совпадает, поэтому
    // привязка по нему отличить попытку A от попытки B не может.
    let a = attempt(&agent, 5, 1);
    let b = attempt(&agent, 5, 3);
    assert_eq!(a.intent_id, b.intent_id, "сцена: интент тот же самый");
    assert_ne!(a.body_bytes(), b.body_bytes(), "сцена: тела попыток разные");
    let ack_a = publish_to_quorum(&mut t, &agent, &a, 1);
    let ack_b = publish_to_quorum(&mut t, &agent, &b, 3);
    let (d_a, d_b) = (tail_of(&ack_a), tail_of(&ack_b));
    assert_ne!(d_a, d_b, "отпечатки двух попыток обязаны различаться");
    assert_eq!(d_a, expected_digest(&a.body_bytes()), "первый ack привязан к первому запросу");
    assert_eq!(d_b, expected_digest(&b.body_bytes()), "второй ack привязан ко второму запросу");
    let sa = PublishAck::decode(&ack_a.frame).expect("ack A разбирается");
    let sb = PublishAck::decode(&ack_b.frame).expect("ack B разбирается");
    assert_eq!((sa.seq, sb.seq), (1, 2), "порядок попыток виден по seq");
    assert_eq!(t.node(t.p).store.len(), 1, "republish заменяет запись на месте (§6.5)");
    // Отпечаток — функция тела, а не счётчик: тот же кадр запроса даёт тот же хвост.
    assert_eq!(d_a, expected_digest(&a.body_bytes()), "отпечаток детерминирован");
    t.clean();
}

/// (г) Матрица §5.3: `PublishAck` стоит в обязательном списке, и подписанных видов — 14.
#[test]
fn the_matrix_puts_publish_ack_into_the_signed_list() {
    assert!(Kind::PublishAck.signature_required(), "`PublishAck` обязан требовать подпись");
    let signed = Kind::ALL.iter().filter(|k| k.signature_required()).count();
    assert_eq!(signed, 14, "подписанных видов кадра после правки — ровно 14");
    assert!(!Kind::Handshake.signature_required(), "handshake остаётся неподписанным видом");
}
