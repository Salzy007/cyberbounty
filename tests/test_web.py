"""Проверки сайта: вход, бронь по HTTP, админка, защита."""
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import booking
from app.config import Settings
from app.server import create_app
from _phone import phone_login

PASSWORD = "test-pass-123"
JSON = {"content-type": "application/json"}


@pytest.fixture()
def site(tmp_path):
    app = create_app(Settings(admin_password=PASSWORD, db_path=tmp_path / "w.db", telegram_bot_username="cb_test_bot"))
    return TestClient(app)


def tomorrow():
    return (booking.local_today(time.time()) + timedelta(days=1)).isoformat()


def first_slot(site, zone="standard", hours=1):
    slots = site.get(f"/api/zones/{zone}/slots", params={"date": tomorrow()}).json()["slots"]
    return next(s for s in slots if s["time"] == "12:00")["start"]


def login(client, name="Аня", phone="+375 29 111-22-33"):
    return phone_login(client, name, phone)


def test_public_pages_and_config(site):
    assert site.get("/").status_code == 200
    cfg = site.get("/api/config").json()
    assert [z["id"] for z in cfg["zones"]] == ["standard", "vip", "tournament", "lounge"] and cfg["me"] is None


def test_booking_requires_login(site):
    start = first_slot(site)
    assert site.post("/api/bookings", json={"place_id": 1, "start": start, "hours": 1}).status_code == 401
    assert site.get("/api/my-bookings").status_code == 401


def test_login_validates_and_same_phone_same_account(site):
    assert site.post("/api/auth/phone/start", json={"name": "A", "phone": "123"}).status_code == 400
    a = login(site)
    b = login(TestClient(site.app), phone="375291112233")           # тот же номер другим написанием
    assert a["id"] == b["id"]


def test_full_flow_price_from_server_and_my_bookings(site):
    me = login(site)
    start = first_slot(site)
    r = site.post("/api/bookings", json={"place_id": 1, "start": start, "hours": 3, "price": 1, "key": "web-key-0001"})
    assert r.status_code == 200
    b = r.json()["booking"]
    assert b["price"] == 18 and b["user_id"] == me["id"]            # 6 BYN * 3 ч, присланная цена игнорируется
    mine = site.get("/api/my-bookings").json()["bookings"]
    assert [x["id"] for x in mine] == [b["id"]]
    again = site.post("/api/bookings", json={"place_id": 1, "start": start, "hours": 3, "key": "web-key-0001"}).json()
    assert again["duplicate"] and again["booking"]["id"] == b["id"]  # двойной клик = одна бронь
    busy = site.get("/api/zones/standard/busy", params={"at": start, "hours": 1}).json()["busy"]
    assert "1" in busy
    other = TestClient(site.app)
    login(other, "Борис", "375441234567")
    r = other.post("/api/bookings", json={"place_id": 1, "start": start + 3600, "hours": 1})
    assert r.status_code == 409 and r.json()["code"] == "taken"
    assert other.get("/api/my-bookings").json()["bookings"] == []   # чужих броней не видно


def test_zone_slots_count_free_places(site):
    login(site)
    start = first_slot(site)
    before = next(s for s in site.get("/api/zones/standard/slots", params={"date": tomorrow()}).json()["slots"] if s["start"] == start)
    assert before["free"]["1"] == 12
    site.post("/api/bookings", json={"place_id": 1, "start": start, "hours": 2})
    after = next(s for s in site.get("/api/zones/standard/slots", params={"date": tomorrow()}).json()["slots"] if s["start"] == start)
    assert after["free"]["1"] == 11 and after["free"]["2"] == 11


def test_past_and_closed_rejected_over_http(site):
    login(site)
    assert site.post("/api/bookings", json={"place_id": 1, "start": int(time.time() // 1800) * 1800 - 7200, "hours": 1}).json()["code"] == "past"
    assert site.post("/api/bookings", json={"place_id": 1, "start": first_slot(site) + 3 * 3600 * 0 + 1, "hours": 1}).status_code == 400


def test_client_cancel_own_only(site):
    login(site)
    start = first_slot(site)
    b = site.post("/api/bookings", json={"place_id": 2, "start": start, "hours": 1}).json()["booking"]
    other = TestClient(site.app)
    login(other, "Борис", "375441234567")
    assert other.post(f"/api/bookings/{b['id']}/cancel").status_code == 404
    assert site.post(f"/api/bookings/{b['id']}/cancel").json()["booking"]["status"] == "canceled"


def test_admin_needs_password_and_controls(site):
    login(site)
    start = first_slot(site)
    b = site.post("/api/bookings", json={"place_id": 3, "start": start, "hours": 1}).json()["booking"]
    assert site.get("/api/admin/day", params={"date": tomorrow()}).status_code == 403   # клиент — не владелец
    assert site.post("/api/admin/login", json={"password": "wrong"}).status_code == 403
    assert site.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    day = site.get("/api/admin/day", params={"date": tomorrow()}).json()
    assert [x["id"] for x in day["bookings"]] == [b["id"]] and day["total"] == 6
    assert site.patch("/api/admin/zones/standard", json={"price": 8}).status_code == 200
    assert site.patch("/api/admin/zones/standard", json={"price": 0}).status_code == 400
    assert site.post(f"/api/admin/bookings/{b['id']}/cancel").json()["booking"]["status"] == "canceled"
    assert site.delete(f"/api/admin/bookings/{b['id']}").status_code == 200
    site.post("/api/admin/logout")
    assert site.get("/api/admin/me").status_code == 403


def test_admin_disabled_without_password(tmp_path):
    c = TestClient(create_app(Settings(admin_password="", db_path=tmp_path / "x.db")))
    assert c.post("/api/admin/login", json={"password": ""}).status_code == 403


def test_foreign_origin_and_plain_form_blocked(site):
    assert site.post("/api/auth/phone/start", json={"name": "Аня", "phone": "375291112233"}, headers={"origin": "https://evil.example"}).status_code == 403
    assert site.post("/api/auth/phone/start", content="name=a", headers={"content-type": "text/plain"}).status_code == 415


def test_login_rate_limit(site):
    codes = [site.post("/api/admin/login", json={"password": "x"}).status_code for _ in range(7)]
    assert codes[:5] == [403] * 5 and codes[-1] == 429


def _book(site, key):
    start = first_slot(site)
    r = site.post("/api/bookings", json={"place_id": 1, "start": start, "hours": 1, "key": key})
    assert r.status_code == 200
    return r.json()["booking"]


def test_client_deletes_own_canceled_only(site):
    login(site)
    b = _book(site, "del-key-00001")
    assert site.delete(f"/api/bookings/{b['id']}").status_code == 409          # действующую нельзя
    assert site.post(f"/api/bookings/{b['id']}/cancel").status_code == 200
    # чужую удалить нельзя
    other = TestClient(site.app)
    login(other, "Боря", "+375 29 555-66-77")
    assert other.delete(f"/api/bookings/{b['id']}").status_code == 404
    assert len(site.get("/api/my-bookings").json()["bookings"]) == 1
    # свою отменённую — можно, место не занимается и не освобождается повторно
    assert site.delete(f"/api/bookings/{b['id']}").status_code == 200
    assert site.get("/api/my-bookings").json()["bookings"] == []
    assert site.delete(f"/api/bookings/{b['id']}").status_code == 404
    # у клуба запись осталась: клиент только убрал её из своего списка
    assert site.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    day = site.get("/api/admin/day", params={"date": tomorrow()}).json()
    assert [(x["id"], x["status"]) for x in day["bookings"]] == [(b["id"], "canceled")]
    site.post("/api/admin/logout")
    assert site.post("/api/bookings", json={"place_id": 1, "start": b["start"], "hours": 1, "key": "del-key-00002"}).status_code == 200


def test_clear_mine_only_my_canceled(site):
    login(site)
    a = _book(site, "clr-key-00001")
    site.post(f"/api/bookings/{a['id']}/cancel")
    start2 = first_slot(site) + 7200
    live = site.post("/api/bookings", json={"place_id": 1, "start": start2, "hours": 1, "key": "clr-key-00002"}).json()["booking"]
    other = TestClient(site.app)
    login(other, "Боря", "+375 29 555-66-77")
    o = other.post("/api/bookings", json={"place_id": 2, "start": start2, "hours": 1, "key": "clr-key-00003"}).json()["booking"]
    other.post(f"/api/bookings/{o['id']}/cancel")
    assert site.post("/api/my-bookings/clear").json() == {"removed": 1}
    assert [x["id"] for x in site.get("/api/my-bookings").json()["bookings"]] == [live["id"]]
    assert len(other.get("/api/my-bookings").json()["bookings"]) == 1       # у соседа осталась
    assert site.post("/api/my-bookings/clear").json() == {"removed": 0}      # повторно убирать нечего
    assert site.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    assert site.get("/api/admin/day", params={"date": tomorrow()}).json()["canceled_total"] == 2   # у владельца обе отменённые на месте
    assert TestClient(site.app).delete(f"/api/bookings/{a['id']}").status_code == 401


def test_bookings_survive_logout_and_login(site):
    me = login(site)
    b = _book(site, "keep-key-0001")
    c = _book_second = site.post("/api/bookings", json={"place_id": 1, "start": b["start"] + 7200, "hours": 1, "key": "keep-key-0002"}).json()["booking"]
    site.post(f"/api/bookings/{c['id']}/cancel")
    assert site.post("/api/logout").status_code == 200
    assert site.get("/api/my-bookings").status_code == 401
    again = login(site)                                    # тот же номер, новая сессия
    assert again["id"] == me["id"]
    ids = {x["id"]: x["status"] for x in site.get("/api/my-bookings").json()["bookings"]}
    assert ids == {b["id"]: "confirmed", c["id"]: "canceled"}


def test_price_change_changes_signature_and_config(site):
    before = site.get("/api/config").json()["zones"][0]["price"]
    r = site.post("/api/admin/login", json={"password": PASSWORD})
    assert r.status_code == 200
    v0 = site.get("/api/wait").json()["version"]
    assert site.patch("/api/admin/zones/standard", json={"price": before + 1}).status_code == 200
    assert site.get("/api/config").json()["zones"][0]["price"] == before + 1
    assert site.get("/api/wait").json()["version"] > v0                       # сайт и бот узнают о смене цены сразу


def test_old_database_gets_client_hidden_column(tmp_path):
    """База без колонки client_hidden (созданная до этой функции) обновляется сама, брони не теряются."""
    import sqlite3
    from app import db
    path = tmp_path / "old.db"
    db.init_db(path)
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE bookings DROP COLUMN client_hidden")
    conn.commit(); conn.close()
    db.init_db(path)
    conn = sqlite3.connect(path)
    assert any(r[1] == "client_hidden" for r in conn.execute("PRAGMA table_info(bookings)"))
    conn.close()


def test_client_clear_notifies_bot(site, tmp_path):
    """Клиент с Telegram убрал отменённые брони на сайте: боту уходит событие, он чистит чат."""
    from app.db import connect
    login(site)
    conn = connect(tmp_path / "w.db")
    conn.execute("UPDATE users SET telegram_id = 777")
    conn.close()
    a = _book(site, "tgn-key-00001")
    site.post(f"/api/bookings/{a['id']}/cancel")
    assert site.post("/api/my-bookings/clear").json() == {"removed": 1}
    conn = connect(tmp_path / "w.db")
    kinds = [(r["kind"], r["payload"]) for r in conn.execute("SELECT kind, payload FROM notify_outbox WHERE kind = 'shredded'")]
    conn.close()
    assert len(kinds) == 1 and '"chat_id": 777' in kinds[0][1]
