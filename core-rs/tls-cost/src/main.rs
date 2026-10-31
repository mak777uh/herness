fn main() {
    let config = rustls::ClientConfig::builder()
        .with_root_certificates(rustls::RootCertStore::empty())
        .with_no_client_auth();
    let server = "example.com".try_into().unwrap();
    match rustls::ClientConnection::new(std::sync::Arc::new(config), server) {
        Ok(_) => println!("tls: соединение создано"),
        Err(error) => println!("tls: ошибка {error}"),
    }
}
