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

    # получение функции отправки из app state
    send_notification_func = request.app.get('notification_func')

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
    logger.info(f"Payload preview: repository={payload.get('repository', {}).get('full_name')}, action={payload.get('action')}")

    # ping
    if event_type == "ping":
        logger.info("Received ping event - webhook is configured correctly!")
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
        logger.warning("No repository URL in payload")
        return web.Response(text="OK")
    repo_url = repo_url.rstrip("/")
    logger.info(f"Processing event for repository: {repo_url}")

    # получение автора события
    author = get_author_from_event(event_type, payload)
    filter_event_type = get_event_type_for_filter(event_type)

    # получение чатов, подписанных на этот репозиторий
    chat_ids = storage.get_chats_for_repo(repo_url)
    logger.info(f"Found {len(chat_ids)} subscribed chats for {repo_url}")

    if not chat_ids:
        logger.warning(f"No subscribed chats for repository {repo_url}")
        return web.Response(text="OK")

    for chat_id in chat_ids:
        # фильтры для этого чата
        filters = storage.get_filters(chat_id, repo_url)

        if filters:
            # проверка, включён ли тип события (только если event_types не пустой)
            event_types = filters.get("event_types", [])
            if event_types and filter_event_type not in event_types:
                logger.info(f"Event type {filter_event_type} filtered out for chat {chat_id}")
                continue

            # проверка исключения автора
            excluded_authors = filters.get("excluded_authors", [])
            if author and author in excluded_authors:
                logger.info(f"Author {author} filtered out for chat {chat_id}")
                continue

        # отправка уведомлений
        logger.info(f"Sending notification to chat {chat_id}")
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
                logger.info(f"✅ Notification sent successfully to chat {chat_id}")
            except Exception as e:
                logger.error(f"❌ Failed to send notification to {chat_id}: {e}", exc_info=True)
        else:
            logger.error("❌ send_notification_func is not set!")

    return web.Response(text="OK")


async def health_check(request: web.Request) -> web.Response:
    """
    Проверка сервера
    """

    return web.Response(text="OK")


def create_app(notification_func=None) -> web.Application:
    """
    Создание веб-приложения
    """

    app = web.Application()

    # сохраняем функцию в app state
    if notification_func:
        app['notification_func'] = notification_func

    app.router.add_post("/webhook/github", handle_github_webhook)
    app.router.add_get("/health", health_check)
    return app


async def start_webhook_server(notification_func=None):
    """
    Запуск webhook сервера
    """

    app = create_app(notification_func)
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
