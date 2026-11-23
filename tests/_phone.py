"""Помощник тестов: проходит вход по телефону так, как это делают бот и человек.
Первый вход по номеру — подтверждение контакта и код; повторный (номер уже привязан к Telegram) — «Да, войти»."""
import hashlib
import re

from app import auth_providers
from app.db import connect

CODE = "123456"


def phone_login(client, name, phone, tg_id=None):
    r = client.post("/api/auth/phone/start", json={"name": name, "phone": phone})
    assert r.status_code == 200, r.text
    st = r.json()
    token = st["token"]
    th = hashlib.sha256(token.encode()).hexdigest()
    conn = connect(client.app.state.db_path)
    try:
        if st["mode"] == "tg":                                # уже привязан: бот подтверждает тем же Telegram
            tg = conn.execute("SELECT expect_tg FROM tg_logins WHERE token_hash = ?", (th,)).fetchone()[0]
            conn.execute("UPDATE tg_logins SET telegram_id = ?, name = ? WHERE token_hash = ?", (tg, name, th))
            conn.close()
            v = client.post("/api/auth/telegram/poll", json={"token": token})
            assert v.status_code == 200, v.text
            return v.json()["me"]
        tg = tg_id or int(re.sub(r"\D", "", phone)[-9:])      # бот записывает Telegram, который подтвердил номер
        conn.execute("UPDATE phone_logins SET tg_id = ?, code_hash = ?, attempts = 0 WHERE token_hash = ?",
                     (tg, auth_providers.phone_code_hash(th, CODE), th))
    finally:
        conn.close()
    assert client.post("/api/auth/phone/poll", json={"token": token}).json() == {"status": "code"}
    v = client.post("/api/auth/phone/verify", json={"token": token, "code": CODE})
    assert v.status_code == 200, v.text
    return v.json()["me"]
