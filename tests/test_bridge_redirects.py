"""BRIDGE-REDIRECT-AUTH-R1: upstream 3xx не должен уносить ключ провайдера.

Прибор поднимает in-process мост, loopback source и отдельный loopback target.
Канарейка синтетическая и не печатается. Для 301/302/303/307/308 проверяются
same-origin и cross-origin: source обязан получить ключ, target — ни одного
запроса. Обычный 200 — положительный контроль работы моста.

    python tests/test_bridge_redirects.py
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import secrets
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import bridge as bridge_module  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(flag: bool, message: str) -> None:
    RESULTS.append((bool(flag), message))


class Recorder:
    def __init__(self) -> None:
        self.records: list[dict[str, str]] = []
        self.lock = threading.Lock()

    def add(self, method: str, path: str, authorization: str) -> None:
        with self.lock:
            self.records.append({
                "method": method,
                "path": path,
                "authorization": authorization,
            })

    def clear(self) -> None:
        with self.lock:
            self.records.clear()

    def snapshot(self) -> list[dict[str, str]]:
        with self.lock:
            return list(self.records)


def handler_for(recorder: Recorder, responder, landing_recorder: Recorder | None = None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # noqa: D401 — URL и заголовки не журналируем
            return

        def _answer(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            selected = (
                landing_recorder
                if landing_recorder is not None and self.path.startswith("/landing/")
                else recorder
            )
            selected.add(method, self.path, self.headers.get("Authorization", ""))
            status, headers, payload = responder(method, self.path)
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            self.close_connection = True

        def do_POST(self) -> None:  # noqa: N802
            self._answer("POST")

        def do_GET(self) -> None:  # noqa: N802
            self._answer("GET")

    return Handler


@contextlib.contextmanager
def serving(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def post_bridge(port: int, local_token: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=b'{"probe": true}',
        headers={
            "Authorization": f"Bearer {local_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as error:
        try:
            return int(error.code), error.read()
        finally:
            error.close()


def main() -> int:
    canary = "hs-redirect-" + secrets.token_hex(12)
    local_token = "hs-local-" + secrets.token_hex(12)
    authorization = f"Bearer {canary}"
    print(f"канарейка: sha256:{hashlib.sha256(canary.encode()).hexdigest()[:16]} (значение не печатается)")

    source_records = Recorder()
    target_records = Recorder()
    source_state = {"status": 302, "location": ""}

    def source_response(_method: str, path: str) -> tuple[int, dict[str, str], bytes]:
        if path.startswith("/landing/"):
            return 200, {}, b'{"role": "redirect-target"}'
        headers = {}
        if source_state["location"]:
            headers["Location"] = source_state["location"]
        return source_state["status"], headers, b'{"role": "source"}'

    def target_response(_method: str, _path: str) -> tuple[int, dict[str, str], bytes]:
        return 200, {}, b'{"role": "redirect-target"}'

    stdout = io.StringIO()
    stderr = io.StringIO()
    responses: list[bytes] = []
    locations: list[str] = []

    with tempfile.TemporaryDirectory(prefix="herness-redirect-auth-") as work:
        log_path = Path(work) / "bridge.log"
        bridge = bridge_module.Bridge(
            upstream="http://127.0.0.1:9/v1/chat/completions",
            provider_key=canary,
            local_token=local_token,
            log_path=log_path,
            session="redirect-auth-test",
        )
        with (
            serving(handler_for(source_records, source_response, target_records)) as source_server,
            serving(handler_for(target_records, target_response)) as target_server,
            serving(bridge_module.make_handler(bridge)) as bridge_server,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            source_origin = f"http://127.0.0.1:{source_server.server_port}"
            target_origins = {
                "same-origin": source_origin,
                "cross-origin": f"http://localhost:{target_server.server_port}",
            }
            for status in (301, 302, 303, 307, 308):
                for scope, target_origin in target_origins.items():
                    source_records.clear()
                    target_records.clear()
                    source_state["status"] = status
                    source_state["location"] = f"{target_origin}/landing/{status}/{scope}"
                    locations.append(source_state["location"])
                    bridge.upstream = f"{source_origin}/v1/chat/completions"

                    response_status, payload = post_bridge(bridge_server.server_port, local_token)
                    responses.append(payload)
                    source_seen = source_records.snapshot()
                    target_seen = target_records.snapshot()
                    label = f"{status} {scope}"
                    check(
                        sum(record["authorization"] == authorization for record in source_seen) == 1,
                        f"{label}: source получил Authorization ровно один раз",
                    )
                    check(not target_seen, f"{label}: redirect target не получил запросов")
                    check(
                        not any(record["authorization"] for record in target_seen),
                        f"{label}: redirect target не получил Authorization",
                    )
                    check(response_status == 502, f"{label}: мост отказал 502 (получено {response_status})")
                    try:
                        refusal = json.loads(payload.decode("utf-8")).get("error")
                    except (ValueError, AttributeError):
                        refusal = None
                    check(
                        refusal == "upstream redirect refused",
                        f"{label}: ответ содержит фиксированную причину отказа",
                    )

            source_records.clear()
            target_records.clear()
            source_state["status"] = 200
            source_state["location"] = ""
            bridge.upstream = f"{source_origin}/v1/chat/completions"
            response_status, payload = post_bridge(bridge_server.server_port, local_token)
            responses.append(payload)
            check(response_status == 200, f"обычный upstream: мост ответил 200 (получено {response_status})")
            check(
                sum(record["authorization"] == authorization for record in source_records.snapshot()) == 1,
                "обычный upstream: source получил Authorization (положительный контроль)",
            )
            check(not target_records.snapshot(), "обычный upstream: redirect target не использован")

            log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
            output_text = stdout.getvalue() + stderr.getvalue()
            response_text = b"\n".join(responses).decode("utf-8", "replace")
            channels = {
                "ответы моста": response_text,
                "bridge.log": log_text,
                "stdout/stderr": output_text,
            }
            for name, text in channels.items():
                check(canary not in text, f"{name}: канарейка отсутствует")
                check("Location" not in text, f"{name}: заголовок Location отсутствует")
                check(
                    all(location not in text for location in locations),
                    f"{name}: redirect target отсутствует",
                )

    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
    failed = sum(1 for flag, _ in RESULTS if not flag)
    print(f"провалов: {failed}")
    print("ВЕРДИКТ: " + ("PASS — upstream redirects запрещены, ключ не перенесён"
                           if not failed else "FAIL — граница redirect/Authorization не закрыта"))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
