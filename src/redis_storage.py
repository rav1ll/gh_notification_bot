import json
from typing import Optional
import redis

from config import Config


"""
Хранилище redis
"""

class RedisStorage:
    def __init__(self):
        self.client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            password=Config.REDIS_PASSWORD,
            decode_responses=True
        )


    def add_subscription(self, chat_id: int, repo_url: str, webhook_id: int = None) -> bool:
        """
        Добавить подписку на заданный репозиторий
        """

        key = f"subscriptions:{chat_id}"
        data = {
            "repo_url": repo_url,
            "webhook_id": webhook_id,
            "filters": {
                "excluded_authors": [],
                "event_types": ["push", "issues", "pull_request", "workflow_run"]
            }
        }
        return self.client.hset(key, repo_url, json.dumps(data))

    def get_subscription(self, chat_id: int, repo_url: str) -> Optional[dict]:
        """
        Получить подписку
        """

        key = f"subscriptions:{chat_id}"
        data = self.client.hget(key, repo_url)
        return json.loads(data) if data else None

    def get_all_subscriptions(self, chat_id: int) -> dict:
        """
        Получить все подписки для чата
        """

        key = f"subscriptions:{chat_id}"
        data = self.client.hgetall(key)
        return {k: json.loads(v) for k, v in data.items()}

    def remove_subscription(self, chat_id: int, repo_url: str) -> bool:
        """
        Удалить подписку
        """

        key = f"subscriptions:{chat_id}"
        return self.client.hdel(key, repo_url) > 0

    def update_webhook_id(self, chat_id: int, repo_url: str, webhook_id: int) -> bool:
        """
        Обновить ID вебхука
        """

        sub = self.get_subscription(chat_id, repo_url)
        if sub:
            sub["webhook_id"] = webhook_id
            key = f"subscriptions:{chat_id}"
            return self.client.hset(key, repo_url, json.dumps(sub))
        return False


    def set_excluded_authors(self, chat_id: int, repo_url: str, authors: list) -> bool:
        """
        Установить список исключённых авторов
        """

        sub = self.get_subscription(chat_id, repo_url)
        if sub:
            sub["filters"]["excluded_authors"] = authors
            key = f"subscriptions:{chat_id}"
            return self.client.hset(key, repo_url, json.dumps(sub))
        return False

    def add_excluded_author(self, chat_id: int, repo_url: str, author: str) -> bool:
        """
        Добавить автора в исключения
        """

        sub = self.get_subscription(chat_id, repo_url)
        if sub:
            if author not in sub["filters"]["excluded_authors"]:
                sub["filters"]["excluded_authors"].append(author)
            key = f"subscriptions:{chat_id}"
            return self.client.hset(key, repo_url, json.dumps(sub))
        return False

    def remove_excluded_author(self, chat_id: int, repo_url: str, author: str) -> bool:
        """
        Удалить автора из исключений
        """

        sub = self.get_subscription(chat_id, repo_url)
        if sub and author in sub["filters"]["excluded_authors"]:
            sub["filters"]["excluded_authors"].remove(author)
            key = f"subscriptions:{chat_id}"
            return self.client.hset(key, repo_url, json.dumps(sub))
        return False

    def set_event_types(self, chat_id: int, repo_url: str, event_types: list) -> bool:
        """
        Настроить виды отслеживаемых событий
        """

        sub = self.get_subscription(chat_id, repo_url)
        if sub:
            sub["filters"]["event_types"] = event_types
            key = f"subscriptions:{chat_id}"
            return self.client.hset(key, repo_url, json.dumps(sub))
        return False

    def get_filters(self, chat_id: int, repo_url: str) -> Optional[dict]:
        """
        Получить фильтры для заданной подписки
        """

        sub = self.get_subscription(chat_id, repo_url)
        return sub["filters"] if sub else None


    def add_repo_chat_mapping(self, repo_url: str, chat_id: int):
        """
        Привязать репозиторий к чату
        """

        key = f"repo_chats:{repo_url}"
        self.client.sadd(key, chat_id)

    def get_chats_for_repo(self, repo_url: str) -> set:
        """
        Получить все чаты, подписанные на заданный репозиторий
        """

        key = f"repo_chats:{repo_url}"
        return {int(x) for x in self.client.smembers(key)}

    def remove_repo_chat_mapping(self, repo_url: str, chat_id: int):
        """
        Удалить связь репозитория и чата
        """

        key = f"repo_chats:{repo_url}"
        self.client.srem(key, chat_id)


    def save_message_id(self, chat_id: int, event_key: str, message_id: int):
        """
        Сохранить ID сообщения для редактирования
        """

        key = f"messages:{chat_id}"
        self.client.hset(key, event_key, message_id)
        self.client.expire(key, 86400)  # 24 часа

    def get_message_id(self, chat_id: int, event_key: str) -> Optional[int]:
        """
        Получить ID заданного сохранённого сообщения
        """

        key = f"messages:{chat_id}"
        msg_id = self.client.hget(key, event_key)
        return int(msg_id) if msg_id else None

    def delete_message_id(self, chat_id: int, event_key: str):
        """
        Удалить сохранённый ID сообщения
        """

        key = f"messages:{chat_id}"
        self.client.hdel(key, event_key)


storage = RedisStorage()
