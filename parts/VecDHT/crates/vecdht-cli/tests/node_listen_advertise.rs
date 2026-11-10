//! H-0178: `NODE_READY listen=…` объявляет адрес, по которому узел реально принимает входящие.
//!
//! Дефект (замер 2026-11-10): сокет слушал `0.0.0.0:7771`, а `NODE_READY` печатал
//! `/ip4/127.0.0.1/udp/7771/quic-v1`. Причина — `service.rs` пушил адрес из `NewListenAddr` в
//! порядке событий, а `node_cmd.rs` брал первый.
//!
//! Три случая, и третий из них — отрицательный контроль правки:
//!
//! 1. `--listen 0.0.0.0` → объявленный адрес **не** loopback;
//! 2. `--listen 0.0.0.0` → объявленный порт совпадает с реально занятым;
//! 3. `--listen 127.0.0.1` → объявленный адрес **остаётся** loopback. Правка, которая вычищает
//!    loopback всегда, этот случай провалит: она сломала бы `selfcheck`, где все три узла живут
//!    на `127.0.0.1`.
//!
//! Тест идёт через `advertised_listen_addrs()` — ту же функцию, которую зовёт `node run`. Узел
//! целиком здесь не поднимается (для этого есть `two-hosts.sh`): проверяется ровно решение «какой
//! адрес объявлять», то есть предмет карточки.

use std::time::{Duration, Instant};

use libp2p::multiaddr::Protocol;
use libp2p::Multiaddr;
use vecdht_artifact::reference_manifest;
use vecdht_crypto::{AuthoritySet, Identity};
use vecdht_net::service::{NetConfig, NetService};
use vecdht_wire::messages::Role;

/// Конфигурация, повторяющая `transport.rs`: модель и preprocessing — контракт handshake (§4.2),
/// а не константа теста.
fn cfg(listen: Multiaddr) -> NetConfig {
    NetConfig {
        listen: vec![listen],
        bootstrap: Vec::new(),
        genesis_hash: [0u8; 32],
        model_version: reference_manifest().model_version,
        preprocessing_version: 1,
        agent_version: "vecdht-net-test/0.1".to_string(),
        request_timeout: Duration::from_secs(5),
        idle_timeout: Duration::from_secs(60),
        provider_republish: Duration::from_secs(180),
        poll_interval: Duration::from_millis(5),
        revoked_dir: None,
    }
}

/// Поднять сервис-агент (без шарда: предмет — слушатель, а не индекс) и дождаться, пока
/// объявленный список наполнится.
async fn service_with_listen(listen: &str) -> NetService {
    let addr: Multiaddr = listen.parse().expect("listen-адрес разбирается");
    let id = Identity::from_seed([7u8; 32]);
    let mut service = NetService::new(
        id,
        Role::Agent,
        None,
        Vec::new(),
        AuthoritySet::new(Vec::new(), 0),
        cfg(addr),
    )
    .expect("сервис поднимается");
    let deadline = Instant::now() + Duration::from_secs(10);
    while service.advertised_listen_addrs().is_empty() {
        assert!(
            Instant::now() < deadline,
            "объявленный список адресов не наполнился за 10 с при --listen {listen}"
        );
        service.step().await;
    }
    service
}

fn is_loopback(addr: &Multiaddr) -> bool {
    addr.iter().any(|p| match p {
        Protocol::Ip4(a) => a.is_loopback(),
        Protocol::Ip6(a) => a.is_loopback(),
        _ => false,
    })
}

fn udp_port(addr: &Multiaddr) -> Option<u16> {
    addr.iter().find_map(|p| match p {
        Protocol::Udp(port) => Some(port),
        _ => None,
    })
}

/// Случай 1: wildcard не объявляет loopback.
#[tokio::test]
async fn wildcard_listen_does_not_advertise_loopback() {
    let service = service_with_listen("/ip4/0.0.0.0/udp/0/quic-v1").await;
    let advertised = service.advertised_listen_addrs();
    let loopbacks: Vec<String> = advertised
        .iter()
        .filter(|a| is_loopback(a))
        .map(ToString::to_string)
        .collect();
    assert!(
        loopbacks.is_empty(),
        "при --listen 0.0.0.0 объявлен loopback {loopbacks:?}: вторая машина пойдёт на свой \
         собственный loopback и не найдёт узел (H-0178). Весь список: {advertised:?}"
    );
}

/// Случай 2: объявленный порт — тот же, что реально занят, иначе адрес бесполезен.
#[tokio::test]
async fn wildcard_listen_advertises_the_real_port() {
    let service = service_with_listen("/ip4/0.0.0.0/udp/0/quic-v1").await;
    let advertised = service.advertised_listen_addrs();
    let real_ports: Vec<u16> = service.listen_addrs().iter().filter_map(udp_port).collect();
    let advertised_ports: Vec<u16> = advertised.iter().filter_map(udp_port).collect();
    assert!(
        !advertised_ports.is_empty(),
        "объявленный список пуст: оператору нечего передать второй машине"
    );
    for port in &advertised_ports {
        assert!(
            real_ports.contains(port),
            "объявлен порт {port}, а заняты {real_ports:?} — адрес не указывает на этот узел"
        );
    }
}

/// Случай 3 (отрицательный контроль): явный loopback остаётся объявленным.
///
/// Правка, которая фильтрует loopback всегда, этот тест провалит — и это правильно: `selfcheck`
/// держит все три узла на `127.0.0.1`, и без loopback он перестал бы работать.
#[tokio::test]
async fn explicit_loopback_listen_still_advertises_loopback() {
    let service = service_with_listen("/ip4/127.0.0.1/udp/0/quic-v1").await;
    let advertised = service.advertised_listen_addrs();
    assert!(
        advertised.iter().any(is_loopback),
        "при --listen 127.0.0.1 loopback обязан остаться объявленным, иначе сломается \
         selfcheck: {advertised:?}"
    );
}
