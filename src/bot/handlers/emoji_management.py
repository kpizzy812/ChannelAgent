"""
Обработчики управления Custom Emoji
Команда /emoji для добавления, просмотра и удаления Premium эмодзи
"""

from typing import Optional, List
from datetime import datetime

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# aiogram
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Локальные импорты
from src.bot.filters.owner import OwnerFilter
from src.emoji.dictionary import get_emoji_dictionary, reload_emoji_dictionary
from src.database.crud.emoji import get_emoji_crud

# Настройка логгера модуля
logger = logger.bind(module="emoji_management")

# Создаем роутер
emoji_router = Router()


class EmojiStates(StatesGroup):
    """Состояния FSM для управления эмодзи"""
    waiting_for_emoji_message = State()  # Ожидание сообщения с Custom Emoji
    waiting_for_standard_emoji = State()  # Ожидание стандартного эмодзи для маппинга
    waiting_for_category = State()       # Ожидание категории


# Временное хранилище для процесса добавления
_adding_emoji_data = {}


def get_emoji_menu_keyboard():
    """Клавиатура меню управления эмодзи"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список эмодзи", callback_data="emoji_list")],
        [InlineKeyboardButton(text="➕ Добавить эмодзи", callback_data="emoji_add")],
        [InlineKeyboardButton(text="🗑 Удалить связь", callback_data="emoji_delete_mode")],
        [InlineKeyboardButton(text="🧪 Тест публикации", callback_data="emoji_test")],
        [InlineKeyboardButton(text="🔄 Обновить кеш", callback_data="emoji_refresh")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])


def get_emoji_list_keyboard(emojis: list, page: int = 0, per_page: int = 10):
    """Клавиатура со списком эмодзи"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    buttons = []

    # Эмодзи на текущей странице
    start = page * per_page
    end = start + per_page
    page_emojis = emojis[start:end]

    for emoji in page_emojis:
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji.standard_emoji} → {emoji.alt_text} ({emoji.usage_count})",
                callback_data=f"emoji_view_{emoji.id}"
            )
        ])

    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"emoji_page_{page-1}"))
    if end < len(emojis):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"emoji_page_{page+1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="emoji_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_emoji_detail_keyboard(emoji_id: int):
    """Клавиатура для детального просмотра эмодзи"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Удалить", callback_data=f"emoji_delete_{emoji_id}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="emoji_list")]
    ])


def get_category_keyboard():
    """Клавиатура выбора категории"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    categories = [
        ("🟢 Позитивные", "positive"),
        ("🔴 Негативные", "negative"),
        ("💰 Крипто", "crypto"),
        ("📊 Общие", "general"),
    ]

    buttons = [[InlineKeyboardButton(text=name, callback_data=f"emoji_cat_{cat}")]
               for name, cat in categories]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="emoji_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_emoji_delete_keyboard(emojis: list, page: int = 0, per_page: int = 10):
    """Клавиатура для удаления эмодзи"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    buttons = []

    # Эмодзи на текущей странице
    start = page * per_page
    end = start + per_page
    page_emojis = emojis[start:end]

    for emoji in page_emojis:
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {emoji.standard_emoji} → {emoji.alt_text}",
                callback_data=f"emoji_confirm_delete_{emoji.id}"
            )
        ])

    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"emoji_delpage_{page-1}"))
    if end < len(emojis):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"emoji_delpage_{page+1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="emoji_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@emoji_router.message(Command("emoji"), OwnerFilter())
async def emoji_command(message: Message):
    """Команда /emoji - управление Custom Emoji"""
    try:
        dictionary = await get_emoji_dictionary()
        emoji_count = dictionary.count

        text = f"""<b>🎨 Управление Custom Emoji</b>

📊 <b>Статистика:</b>
• Эмодзи в словаре: <code>{emoji_count}</code>
• Кеш загружен: {'✅' if dictionary.is_loaded else '❌'}

<i>Выберите действие:</i>"""

        await message.answer(text, reply_markup=get_emoji_menu_keyboard(), parse_mode="HTML")

    except Exception as e:
        logger.error("Ошибка команды /emoji: {}", str(e))
        await message.answer("❌ Произошла ошибка")


@emoji_router.callback_query(F.data == "emoji_menu", OwnerFilter())
async def show_emoji_menu(callback: CallbackQuery, state: FSMContext):
    """Показать меню управления эмодзи"""
    await state.clear()

    dictionary = await get_emoji_dictionary()
    emoji_count = dictionary.count

    text = f"""<b>🎨 Управление Custom Emoji</b>

📊 <b>Статистика:</b>
• Эмодзи в словаре: <code>{emoji_count}</code>
• Кеш загружен: {'✅' if dictionary.is_loaded else '❌'}

<i>Выберите действие:</i>"""

    await callback.message.edit_text(text, reply_markup=get_emoji_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


@emoji_router.callback_query(F.data == "emoji_list", OwnerFilter())
async def show_emoji_list(callback: CallbackQuery):
    """Показать список эмодзи"""
    try:
        crud = get_emoji_crud()
        emojis = await crud.get_all(active_only=True)

        if not emojis:
            await callback.message.edit_text(
                "📋 <b>Список Custom Emoji</b>\n\n"
                "<i>Словарь пуст. Добавьте эмодзи через меню.</i>",
                reply_markup=get_emoji_menu_keyboard(),
                parse_mode="HTML"
            )
        else:
            # Формируем список эмодзи для копирования
            emoji_chars = " ".join([e.standard_emoji for e in emojis])
            text = (
                f"📋 <b>Список Custom Emoji</b>\n\n"
                f"Всего: {len(emojis)}\n\n"
                f"<b>Для копирования:</b>\n<code>{emoji_chars}</code>\n"
            )
            await callback.message.edit_text(
                text,
                reply_markup=get_emoji_list_keyboard(emojis),
                parse_mode="HTML"
            )

        await callback.answer()

    except Exception as e:
        logger.error("Ошибка показа списка эмодзи: {}", str(e))
        await callback.answer("Ошибка загрузки", show_alert=True)


@emoji_router.callback_query(F.data.startswith("emoji_page_"), OwnerFilter())
async def emoji_pagination(callback: CallbackQuery):
    """Пагинация списка эмодзи"""
    try:
        page = int(callback.data.split("_")[2])
        crud = get_emoji_crud()
        emojis = await crud.get_all(active_only=True)

        # Формируем список эмодзи для копирования
        emoji_chars = " ".join([e.standard_emoji for e in emojis])
        text = (
            f"📋 <b>Список Custom Emoji</b>\n\n"
            f"Всего: {len(emojis)}\n\n"
            f"<b>Для копирования:</b>\n<code>{emoji_chars}</code>\n"
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_emoji_list_keyboard(emojis, page),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error("Ошибка пагинации: {}", str(e))
        await callback.answer("Ошибка", show_alert=True)


@emoji_router.callback_query(F.data.startswith("emoji_view_"), OwnerFilter())
async def view_emoji_detail(callback: CallbackQuery):
    """Детальный просмотр эмодзи"""
    try:
        emoji_id = int(callback.data.split("_")[2])
        crud = get_emoji_crud()
        emoji = await crud.get_by_id(emoji_id)

        if not emoji:
            await callback.answer("Эмодзи не найден", show_alert=True)
            return

        text = f"""<b>🎨 Custom Emoji</b>

📝 <b>Стандартный:</b> {emoji.standard_emoji}
✨ <b>Premium:</b> {emoji.alt_text}
🆔 <b>Document ID:</b> <code>{emoji.document_id}</code>

📁 <b>Категория:</b> {emoji.category}
📝 <b>Описание:</b> {emoji.description or 'нет'}
📊 <b>Использований:</b> {emoji.usage_count}

🕐 <b>Добавлен:</b> {emoji.created_at.strftime('%d.%m.%Y %H:%M')}"""

        await callback.message.edit_text(
            text,
            reply_markup=get_emoji_detail_keyboard(emoji_id),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error("Ошибка просмотра эмодзи: {}", str(e))
        await callback.answer("Ошибка", show_alert=True)


@emoji_router.callback_query(F.data == "emoji_add", OwnerFilter())
async def start_add_emoji(callback: CallbackQuery, state: FSMContext):
    """Начать добавление эмодзи"""
    await state.set_state(EmojiStates.waiting_for_emoji_message)

    text = """<b>➕ Добавление Custom Emoji</b>

Отправьте сообщение с Premium эмодзи, который хотите добавить.

<b>Как получить:</b>
1. Найдите сообщение с Premium эмодзи
2. Перешлите его сюда
3. Или отправьте новое с нужным эмодзи

<i>Отправьте сообщение с Premium эмодзи...</i>"""

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="emoji_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=cancel_kb, parse_mode="HTML")
    await callback.answer()


@emoji_router.message(EmojiStates.waiting_for_emoji_message, OwnerFilter())
async def process_emoji_message(message: Message, state: FSMContext):
    """Обработать сообщение с Custom Emoji"""
    try:
        # Для aiogram сообщений извлекаем базовую информацию
        custom_emojis = []

        if message.entities:
            for entity in message.entities:
                if entity.type == "custom_emoji":
                    emoji_char = message.text[entity.offset:entity.offset + entity.length]
                    # aiogram возвращает custom_emoji_id как строку, преобразуем в int
                    doc_id = int(entity.custom_emoji_id)
                    custom_emojis.append((emoji_char, doc_id))

        if not custom_emojis:
            await message.answer(
                "❌ В сообщении не найдено Premium Custom Emoji.\n\n"
                "Убедитесь что отправляете сообщение с Premium эмодзи, "
                "а не обычными."
            )
            return

        # Получаем полную информацию через Telegram API (включая связанный стандартный эмодзи)
        extracted_with_info = []
        try:
            from src.userbot.client import get_userbot_client
            from src.emoji.extractor import get_emoji_extractor

            extractor = await get_emoji_extractor()
            client_wrapper = await get_userbot_client()

            if client_wrapper and client_wrapper.client:
                extractor.set_client(client_wrapper.client)
                doc_ids = [doc_id for _, doc_id in custom_emojis]
                emoji_info = await extractor.get_emoji_info(doc_ids)

                for emoji_char, doc_id in custom_emojis:
                    if doc_id in emoji_info:
                        extracted_with_info.append(emoji_info[doc_id])
                    else:
                        # Fallback
                        from src.emoji.extractor import ExtractedEmoji
                        extracted_with_info.append(ExtractedEmoji(
                            document_id=doc_id,
                            premium_char=emoji_char,
                            standard_emoji=emoji_char,
                            is_free=False
                        ))
        except Exception as api_error:
            logger.warning("Не удалось получить info через API: {}", str(api_error))
            # Fallback - используем символы из сообщения
            from src.emoji.extractor import ExtractedEmoji
            for emoji_char, doc_id in custom_emojis:
                extracted_with_info.append(ExtractedEmoji(
                    document_id=doc_id,
                    premium_char=emoji_char,
                    standard_emoji=emoji_char,
                    is_free=False
                ))

        # Сохраняем данные
        user_id = message.from_user.id
        _adding_emoji_data[user_id] = extracted_with_info

        # Показываем найденные эмодзи
        first_emoji = extracted_with_info[0]

        text = f"""<b>✅ Premium эмодзи получен!</b>

🆔 Document ID: <code>{first_emoji.document_id}</code>

<b>📝 Как будет работать:</b>
Когда в тексте поста встретится {first_emoji.standard_emoji} — он автоматически заменится на отправленный вами Premium эмодзи.

<b>Заменять {first_emoji.standard_emoji}?</b>"""

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"✅ Да, заменять {first_emoji.standard_emoji}",
                callback_data="emoji_use_detected"
            )],
            [InlineKeyboardButton(text="✏️ Нет, указать другой", callback_data="emoji_use_custom")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="emoji_menu")]
        ])

        await state.set_state(EmojiStates.waiting_for_standard_emoji)
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logger.error("Ошибка обработки сообщения с эмодзи: {}", str(e))
        await message.answer("❌ Произошла ошибка при извлечении эмодзи")


@emoji_router.callback_query(F.data == "emoji_use_detected", EmojiStates.waiting_for_standard_emoji, OwnerFilter())
async def use_detected_standard_emoji(callback: CallbackQuery, state: FSMContext):
    """Использовать автоматически определённый стандартный эмодзи"""
    try:
        user_id = callback.from_user.id
        extracted_emojis = _adding_emoji_data.get(user_id, [])

        if not extracted_emojis:
            await callback.answer("Данные утеряны", show_alert=True)
            await state.clear()
            return

        # Берем первый эмодзи
        first_emoji = extracted_emojis[0]

        # Используем автоопределённый standard_emoji
        _adding_emoji_data[user_id] = {
            "standard": first_emoji.standard_emoji,
            "alt_text": first_emoji.premium_char,
            "document_id": first_emoji.document_id
        }

        await state.set_state(EmojiStates.waiting_for_category)
        await callback.message.edit_text(
            f"<b>Выберите категорию для эмодзи:</b>\n\n"
            f"Маппинг: {first_emoji.standard_emoji} → {first_emoji.premium_char}",
            reply_markup=get_category_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error("Ошибка использования определённого эмодзи: {}", str(e))
        await callback.answer("Ошибка", show_alert=True)


@emoji_router.callback_query(F.data == "emoji_use_custom", EmojiStates.waiting_for_standard_emoji, OwnerFilter())
async def use_custom_standard_emoji(callback: CallbackQuery, state: FSMContext):
    """Запросить ввод собственного стандартного эмодзи"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="emoji_menu")]
    ])

    await callback.message.edit_text(
        "<b>✏️ Укажите стандартный эмодзи</b>\n\n"
        "Отправьте эмодзи, который будет заменяться на Premium версию.\n\n"
        "<i>Например: 🔥 или 🚀</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )
    await callback.answer()


@emoji_router.message(EmojiStates.waiting_for_standard_emoji, OwnerFilter())
async def process_standard_emoji(message: Message, state: FSMContext):
    """Обработать стандартный эмодзи для маппинга (ручной ввод)"""
    try:
        user_id = message.from_user.id
        extracted_emojis = _adding_emoji_data.get(user_id, [])

        if not extracted_emojis:
            await message.answer("❌ Данные утеряны. Начните заново.")
            await state.clear()
            return

        standard_emoji = message.text.strip()

        if not standard_emoji:
            await message.answer("❌ Отправьте эмодзи")
            return

        # Берем первый Premium emoji из ExtractedEmoji
        first_emoji = extracted_emojis[0]

        # Сохраняем для выбора категории
        _adding_emoji_data[user_id] = {
            "standard": standard_emoji,
            "alt_text": first_emoji.premium_char,
            "document_id": first_emoji.document_id
        }

        await state.set_state(EmojiStates.waiting_for_category)
        await message.answer(
            f"<b>Выберите категорию для эмодзи:</b>\n\n"
            f"Маппинг: {standard_emoji} → {first_emoji.premium_char}",
            reply_markup=get_category_keyboard(),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error("Ошибка обработки стандартного эмодзи: {}", str(e))
        await message.answer("❌ Произошла ошибка")


@emoji_router.callback_query(F.data.startswith("emoji_cat_"), EmojiStates.waiting_for_category, OwnerFilter())
async def process_category_selection(callback: CallbackQuery, state: FSMContext):
    """Обработать выбор категории и сохранить эмодзи"""
    try:
        category = callback.data.split("_")[2]
        user_id = callback.from_user.id
        data = _adding_emoji_data.get(user_id, {})

        if not data:
            await callback.answer("Данные утеряны", show_alert=True)
            await state.clear()
            return

        # Добавляем в словарь
        dictionary = await get_emoji_dictionary()
        success = await dictionary.add_emoji(
            standard_emoji=data["standard"],
            document_id=data["document_id"],
            alt_text=data["alt_text"],
            category=category,
            description=f"Добавлен {datetime.now().strftime('%d.%m.%Y')}"
        )

        if success:
            await callback.message.edit_text(
                f"<b>✅ Custom Emoji добавлен!</b>\n\n"
                f"Маппинг: {data['standard']} → {data['alt_text']}\n"
                f"Категория: {category}\n"
                f"Document ID: <code>{data['document_id']}</code>",
                reply_markup=get_emoji_menu_keyboard(),
                parse_mode="HTML"
            )
            logger.info("Добавлен Custom Emoji: {} -> {}", data['standard'], data['document_id'])
        else:
            await callback.message.edit_text(
                "❌ Не удалось добавить эмодзи. Возможно он уже существует.",
                reply_markup=get_emoji_menu_keyboard()
            )

        # Очищаем
        _adding_emoji_data.pop(user_id, None)
        await state.clear()
        await callback.answer()

    except Exception as e:
        logger.error("Ошибка сохранения эмодзи: {}", str(e))
        await callback.answer("Ошибка сохранения", show_alert=True)


@emoji_router.callback_query(
    F.data.startswith("emoji_delete_") & ~F.data.in_({"emoji_delete_mode"}),
    OwnerFilter()
)
async def delete_emoji(callback: CallbackQuery):
    """Удалить эмодзи по ID (исключая emoji_delete_mode)"""
    try:
        emoji_id = int(callback.data.split("_")[2])
        crud = get_emoji_crud()

        success = await crud.delete(emoji_id)

        if success:
            await reload_emoji_dictionary()
            await callback.message.edit_text(
                "✅ Эмодзи удален!",
                reply_markup=get_emoji_menu_keyboard()
            )
            logger.info("Удален Custom Emoji ID: {}", emoji_id)
        else:
            await callback.answer("Не удалось удалить", show_alert=True)

    except Exception as e:
        logger.error("Ошибка удаления эмодзи: {}", str(e))
        await callback.answer("Ошибка", show_alert=True)


@emoji_router.callback_query(F.data == "emoji_refresh", OwnerFilter())
async def refresh_emoji_cache(callback: CallbackQuery):
    """Обновить кеш эмодзи"""
    try:
        await reload_emoji_dictionary()
        dictionary = await get_emoji_dictionary()

        await callback.answer(f"Кеш обновлен! Загружено: {dictionary.count}", show_alert=True)
        logger.info("Кеш эмодзи обновлен")

    except Exception as e:
        logger.error("Ошибка обновления кеша: {}", str(e))
        await callback.answer("Ошибка обновления", show_alert=True)


@emoji_router.callback_query(F.data == "emoji_delete_mode", OwnerFilter())
async def show_delete_mode(callback: CallbackQuery):
    """Показать режим удаления эмодзи"""
    try:
        crud = get_emoji_crud()
        emojis = await crud.get_all(active_only=True)

        if not emojis:
            await callback.message.edit_text(
                "🗑 <b>Удаление связей</b>\n\n"
                "<i>Словарь пуст. Нечего удалять.</i>",
                reply_markup=get_emoji_menu_keyboard(),
                parse_mode="HTML"
            )
        else:
            text = (
                f"🗑 <b>Удаление связей эмодзи</b>\n\n"
                f"Всего связей: {len(emojis)}\n\n"
                f"<i>Выберите связь для удаления:</i>"
            )
            await callback.message.edit_text(
                text,
                reply_markup=get_emoji_delete_keyboard(emojis),
                parse_mode="HTML"
            )

        await callback.answer()

    except Exception as e:
        logger.error("Ошибка режима удаления: {}", str(e))
        await callback.answer("Ошибка", show_alert=True)


@emoji_router.callback_query(F.data.startswith("emoji_delpage_"), OwnerFilter())
async def delete_mode_pagination(callback: CallbackQuery):
    """Пагинация режима удаления"""
    try:
        page = int(callback.data.split("_")[2])
        crud = get_emoji_crud()
        emojis = await crud.get_all(active_only=True)

        text = (
            f"🗑 <b>Удаление связей эмодзи</b>\n\n"
            f"Всего связей: {len(emojis)}\n\n"
            f"<i>Выберите связь для удаления:</i>"
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_emoji_delete_keyboard(emojis, page),
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error("Ошибка пагинации удаления: {}", str(e))
        await callback.answer("Ошибка", show_alert=True)


@emoji_router.callback_query(F.data.startswith("emoji_confirm_delete_"), OwnerFilter())
async def confirm_delete_emoji(callback: CallbackQuery):
    """Подтвердить удаление эмодзи"""
    try:
        emoji_id = int(callback.data.split("_")[3])
        crud = get_emoji_crud()
        emoji = await crud.get_by_id(emoji_id)

        if not emoji:
            await callback.answer("Эмодзи не найден", show_alert=True)
            return

        # Удаляем
        success = await crud.delete(emoji_id)

        if success:
            await reload_emoji_dictionary()
            await callback.answer(
                f"✅ Связь удалена: {emoji.standard_emoji} → {emoji.alt_text}",
                show_alert=True
            )
            logger.info("Удалена связь эмодзи: {} -> {}", emoji.standard_emoji, emoji.document_id)

            # Обновляем список
            emojis = await crud.get_all(active_only=True)
            if not emojis:
                await callback.message.edit_text(
                    "🗑 <b>Удаление связей</b>\n\n"
                    "<i>Все связи удалены.</i>",
                    reply_markup=get_emoji_menu_keyboard(),
                    parse_mode="HTML"
                )
            else:
                text = (
                    f"🗑 <b>Удаление связей эмодзи</b>\n\n"
                    f"Всего связей: {len(emojis)}\n\n"
                    f"<i>Выберите связь для удаления:</i>"
                )
                await callback.message.edit_text(
                    text,
                    reply_markup=get_emoji_delete_keyboard(emojis),
                    parse_mode="HTML"
                )
        else:
            await callback.answer("Не удалось удалить", show_alert=True)

    except Exception as e:
        logger.error("Ошибка удаления связи: {}", str(e))
        await callback.answer("Ошибка", show_alert=True)


@emoji_router.callback_query(F.data == "emoji_test", OwnerFilter())
async def test_emoji_publish(callback: CallbackQuery):
    """Тестовая публикация с Premium Emoji - отправляет все эмодзи из словаря"""
    try:
        from src.userbot.publisher import get_userbot_publisher

        publisher = await get_userbot_publisher()

        if not publisher or not publisher.is_available:
            await callback.answer("UserBot Publisher недоступен", show_alert=True)
            return

        await callback.answer("⏳ Отправляю тест на @Kpeezy4L...")

        # Получаем все эмодзи из словаря
        dictionary = await get_emoji_dictionary()
        all_emojis = dictionary.get_all_with_details()

        if not all_emojis:
            await callback.message.edit_text(
                "❌ Словарь эмодзи пуст. Добавьте эмодзи сначала.",
                reply_markup=get_emoji_menu_keyboard()
            )
            return

        # Формируем тестовое сообщение со ВСЕМИ эмодзи
        emoji_lines = []
        for standard, (doc_id, alt_text) in all_emojis.items():
            # Показываем премиум → стандартный (в моноширинном шрифте чтоб не заменился)
            emoji_lines.append(f"{alt_text} → `{standard}`")

        test_text = (
            "🧪 **ТЕСТ PREMIUM EMOJI**\n\n"
            + "\n".join(emoji_lines) +
            f"\n\n📊 Всего эмодзи: {len(all_emojis)}"
        )

        # Отправляем на тестовый канал @Kpeezy4L
        message_id = await publisher.send_test_message(
            channel_id="@Kpeezy4L",
            test_text=test_text
        )

        if message_id:
            await callback.message.edit_text(
                f"✅ <b>Тест отправлен!</b>\n\n"
                f"Канал: @Kpeezy4L\n"
                f"Message ID: <code>{message_id}</code>\n"
                f"Эмодзи в тесте: {len(all_emojis)}\n\n"
                f"<i>Проверьте канал - эмодзи должны быть Premium</i>",
                reply_markup=get_emoji_menu_keyboard(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                "❌ Не удалось отправить тест",
                reply_markup=get_emoji_menu_keyboard()
            )

    except Exception as e:
        logger.error("Ошибка тестовой публикации: {}", str(e))
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=get_emoji_menu_keyboard()
        )
