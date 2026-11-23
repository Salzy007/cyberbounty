"""Собирает публичную демо-версию для GitHub Pages: копирует web/ в docs/ (демо-режим включается сам, см. web/demo.js).
Запуск: .venv\\Scripts\\python tools\\build_pages.py, потом закоммитить и отправить на GitHub.
"""
import hashlib
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "web", ROOT / "docs"

if OUT.exists():
    shutil.rmtree(OUT)
shutil.copytree(SRC, OUT)
# версия файлов в ссылках (?v=...) ставится сама из содержимого web/: если файл изменился, адрес меняется,
# и браузеры (Chrome, Telegram, Google) не держат старую копию из кэша
h = hashlib.sha1()
for f in sorted(SRC.rglob("*")):
    if f.is_file():
        h.update(f.relative_to(SRC).as_posix().encode()); h.update(f.read_bytes())
stamp = h.hexdigest()[:8]
for page in OUT.glob("*.html"):
    text = page.read_text(encoding="utf-8")
    page.write_text(re.sub(r"(\.(?:css|js))\?v=[0-9A-Za-z]+", r"\1?v=" + stamp, text), encoding="utf-8")
print("версия файлов:", stamp)
(OUT / ".nojekyll").write_text("", encoding="utf-8")        # Pages не должен «обрабатывать» файлы
print("готово:", sum(1 for _ in OUT.rglob("*") if _.is_file()), "файлов в docs/")
