"""
Обработчики для управления еженедельной аналитикой
Настройка дня/времени публикации, включение/выключение, тестовые посты
"""

from datetime import datetime
from typing import Optional

from loguru import logger

from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.bot.filters.owner import OwnerFilter
from src.utils.config import get_config

# Настройка логгера модуля
logger = logger.bind(module="bot_weekly_analytics")

# Создаем роутер
router = Router()


class WeeklyAnalyticsStates(StatesGroup):
    """Состояния FSM для настройки еженедельной аналитики"""
    waiting_for_photo = State()
    waiting_for_time = State()


# Дни недели
WEEKDAYS_RU = [
    "Понедельник", "Вторник", "Среда", "Четверг",
    "Пятница", "Суббота", "Воскресенье"
]


def get_weekly_menu_keyboard(enabled: bool, day: int, time_str: str) -> InlineKeyboardMarkup:
    """Создать клавиатуру меню еженедельной аналитики"""
    status_icon = "🟢" if enabled else "🔴"
    toggle_text = "Выключить" if enabled else "Включить"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{status_icon} {toggle_text} еженедельную аналитику",
            callback_data="weekly_toggle"
        )],
        [InlineKeyboardButton(
            text=f"📅 День: {WEEKDAYS_RU[day]}",
            callback_data="weekly_set_day"
        )],
        [InlineKeyboardButton(
            text=f"⏰ Время: {time_str}",
            callback_data="weekly_set_time"
        )],
        [InlineKeyboardButton(
            text="🖼 Установить фото",
            callback_data="weekly_set_photo"
        )],
        [InlineKeyboardButton(
            text="📌 Закрепление",
            callback_data="weekly_pin_toggle"
        )],
        [InlineKeyboardButton(
            text="🧪 Тестовый пост",
            callback_data="weekly_test"
        )],
        [InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="main_menu"
        )]
    ])
    return keyboard


@router.message(Command("weekly"), OwnerFilter())
async def weekly_analytics_menu(message: Message):
    """Меню управления еженедельной аналитикой"""
    try:
        logger.info("Пользователь {} открыл меню еженедельной аналитики", message.from_user.id)

        from src.database.crud.setting import get_bool_setting, get_setting_crud
        setting_crud = get_setting_crud()

        # Получаем текущие настройки
        enabled = await get_bool_setting("weekly_analytics.enabled", False)
        day_setting = await setting_crud.get_setting("weekly_analytics.day")
        day = int(day_setting) if day_setting else 6  # По умолчанию воскресенье
        time_setting = await setting_crud.get_setting("weekly_analytics.time")
        time_str = time_setting.strip('"') if time_setting else "18:00"

        # Проверяем доступность SyntraAI
        from src.scheduler.syntra_client import get_syntra_client
        syntra_client = get_syntra_client()
        syntra_available = await syntra_client.check_health()

        status_text = "🟢 Включено" if enabled else "🔴 Выключено"
        syntra_status = "🟢 Доступен" if syntra_available else "🔴 Недоступен"

        text = f"""📊 **Еженедельная аналитика рынка**

**Статус:** {status_text}
**SyntraAI API:** {syntra_status}

**📅 День публикации:** {WEEKDAYS_RU[day]}
**⏰ Время:** {time_str} (UTC+3)

**Данные:**
• Фаза рынка (цикл)
• BTC/ETH цены и изменения
• Доминация альткоинов (OTHERS.D)
• Fear & Greed Index
• AI-анализ для инвесторов

Выберите действие:"""

        keyboard = get_weekly_menu_keyboard(enabled, day, time_str)

        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        logger.exception("Ошибка отображения меню еженедельной аналитики: {}", str(e))
        await message.answer("❌ Ошибка загрузки меню")


@router.callback_query(lambda c: c.data == "weekly_analytics_menu")
async def weekly_analytics_menu_callback(callback: CallbackQuery):
    """Callback для открытия меню еженедельной аналитики"""
    try:
        await callback.answer()

        from src.database.crud.setting import get_bool_setting, get_setting_crud
        setting_crud = get_setting_crud()

        enabled = await get_bool_setting("weekly_analytics.enabled", False)
        day_setting = await setting_crud.get_setting("weekly_analytics.day")
        day = int(day_setting) if day_setting else 6
        time_setting = await setting_crud.get_setting("weekly_analytics.time")
        time_str = time_setting.strip('"') if time_setting else "18:00"

        from src.scheduler.syntra_client import get_syntra_client
        syntra_client = get_syntra_client()
        syntra_available = await syntra_client.check_health()

        status_text = "🟢 Включено" if enabled else "🔴 Выключено"
        syntra_status = "🟢 Доступен" if syntra_available else "🔴 Недоступен"

        text = f"""📊 **Еженедельная аналитика рынка**

**Статус:** {status_text}
**SyntraAI API:** {syntra_status}

**📅 День публикации:** {WEEKDAYS_RU[day]}
**⏰ Время:** {time_str} (UTC+3)

Выберите действие:"""

        keyboard = get_weekly_menu_keyboard(enabled, day, time_str)

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        logger.exception("Ошибка меню: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data == "weekly_toggle")
async def toggle_weekly_analytics(callback: CallbackQuery):
    """Переключить включение/выключение еженедельной аналитики"""
    try:
        await callback.answer("⏳ Обновляю настройки...")

        from src.database.crud.setting import get_bool_setting, get_setting_crud
        setting_crud = get_setting_crud()

        current_enabled = await get_bool_setting("weekly_analytics.enabled", False)
        new_enabled = not current_enabled

        await setting_crud.set_setting(
            key="weekly_analytics.enabled",
            value="true" if new_enabled else "false"
        )

        # Перезапускаем планировщик
        from src.scheduler.main import get_scheduler
        scheduler = get_scheduler()
        if scheduler and scheduler.is_running:
            await scheduler._add_weekly_analytics_job()

        status = "включена" if new_enabled else "выключена"
        icon = "🟢" if new_enabled else "🔴"

        # Обновляем меню
        day_setting = await setting_crud.get_setting("weekly_analytics.day")
        day = int(day_setting) if day_setting else 6
        time_setting = await setting_crud.get_setting("weekly_analytics.time")
        time_str = time_setting.strip('"') if time_setting else "18:00"

        text = f"""{icon} **Еженедельная аналитика {status}!**

**📅 День публикации:** {WEEKDAYS_RU[day]}
**⏰ Время:** {time_str} (UTC+3)

Выберите действие:"""

        keyboard = get_weekly_menu_keyboard(new_enabled, day, time_str)

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        logger.info("Еженедельная аналитика {} пользователем {}", status, callback.from_user.id)

    except Exception as e:
        logger.exception("Ошибка переключения: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data == "weekly_set_day")
async def set_day_menu(callback: CallbackQuery):
    """Меню выбора дня недели"""
    try:
        await callback.answer()

        buttons = []
        for i, day_name in enumerate(WEEKDAYS_RU):
            buttons.append([InlineKeyboardButton(
                text=day_name,
                callback_data=f"weekly_day_{i}"
            )])

        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="weekly_analytics_menu")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            "📅 **Выберите день публикации:**\n\n"
            "Еженедельный обзор рынка будет публиковаться в выбранный день.",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.exception("Ошибка: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("weekly_day_"))
async def set_day(callback: CallbackQuery):
    """Установить день недели"""
    try:
        day = int(callback.data.replace("weekly_day_", ""))

        from src.database.crud.setting import get_setting_crud
        setting_crud = get_setting_crud()
        await setting_crud.set_setting("weekly_analytics.day", str(day))

        # Перезапускаем задачу
        from src.scheduler.main import get_scheduler
        scheduler = get_scheduler()
        if scheduler and scheduler.is_running:
            await scheduler._add_weekly_analytics_job()

        await callback.answer(f"✅ День установлен: {WEEKDAYS_RU[day]}")

        # Возвращаемся в меню
        from src.database.crud.setting import get_bool_setting
        enabled = await get_bool_setting("weekly_analytics.enabled", False)
        time_setting = await setting_crud.get_setting("weekly_analytics.time")
        time_str = time_setting.strip('"') if time_setting else "18:00"

        text = f"""✅ **День публикации изменен!**

**📅 Новый день:** {WEEKDAYS_RU[day]}
**⏰ Время:** {time_str} (UTC+3)

Выберите действие:"""

        keyboard = get_weekly_menu_keyboard(enabled, day, time_str)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

        logger.info("День еженедельной публикации изменен на {} пользователем {}",
                    WEEKDAYS_RU[day], callback.from_user.id)

    except Exception as e:
        logger.exception("Ошибка: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data == "weekly_set_time")
async def set_time_menu(callback: CallbackQuery):
    """Меню выбора времени"""
    try:
        await callback.answer()

        times = ["09:00", "12:00", "15:00", "18:00", "21:00"]
        buttons = []

        for t in times:
            buttons.append([InlineKeyboardButton(text=f"⏰ {t}", callback_data=f"weekly_time_{t}")])

        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="weekly_analytics_menu")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            "⏰ **Выберите время публикации:**\n\n"
            "Время указывается в часовом поясе UTC+3 (Москва)",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.exception("Ошибка: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("weekly_time_"))
async def set_time(callback: CallbackQuery):
    """Установить время публикации"""
    try:
        time_str = callback.data.replace("weekly_time_", "")

        from src.database.crud.setting import get_setting_crud, get_bool_setting
        setting_crud = get_setting_crud()
        await setting_crud.set_setting("weekly_analytics.time", f'"{time_str}"')

        # Перезапускаем задачу
        from src.scheduler.main import get_scheduler
        scheduler = get_scheduler()
        if scheduler and scheduler.is_running:
            await scheduler._add_weekly_analytics_job()

        await callback.answer(f"✅ Время установлено: {time_str}")

        # Возвращаемся в меню
        enabled = await get_bool_setting("weekly_analytics.enabled", False)
        day_setting = await setting_crud.get_setting("weekly_analytics.day")
        day = int(day_setting) if day_setting else 6

        text = f"""✅ **Время публикации изменено!**

**📅 День:** {WEEKDAYS_RU[day]}
**⏰ Новое время:** {time_str} (UTC+3)

Выберите действие:"""

        keyboard = get_weekly_menu_keyboard(enabled, day, time_str)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

        logger.info("Время еженедельной публикации изменено на {} пользователем {}",
                    time_str, callback.from_user.id)

    except Exception as e:
        logger.exception("Ошибка: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data == "weekly_set_photo")
async def request_photo(callback: CallbackQuery, state: FSMContext):
    """Запросить фото для поста"""
    try:
        await callback.answer()

        await state.set_state(WeeklyAnalyticsStates.waiting_for_photo)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Удалить фото", callback_data="weekly_remove_photo")],
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="weekly_analytics_menu")]
        ])

        await callback.message.edit_text(
            "🖼 **Установка фото для еженедельного поста**\n\n"
            "Отправьте фото, которое будет прикрепляться к посту.\n\n"
            "💡 Рекомендуемый размер: 1280x720 или 1920x1080",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.exception("Ошибка: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.message(WeeklyAnalyticsStates.waiting_for_photo)
async def process_photo(message: Message, state: FSMContext):
    """Обработать полученное фото"""
    try:
        if not message.photo:
            await message.answer(
                "❌ Пожалуйста, отправьте фото.\n\n"
                "Используйте /weekly для возврата в меню."
            )
            return

        # Получаем file_id самого большого фото
        photo = message.photo[-1]
        file_id = photo.file_id

        # Сохраняем в настройки
        from src.database.crud.setting import get_setting_crud
        setting_crud = get_setting_crud()
        await setting_crud.set_setting("weekly_analytics.photo_file_id", file_id)

        await state.clear()

        await message.answer(
            "✅ **Фото успешно установлено!**\n\n"
            "Теперь еженедельные посты будут публиковаться с этим фото.\n\n"
            "Используйте /weekly для возврата в меню.",
            parse_mode="Markdown"
        )

        logger.info("Фото для еженедельного поста установлено пользователем {}", message.from_user.id)

    except Exception as e:
        logger.exception("Ошибка сохранения фото: {}", str(e))
        await message.answer("❌ Ошибка сохранения фото")


@router.callback_query(lambda c: c.data == "weekly_remove_photo")
async def remove_photo(callback: CallbackQuery, state: FSMContext):
    """Удалить фото"""
    try:
        await state.clear()

        from src.database.crud.setting import get_setting_crud
        setting_crud = get_setting_crud()
        await setting_crud.delete_setting("weekly_analytics.photo_file_id")

        await callback.answer("✅ Фото удалено")

        # Возвращаемся в меню
        from src.database.crud.setting import get_bool_setting
        enabled = await get_bool_setting("weekly_analytics.enabled", False)
        day_setting = await setting_crud.get_setting("weekly_analytics.day")
        day = int(day_setting) if day_setting else 6
        time_setting = await setting_crud.get_setting("weekly_analytics.time")
        time_str = time_setting.strip('"') if time_setting else "18:00"

        text = "✅ **Фото удалено!**\n\nВыберите действие:"
        keyboard = get_weekly_menu_keyboard(enabled, day, time_str)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        logger.exception("Ошибка: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data == "weekly_pin_toggle")
async def toggle_pin(callback: CallbackQuery):
    """Переключить закрепление постов"""
    try:
        from src.database.crud.setting import get_setting_crud, get_bool_setting
        setting_crud = get_setting_crud()

        current_pin = await get_bool_setting("weekly_analytics.pin_enabled", False)
        new_pin = not current_pin

        await setting_crud.set_setting("weekly_analytics.pin_enabled", str(new_pin).lower())

        pin_status = "включено" if new_pin else "выключено"
        await callback.answer(f"📌 Закрепление {pin_status}!")

        # Обновляем меню
        enabled = await get_bool_setting("weekly_analytics.enabled", False)
        day_setting = await setting_crud.get_setting("weekly_analytics.day")
        day = int(day_setting) if day_setting else 6
        time_setting = await setting_crud.get_setting("weekly_analytics.time")
        time_str = time_setting.strip('"') if time_setting else "18:00"

        icon = "📌" if new_pin else "📄"
        text = f"""{icon} **Закрепление постов {pin_status}!**

Выберите действие:"""

        keyboard = get_weekly_menu_keyboard(enabled, day, time_str)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

        logger.info("Закрепление еженедельных постов {} пользователем {}",
                    pin_status, callback.from_user.id)

    except Exception as e:
        logger.exception("Ошибка: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data == "weekly_test")
async def create_test_post(callback: CallbackQuery):
    """Создать тестовый еженедельный пост"""
    try:
        await callback.answer("⏳ Создаю тестовый пост...")

        # Проверяем доступность SyntraAI
        from src.scheduler.syntra_client import get_syntra_client
        syntra_client = get_syntra_client()

        if not await syntra_client.check_health():
            await callback.message.edit_text(
                "❌ **SyntraAI API недоступен!**\n\n"
                "Проверьте:\n"
                "1. Запущен ли SyntraAI сервер\n"
                "2. Правильный ли адрес API в .env\n\n"
                "Используйте /weekly для возврата в меню.",
                parse_mode="Markdown"
            )
            return

        # Создаем тестовый пост (отправляется владельцу, не в канал)
        from src.scheduler.tasks.weekly_posts import create_test_weekly_post
        content = await create_test_weekly_post()

        if content:
            await callback.message.edit_text(
                f"✅ **Тестовый пост отправлен вам!**\n\n"
                f"📏 Длина: {len(content)} символов\n\n"
                f"Проверьте сообщение выше ☝️\n"
                f"Это превью, пост не опубликован в канал.",
                parse_mode="Markdown"
            )
            logger.info("Тестовый еженедельный пост отправлен пользователю {}", callback.from_user.id)
        else:
            await callback.message.edit_text(
                "❌ **Ошибка создания поста!**\n\n"
                "Проверьте логи для деталей.\n\n"
                "Используйте /weekly для возврата в меню.",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.exception("Ошибка создания тестового поста: {}", str(e))
        await callback.answer("❌ Ошибка создания поста", show_alert=True)
