"""Проверка: внешний помощник net.py не пишет в комнату/репозиторий.

Предмет — файловая граница, а не сеть. `net.py` разбирает чужой HTML; если
разбор ошибётся, процесс не должен уметь писать вне `runs/net`. Landlock
оставляет запись только в downstream-состоянии (session.json, журнал), а
попытка записи в соседний `room/protected.txt` получает EACCES.

Плечи:
  A — после изменения fake_fetch (имитация ошибки разбора) пишет защищённый
      файл: PROTECTED_WRITE=0, errno 13; STATE_WRITE=1, session.json создан
      с результатами, журнал записан.
  B — ABI Landlock < 3: отказ fs-sandbox до сети, fetch не вызван, rc=3.
  C — прямой `net.py links` без сессии: прежний отказ no-page rc=3, барьер
      не ломает штатный путь и не оставляет __pycache__ в репозитории.
  D — тот же probe в каталоге рядом с репозиторием (в WSL это /mnt/c, 9p):
      Landlock там не узнаёт существующие inode, поэтому журнал и сессия
      пишутся через fd, открытые до барьера. Проверяется, что защищённая
      запись всё равно отвергнута, а журнал и session.json записаны.
  E — прямой `net.py links` в том же 9p-дереве: отказ no-page rc=3,
      журнал пополняется, __pycache__ не появляется.

Windows: делегирует в WSL Ubuntu. Windows-барьер — low-IL (C-0330), здесь
не эмулируется; этот тест про Landlock.

    python tests/test_net_fs_write_barrier.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[bool, str]] = []

PROBE = '''\
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "bin"))
import net

net.STATE = root / "runs" / "net"
net.SESSION = net.STATE / "session.json"
net.JOURNAL = net.STATE / "net.jsonl"
protected = root / "room" / "protected.txt"
DIRECT_STATE = __DIRECT_STATE__

print("SANDBOX=" + ("present" if hasattr(net, "apply_fs_sandbox") else "absent"))


def fake_fetch(url, max_bytes, timeout, form=None):
    try:
        protected.write_text("PWNED", encoding="utf-8")
        print("PROTECTED_WRITE=1")
    except OSError as error:
        print("PROTECTED_WRITE=0")
        print("PROTECTED_ERRNO=%s" % error.errno)
    return ('<a class="result__a" href="https://example.com">X</a>', 10, False)


net.fetch = fake_fetch
rc = net.main(["search", "probe"])
print("RC=%d" % rc)
if DIRECT_STATE:
    try:
        (net.STATE / "after.txt").write_text("state", encoding="utf-8")
        print("STATE_WRITE=1")
    except OSError as error:
        print("STATE_WRITE=0")
        print("STATE_ERRNO=%s" % error.errno)
try:
    print("JOURNAL=%s" % (1 if '"cmd": "search"' in
                          net.JOURNAL.read_text(encoding="utf-8") else 0))
except OSError:
    print("JOURNAL=0")
try:
    saved = json.loads(net.SESSION.read_text(encoding="utf-8"))
    print("SESSION_RESULTS=%d" % len(saved.get("results") or []))
except (OSError, ValueError):
    print("SESSION_RESULTS=-1")
print("PROTECTED_TEXT=%r" % protected.read_text(encoding="utf-8"))
'''

ABI_PROBE = '''\
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "bin"))
import net

net.STATE = root / "runs" / "net"
net.SESSION = net.STATE / "session.json"
net.JOURNAL = net.STATE / "net.jsonl"
net._landlock_abi = lambda libc: 0


def fake_fetch(*args, **kwargs):
    print("FETCH_CALLED=1")
    return ("", 0, False)


net.fetch = fake_fetch
rc = net.main(["search", "probe"])
print("RC=%d" % rc)
'''


def check(flag: bool, message: str) -> None:
    RESULTS.append((flag, message))


def tree(base: Path | None = None) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="herness-net-fs-", dir=base))
    (tmp / "bin").mkdir()
    shutil.copy2(ROOT / "bin" / "net.py", tmp / "bin" / "net.py")
    shutil.copy2(ROOT / "bin" / "net_policy.py", tmp / "bin" / "net_policy.py")
    (tmp / "runs" / "net").mkdir(parents=True)
    (tmp / "room").mkdir()
    (tmp / "room" / "protected.txt").write_text("original\n", encoding="utf-8")
    return tmp


def run_probe(tmp: Path, direct: bool = True) -> str:
    probe = tmp / "probe.py"
    probe.write_text(PROBE.replace("__DIRECT_STATE__", str(direct)), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-B", str(probe)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(tmp), timeout=60,
    )
    return (result.stdout or "") + (result.stderr or "")


def run_abi_probe(tmp: Path) -> str:
    probe = tmp / "probe_abi.py"
    probe.write_text(ABI_PROBE, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-B", str(probe)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(tmp), timeout=60,
    )
    return (result.stdout or "") + (result.stderr or "")


def run_tests() -> int:
    tmp = tree()
    try:
        output = run_probe(tmp)
        print("A: вывод probe")
        print(output.strip() or "(пусто)")
        check("SANDBOX=present" in output, "A: барьер apply_fs_sandbox присутствует")
        check("PROTECTED_WRITE=0" in output, "A: запись в room/protected.txt отвергнута")
        check("PROTECTED_ERRNO=13" in output, "A: отказ записи — EACCES (errno 13)")
        check("PROTECTED_WRITE=1" not in output, "A: в выводе нет успешной защищённой записи")
        check("STATE_WRITE=1" in output, "A: запись в runs/net разрешена")
        check("JOURNAL=1" in output, "A: журнал записан внутри разрешённого пути")
        check("SESSION_RESULTS=1" in output,
              "A: session.json создан и содержит результаты")
        check("RC=0" in output, "A: штатный путь search завершился rc=0")
        check((tmp / "room" / "protected.txt").read_text(encoding="utf-8") == "original\n",
              "A: защищённый файл не изменён")

        abi = run_abi_probe(tmp)
        print("B: вывод probe с ABI=0")
        print(abi.strip() or "(пусто)")
        check("ОТКАЗ fs-sandbox" in abi, "B: старый ABI отвергнут кодом fs-sandbox")
        check("FETCH_CALLED=1" not in abi, "B: при отказе fetch не вызван")
        check("RC=3" in abi, "B: отказ возвращает rc=3")

        direct = subprocess.run(
            [sys.executable, str(tmp / "bin" / "net.py"), "links"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(tmp), timeout=60,
        )
        text = (direct.stdout or "") + (direct.stderr or "")
        print("C: вывод net.py links")
        print(text.strip() or "(пусто)")
        check(direct.returncode == 3, f"C: links без сессии — rc=3 (получено {direct.returncode})")
        check("no-page" in text, "C: причина отказа — no-page, а не падение барьера")
        journal_text = (tmp / "runs" / "net" / "net.jsonl").read_text(
            encoding="utf-8", errors="replace") if (tmp / "runs" / "net" / "net.jsonl").exists() else ""
        check('"cmd": "links"' in journal_text, "C: журнал пополнен после прямого запуска")
        check(not (tmp / "bin" / "__pycache__").exists(),
              "C: импорт политики не оставил __pycache__ в репозитории")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    base = ROOT.parent
    tmp9p = tree(base)
    try:
        output = run_probe(tmp9p, direct=False)
        print("D: вывод probe на каталоге рядом с репозиторием (WSL: 9p)")
        print(output.strip() or "(пусто)")
        check("SANDBOX=present" in output, "D: барьер apply_fs_sandbox присутствует")
        check("PROTECTED_WRITE=0" in output, "D: запись в room/protected.txt отвергнута")
        check("PROTECTED_ERRNO=13" in output, "D: отказ записи — EACCES (errno 13)")
        check("JOURNAL=1" in output, "D: журнал записан через fd, открытый до барьера")
        check("SESSION_RESULTS=1" in output,
              "D: session.json переписан через fd и содержит результаты")
        check("RC=0" in output, "D: штатный путь search завершился rc=0")
        check((tmp9p / "room" / "protected.txt").read_text(encoding="utf-8") == "original\n",
              "D: защищённый файл не изменён")

        direct = subprocess.run(
            [sys.executable, str(tmp9p / "bin" / "net.py"), "links"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(tmp9p), timeout=60,
        )
        text = (direct.stdout or "") + (direct.stderr or "")
        print("E: вывод net.py links в 9p-дереве")
        print(text.strip() or "(пусто)")
        check(direct.returncode == 3, f"E: links без страницы — rc=3 (получено {direct.returncode})")
        check("no-page" in text, "E: причина отказа — no-page, а не падение записи")
        journal_path = tmp9p / "runs" / "net" / "net.jsonl"
        journal_text = journal_path.read_text(
            encoding="utf-8", errors="replace") if journal_path.exists() else ""
        check('"cmd": "links"' in journal_text, "E: журнал пополнен на 9p")
        check(not (tmp9p / "bin" / "__pycache__").exists(),
              "E: импорт политики не оставил __pycache__ на 9p")
    finally:
        shutil.rmtree(tmp9p, ignore_errors=True)

    failed = 0
    for flag, message in RESULTS:
        print(f"[{'ok' if flag else 'FAIL'}] {message}")
        failed += 0 if flag else 1
    print(f"провалов: {failed}")
    if failed:
        print("ВЕРДИКТ: FAIL — внешний помощник пишет вне runs/net или барьер ломает штатный путь")
        return 1
    print("ВЕРДИКТ: PASS — запись внешнего ограничена runs/net (в т.ч. fd на 9p); старый ABI отвергнут до сети")
    return 0


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = str(resolved).replace("\\", "/")[len(resolved.drive):]
    return f"/mnt/{drive}{rest}"


def delegate_wsl() -> int:
    if shutil.which("wsl") is None:
        print("N/A: WSL не найден, срез не выполнен")
        return 2
    script = wsl_path(Path(__file__).resolve())
    result = subprocess.run(
        ["wsl", "-d", "Ubuntu", "--exec", "python3", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240,
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def main() -> int:
    if not sys.platform.startswith("linux"):
        return delegate_wsl()
    return run_tests()


if __name__ == "__main__":
    raise SystemExit(main())
