"""Собирает публичную демо-версию для GitHub Pages: копирует web/ в docs/ (демо-режим включается сам, см. web/demo.js).
Запуск: .venv\\Scripts\\python tools\\build_pages.py, потом закоммитить и отправить на GitHub.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "web", ROOT / "docs"

if OUT.exists():
    shutil.rmtree(OUT)
shutil.copytree(SRC, OUT)
(OUT / ".nojekyll").write_text("", encoding="utf-8")        # Pages не должен «обрабатывать» файлы
print("готово:", sum(1 for _ in OUT.rglob("*") if _.is_file()), "файлов в docs/")
