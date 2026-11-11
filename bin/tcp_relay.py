"""bin/tcp_relay.py — stdio ↔ TCP для QEMU `guestfwd`.

Зачем Python, а не hs-core. `hs-core` — Linux-бинарник для комнаты: он использует
`libc::utsname`, `libc::uname`, `libc::syscall` и на Windows не собирается вовсе (это не
регрессия, так было). А `guestfwd` нужна команда на ХОСТЕ, и хост здесь Windows.

Что делает: соединяется с мостом по адресу из аргумента, перекачивает байты в обе стороны
пока одна сторона не закроется.

Граница честности: не проверяет, кто пришёл, не ограничивает объём, обслуживает одно
соединение. Запускается только из `guestfwd` и только на 127.0.0.1.

    python bin/tcp_relay.py 127.0.0.1:8790
"""

from __future__ import annotations

import socket
import sys
import threading


def pump(source, target) -> None:
    try:
        while True:
            chunk = source.read(8192)
            if not chunk:
                break
            target.write(chunk)
            target.flush()
    except (OSError, ValueError):
        pass
    finally:
        try:
            target.close()
        except OSError:
            pass


def main(argv: list[str]) -> int:
    address = argv[0] if argv else "127.0.0.1:8790"
    host, _, port = address.rpartition(":")
    if not host or not port.isdigit():
        print(f"нужно: tcp_relay.py host:port, получено {address!r}", file=sys.stderr)
        return 2
    try:
        sock = socket.create_connection((host, int(port)), timeout=10)
    except OSError as error:
        print(f"relay: нет соединения с {address}: {error}", file=sys.stderr)
        return 1
    sock.settimeout(None)

    # Вход: stdin -> сокет. Выход: сокет -> stdout, в отдельном потоке, иначе ответ моста
    # не дойдёт, пока гость не закроет ввод.
    to_socket = sock.makefile("wb")
    from_socket = sock.makefile("rb")
    writer = threading.Thread(
        target=pump, args=(sys.stdin.buffer, to_socket), daemon=True
    )
    writer.start()
    pump(from_socket, sys.stdout.buffer)
    writer.join(timeout=1)
    try:
        sock.close()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
