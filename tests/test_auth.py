"""Вход тремя способами (Telegram, Google, почта) и общая бронь сайта и бота."""
import hashlib
import hmac
import logging
import re
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import accounts, auth_providers, booking
from app.booking import BookingError
from app.config import Settings
from app.db import connect, init_db
from app.server import create_app

BOT_TOKEN = "123456:TEST-token-not-real"
CLIENT_ID = "test-client.apps.googleusercontent.com"


def tg_payload(tg_id=777, first="Ира", token=BOT_TOKEN, age=0, **extra):
    data = {"id": tg_id, "first_name": first, "auth_date": int(time.time()) - age, **extra}
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    data["hash"] = hmac.new(hashlib.sha256(token.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    return data


@pytest.fixture()
def site(tmp_path):
    s = Settings(admin_password="x", db_path=tmp_path / "a.db", telegram_bot_token=BOT_TOKEN,
                 telegram_bot_username="cb_test_bot", google_client_id=CLIENT_ID)
    return TestClient(create_app(s)), s


def fresh(site_pair):
    return TestClient(site_pair[0].app)         # второй «браузер» без cookie


def tomorrow_slot(client, hhmm="12:00", zone="standard"):
    day = (booking.local_today(time.time()) + timedelta(days=1)).isoformat()
    return next(s for s in client.get(f"/api/zones/{zone}/slots", params={"date": day}).json()["slots"] if s["time"] == hhmm)["start"]


# ---------- Telegram ----------

def test_telegram_signature_checked(site):
    c, _ = site
    assert c.post("/api/auth/telegram", json=tg_payload()).status_code == 200
    bad = tg_payload(); bad["id"] = 1                       # подмена id после подписи
    assert c.post("/api/auth/telegram", json=bad).status_code == 401
    assert c.post("/api/auth/telegram", json=tg_payload(token="9:other")).status_code == 401
    assert c.post("/api/auth/telegram", json=tg_payload(age=3 * 86400)).status_code == 401


def test_telegram_same_person_same_account(site):
    c, _ = site
    a = c.post("/api/auth/telegram", json=tg_payload()).json()["me"]
    b = fresh(site).post("/api/auth/telegram", json=tg_payload()).json()["me"]
    assert a["id"] == b["id"] and a["via"]["telegram"]


# ---------- Google ----------

def google(monkeypatch, sub="g-1", email="ira@example.com", name="Ира Г"):
    monkeypatch.setattr(auth_providers, "verify_google", lambda cred, cid: {"sub": sub, "email": email, "name": name})


def test_google_login_and_links_by_verified_email(site, monkeypatch):
    c, _ = site
    google(monkeypatch)
    g = c.post("/api/auth/google", json={"credential": "x" * 30}).json()["me"]
    assert g["email"] == "ira@example.com" and g["via"]["google"]
    # тот же человек зашёл по почте с кодом -> тот же аккаунт
    assert fresh(site).post("/api/auth/google", json={"credential": "y" * 30}).json()["me"]["id"] == g["id"]


def test_google_token_must_be_for_our_client(monkeypatch):
    class R:
        status_code = 200
        def json(self): return {"aud": "other", "iss": "accounts.google.com", "exp": str(int(time.time()) + 99), "sub": "1"}
    monkeypatch.setattr(auth_providers.httpx, "get", lambda *a, **k: R())
    with pytest.raises(BookingError):
        auth_providers.verify_google("t" * 30, CLIENT_ID)


# ---------- почта ----------

def code_from_log(caplog):
    return re.search(r"Код входа для \S+: (\d{6})", caplog.text).group(1)


def test_email_code_flow_dev_mode_logs_code(site, caplog):
    c, _ = site
    with caplog.at_level(logging.WARNING, logger="cyberbounty"):
        r = c.post("/api/auth/email/request", json={"email": " Ira@Example.com "})
    assert r.status_code == 200 and r.json()["dev"] is True and "code" not in r.text
    code = code_from_log(caplog)
    assert c.post("/api/auth/email/verify", json={"email": "ira@example.com", "code": "000000" if code != "000000" else "111111"}).status_code == 400
    me = c.post("/api/auth/email/verify", json={"email": "ira@example.com", "code": code}).json()["me"]
    assert me["email"] == "ira@example.com" and c.get("/api/config").json()["me"]["id"] == me["id"]
    assert fresh(site).post("/api/auth/email/verify", json={"email": "ira@example.com", "code": code}).status_code == 400   # одноразовый


def test_email_code_limits(site, caplog):
    c, _ = site
    with caplog.at_level(logging.WARNING, logger="cyberbounty"):
        assert c.post("/api/auth/email/request", json={"email": "a@b.co"}).status_code == 200
        assert c.post("/api/auth/email/request", json={"email": "a@b.co"}).status_code == 429       # не чаще раза в 30 с
    assert c.post("/api/auth/email/request", json={"email": "не почта"}).status_code == 400
    code = code_from_log(caplog)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        c.post("/api/auth/email/verify", json={"email": "a@b.co", "code": wrong})
    assert c.post("/api/auth/email/verify", json={"email": "a@b.co", "code": code}).status_code in (400, 429)   # после 5 ошибок код сгорел


def test_providers_reflect_config(tmp_path):
    c = TestClient(create_app(Settings(admin_password="x", db_path=tmp_path / "p.db")))
    p = c.get("/api/auth/providers").json()
    assert p["telegram"]["enabled"] is False and p["google"]["enabled"] is False and p["email"]["enabled"] is True
    assert c.post("/api/auth/telegram", json=tg_payload()).status_code == 503
    assert c.post("/api/auth/google", json={"credential": "x" * 30}).status_code == 503


# ---------- привязка способов к одному человеку ----------

def test_adding_methods_to_logged_in_user_and_conflicts(site, monkeypatch, caplog):
    c, _ = site
    me = c.post("/api/login", json={"name": "Аня", "phone": "+375291112233"}).json()["me"]
    tg = c.post("/api/auth/telegram", json=tg_payload()).json()["me"]          # вошла -> привязали Telegram к тому же аккаунту
    assert tg["id"] == me["id"] and tg["via"] == {"telegram": True, "google": False, "email": False, "phone": True}
    other = fresh(site)
    other.post("/api/login", json={"name": "Боря", "phone": "+375299998877"})
    google(monkeypatch, sub="g-boris", email="b@example.com")
    other.post("/api/auth/google", json={"credential": "x" * 30})
    google(monkeypatch, sub="g-boris", email="b@example.com")
    assert c.post("/api/auth/google", json={"credential": "x" * 30}).status_code == 409   # чужой Google к моему аккаунту не пристегнуть


def test_accounts_telegram_and_old_phone_users_migrate(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT NOT NULL UNIQUE, created_ts INTEGER NOT NULL);"
                      "INSERT INTO users (name, phone, created_ts) VALUES ('Старый', '375291234567', 1);")
    old.close()
    init_db(path)
    conn = connect(path)
    assert conn.execute("SELECT name, phone, telegram_id FROM users").fetchone()["name"] == "Старый"
    conn.execute("INSERT INTO users (name, telegram_id, created_ts) VALUES ('Без телефона', 5, 2)")      # телефон теперь необязателен


# ---------- единая бронь сайта и бота ----------

def bot_side(settings):
    """Бот работает с той же базой через те же функции: это и есть mini app."""
    conn = connect(settings.db_path)
    return conn


def test_bot_booking_blocks_site_and_vice_versa(site):
    c, settings = site
    start = tomorrow_slot(c)
    # 1) бронь из mini app (telegram_id=777)
    bconn = bot_side(settings)
    tg_user = accounts.telegram_account(bconn, {"id": 777, "first_name": "Ира"})
    made, _ = booking.create_booking(bconn, {"id": tg_user["id"], "name": tg_user["name"]}, 1, start, 2, "bot-key-0001")
    assert made["telegram_id"] == 777
    # на сайте место занято на это время (и для чужого гостя тоже)
    guest = fresh(site)
    busy = guest.get("/api/zones/standard/busy", params={"at": start, "hours": 1}).json()["busy"]
    assert "1" in busy
    guest.post("/api/login", json={"name": "Гость", "phone": "+375290000001"})
    r = guest.post("/api/bookings", json={"place_id": 1, "start": start + 1800, "hours": 1, "key": "web-key-0001"})
    assert r.status_code == 409 and r.json()["code"] == "taken"
    # 2) Ира входит на сайте через Telegram — видит бронь из mini app, отменяет её на сайте
    ira = fresh(site)
    ira.post("/api/auth/telegram", json=tg_payload(777))
    mine = ira.get("/api/my-bookings").json()["bookings"]
    assert [b["code"] for b in mine] == [made["code"]]
    # 3) бронь с сайта на другое место блокирует то же место для бота
    r = ira.post("/api/bookings", json={"place_id": 2, "start": start, "hours": 1, "key": "web-key-0002"})
    assert r.status_code == 200
    with pytest.raises(BookingError) as e:
        booking.create_booking(bot_side(settings), {"id": 999, "name": "Кто-то"}, 2, start, 1, "bot-key-0002")
    assert e.value.code == "taken"
    # 4) отмена на сайте освобождает место и для бота
    assert ira.post(f"/api/bookings/{mine[0]['id']}/cancel").status_code == 200
    again, new = booking.create_booking(bot_side(settings), {"id": 999, "name": "Кто-то"}, 1, start, 1, "bot-key-0003")
    assert new


def test_same_person_phone_site_and_telegram_sees_all(site):
    """Человек вошёл на сайте телефоном, потом привязал Telegram — брони с обеих сторон у одного аккаунта."""
    c, settings = site
    c.post("/api/login", json={"name": "Аня", "phone": "+375291112233"})
    start = tomorrow_slot(c)
    assert c.post("/api/bookings", json={"place_id": 3, "start": start, "hours": 1, "key": "web-key-0003"}).status_code == 200
    c.post("/api/auth/telegram", json=tg_payload(555))
    conn = bot_side(settings)
    tg = accounts.telegram_account(conn, {"id": 555, "first_name": "Аня"})
    booking.create_booking(conn, {"id": tg["id"], "name": tg["name"]}, 4, start, 1, "bot-key-0004")
    assert len(c.get("/api/my-bookings").json()["bookings"]) == 2


def test_double_click_across_site_is_one_booking_and_wait_sees_bot_change(site):
    c, settings = site
    c.post("/api/login", json={"name": "Аня", "phone": "+375291112233"})
    start = tomorrow_slot(c)
    body = {"place_id": 5, "start": start, "hours": 1, "key": "web-key-0005"}
    assert c.post("/api/bookings", json=body).json()["duplicate"] is False
    assert c.post("/api/bookings", json=body).json()["duplicate"] is True
    # бот записал бронь в общую базу -> /api/wait замечает без перезапуска
    c.get("/api/wait", params={"since": -1})                # первая проверка запоминает отпечаток
    conn = bot_side(settings)
    booking.create_booking(conn, {"id": 4242, "name": "Бот"}, 6, start, 1, "bot-key-0006")
    r = c.get("/api/wait", params={"since": c.get("/api/wait").json()["version"]}).json()
    assert r["changed"] is True
