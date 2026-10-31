// Проба: может ли WASI запускать внешнюю программу — то, на чём стоит наш слой инструментов.
fn main() {
    println!("wasm-probe: старт");
    match std::process::Command::new("sh").arg("-c").arg("true").status() {
        Ok(status) => println!("spawn: ok, код {:?}", status.code()),
        Err(err) => println!("spawn: ошибка: {}", err),
    }
}
