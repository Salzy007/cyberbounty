"""Правила брони. Всё, что нельзя нарушать, проверяется здесь, на сервере (клиенту не доверяем).

Время хранится в секундах (unix). Часы клуба — по Минску (UTC+3, без перехода на летнее время).
«Клубный день» D длится от открытия D до закрытия D+1 (по умолчанию 10:00 → 02:00),
поэтому в 01:00 ночи «сегодня» ещё вчерашний день.
"""
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

TZ = timezone(timedelta(hours=3))
STEP = 30 * 60
DURATIONS = (1, 2, 3, 5)
DAYS_AHEAD = 7
WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


class BookingError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# ---------- время ----------

def hhmm(ts: int) -> str:
    return datetime.fromtimestamp(ts, TZ).strftime("%H:%M")


def ddmm(ts: int) -> str:
    local = datetime.fromtimestamp(ts, TZ)
    return f"{local.day:02d}.{local.month:02d} {WEEKDAYS[local.weekday()]}"


def midnight(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=TZ).timestamp())


def local_today(now: float) -> date:
    return datetime.fromtimestamp(now, TZ).date()


def zone_days(zone, now: float) -> list[date]:
    """Даты для выбора: сегодня по календарю и ещё 7 дней. Ночные часы после полуночи показываются в той дате, на которую приходятся."""
    start = local_today(now)
    return [start + timedelta(days=i) for i in range(DAYS_AHEAD + 1)]


def window(zone, d: date) -> tuple[int, int]:
    base = midnight(d)
    return base + zone["open_min"] * 60, base + zone["close_min"] * 60


# ---------- чтение ----------

def get_zone(conn, zone_id: str):
    zone = conn.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone()
    if not zone:
        raise BookingError("no_zone", "Такой зоны нет.", 404)
    return zone


def get_place(conn, place_id):
    row = conn.execute(
        "SELECT p.id, p.number, p.zone_id, z.name AS zone_name, z.place_word, z.price,"
        " z.open_min, z.close_min FROM places p JOIN zones z ON z.id = p.zone_id WHERE p.id = ?",
        (place_id,),
    ).fetchone() if isinstance(place_id, int) else None
    if not row:
        raise BookingError("no_place", "Такого места нет.", 404)
    return row


def place_label(row) -> str:
    return f"{row['place_word']} {row['number']}"


def parse_day(zone, text: str, now: float) -> date:
    try:
        d = date.fromisoformat(text)
    except (TypeError, ValueError):
        raise BookingError("bad_date", "Неверная дата.") from None
    if d not in zone_days(zone, now):
        raise BookingError("bad_date", "Эта дата недоступна для брони.")
    return d


def catalog(conn, now: float) -> list[dict]:
    out = []
    for z in conn.execute("SELECT * FROM zones ORDER BY sort"):
        places = conn.execute("SELECT id, number FROM places WHERE zone_id = ? ORDER BY number", (z["id"],)).fetchall()
        out.append({
            "id": z["id"], "name": z["name"], "tagline": z["tagline"], "price": z["price"],
            "place_word": z["place_word"],
            "open": f"{(z['open_min'] // 60) % 24:02d}:{z['open_min'] % 60:02d}",
            "close": f"{(z['close_min'] // 60) % 24:02d}:{z['close_min'] % 60:02d}",
            "places": [{"id": p["id"], "number": p["number"]} for p in places],
            "days": [d.isoformat() for d in zone_days(z, now)],
        })
    return out


def busy_at(conn, zone_id: str, at: float, span: int = 0) -> dict[int, str]:
    """Занятые места зоны на момент at: {id места: подпись}.
    span=0 — занято прямо в этот момент («до 15:30»); span=3600 — пересекается с часом, который начинается в at
    (если бронь начнётся позже, чем at, подпись «с 20:30»). Подряд идущие брони склеиваем."""
    rows = conn.execute(
        "SELECT b.place_id, b.start_ts, b.end_ts FROM bookings b JOIN places p ON p.id = b.place_id"
        " WHERE p.zone_id = ? AND b.status = 'confirmed' AND b.start_ts < ? AND b.end_ts > ? ORDER BY b.start_ts",
        (zone_id, at + max(span, 1), at),
    ).fetchall()
    out: dict[int, str] = {}
    for r in rows:
        if r["place_id"] in out:
            continue
        if r["start_ts"] > at:
            out[r["place_id"]] = "с " + hhmm(r["start_ts"])
            continue
        end = r["end_ts"]
        while True:      # следующая бронь встык продлевает занятость
            nxt = conn.execute("SELECT end_ts FROM bookings WHERE place_id = ? AND status = 'confirmed' AND start_ts = ?",
                               (r["place_id"], end)).fetchone()
            if not nxt:
                break
            end = nxt["end_ts"]
        out[r["place_id"]] = "до " + hhmm(end)
    return out


def busy_now(conn, zone_id: str, now: float) -> dict[int, str]:
    return busy_at(conn, zone_id, now, 0)


def _overlaps(conn, place_id: int, start: int, end: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM bookings WHERE place_id = ? AND status = 'confirmed' AND start_ts < ? AND end_ts > ? LIMIT 1",
        (place_id, end, start),
    ).fetchone() is not None


def slots(conn, place_id: int, day_text: str, now: float) -> dict:
    """Время начала на календарную дату: сначала ночной «хвост» вчерашнего клубного дня (00:00–01:00),
    потом дневные часы. Прошедшее не показываем, занятое помечено free=False."""
    place = get_place(conn, place_id)
    d = parse_day(place, day_text, now)
    day_start = midnight(d)
    day_end = day_start + 1440 * 60
    busy = [(r["start_ts"], r["end_ts"]) for r in conn.execute(
        "SELECT start_ts, end_ts FROM bookings WHERE place_id = ? AND status = 'confirmed'"
        " AND end_ts > ? AND start_ts < ?", (place_id, day_start - 86400, day_end + 86400))]
    out = []
    for session in (d - timedelta(days=1), d):
        open_ts, close_ts = window(place, session)
        t = open_ts
        while t + DURATIONS[0] * 3600 <= close_ts:          # начало, после которого не влезает даже 1 час, не предлагаем
            if day_start <= t < day_end and t >= now:
                durations = [h for h in DURATIONS
                             if t + h * 3600 <= close_ts and not any(s < t + h * 3600 and e > t for s, e in busy)]
                out.append({"start": t, "time": hhmm(t), "after_midnight": t < day_start + place["open_min"] * 60,
                            "free": bool(durations), "durations": durations})
            t += STEP
    out.sort(key=lambda x: x["start"])
    return {"date": d.isoformat(), "price": place["price"], "slots": out}


# ---------- создание и отмена ----------

def zone_slots(conn, zone_id: str, day_text: str, now: float) -> dict:
    """Время начала для зоны на календарную дату. Для каждого времени и длительности — сколько мест свободно."""
    zone = get_zone(conn, zone_id)
    d = parse_day(zone, day_text, now)
    day_start = midnight(d)
    day_end = day_start + 86400
    total = conn.execute("SELECT COUNT(*) FROM places WHERE zone_id = ?", (zone_id,)).fetchone()[0]
    busy = [(r["start_ts"], r["end_ts"]) for r in conn.execute(
        "SELECT b.start_ts, b.end_ts FROM bookings b JOIN places p ON p.id = b.place_id"
        " WHERE p.zone_id = ? AND b.status = 'confirmed' AND b.end_ts > ? AND b.start_ts < ?",
        (zone_id, day_start - 86400, day_end + 86400))]
    out = []
    for session in (d - timedelta(days=1), d):
        open_ts, close_ts = window(zone, session)
        t = open_ts
        while t + DURATIONS[0] * 3600 <= close_ts:
            if day_start <= t < day_end and t >= now:
                free = {h: total - sum(1 for s, e in busy if s < t + h * 3600 and e > t)
                        for h in DURATIONS if t + h * 3600 <= close_ts}
                out.append({"start": t, "time": hhmm(t), "after_midnight": t < day_start + zone["open_min"] * 60,
                            "free": free})
            t += STEP
    out.sort(key=lambda x: x["start"])
    return {"date": d.isoformat(), "total": total, "slots": out}


def booking_view(row) -> dict:
    return {
        "id": row["id"], "code": f"CB-{row['id']:04d}",
        "zone": row["zone_name"], "place": place_label(row),
        "date": ddmm(row["start_ts"]), "start_time": hhmm(row["start_ts"]), "end_time": hhmm(row["end_ts"]),
        "start": row["start_ts"], "end": row["end_ts"],
        "hours": row["hours"], "price": row["price"], "status": row["status"],
        "client": row["client_name"], "phone": row["client_phone"], "user_id": row["user_id"],
        "telegram_id": row["telegram_id"],           # есть, если человек связан с Telegram (уведомления бота)
    }


_SELECT = ("SELECT b.*, z.name AS zone_name, z.place_word, p.number, u.telegram_id AS telegram_id FROM bookings b"
           " JOIN places p ON p.id = b.place_id JOIN zones z ON z.id = p.zone_id LEFT JOIN users u ON u.id = b.user_id")


def get_booking(conn, booking_id: int) -> dict:
    row = conn.execute(_SELECT + " WHERE b.id = ?", (booking_id,)).fetchone()
    if not row:
        raise BookingError("no_booking", "Такой брони нет.", 404)
    return booking_view(row)


def create_booking(conn: sqlite3.Connection, user: dict, place_id, start_ts, hours, key, now: float | None = None) -> tuple[dict, bool]:
    """Создаёт бронь. Возвращает (бронь, создана_новая). Повтор с тем же key даёт ту же бронь."""
    now = time.time() if now is None else now
    if hours not in DURATIONS:
        raise BookingError("bad_hours", "Выберите 1, 2, 3 или 5 часов.")
    if not isinstance(start_ts, int) or isinstance(start_ts, bool) or start_ts % STEP:
        raise BookingError("bad_time", "Время начала должно быть кратно 30 минутам.")
    if key is not None and (not isinstance(key, str) or not 8 <= len(key) <= 64):
        raise BookingError("bad_key", "Неверный ключ запроса.")
    place = get_place(conn, place_id)
    end_ts = start_ts + hours * 3600

    if start_ts < now:
        raise BookingError("past", "Это время уже прошло. Выберите другое.")
    first = zone_days(place, now)[0]
    sessions = [first - timedelta(days=1)] + zone_days(place, now)
    if not any(window(place, d)[0] <= start_ts and end_ts <= window(place, d)[1] for d in sessions)             or start_ts >= midnight(first) + (DAYS_AHEAD + 1) * 86400:
        raise BookingError("closed", "Клуб в это время закрыт, или бронь выходит за время закрытия.")

    name = (user.get("name") or user.get("first_name") or "").strip()[:60] or f"id {user['id']}"

    conn.execute("BEGIN IMMEDIATE")          # дальше никто другой не запишет, пока мы не закончим
    try:
        if key:
            same = conn.execute("SELECT id FROM bookings WHERE user_id = ? AND idem_key = ?", (user["id"], key)).fetchone()
            if same:
                conn.execute("COMMIT")
                return get_booking(conn, same["id"]), False
        if _overlaps(conn, place_id, start_ts, end_ts):
            raise BookingError("taken", "Это место уже занято на выбранное время.", 409)
        phone = conn.execute("SELECT phone FROM users WHERE id = ?", (user["id"],)).fetchone()
        price = place["price"] * hours       # цена только из базы
        cur = conn.execute(
            "INSERT INTO bookings (user_id, client_name, client_phone, place_id, start_ts, end_ts, hours, price,"
            " idem_key, created_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user["id"], name, phone["phone"] if phone else None, place_id, start_ts, end_ts, hours, price, key, int(now)),
        )
        new_id = cur.lastrowid
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return get_booking(conn, new_id), True


def cancel_booking(conn, booking_id: int, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    b = get_booking(conn, booking_id)
    if b["status"] == "canceled":
        raise BookingError("already", "Бронь уже отменена.", 409)
    if b["end"] <= now:
        raise BookingError("finished", "Эта бронь уже закончилась.", 409)
    conn.execute("UPDATE bookings SET status = 'canceled', canceled_ts = ? WHERE id = ? AND status = 'confirmed'",
                 (int(now), booking_id))
    return get_booking(conn, booking_id)


def cancel_by_client(conn, booking_id: int, user_id: int, now: float | None = None) -> dict:
    """Клиент отменяет свою бронь, пока она не началась."""
    now = time.time() if now is None else now
    b = get_booking(conn, booking_id)
    if b["user_id"] != user_id:
        raise BookingError("no_booking", "Такой брони нет.", 404)      # чужую бронь даже не показываем
    if b["status"] == "canceled":
        raise BookingError("already", "Бронь уже отменена.", 409)
    if b["start"] <= now:
        raise BookingError("started", "Бронь уже началась. Отмену решает клуб: напишите администратору.", 409)
    return cancel_booking(conn, booking_id, now)


def delete_booking(conn, booking_id: int) -> None:
    """Владелец стирает из истории только ОТМЕНЁННУЮ бронь. Подтверждённые (и будущие, и прошедшие) остаются."""
    b = get_booking(conn, booking_id)
    if b["status"] != "canceled":
        raise BookingError("active", "Стереть можно только отменённую бронь. Подтверждённые остаются в истории.", 409)
    conn.execute("DELETE FROM bookings WHERE id = ? AND status = 'canceled'", (booking_id,))


def delete_by_client(conn, booking_id: int, user_id: int, now: float | None = None) -> dict:
    """Клиент стирает из своего списка отменённую или уже прошедшую бронь. Действующую (идёт/будет) — нельзя."""
    now = time.time() if now is None else now
    b = get_booking(conn, booking_id)
    if b["user_id"] != user_id:
        raise BookingError("no_booking", "Такой брони нет.", 404)
    if b["status"] != "canceled" and b["end"] > now:
        raise BookingError("active", "Стереть можно только отменённую или прошедшую бронь.", 409)
    conn.execute("DELETE FROM bookings WHERE id = ? AND (status = 'canceled' OR end_ts <= ?)", (booking_id, int(now)))
    return b


def clear_mine(conn, user_id: int) -> int:
    """Клиент стирает все свои отменённые брони."""
    return conn.execute("DELETE FROM bookings WHERE status = 'canceled' AND user_id = ?", (user_id,)).rowcount


def canceled_owners(conn) -> list[int]:
    return [r[0] for r in conn.execute("SELECT DISTINCT user_id FROM bookings WHERE status = 'canceled'")]


def signature(conn) -> tuple:
    """Отпечаток всех броней: меняется, когда кто-то (в том числе другая программа — бот) создал или отменил бронь."""
    prices = tuple(r[0] for r in conn.execute("SELECT price FROM zones ORDER BY id"))      # смена цены владельцем тоже считается изменением
    return tuple(conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(canceled_ts), 0) FROM bookings").fetchone()) + prices


def clear_history(conn) -> int:
    """Стирает все отменённые брони. Подтверждённые не трогает."""
    return conn.execute("DELETE FROM bookings WHERE status = 'canceled'").rowcount


def my_bookings(conn, user_id: int) -> list[dict]:
    rows = conn.execute(_SELECT + " WHERE b.user_id = ? ORDER BY b.start_ts DESC LIMIT 50", (user_id,))
    return [booking_view(r) for r in rows]


# ---------- админка ----------

def set_price(conn, zone_id: str, price) -> None:
    if not isinstance(price, int) or isinstance(price, bool) or not 1 <= price <= 1000:
        raise BookingError("bad_price", "Цена за час — целое число от 1 до 1000.")
    get_zone(conn, zone_id)
    conn.execute("UPDATE zones SET price = ? WHERE id = ?", (price, zone_id))


def day_overview(conn, day_text: str, now: float) -> dict:
    """Брони выбранной календарной даты и свободные окна по местам."""
    try:
        d = date.fromisoformat(day_text)
    except (TypeError, ValueError):
        raise BookingError("bad_date", "Неверная дата.") from None
    day_start = midnight(d)
    day_end = day_start + 86400
    rows = conn.execute(
        _SELECT + " WHERE b.start_ts >= ? AND b.start_ts < ? ORDER BY b.start_ts, z.sort, p.number", (day_start, day_end)).fetchall()
    bookings = [booking_view(r) for r in rows]
    confirmed = [b for b in bookings if b["status"] == "confirmed"]
    near = [booking_view(r) for r in conn.execute(           # занятость учитывает и брони, начавшиеся сразу после полуночи
        _SELECT + " WHERE b.status = 'confirmed' AND b.end_ts > ? AND b.start_ts < ?", (day_start, day_end + 86400))]
    zones = []
    for z in conn.execute("SELECT * FROM zones ORDER BY sort"):
        # окна, которые попадают на эту дату: ночной хвост вчерашнего дня и сегодняшний день
        wins = []
        for session in (d - timedelta(days=1), d):
            o, c = window(z, session)
            o, c = max(o, day_start), min(c, day_end + 86400)
            if session == d - timedelta(days=1):
                c = min(c, day_end)
            if c > o:
                wins.append((o, c))
        from_ts = -(-int(now) // STEP) * STEP                    # прошедшее время «свободным» не считаем
        places = []
        for p in conn.execute("SELECT id, number FROM places WHERE zone_id = ? ORDER BY number", (z["id"],)):
            label = f"{z['place_word']} {p['number']}"
            busy = sorted((b["start"], b["end"]) for b in near if b["place"] == label and b["zone"] == z["name"])
            free = []
            for o, c in wins:
                cursor = max(o, from_ts)
                for s_, e_ in busy:
                    if e_ <= cursor or s_ >= c:
                        continue
                    if s_ > cursor:
                        free.append((cursor, s_))
                    cursor = max(cursor, e_)
                if cursor < c:
                    free.append((cursor, c))
            free = [(a_, b_) for a_, b_ in free if b_ > a_]
            whole = not busy and from_ts <= wins[-1][0] if wins else False
            places.append({"id": p["id"], "label": label, "free": [f"{hhmm(a_)}–{hhmm(b_)}" for a_, b_ in free], "free_all": whole})
        zones.append({"id": z["id"], "name": z["name"], "price": z["price"], "places": places})
    canceled_total = conn.execute("SELECT COUNT(*) FROM bookings WHERE status = 'canceled'").fetchone()[0]
    return {"date": d.isoformat(), "canceled_total": canceled_total, "bookings": bookings,
            "total": sum(b["price"] for b in confirmed), "zones": zones}
