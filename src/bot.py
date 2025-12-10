import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from redis_storage import storage
from github_api import github_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class SubscribeStates(StatesGroup):
    waiting_for_repo = State()


class FilterStates(StatesGroup):
    waiting_for_repo_choice = State()
    waiting_for_filter_action = State()
    waiting_for_author = State()
    waiting_for_events = State()


# === Команды ===

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """
    Приветственное сообщение
    """
    text = """
    
🤖 <b>GitHub Notification Bot</b>

    Бот для получения уведомлений о событиях в GitHub репозиториях
    
    <b>Доступные команды:</b>
    /subscribe - Подписаться на репозиторий
    /unsubscribe - Отписаться от репозитория
    /list - Список подписок
    /filters - Настроить фильтры
    /help - Помощь
    
    <b>Поддерживаемые события:</b>
    • Push (новые коммиты)
    • Issues (создание, комментарии)
    • Pull Requests (создание, комментарии)
    • GitHub Actions (запуск, статус выполнения)
    """
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """
    Справка
    """

    text = """
    <b>Как использовать бота:</b>
    
    1️⃣ <b>Подписка на репозиторий</b>
       /subscribe → введите ссылку на репозиторий
       Пример: https://github.com/owner/repo
    
    2️⃣ <b>Настройка фильтров</b>
       /filters - выбрать репозиторий - настроить:
       • Исключить авторов (например, dependabot)
       • Выбрать типы событий
    
    3️⃣ <b>Отписка</b>
       /unsubscribe - выбрать репозиторий
    
    <b>Формат уведомлений:</b>
    • Push: список коммитов с авторами
    • Issues/PR: текст с комментарием
    • Actions: статус выполнения workflow
    """
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("subscribe"))
async def cmd_subscribe(message: types.Message, state: FSMContext):
    """
    Подключение к репозиторию
    """

    await state.set_state(SubscribeStates.waiting_for_repo)
    await message.answer(
        "Отправьте ссылку на GitHub репозиторий:\n"
        "Например: <code>https://github.com/owner/repo</code>",
        parse_mode="HTML"
    )


@dp.message(SubscribeStates.waiting_for_repo)
async def process_repo_url(message: types.Message, state: FSMContext):
    """
    Обработка полученного URL репозитория
    """

    url = message.text.strip()
    parsed = github_api.parse_repo_url(url)

    if not parsed:
        await message.answer("Неверный формат ссылки. Попробуйте ещё раз")
        return

    owner, repo_name = parsed
    repo_url = f"https://github.com/{owner}/{repo_name}"
    chat_id = message.chat.id

    # проверка существует ли репозиторий
    repo_info = github_api.get_repo_info(owner, repo_name)
    if not repo_info:
        await message.answer("Репозиторий не найден или нет доступа")
        await state.clear()
        return

    # проверка имеющейся подписки на репозиторий
    existing = storage.get_subscription(chat_id, repo_url)
    if existing:
        await message.answer("Вы уже подписаны на этот репозиторий")
        await state.clear()
        return

    # настройка webhook
    await message.answer("Настройка webhook...")
    webhook_id = github_api.create_webhook(owner, repo_name)

    if not webhook_id:
        await message.answer(
            "Не удалось создать webhook. Убедитесь, что токен настроен с admin:repo_hook\n"
            "Подписка создана, но уведомления могут не приходить"
        )

    # сохранение подписку
    storage.add_subscription(chat_id, repo_url, webhook_id)
    storage.add_repo_chat_mapping(repo_url, chat_id)

    await message.answer(
        f" <b>Подписка оформлена!</b>\n\n"
        f" <b>{repo_info['full_name']}</b>\n"
        f" {repo_info['description'] or 'Без описания'}\n"
        f" {repo_info['stars']} stars\n\n"
        f"Используйте /filters для настройки фильтров",
        parse_mode="HTML"
    )
    await state.clear()


@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    """
    Список подписок на репозитории
    """

    chat_id = message.chat.id
    subs = storage.get_all_subscriptions(chat_id)

    if not subs:
        await message.answer("У вас нет активных подписок.\nИспользуйте /subscribe для подписки")
        return

    text = "<b>Ваши подписки:</b>\n\n"
    for repo_url, data in subs.items():
        filters = data.get("filters", {})
        excluded = filters.get("excluded_authors", [])
        events = filters.get("event_types", [])

        text += f"<a href='{repo_url}'>{repo_url.replace('https://github.com/', '')}</a>\n"
        text += f"События: {', '.join(events)}\n"
        if excluded:
            text += f"Исключены: {', '.join(excluded)}\n"
        text += "\n"

    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: types.Message):
    """
    Отписаться от репозитория
    """

    chat_id = message.chat.id
    subs = storage.get_all_subscriptions(chat_id)

    if not subs:
        await message.answer("У вас нет активных подписок на репозитории")
        return

    keyboard = []
    for repo_url in subs.keys():
        repo_name = repo_url.replace("https://github.com/", "")
        keyboard.append([InlineKeyboardButton(
            text=repo_name,
            callback_data=f"unsub:{repo_url}"
        )])

    await message.answer(
        "Выберите репозиторий для отписки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


@dp.callback_query(F.data.startswith("unsub:"))
async def process_unsubscribe(callback: types.CallbackQuery):
    """
    Обработка отписки
    """

    repo_url = callback.data.replace("unsub:", "")
    chat_id = callback.message.chat.id

    sub = storage.get_subscription(chat_id, repo_url)
    if sub:
        # удаляем webhook если есть
        webhook_id = sub.get("webhook_id")
        if webhook_id:
            parsed = github_api.parse_repo_url(repo_url)
            if parsed:
                github_api.delete_webhook(parsed[0], parsed[1], webhook_id)

        storage.remove_subscription(chat_id, repo_url)
        storage.remove_repo_chat_mapping(repo_url, chat_id)

        await callback.message.edit_text(f"Отписка от {repo_url} выполнена!")
    else:
        await callback.message.edit_text("Подписка не найдена")

    await callback.answer()


@dp.message(Command("filters"))
async def cmd_filters(message: types.Message, state: FSMContext):
    """
    Настройка фильтров подписок
    """

    chat_id = message.chat.id
    subs = storage.get_all_subscriptions(chat_id)

    if not subs:
        await message.answer("У вас нет активных подписок")
        return

    keyboard = []
    for repo_url in subs.keys():
        repo_name = repo_url.replace("https://github.com/", "")
        keyboard.append([InlineKeyboardButton(
            text=repo_name,
            callback_data=f"filter_repo:{repo_url}"
        )])

    await state.set_state(FilterStates.waiting_for_repo_choice)
    await message.answer(
        "Выберите репозиторий для настройки фильтров:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


@dp.callback_query(F.data.startswith("filter_repo:"))
async def process_filter_repo(callback: types.CallbackQuery, state: FSMContext):
    """
    Выбор репозитория для применения фильтров
    """

    repo_url = callback.data.replace("filter_repo:", "")
    await state.update_data(repo_url=repo_url)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Исключить автора", callback_data="filter:add_author")],
        [InlineKeyboardButton(text="Удалить из исключений", callback_data="filter:remove_author")],
        [InlineKeyboardButton(text="Типы событий", callback_data="filter:events")],
        [InlineKeyboardButton(text="Отмена", callback_data="filter:cancel")]
    ])

    filters = storage.get_filters(callback.message.chat.id, repo_url)
    text = f"<b>Фильтры для {repo_url.replace('https://github.com/', '')}</b>\n\n"
    if filters:
        text += f"Исключённые авторы: {', '.join(filters['excluded_authors']) or 'не выбрано'}\n"
        text += f"Типы событий: {', '.join(filters['event_types'])}"

    await callback.message.edit_text(text, parse_mode="HTML",
                                      reply_markup=keyboard)
    await state.set_state(FilterStates.waiting_for_filter_action)
    await callback.answer()


@dp.callback_query(F.data == "filter:add_author")
async def filter_add_author(callback: types.CallbackQuery, state: FSMContext):
    """
    Исключить автора из уведомлений
    """

    await callback.message.edit_text(
        "Введите имя пользователя GitHub для исключения:\n"
        "Например: <code>dependabot[bot]</code>",
        parse_mode="HTML"
    )
    await state.set_state(FilterStates.waiting_for_author)
    await state.update_data(action="add")
    await callback.answer()


@dp.callback_query(F.data == "filter:remove_author")
async def filter_remove_author(callback: types.CallbackQuery, state: FSMContext):
    """
    Удаление автора из исключений уведомлений
    """

    data = await state.get_data()
    repo_url = data.get("repo_url")
    filters = storage.get_filters(callback.message.chat.id, repo_url)

    if not filters or not filters["excluded_authors"]:
        await callback.answer("Нет исключенных авторов", show_alert=True)
        return

    keyboard = []
    for author in filters["excluded_authors"]:
        keyboard.append([InlineKeyboardButton(
            text=author,
            callback_data=f"rm_author:{author}"
        )])

    await callback.message.edit_text(
        "Выберите автора для удаления из исключений:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("rm_author:"))
async def process_remove_author(callback: types.CallbackQuery, state: FSMContext):
    """
    Удаление автора
    """

    author = callback.data.replace("rm_author:", "")
    data = await state.get_data()
    repo_url = data.get("repo_url")

    storage.remove_excluded_author(callback.message.chat.id, repo_url, author)
    await callback.message.edit_text(f"Автор {author} удалён из исключений")
    await state.clear()
    await callback.answer()


@dp.message(FilterStates.waiting_for_author)
async def process_author_input(message: types.Message, state: FSMContext):
    """
    Обработка ввода нового автора
    """

    author = message.text.strip()
    data = await state.get_data()
    repo_url = data.get("repo_url")
    action = data.get("action")

    if action == "add":
        storage.add_excluded_author(message.chat.id, repo_url, author)
        await message.answer(f"Автор <code>{author}</code> добавлен в исключения.", parse_mode="HTML")

    await state.clear()


@dp.callback_query(F.data == "filter:events")
async def filter_events(callback: types.CallbackQuery, state: FSMContext):
    """
    Настройка типов событий для получения уведомлений
    """

    data = await state.get_data()
    repo_url = data.get("repo_url")
    filters = storage.get_filters(callback.message.chat.id, repo_url)
    current_events = filters.get("event_types", []) if filters else []

    all_events = ["push", "issues", "pull_request", "workflow_run"]

    keyboard = []
    for event in all_events:
        status = "YES" if event in current_events else "NO"
        keyboard.append([InlineKeyboardButton(
            text=f"{status} {event}",
            callback_data=f"toggle_event:{event}"
        )])
    keyboard.append([InlineKeyboardButton(text="Сохранить", callback_data="save_events")])

    await state.update_data(selected_events=current_events)
    await callback.message.edit_text(
        "Выберите типы событий для отслеживания:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await state.set_state(FilterStates.waiting_for_events)
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_event:"))
async def toggle_event(callback: types.CallbackQuery, state: FSMContext):
    """
    Смена типа события
    """

    event = callback.data.replace("toggle_event:", "")
    data = await state.get_data()
    selected = data.get("selected_events", [])

    if event in selected:
        selected.remove(event)
    else:
        selected.append(event)

    await state.update_data(selected_events=selected)

    all_events = ["push", "issues", "pull_request", "workflow_run"]
    keyboard = []
    for e in all_events:
        status = "YES" if e in selected else "NO"
        keyboard.append([InlineKeyboardButton(
            text=f"{status} {e}",
            callback_data=f"toggle_event:{e}"
        )])
    keyboard.append([InlineKeyboardButton(text="Сохранить", callback_data="save_events")])

    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()


@dp.callback_query(F.data == "save_events")
async def save_events(callback: types.CallbackQuery, state: FSMContext):
    """
    Сохранение выбранных событий
    """

    data = await state.get_data()
    repo_url = data.get("repo_url")
    selected = data.get("selected_events", [])

    if not selected:
        await callback.answer("Выберите хотя бы один тип события", show_alert=True)
        return

    storage.set_event_types(callback.message.chat.id, repo_url, selected)
    await callback.message.edit_text(f"Типы событий сохранены: {', '.join(selected)}")
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "filter:cancel")
async def filter_cancel(callback: types.CallbackQuery, state: FSMContext):
    """
    Отмена настройки фильтров
    """

    await callback.message.edit_text("Настройка фильтров отменена")
    await state.clear()
    await callback.answer()


async def send_notification(chat_id: int, text: str, event_key: str = None,
                            edit_existing: bool = False) -> int:
    """
    Отправить или отредактировать уведомление
    """

    if edit_existing and event_key:
        existing_msg_id = storage.get_message_id(chat_id, event_key)
        if existing_msg_id:
            try:
                await bot.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=existing_msg_id,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                return existing_msg_id
            except Exception:
                pass  # отправка нового при неудачном редактировании

    msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

    if event_key:
        storage.save_message_id(chat_id, event_key, msg.message_id)

    return msg.message_id


async def start_bot():
    """
    Запуск бота
    """

    logger.info("starting Telegram bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(start_bot())
