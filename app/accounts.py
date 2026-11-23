"""Аккаунты. Один человек = одна строка в users; Telegram, Google, почта и телефон — способы войти в неё.

Правило привязки: если вход уже есть у какого-то аккаунта — входим в него; если нет — создаём новый.
Если человек уже вошёл (current_id), новый способ добавляется к его аккаунту.
Идентификатор, который принадлежит другому аккаунту, молча не переносим — это ошибка 409.
Общий файл: такая же копия лежит в боте (cyberbounty-bot), чтобы mini app и сайт видели одного человека.
"""
import time

from app.booking import BookingError

FIELDS = ("telegram_id", "email", "google_sub", "phone")


def _by(conn, field: str, value):
    assert field in FIELDS
    return conn.execute(f"SELECT * FROM users WHERE {field} = ?", (value,)).fetchone()


def public(row) -> dict:
    """Что показываем клиенту о себе (без чужих id)."""
    return {"id": row["id"], "name": row["name"], "phone": row["phone"], "email": row["email"],
            "via": {k: row[col] is not None for k, col in
                    (("telegram", "telegram_id"), ("google", "google_sub"), ("email", "email"), ("phone", "phone"))}}


def get(conn, user_id: int):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def sign_in(conn, field: str, value, name: str, *, current_id: int | None = None, email: str | None = None):
    """Находит или создаёт аккаунт по способу входа и возвращает строку users.
    email — подтверждённая почта (Google), по ней тоже узнаём человека."""
    name = " ".join((name or "").split())[:60] or "Игрок"
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = _by(conn, field, value)
        if row is None and email:
            row = _by(conn, "email", email)
        if current_id is not None:
            if row is not None and row["id"] != current_id:
                raise BookingError("linked_other", "Этот способ входа уже привязан к другому аккаунту.", 409)
            row = get(conn, current_id) or row
        if row is None:
            cur = conn.execute("INSERT INTO users (name, " + field + ", email, created_ts) VALUES (?, ?, ?, ?)",
                               (name, value, email, int(time.time())))
            row_id = cur.lastrowid
        else:
            row_id = row["id"]
            if row[field] is None:
                conn.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (value, row_id))
            if email and row["email"] is None and _by(conn, "email", email) is None:
                conn.execute("UPDATE users SET email = ? WHERE id = ?", (email, row_id))
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return get(conn, row_id)


def telegram_account(conn, tg_user: dict):
    """Для mini app в боте: аккаунт человека по его Telegram id (создаётся при первом заходе)."""
    name = " ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])) or tg_user.get("username") or ""
    return sign_in(conn, "telegram_id", tg_user["id"], name)


def link_phone_telegram(conn, phone: str, tg_id: int, name: str, current_id: int | None = None):
    """Вход по телефону, подтверждённому в Telegram: находим или создаём аккаунт по номеру и Telegram id.
    Если номер и Telegram принадлежат разным аккаунтам — не склеиваем молча, а отказываем."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        by_phone, by_tg = _by(conn, "phone", phone), _by(conn, "telegram_id", tg_id)
        if (by_tg is not None and by_tg["phone"] and by_tg["phone"] != phone) or                 (by_phone is not None and by_phone["telegram_id"] and by_phone["telegram_id"] != tg_id):
            raise BookingError("linked_other", "Этот Telegram или номер уже привязан к другому аккаунту.", 409)
        ids = {r["id"] for r in (by_phone, by_tg) if r is not None}
        if current_id is not None:
            if ids - {current_id}:
                raise BookingError("linked_other", "Этот номер или Telegram уже привязан к другому аккаунту.", 409)
            uid = current_id
        elif len(ids) > 1:
            raise BookingError("linked_other", "Этот номер и Telegram привязаны к разным аккаунтам. Напишите администратору.", 409)
        elif ids:
            uid = ids.pop()
        else:
            uid = conn.execute("INSERT INTO users (name, phone, telegram_id, created_ts) VALUES (?, ?, ?, ?)",
                               (" ".join((name or "").split())[:60] or "Игрок", phone, tg_id, int(time.time()))).lastrowid
        row = get(conn, uid)
        if row["phone"] is None:
            conn.execute("UPDATE users SET phone = ? WHERE id = ?", (phone, uid))
        if row["telegram_id"] is None:
            conn.execute("UPDATE users SET telegram_id = ? WHERE id = ?", (tg_id, uid))
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return get(conn, uid)
