import asyncio
import logging
import signal
import sys

from bot import bot, dp, send_notification
from webhook_server import start_webhook_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    """
    Main обработчик бота и webhook сервера
    """

    logger.info("Starting GitHub Telegram Notification Bot...")

    # запуск webhook сервер
    webhook_runner = await start_webhook_server(notification_func=send_notification)

    # запуск telegram бота
    try:
        logger.info("Starting Telegram bot polling...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
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
