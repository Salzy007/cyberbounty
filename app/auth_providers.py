"""Проверка входа через Telegram, Google и почту. Доверяем только тому, что проверили подписью/сервером Google."""
import hashlib
import hmac
import logging
import secrets
import smtplib
import time
from email.message import EmailMessage

import httpx

from app.booking import BookingError

log = logging.getLogger("cyberbounty")
TG_MAX_AGE = 24 * 3600
CODE_TTL = 10 * 60
CODE_ATTEMPTS = 5


# ---------- Telegram Login Widget ----------

def verify_telegram(data: dict, bot_token: str, now: float | None = None) -> dict:
    """Подпись виджета: hash = HMAC-SHA256(строка полей, ключ = SHA256(токен бота)). Подделать без токена нельзя."""
    if not bot_token:
        raise BookingError("off", "Вход через Telegram не настроен.", 503)
    fields = {k: str(v) for k, v in data.items() if k != "hash" and v is not None and isinstance(v, (str, int))}
    got = data.get("hash")
    if not isinstance(got, str) or "id" not in fields:
        raise BookingError("bad_tg", "Данные от Telegram повреждены.", 401)
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    expected = hmac.new(hashlib.sha256(bot_token.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, got):
        raise BookingError("bad_tg", "Подпись Telegram не сходится.", 401)
    try:
        age = (time.time() if now is None else now) - int(fields.get("auth_date", "0"))
        tg_id = int(fields["id"])
    except ValueError:
        raise BookingError("bad_tg", "Данные от Telegram повреждены.", 401) from None
    if age > TG_MAX_AGE:
        raise BookingError("bad_tg", "Вход устарел. Попробуйте ещё раз.", 401)
    name = " ".join(filter(None, [fields.get("first_name"), fields.get("last_name")])) or fields.get("username", "")
    return {"id": tg_id, "name": name}


# ---------- Google Identity Services ----------

def verify_google(credential: str, client_id: str) -> dict:
    """ID-токен проверяет сам Google (tokeninfo): подпись и срок. Мы сверяем, что он выдан нашему приложению."""
    if not client_id:
        raise BookingError("off", "Вход через Google не настроен.", 503)
    if not isinstance(credential, str) or not 20 <= len(credential) <= 4000:
        raise BookingError("bad_google", "Google не подтвердил вход.", 401)
    try:
        r = httpx.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": credential}, timeout=8)
    except httpx.HTTPError:
        raise BookingError("google_down", "Не удалось связаться с Google. Попробуйте позже.", 502) from None
    if r.status_code != 200:
        raise BookingError("bad_google", "Google не подтвердил вход.", 401)
    info = r.json()
    if info.get("aud") != client_id or info.get("iss") not in ("accounts.google.com", "https://accounts.google.com") \
            or int(info.get("exp", 0)) < time.time() or not info.get("sub"):
        raise BookingError("bad_google", "Google не подтвердил вход.", 401)
    verified = str(info.get("email_verified")).lower() == "true"
    return {"sub": info["sub"], "email": info["email"].lower() if verified and info.get("email") else None,
            "name": info.get("name") or ""}


# ---------- вход по почте: код из 6 цифр ----------

def _hash_code(email: str, code: str) -> str:
    return hashlib.sha256(f"{email}:{code}".encode()).hexdigest()


def smtp_ready(settings) -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def send_code(settings, email: str, code: str) -> None:
    if not smtp_ready(settings):
        log.warning("[DEV] SMTP не настроен. Код входа для %s: %s (действует 10 минут)", email, code)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, email, "Код входа CyberBounty"
    msg.set_content(f"Ваш код входа: {code}\nОн действует 10 минут. Если это не вы — просто проигнорируйте письмо.\n\nCyberBounty (демо-проект)")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except (OSError, smtplib.SMTPException):
        log.exception("Не удалось отправить письмо")
        raise BookingError("mail_failed", "Не удалось отправить письмо. Попробуйте позже.", 502) from None


def issue_code(conn, email: str, now: float | None = None) -> str:
    """Выдаёт код (отправляет вызывающий).  Не чаще раза в 30 секунд и 5 раз в час на адрес."""
    now = int(time.time() if now is None else now)
    row = conn.execute("SELECT * FROM email_codes WHERE email = ?", (email,)).fetchone()
    sent = [int(x) for x in (row["sent_log"].split(",") if row and row["sent_log"] else []) if now - int(x) < 3600]
    if sent and now - sent[-1] < 30:
        raise BookingError("slow_down", "Код уже отправлен. Следующий можно запросить через 30 секунд.", 429)
    if len(sent) >= 5:
        raise BookingError("slow_down", "Слишком много кодов. Попробуйте через час.", 429)
    code = f"{secrets.randbelow(10**6):06d}"
    conn.execute("INSERT INTO email_codes (email, code_hash, expires_ts, attempts, created_ts, sent_log) VALUES (?, ?, ?, 0, ?, ?)"
                 " ON CONFLICT(email) DO UPDATE SET code_hash = excluded.code_hash, expires_ts = excluded.expires_ts,"
                 " attempts = 0, created_ts = excluded.created_ts, sent_log = excluded.sent_log",
                 (email, _hash_code(email, code), now + CODE_TTL, now, ",".join(map(str, sent + [now]))))
    return code


def check_code(conn, email: str, code, now: float | None = None) -> None:
    now = int(time.time() if now is None else now)
    row = conn.execute("SELECT * FROM email_codes WHERE email = ?", (email,)).fetchone()
    if not row or row["expires_ts"] < now:
        raise BookingError("bad_code", "Код не найден или устарел. Запросите новый.", 400)
    if row["attempts"] >= CODE_ATTEMPTS:
        raise BookingError("bad_code", "Слишком много неверных попыток. Запросите новый код.", 429)
    if not isinstance(code, str) or not hmac.compare_digest(_hash_code(email, code.strip()), row["code_hash"]):
        conn.execute("UPDATE email_codes SET attempts = attempts + 1 WHERE email = ?", (email,))
        raise BookingError("bad_code", "Неверный код.", 400)
    conn.execute("UPDATE email_codes SET expires_ts = 0 WHERE email = ?", (email,))    # код одноразовый
