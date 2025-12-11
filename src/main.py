import asyncio
import logging
import signal
import sys
from pathlib import Path

from bot import bot, dp, send_notification
from webhook_server import start_webhook_server
from github_polling import GitHubPoller

# Создаём папку для логов
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Настройка логирования в файл и консоль
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """
    Main обработчик бота и webhook сервера
    """

    logger.info("Starting GitHub Telegram Notification Bot...")

    # запуск webhook сервер (для будущего использования)
    webhook_runner = await start_webhook_server(notification_func=send_notification)

    # запуск GitHub polling (опрос событий)
    poller = GitHubPoller(notification_func=send_notification, poll_interval=60)
    polling_task = asyncio.create_task(poller.start())
    logger.info("GitHub polling task created")

    # запуск telegram бота
    try:
        logger.info("Starting Telegram bot polling...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        # остановка polling
        logger.info("Stopping GitHub polling...")
        await poller.stop()
        polling_task.cancel()

        # очистка после запуска
        await webhook_runner.cleanup()
        await bot.session.close()


def handle_signal(signum, frame):
    """
    Обработка команд завершения
    """

    logger.info("Received shutdown signal")
    sys.exit(0)


if __name__ == "__main__":
    # регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # запуск сервиса
    asyncio.run(main())
