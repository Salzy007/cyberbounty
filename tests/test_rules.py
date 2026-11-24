"""Проверки правил брони и сервера. Запуск: .venv\\Scripts\\python -m pytest -q"""
import threading
import time
from datetime import date, datetime

import pytest

from app import booking
from app.booking import TZ, BookingError
from app.db import connect, init_db



def ts(y, m, d, hh, mm=0) -> int:
    return int(datetime(y, m, d, hh, mm, tzinfo=TZ).timestamp())


NOW = ts(2026, 11, 22, 15, 10)           # воскресенье 15:10
U1, U2 = {"id": 1, "name": "Аня"}, {"id": 2, "name": "Борис"}


@pytest.fixture()
def conn(tmp_path):
    path = tmp_path / "t.db"
    init_db(path)
    c = connect(path)
    yield c
    c.close()


def make(conn, user=U1, place=1, start=None, hours=1, key=None, now=NOW):
    return booking.create_booking(conn, user, place, start if start is not None else ts(2026, 11, 22, 18), hours, key, now)


def code(fn):
    with pytest.raises(BookingError) as e:
        fn()
    return e.value.code


# ---------- цена ----------
def test_price_comes_from_zone_and_hours(conn):
    for first_place, zone_price in ((1, 6), (13, 12), (19, 18)):       # Standard, VIP, Tournament
        for i, h in enumerate(booking.DURATIONS):
            b, _ = make(conn, place=first_place + i, hours=h, start=ts(2026, 11, 23, 12))
            assert b["price"] == zone_price * h


def test_price_change_only_affects_new_bookings(conn):
    old, _ = make(conn, place=1, hours=2)
    booking.set_price(conn, "standard", 10)
    new, _ = make(conn, place=2, hours=2)
    assert (old["price"], new["price"]) == (12, 20)
    assert booking.get_booking(conn, old["id"])["price"] == 12


def test_bad_price_rejected(conn):
    for bad in (0, -5, 1001, 1.5, "7", True, None):
        assert code(lambda: booking.set_price(conn, "standard", bad)) == "bad_price"


# ---------- пересечения ----------
def test_overlap_rejected_adjacent_allowed(conn):
    make(conn, start=ts(2026, 11, 22, 18), hours=2)                           # 18:00–20:00
    assert code(lambda: make(conn, U2, start=ts(2026, 11, 22, 19), hours=1)) == "taken"
    assert code(lambda: make(conn, U2, start=ts(2026, 11, 22, 17, 30), hours=1)) == "taken"
    assert code(lambda: make(conn, U2, start=ts(2026, 11, 22, 16), hours=3)) == "taken"
    assert code(lambda: make(conn, U2, start=ts(2026, 11, 22, 18), hours=1)) == "taken"
    make(conn, U2, start=ts(2026, 11, 22, 20), hours=1)                       # встык после — можно
    make(conn, U2, start=ts(2026, 11, 22, 17), hours=1)                       # встык до — можно
    make(conn, U2, place=2, start=ts(2026, 11, 22, 18), hours=2)              # другое место — можно


def test_canceled_booking_frees_place(conn):
    b, _ = make(conn)
    booking.cancel_booking(conn, b["id"], NOW)
    make(conn, U2)


def test_busy_slot_not_free_in_availability(conn):
    make(conn, start=ts(2026, 11, 22, 18), hours=2)
    by_time = {s["time"]: s for s in booking.slots(conn, 1, "2026-11-22", NOW)["slots"]}
    assert not by_time["18:00"]["free"] and not by_time["19:30"]["free"]
    assert by_time["20:00"]["free"] and not by_time["17:30"]["free"]   # 17:30–18:30 задевает бронь
    assert by_time["17:00"]["durations"] == [1]                       # 17:00–18:00 встык: только 1 час


# ---------- прошлое и часы работы ----------
def test_past_not_offered_and_rejected(conn):
    slots = booking.slots(conn, 1, "2026-11-22", NOW)["slots"]
    assert slots and min(s["start"] for s in slots) >= NOW and slots[0]["time"] == "15:30"
    assert code(lambda: make(conn, start=ts(2026, 11, 22, 15))) == "past"
    assert code(lambda: make(conn, start=ts(2026, 11, 21, 12))) == "past"


def test_outside_hours_not_offered_and_rejected(conn):
    slots = booking.slots(conn, 1, "2026-11-23", NOW)["slots"]
    times = [s["time"] for s in slots]
    assert times[:4] == ["00:00", "00:30", "01:00", "10:00"]   # ночной хвост вчерашнего дня, потом дневные часы
    assert times[-1] == "23:30" and "09:30" not in times and "01:30" not in times
    assert [s["after_midnight"] for s in slots[:4]] == [True, True, True, False]
    assert code(lambda: make(conn, start=ts(2026, 11, 23, 9, 30))) == "closed"
    assert code(lambda: make(conn, start=ts(2026, 11, 24, 2))) == "closed"      # 02:00 уже закрыто
    assert code(lambda: make(conn, start=ts(2026, 11, 23, 5))) == "closed"


def test_duration_beyond_closing_rejected(conn):
    assert code(lambda: make(conn, start=ts(2026, 11, 23, 22), hours=5)) == "closed"   # до 03:00
    assert code(lambda: make(conn, start=ts(2026, 11, 24, 1), hours=2)) == "closed"    # 01:00–03:00
    b, _ = make(conn, start=ts(2026, 11, 24, 0), hours=2)                              # 00:00–02:00 впритык — можно
    assert b["end_time"] == "02:00"
    slot = {s["time"]: s for s in booking.slots(conn, 3, "2026-11-23", NOW)["slots"]}
    assert slot["21:00"]["durations"] == [1, 2, 3, 5] and slot["22:00"]["durations"] == [1, 2, 3]
    assert slot["23:30"]["durations"] == [1, 2]
    assert slot["00:00"]["durations"] == [1, 2] and slot["01:00"]["durations"] == [1]


def test_night_hours_belong_to_previous_club_day(conn):
    # в 00:30 ночью «сегодня» — уже по календарю (23.11), а до 02:00 ещё можно взять место на хвост вчерашнего дня
    now = ts(2026, 11, 23, 0, 30)
    zone = booking.get_zone(conn, "standard")
    assert booking.zone_days(zone, now)[0] == date(2026, 11, 23)
    night = booking.slots(conn, 1, "2026-11-23", now)["slots"]
    assert [s["time"] for s in night][:3] == ["00:30", "01:00", "10:00"]
    b, _ = booking.create_booking(conn, U1, 1, ts(2026, 11, 23, 1), 1, None, now)
    assert b["end_time"] == "02:00"


def test_date_window_today_plus_seven(conn):
    zone = booking.get_zone(conn, "standard")
    assert len(booking.zone_days(zone, NOW)) == 8
    booking.slots(conn, 1, "2026-11-29", NOW)
    assert code(lambda: booking.slots(conn, 1, "2026-11-30", NOW)) == "bad_date"
    assert code(lambda: booking.slots(conn, 1, "2026-11-21", NOW)) == "bad_date"
    assert code(lambda: make(conn, start=ts(2026, 11, 30, 12))) == "closed"


def test_bad_input(conn):
    assert code(lambda: make(conn, hours=4)) == "bad_hours"
    assert code(lambda: make(conn, start=ts(2026, 11, 22, 18) + 60)) == "bad_time"
    assert code(lambda: make(conn, place=9999)) == "no_place"
    assert code(lambda: make(conn, place="1")) == "no_place"


# ---------- двойное нажатие ----------
def test_same_key_gives_one_booking(conn):
    a, new_a = make(conn, key="key-12345678")
    b, new_b = make(conn, key="key-12345678")
    assert (new_a, new_b) == (True, False) and a["id"] == b["id"]
    assert conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 1


def test_parallel_requests_one_winner(tmp_path):
    path = tmp_path / "p.db"
    init_db(path)
    results = []

    def attempt(i):
        c = connect(path)
        try:
            results.append(booking.create_booking(c, {"id": 100 + i, "name": "x"}, 1, ts(2026, 11, 22, 20), 2, f"key-parallel-{i}", NOW)[1])
        except BookingError as e:
            results.append(e.code)
        finally:
            c.close()

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 1 and results.count("taken") == 11


# ---------- отмена ----------
def test_cancel_rules(conn):
    b, _ = make(conn)
    assert booking.cancel_booking(conn, b["id"], NOW)["status"] == "canceled"
    assert code(lambda: booking.cancel_booking(conn, b["id"], NOW)) == "already"
    assert code(lambda: booking.cancel_booking(conn, 9999, NOW)) == "no_booking"
    old, _ = make(conn, place=2)
    assert code(lambda: booking.cancel_booking(conn, old["id"], old["end"] + 1)) == "finished"


def test_admin_day_overview(conn):
    make(conn, start=ts(2026, 11, 22, 18), hours=2)
    make(conn, U2, place=2, start=ts(2026, 11, 22, 19), hours=1)
    x, _ = make(conn, U2, place=3, start=ts(2026, 11, 22, 20), hours=1)
    booking.cancel_booking(conn, x["id"], NOW)
    ov = booking.day_overview(conn, "2026-11-22", NOW)
    assert len(ov["bookings"]) == 3 and ov["total"] == 18            # отменённая в сумму не входит
    p1 = ov["zones"][0]["places"][0]
    assert p1["free"] == ["15:30–18:00", "20:00–02:00"] and not p1["free_all"]
    assert ov["zones"][0]["places"][3]["free"] == ["15:30–02:00"]
    tomorrow = booking.day_overview(conn, "2026-11-23", NOW)
    assert tomorrow["bookings"] == [] and tomorrow["zones"][0]["places"][0]["free_all"]


def test_client_cancel_rules(conn):
    b, _ = make(conn)
    assert code(lambda: booking.cancel_by_client(conn, b["id"], 999, NOW)) == "no_booking"     # чужую не отменить
    assert code(lambda: booking.cancel_by_client(conn, b["id"], 1, b["end"] + 60)) == "finished"   # закончившуюся не отменить
    assert booking.cancel_by_client(conn, b["id"], 1, NOW)["status"] == "canceled"
    assert code(lambda: booking.cancel_by_client(conn, b["id"], 1, NOW)) == "already"
    make(conn, U2)                                                                              # место снова свободно


def test_history_cleanup(conn):
    future, _ = make(conn, place=1, start=ts(2026, 11, 23, 12))
    gone, _ = make(conn, place=2, start=ts(2026, 11, 23, 12))
    booking.cancel_booking(conn, gone["id"], NOW)
    old, _ = make(conn, place=3, start=ts(2026, 11, 22, 16))                      # потом станет прошедшей, но подтверждённой
    assert code(lambda: booking.delete_booking(conn, future["id"])) == "active"   # стереть можно только отменённую
    assert code(lambda: booking.delete_booking(conn, old["id"])) == "active"
    canceled2, _ = make(conn, place=4, start=ts(2026, 11, 24, 12))
    booking.cancel_booking(conn, canceled2["id"], NOW)
    booking.delete_booking(conn, gone["id"])                                      # отменённую — можно
    assert booking.day_overview(conn, "2026-11-22", NOW)["canceled_total"] == 1   # кнопка «очистить» в админке покажется
    assert booking.clear_history(conn) == 1                                       # осталась одна отменённая — стёрта
    assert booking.day_overview(conn, "2026-11-22", NOW)["canceled_total"] == 0   # больше нечего чистить — кнопка пропадёт
    left = sorted(r["id"] for r in conn.execute("SELECT id FROM bookings"))
    assert left == sorted([future["id"], old["id"]])                              # подтверждённые целы, даже прошедшие



def test_busy_at_chosen_time(conn):
    make(conn, place=1, start=ts(2026, 11, 22, 18), hours=2)                      # 18:00–20:00
    make(conn, U2, place=2, start=ts(2026, 11, 22, 20, 30), hours=1)               # 20:30–21:30
    at = lambda h, m=0: ts(2026, 11, 22, h, m)
    assert booking.busy_at(conn, "standard", at(19), 3600) == {1: "до 20:00"}       # идёт в этот момент
    assert booking.busy_at(conn, "standard", at(20), 3600) == {2: "с 20:30"}        # начнётся внутри часа — тоже мешает
    assert booking.busy_at(conn, "standard", at(22), 3600) == {}                    # свободно
    assert booking.busy_at(conn, "standard", at(18, 30), 0) == {1: "до 20:00"}      # «сейчас»: только то, что идёт
    assert booking.busy_at(conn, "standard", at(20), 0) == {}




def test_client_can_cancel_started_booking_and_frees_place(conn):
    """Клиент отменяет бронь в любое время, в том числе когда игра уже идёт; место освобождается сразу."""
    b, _ = make(conn)
    mid = b["start"] + 60                                           # бронь уже началась
    assert booking.busy_at(conn, "standard", mid, 0)                # место занято
    assert booking.cancel_by_client(conn, b["id"], 1, mid)["status"] == "canceled"
    assert not booking.busy_at(conn, "standard", mid, 0)            # и свободно сразу после отмены
    assert code(lambda: booking.cancel_by_client(conn, b["id"], 1, mid)) == "already"


def test_admin_day_lists_booking_carried_over_midnight(conn):
    """Бронь 23:00–01:00 занимает время следующей даты, поэтому видна в списке обеих дат; в итог дня входит один раз."""
    b, _ = make(conn, start=ts(2026, 11, 22, 23), hours=2)
    first = booking.day_overview(conn, "2026-11-22", NOW)
    second = booking.day_overview(conn, "2026-11-23", NOW)
    assert [(x["id"], x["carried"]) for x in first["bookings"]] == [(b["id"], False)] and first["total"] == b["price"]
    assert [(x["id"], x["carried"]) for x in second["bookings"]] == [(b["id"], True)] and second["total"] == 0
