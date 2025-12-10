import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    # GitHub
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

    # Webhook
    WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "http://localhost")
    WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8080))
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "secret")

    @classmethod
    def get_webhook_url(cls) -> str:
        return f"{cls.WEBHOOK_HOST}/webhook/github"
