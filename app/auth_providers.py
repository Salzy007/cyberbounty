"""Проверка входа через Telegram: подпись данных с токеном бота (старый виджет). Вход по ссылке на бота — в server.py."""
import hashlib
import hmac
import time

from app.booking import BookingError

TG_MAX_AGE = 24 * 3600
PHONE_CODE_TTL = 10 * 60
PHONE_CODE_ATTEMPTS = 5


def phone_code_hash(token_hash: str, code: str) -> str:
    """Код хранится только хэшем. Бот считает ту же формулу (см. bot.py)."""
    return hashlib.sha256(f"{token_hash}:{code}".encode()).hexdigest()


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
