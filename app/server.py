"""Сайт CyberBounty: FastAPI. Правила брони — в app/booking.py, всё проверяет сервер.

Публично (смотреть можно без входа): GET /api/config, /api/zones/{id}/slots, /api/zones/{id}/busy, /api/wait
Клиент (cookie cb_session): POST /api/login, /api/logout, GET /api/me, POST /api/bookings,
    GET /api/my-bookings, POST /api/bookings/{id}/cancel
Владелец (cookie cb_admin, пароль из .env): POST /api/admin/login|logout, GET /api/admin/me|day,
    POST /api/admin/bookings/{id}/cancel, DELETE /api/admin/bookings/{id}, POST /api/admin/clear, PATCH /api/admin/zones/{id}
"""
import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import asyncio

from app import accounts, auth_providers as providers, booking
from app.booking import BookingError
from app.config import BASE_DIR, Settings
from app.db import connect, init_db
from app.live import hub

WEB_DIR = BASE_DIR / "web"
MAX_BODY = 4_000
USER_TTL = 30 * 86400
ADMIN_TTL = 12 * 3600


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def clean_phone(raw) -> str:
    digits = re.sub(r"\D", "", raw if isinstance(raw, str) else "")
    if not 7 <= len(digits) <= 15:
        raise BookingError("bad_phone", "Введите телефон: от 7 до 15 цифр.")
    return digits


def clean_name(raw) -> str:
    name = re.sub(r"\s+", " ", raw if isinstance(raw, str) else "").strip()
    if not 2 <= len(name) <= 40:
        raise BookingError("bad_name", "Имя — от 2 до 40 символов.")
    return name


class Limiter:
    """Не больше N попыток за окно на один адрес (защита входа от перебора)."""
    def __init__(self, limit: int, window: float):
        self.limit, self.window, self.hits = limit, window, defaultdict(deque)

    def hit(self, key: str) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise BookingError("slow_down", "Слишком много попыток. Подождите минуту.", 429)
        q.append(now)


def create_app(settings: Settings) -> FastAPI:
    init_db(settings.db_path)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db_path = settings.db_path
    login_limit, admin_limit = Limiter(10, 60), Limiter(5, 60)
    sig = {"v": None}          # отпечаток броней: так замечаем, что бот (другая программа) что-то записал в общую базу

    def db():
        return connect(settings.db_path)

    # ---------- сессии ----------

    def start_session(conn, kind: str, user_id, ttl: int) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        conn.execute("DELETE FROM sessions WHERE expires_ts < ?", (now,))
        conn.execute("INSERT INTO sessions (token_hash, kind, user_id, created_ts, expires_ts) VALUES (?, ?, ?, ?, ?)",
                     (_hash(token), kind, user_id, now, now + ttl))
        return token

    def set_cookie(resp: Response, name: str, token: str, ttl: int) -> None:
        resp.set_cookie(name, token, max_age=ttl, httponly=True, samesite="lax", secure=settings.secure_cookie, path="/")

    def session_row(request: Request, cookie: str, kind: str):
        token = request.cookies.get(cookie)
        if not token:
            return None
        conn = db()
        try:
            return conn.execute("SELECT s.user_id, u.* FROM sessions s LEFT JOIN users u ON u.id = s.user_id"
                                " WHERE s.token_hash = ? AND s.kind = ? AND s.expires_ts > ?",
                                (_hash(token), kind, int(time.time()))).fetchone()
        finally:
            conn.close()

    def current_user(request: Request) -> dict | None:
        row = session_row(request, "cb_session", "user")
        return accounts.public(row) if row and row["name"] is not None else None

    def need_user(request: Request) -> dict:
        user = current_user(request)
        if not user:
            raise HTTPException(401, "Войдите, чтобы забронировать.")
        return user

    def need_admin(request: Request) -> None:
        if not session_row(request, "cb_admin", "admin"):
            raise HTTPException(403, "Админка только для владельца.")

    def drop_session(request: Request, cookie: str) -> None:
        token = request.cookies.get(cookie)
        if token:
            conn = db()
            try:
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))
            finally:
                conn.close()

    async def read_json(request: Request) -> dict:
        if "application/json" not in request.headers.get("content-type", ""):
            raise HTTPException(415, "Неверный запрос.")
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise HTTPException(413, "Слишком большой запрос.")
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(400, "Неверный запрос.") from None
        if not isinstance(data, dict):
            raise HTTPException(400, "Неверный запрос.")
        return data

    @app.exception_handler(BookingError)
    async def booking_error(_: Request, exc: BookingError):
        return JSONResponse({"error": exc.message, "code": exc.code}, status_code=exc.status)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.method in ("POST", "PATCH", "DELETE"):           # запросы только с нашего же сайта
            origin = request.headers.get("origin")
            if origin and origin.split("://", 1)[-1] != request.headers.get("host"):
                return JSONResponse({"error": "Запрос с чужого сайта."}, status_code=403)
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        elif path.startswith("/fonts/"):
            response.headers["Cache-Control"] = "public, max-age=604800"
        else:
            response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    client_ip = lambda r: r.client.host if r.client else "?"

    # ---------- публичное ----------

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/api/config")
    async def config(request: Request):
        conn = db()
        try:
            return {"zones": booking.catalog(conn, time.time()), "durations": list(booking.DURATIONS),
                    "version": hub.version(0), "now": int(time.time()), "me": current_user(request)}
        finally:
            conn.close()

    @app.get("/api/zones/{zone_id}/slots")
    async def zone_slots(zone_id: str, date: str):
        conn = db()
        try:
            return booking.zone_slots(conn, zone_id, date, time.time())
        finally:
            conn.close()

    @app.get("/api/zones/{zone_id}/busy")
    async def zone_busy(zone_id: str, at: int, hours: int = 1):
        """Какие места заняты на выбранное окно [at, at + hours)."""
        now = time.time()
        if hours not in booking.DURATIONS or not (now - 1800 <= at <= now + 9 * 86400):
            raise BookingError("bad_time", "Это время недоступно.")
        conn = db()
        try:
            booking.get_zone(conn, zone_id)
            return {"busy": booking.busy_at(conn, zone_id, at, hours * 3600)}
        finally:
            conn.close()

    def sync_signature() -> None:
        conn = db()
        try:
            now_sig = booking.signature(conn)
        finally:
            conn.close()
        if sig["v"] is not None and sig["v"] != now_sig:
            hub.publish(0)
        sig["v"] = now_sig

    @app.get("/api/wait")
    async def wait(since: int | None = None):
        if since is None:
            return {"version": hub.version(0), "changed": False}
        for _ in range(12):                      # ждём до ~24 с, раз в 2 с глядя, не записал ли бот что-то в общую базу
            sync_signature()
            version, changed = await hub.wait(0, since, timeout=2.0)
            if changed:
                return {"version": version, "changed": True}
        return {"version": hub.version(0), "changed": False}

    # ---------- клиент ----------

    def finish_login(conn, row, request: Request) -> JSONResponse:
        token = start_session(conn, "user", row["id"], USER_TTL)
        resp = JSONResponse({"me": accounts.public(row)})
        set_cookie(resp, "cb_session", token, USER_TTL)
        return resp

    @app.get("/api/auth/providers")
    async def auth_providers():
        """Какие способы входа настроены. Сейчас это только Telegram."""
        tg = bool(settings.telegram_bot_username)
        return {"telegram": {"enabled": tg}}

    @app.post("/api/auth/telegram/start")
    async def tg_start(request: Request):
        """Вход через бота без домена и BotFather: даём ссылку t.me/бот?start=login_<секрет>, бот подтверждает, сайт ждёт."""
        login_limit.hit(client_ip(request))
        if not settings.telegram_bot_username:
            raise BookingError("off", "Вход через Telegram не настроен.", 503)
        secret = secrets.token_urlsafe(24)
        conn = db()
        try:
            conn.execute("DELETE FROM tg_logins WHERE expires_ts < ?", (int(time.time()),))
            conn.execute("INSERT INTO tg_logins (token_hash, expires_ts) VALUES (?, ?)", (_hash(secret), int(time.time()) + 300))
        finally:
            conn.close()
        return {"token": secret, "url": f"https://t.me/{settings.telegram_bot_username}?start=login_{secret}"}

    @app.post("/api/auth/telegram/poll")
    async def tg_poll(request: Request):
        data = await read_json(request)
        token = data.get("token")
        if not isinstance(token, str) or not 10 <= len(token) <= 64:
            raise BookingError("bad_token", "Неверный запрос.")
        conn = db()
        try:
            row = conn.execute("SELECT * FROM tg_logins WHERE token_hash = ?", (_hash(token),)).fetchone()
            if not row or row["expires_ts"] < time.time():
                raise BookingError("expired", "Время входа вышло. Нажмите кнопку ещё раз.", 410)
            if row["telegram_id"] is None:
                return {"status": "pending"}
            if row["expect_tg"] and row["telegram_id"] != row["expect_tg"]:
                conn.execute("DELETE FROM tg_logins WHERE token_hash = ?", (row["token_hash"],))
                raise BookingError("wrong_tg", "Этот Telegram не привязан к вашему номеру. Войдите по номеру: бот пришлёт код.", 403)
            conn.execute("DELETE FROM tg_logins WHERE token_hash = ?", (row["token_hash"],))      # секрет одноразовый
            cur = current_user(request)
            user = accounts.sign_in(conn, "telegram_id", row["telegram_id"], row["name"], current_id=cur["id"] if cur else None)
            return finish_login(conn, user, request)
        finally:
            conn.close()

    @app.post("/api/auth/telegram")
    async def auth_telegram(request: Request):
        login_limit.hit(client_ip(request))
        data = await read_json(request)
        tg = providers.verify_telegram(data, settings.telegram_bot_token)
        cur = current_user(request)
        conn = db()
        try:
            row = accounts.sign_in(conn, "telegram_id", tg["id"], tg["name"], current_id=cur["id"] if cur else None)
            return finish_login(conn, row, request)
        finally:
            conn.close()

    @app.post("/api/auth/phone/start")
    async def phone_start(request: Request):
        """Шаг 1: имя и телефон. Даём ссылку на бота: там человек поделится номером, и бот пришлёт код в Telegram."""
        login_limit.hit(client_ip(request))
        data = await read_json(request)
        name, phone = clean_name(data.get("name")), clean_phone(data.get("phone"))
        bot = settings.telegram_bot_username
        if not bot:
            raise BookingError("off", "Вход по телефону пока не настроен. Войдите через Telegram.", 503)
        secret = secrets.token_urlsafe(24)
        conn = db()
        try:
            known = conn.execute("SELECT telegram_id FROM users WHERE phone = ?", (phone,)).fetchone()
            if known and known["telegram_id"]:
                # номер уже подтверждён и привязан к Telegram: вход в один клик, но только с этого Telegram
                conn.execute("DELETE FROM tg_logins WHERE expires_ts < ?", (int(time.time()),))
                conn.execute("INSERT INTO tg_logins (token_hash, expires_ts, expect_tg) VALUES (?, ?, ?)",
                             (_hash(secret), int(time.time()) + providers.PHONE_CODE_TTL, known["telegram_id"]))
                return {"token": secret, "url": f"https://t.me/{bot}?start=login_{secret}", "bot": bot, "mode": "tg"}
            conn.execute("DELETE FROM phone_logins WHERE expires_ts < ?", (int(time.time()),))
            conn.execute("INSERT INTO phone_logins (token_hash, phone, name, expires_ts) VALUES (?, ?, ?, ?)",
                         (_hash(secret), phone, name, int(time.time()) + providers.PHONE_CODE_TTL))
        finally:
            conn.close()
        return {"token": secret, "url": f"https://t.me/{bot}?start=phone_{secret}", "bot": bot, "mode": "contact"}

    def phone_row(conn, token):
        if not isinstance(token, str) or not 10 <= len(token) <= 64:
            raise BookingError("expired", "Время входа вышло. Начните заново.", 410)
        row = conn.execute("SELECT * FROM phone_logins WHERE token_hash = ? AND expires_ts > ?",
                           (_hash(token), int(time.time()))).fetchone()
        if not row:
            raise BookingError("expired", "Время входа вышло. Начните заново.", 410)
        return row

    @app.post("/api/auth/phone/poll")
    async def phone_poll(request: Request):
        data = await read_json(request)
        conn = db()
        try:
            row = phone_row(conn, data.get("token"))
            return {"status": "code" if row["code_hash"] else "pending"}
        finally:
            conn.close()

    @app.post("/api/auth/phone/verify")
    async def phone_verify(request: Request):
        data = await read_json(request)
        token, code = data.get("token"), data.get("code")
        conn = db()
        try:
            row = phone_row(conn, token)
            if not row["code_hash"]:
                raise BookingError("no_code", "Код ещё не пришёл. Откройте бота и поделитесь номером.", 400)
            if row["attempts"] >= providers.PHONE_CODE_ATTEMPTS:
                raise BookingError("bad_code", "Слишком много неверных попыток. Начните вход заново.", 429)
            if not isinstance(code, str) or not hmac.compare_digest(
                    providers.phone_code_hash(row["token_hash"], code.strip()), row["code_hash"]):
                conn.execute("UPDATE phone_logins SET attempts = attempts + 1 WHERE token_hash = ?", (row["token_hash"],))
                raise BookingError("bad_code", "Неверный код.", 400)
            conn.execute("DELETE FROM phone_logins WHERE token_hash = ?", (row["token_hash"],))      # код одноразовый
            cur = current_user(request)
            user = accounts.link_phone_telegram(conn, row["phone"], row["tg_id"], row["name"],
                                                current_id=cur["id"] if cur else None)
            return finish_login(conn, user, request)
        finally:
            conn.close()

    @app.post("/api/logout")
    async def logout(request: Request):
        drop_session(request, "cb_session")
        resp = JSONResponse({"ok": True})
        resp.delete_cookie("cb_session", path="/")
        return resp

    @app.post("/api/bookings")
    async def create(request: Request):
        user = need_user(request)
        data = await read_json(request)
        conn = db()
        try:
            created, is_new = booking.create_booking(
                conn, user, data.get("place_id"), data.get("start"), data.get("hours"), data.get("key"))
        finally:
            conn.close()
        if is_new:
            hub.publish(0, user["id"])
        return {"booking": created, "duplicate": not is_new}

    @app.get("/api/my-bookings")
    async def my(request: Request):
        user = need_user(request)
        conn = db()
        try:
            return {"bookings": booking.my_bookings(conn, user["id"])}
        finally:
            conn.close()

    @app.post("/api/bookings/{booking_id}/cancel")
    async def cancel_mine(booking_id: int, request: Request):
        user = need_user(request)
        conn = db()
        try:
            canceled = booking.cancel_by_client(conn, booking_id, user["id"])
        finally:
            conn.close()
        hub.publish(0, user["id"])
        return {"booking": canceled}

    # ---------- владелец ----------

    @app.post("/api/admin/login")
    async def admin_login(request: Request):
        admin_limit.hit(client_ip(request))
        data = await read_json(request)
        given = data.get("password")
        if not settings.admin_password or not isinstance(given, str) or not hmac.compare_digest(
                given.encode(), settings.admin_password.encode()):
            raise HTTPException(403, "Неверный пароль.")
        conn = db()
        try:
            token = start_session(conn, "admin", None, ADMIN_TTL)
        finally:
            conn.close()
        resp = JSONResponse({"ok": True})
        set_cookie(resp, "cb_admin", token, ADMIN_TTL)
        return resp

    @app.post("/api/admin/logout")
    async def admin_logout(request: Request):
        drop_session(request, "cb_admin")
        resp = JSONResponse({"ok": True})
        resp.delete_cookie("cb_admin", path="/")
        return resp

    @app.get("/api/admin/me")
    async def admin_me(request: Request):
        need_admin(request)
        return {"ok": True}

    @app.get("/api/admin/day")
    async def admin_day(date: str, request: Request):
        need_admin(request)
        conn = db()
        try:
            return booking.day_overview(conn, date, time.time())
        finally:
            conn.close()

    @app.post("/api/admin/bookings/{booking_id}/cancel")
    async def admin_cancel(booking_id: int, request: Request):
        need_admin(request)
        conn = db()
        try:
            canceled = booking.cancel_booking(conn, booking_id)
        finally:
            conn.close()
        hub.publish(0, canceled["user_id"])
        return {"booking": canceled}

    @app.delete("/api/admin/bookings/{booking_id}")
    async def admin_delete(booking_id: int, request: Request):
        need_admin(request)
        conn = db()
        try:
            booking.delete_booking(conn, booking_id)
        finally:
            conn.close()
        hub.publish(0)
        return {"ok": True}

    @app.post("/api/admin/clear")
    async def admin_clear(request: Request):
        """Стирает из истории только отменённые брони. Подтверждённые остаются."""
        need_admin(request)
        conn = db()
        try:
            removed = booking.clear_history(conn)
        finally:
            conn.close()
        hub.publish(0)
        return {"removed": removed}

    @app.patch("/api/admin/zones/{zone_id}")
    async def admin_price(zone_id: str, request: Request):
        need_admin(request)
        data = await read_json(request)
        conn = db()
        try:
            booking.set_price(conn, zone_id, data.get("price"))
        finally:
            conn.close()
        hub.publish(0)
        return {"ok": True}

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
