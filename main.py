"""Запуск: .venv\\Scripts\\python main.py  ->  http://127.0.0.1:8002"""
import uvicorn

from app.config import load_settings
from app.server import create_app

settings = load_settings()
app = create_app(settings)

if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
