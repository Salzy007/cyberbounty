"""Вход через Telegram и общая бронь сайта и бота."""
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


def tg_payload(tg_id=777, first="Ира", token=BOT_TOKEN, age=0, **extra):
    data = {"id": tg_id, "first_name": first, "auth_date": int(time.time()) - age, **extra}
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    data["hash"] = hmac.new(hashlib.sha256(token.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    return data


@pytest.fixture()
def site(tmp_path):
    s = Settings(admin_password="x", db_path=tmp_path / "a.db", telegram_bot_token=BOT_TOKEN,
                 telegram_bot_username="cb_test_bot")
    return TestClient(create_app(s)), s


def fresh(site_pair):
    return TestClient(site_pair[0].app)         # второй «браузер» без cookie


def tomorrow_slot(client, hhmm="12:00", zone="standard"):
    day = (booking.local_today(time.time()) + timedelta(days=1)).isoformat()
    return next(s for s in client.get(f"/api/zones/{zone}/slots", params={"date": day}).json()["slots"] if s["time"] == hhmm)["start"]


# ---------- Telegram ----------

def test_providers_only_telegram(tmp_path):
    c = TestClient(create_app(Settings(admin_password="x", db_path=tmp_path / "p.db")))
    assert c.get("/api/auth/providers").json() == {"telegram": {"enabled": False}}
    assert c.post("/api/auth/telegram", json=tg_payload()).status_code == 503
    assert c.post("/api/auth/google", json={"credential": "x" * 30}).status_code >= 400
    assert c.post("/api/auth/email/request", json={"email": "a@b.co"}).status_code >= 400


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


# ---------- привязка способов к одному человеку ----------

def test_telegram_links_to_logged_in_phone_account_and_conflicts(site):
    c, settings = site
    me = c.post("/api/login", json={"name": "Аня", "phone": "+375291112233"}).json()["me"]
    tg = c.post("/api/auth/telegram", json=tg_payload()).json()["me"]
    assert tg["id"] == me["id"] and tg["via"] == {"telegram": True, "google": False, "email": False, "phone": True}
    other = fresh(site)
    other.post("/api/login", json={"name": "Боря", "phone": "+375299998877"})
    assert other.post("/api/auth/telegram", json=tg_payload()).status_code == 409        # чужой Telegram не пристегнуть


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


# ---------- вход через ссылку на бота (без домена) ----------

def test_telegram_deeplink_login(site):
    c, settings = site
    r = c.post("/api/auth/telegram/start").json()
    assert r["url"].startswith("https://t.me/cb_test_bot?start=login_")
    assert c.post("/api/auth/telegram/poll", json={"token": r["token"]}).json() == {"status": "pending"}
    conn = connect(settings.db_path)                           # бот подтверждает: пишет в общую базу
    h = hashlib.sha256(r["token"].encode()).hexdigest()
    conn.execute("UPDATE tg_logins SET telegram_id = 4242, name = 'Ира' WHERE token_hash = ?", (h,))
    me = c.post("/api/auth/telegram/poll", json={"token": r["token"]}).json()["me"]
    assert me["via"]["telegram"] and me["name"] == "Ира"
    assert c.post("/api/auth/telegram/poll", json={"token": r["token"]}).status_code == 410      # секрет одноразовый
    assert c.post("/api/auth/telegram/poll", json={"token": "x" * 30}).status_code == 410
