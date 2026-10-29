import pathlib
import subprocess
import sys

root = pathlib.Path(r"C:\111\herness")
status = (root / "docs" / "STATUS.md").read_text(encoding="utf-8")
task = (
    "Ниже документ STATUS.md. Найди строки, которые утверждают готовность или наличие возможности, "
    "но НЕ ссылаются ни на утверждение вида C-XXXX, ни на команду, ни на тест. "
    "Ответь списком номеров строк и коротким обоснованием. Если таких строк нет — скажи это прямо.\n\n"
    + status
)

for model in sys.argv[1:]:
    print("=" * 20, model)
    result = subprocess.run(
        [sys.executable, "bin/hs.py", "live", task, "--steps", "1", "--no-tools", "--max-tokens", "4096",
         "--model", model],
        cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(result.stdout.strip()[:200])

