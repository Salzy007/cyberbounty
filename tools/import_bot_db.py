r"""Один раз перенести брони из старой отдельной базы бота в общую базу сайта.
Запуск:  .venv\Scripts\python tools\import_bot_db.py "D:\проекты\боты\cyberbounty-bot\data\cyberbounty.db"
Брони, которые пересекаются с уже существующими, пропускаются (и печатаются). Повторный запуск безопасен."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import accounts                                   # noqa: E402
from app.config import load_settings                        # noqa: E402
from app.db import connect, init_db                         # noqa: E402


def main(old_path: str) -> None:
    settings = load_settings()
    init_db(settings.db_path)
    new, old = connect(settings.db_path), sqlite3.connect(old_path)
    old.row_factory = sqlite3.Row
    done = skipped = 0
    for b in old.execute("SELECT b.*, z.id AS zone_id, p.number FROM bookings b JOIN places p ON p.id = b.place_id JOIN zones z ON z.id = p.zone_id ORDER BY b.id"):
        user = accounts.telegram_account(new, {"id": b["telegram_id"], "first_name": b["client_name"]})
        place = new.execute("SELECT id FROM places WHERE zone_id = ? AND number = ?", (b["zone_id"], b["number"])).fetchone()
        key = b["idem_key"] if b["idem_key"] and new.execute("SELECT 1 FROM bookings WHERE user_id = ? AND idem_key = ?", (user["id"], b["idem_key"])).fetchone() is None else None
        if b["idem_key"] and key is None:
            skipped += 1                                    # уже переносили
            continue
        new.execute("BEGIN IMMEDIATE")
        clash = b["status"] == "confirmed" and new.execute(
            "SELECT 1 FROM bookings WHERE place_id = ? AND status = 'confirmed' AND start_ts < ? AND end_ts > ?",
            (place["id"], b["end_ts"], b["start_ts"])).fetchone()
        if place is None or clash:
            new.execute("ROLLBACK")
            print("пропущена (место занято):", b["id"], b["zone_id"], b["number"])
            skipped += 1
            continue
        new.execute("INSERT INTO bookings (user_id, client_name, client_phone, place_id, start_ts, end_ts, hours, price, status, idem_key,"
                    " created_ts, canceled_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (user["id"], b["client_name"], b["client_phone"], place["id"], b["start_ts"], b["end_ts"], b["hours"], b["price"],
                     b["status"], key, b["created_ts"], b["canceled_ts"]))
        new.execute("COMMIT")
        done += 1
    print(f"перенесено: {done}, пропущено: {skipped}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
