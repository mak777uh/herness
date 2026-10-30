"""Перепроверка: 2607.16127 (я записал как несуществующий), 2505.03275, OSF, tamperlog, costwright."""

import json
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 herness"}


def page(url: str, limit: int = 600) -> tuple[int, str]:
    try:
        body = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
        text = body.decode("utf-8", "replace")
        title = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
        return 200, (title.group(1).strip()[:110] if title else text[:110].replace("\n", " "))
    except urllib.error.HTTPError as exc:
        return exc.code, "HTTP error"
    except Exception as exc:  # noqa: BLE001
        return 0, type(exc).__name__


CHECKS = [
    ("arXiv 2607.16127", "https://arxiv.org/abs/2607.16127"),
    ("ar5iv 2607.16127", "https://ar5iv.labs.arxiv.org/html/2607.16127"),
    ("arXiv 2505.03275", "https://arxiv.org/abs/2505.03275"),
    ("OSF MethodSeal", "https://osf.io/h64gm/"),
    ("PyPI tamperlog", "https://pypi.org/project/tamperlog/"),
    ("GitHub costwright", "https://github.com/eleata/costwright-mcp"),
]

for label, url in CHECKS:
    status, title = page(url)
    print(f"{label:<22} {status:<5} {title}")
