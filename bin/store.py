"""store — атомарная запись состояния: временный файл, fsync, замена, fsync каталога.

Зачем: состояние (очередь заданий, реестр, артефакт покрытия) не должно теряться из-за падения
в момент записи. `Path.write_text` на месте оставляет обрезанный файл — и это не гипотеза:
процесс может умереть между `open` и `close`, а на ext4 без fsync данные могут не дойти до диска
даже после успешного `close`.

Порядок намеренный и важен:
1) пишем во временный файл в **том же каталоге** (иначе `os.replace` может оказаться копией);
2) `fsync` файла — содержимое на диске;
3) `os.replace` — атомарная подмена имени;
4) `fsync` каталога — сама запись имени тоже durable. Без шага 4 замена может не пережить падение.

Границы, а не обещания:
- На Windows каталог нельзя открыть как файл, поэтому `fsync` каталога там не выполняется —
  функция говорит это явно в `durable_dir` и не притворяется, что шаг сделан.
- Частичная запись видна только как отсутствие файла (временный файл), а не как полу-JSON.
- Ошибка пробрасывается: молча «сохранено» — худший из возможных исходов.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["write_text", "write_json", "durable_dir"]


def durable_dir() -> bool:
    """Можно ли в этом окружении сделать durable запись имени в каталоге."""
    return os.name != "nt"


def _fsync_dir(directory: Path) -> None:
    if not durable_dir():
        return
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
    """Записать текст атомарно. Возвращает путь (для удобства в вызывающем коде)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix="." + target.name + ".", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        _fsync_dir(target.parent)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target


def write_json(path: str | Path, data: Any, *, indent: int = 1) -> Path:
    """Записать JSON атомарно, с переводом строки в конце (как у остальных артефактов)."""
    text = json.dumps(data, ensure_ascii=False, indent=indent) + "\n"
    return write_text(path, text)
