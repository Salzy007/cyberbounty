"""Настройки. Секреты только из .env (он не попадает в GitHub)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    admin_password: str = ""
    db_path: Path = BASE_DIR / "data" / "pcclub.db"
    host: str = "127.0.0.1"
    port: int = 8002
    secure_cookie: bool = False          # True, когда сайт открыт по https
    # вход через Telegram: токен бота нужен только серверу для проверки подписи; username — публичный
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    google_client_id: str = ""
    smtp_host: str = ""                  # пусто — код входа по почте пишется в лог сервера (режим разработки)
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""


def load_settings() -> Settings:
    return Settings(
        admin_password=os.getenv("ADMIN_PASSWORD", "").strip(),
        db_path=Path(os.getenv("DB_PATH")) if os.getenv("DB_PATH") else BASE_DIR / "data" / "pcclub.db",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8002")),
        secure_cookie=os.getenv("SECURE_COOKIE", "") == "1",
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_bot_username=os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@"),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        smtp_host=os.getenv("SMTP_HOST", "").strip(),
        smtp_port=int(os.getenv("SMTP_PORT", "587") or 587),
        smtp_user=os.getenv("SMTP_USER", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from=os.getenv("SMTP_FROM", "").strip(),
    )
