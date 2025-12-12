import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

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


# === Клавиатура с кнопками ===

def get_main_keyboard():
    """
    Главная клавиатура с кнопками команд
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📝 Подписаться"),
                KeyboardButton(text="📋 Мои подписки")
            ],
            [
                KeyboardButton(text="⚙️ Фильтры"),
                KeyboardButton(text="❌ Отписаться")
            ],
            [
                KeyboardButton(text="ℹ️ Помощь")
            ]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )
    return keyboard


# === Обработчики кнопок (должны быть первыми!) ===

@dp.message(F.text == "📝 Подписаться")
async def button_subscribe(message: types.Message, state: FSMContext):
    """
    Обработка нажатия кнопки Подписаться
    """
    await state.clear()  # Сбрасываем предыдущее состояние
    await state.set_state(SubscribeStates.waiting_for_repo)
    await message.answer(
        "Отправьте ссылку на GitHub репозиторий:\n"
        "Например: <code>https://github.com/owner/repo</code>",
        parse_mode="HTML"
    )


@dp.message(F.text == "📋 Мои подписки")
async def button_list(message: types.Message, state: FSMContext):
    """
    Обработка нажатия кнопки Мои подписки
    """
    await state.clear()  # Сбрасываем предыдущее состояние

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
        if events:
            text += f"События: {', '.join(events)}\n"
        else:
            text += f"События: все\n"
        if excluded:
            text += f"Исключены: {', '.join(excluded)}\n"
        text += "\n"

    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@dp.message(F.text == "⚙️ Фильтры")
async def button_filters(message: types.Message, state: FSMContext):
    """
    Обработка нажатия кнопки Фильтры
    """
    await state.clear()  # Сбрасываем предыдущее состояние

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
            callback_data=f"filter_repo:{repo_name}"
        )])

    await state.set_state(FilterStates.waiting_for_repo_choice)
    await message.answer(
        "Выберите репозиторий для настройки фильтров:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


@dp.message(F.text == "❌ Отписаться")
async def button_unsubscribe(message: types.Message, state: FSMContext):
    """
    Обработка нажатия кнопки Отписаться
    """
    await state.clear()  # Сбрасываем предыдущее состояние

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
            callback_data=f"unsub:{repo_name}"
        )])

    await message.answer(
        "Выберите репозиторий для отписки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


@dp.message(F.text == "ℹ️ Помощь")
async def button_help(message: types.Message, state: FSMContext):
    """
    Обработка нажатия кнопки Помощь
    """
    await state.clear()  # Сбрасываем предыдущее состояние

    text = """
<b>Как использовать бота:</b>

1️⃣ <b>Подписка на репозиторий</b>
   📝 Подписаться - введите ссылку на репозиторий
   Пример: https://github.com/owner/repo

2️⃣ <b>Настройка фильтров</b>
   ⚙️ Фильтры - выбрать репозиторий - настроить:
   • Исключить авторов (например, dependabot[bot])
   • Выбрать типы событий (push, issues, pull_request, workflow_run)
   • Группировать сообщения (ВКЛ/ВЫКЛ)

3️⃣ <b>Просмотр подписок</b>
   📋 Мои подписки - список активных подписок с фильтрами

4️⃣ <b>Отписка</b>
   ❌ Отписаться - выбрать репозиторий

<b>Группировка событий:</b>
• ВЫКЛ (по умолчанию) - каждое событие отдельным сообщением
• ВКЛ - все события за минуту в одном сообщении

<b>Формат уведомлений:</b>
• Push: список коммитов с авторами и ссылками
• Issues: создание, закрытие, комментарии
• Pull Requests: создание, merge, комментарии к коду
• Actions: статус выполнения workflow
    """
    await message.answer(text, parse_mode="HTML")


# === Команды ===

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """
    Приветственное сообщение
    """
    text = """
🤖 <b>GitHub Notification Bot</b>

Бот для получения уведомлений о событиях в GitHub репозиториях

<b>Поддерживаемые события:</b>
• Push (новые коммиты)
• Issues (создание, комментарии)
• Pull Requests (создание, комментарии)
• GitHub Actions (запуск, статус выполнения)

Используйте кнопки ниже для управления подписками!
    """
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """
    Справка
    """

    text = """
<b>Как использовать бота:</b>

1️⃣ <b>Подписка на репозиторий</b>
   📝 Подписаться - введите ссылку на репозиторий
   Пример: https://github.com/owner/repo

2️⃣ <b>Настройка фильтров</b>
   ⚙️ Фильтры - выбрать репозиторий - настроить:
   • Исключить авторов (например, dependabot[bot])
   • Выбрать типы событий (push, issues, pull_request, workflow_run)
   • Группировать сообщения (ВКЛ/ВЫКЛ)

3️⃣ <b>Просмотр подписок</b>
   📋 Мои подписки - список активных подписок с фильтрами

4️⃣ <b>Отписка</b>
   ❌ Отписаться - выбрать репозиторий

<b>Группировка событий:</b>
• ВЫКЛ (по умолчанию) - каждое событие отдельным сообщением
• ВКЛ - все события за минуту в одном сообщении

<b>Формат уведомлений:</b>
• Push: список коммитов с авторами и ссылками
• Issues: создание, закрытие, комментарии
• Pull Requests: создание, merge, комментарии к коду
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

    # сохранение подписки
    await message.answer("Настройка подписки...")

    # Пытаемся создать webhook (обязательно для работы бота!)
    webhook_id = None
    webhook_status = ""
    try:
        from config import Config
        if Config.WEBHOOK_HOST and Config.WEBHOOK_HOST != "http://localhost":
            webhook_id = github_api.create_webhook(owner, repo_name)
            if webhook_id:
                webhook_status = "\n🔗 Webhook настроен (мгновенные уведомления)"
                logger.info(f"Webhook created: id={webhook_id} for {repo_url}")
            else:
                webhook_status = "\n❌ Не удалось создать webhook! Проверьте права токена (admin:repo_hook)"
        else:
            webhook_status = "\n⚠️ WEBHOOK_HOST не настроен! Настройте ngrok для получения уведомлений"
    except Exception as e:
        logger.warning(f"Failed to create webhook: {e}")
        webhook_status = "\n❌ Ошибка создания webhook. Проверьте настройки WEBHOOK_HOST"

    storage.add_subscription(chat_id, repo_url, webhook_id=webhook_id)
    storage.add_repo_chat_mapping(repo_url, chat_id)
    logger.info(f"Subscription created: chat_id={chat_id}, repo={repo_url}, webhook_id={webhook_id}")

    await message.answer(
        f"✅ <b>Подписка оформлена!</b>\n\n"
        f"<b>{repo_info['full_name']}</b>\n"
        f"{repo_info['description'] or 'Без описания'}\n"
        f"{repo_info['stars']} stars"
        f"{webhook_status}\n\n"
        f"Используйте кнопку <b> Фильтры</b> для настройки фильтров",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
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
        if events:
            text += f"События: {', '.join(events)}\n"
        else:
            text += f"События: все\n"
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
            callback_data=f"unsub:{repo_name}"
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

    repo_name = callback.data.replace("unsub:", "")
    repo_url = f"https://github.com/{repo_name}"
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
            callback_data=f"filter_repo:{repo_name}"
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

    repo_name = callback.data.replace("filter_repo:", "")
    repo_url = f"https://github.com/{repo_name}"
    await state.update_data(repo_url=repo_url)

    filters = storage.get_filters(callback.message.chat.id, repo_url)
    group_events = filters.get('group_events', False) if filters else False
    group_status = "✅ ВКЛ" if group_events else "❌ ВЫКЛ"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Исключить автора", callback_data="filter:add_author")],
        [InlineKeyboardButton(text="Удалить из исключений", callback_data="filter:remove_author")],
        [InlineKeyboardButton(text="Типы событий", callback_data="filter:events")],
        [InlineKeyboardButton(text=f"Группировать сообщения: {group_status}", callback_data="filter:toggle_group")],
        [InlineKeyboardButton(text="Отмена", callback_data="filter:cancel")]
    ])

    text = f"<b>Фильтры для {repo_url.replace('https://github.com/', '')}</b>\n\n"
    if filters:
        excluded = filters.get('excluded_authors', [])
        events = filters.get('event_types', [])
        text += f"Исключённые авторы: {', '.join(excluded) if excluded else 'не выбрано'}\n"
        text += f"Типы событий: {', '.join(events) if events else 'все'}\n"
        text += f"Группировать сообщения: {'включено' if group_events else 'выключено'}"
    else:
        text += "Фильтры не настроены"

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

    excluded_authors = filters.get("excluded_authors", []) if filters else []
    if not excluded_authors:
        await callback.answer("Нет исключенных авторов", show_alert=True)
        return

    keyboard = []
    for author in excluded_authors:
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
        status = "✅" if event in current_events else "❌"
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
        status = "✅" if e in selected else "❌"
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


@dp.callback_query(F.data == "filter:toggle_group")
async def filter_toggle_group(callback: types.CallbackQuery, state: FSMContext):
    """
    Переключение группировки событий
    """

    data = await state.get_data()
    repo_url = data.get("repo_url")

    # Получаем текущее состояние
    filters = storage.get_filters(callback.message.chat.id, repo_url)
    current_group = filters.get('group_events', False) if filters else False

    # Переключаем
    new_group = not current_group
    storage.set_group_events(callback.message.chat.id, repo_url, new_group)

    # Обновляем кнопку
    group_status = "✅ ВКЛ" if new_group else "❌ ВЫКЛ"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Исключить автора", callback_data="filter:add_author")],
        [InlineKeyboardButton(text="Удалить из исключений", callback_data="filter:remove_author")],
        [InlineKeyboardButton(text="Типы событий", callback_data="filter:events")],
        [InlineKeyboardButton(text=f"Группировать сообщения: {group_status}", callback_data="filter:toggle_group")],
        [InlineKeyboardButton(text="Отмена", callback_data="filter:cancel")]
    ])

    # Обновляем текст
    filters = storage.get_filters(callback.message.chat.id, repo_url)
    text = f"<b>Фильтры для {repo_url.replace('https://github.com/', '')}</b>\n\n"
    if filters:
        excluded = filters.get('excluded_authors', [])
        events = filters.get('event_types', [])
        text += f"Исключённые авторы: {', '.join(excluded) if excluded else 'не выбрано'}\n"
        text += f"Типы событий: {', '.join(events) if events else 'все'}\n"
        text += f"Группировать сообщения: {'включено ✅' if new_group else 'выключено ❌'}"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer(f"Группировка сообщений {'включена' if new_group else 'выключена'}")


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
