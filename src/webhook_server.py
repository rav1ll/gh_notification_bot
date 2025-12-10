import hmac
import hashlib
import logging
import asyncio
from aiohttp import web

from config import Config
from redis_storage import storage
from event_handlers import (
    get_event_handler,
    get_author_from_event,
    get_event_type_for_filter
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ссылка на функцию отправки сообщений из бота (будет установлена при запуске)
send_notification_func = None


def verify_signature(payload: bytes, signature: str) -> bool:
    """
    Проверка подписи вебхука
    """

    if not signature:
        return False

    expected = "sha256=" + hmac.new(
        Config.WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


async def handle_github_webhook(request: web.Request) -> web.Response:
    """
    Обработчик GitHub webhook
    """



    # получение заголовка
    event_type = request.headers.get("X-GitHub-Event")
    signature = request.headers.get("X-Hub-Signature-256")
    delivery_id = request.headers.get("X-GitHub-Delivery")

    if not event_type:
        return web.Response(status=400, text="Missing event type")

    # получение тела запроса
    try:
        payload_bytes = await request.read()
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse payload: {e}")
        return web.Response(status=400, text="Invalid payload")

    # проверка подписи
    if Config.WEBHOOK_SECRET and not verify_signature(payload_bytes, signature):
        logger.warning(f"Invalid signature for delivery {delivery_id}")
        return web.Response(status=401, text="Invalid signature")

    logger.info(f"Received event: {event_type}, delivery: {delivery_id}")

    # ping
    if event_type == "ping":
        return web.Response(text="pong")

    # получение обработчика события
    handler = get_event_handler(event_type)
    if not handler:
        logger.info(f"No handler for event type: {event_type}")
        return web.Response(text="OK")

    # формат сообщений
    try:
        text, event_key = handler(payload)
        if not text:
            return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Error formatting event: {e}")
        return web.Response(status=500, text="Formatting error")

    # получение URL репозитория
    repo = payload.get("repository", {})
    repo_url = repo.get("html_url", "")

    if not repo_url:
        return web.Response(text="OK")
    repo_url = repo_url.rstrip("/")

    # получение автора события
    author = get_author_from_event(event_type, payload)
    filter_event_type = get_event_type_for_filter(event_type)

    # получение чатов, подписанных на этот репозиторий
    chat_ids = storage.get_chats_for_repo(repo_url)
    logger.info(f"Found {len(chat_ids)} subscribed chats for {repo_url}")

    for chat_id in chat_ids:
        # фильтры для этого чата
        filters = storage.get_filters(chat_id, repo_url)

        if filters:
            # проверка, включён ли тип события
            if filter_event_type not in filters.get("event_types", []):
                logger.info(f"Event type {filter_event_type} filtered out for chat {chat_id}")
                continue

            # проверка исключения автора
            excluded_authors = filters.get("excluded_authors", [])
            if author and author in excluded_authors:
                logger.info(f"Author {author} filtered out for chat {chat_id}")
                continue

        # отправка уведомлений
        if send_notification_func:
            try:
                # необходимость редактирования сообщения
                edit_existing = event_type in ["workflow_run", "pull_request"]
                await send_notification_func(
                    chat_id=chat_id,
                    text=text,
                    event_key=event_key,
                    edit_existing=edit_existing
                )
                logger.info(f"Notification sent to chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send notification to {chat_id}: {e}")

    return web.Response(text="OK")


async def health_check(request: web.Request) -> web.Response:
    """
    Проверка сервера
    """

    return web.Response(text="OK")


def create_app() -> web.Application:
    """
    Создание веб-приложения
    """

    app = web.Application()
    app.router.add_post("/webhook/github", handle_github_webhook)
    app.router.add_get("/health", health_check)
    return app


async def start_webhook_server(notification_func=None):
    """
    Запуск webhook сервера
    """


    send_notification_func = notification_func

    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", Config.WEBHOOK_PORT)
    await site.start()
    logger.info(f"Webhook server started on port {Config.WEBHOOK_PORT}")
    return runner


if __name__ == "__main__":
    async def main():
        await start_webhook_server()
        # Keep running
        while True:
            await asyncio.sleep(3600)

    asyncio.run(main())
