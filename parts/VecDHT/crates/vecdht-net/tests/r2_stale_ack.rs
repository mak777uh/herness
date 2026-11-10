//! R2 / H-0166: опоздавшее подтверждение первой попытки не засчитывается второй.
//!
//! `PublishAck` в v8 не несёт ни `query_id`, ни отпечатка запроса, и клиент различает ответы
//! только парой `(shard, epoch)` (`wait_publish_result`). Две публикации одного агента на одном
//! шарде в одной эпохе под этим фильтром неразличимы: ack от первой попытки проходит на вторую.
//! Для republish это не косметика — запись заменяется на месте (§6.5), `slot` у обеих попыток
//! один и тот же, и единственное, чем агент мог бы отличить «это подтверждение про ту запись»,
//! — привязка к телу запроса.
//!
//! Сцена построена так, чтобы опоздание было не случайностью, а единственно возможным порядком:
//! реплика не шагает, пока агент не дошёл до ожидания подтверждения, — и оба `ReplicateAck`
//! (и, следом, оба `PublishAck`) появляются только тогда, когда второй запрос уже в полёте.
//! Транспорт один, поток упорядочен: ack первой попытки arrives раньше.
//!
//! Проверка ведётся на публике: `PublishReceipt.seq` — то, что агент считает durable. У пина
//! это 1 (запись, которой у второй попытки нет), после правки — 2.

use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use libp2p::Multiaddr;
use tokio::sync::oneshot;
use tokio::task::LocalSet;
use vecdht_artifact::{reference_artifact, reference_manifest};
use vecdht_net::{
    Agent, AgentConfig, AgentError, NetConfig, NetService, NetworkParams, PublishReceipt,
    PublishRequest,
};
use vecdht_node::{candidates, testing, Clock, ShardNode};
use vecdht_wire::frame::Kind;
use vecdht_wire::messages::{domain, Codec, Publish, Role};

const SHARD: u16 = 7;
const CLUSTER: u16 = 112;
const SEEDS: [u8; 3] = [1, 2, 3];
/// Сложность эталонного артефакта: `mine_pow` клиента считает nonce именно под неё, а узел
/// отвергает любую попытку вне диапазона `pow_bits_max` своего манифеста (§11.1). Тестовая
/// «дёшева» сложность 8 для клиентского пути не годна — агент получил бы `POW_INVALID`.
const POW: u32 = 20;
const TTL: u16 = 225;

fn dir(name: &str) -> PathBuf {
    let p = std::env::temp_dir().join(format!("vecdht-r2-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&p);
    std::fs::create_dir_all(&p).expect("временный каталог теста");
    p
}

fn quic_addr() -> Multiaddr {
    "/ip4/127.0.0.1/udp/0/quic-v1".parse().expect("listen-адрес QUIC")
}

fn cfg(listen: Multiaddr) -> NetConfig {
    NetConfig {
        listen: vec![listen],
        bootstrap: Vec::new(),
        genesis_hash: testing::genesis_hash(),
        model_version: reference_manifest().model_version,
        preprocessing_version: testing::PREPROCESSING_VERSION,
        agent_version: "vecdht-r2-test/0.1".to_string(),
        request_timeout: Duration::from_secs(5),
        idle_timeout: Duration::from_secs(60),
        provider_republish: Duration::from_secs(180),
        poll_interval: Duration::from_millis(5),
        revoked_dir: None,
    }
}

fn now_sec() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).expect("часы после эпохи").as_secs()
}

/// Primary шарда по порядку §9.3 — тест не вправе назначать его первым сидом.
fn primary_seed() -> u8 {
    let order = candidates::ordered(1, SHARD, &testing::holders(&SEEDS));
    *SEEDS
        .iter()
        .find(|s| testing::identity(**s).pubkey() == order[0].owner_ed25519)
        .expect("primary — один из тестовых сидов")
}

/// Узел шарда с genesis-эпохой, применяемый на текущем бакете: lease привязан к моменту
/// применения, и узел, открытый «в 1970-м», к реальному времени шард уже не обслуживает.
fn index_service(seed: u8, dir: &Path, listen: Multiaddr) -> NetService {
    let id = testing::identity(seed);
    let peer = vecdht_net::keys::peer_id(&id);
    let mut node = ShardNode::open(
        dir,
        SHARD,
        id.clone(),
        peer.to_bytes(),
        testing::params(POW),
        testing::authority_set(),
        testing::holders(&SEEDS),
    )
    .expect("открыть узел шарда");
    let now_bucket = Clock::at(now_sec()).bucket;
    node.on_frame(
        testing::identity(9).pubkey(),
        &testing::signed_frame(&testing::genesis_update(SHARD, &SEEDS, 0)),
        testing::clock(now_bucket),
    )
    .expect("genesis");
    let cert = testing::node_cert(seed, peer.to_bytes(), vec![SHARD], Role::IndexNode, 0, u32::MAX);
    NetService::new(
        id,
        Role::IndexNode,
        Some(cert),
        vec![node],
        testing::authority_set(),
        cfg(listen),
    )
    .expect("сервис узла")
}

async fn wait_listen(s: &mut NetService) -> Multiaddr {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(10);
    loop {
        if let Some(a) = s.listen_addrs().first() {
            return a.clone();
        }
        assert!(tokio::time::Instant::now() < deadline, "listener не поднялся за 10 с");
        s.step().await;
    }
}

fn agent_network() -> NetworkParams {
    NetworkParams::from_artifact(&reference_artifact()).expect("параметры артефакта")
}

fn agent_cfg(bootstrap: Vec<Multiaddr>) -> AgentConfig {
    AgentConfig {
        bootstrap,
        listen: vec![quic_addr()],
        call_timeout: Duration::from_secs(40),
        ..AgentConfig::default()
    }
}

/// Первая попытка: кадр `Publish`, собранный руками, а не клиентом. Он обязан быть законным —
/// иначе отказ узла выдался бы за опоздание, а замер перестал бы мерить привязку.
fn attempt_frame(agent: &vecdht_crypto::Identity, vec_seed: u8) -> Publish {
    let vec_q = testing::vector(vec_seed);
    testing::PublishSpec {
        agent,
        vec_q: &vec_q,
        cluster_id: CLUSTER,
        shard: SHARD,
        epoch: 1,
        published_bucket: Clock::at(now_sec()).bucket,
        ttl_buckets: TTL,
        bits: POW,
    }
    .msg(Vec::new())
}

/// Шагать primary, пока он не применит столько записей, сколько ждём. Реплика в этом окне не
/// шагает вовсе — значит кворума нет и `PublishAck` ещё не выпущен. Ранний результат задачи
/// агента здесь — авария сцены, а не успех: до второй записи подтверждений быть не должно.
async fn pump_primary_until_applied(
    primary: &mut NetService,
    want: u64,
    rx: &mut oneshot::Receiver<Result<PublishReceipt, AgentError>>,
) {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(60);
    loop {
        let got = primary.node(SHARD).map(|n| n.applied_seq()).unwrap_or(0);
        if got >= want {
            return;
        }
        if let Ok(v) = rx.try_recv() {
            panic!("агент закончил publish раньше, чем primary применил {want} записи: {v:?}");
        }
        assert!(!rx.is_terminated(), "задача агента завершилась без результата");
        assert!(
            tokio::time::Instant::now() < deadline,
            "primary не применил {want} записей за 60 с (применено {got}); ошибки {:?}",
            primary.take_errors()
        );
        primary.step().await;
        tokio::time::sleep(Duration::from_millis(2)).await;
    }
}

/// Крутить узлы, пока фоновая задача агента не вернёт результат: агент шагает своё соединение
/// сам, узлы обязаны шагать извне.
async fn pump_nodes_until<T>(
    primary: &mut NetService,
    replica: &mut NetService,
    rx: &mut oneshot::Receiver<T>,
) -> T {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(60);
    loop {
        if let Ok(v) = rx.try_recv() {
            return v;
        }
        assert!(
            !rx.is_terminated(),
            "задача агента завершилась без результата; ошибки P={:?} R={:?}",
            primary.take_errors(),
            replica.take_errors()
        );
        assert!(
            tokio::time::Instant::now() < deadline,
            "агент не получил результат за 60 с; ошибки P={:?} R={:?}",
            primary.take_errors(),
            replica.take_errors()
        );
        primary.step().await;
        replica.step().await;
        tokio::time::sleep(Duration::from_millis(2)).await;
    }
}

#[test]
fn a_late_ack_of_an_earlier_attempt_is_not_credit_for_the_later_one() {
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    rt.block_on(async {
        let local = LocalSet::new();
        local
            .run_until(async {
                let d_primary = dir("stale-primary");
                let d_replica = dir("stale-replica");
                let p_seed = primary_seed();
                let r_seed = *SEEDS.iter().find(|s| **s != p_seed).expect("второй тестовый сид");
                let mut primary = index_service(p_seed, &d_primary, quic_addr());
                let mut replica = index_service(r_seed, &d_replica, quic_addr());
                let primary_addr = wait_listen(&mut primary).await;
                let _ = wait_listen(&mut replica).await;
                replica.dial(primary_addr.clone()).expect("dial primary репликой");

                let publisher_id = testing::identity(77);
                let mut publisher = Agent::new(
                    publisher_id.clone(),
                    agent_network(),
                    agent_cfg(vec![primary_addr.clone()]),
                )
                .expect("агент-издатель");

                let (pp, rp, ap) = (primary.peer_id(), replica.peer_id(), publisher.peer_id());
                let deadline = tokio::time::Instant::now() + Duration::from_secs(30);
                loop {
                    publisher.net_mut().step().await;
                    primary.step().await;
                    replica.step().await;
                    // Соединение primary ↔ реплика обязано быть установленным заранее: дальше
                    // реплика не шагает ни разу, и «дочитать handshake» ей будет нечем.
                    if primary.is_authenticated(&ap)
                        && publisher.net().is_authenticated(&pp)
                        && primary.is_authenticated(&rp)
                        && replica.is_authenticated(&pp)
                    {
                        break;
                    }
                    assert!(
                        tokio::time::Instant::now() < deadline,
                        "handshake не сошёлся за 30 с; ошибки P={:?}, R={:?}, агента={:?}",
                        primary.take_errors(),
                        replica.take_errors(),
                        publisher.net_mut().take_errors()
                    );
                }

                // (1) Первая попытка уходит руками. Реплику не крутим вовсе: запись будет
                // применена primary, `ReplicateOp` встанет в неотчитанное соединение, и
                // подтверждения первой попытки ещё не существует.
                let first = attempt_frame(&publisher_id, 3);
                let body = first.body_bytes();
                let sig = publisher_id.sign_body(domain::PUBLISH, Kind::Publish, &body);
                assert!(
                    publisher.net_mut().send_frame(pp, first.encode_signed(&sig)),
                    "агент аутентифицирован — кадр обязан уйти"
                );

                // (2) Вторая попытка — обычный клиентский publish того же агента на тот же шард.
                let req = PublishRequest::new(
                    testing::vector(4),
                    CLUSTER,
                    TTL,
                    testing::PREPROCESSING_VERSION,
                );
                let (tx, mut rx) = oneshot::channel();
                local.spawn_local(async move {
                    let r = publisher.publish(&req).await;
                    let _ = tx.send(r);
                });

                // (3) Ждём, пока вторая попытка будет применена: это наблюдаемое доказательство,
                // что агент уже прошёл `probe_epoch` (который выбрасывает из почты всё, кроме
                // `MatchResult`) и стоит в ожидании подтверждения. Только после этого реплика
                // начинает читать — и оба `ReplicateAck`, и оба `PublishAck` рождаются в полёте
                // второй попытки, причём первый идёт раньше: поток один и он упорядочен.
                pump_primary_until_applied(&mut primary, 2, &mut rx).await;
                assert_eq!(primary.node(SHARD).map(|n| n.store.len()), Some(1),
                    "republish заменяет запись на месте (§6.5): по slot попытки не различить");

                let receipt = pump_nodes_until(&mut primary, &mut replica, &mut rx)
                    .await
                    .expect("вторая публикация подтверждена");

                assert_eq!(
                    receipt.seq, 2,
                    "агент обязан принять подтверждение второй попытки, а не опоздавшее первой"
                );
                assert_eq!(receipt.epoch, 1);
                assert_eq!(receipt.shard, SHARD);
                assert_eq!(
                    replica.node(SHARD).map(|n| n.applied_seq()),
                    Some(2),
                    "сцена: реплика применила обе попытки — значит primary выпустил два ack, \
                     и первый пришёл агенту раньше второго"
                );
                let _ = std::fs::remove_dir_all(&d_primary);
                let _ = std::fs::remove_dir_all(&d_replica);
            })
            .await;
    });
}
