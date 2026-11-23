"""База данных SQLite: зоны, места, брони. Файл базы — data/cyberbounty.db (в GitHub не попадает)."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS zones (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    tagline     TEXT NOT NULL,
    price       INTEGER NOT NULL CHECK (price > 0),   -- цена за час, BYN
    open_min    INTEGER NOT NULL,                      -- открытие, минут от полуночи (600 = 10:00)
    close_min   INTEGER NOT NULL,                      -- закрытие; больше 1440 — уже следующая ночь (1560 = 02:00)
    place_word  TEXT NOT NULL,
    sort        INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS places (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id  TEXT NOT NULL REFERENCES zones(id),
    number   INTEGER NOT NULL,
    UNIQUE (zone_id, number)
);
CREATE TABLE IF NOT EXISTS users (                    -- один человек = одна строка; способы входа — колонки
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    phone        TEXT UNIQUE,                          -- только цифры, 7-15 штук
    telegram_id  INTEGER UNIQUE,                       -- вход через Telegram и mini app в боте
    email        TEXT UNIQUE,                          -- маленькими буквами
    google_sub   TEXT UNIQUE,                          -- неизменный id аккаунта Google
    created_ts   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tg_logins (                 -- вход через ссылку на бота: сайт ждёт, бот подтверждает
    token_hash   TEXT PRIMARY KEY,                     -- sha256 от секрета, который знает только браузер
    telegram_id  INTEGER,
    name         TEXT,
    expires_ts   INTEGER NOT NULL,
    expect_tg    INTEGER                               -- если вход по уже привязанному номеру: только этот Telegram
);
CREATE TABLE IF NOT EXISTS phone_logins (              -- вход по телефону: код приходит в Telegram-бот
    token_hash   TEXT PRIMARY KEY,                     -- sha256 от секрета из ссылки
    phone        TEXT NOT NULL,                        -- цифры, как введены на сайте
    name         TEXT NOT NULL,
    tg_id        INTEGER,                              -- Telegram, который подтвердил номер (кнопкой «Поделиться номером»)
    code_hash    TEXT,                                 -- sha256(token_hash:код); пусто, пока код не отправлен
    attempts     INTEGER NOT NULL DEFAULT 0,
    expires_ts   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS email_codes (               -- одноразовые коды входа по почте (хранится только хэш)
    email       TEXT PRIMARY KEY,
    code_hash   TEXT NOT NULL,
    expires_ts  INTEGER NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_ts  INTEGER NOT NULL,
    sent_log    TEXT NOT NULL DEFAULT ''               -- метки времени отправок за последний час (для лимита)
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,                      -- sha256 от cookie; сам токен в базе не хранится
    kind        TEXT NOT NULL CHECK (kind IN ('user', 'admin')),
    user_id     INTEGER,
    created_ts  INTEGER NOT NULL,
    expires_ts  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    client_name  TEXT NOT NULL,
    client_phone TEXT,
    place_id     INTEGER NOT NULL REFERENCES places(id),
    start_ts     INTEGER NOT NULL,
    end_ts       INTEGER NOT NULL,
    hours        INTEGER NOT NULL,
    price        INTEGER NOT NULL,                     -- итог, посчитан сервером на момент брони
    status       TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'canceled')),
    idem_key     TEXT,                                 -- защита от двойного нажатия
    created_ts   INTEGER NOT NULL,
    canceled_ts  INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_bookings_key ON bookings (user_id, idem_key) WHERE idem_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_bookings_place ON bookings (place_id, status, start_ts);
CREATE INDEX IF NOT EXISTS ix_bookings_user ON bookings (user_id, start_ts);
"""

# Зоны, цены и описания вымышленные (демо)
SEED_ZONES = [
    ("standard", "Standard", "RTX 4060 · 240 Hz", 6, "PC", 12),
    ("vip", "VIP", "RTX 4080 · 360 Hz · кресла", 12, "VIP", 6),
    ("tournament", "Tournament", "Турнирные столы для команд", 18, "Table", 4),
    ("lounge", "Lounge", "PlayStation 5 · диваны · 4K TV", 10, "Sofa", 4),
]
OPEN_MIN = 10 * 60
CLOSE_MIN = 26 * 60  # 02:00 следующей ночи


def connect(db_path: Path) -> sqlite3.Connection:
    # isolation_level=None: транзакциями управляем сами (BEGIN IMMEDIATE при создании брони)
    conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migrate_users(conn: sqlite3.Connection) -> None:
    """Старая таблица users (телефон обязателен, без telegram_id/email/google_sub) -> новая, с сохранением id."""
    cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(users)")}
    if "telegram_id" in cols and not cols["phone"]["notnull"]:
        return
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("ALTER TABLE users RENAME TO users_old")
    conn.execute("""CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT UNIQUE,
        telegram_id INTEGER UNIQUE, email TEXT UNIQUE, google_sub TEXT UNIQUE, created_ts INTEGER NOT NULL)""")
    conn.execute("INSERT INTO users (id, name, phone, created_ts) SELECT id, name, phone, created_ts FROM users_old")
    conn.execute("DROP TABLE users_old")
    conn.execute("COMMIT")
    conn.execute("PRAGMA foreign_keys = ON")


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone():
            _migrate_users(conn)
        conn.executescript(SCHEMA)
        if "expect_tg" not in [r["name"] for r in conn.execute("PRAGMA table_info(tg_logins)")]:
            conn.execute("ALTER TABLE tg_logins ADD COLUMN expect_tg INTEGER")
        if conn.execute("SELECT COUNT(*) FROM zones").fetchone()[0] == 0:
            for sort, (zid, name, tagline, price, word, count) in enumerate(SEED_ZONES):
                conn.execute(
                    "INSERT INTO zones (id, name, tagline, price, open_min, close_min, place_word, sort)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (zid, name, tagline, price, OPEN_MIN, CLOSE_MIN, word, sort),
                )
                for n in range(1, count + 1):
                    conn.execute("INSERT INTO places (zone_id, number) VALUES (?, ?)", (zid, n))
    finally:
        conn.close()
