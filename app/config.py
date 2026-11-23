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
    # вход через Telegram: username бота нужен для ссылки «Войти через Telegram»
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""


def load_settings() -> Settings:
    return Settings(
        admin_password=os.getenv("ADMIN_PASSWORD", "").strip(),
        db_path=Path(os.getenv("DB_PATH")) if os.getenv("DB_PATH") else BASE_DIR / "data" / "pcclub.db",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8002")),
        secure_cookie=os.getenv("SECURE_COOKIE", "") == "1",
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_bot_username=os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@"),
    )
