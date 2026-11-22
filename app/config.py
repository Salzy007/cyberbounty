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


def load_settings() -> Settings:
    return Settings(
        admin_password=os.getenv("ADMIN_PASSWORD", "").strip(),
        db_path=Path(os.getenv("DB_PATH")) if os.getenv("DB_PATH") else BASE_DIR / "data" / "pcclub.db",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8002")),
        secure_cookie=os.getenv("SECURE_COOKIE", "") == "1",
    )
