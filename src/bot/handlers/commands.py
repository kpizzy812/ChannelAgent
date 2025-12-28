"""
Основные команды бота
Базовые команды управления и информации
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# aiogram 3.x импорты
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

# Локальные импорты
from src.bot.filters.owner import OwnerFilter
from src.bot.keyboards.inline import get_main_menu_keyboard, get_status_keyboard, get_settings_menu_keyboard
from src.database.crud.channel import get_channel_crud
from src.database.crud.post import get_post_crud
from src.database.models.post import PostStatus
from src.database.crud.user_post import get_user_post_crud
from src.userbot.monitor import get_channel_monitor
from src.userbot.auth_manager import get_auth_manager, AuthStatus
from src.ai.processor import get_ai_processor
from src.utils.config import get_config
from src.utils.html_formatter import (
    bold, format_success_message, format_info_message, format_warning_message,
    format_error_message, format_list_items, get_parse_mode
)

# Настройка логгера модуля
logger = logger.bind(module="bot_commands")


async def safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = False) -> bool:
    """Безопасный ответ на callback query с проверкой возраста"""
    try:
        # Проверяем возраст callback (Telegram отклоняет старые callback после ~30 секунд)
        callback_age = datetime.now().timestamp() - callback.message.date.timestamp()
        if callback_age > 25:  # 25 секунд - безопасный лимит
            logger.warning("Callback query слишком старый ({}с), пропускаем answer", int(callback_age))
            return False
            
        await callback.answer(text, show_alert=show_alert)
        return True
        
    except Exception as e:
        error_msg = str(e)
        if "query is too old" in error_msg or "timeout expired" in error_msg or "query ID is invalid" in error_msg:
            logger.warning("Callback query устарел или недействителен: {}", error_msg)
            return False
        else:
            logger.error("Ошибка ответа на callback: {}", error_msg)
            return False

# Роутер для команд
commands_router = Router()


@commands_router.message(CommandStart(), OwnerFilter())
async def start_command(message: Message):
    """Команда /start - главное меню"""
    try:
        config = get_config()
        auth_manager = get_auth_manager()
        
        # Получаем краткую статистику
        channel_crud = get_channel_crud()
        post_crud = get_post_crud()
        
        active_channels = len(await channel_crud.get_active_channels())
        pending_posts = len(await post_crud.get_posts_by_status(PostStatus.PENDING))
        
        # Проверяем статус UserBot
        userbot_status = await auth_manager.get_status()
        
        if userbot_status == AuthStatus.CONNECTED:
            userbot_icon = "🟢"
            userbot_text = "Подключен"
        elif userbot_status == AuthStatus.CONNECTING:
            userbot_icon = "🟡"
            userbot_text = "Подключается..."
        else:
            userbot_icon = "🔴"
            userbot_text = "Не подключен"
        
        welcome_text = f"""🤖 {bold('Channel Agent Bot')}

👋 Добро пожаловать, владелец!

📊 {bold('Краткая статистика:')}
📺 Активных каналов: {active_channels}
⏳ Постов на модерации: {pending_posts}
{userbot_icon} UserBot: {userbot_text}

🔗 {bold('Основные функции:')}
{format_list_items([
    'Мониторинг Telegram каналов',
    'AI анализ и рестайлинг постов',
    'Автоматическая модерация', 
    'Управление примерами стиля'
])}

Выберите действие из меню ниже:"""
        
        # Используем стандартную клавиатуру главного меню
        keyboard = get_main_menu_keyboard()
        
        # Добавляем кнопку подключения UserBot если не подключен
        if userbot_status != AuthStatus.CONNECTED:
            # Создаем новую клавиатуру с дополнительной кнопкой UserBot
            main_buttons = keyboard.inline_keyboard.copy()
            # Вставляем кнопку UserBot после первых двух рядов
            userbot_button_row = [InlineKeyboardButton(text="🔐 Подключить UserBot", callback_data="connect_userbot")]
            main_buttons.insert(2, userbot_button_row)
            keyboard = InlineKeyboardMarkup(inline_keyboard=main_buttons)
        
        await message.answer(
            welcome_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.info("Пользователь {} выполнил команду /start", message.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка выполнения команды /start: {}", str(e))
        await message.answer("❌ Произошла ошибка при загрузке главного меню")


@commands_router.callback_query(F.data == "connect_userbot", OwnerFilter())
async def connect_userbot_callback(callback: CallbackQuery):
    """Callback для подключения UserBot"""
    try:
        await safe_callback_answer(callback)
        
        # Создаем клавиатуру для подтверждения
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="📱 Начать авторизацию", 
                    callback_data="start_userbot_auth"
                )],
                [InlineKeyboardButton(
                    text="ℹ️ Подробнее", 
                    callback_data="userbot_info"
                )],
                [InlineKeyboardButton(
                    text="🏠 Главное меню", 
                    callback_data="back_to_main"
                )]
            ]
        )
        
        auth_text = """🔐 <b>Подключение UserBot</b>

📱 UserBot позволяет мониторить каналы и находить релевантный контент для вашего канала

🔒 <b>Безопасность:</b>
• Используются только официальные Telegram API
• Данные авторизации хранятся локально
• Доступ только к публичным каналам

🚀 <b>Возможности:</b>
• Автоматический мониторинг каналов
• Поиск постов с фотографиями
• AI анализ релевантности
• Умная фильтрация контента

Готовы начать?"""
        
        await callback.message.edit_text(
            auth_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
    except Exception as e:
        logger.error("Ошибка callback подключения UserBot: {}", str(e))
        await callback.message.edit_text("❌ Произошла ошибка")


@commands_router.callback_query(F.data == "userbot_info", OwnerFilter())
async def userbot_info_callback(callback: CallbackQuery):
    """Информация о UserBot"""
    await safe_callback_answer(callback)
    
    info_text = """ℹ️ <b>Подробно о UserBot</b>

<b>Что такое UserBot?</b>
UserBot - это ваш личный аккаунт Telegram, который работает через официальное API для автоматизации задач.

<b>Как это работает?</b>
1️⃣ Вы авторизуете свой Telegram аккаунт
2️⃣ UserBot подписывается на указанные каналы
3️⃣ Отслеживает новые посты с фотографиями  
4️⃣ AI анализирует релевантность контента
5️⃣ Лучшие посты отправляются вам на модерацию

<b>Безопасно ли это?</b>
✅ Используется только официальное Telegram API
✅ Никаких сторонних сервисов
✅ Данные хранятся только локально
✅ Полный контроль над процессом

<b>Нужны права администратора?</b>
❌ Нет! UserBot работает как обычный пользователь
❌ Не нужно делать его админом каналов
❌ Просто подписывается и читает публичные посты"""
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📱 Начать авторизацию", 
                callback_data="start_userbot_auth"
            )],
            [InlineKeyboardButton(
                text="◀️ Назад", 
                callback_data="connect_userbot"
            )]
        ]
    )
    
    await callback.message.edit_text(
        info_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@commands_router.callback_query(F.data == "back_to_main", OwnerFilter())
async def back_to_main_callback(callback: CallbackQuery):
    """Возврат в главное меню"""
    await safe_callback_answer(callback)
    
    # Эмулируем команду /start
    await start_command(callback.message)


@commands_router.message(Command("status"), OwnerFilter())
async def status_command(message: Message):
    """Команда /status - статус системы"""
    try:
        # Собираем информацию о состоянии системы
        status_info = await get_system_status()
        
        status_text = format_status_message(status_info)
        keyboard = get_status_keyboard()
        
        await message.answer(
            status_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.info("Пользователь {} запросил статус системы", message.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка выполнения команды /status: {}", str(e))
        await message.answer("❌ Произошла ошибка при получении статуса")


@commands_router.message(Command("help"), OwnerFilter())
async def help_command(message: Message):
    """Команда /help - справка по командам"""
    try:
        help_text = """❓ <b>Справка по командам Channel Agent</b>

🔧 <b>Основные команды:</b>
/start - Главное меню бота
/status - Статус всех компонентов
/channels - Управление каналами
/moderation - Модерация постов
/examples - Примеры ваших постов
/settings - Настройки системы
/stats - Подробная статистика

📺 <b>Управление каналами:</b>
• Добавление/удаление каналов для мониторинга
• Автоматическая подписка UserBot
• Проверка доступа к каналам

⚖️ <b>Модерация постов:</b>
• Просмотр постов на модерации
• Одобрение/отклонение постов
• Редактирование текста
• Отложенная публикация

📝 <b>Примеры постов:</b>
• Добавление примеров вашего стиля
• Загрузка по ссылкам Telegram
• Категоризация примеров
• Оценка качества примеров

🤖 <b>AI анализ:</b>
• Автоматический анализ релевантности
• Определение тональности
• Рестайлинг под ваш стиль
• Анализ изображений

📊 <b>Статистика:</b>
• Количество обработанных постов
• Статистика по каналам
• Эффективность AI фильтров
• Время работы системы"""
        
        await message.answer(help_text, parse_mode="HTML")
        
        logger.info("Пользователь {} запросил справку", message.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка выполнения команды /help: {}", str(e))
        await message.answer("❌ Произошла ошибка при загрузке справки")


@commands_router.message(Command("stats"), OwnerFilter())
async def stats_command(message: Message):
    """Команда /stats - подробная статистика"""
    try:
        # Собираем детальную статистику
        stats = await get_detailed_statistics()
        
        stats_text = format_statistics_message(stats)
        
        # Клавиатура с дополнительными опциями статистики
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Графики", callback_data="stats_charts"),
                InlineKeyboardButton(text="📊 По каналам", callback_data="stats_channels")
            ],
            [
                InlineKeyboardButton(text="🤖 AI статистика", callback_data="stats_ai"),
                InlineKeyboardButton(text="⏱️ По времени", callback_data="stats_time")
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_stats")
            ]
        ])
        
        await message.answer(
            stats_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.info("Пользователь {} запросил статистику", message.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка выполнения команды /stats: {}", str(e))
        await message.answer("❌ Произошла ошибка при загрузке статистики")


@commands_router.callback_query(F.data == "main_menu", OwnerFilter())
async def main_menu_callback(callback: CallbackQuery):
    """Возврат в главное меню"""
    try:
        # Безопасный ответ на callback query
        answered = await safe_callback_answer(callback)
        
        # Получаем обновленную статистику
        channel_crud = get_channel_crud()
        post_crud = get_post_crud()
        
        active_channels = len(await channel_crud.get_active_channels())
        pending_posts = len(await post_crud.get_posts_by_status(PostStatus.PENDING))
        
        welcome_text = f"""🤖 <b>Channel Agent Bot</b>

📊 <b>Краткая статистика:</b>
📺 Активных каналов: {active_channels}
⏳ Постов на модерации: {pending_posts}

🔗 <b>Основные функции:</b>
• Мониторинг Telegram каналов
• AI анализ и рестайлинг постов  
• Автоматическая модерация
• Управление примерами стиля

Выберите действие из меню ниже:"""
        
        keyboard = get_main_menu_keyboard()
        
        await callback.message.edit_text(
            welcome_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Пользователь {} вернулся в главное меню", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка возврата в главное меню: {}", str(e))
        # НЕ вызываем callback.answer() снова, если уже был вызван
        if not answered:
            await safe_callback_answer(callback, "❌ Произошла ошибка", show_alert=True)


@commands_router.callback_query(F.data == "system_status", OwnerFilter())
async def system_status_callback(callback: CallbackQuery):
    """Показать статус системы"""
    try:
        await safe_callback_answer(callback)
        
        status_info = await get_system_status()
        status_text = format_status_message(status_info)
        keyboard = get_status_keyboard()
        
        await callback.message.edit_text(
            status_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Пользователь {} запросил статус системы", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка получения статуса системы: {}", str(e))
        await safe_callback_answer(callback, "❌ Ошибка получения статуса", show_alert=True)


@commands_router.callback_query(F.data == "refresh_status", OwnerFilter())
async def refresh_status_callback(callback: CallbackQuery):
    """Обновление статуса системы"""
    try:
        await safe_callback_answer(callback, "🔄 Обновление статуса...")
        
        status_info = await get_system_status()
        status_text = format_status_message(status_info)
        keyboard = get_status_keyboard()
        
        await callback.message.edit_text(
            status_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Пользователь {} обновил статус", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка обновления статуса: {}", str(e))
        await safe_callback_answer(callback, "❌ Ошибка обновления", show_alert=True)


@commands_router.callback_query(F.data == "show_statistics", OwnerFilter())
async def show_statistics_callback(callback: CallbackQuery):
    """Показать статистику"""
    try:
        await safe_callback_answer(callback)
        
        # Собираем детальную статистику
        stats = await get_detailed_statistics()
        
        stats_text = format_statistics_message(stats)
        
        # Клавиатура с дополнительными опциями статистики
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Графики", callback_data="stats_charts"),
                InlineKeyboardButton(text="📊 По каналам", callback_data="stats_channels")
            ],
            [
                InlineKeyboardButton(text="🤖 AI статистика", callback_data="stats_ai"),
                InlineKeyboardButton(text="⏱️ По времени", callback_data="stats_time")
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_stats"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
            ]
        ])
        
        await callback.message.edit_text(
            stats_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.info("Пользователь {} запросил статистику", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка получения статистики: {}", str(e))
        await safe_callback_answer(callback, "❌ Ошибка получения статистики", show_alert=True)


@commands_router.callback_query(F.data == "settings_menu", OwnerFilter())
async def settings_menu_callback(callback: CallbackQuery):
    """Показать меню настроек"""
    try:
        await safe_callback_answer(callback)
        
        config = get_config()
        
        settings_text = f"""⚙️ {bold('Настройки Channel Agent')}

🤖 {bold('AI Настройки:')}
• Модель: {config.OPENAI_MODEL}
• Порог релевантности: {config.RELEVANCE_THRESHOLD}/10

📊 {bold('Мониторинг:')}
• Интервал проверки: {config.MONITORING_INTERVAL} сек
• Часовой пояс: UTC+3

🔧 {bold('Доступные настройки:')}
{format_list_items([
    'AI параметры и промпты',
    'Настройки каналов',
    'Расписание публикаций',
    'Параметры мониторинга'
])}"""
        
        keyboard = get_settings_menu_keyboard()
        
        await callback.message.edit_text(
            settings_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Пользователь {} открыл настройки", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка открытия настроек: {}", str(e))
        await safe_callback_answer(callback, "❌ Ошибка открытия настроек", show_alert=True)


@commands_router.callback_query(F.data == "show_help", OwnerFilter())
async def show_help_callback(callback: CallbackQuery):
    """Показать справку"""
    try:
        await safe_callback_answer(callback)
        
        help_text = f"""❓ {bold('Справка по Channel Agent')}

🤖 {bold('Channel Agent')} - ваш персональный помощник для мониторинга Telegram каналов и автоматической подготовки контента с помощью AI.

🔧 {bold('Основные возможности:')}
{format_list_items([
    '📺 Мониторинг множества каналов',
    '🤖 AI анализ релевантности постов',
    '✏️ Автоматический рестайлинг под ваш стиль',
    '⚖️ Удобная модерация через бота',
    '⏰ Отложенная публикация',
    '📊 Детальная статистика'
])}

📝 {bold('Как это работает:')}
1️⃣ Добавьте каналы для мониторинга (/channels)
2️⃣ Подключите UserBot для доступа (/connect_userbot)
3️⃣ Добавьте примеры ваших постов (/examples)
4️⃣ Настройте AI под ваш стиль
5️⃣ Модерируйте найденные посты (/moderation)

🔐 {bold('UserBot')} использует официальное Telegram API и полностью безопасен.

💡 {bold('Нужна помощь?')} Все действия интуитивно понятны - просто следуйте подсказкам в меню!"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📺 Начать с каналов", callback_data="channels_menu"),
                InlineKeyboardButton(text="📝 Примеры постов", callback_data="examples_menu")
            ],
            [
                InlineKeyboardButton(text="🔐 Подключить UserBot", callback_data="connect_userbot")
            ],
            [
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
            ]
        ])
        
        await callback.message.edit_text(
            help_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Пользователь {} запросил справку", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа справки: {}", str(e))
        await safe_callback_answer(callback, "❌ Ошибка показа справки", show_alert=True)


@commands_router.callback_query(F.data == "examples_menu", OwnerFilter())
async def examples_menu_callback(callback: CallbackQuery):
    """Переадресация в меню примеров постов"""
    try:
        await safe_callback_answer(callback)
        
        # Перенаправляем к команде /examples
        from src.bot.handlers.user_posts import examples_menu_command
        
        # Имитируем сообщение для команды /examples
        await examples_menu_command(callback.message)
        
        logger.debug("Пользователь {} перешел к примерам постов", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка перехода к примерам постов: {}", str(e))
        await safe_callback_answer(callback, "❌ Ошибка перехода к примерам", show_alert=True)


@commands_router.callback_query(F.data == "userbot_status", OwnerFilter())
async def userbot_status_callback(callback: CallbackQuery):
    """Показать статус UserBot"""
    try:
        await safe_callback_answer(callback)

        auth_manager = get_auth_manager()
        status = await auth_manager.get_status()

        if status == AuthStatus.CONNECTED:
            status_icon = "🟢"
            status_text = "Подключен и активен"
            additional_info = "📡 Мониторинг каналов работает\n🔄 Последняя активность: только что"
        elif status == AuthStatus.CONNECTING:
            status_icon = "🟡"
            status_text = "Подключается..."
            additional_info = "⏳ Процесс подключения в процессе"
        else:
            status_icon = "🔴"
            status_text = "Не подключен"
            additional_info = "❌ Мониторинг каналов остановлен\n🔧 Используйте /connect_userbot для подключения"

        # Получаем информацию о UserbotPublisher для Premium Emoji
        publisher_info = ""
        if status == AuthStatus.CONNECTED:
            try:
                from src.userbot.publisher import get_userbot_publisher
                publisher = await get_userbot_publisher()

                if publisher and publisher.is_available:
                    # Получаем информацию о UserBot
                    me = await publisher.client.get_me()
                    userbot_name = f"@{me.username}" if me.username else f"{me.first_name} {me.last_name or ''}"

                    # Проверяем найден ли целевой канал
                    if publisher._target_entity:
                        channel_title = getattr(publisher._target_entity, 'title', 'unknown')
                        channel_username = getattr(publisher._target_entity, 'username', None)
                        channel_info = f"@{channel_username}" if channel_username else channel_title
                        publisher_info = f"""

🎨 {bold('Premium Emoji Publisher:')}
👤 Аккаунт: {userbot_name}
✅ Целевой канал: {channel_info}
🚀 Готов к публикации с Premium эмодзи"""
                    else:
                        publisher_info = f"""

🎨 {bold('Premium Emoji Publisher:')}
👤 Аккаунт: {userbot_name}
❌ Целевой канал НЕ найден в диалогах!
⚠️ Публикация через Bot API (без Premium эмодзи)"""
                else:
                    publisher_info = f"""

🎨 {bold('Premium Emoji Publisher:')}
🔴 Не инициализирован"""
            except Exception as pub_error:
                logger.warning("Не удалось получить статус Publisher: {}", str(pub_error))
                publisher_info = f"""

🎨 {bold('Premium Emoji Publisher:')}
⚠️ Ошибка: {str(pub_error)[:50]}"""

        userbot_text = f"""🤖 {bold('Статус UserBot')}

{status_icon} {bold('Состояние:')} {status_text}

📋 {bold('Подробности:')}
{additional_info}{publisher_info}

💡 {bold('UserBot')} - это ваш личный аккаунт Telegram, который используется для мониторинга каналов через официальное API."""
        
        # Создаем клавиатуру в зависимости от статуса
        keyboard_buttons = [
            [
                InlineKeyboardButton(text="🔄 Обновить статус", callback_data="userbot_status")
            ]
        ]
        
        # Если UserBot подключен, добавляем кнопку перерегистрации
        if status == AuthStatus.CONNECTED:
            keyboard_buttons.append([
                InlineKeyboardButton(text="🔧 Перерегистрировать обработчики", callback_data="reregister_handlers")
            ])
        
        keyboard_buttons.extend([
            [
                InlineKeyboardButton(text="🔐 Подключить UserBot", callback_data="connect_userbot") if status != AuthStatus.CONNECTED else
                InlineKeyboardButton(text="🔌 Отключить UserBot", callback_data="disconnect_userbot")
            ],
            [
                InlineKeyboardButton(text="🗑️ Сбросить сессию (сменить аккаунт)", callback_data="confirm_reset_userbot")
            ],
            [
                InlineKeyboardButton(text="⬅️ К статусу системы", callback_data="system_status")
            ]
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            userbot_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Показан статус UserBot пользователю {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа статуса UserBot: {}", str(e))
        await safe_callback_answer(callback, "❌ Ошибка получения статуса UserBot", show_alert=True)


@commands_router.callback_query(F.data == "reregister_handlers", OwnerFilter())
async def reregister_handlers_callback(callback: CallbackQuery):
    """🔧 Вступление в каналы + перерегистрация обработчиков Telethon"""
    try:
        await safe_callback_answer(callback, "🔄 Вступление в каналы...", show_alert=True)

        # Показываем процесс - Шаг 1
        process_text = """🔧 <b>Вступление в каналы и перерегистрация</b>

⏳ <b>Шаг 1/2:</b> Вступаем во все каналы из БД...

⚠️ Это может занять до 60 секунд"""

        await callback.message.edit_text(
            process_text,
            parse_mode=get_parse_mode()
        )

        from src.userbot.monitor import get_channel_monitor
        monitor = get_channel_monitor()
        logger.info("🔧 Пользователь {} запросил вступление в каналы и перерегистрацию", callback.from_user.id)

        # Шаг 1: Вступаем во все каналы
        join_results = await monitor.join_all_channels()

        # Обновляем статус - Шаг 2
        step2_text = f"""🔧 <b>Вступление в каналы и перерегистрация</b>

✅ <b>Шаг 1/2:</b> Вступление завершено
   • Вступили: {join_results['joined']}
   • Уже были: {join_results['already_member']}
   • Ошибки: {join_results['failed']}

⏳ <b>Шаг 2/2:</b> Перерегистрация обработчиков..."""

        await callback.message.edit_text(
            step2_text,
            parse_mode=get_parse_mode()
        )

        # Шаг 2: Перерегистрация обработчиков
        reregister_success = await monitor.force_reregister_handlers()

        if reregister_success:
            result_text = f"""✅ <b>Операция завершена!</b>

📊 <b>Вступление в каналы:</b>
   • Вступили: {join_results['joined']}
   • Уже были: {join_results['already_member']}
   • Ошибки: {join_results['failed']} / {join_results['total']}

🔄 <b>Перерегистрация:</b> ✅ успешно

📡 Мониторинг должен работать"""
            result_icon = "✅"
        else:
            result_text = f"""⚠️ <b>Завершено с ошибками</b>

📊 <b>Вступление в каналы:</b>
   • Вступили: {join_results['joined']}
   • Уже были: {join_results['already_member']}
   • Ошибки: {join_results['failed']}

❌ <b>Перерегистрация:</b> ошибка

🔧 Попробуйте переподключить UserBot"""
            result_icon = "⚠️"
        
        # Создаем клавиатуру результата
        result_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Проверить статус", callback_data="userbot_status")
            ],
            [
                InlineKeyboardButton(text="📊 Статус системы", callback_data="system_status")
            ]
        ])
        
        await callback.message.edit_text(
            result_text,
            reply_markup=result_keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.info("{} Перерегистрация обработчиков завершена для пользователя {}", 
                   result_icon, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка перерегистрации обработчиков: {}", str(e))
        
        error_text = """❌ <b>Критическая ошибка</b>

🚨 Не удалось выполнить перерегистрацию
📋 Ошибка записана в логи

🔧 Попробуйте перезапустить UserBot"""
        
        error_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад к статусу", callback_data="userbot_status")
            ]
        ])
        
        await callback.message.edit_text(
            error_text,
            reply_markup=error_keyboard,
            parse_mode=get_parse_mode()
        )


@commands_router.callback_query(F.data == "ai_status", OwnerFilter())
async def ai_status_callback(callback: CallbackQuery):
    """Показать статус AI модуля"""
    try:
        await safe_callback_answer(callback)
        
        try:
            ai_processor = get_ai_processor()
            config = get_config()
            
            ai_text = f"""🧠 {bold('Статус AI Модуля')}

🟢 {bold('Состояние:')} Доступен

📋 {bold('Настройки:')}
• Модель: {config.OPENAI_MODEL}
• Порог релевантности: {config.RELEVANCE_THRESHOLD}/10

🎯 {bold('Возможности:')}
{format_list_items([
    'Анализ релевантности постов',
    'Определение тональности',
    'Рестайлинг под ваш стиль',
    'Анализ изображений'
])}

💰 {bold('Примерная стоимость:')}
• Анализ поста: ~$0.001-0.003
• Рестайлинг: ~$0.002-0.005"""
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Проверить AI", callback_data="test_ai")
                ],
                [
                    InlineKeyboardButton(text="⚙️ Настройки AI", callback_data="ai_settings")
                ],
                [
                    InlineKeyboardButton(text="⬅️ К статусу системы", callback_data="system_status")
                ]
            ])
            
        except Exception:
            ai_text = f"""🧠 {bold('Статус AI Модуля')}

🔴 {bold('Состояние:')} Недоступен

❌ {bold('Проблема:')} Не удалось подключиться к OpenAI API

🔧 {bold('Возможные причины:')}
{format_list_items([
    'Неверный API ключ',
    'Отсутствует интернет-соединение', 
    'Проблемы с OpenAI API',
    'Исчерпан лимит запросов'
])}"""
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Проверить снова", callback_data="ai_status")
                ],
                [
                    InlineKeyboardButton(text="⚙️ Настройки AI", callback_data="ai_settings")
                ],
                [
                    InlineKeyboardButton(text="⬅️ К статусу системы", callback_data="system_status")
                ]
            ])
        
        await callback.message.edit_text(
            ai_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Показан статус AI модуля пользователю {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа статуса AI: {}", str(e))
        await safe_callback_answer(callback, "❌ Ошибка получения статуса AI", show_alert=True)


@commands_router.callback_query(F.data == "database_status", OwnerFilter())
async def database_status_callback(callback: CallbackQuery):
    """Показать статус базы данных"""
    try:
        await safe_callback_answer(callback)
        
        try:
            # Проверяем доступность БД
            channel_crud = get_channel_crud()
            post_crud = get_post_crud()
            user_post_crud = get_user_post_crud()
            
            channels = await channel_crud.get_all_channels()
            posts = await post_crud.get_all_posts()
            user_posts = await user_post_crud.get_active_user_posts()
            
            db_text = f"""💾 {bold('Статус базы данных')}

🟢 {bold('Состояние:')} Подключена

📊 {bold('Статистика данных:')}
• Каналов: {len(channels)}
• Постов: {len(posts)}
• Примеров: {len(user_posts)}

📁 {bold('Таблицы:')}
{format_list_items([
    'channels - отслеживаемые каналы',
    'posts - история обработанных постов',
    'user_posts - примеры стиля пользователя',
    'settings - настройки системы'
])}

💾 {bold('База данных:')} SQLite (локальная)
📍 {bold('Расположение:')} data/channel_agent.db"""
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🧹 Очистить старые данные", callback_data="cleanup_db")
                ],
                [
                    InlineKeyboardButton(text="📊 Подробная статистика", callback_data="db_stats")
                ],
                [
                    InlineKeyboardButton(text="⬅️ К статусу системы", callback_data="system_status")
                ]
            ])
            
        except Exception as db_error:
            db_text = f"""💾 {bold('Статус базы данных')}

🔴 {bold('Состояние:')} Недоступна

❌ {bold('Ошибка:')} {str(db_error)[:100]}...

🔧 {bold('Возможные причины:')}
{format_list_items([
    'Файл базы данных заблокирован',
    'Недостаточно прав доступа',
    'Повреждение базы данных',
    'Недостаточно места на диске'
])}"""
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Проверить снова", callback_data="database_status")
                ],
                [
                    InlineKeyboardButton(text="🛠️ Восстановить БД", callback_data="repair_db")
                ],
                [
                    InlineKeyboardButton(text="⬅️ К статусу системы", callback_data="system_status")
                ]
            ])
        
        await callback.message.edit_text(
            db_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Показан статус БД пользователю {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа статуса БД: {}", str(e))
        await safe_callback_answer(callback, "❌ Ошибка получения статуса БД", show_alert=True)


@commands_router.callback_query(F.data == "monitoring_status", OwnerFilter())
async def monitoring_status_callback(callback: CallbackQuery):
    """Показать статус мониторинга"""
    try:
        await safe_callback_answer(callback)
        
        monitor = get_channel_monitor()
        monitor_status = monitor.get_status()
        
        is_running = monitor_status.get("is_monitoring", False)
        uptime = monitor_status.get("uptime_seconds", 0)
        
        if is_running:
            status_icon = "🟢"
            status_text = "Активен"
            
            hours = uptime // 3600
            minutes = (uptime % 3600) // 60
            uptime_text = f"⏱️ Время работы: {hours}ч {minutes}м"
        else:
            status_icon = "🔴"  
            status_text = "Остановлен"
            uptime_text = "⏹️ Мониторинг не запущен"
        
        # Получаем количество активных каналов
        channel_crud = get_channel_crud()
        active_channels = await channel_crud.get_active_channels()
        
        monitoring_text = f"""📊 {bold('Статус мониторинга')}

{status_icon} {bold('Состояние:')} {status_text}

📋 {bold('Детали:')}
• Активных каналов: {len(active_channels)}
• {uptime_text}
• Интервал проверки: {get_config().MONITORING_INTERVAL} сек

🔍 {bold('Процесс мониторинга:')}
{format_list_items([
    'Проверка новых постов в каналах',
    'Фильтрация постов с изображениями',
    'AI анализ релевантности',
    'Отправка на модерацию'
])}"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Запустить мониторинг" if not is_running else "⏸️ Остановить мониторинг",
                    callback_data="toggle_monitoring"
                )
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить статус", callback_data="monitoring_status")
            ],
            [
                InlineKeyboardButton(text="⬅️ К статусу системы", callback_data="system_status")
            ]
        ])
        
        await callback.message.edit_text(
            monitoring_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Показан статус мониторинга пользователю {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа статуса мониторинга: {}", str(e))
        await safe_callback_answer(callback, "❌ Ошибка получения статуса мониторинга", show_alert=True)


@commands_router.callback_query(F.data == "ai_settings", OwnerFilter())
async def ai_settings_callback(callback: CallbackQuery):
    """Настройки AI"""
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "🤖 <b>Настройки AI</b>\n\n"
        "🚧 Этот раздел находится в разработке.\n"
        "Скоро здесь можно будет настроить:\n"
        "• Модель OpenAI\n"
        "• Порог релевантности\n"
        "• Промпты для анализа\n"
        "• Параметры рестайлинга",
        parse_mode="HTML"
    )


@commands_router.callback_query(F.data == "channel_settings", OwnerFilter())
async def channel_settings_callback(callback: CallbackQuery):
    """Настройки каналов"""
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "📺 <b>Настройки каналов</b>\n\n"
        "🚧 Этот раздел находится в разработке.\n"
        "Скоро здесь можно будет настроить:\n"
        "• Фильтры для каналов\n"
        "• Исключения и правила\n"
        "• Приоритеты каналов\n"
        "• Категории контента",
        parse_mode="HTML"
    )


@commands_router.callback_query(F.data == "schedule_settings", OwnerFilter())
async def schedule_settings_callback(callback: CallbackQuery):
    """Настройки расписания"""
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "⏰ <b>Настройки расписания</b>\n\n"
        "🚧 Этот раздел находится в разработке.\n"
        "Скоро здесь можно будет настроить:\n"
        "• Время публикации постов\n"
        "• Интервалы между постами\n"
        "• Расписание по дням недели\n"
        "• Отложенная публикация",
        parse_mode="HTML"
    )


@commands_router.callback_query(F.data == "monitor_settings", OwnerFilter())
async def monitor_settings_callback(callback: CallbackQuery):
    """Настройки мониторинга"""
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "📊 <b>Настройки мониторинга</b>\n\n"
        "🚧 Этот раздел находится в разработке.\n"
        "Скоро здесь можно будет настроить:\n"
        "• Интервал проверки каналов\n"
        "• Фильтры контента\n"
        "• Уведомления о новых постах\n"
        "• Лимиты обработки",
        parse_mode="HTML"
    )


@commands_router.callback_query(F.data == "coingecko_settings", OwnerFilter())
async def coingecko_settings_callback(callback: CallbackQuery):
    """Настройки CoinGecko"""
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "💰 <b>Настройки CoinGecko</b>\n\n"
        "🚧 Этот раздел находится в разработке.\n"
        "Скоро здесь можно будет настроить:\n"
        "• API ключ CoinGecko\n"
        "• Отслеживаемые криптовалюты\n"
        "• Интервалы обновления курсов\n"
        "• Интеграция с постами",
        parse_mode="HTML"
    )


@commands_router.callback_query(F.data == "cleanup_db", OwnerFilter())
async def cleanup_db_callback(callback: CallbackQuery):
    """Очистить старые данные из базы данных"""
    try:
        await safe_callback_answer(callback)
        
        # Клавиатура подтверждения
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚠️ Да, очистить старые данные",
                    callback_data="confirm_cleanup_db"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="database_status"
                )
            ]
        ])
        
        warning_text = f"""🧹 {bold('Очистка старых данных')}

Будут удалены старые записи:
• Посты старше 30 дней
• Неактивные записи каналов
• Устаревшие логи и кеш

⚠️ {bold('ВНИМАНИЕ:')}
• Активные примеры постов НЕ будут удалены
• Настройки системы сохранятся
• Действие нельзя отменить

Продолжить очистку?"""
        
        await callback.message.edit_text(
            warning_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Запрос на очистку БД пользователем {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка запроса очистки БД: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@commands_router.callback_query(F.data == "confirm_cleanup_db", OwnerFilter())
async def confirm_cleanup_db_callback(callback: CallbackQuery):
    """Подтверждённая очистка базы данных"""
    try:
        await safe_callback_answer(callback, "🧹 Очищаю старые данные...")
        
        # Показываем процесс очистки
        await callback.message.edit_text(
            "🧹 Очищаю старые данные из базы...\n"
            "Это может занять некоторое время."
        )
        
        # Выполняем очистку
        from src.database.connection import get_db_connection
        from datetime import datetime, timedelta
        
        cleanup_date = datetime.now() - timedelta(days=30)
        cleanup_stats = {
            "old_posts": 0,
            "inactive_channels": 0,
            "old_logs": 0
        }
        
        async with get_db_connection() as conn:
            # Очистка старых постов (кроме POSTED)
            cursor = await conn.execute(
                """DELETE FROM posts 
                   WHERE created_at < ? AND status NOT IN ('posted', 'approved')""",
                (cleanup_date.isoformat(),)
            )
            cleanup_stats["old_posts"] = cursor.rowcount
            
            # Очистка неактивных каналов без постов
            cursor = await conn.execute(
                """DELETE FROM channels 
                   WHERE is_active = 0 
                   AND posts_processed = 0 
                   AND created_at < ?""",
                (cleanup_date.isoformat(),)
            )
            cleanup_stats["inactive_channels"] = cursor.rowcount
            
            await conn.commit()
        
        # Очистка файлов логов (старше 7 дней)
        import os
        import glob
        from pathlib import Path
        
        logs_dir = Path("logs")
        if logs_dir.exists():
            old_log_files = []
            cutoff_time = (datetime.now() - timedelta(days=7)).timestamp()
            
            for log_file in glob.glob(str(logs_dir / "*.log*")):
                if os.path.getmtime(log_file) < cutoff_time:
                    try:
                        os.remove(log_file)
                        old_log_files.append(log_file)
                    except:
                        pass
            
            cleanup_stats["old_logs"] = len(old_log_files)
        
        # Результат очистки
        result_text = f"""✅ {bold('Очистка завершена!')}

📊 {bold('Удалено:')}
• Старых постов: {cleanup_stats['old_posts']}
• Неактивных каналов: {cleanup_stats['inactive_channels']}  
• Файлов логов: {cleanup_stats['old_logs']}

💾 {bold('База данных оптимизирована!')}
Освобождено место на диске и улучшена производительность."""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Проверить статус БД", callback_data="database_status")
            ],
            [
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
            ]
        ])
        
        await callback.message.edit_text(
            result_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.info("Очистка БД выполнена пользователем {}: посты={}, каналы={}, логи={}", 
                   callback.from_user.id, cleanup_stats['old_posts'], 
                   cleanup_stats['inactive_channels'], cleanup_stats['old_logs'])
        
    except Exception as e:
        logger.error("Ошибка очистки БД: {}", str(e))
        await callback.message.edit_text(
            format_error_message(
                "Ошибка очистки",
                f"Произошла ошибка при очистке базы данных: {str(e)[:100]}"
            ),
            parse_mode=get_parse_mode()
        )


@commands_router.callback_query(F.data == "toggle_monitoring", OwnerFilter())
async def toggle_monitoring_callback(callback: CallbackQuery):
    """Переключить состояние мониторинга"""
    try:
        await safe_callback_answer(callback)
        
        monitor = get_channel_monitor()
        current_status = monitor.get_status()
        is_running = current_status.get("is_monitoring", False)
        
        if is_running:
            # Останавливаем мониторинг
            try:
                await monitor.stop_monitoring()
                action_text = "⏸️ Мониторинг остановлен"
                new_status = "остановлен"
                logger.info("Мониторинг остановлен пользователем {}", callback.from_user.id)
            except Exception as e:
                logger.error("Ошибка остановки мониторинга: {}", str(e))
                await safe_callback_answer(callback, "❌ Ошибка остановки мониторинга", show_alert=True)
                return
        else:
            # Запускаем мониторинг
            try:
                # Проверяем что есть активные каналы
                channel_crud = get_channel_crud()
                active_channels = await channel_crud.get_active_channels()
                
                if not active_channels:
                    await safe_callback_answer(
                        callback,
                        "❌ Нет активных каналов для мониторинга.\nДобавьте каналы сначала.",
                        show_alert=True
                    )
                    return
                
                # Проверяем статус UserBot
                from src.userbot.auth_manager import get_auth_manager, AuthStatus
                auth_manager = get_auth_manager()
                auth_status = await auth_manager.get_status()
                
                if auth_status != AuthStatus.CONNECTED:
                    await safe_callback_answer(
                        callback,
                        "❌ UserBot не подключен.\nПодключите UserBot для мониторинга.",
                        show_alert=True
                    )
                    return
                
                await monitor.start_monitoring()
                action_text = "▶️ Мониторинг запущен"
                new_status = "активен"
                logger.info("Мониторинг запущен пользователем {}", callback.from_user.id)
                
            except Exception as e:
                logger.error("Ошибка запуска мониторинга: {}", str(e))
                await safe_callback_answer(callback, f"❌ Ошибка запуска: {str(e)[:50]}", show_alert=True)
                return
        
        # Обновляем статус мониторинга
        updated_status = monitor.get_status()
        is_now_running = updated_status.get("is_monitoring", False)
        
        status_icon = "🟢" if is_now_running else "🔴"
        status_text = "Активен" if is_now_running else "Остановлен"
        
        # Получаем количество активных каналов
        channel_crud = get_channel_crud()
        active_channels = await channel_crud.get_active_channels()
        
        monitoring_text = f"""📊 {bold('Статус мониторинга')}

{status_icon} {bold('Состояние:')} {status_text}

✅ {action_text}

📋 {bold('Детали:')}
• Активных каналов: {len(active_channels)}
• Интервал проверки: {get_config().MONITORING_INTERVAL} сек

🔍 {bold('Процесс мониторинга:')}
{format_list_items([
    'Проверка новых постов в каналах',
    'Фильтрация постов с изображениями',
    'AI анализ релевантности',
    'Отправка на модерацию'
])}"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏸️ Остановить мониторинг" if is_now_running else "▶️ Запустить мониторинг",
                    callback_data="toggle_monitoring"
                )
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить статус", callback_data="monitoring_status")
            ],
            [
                InlineKeyboardButton(text="⬅️ К статусу системы", callback_data="system_status")
            ]
        ])
        
        await callback.message.edit_text(
            monitoring_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
    except Exception as e:
        logger.error("Ошибка переключения мониторинга: {}", str(e))
        await safe_callback_answer(callback, "❌ Ошибка переключения мониторинга", show_alert=True)


@commands_router.callback_query(F.data == "examples_settings", OwnerFilter())
async def examples_settings_callback(callback: CallbackQuery):
    """Настройки примеров"""
    await callback.answer()
    await callback.message.edit_text(
        "📝 <b>Настройки примеров</b>\n\n"
        "🚧 Этот раздел находится в разработке.\n"
        "Скоро здесь можно будет настроить:\n"
        "• Критерии качества примеров\n"
        "• Автоматическая категоризация\n"
        "• Веса различных категорий\n"
        "• Экспорт/импорт примеров",
        parse_mode="HTML"
    )


@commands_router.callback_query(F.data == "reset_settings", OwnerFilter())
async def reset_settings_callback(callback: CallbackQuery):
    """Сброс настроек"""
    await callback.answer()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚠️ Да, сбросить все", callback_data="confirm_reset_settings"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="settings_menu")
        ]
    ])
    
    await callback.message.edit_text(
        "⚠️ <b>Сброс настроек</b>\n\n"
        "Вы действительно хотите сбросить все настройки к значениям по умолчанию?\n\n"
        "⚠️ <b>ВНИМАНИЕ:</b> Это действие нельзя отменить!\n\n"
        "Будут сброшены:\n"
        "• Настройки AI и промпты\n"
        "• Конфигурация мониторинга\n"  
        "• Расписание публикаций\n"
        "• Прочие параметры системы\n\n"
        "<i>Каналы и примеры постов НЕ будут удалены</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def get_system_status() -> Dict[str, Any]:
    """Получить статус всех компонентов системы"""
    try:
        status = {}
        
        # Статус UserBot мониторинга
        monitor = get_channel_monitor()
        monitor_status = monitor.get_status()
        status["monitor"] = {
            "is_running": monitor_status.get("is_monitoring", False),
            "uptime": monitor_status.get("uptime_seconds", 0),
            "channels_count": len(await get_channel_crud().get_active_channels())
        }
        
        # Статус AI процессора
        try:
            from src.utils.config import get_config
            config = get_config()
            ai_processor = get_ai_processor()
            status["ai"] = {
                "is_available": True,
                "model": config.OPENAI_MODEL
            }
        except Exception:
            status["ai"] = {
                "is_available": False,
                "model": None
            }
        
        # Статус базы данных
        try:
            channel_crud = get_channel_crud()
            post_crud = get_post_crud()
            user_post_crud = get_user_post_crud()
            
            status["database"] = {
                "is_available": True,
                "channels": len(await channel_crud.get_all_channels()),
                "posts": len(await post_crud.get_all_posts()),
                "user_posts": len(await user_post_crud.get_active_user_posts())
            }
        except Exception:
            status["database"] = {
                "is_available": False
            }
        
        # Статус бота
        status["bot"] = {
            "is_running": True,
            "start_time": datetime.now()
        }
        
        return status
        
    except Exception as e:
        logger.error("Ошибка получения статуса системы: {}", str(e))
        return {}


def format_status_message(status: Dict[str, Any]) -> str:
    """Форматировать сообщение со статусом"""
    try:
        text = "📊 <b>Статус Channel Agent</b>\n\n"
        
        # Статус мониторинга
        monitor = status.get("monitor", {})
        monitor_icon = "🟢" if monitor.get("is_running") else "🔴"
        text += f"{monitor_icon} <b>Мониторинг:</b> "
        text += "Активен" if monitor.get("is_running") else "Остановлен"
        text += f"\n   📺 Каналов: {monitor.get('channels_count', 0)}\n"
        
        if monitor.get("uptime"):
            hours = monitor["uptime"] // 3600
            minutes = (monitor["uptime"] % 3600) // 60
            text += f"   ⏱️ Время работы: {hours}ч {minutes}м\n"
        
        # Статус AI
        ai = status.get("ai", {})
        ai_icon = "🟢" if ai.get("is_available") else "🔴"
        text += f"\n{ai_icon} <b>AI Модуль:</b> "
        text += "Доступен" if ai.get("is_available") else "Недоступен"
        if ai.get("model"):
            text += f"\n   🧠 Модель: {ai['model']}\n"
        
        # Статус БД
        db = status.get("database", {})
        db_icon = "🟢" if db.get("is_available") else "🔴"
        text += f"\n{db_icon} <b>База данных:</b> "
        text += "Подключена" if db.get("is_available") else "Недоступна"
        
        if db.get("is_available"):
            text += f"\n   📺 Каналов: {db.get('channels', 0)}"
            text += f"\n   📝 Постов: {db.get('posts', 0)}"
            text += f"\n   📋 Примеров: {db.get('user_posts', 0)}\n"
        
        # Общий статус
        all_ok = (
            monitor.get("is_running", False) and
            ai.get("is_available", False) and 
            db.get("is_available", False)
        )
        
        overall_icon = "✅" if all_ok else "⚠️"
        text += f"\n{overall_icon} <b>Общий статус:</b> "
        text += "Все системы работают" if all_ok else "Есть проблемы"
        
        return text
        
    except Exception as e:
        logger.error("Ошибка форматирования статуса: {}", str(e))
        return "❌ Ошибка получения статуса"


async def get_detailed_statistics() -> Dict[str, Any]:
    """Получить детальную статистику системы"""
    try:
        stats = {}
        
        # Статистика каналов
        channel_crud = get_channel_crud()
        channels = await channel_crud.get_all_channels()
        stats["channels"] = {
            "total": len(channels),
            "active": len([c for c in channels if c.is_active]),
            "total_processed": sum(c.posts_processed for c in channels)
        }
        
        # Статистика постов
        post_crud = get_post_crud()
        all_posts = await post_crud.get_all_posts()
        stats["posts"] = {
            "total": len(all_posts),
            "pending": len([p for p in all_posts if p.status == PostStatus.PENDING]),
            "approved": len([p for p in all_posts if p.status == PostStatus.APPROVED]),
            "rejected": len([p for p in all_posts if p.status == PostStatus.REJECTED]),
            "published": len([p for p in all_posts if p.status == PostStatus.POSTED])
        }
        
        # Статистика примеров
        user_post_crud = get_user_post_crud()
        user_stats = await user_post_crud.get_statistics()
        stats["user_posts"] = user_stats
        
        return stats
        
    except Exception as e:
        logger.error("Ошибка получения статистики: {}", str(e))
        return {}


def format_statistics_message(stats: Dict[str, Any]) -> str:
    """Форматировать сообщение со статистикой"""
    try:
        text = "📈 <b>Детальная статистика</b>\n\n"
        
        # Каналы
        channels = stats.get("channels", {})
        text += "📺 <b>Каналы:</b>\n"
        text += f"   Всего: {channels.get('total', 0)}\n"
        text += f"   Активных: {channels.get('active', 0)}\n"
        text += f"   Обработано постов: {channels.get('total_processed', 0)}\n\n"
        
        # Посты
        posts = stats.get("posts", {})
        text += "📝 <b>Посты:</b>\n"
        text += f"   Всего: {posts.get('total', 0)}\n"
        text += f"   ⏳ На модерации: {posts.get('pending', 0)}\n"
        text += f"   ✅ Одобрены: {posts.get('approved', 0)}\n"
        text += f"   ❌ Отклонены: {posts.get('rejected', 0)}\n"
        text += f"   📤 Опубликованы: {posts.get('published', 0)}\n\n"
        
        # Примеры
        user_posts = stats.get("user_posts", {})
        text += "📋 <b>Примеры постов:</b>\n"
        text += f"   Всего: {user_posts.get('total_posts', 0)}\n"
        text += f"   Активных: {user_posts.get('active_posts', 0)}\n"
        text += f"   Средняя оценка: {user_posts.get('average_quality_score', 0)}/10\n"
        
        return text
        
    except Exception as e:
        logger.error("Ошибка форматирования статистики: {}", str(e))
        return "❌ Ошибка получения статистики"


def get_commands_router() -> Router:
    """Получить роутер команд"""
    return commands_router