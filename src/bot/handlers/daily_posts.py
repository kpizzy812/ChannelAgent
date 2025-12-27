"""
Обработчики для управления ежедневными постами
Создание, планирование и управление шаблонами
"""

from datetime import datetime, time
from typing import Optional

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# aiogram импорты
from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Локальные импорты
from src.bot.filters.owner import OwnerFilter
from src.bot.states.fsm import DailyPostStates
from src.scheduler.templates import (
    get_template_manager, 
    create_daily_post_from_template,
    get_available_variables
)
from src.utils.config import get_config

# Настройка логгера модуля
logger = logger.bind(module="bot_daily_posts")


async def ensure_target_channel_exists(channel_id: int) -> None:
    """
    Обеспечить существование целевого канала в БД
    
    Args:
        channel_id: ID канала
    """
    try:
        from src.database.crud.channel import get_channel_crud
        from src.database.models.channel import Channel
        
        channel_crud = get_channel_crud()
        
        # Проверяем существует ли канал
        existing_channel = await channel_crud.get_by_channel_id(channel_id)
        if not existing_channel:
            # Создаем системный канал
            system_channel = Channel(
                channel_id=channel_id,
                username="target_channel",
                title="Целевой канал для публикации",
                is_active=True
            )
            await channel_crud.create(system_channel)
            logger.info("Создан целевой канал в БД: {}", channel_id)
        else:
            logger.debug("Целевой канал уже существует в БД: {}", channel_id)
            
    except Exception as e:
        logger.error("Ошибка проверки/создания целевого канала: {}", str(e))
        raise


async def safe_edit_message(
    callback: CallbackQuery, 
    text: str, 
    reply_markup=None, 
    parse_mode: str = "Markdown"
) -> None:
    """
    Безопасное редактирование сообщения (текст или фото)
    
    Args:
        callback: Callback объект
        text: Новый текст
        reply_markup: Клавиатура
        parse_mode: Режим парсинга
    """
    try:
        if callback.message.photo:
            # Если сообщение с фото, отправляем новое
            await callback.message.delete()
            await callback.message.answer(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            # Если текстовое сообщение, редактируем
            await callback.message.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    except Exception as edit_error:
        logger.debug("Не удалось отредактировать сообщение: {}, отправляем новое", str(edit_error))
        try:
            await callback.message.answer(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except Exception as send_error:
            logger.error("Не удалось отправить сообщение: {}", str(send_error))
            await callback.answer("❌ Ошибка обновления интерфейса", show_alert=True)


async def refresh_template_preview(callback: CallbackQuery, template_name: str) -> None:
    """
    Обновить предпросмотр шаблона без изменения callback.data
    
    Args:
        callback: Callback объект
        template_name: Имя шаблона
    """
    try:
        template_manager = get_template_manager()
        template = await template_manager.get_template(template_name)
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        # Получаем превью с переменными
        from src.scheduler.coingecko import get_template_variables
        variables = await get_template_variables()
        from src.scheduler.coingecko import apply_template_variables
        rendered_template = apply_template_variables(template.template, variables)
        
        # Ограничиваем длину превью
        if len(rendered_template) > 600:
            preview_text = rendered_template[:600] + "..."
        else:
            preview_text = rendered_template
        
        # Загружаем настройки шаблона из таблицы templates
        try:
            is_active = await template_manager.is_template_active(template_name)
            pin_enabled = await template_manager.get_template_pin_enabled(template_name)
            auto_time = await template_manager.get_template_auto_time(template_name)
            
            logger.debug("Настройки шаблона '{}': active={}, pin={}, time={}", 
                        template_name, is_active, pin_enabled, auto_time)
        except Exception as e:
            logger.warning("Ошибка загрузки настроек шаблона: {}", str(e))
            is_active = True
            pin_enabled = False
            auto_time = None
        
        # Статусы для отображения
        active_icon = "✅" if is_active else "💤"
        pin_icon = "📌" if pin_enabled else "🔓"
        time_icon = "⏰" if auto_time else "🕐"
        
        # Создаем текст предпросмотра
        text = f"🎨 **Шаблон: {template_name}**\n\n"
        text += f"**📝 Превью:**\n{preview_text}\n\n"
        text += "**⚙️ Настройки:**\n"
        text += f"{active_icon} Статус: {'Активен' if is_active else 'Неактивен'}\n"
        text += f"{pin_icon} Закрепление: {'Включено' if pin_enabled else 'Отключено'}\n"
        text += f"{time_icon} Время: {auto_time or 'Не установлено'}\n"
        
        if template.has_photo:
            text += "📸 Содержит фото\n"
        
        text += f"\n📊 Символов: {len(template.template)}"
        
        # Кнопки управления
        keyboard = []
        
        # Переключатели статуса
        toggle_active_text = "💤 Деактивировать" if is_active else "✅ Активировать"
        toggle_pin_text = "🔓 Отключить закрепление" if pin_enabled else "📌 Включить закрепление"
        
        keyboard.extend([
            [
                InlineKeyboardButton(text=toggle_active_text, callback_data=f"toggle_active_{template_name}"),
                InlineKeyboardButton(text=toggle_pin_text, callback_data=f"toggle_pin_{template_name}")
            ],
            [
                InlineKeyboardButton(text=f"{time_icon} Настроить время", callback_data=f"set_template_time_{template_name}"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_template_{template_name}")
            ]
        ])
        
        # Действия с шаблоном  
        keyboard.extend([
            [
                InlineKeyboardButton(text="🚀 Создать пост сейчас", callback_data=f"test_template_{template_name}"),
                InlineKeyboardButton(text="📋 Копировать", callback_data=f"copy_template_{template_name}")
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить шаблон", callback_data=f"delete_template_{template_name}"),
                InlineKeyboardButton(text="🔙 К списку", callback_data="daily_templates")
            ]
        ])
        
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        # Отправляем превью с фото если есть
        if template.has_photo and template.photo_info and template.photo_info.get('file_id'):
            try:
                from aiogram.types import InputMediaPhoto
                await callback.message.edit_media(
                    media=InputMediaPhoto(
                        media=template.photo_info['file_id'],
                        caption=text,
                        parse_mode="Markdown"
                    ),
                    reply_markup=reply_markup
                )
            except Exception:
                # Fallback - используем безопасное редактирование
                await safe_edit_message(callback, text, reply_markup, "Markdown")
        else:
            # Используем безопасное редактирование
            await safe_edit_message(callback, text, reply_markup, "Markdown")
            
        logger.info("Показан предпросмотр шаблона '{}' пользователю {}", template_name, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка обновления предпросмотра шаблона '{}': {}", template_name, str(e))
        await callback.answer("❌ Ошибка загрузки шаблона", show_alert=True)


# Создаем роутер
router = Router()

# Применяем фильтр владельца ко всем обработчикам
router.message.filter(OwnerFilter())
router.callback_query.filter(OwnerFilter())


# Используем состояния из fsm.py


@router.message(Command("daily"))
async def daily_posts_menu(message: Message, state: FSMContext):
    """Главное меню управления ежедневными постами"""
    try:
        logger.debug("Пользователь {} открыл меню ежедневных постов", message.from_user.id)
        
        # Сброс состояния
        await state.clear()
        
        # Проверяем текущие настройки из БД
        from src.database.crud.setting import get_bool_setting
        daily_enabled = await get_bool_setting("daily_post.enabled", True)  # По умолчанию включено
        
        # Получаем количество активных шаблонов с автопубликацией
        from src.scheduler.templates import get_template_manager
        template_manager = get_template_manager()
        try:
            active_templates = await template_manager.get_active_templates_with_time()
            active_templates_count = len(active_templates)
        except:
            active_templates_count = 0
            
        # Получаем время для legacy постов из БД
        from src.database.crud.setting import get_setting_value
        daily_time = await get_setting_value("daily_post.time", "09:00")
        
        status_text = "🟢 Включены" if daily_enabled else "🔴 Выключены"
        
        menu_text = f"""📊 **Ежедневные посты с криптоданными**

📊 **Текущий статус:**
• 📈 Публикация: {status_text}
• 🤖 Активных шаблонов: {active_templates_count}
• ⏰ Время legacy поста: {daily_time} (UTC+3)

🚀 **Возможности системы:**
• Автозагрузка курсов криптовалют (CoinGecko API)
• Капитализация рынка и доминация BTC
• Умные шаблоны с 15+ переменными
• Автовыбор шаблона по состоянию рынка
• Закрепление постов в канале

💎 **Поддерживаемые валюты:**
BTC • ETH • SOL • ADA • DOT

📝 **Переменные для шаблонов:**
`{{BTC}}` `{{BTC_CHANGE}}` `{{MARKET_CAP}}` `{{BTC_DOMINANCE}}`
`{{DATE}}` `{{TIME}}` `{{WEEKDAY_RU}}` и другие"""
        
        # Создаем клавиатуру для управления шаблонами
        toggle_text = "🔴 Выключить публикацию" if daily_enabled else "🟢 Включить публикацию"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Создать разовый пост", callback_data="daily_create_new")
            ],
            [
                InlineKeyboardButton(text="📋 Мои шаблоны", callback_data="daily_templates"),
                InlineKeyboardButton(text="➕ Создать шаблон", callback_data="daily_create_template")
            ],
            [
                InlineKeyboardButton(text=toggle_text, callback_data="daily_toggle_publication")
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить статус", callback_data="daily_refresh")
            ]
        ])
        
        await message.answer(menu_text, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        logger.error("Ошибка отображения меню ежедневных постов: {}", str(e))
        await message.answer("❌ Ошибка загрузки меню ежедневных постов")


@router.callback_query(lambda c: c.data == "daily_toggle_publication")
async def toggle_daily_publication(callback: CallbackQuery):
    """Переключить включение/выключение ежедневной публикации"""
    try:
        await callback.answer("⏳ Обновляю настройки...")
        
        # Получаем текущее состояние из БД
        from src.database.crud.setting import get_bool_setting
        current_enabled = await get_bool_setting("daily_post.enabled", True)  # По умолчанию включено
        
        # Переключаем состояние
        new_enabled = not current_enabled
        
        # Обновляем настройку в БД
        from src.database.crud.setting import get_setting_crud
        setting_crud = get_setting_crud()
        
        await setting_crud.set_setting(
            key="daily_post.enabled",
            value="true" if new_enabled else "false"
        )
        
        status_text = "включена" if new_enabled else "выключена"
        emoji = "🟢" if new_enabled else "🔴"
        
        notification_text = f"{emoji} **Публикация ежедневных постов {status_text}**"
        
        await callback.message.answer(
            notification_text,
            parse_mode="Markdown"
        )
        
        # Обновляем главное меню
        await daily_posts_refresh_menu(callback)
        
        logger.info("Пользователь {} изменил публикацию ежедневных постов: {}", 
                   callback.from_user.id, status_text)
        
    except Exception as e:
        logger.error("Ошибка переключения публикации: {}", str(e))
        await callback.answer("❌ Ошибка изменения настроек", show_alert=True)


@router.callback_query(lambda c: c.data == "daily_refresh")
async def daily_posts_refresh_menu(callback: CallbackQuery):
    """Обновить меню ежедневных постов"""
    try:
        await callback.answer()
        
        # Получаем текущие настройки из БД
        from src.database.crud.setting import get_bool_setting
        daily_enabled = await get_bool_setting("daily_post.enabled", True)  # По умолчанию включено
        
        # Получаем количество активных шаблонов с автопубликацией
        from src.scheduler.templates import get_template_manager
        template_manager = get_template_manager()
        try:
            active_templates = await template_manager.get_active_templates_with_time()
            active_templates_count = len(active_templates)
        except:
            active_templates_count = 0
            
        # Получаем время для legacy постов из БД
        from src.database.crud.setting import get_setting_value
        daily_time = await get_setting_value("daily_post.time", "09:00")
        
        status_text = "🟢 Включены" if daily_enabled else "🔴 Выключены"
        
        menu_text = f"""📊 **Ежедневные посты с криптоданными**

📊 **Текущий статус:**
• 📈 Публикация: {status_text}
• 🤖 Активных шаблонов: {active_templates_count}
• ⏰ Время legacy поста: {daily_time} (UTC+3)

🚀 **Возможности системы:**
• Автозагрузка курсов криптовалют (CoinGecko API)
• Капитализация рынка и доминация BTC
• Умные шаблоны с 15+ переменными
• Автовыбор шаблона по состоянию рынка
• Закрепление постов в канале

💎 **Поддерживаемые валюты:**
BTC • ETH • SOL • ADA • DOT

📝 **Переменные для шаблонов:**
`{{BTC}}` `{{BTC_CHANGE}}` `{{MARKET_CAP}}` `{{BTC_DOMINANCE}}`
`{{DATE}}` `{{TIME}}` `{{WEEKDAY_RU}}` и другие"""
        
        # Создаем клавиатуру
        toggle_text = "🔴 Выключить публикацию" if daily_enabled else "🟢 Включить публикацию"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Создать разовый пост", callback_data="daily_create_new")
            ],
            [
                InlineKeyboardButton(text="📋 Мои шаблоны", callback_data="daily_templates"),
                InlineKeyboardButton(text="➕ Создать шаблон", callback_data="daily_create_template")
            ],
            [
                InlineKeyboardButton(text=toggle_text, callback_data="daily_toggle_publication")
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить статус", callback_data="daily_refresh")
            ]
        ])
        
        try:
            await safe_edit_message(
                callback,
                menu_text,
                reply_markup=keyboard
            )
        except Exception as edit_error:
            # Если не удается редактировать (например, сообщение с фото), отправляем новое
            logger.debug("Не удалось отредактировать сообщение, отправляем новое: {}", str(edit_error))
            await callback.message.answer(
                menu_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        
    except Exception as e:
        logger.error("Ошибка обновления меню: {}", str(e))
        await callback.answer("❌ Ошибка обновления", show_alert=True)


@router.callback_query(lambda c: c.data == "daily_create_new")
async def start_creating_new_post(callback: CallbackQuery, state: FSMContext):
    """Начать создание нового поста с выбором шаблона"""
    try:
        logger.info("Пользователь {} начинает создание нового поста", callback.from_user.id)
        
        await callback.answer()
        
        # Получаем список пользовательских шаблонов
        from src.scheduler.templates import get_template_manager
        template_manager = get_template_manager()
        templates = await template_manager.list_templates()
        
        # Фильтруем только пользовательские шаблоны
        user_templates = [t for t in templates if t.get('type') == 'custom']
        
        if not user_templates:
            try:
                await safe_edit_message(
                    callback,
                    "❌ **У вас нет созданных шаблонов!**\n\n"
                    "Сначала создайте шаблон для постов.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="➕ Создать шаблон", callback_data="daily_create_template")],
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="daily_refresh")]
                    ])
                )
            except Exception as edit_error:
                logger.debug("Не удалось отредактировать сообщение, отправляем новое: {}", str(edit_error))
                await callback.message.answer(
                    "❌ **У вас нет созданных шаблонов!**\n\n"
                    "Сначала создайте шаблон для постов.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="➕ Создать шаблон", callback_data="daily_create_template")],
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="daily_refresh")]
                    ]),
                    parse_mode="Markdown"
                )
            return
        
        # Показываем список пользовательских шаблонов для выбора
        menu_text = "📝 **Выберите шаблон для создания поста:**\n\n"
        
        keyboard = []
        for template in user_templates:
            name = template['name']
            desc = template['description'] or "Без описания"
            button_text = f"{desc[:25]}..." if len(desc) > 25 else desc
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📋 {button_text}", 
                    callback_data=f"create_from_template_{name}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="daily_refresh")
        ])
        
        try:
            await safe_edit_message(
                callback,
                menu_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
        except Exception as edit_error:
            logger.debug("Не удалось отредактировать сообщение, отправляем новое: {}", str(edit_error))
            await callback.message.answer(
                menu_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        
    except Exception as e:
        logger.error("Ошибка начала создания поста: {}", str(e))
        await callback.answer("❌ Ошибка создания поста", show_alert=True)



@router.callback_query(lambda c: c.data.startswith("create_from_template_"))
async def create_post_from_template(callback: CallbackQuery, state: FSMContext):
    """Создать пост из выбранного шаблона"""
    try:
        template_name = callback.data.replace("create_from_template_", "")
        logger.info("Пользователь {} создает пост из шаблона: {}", callback.from_user.id, template_name)
        
        await callback.answer("⏳ Создаю пост из шаблона...")
        
        # Создаем контент из шаблона
        from src.scheduler.templates import create_daily_post_from_template
        post_content = await create_daily_post_from_template(template_name=template_name)
        
        if not post_content:
            try:
                await safe_edit_message(
                    callback,
                    "❌ **Ошибка создания поста!**\n\n"
                    "Не удалось сгенерировать контент из шаблона.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="daily_create_new")]
                    ])
                )
            except Exception as edit_error:
                logger.debug("Не удалось отредактировать сообщение, отправляем новое: {}", str(edit_error))
                await callback.message.answer(
                    "❌ **Ошибка создания поста!**\n\n"
                    "Не удалось сгенерировать контент из шаблона.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="daily_create_new")]
                    ]),
                    parse_mode="Markdown"
                )
            return
        
        # Показываем превью поста и настройки
        # Обрезаем для превью
        if len(post_content) > 500:
            preview_text = post_content[:500] + "..."
        else:
            preview_text = post_content
        
        settings_text = f"📝 **Превью поста:**\n\n{preview_text}\n\n"
        settings_text += "⚙️ **Настройки публикации:**\n"
        settings_text += "📅 Время: Сейчас\n"
        settings_text += "📌 Закрепить: Нет\n\n"
        settings_text += "Настроить публикацию?"
        
        # Сохраняем контент поста в состояние
        await state.update_data(post_content=post_content, template_name=template_name)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📤 Сейчас", callback_data="publish_now"),
                InlineKeyboardButton(text="⏰ Настроить время", callback_data="setup_publish_time")
            ],
            [
                InlineKeyboardButton(text="📌 Закрепить пост", callback_data="toggle_pin"),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_post_content")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="daily_create_new")
            ]
        ])
        
        try:
            await safe_edit_message(
                callback,
                settings_text,
                reply_markup=keyboard
            )
        except Exception as edit_error:
            logger.debug("Не удалось отредактировать сообщение, отправляем новое: {}", str(edit_error))
            await callback.message.answer(
                settings_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        
        # Устанавливаем состояние настройки поста
        await state.set_state(DailyPostStates.configuring_post)
        
    except Exception as e:
        logger.error("Ошибка создания поста из шаблона: {}", str(e))
        await callback.answer("❌ Ошибка создания поста", show_alert=True)


@router.callback_query(lambda c: c.data == "publish_now", DailyPostStates.configuring_post)
async def publish_post_now(callback: CallbackQuery, state: FSMContext):
    """Опубликовать пост сейчас"""
    try:
        await callback.answer("📤 Публикую пост...")
        
        # Получаем данные из состояния
        data = await state.get_data()
        post_content = data.get('post_content')
        pin_post = data.get('pin_post', False)
        template_name = data.get('template_name')
        
        if not post_content:
            await callback.answer("❌ Ошибка: контент поста не найден", show_alert=True)
            return
        
        # Получаем информацию о фото из шаблона
        photo_file_id = None
        if template_name:
            from src.scheduler.templates import get_template_manager
            template_manager = get_template_manager()
            template = await template_manager.get_template(template_name)
            if template and template.photo_info:
                photo_file_id = template.photo_info.get('file_id')
                logger.info("📸 Получен photo_file_id из шаблона '{}': {}", template_name, photo_file_id)
            else:
                logger.info("📝 Шаблон '{}' без фото", template_name)
        
        # Создаем пост в БД и публикуем
        from src.scheduler.tasks.daily_posts import save_daily_post
        
        # Создаем пост с дополнительными настройками закрепления
        from src.database.models.post import PostStatus, create_post, PostSentiment
        from src.utils.config import get_config
        config = get_config()
        
        # Обеспечиваем существование целевого канала в БД
        await ensure_target_channel_exists(config.TARGET_CHANNEL_ID)
        
        import time
        message_id = int(time.time())
        
        post = create_post(
            channel_id=config.TARGET_CHANNEL_ID,
            message_id=message_id,
            original_text=post_content,
            processed_text=post_content,
            status=PostStatus.APPROVED,  # Для немедленной публикации
            relevance_score=10,
            sentiment=PostSentiment.NEUTRAL,
            ai_analysis="Пользовательский пост с настройками публикации",
            posted_date=datetime.now(),
            pin_post=pin_post,  # Устанавливаем флаг закрепления
            photo_file_id=photo_file_id  # Добавляем фото если есть
        )
        
        logger.info("📋 Создан пост с photo_file_id: {}", photo_file_id)
        
        from src.database.crud.post import get_post_crud
        post_crud = get_post_crud()
        created_post = await post_crud.create(post)
        
        # Публикуем пост
        if created_post:
            success = await publish_post_immediately(created_post, post_content, pin_post)
            post = created_post if success else None
        else:
            post = None
        
        if post:
            success_text = f"✅ **Пост опубликован!**\n\n"
            success_text += f"🆔 ID поста: {post.id}\n"
            success_text += f"📏 Длина: {len(post_content)} символов\n"
            success_text += f"📌 Закреплен: {'Да' if pin_post else 'Нет'}"
            
            try:
                await safe_edit_message(
                    callback,
                    success_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 К меню", callback_data="daily_refresh")]
                    ])
                )
            except Exception as edit_error:
                logger.debug("Не удалось отредактировать сообщение, отправляем новое: {}", str(edit_error))
                await callback.message.answer(
                    success_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 К меню", callback_data="daily_refresh")]
                    ]),
                    parse_mode="Markdown"
                )
            
            # Если нужно закрепить пост
            if pin_post:
                try:
                    config = get_config()
                    bot = callback.bot
                    
                    # Здесь нужно получить message_id из опубликованного поста
                    # TODO: Добавить логику закрепления
                    
                except Exception as pin_error:
                    logger.warning("Ошибка закрепления поста: {}", str(pin_error))
            
            await state.clear()
            logger.info("Пост опубликован пользователем {}: ID {}", callback.from_user.id, post.id)
        else:
            try:
                await safe_edit_message(
                    callback,
                    "❌ **Ошибка публикации!**\n\nПопробуйте еще раз.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="daily_create_new")]
                    ])
                )
            except Exception as edit_error:
                logger.debug("Не удалось отредактировать сообщение, отправляем новое: {}", str(edit_error))
                await callback.message.answer(
                    "❌ **Ошибка публикации!**\n\nПопробуйте еще раз.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="daily_create_new")]
                    ])
                )
        
    except Exception as e:
        logger.error("Ошибка публикации поста: {}", str(e))
        await callback.answer("❌ Ошибка публикации", show_alert=True)


@router.callback_query(lambda c: c.data == "setup_publish_time", DailyPostStates.configuring_post)
async def setup_publish_time(callback: CallbackQuery, state: FSMContext):
    """Настроить время публикации"""
    try:
        # Получаем имя шаблона из состояния
        data = await state.get_data()
        template_name = data.get('template_name', '')
        
        try:
            await safe_edit_message(
                callback,
                "⏰ **Настройка времени публикации**\n\n"
                "Введите время в формате **HH:MM**\n\n"
                "Примеры:\n"
                "• `14:30` - сегодня в 14:30\n"
                "• `09:15` - сегодня в 09:15\n"
                "• `22:00` - сегодня в 22:00\n\n"
                "⏰ Время указывается в UTC+3\n"
                "📅 Если указанное время уже прошло сегодня,\nпост будет запланирован на завтра",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data=f"create_from_template_{template_name}")]
                ])
            )
        except Exception as edit_error:
            logger.debug("Не удалось отредактировать сообщение, отправляем новое: {}", str(edit_error))
            await callback.message.answer(
                "⏰ **Настройка времени публикации**\n\n"
                "Введите время в формате:\n"
                "• `HH:MM` - для публикации сегодня\n"
                "• `DD.MM HH:MM` - для конкретной даты\n\n"
                "Примеры:\n"
                "• `14:30` - сегодня в 14:30\n"
                "• `15.08 09:00` - 15 августа в 09:00\n\n"
                "⏰ Время указывается в UTC+3",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data=f"create_from_template_{template_name}")]
                ]),
                parse_mode="Markdown"
            )
        
        await state.set_state(DailyPostStates.setting_publish_time)
        
    except Exception as e:
        logger.error("Ошибка настройки времени: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data == "toggle_pin", DailyPostStates.configuring_post)
async def toggle_pin_post(callback: CallbackQuery, state: FSMContext):
    """Переключить закрепление поста"""
    try:
        await callback.answer()
        
        # Получаем текущее состояние
        data = await state.get_data()
        current_pin = data.get('pin_post', False)
        new_pin = not current_pin
        
        # Обновляем данные
        await state.update_data(pin_post=new_pin)
        
        # Обновляем интерфейс
        post_content = data.get('post_content', '')
        
        if len(post_content) > 500:
            preview_text = post_content[:500] + "..."
        else:
            preview_text = post_content
        
        settings_text = f"📝 **Превью поста:**\n\n{preview_text}\n\n"
        settings_text += "⚙️ **Настройки публикации:**\n"
        settings_text += "📅 Время: Сейчас\n"
        settings_text += f"📌 Закрепить: {'Да' if new_pin else 'Нет'}\n\n"
        settings_text += "Настроить публикацию?"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📤 Сейчас", callback_data="publish_now"),
                InlineKeyboardButton(text="⏰ Настроить время", callback_data="setup_publish_time")
            ],
            [
                InlineKeyboardButton(
                    text=f"📌 {'Не закреплять' if new_pin else 'Закрепить пост'}", 
                    callback_data="toggle_pin"
                ),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_post_content")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="daily_create_new")
            ]
        ])
        
        await safe_edit_message(
            callback,
            settings_text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error("Ошибка переключения закрепления: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.message(DailyPostStates.setting_publish_time)
async def process_publish_time_input(message: Message, state: FSMContext):
    """Обработка ввода времени публикации"""
    try:
        time_input = message.text.strip()
        
        # Парсим введенное время
        from datetime import datetime, timedelta
        import re
        
        # Удаляем сообщение пользователя
        try:
            await message.delete()
        except:
            pass
        
        # Проверяем формат HH:MM (только этот формат)
        if not re.match(r'^\d{1,2}:\d{2}$', time_input):
            raise ValueError("Неверный формат времени. Используйте HH:MM")
        
        hour, minute = map(int, time_input.split(':'))
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Неверное время. Часы: 0-23, минуты: 0-59")
        
        # Планируем на сегодня
        publish_time = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Если время уже прошло, планируем на завтра
        if publish_time <= datetime.now():
            publish_time += timedelta(days=1)
            day_text = "завтра"
        else:
            day_text = "сегодня"
        
        # Сохраняем время публикации
        await state.update_data(publish_time=publish_time)
        
        # Получаем данные поста
        data = await state.get_data()
        post_content = data.get('post_content', '')
        pin_post = data.get('pin_post', False)
        
        # Форматируем время для отображения
        time_str = publish_time.strftime("%d.%m.%Y %H:%M")
        
        # Обновляем превью
        if len(post_content) > 500:
            preview_text = post_content[:500] + "..."
        else:
            preview_text = post_content
        
        settings_text = f"✅ **Время установлено: {time_input} ({day_text})**\n\n"
        settings_text += f"📝 **Превью поста:**\n\n{preview_text}\n\n"
        settings_text += "⚙️ **Настройки публикации:**\n"
        settings_text += f"📅 Время: {time_str} (UTC+3)\n"
        settings_text += f"📌 Закрепить: {'Да' if pin_post else 'Нет'}\n\n"
        settings_text += "Сохранить пост для публикации?"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💾 Сохранить для публикации", callback_data="save_scheduled_post"),
                InlineKeyboardButton(text="📤 Сейчас", callback_data="publish_now")
            ],
            [
                InlineKeyboardButton(
                    text=f"📌 {'Не закреплять' if pin_post else 'Закрепить пост'}", 
                    callback_data="toggle_pin"
                ),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_post_content")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="daily_create_new")
            ]
        ])
        
        # Отправляем новое сообщение
        new_msg = await message.answer(
            settings_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        await state.update_data(bot_message=new_msg)
        
        await state.set_state(DailyPostStates.configuring_post)
        
        logger.info("Пользователь {} установил время публикации: {}", message.from_user.id, time_str)
        
    except ValueError as e:
        await message.answer(
            f"❌ **Ошибка формата времени!**\n\n"
            f"Используйте правильный формат:\n"
            f"• `HH:MM` (например: 14:30, 09:15, 22:00)\n\n"
            f"Подробность: {str(e)}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error("Ошибка обработки времени публикации: {}", str(e))
        await message.answer("❌ Ошибка обработки времени")


@router.callback_query(lambda c: c.data == "save_scheduled_post", DailyPostStates.configuring_post)
async def save_scheduled_post(callback: CallbackQuery, state: FSMContext):
    """Сохранить пост для отложенной публикации"""
    try:
        await callback.answer("💾 Сохраняю пост...")
        
        # Получаем данные из состояния
        data = await state.get_data()
        post_content = data.get('post_content')
        publish_time = data.get('publish_time')
        pin_post = data.get('pin_post', False)
        
        if not post_content or not publish_time:
            await callback.answer("❌ Ошибка: не хватает данных", show_alert=True)
            return
        
        # Создаем пост в БД для отложенной публикации  
        from src.database.models.post import PostStatus, create_post, PostSentiment
        from src.utils.config import get_config
        config = get_config()
        
        # Обеспечиваем существование целевого канала в БД
        await ensure_target_channel_exists(config.TARGET_CHANNEL_ID)
        
        import time
        message_id = int(time.time())
        
        post = create_post(
            channel_id=config.TARGET_CHANNEL_ID,
            message_id=message_id,
            original_text=post_content,
            processed_text=post_content,
            status=PostStatus.SCHEDULED,  # Статус отложенной публикации
            relevance_score=10,
            sentiment=PostSentiment.NEUTRAL,
            ai_analysis="Пользовательский пост с настройками времени публикации",
            scheduled_date=publish_time,  # Устанавливаем время публикации
            pin_post=pin_post  # Устанавливаем флаг закрепления
        )
        
        from src.database.crud.post import get_post_crud
        post_crud = get_post_crud()
        created_post = await post_crud.create(post)
        
        if created_post:
            time_str = publish_time.strftime("%d.%m.%Y %H:%M")
            
            success_text = f"✅ **Пост сохранен для публикации!**\n\n"
            success_text += f"🆔 ID поста: {created_post.id}\n"
            success_text += f"📅 Время публикации: {time_str} (UTC+3)\n"
            success_text += f"📏 Длина: {len(post_content)} символов\n"
            success_text += f"📌 Закрепить: {'Да' if pin_post else 'Нет'}\n\n"
            success_text += "Пост будет автоматически опубликован в указанное время."
            
            await safe_edit_message(
                callback,
                success_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К меню", callback_data="daily_refresh")]
                ])
            )
            
            await state.clear()
            logger.info("Отложенный пост создан пользователем {}: ID {}, время {}", 
                       callback.from_user.id, created_post.id, time_str)
        else:
            await safe_edit_message(
                callback,
                "❌ **Ошибка сохранения!**\n\nПопробуйте еще раз.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="daily_create_new")]
                ])
            )
        
    except Exception as e:
        logger.error("Ошибка сохранения отложенного поста: {}", str(e))
        await callback.answer("❌ Ошибка сохранения", show_alert=True)


@router.callback_query(lambda c: c.data == "edit_post_content", DailyPostStates.configuring_post)
async def edit_post_content(callback: CallbackQuery, state: FSMContext):
    """Редактировать контент поста"""
    try:
        await safe_edit_message(
            callback,
            "✏️ **Редактирование поста**\n\n"
            "Отправьте новый текст поста.\n"
            "Вы можете использовать переменные шаблона:\n\n"
            "`{BTC}` `{ETH}` `{SOL}` `{MARKET_CAP}` и другие\n\n"
            "💡 Telegram разметка поддерживается",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="daily_create_new")]
            ])
        )
        
        await state.set_state(DailyPostStates.editing_post_content)
        
    except Exception as e:
        logger.error("Ошибка редактирования контента: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.message(DailyPostStates.editing_post_content)
async def process_edited_content(message: Message, state: FSMContext):
    """Обработка отредактированного контента"""
    try:
        new_content = message.text
        
        # Удаляем сообщение пользователя
        try:
            await message.delete()
        except:
            pass
        
        # Обновляем контент в состоянии
        await state.update_data(post_content=new_content)
        
        # Возвращаемся к настройкам поста
        data = await state.get_data()
        pin_post = data.get('pin_post', False)
        publish_time = data.get('publish_time')
        
        if len(new_content) > 500:
            preview_text = new_content[:500] + "..."
        else:
            preview_text = new_content
        
        settings_text = f"📝 **Превью поста (отредактирован):**\n\n{preview_text}\n\n"
        settings_text += "⚙️ **Настройки публикации:**\n"
        
        if publish_time:
            time_str = publish_time.strftime("%d.%m.%Y %H:%M")
            settings_text += f"📅 Время: {time_str} (UTC+3)\n"
        else:
            settings_text += "📅 Время: Сейчас\n"
            
        settings_text += f"📌 Закрепить: {'Да' if pin_post else 'Нет'}\n\n"
        settings_text += "Настроить публикацию?"
        
        keyboard_buttons = []
        
        if publish_time:
            keyboard_buttons.append([
                InlineKeyboardButton(text="💾 Сохранить для публикации", callback_data="save_scheduled_post"),
                InlineKeyboardButton(text="📤 Сейчас", callback_data="publish_now")
            ])
        else:
            keyboard_buttons.append([
                InlineKeyboardButton(text="📤 Сейчас", callback_data="publish_now"),
                InlineKeyboardButton(text="⏰ Настроить время", callback_data="setup_publish_time")
            ])
        
        keyboard_buttons.extend([
            [
                InlineKeyboardButton(
                    text=f"📌 {'Не закреплять' if pin_post else 'Закрепить пост'}", 
                    callback_data="toggle_pin"
                ),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_post_content")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="daily_create_new")
            ]
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        new_msg = await message.answer(
            settings_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await state.update_data(bot_message=new_msg)
        await state.set_state(DailyPostStates.configuring_post)
        
        logger.info("Пользователь {} отредактировал контент поста", message.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка обработки отредактированного контента: {}", str(e))
        await message.answer("❌ Ошибка обработки контента")


async def publish_post_immediately(post, content: str, pin_post: bool = False) -> bool:
    """
    Опубликовать пост немедленно
    
    Args:
        post: Объект поста из БД
        content: Содержимое поста
        pin_post: Нужно ли закрепить пост
        
    Returns:
        True если пост опубликован успешно
    """
    try:
        logger.info("📤 Немедленная публикация поста в канал")
        
        config = get_config()
        
        # Получаем экземпляр бота
        from src.bot.main import get_bot_instance
        bot = get_bot_instance()
        
        # Публикуем пост в целевой канал
        sent_message = None
        
        # Если есть фото
        if hasattr(post, 'photo_file_id') and post.photo_file_id:
            logger.info("📸 Публикуем пост с фото: {}", post.photo_file_id)
            sent_message = await bot.send_photo(
                chat_id=config.TARGET_CHANNEL_ID,
                photo=post.photo_file_id,
                caption=content,
                parse_mode="Markdown"
            )
        else:
            logger.info("📝 Публикуем текстовый пост")
            sent_message = await bot.send_message(
                chat_id=config.TARGET_CHANNEL_ID,
                text=content,
                parse_mode="Markdown"
            )
        
        if sent_message:
            # Обновляем пост в БД - отмечаем как опубликованный
            from src.database.crud.post import get_post_crud
            from src.database.models.post import PostStatus
            post_crud = get_post_crud()
            await post_crud.update_post_status(post.id, PostStatus.POSTED)
            await post_crud.update_post(post.id, posted_date=datetime.now())
            
            # Если нужно закрепить пост
            if pin_post:
                try:
                    pin_message = await bot.pin_chat_message(
                        chat_id=config.TARGET_CHANNEL_ID,
                        message_id=sent_message.message_id,
                        disable_notification=True
                    )
                    logger.info("📌 Пост {} закреплен в канале", post.id)
                    
                    # Автоматически удаляем системное сообщение о закреплении
                    try:
                        # Обычно системное сообщение появляется следующим после закрепленного
                        import asyncio
                        await asyncio.sleep(0.5)  # Небольшая задержка
                        
                        # Получаем последние сообщения в канале
                        updates = await bot.get_updates(limit=10)
                        for update in updates:
                            if (update.message and 
                                update.message.chat.id == config.TARGET_CHANNEL_ID and
                                update.message.pinned_message and
                                update.message.pinned_message.message_id == sent_message.message_id):
                                # Это системное сообщение о закреплении
                                await bot.delete_message(
                                    chat_id=config.TARGET_CHANNEL_ID,
                                    message_id=update.message.message_id
                                )
                                logger.debug("🗑️ Удалено системное сообщение о закреплении")
                                break
                    except Exception as delete_error:
                        logger.debug("Не удалось удалить системное сообщение о закреплении: {}", str(delete_error))
                        
                except Exception as pin_error:
                    logger.warning("⚠️ Не удалось закрепить пост {}: {}", post.id, str(pin_error))
            
            logger.info("✅ Пост {} опубликован в канал: message_id {}", post.id, sent_message.message_id)
            return True
        else:
            logger.error("❌ Не удалось отправить пост в канал")
            return False
            
    except Exception as e:
        logger.error("❌ Ошибка немедленной публикации поста: {}", str(e))
        return False



@router.callback_query(lambda c: c.data == "daily_templates")
async def show_templates_list(callback: CallbackQuery):
    """Показать интерактивный список всех шаблонов"""
    try:
        template_manager = get_template_manager()
        templates = await template_manager.list_templates()
        
        if not templates:
            empty_text = ("📋 **Мои шаблоны**\n\n"
                         "❌ У вас пока нет пользовательских шаблонов\n\n"
                         "💡 Создайте свой первый шаблон для ежедневных постов!")
            empty_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать первый шаблон", callback_data="daily_create_template")],
                [InlineKeyboardButton(text="🔙 К ежедневным постам", callback_data="daily_refresh")]
            ])
            
            # Безопасная замена сообщения
            await safe_edit_message(callback, empty_text, empty_keyboard, "Markdown")
            return
        
        # Группируем шаблоны
        default_templates = [t for t in templates if t['type'] == 'default']
        custom_templates = [t for t in templates if t['type'] == 'custom']
        
        text = "📋 **Управление шаблонами**\n\n"
        
        # Показываем статистику
        total_templates = len(templates)
        custom_count = len(custom_templates)
        default_count = len(default_templates)
        
        text += f"📊 **Статистика:**\n"
        text += f"• 🔧 Стандартных: {default_count}\n"
        text += f"• ⭐ Пользовательских: {custom_count}\n"
        text += f"• 📈 Всего доступно: {total_templates}\n\n"
        
        keyboard = []
        
        # Стандартные шаблоны (только для просмотра)
        if default_templates:
            text += "🔧 **Стандартные шаблоны** (только просмотр):\n"
            for template in default_templates[:3]:  # Показываем первые 3
                status_icon = "✅"
                name = template['name']
                desc = template['description'][:30] + "..." if len(template['description']) > 30 else template['description']
                
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"{status_icon} {name} - {desc}",
                        callback_data=f"view_template_{name}"
                    )
                ])
            
            if len(default_templates) > 3:
                text += f"... и еще {len(default_templates) - 3} стандартных шаблонов\n"
            text += "\n"
        
        # Пользовательские шаблоны (полное управление)
        if custom_templates:
            text += "⭐ **Мои шаблоны** (нажмите для управления):\n"
            for template in custom_templates:
                # Получаем настройки шаблона
                is_active = template.get('is_active', True)
                has_pin = template.get('pin_enabled', False)
                has_time = template.get('auto_time') is not None
                
                # Основная иконка статуса
                status_icon = "✅" if is_active else "💤"
                
                # Дополнительные иконки
                extra_icons = ""
                if has_pin:
                    extra_icons += "📌"
                if has_time:
                    extra_icons += "⏰"
                
                name = template['name']
                desc = template['description'][:20] + "..." if len(template['description']) > 20 else template['description']
                created = template.get('created_at')
                
                # Форматируем дату создания
                if created:
                    try:
                        if isinstance(created, str):
                            from datetime import datetime
                            created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                            date_str = created_dt.strftime("%d.%m")
                        else:
                            date_str = created.strftime("%d.%m")
                    except:
                        date_str = ""
                else:
                    date_str = ""
                
                button_text = f"{status_icon}{extra_icons} {name}"
                if date_str:
                    button_text += f" ({date_str})"
                if desc and desc != "Без описания":
                    button_text += f" - {desc}"
                
                keyboard.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"manage_template_{name}"
                    )
                ])
            text += "\n"
        
        text += "💡 **Легенда:** ✅ Активен • 💤 Неактивен • 📌 Закрепление • ⏰ Свое время\n\n"
        text += "👆 **Нажмите на шаблон для индивидуального управления**"
        
        # Кнопки управления (только создание и навигация)
        keyboard.extend([
            [InlineKeyboardButton(text="➕ Создать новый шаблон", callback_data="daily_create_template")],
            [InlineKeyboardButton(text="🔙 К ежедневным постам", callback_data="daily_refresh")]
        ])
        
        # Безопасная замена сообщения на список шаблонов
        list_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await safe_edit_message(callback, text, list_keyboard, "Markdown")
        
        logger.debug("Показан улучшенный список шаблонов пользователю {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка отображения шаблонов: {}", str(e))
        await callback.answer("❌ Ошибка загрузки шаблонов", show_alert=True)


@router.callback_query(lambda c: c.data == "daily_refresh")
async def refresh_daily_menu(callback: CallbackQuery, state: FSMContext):
    """Обновить главное меню"""
    try:
        await state.clear()
        
        # Эмулируем команду /daily
        from types import SimpleNamespace
        fake_message = SimpleNamespace()
        fake_message.from_user = callback.from_user
        fake_message.answer = callback.message.edit_text
        
        await daily_posts_menu(fake_message, state)
        
    except Exception as e:
        logger.error("Ошибка обновления меню: {}", str(e))
        await callback.answer("❌ Ошибка обновления", show_alert=True)


@router.callback_query(lambda c: c.data == "daily_create_template")
async def start_create_template(callback: CallbackQuery, state: FSMContext):
    """Начать создание пользовательского шаблона"""
    try:
        variables_text = "`, `".join(get_available_variables()[:10])  # Первые 10
        
        text = f"""➕ **Создание пользовательского шаблона**

🎨 **Шаг 1:** Введите название шаблона

**Доступные переменные:**
`{variables_text}` и другие...

**Пример шаблона:**
```
🚀 Курсы на {{DATE}}

Bitcoin: {{BTC}} {{BTC_CHANGE}}
Ethereum: {{ETH}} {{ETH_CHANGE}}

Рынок: {{MARKET_CAP}} {{MARKET_CHANGE}}
```

**Поддерживается Telegram разметка:**
• `**жирный**` → **жирный**
• `*курсив*` → *курсив*
• `__подчеркнутый__` → __подчеркнутый__
• `||спойлер||` → ||спойлер||
• `>цитата` → цитата

Введите название шаблона:"""
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="daily_refresh")]
            ]),
            parse_mode="Markdown"
        )
        
        await state.set_state(DailyPostStates.entering_template_name)
        
    except Exception as e:
        logger.error("Ошибка создания шаблона: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.message(DailyPostStates.entering_template_name)
async def process_template_name(message: Message, state: FSMContext):
    """Обработка названия шаблона"""
    try:
        # Безопасная проверка на None
        if not message.text:
            await message.answer(
                "❌ **Нужно отправить текстовое сообщение с названием!**\n\n"
                "Пожалуйста, введите название шаблона:",
                parse_mode="Markdown"
            )
            return
        
        template_name = message.text.strip()
        
        # Валидация названия
        if len(template_name) < 2:
            await message.answer(
                "❌ Название слишком короткое! Минимум 2 символа.\n"
                "Введите название еще раз:"
            )
            return
        
        if len(template_name) > 50:
            await message.answer(
                "❌ Название слишком длинное! Максимум 50 символов.\n"
                "Введите название еще раз:"
            )
            return
        
        # Проверяем что шаблон с таким именем не существует
        template_manager = get_template_manager()
        if await template_manager.get_template(template_name):
            await message.answer(
                f"❌ Шаблон с названием **'{template_name}'** уже существует!\n"
                "Выберите другое название:",
                parse_mode="Markdown"
            )
            return
        
        # Сохраняем название в состояние
        await state.update_data(template_name=template_name)
        
        # Переходим к вводу текста шаблона
        variables_list = "\n".join([
            "• `{BTC}` - Bitcoin: $95,432 📈 +2.5%",
            "• `{ETH}` - Ethereum: $3,245 📉 -1.2%", 
            "• `{SOL}` - Solana: $105.67 📈 +5.1%",
            "• `{ADA}` - Cardano: $0.456 📈 +0.8%",
            "• `{DOT}` - Polkadot: $7.89 📉 -2.1%",
            "• `{MARKET_CAP}` - $2.34T 📈 +1.5%",
            "• `{BTC_DOMINANCE}` - 56.7%",
            "• `{DATE}` - 07.08.2025",
            "• `{TIME}` - 14:30", 
            "• `{WEEKDAY_RU}` - Среда"
        ])
        
        await message.answer(
            f"✅ Название: **'{template_name}'**\n\n"
            "🎨 **Шаг 2:** Создайте пост с шаблоном\n\n"
            "**📋 Доступные переменные:**\n"
            f"{variables_list}\n\n"
            "**✨ Как создать:**\n"
            "1. Напишите текст и примените **форматирование** через Telegram\n"
            "2. Добавьте переменные где нужно: `{BTC}`, `{MARKET_CAP}` и т.д.\n"
            "3. Можете приложить **фото** к сообщению\n"
            "4. Отправьте готовый пост\n\n"
            "💡 **Используйте встроенное форматирование Telegram!**\n"
            "Выделите текст → выберите **жирный/курсив/подчеркнутый**",
            parse_mode="Markdown"
        )
        
        await state.set_state(DailyPostStates.entering_template_text)
        
    except Exception as e:
        logger.error("Ошибка обработки названия шаблона: {}", str(e))
        await message.answer("❌ Ошибка обработки названия")


@router.message(DailyPostStates.entering_template_text)
async def process_template_text(message: Message, state: FSMContext):
    """Обработка текста шаблона с сохранением форматирования"""
    try:
        # Извлекаем текст из любого типа сообщения
        template_text = message.text or message.caption or ""
        
        if not template_text.strip():
            await message.answer(
                "❌ **Текст шаблона не может быть пустым!**\n\n"
                "Отправьте сообщение с текстом или фото с подписью.\n"
                "Не забудьте добавить переменные: `{BTC}`, `{MARKET_CAP}` и т.д.",
                parse_mode="Markdown"
            )
            return
        
        if len(template_text) > 4000:
            await message.answer(
                "❌ Текст слишком длинный! Максимум 4000 символов.\n"
                "Сократите шаблон и попробуйте еще раз:"
            )
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        template_name = data.get('template_name', 'unknown')
        
        # Для превью используем сырой текст с переменными
        formatted_template = template_text
        
        # Сохраняем информацию о фото если есть
        has_photo = bool(message.photo)
        photo_info = None
        
        if has_photo:
            # Получаем информацию о фото (можно добавить сохранение file_id)
            photo = message.photo[-1]  # Берем самое большое фото
            photo_info = {
                'file_id': photo.file_id,
                'width': photo.width,
                'height': photo.height,
                'file_size': photo.file_size
            }
            logger.debug("Шаблон содержит фото: {}x{}, {} байт", 
                        photo.width, photo.height, photo.file_size)
        
        # Создаем превью шаблона с подставленными переменными
        from src.scheduler.coingecko import get_template_variables, apply_template_variables
        
        try:
            # Получаем переменные для превью
            variables = await get_template_variables()
            
            # Применяем переменные к сырому тексту
            from src.scheduler.coingecko import apply_template_variables
            preview_text = apply_template_variables(template_text, variables)
            
            # Обрезаем для превью
            if len(preview_text) > 800:
                preview_text = preview_text[:800] + "..."
            
        except Exception as e:
            logger.warning("Ошибка создания превью шаблона: {}", str(e))
            preview_text = formatted_template[:400] + "..." if len(formatted_template) > 400 else formatted_template
        
        # Сохраняем все данные в состояние  
        await state.update_data(
            template_text=template_text,  # Сырой текст для переменных и БД
            formatted_template=template_text,  # Тоже сырой текст
            has_photo=has_photo,
            photo_info=photo_info
        )
        
        # Показываем превью
        photo_text = "\n📷 **С фото**" if has_photo else ""
        confirm_text = f"🎨 **Превью шаблона '{template_name}':**{photo_text}\n\n"
        confirm_text += "*📝 Форматирование (жирный, курсив и т.д.) отобразится корректно в итоговом посте*\n\n"
        
        # Отправляем превью с сохранением форматирования
        try:
            if has_photo and photo_info:
                # Отправляем превью как фото с подписью
                await message.answer_photo(
                    photo=photo_info['file_id'],
                    caption=confirm_text + preview_text + "\n\n**Сохранить этот шаблон?**",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Сохранить", callback_data="save_template"),
                            InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_template")
                        ],
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_template")]
                    ]),
                    parse_mode="Markdown"  # Используем Markdown - соответствует _extract_formatted_text_from_message
                )
            else:
                # Отправляем как обычное сообщение
                await message.answer(
                    confirm_text + preview_text + "\n\n**Сохранить этот шаблон?**",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Сохранить", callback_data="save_template"),
                            InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_template")
                        ],
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_template")]
                    ]),
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            # Fallback без форматирования
            logger.debug("Ошибка отправки превью с форматированием: {}", str(e))
            await message.answer(
                f"🎨 Превью шаблона '{template_name}':\n\n"
                f"{preview_text}\n\n"
                "Сохранить этот шаблон?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Сохранить", callback_data="save_template"),
                        InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_template")
                    ],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_template")]
                ])
            )
        
        await state.set_state(DailyPostStates.creating_custom_template)
        
    except Exception as e:
        logger.error("Ошибка обработки текста шаблона: {}", str(e))
        await message.answer("❌ Ошибка обработки шаблона")



async def _extract_formatted_text_from_message(message: Message) -> str:
    """
    Извлечь отформатированный текст из сообщения, используя встроенные возможности aiogram
    
    Args:
        message: Сообщение aiogram
        
    Returns:
        Текст с Markdown разметкой
    """
    try:
        # Используем встроенный атрибут aiogram для Markdown
        if message.text:
            # Для обычного текста используем md_text
            result = message.md_text or message.text
        elif message.caption:
            # Для caption строим из entities
            if message.caption_entities:
                # Используем Text object для правильного извлечения
                from aiogram.utils.formatting import Text
                # Применяем entities к тексту - пока возвращаем просто caption
                result = message.caption
            else:
                result = message.caption
        else:
            result = ""
        
        logger.debug("Извлечен форматированный текст: '{}'", result[:100])
        return result
        
    except Exception as e:
        logger.error("Ошибка извлечения форматированного текста: {}", str(e))
        # Возвращаем сырой текст в случае ошибки
        return message.text or message.caption or ""


@router.callback_query(lambda c: c.data == "save_template", DailyPostStates.creating_custom_template)
async def save_custom_template(callback: CallbackQuery, state: FSMContext):
    """Сохранить пользовательский шаблон"""
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        template_name = data.get('template_name', '')
        template_text = data.get('template_text', '')  # Используем сырой текст
        
        if not template_name or not template_text:
            await callback.answer("❌ Данные шаблона потеряны", show_alert=True)
            await state.clear()
            return
        
        # Получаем данные о фото из состояния
        has_photo = data.get('has_photo', False)
        photo_info = data.get('photo_info', None)
        
        # Сохраняем шаблон с сырым текстом
        template_manager = get_template_manager()
        success = await template_manager.add_custom_template(
            template_name, 
            template_text,  # Сохраняем сырой текст для корректных переменных
            f"Создано {datetime.now().strftime('%d.%m.%Y в %H:%M')}",
            photo_info
        )
        
        if success:
            success_text = f"✅ **Шаблон '{template_name}' успешно создан!**\n\n" \
                          "Теперь вы можете:\n" \
                          "• Использовать его в ежедневных постах\n" \
                          "• Создать пост с этим шаблоном прямо сейчас\n" \
                          "• Настроить автоматическое использование\n\n" \
                          "💡 Управление шаблонами: /daily"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Создать пост сейчас", callback_data=f"test_template_{template_name}")],
                [InlineKeyboardButton(text="🔙 К настройкам", callback_data="daily_refresh")]
            ])
            
            # Безопасное редактирование сообщения
            try:
                if callback.message.photo:
                    # Если сообщение с фото - редактируем caption
                    await callback.message.edit_caption(
                        caption=success_text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                else:
                    # Если текстовое сообщение - редактируем текст
                    await callback.message.edit_text(
                        text=success_text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
            except Exception as edit_error:
                # Если редактирование не удалось - отправляем новое сообщение
                logger.debug("Не удалось отредактировать сообщение: {}, отправляем новое", str(edit_error))
                await callback.message.answer(
                    text=success_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            
            logger.info("Пользователь {} создал шаблон: {}", callback.from_user.id, template_name)
        else:
            await callback.answer("❌ Ошибка сохранения шаблона", show_alert=True)
        
        await state.clear()
        
    except Exception as e:
        logger.error("Ошибка сохранения шаблона: {}", str(e))
        await callback.answer("❌ Ошибка сохранения", show_alert=True)


@router.callback_query(lambda c: c.data == "edit_template", DailyPostStates.creating_custom_template)
async def edit_template_text(callback: CallbackQuery, state: FSMContext):
    """Редактировать текст шаблона"""
    try:
        await callback.message.edit_text(
            "✏️ **Редактирование шаблона**\n\n"
            "Отправьте **новый пост** с исправленным текстом:\n\n"
            "**🎨 Не забудьте:**\n"
            "• Применить форматирование через Telegram\n"
            "• Добавить переменные: `{BTC}`, `{MARKET_CAP}` и т.д.\n"
            "• Можно приложить фото к сообщению\n\n"
            "💡 Выделите текст → **жирный/курсив/подчеркнутый**",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_template")]
            ]),
            parse_mode="Markdown"
        )
        
        await state.set_state(DailyPostStates.entering_template_text)
        
    except Exception as e:
        logger.error("Ошибка редактирования шаблона: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data == "cancel_template")
async def cancel_template_creation(callback: CallbackQuery, state: FSMContext):
    """Отменить создание шаблона"""
    try:
        await state.clear()
        
        await callback.message.edit_text(
            "❌ **Создание шаблона отменено**\n\n"
            "Возвращаемся к настройкам ежедневных постов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К настройкам", callback_data="daily_refresh")]
            ]),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error("Ошибка отмены создания шаблона: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


# ============================================================================
# НОВЫЕ ОБРАБОТЧИКИ ДЛЯ УПРАВЛЕНИЯ ШАБЛОНАМИ  
# ============================================================================

@router.callback_query(lambda c: c.data.startswith("manage_template_"))
async def manage_template_preview(callback: CallbackQuery):
    """Предпросмотр пользовательского шаблона с управлением"""
    try:
        template_name = callback.data.replace("manage_template_", "")
        # Используем новую правильную функцию
        await refresh_template_preview(callback, template_name)
        
    except Exception as e:
        logger.error("Ошибка предпросмотра шаблона: {}", str(e))
        await callback.answer("❌ Ошибка загрузки шаблона", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("view_template_"))
async def view_standard_template(callback: CallbackQuery):
    """Просмотр стандартного шаблона"""
    try:
        template_name = callback.data.replace("view_template_", "")
        
        template_manager = get_template_manager()
        template = await template_manager.get_template(template_name)
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        # Получаем превью с переменными
        from src.scheduler.coingecko import get_template_variables
        try:
            variables = await get_template_variables()
            preview = template.template
            
            # Заменяем несколько основных переменных для превью
            for var, value in list(variables.items())[:5]:  # Первые 5 переменных
                preview = preview.replace(f"{{{var}}}", str(value))
            
        except Exception as e:
            logger.warning("Не удалось получить переменные для превью: {}", str(e))
            preview = template.template
        
        # Обрезаем превью если слишком длинный
        if len(preview) > 800:
            preview = preview[:800] + "..."
        
        text = f"📋 <b>Стандартный шаблон {template_name}</b>\n\n"
        text += f"📝 <b>Описание:</b> {template.description}\n"
        text += f"📊 <b>Тип:</b> Стандартный (встроенный)\n"
        text += f"📏 <b>Длина:</b> {len(template.template)} символов\n\n"
        
        # Экранируем HTML символы в предпросмотре
        from src.utils.html_formatter import safe_html_message
        escaped_preview = safe_html_message(preview)
        text += f"👀 <b>Предпросмотр:</b>\n\n<pre>{escaped_preview}</pre>"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Создать пост", callback_data=f"test_template_{template_name}")],
            [InlineKeyboardButton(text="📋 Копировать как основу", callback_data=f"copy_template_{template_name}")],
            [InlineKeyboardButton(text="🔙 К списку шаблонов", callback_data="daily_templates")]
        ])
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info("Показан стандартный шаблон '{}' пользователю {}", template_name, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка просмотра стандартного шаблона: {}", str(e))
        await callback.answer("❌ Ошибка загрузки шаблона", show_alert=True)




@router.callback_query(lambda c: c.data == "daily_pin_toggle")
async def toggle_pin_posts(callback: CallbackQuery):
    """Переключение закрепления постов"""
    try:
        from src.database.crud.setting import get_setting_crud
        setting_crud = get_setting_crud()
        
        # Получаем текущее состояние
        current_setting = await setting_crud.get_setting("daily_post.pin_enabled")
        current_pin = current_setting and current_setting.lower() == 'true'
        
        # Переключаем состояние
        new_pin = not current_pin
        await setting_crud.set_setting("daily_post.pin_enabled", str(new_pin).lower())
        
        pin_icon = "📌" if new_pin else "📄"
        pin_status = "включено" if new_pin else "отключено"
        
        text = f"{pin_icon} **Закрепление постов {pin_status}**\n\n"
        
        if new_pin:
            text += "✅ Ежедневные посты будут автоматически закрепляться в канале\n\n"
            text += "💡 **Что это значит:**\n"
            text += "• Пост останется вверху канала\n"
            text += "• Привлечет больше внимания\n"
            text += "• Предыдущий закрепленный пост будет откреплен"
        else:
            text += "❌ Ежедневные посты не будут закрепляться\n\n"
            text += "💡 **Что это значит:**\n"
            text += "• Посты публикуются обычным способом\n"
            text += "• Не влияют на другие закрепленные сообщения\n"
            text += "• Подходит для каналов с активной публикацией"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"📌 {'Отключить' if new_pin else 'Включить'} закрепление",
                callback_data="daily_pin_toggle"
            )],
            [InlineKeyboardButton(text="🔙 К управлению шаблонами", callback_data="daily_templates")]
        ])
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        logger.info("Закрепление постов {} пользователем {}", pin_status, callback.from_user.id)
        await callback.answer(f"✅ Закрепление {pin_status}!")
        
    except Exception as e:
        logger.error("Ошибка переключения закрепления: {}", str(e))
        await callback.answer("❌ Ошибка изменения настройки", show_alert=True)


# ============================================================================
# ОБРАБОТЧИКИ ВРЕМЕНИ ПУБЛИКАЦИИ
# ============================================================================

@router.callback_query(lambda c: c.data.startswith("set_time_"))
async def set_specific_time(callback: CallbackQuery):
    """Установить конкретное время публикации"""
    try:
        time_str = callback.data.replace("set_time_", "")
        
        if time_str == "custom":
            # Переход к ручному вводу времени
            await callback.message.edit_text(
                "⏰ **Введите время вручную**\n\n"
                "📋 Введите время в формате **HH:MM**\n"
                "Например: `10:30`, `07:15`, `14:00`\n\n"
                "⚠️ Время указывается в часовом поясе **UTC+3**\n"
                "💡 Рекомендуется: 08:00 - 12:00",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К шаблонам", callback_data="daily_templates")]
                ]),
                parse_mode="Markdown"
            )
            
            # Здесь можно добавить FSM для ввода времени
            return
        
        # Валидация времени
        try:
            hour, minute = time_str.split(":")
            hour_int = int(hour)
            minute_int = int(minute)
            
            if not (0 <= hour_int <= 23 and 0 <= minute_int <= 59):
                raise ValueError("Неверный формат времени")
                
        except ValueError:
            await callback.answer("❌ Неверный формат времени", show_alert=True)
            return
        
        # Сохраняем время в настройки
        from src.database.crud.setting import get_setting_crud
        setting_crud = get_setting_crud()
        
        await setting_crud.set_setting("daily_post.time", f'"{time_str}"')
        
        # Определяем эмодзи для времени
        hour_int = int(hour)
        if 6 <= hour_int < 9:
            time_icon = "🌅"
            time_desc = "Раннее утро"
        elif 9 <= hour_int < 12:
            time_icon = "🌞"
            time_desc = "Утро"
        elif 12 <= hour_int < 15:
            time_icon = "☀️"
            time_desc = "День"
        elif 15 <= hour_int < 18:
            time_icon = "🌤"
            time_desc = "День"
        elif 18 <= hour_int < 21:
            time_icon = "🌆"
            time_desc = "Вечер"
        else:
            time_icon = "🌙"
            time_desc = "Ночь"
        
        text = f"{time_icon} **Время публикации установлено!**\n\n"
        text += f"⏰ **Новое время:** {time_str} (UTC+3)\n"
        text += f"📅 **Описание:** {time_desc}\n\n"
        text += f"✅ Ежедневные посты теперь будут публиковаться в **{time_str}** по московскому времени\n\n"
        text += f"💡 **Следующая публикация:** завтра в {time_str}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📌 Настроить закрепление", callback_data="daily_pin_toggle")],
            [InlineKeyboardButton(text="🔙 К управлению шаблонами", callback_data="daily_templates")]
        ])
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        logger.info("Время публикации установлено на {} пользователем {}", time_str, callback.from_user.id)
        await callback.answer(f"✅ Время установлено: {time_str}")
        
    except Exception as e:
        logger.error("Ошибка установки времени: {}", str(e))
        await callback.answer("❌ Ошибка установки времени", show_alert=True)


# ============================================================================
# ОБРАБОТЧИКИ УДАЛЕНИЯ И РЕДАКТИРОВАНИЯ ШАБЛОНОВ
# ============================================================================

@router.callback_query(lambda c: c.data.startswith("delete_template_"))
async def delete_template_confirm(callback: CallbackQuery):
    """Подтверждение удаления шаблона"""
    try:
        template_name = callback.data.replace("delete_template_", "")
        
        text = f"🗑 **Удаление шаблона `{template_name}`**\n\n"
        text += f"⚠️ **Внимание!** Это действие нельзя отменить.\n\n"
        text += f"Шаблон будет удален из базы данных безвозвратно.\n"
        text += f"Все связанные данные также будут утеряны.\n\n"
        text += f"Вы уверены что хотите удалить шаблон **`{template_name}`**?"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"confirm_delete_{template_name}"),
                InlineKeyboardButton(text="❌ Нет, отмена", callback_data=f"manage_template_{template_name}")
            ],
            [InlineKeyboardButton(text="🔙 К списку шаблонов", callback_data="daily_templates")]
        ])
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error("Ошибка подтверждения удаления шаблона: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("confirm_delete_"))
async def delete_template_final(callback: CallbackQuery):
    """Окончательное удаление шаблона"""
    try:
        template_name = callback.data.replace("confirm_delete_", "")
        
        template_manager = get_template_manager()
        success = await template_manager.remove_custom_template(template_name)
        
        if success:
            text = f"✅ **Шаблон удален!**\n\n"
            text += f"🗑 Шаблон **`{template_name}`** успешно удален из базы данных.\n\n"
            text += f"💡 Теперь вы можете создать новый шаблон с таким же названием или выбрать другой."
            
            await callback.answer("✅ Шаблон удален!", show_alert=False)
        else:
            text = f"❌ **Ошибка удаления**\n\n"
            text += f"Не удалось удалить шаблон **`{template_name}`**.\n\n"
            text += f"Возможно, шаблон уже был удален или произошла ошибка базы данных."
            
            await callback.answer("❌ Ошибка удаления", show_alert=True)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К списку шаблонов", callback_data="daily_templates")]
        ])
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        logger.info("Пользователь {} {} шаблон '{}'", 
                   callback.from_user.id, 
                   "удалил" if success else "не смог удалить", 
                   template_name)
        
    except Exception as e:
        logger.error("Ошибка удаления шаблона: {}", str(e))
        await callback.answer("❌ Критическая ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("copy_template_"))
async def copy_template_as_base(callback: CallbackQuery, state: FSMContext):
    """Копировать шаблон как основу для нового"""
    try:
        template_name = callback.data.replace("copy_template_", "")
        
        template_manager = get_template_manager()
        template = await template_manager.get_template(template_name)
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        # Сохраняем данные шаблона в состояние для копирования
        await state.set_data({
            'copy_from': template_name,
            'template_text': template.template,
            'source_description': template.description
        })
        
        text = f"📋 **Копирование шаблона `{template_name}`**\n\n"
        text += f"📝 **Исходный шаблон:** {template.description}\n"
        text += f"📏 **Размер:** {len(template.template)} символов\n\n"
        text += f"💡 Введите **название** для нового шаблона:\n\n"
        text += f"⚠️ Название должно быть уникальным"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить копирование", callback_data=f"manage_template_{template_name}")]
        ])
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # Устанавливаем состояние ожидания названия для копии
        await state.set_state(DailyPostStates.entering_copy_name)
        
    except Exception as e:
        logger.error("Ошибка копирования шаблона: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("test_template_"))
async def test_template_now(callback: CallbackQuery, state: FSMContext):
    """Создать пост с выбранным шаблоном через полный флоу настроек"""
    try:
        template_name = callback.data.replace("test_template_", "")
        
        await callback.answer("⏳ Создаю пост из шаблона...")
        
        # Создаем пост из шаблона
        post_content = await create_daily_post_from_template(template_name)
        
        if not post_content:
            error_text = ("❌ **Ошибка создания поста!**\n\n"
                         f"Не удалось создать пост из шаблона '{template_name}'.")
            error_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К шаблону", callback_data=f"manage_template_{template_name}")]
            ])
            
            # Безопасное редактирование сообщения
            try:
                if callback.message.photo:
                    await callback.message.edit_caption(
                        caption=error_text,
                        reply_markup=error_keyboard,
                        parse_mode="Markdown"
                    )
                else:
                    await callback.message.edit_text(
                        text=error_text,
                        reply_markup=error_keyboard,
                        parse_mode="Markdown"
                    )
            except Exception:
                await callback.message.answer(
                    text=error_text,
                    reply_markup=error_keyboard,
                    parse_mode="Markdown"
                )
            return
        
        # Загружаем индивидуальные настройки шаблона через TemplateManager
        from src.scheduler.templates import get_template_manager
        template_manager = get_template_manager()
        
        try:
            template_pin = await template_manager.get_template_pin_enabled(template_name)
            template_time = await template_manager.get_template_auto_time(template_name)
            
            logger.debug("Настройки шаблона '{}' для создания поста: pin={}, time={}", 
                        template_name, template_pin, template_time)
        except Exception as e:
            logger.warning("Ошибка загрузки настроек шаблона: {}", str(e))
            template_pin = False
            template_time = None
        
        # Показываем превью поста с настройками шаблона
        if len(post_content) > 500:
            preview_text = post_content[:500] + "..."
        else:
            preview_text = post_content
        
        settings_text = f"📝 **Превью поста из шаблона '{template_name}':**\n\n{preview_text}\n\n"
        settings_text += "⚙️ **Настройки из шаблона:**\n"
        
        if template_time:
            settings_text += f"📅 Время: {template_time} (UTC+3)\n"
        else:
            settings_text += "📅 Время: Сейчас\n"
            
        settings_text += f"📌 Закрепить: {'Да' if template_pin else 'Нет'}\n\n"
        settings_text += "Настроить публикацию?"
        
        # Сохраняем данные в состояние для дальнейшей обработки
        await state.update_data(
            post_content=post_content, 
            template_name=template_name,
            pin_post=template_pin,
            publish_time=None  # Будет установлено если выберут отложенную публикацию
        )
        
        keyboard_buttons = []
        
        if template_time:
            # Если у шаблона есть свое время - предлагаем отложенную публикацию
            from datetime import datetime, timedelta
            import re
            
            try:
                # Парсим время шаблона
                if re.match(r'^\d{1,2}:\d{2}$', template_time):
                    hour, minute = map(int, template_time.split(':'))
                    
                    # Планируем на сегодня
                    publish_time = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
                    
                    # Если время уже прошло, планируем на завтра
                    if publish_time <= datetime.now():
                        publish_time += timedelta(days=1)
                    
                    await state.update_data(publish_time=publish_time)
                    
                    time_str = publish_time.strftime("%d.%m.%Y %H:%M")
                    keyboard_buttons.append([
                        InlineKeyboardButton(text=f"⏰ В {template_time}", callback_data="save_scheduled_post"),
                        InlineKeyboardButton(text="📤 Сейчас", callback_data="publish_now")
                    ])
                else:
                    # Неверный формат времени в шаблоне
                    keyboard_buttons.append([
                        InlineKeyboardButton(text="📤 Сейчас", callback_data="publish_now"),
                        InlineKeyboardButton(text="⏰ Настроить время", callback_data="setup_publish_time")
                    ])
            except:
                # Ошибка парсинга времени
                keyboard_buttons.append([
                    InlineKeyboardButton(text="📤 Сейчас", callback_data="publish_now"),
                    InlineKeyboardButton(text="⏰ Настроить время", callback_data="setup_publish_time")
                ])
        else:
            # У шаблона нет своего времени - обычные опции
            keyboard_buttons.append([
                InlineKeyboardButton(text="📤 Сейчас", callback_data="publish_now"),
                InlineKeyboardButton(text="⏰ Настроить время", callback_data="setup_publish_time")
            ])
        
        keyboard_buttons.extend([
            [
                InlineKeyboardButton(
                    text=f"📌 {'Не закреплять' if template_pin else 'Закрепить пост'}", 
                    callback_data="toggle_pin"
                ),
                InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_post_content")
            ],
            [
                InlineKeyboardButton(text="🔙 К шаблону", callback_data=f"manage_template_{template_name}")
            ]
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        # Безопасное редактирование сообщения
        try:
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=settings_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await callback.message.edit_text(
                    text=settings_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
        except Exception as edit_error:
            logger.debug("Не удалось отредактировать сообщение: {}, отправляем новое", str(edit_error))
            await callback.message.answer(
                text=settings_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        
        # Устанавливаем состояние настройки поста
        await state.set_state(DailyPostStates.configuring_post)
        
        logger.info("Пользователь {} создает пост из шаблона '{}'", callback.from_user.id, template_name)
        
    except Exception as e:
        logger.error("Ошибка создания поста из шаблона: {}", str(e))
        await callback.answer("❌ Ошибка создания поста", show_alert=True)


# ============================================================================ 
# ОБРАБОТЧИКИ РЕДАКТИРОВАНИЯ ШАБЛОНОВ
# ============================================================================

@router.callback_query(lambda c: c.data.startswith("edit_template_"))
async def edit_template_start(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование пользовательского шаблона"""
    try:
        template_name = callback.data.replace("edit_template_", "")
        
        template_manager = get_template_manager()
        template = await template_manager.get_template(template_name)
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        # Все шаблоны теперь пользовательские и редактируемые
        
        # Сохраняем данные шаблона в состояние
        await state.set_data({
            'editing_template_name': template_name,
            'original_text': template.template,
            'original_description': template.description
        })
        
        text = f"✏️ **Редактирование шаблона `{template_name}`**\n\n"
        text += f"📝 **Текущее описание:** {template.description or 'Без описания'}\n"
        text += f"📏 **Размер:** {len(template.template)} символов\n\n"
        text += f"**Шаг 1:** Введите новое название шаблона\n"
        text += f"Или отправьте `/skip` чтобы оставить текущее название: `{template_name}`"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить редактирование", callback_data=f"manage_template_{template_name}")]
        ])
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await state.set_state(DailyPostStates.editing_template_name)
        
    except Exception as e:
        logger.error("Ошибка начала редактирования шаблона: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.message(DailyPostStates.editing_template_name)
async def process_edit_template_name(message: Message, state: FSMContext):
    """Обработка нового названия при редактировании"""
    try:
        data = await state.get_data()
        old_name = data.get('editing_template_name', '')
        
        if message.text and message.text.strip() == '/skip':
            # Пропускаем изменение названия
            new_name = old_name
        else:
            new_name = message.text.strip() if message.text else ''
            
            if not new_name:
                await message.answer(
                    "❌ Название не может быть пустым!\n"
                    "Введите новое название или `/skip` для пропуска:"
                )
                return
            
            if len(new_name) < 2 or len(new_name) > 50:
                await message.answer(
                    "❌ Название должно быть от 2 до 50 символов!\n"
                    "Введите другое название или `/skip`:"
                )
                return
            
            # Если название изменилось, проверяем уникальность
            if new_name != old_name:
                template_manager = get_template_manager()
                existing = await template_manager.get_template(new_name)
                
                if existing:
                    await message.answer(
                        f"❌ Шаблон с названием **`{new_name}`** уже существует!\n"
                        "Выберите другое название или `/skip`:",
                        parse_mode="Markdown"
                    )
                    return
        
        # Сохраняем новое название
        await state.update_data(new_template_name=new_name)
        
        # Показываем текущий шаблон для редактирования
        original_text = data.get('original_text', '')
        
        if len(original_text) > 3000:
            preview_text = original_text[:3000] + "..."
        else:
            preview_text = original_text
        
        name_change_text = ""
        if new_name != old_name:
            name_change_text = f"\n✅ **Новое название:** `{new_name}`"
        
        text = f"✏️ **Редактирование шаблона**{name_change_text}\n\n"
        text += f"📋 **Шаг 2:** Создайте новый пост с обновленным содержимым\n\n"
        text += f"**Текущий шаблон:**\n"
        text += f"```\n{preview_text}\n```\n\n"
        text += f"**Отправьте новый пост:**\n"
        text += f"• Примените **форматирование** через Telegram\n"
        text += f"• Добавьте переменные: `{{BTC}}`, `{{MARKET_CAP}}` и т.д.\n"
        text += f"• Можете приложить **фото**"
        
        await message.answer(
            text,
            parse_mode="Markdown"
        )
        
        await state.set_state(DailyPostStates.editing_template_text)
        
    except Exception as e:
        logger.error("Ошибка обработки названия при редактировании: {}", str(e))
        await message.answer("❌ Ошибка обработки названия")


@router.message(DailyPostStates.editing_template_text)
async def process_edit_template_text(message: Message, state: FSMContext):
    """Обработка нового текста шаблона"""
    try:
        # Извлекаем текст
        new_text = message.text or message.caption or ""
        
        if not new_text.strip():
            await message.answer(
                "❌ **Текст шаблона не может быть пустым!**\n\n"
                "Отправьте сообщение с текстом или фото с подписью.",
                parse_mode="Markdown"
            )
            return
        
        if len(new_text) > 4000:
            await message.answer(
                "❌ Текст слишком длинный! Максимум 4000 символов.\n"
                "Сократите шаблон и попробуйте еще раз:"
            )
            return
        
        data = await state.get_data()
        old_name = data.get('editing_template_name', '')
        new_name = data.get('new_template_name', old_name)
        
        # Получаем форматированный текст
        formatted_text = await _extract_formatted_text_from_message(message)
        
        # Информация о фото
        photo_info = None
        if message.photo:
            photo = message.photo[-1]
            photo_info = {
                'file_id': photo.file_id,
                'width': photo.width,
                'height': photo.height,
                'file_size': photo.file_size
            }
        
        # Создаем превью с переменными
        try:
            from src.scheduler.coingecko import get_template_variables, apply_template_variables
            variables = await get_template_variables()
            # Применяем переменные к сырому тексту
            preview_text = apply_template_variables(new_text, variables)
            
            if len(preview_text) > 800:
                preview_text = preview_text[:800] + "..."
                
        except Exception as e:
            logger.warning("Ошибка создания превью: {}", str(e))
            preview_text = new_text[:400] + "..." if len(new_text) > 400 else new_text
        
        # Сохраняем новые данные
        await state.update_data(
            new_template_text=new_text,
            new_formatted_text=formatted_text,
            new_photo_info=photo_info,
            has_photo=bool(message.photo)
        )
        
        # Показываем превью
        changes_text = ""
        if new_name != old_name:
            changes_text += f"📝 **Название:** `{old_name}` → `{new_name}`\n"
        changes_text += f"📏 **Размер:** {len(new_text)} символов\n"
        if message.photo:
            changes_text += f"📷 **С фото:** {photo.width}x{photo.height}\n"
        changes_text += "\n"
        
        confirm_text = f"✅ **Предпросмотр изменений:**\n\n{changes_text}{preview_text}\n\n**Сохранить изменения?**"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить изменения", callback_data="save_edit_template"),
                InlineKeyboardButton(text="✏️ Изменить текст", callback_data="edit_template_text_again")
            ],
            [InlineKeyboardButton(text="❌ Отменить редактирование", callback_data=f"manage_template_{old_name}")]
        ])
        
        try:
            if message.photo and photo_info:
                await message.answer_photo(
                    photo=photo_info['file_id'],
                    caption=confirm_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    confirm_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
        except Exception:
            # Fallback без форматирования
            await message.answer(
                f"✅ Предпросмотр изменений:\n\n{preview_text}\n\nСохранить изменения?",
                reply_markup=keyboard
            )
        
    except Exception as e:
        logger.error("Ошибка обработки текста при редактировании: {}", str(e))
        await message.answer("❌ Ошибка обработки текста")


@router.callback_query(lambda c: c.data == "save_edit_template")
async def save_edited_template(callback: CallbackQuery, state: FSMContext):
    """Сохранить отредактированный шаблон"""
    try:
        data = await state.get_data()
        old_name = data.get('editing_template_name', '')
        new_name = data.get('new_template_name', old_name)
        new_text = data.get('new_template_text', '')  # Используем сырой текст
        photo_info = data.get('new_photo_info')
        
        if not old_name or not new_text:
            await callback.answer("❌ Данные редактирования потеряны", show_alert=True)
            await state.clear()
            return
        
        template_manager = get_template_manager()
        
        # Для любых изменений удаляем старый шаблон и создаем новый
        # (поскольку нет специального метода update_custom_template)
        
        # Удаляем старый шаблон
        await template_manager.remove_custom_template(old_name)
        
        # Создаем новый с обновленными данными
        success = await template_manager.add_custom_template(
            new_name,
            new_text,  # Сохраняем сырой текст для корректных переменных
            f"Отредактирован {datetime.now().strftime('%d.%m.%Y в %H:%M')}",
            photo_info
        )
        
        if success:
            text = f"✅ **Шаблон успешно отредактирован!**\n\n"
            text += f"📋 **Шаблон:** `{new_name}`\n"
            text += f"📏 **Размер:** {len(new_text)} символов\n"
            
            if new_name != old_name:
                text += f"📝 **Название изменено:** `{old_name}` → `{new_name}`\n"
            
            text += f"\n💡 Изменения сохранены и готовы к использованию!"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👀 Посмотреть шаблон", callback_data=f"manage_template_{new_name}")],
                [InlineKeyboardButton(text="🚀 Создать пост", callback_data=f"test_template_{new_name}")],
                [InlineKeyboardButton(text="🔙 К списку шаблонов", callback_data="daily_templates")]
            ])
            
            # Безопасное редактирование сообщения
            try:
                if callback.message.photo:
                    await callback.message.edit_caption(
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                else:
                    await callback.message.edit_text(
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
            except Exception:
                await callback.message.answer(
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            
            logger.info("Пользователь {} отредактировал шаблон '{}' → '{}'", 
                       callback.from_user.id, old_name, new_name)
            await callback.answer("✅ Шаблон сохранен!")
        else:
            await callback.answer("❌ Ошибка сохранения изменений", show_alert=True)
        
        await state.clear()
        
    except Exception as e:
        logger.error("Ошибка сохранения отредактированного шаблона: {}", str(e))
        await callback.answer("❌ Ошибка сохранения", show_alert=True)


@router.callback_query(lambda c: c.data == "edit_template_text_again")
async def edit_template_text_again(callback: CallbackQuery):
    """Повторное редактирование текста шаблона"""
    try:
        await callback.message.edit_text(
            "✏️ **Повторное редактирование**\n\n"
            "Отправьте **новый пост** с исправленным текстом:\n\n"
            "**🎨 Не забудьте:**\n"
            "• Применить форматирование через Telegram\n"
            "• Добавить переменные: `{BTC}`, `{MARKET_CAP}` и т.д.\n"
            "• Можно приложить фото к сообщению",
            parse_mode="Markdown"
        )
        
        # Состояние остается editing_template_text
        
    except Exception as e:
        logger.error("Ошибка повторного редактирования: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


# ============================================================================
# ОБРАБОТЧИКИ ИНДИВИДУАЛЬНЫХ НАСТРОЕК ШАБЛОНОВ  
# ============================================================================

@router.callback_query(lambda c: c.data.startswith("toggle_active_"))
async def toggle_template_active(callback: CallbackQuery):
    """Переключить активность шаблона"""
    try:
        template_name = callback.data.replace("toggle_active_", "")
        
        template_manager = get_template_manager()
        template = await template_manager.get_template(template_name)
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        # Получаем текущую активность из БД через TemplateManager
        current_active = await template_manager.is_template_active(template_name)
        new_active = not current_active
        
        # Сохраняем новое состояние в БД
        success = await template_manager.set_template_active(template_name, new_active)
        
        if not success:
            await callback.answer("❌ Ошибка изменения статуса", show_alert=True)
            return
        
        status_text = "активирован" if new_active else "деактивирован"
        status_icon = "✅" if new_active else "💤"
        
        await callback.answer(f"{status_icon} Шаблон {status_text}!")
        
        # Обновляем интерфейс
        await refresh_template_preview(callback, template_name)
        
        logger.info("Пользователь {} {} шаблон '{}'", 
                   callback.from_user.id, status_text, template_name)
        
    except Exception as e:
        logger.error("Ошибка переключения активности шаблона: {}", str(e))
        await callback.answer("❌ Ошибка изменения статуса", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("toggle_pin_"))
async def toggle_template_pin(callback: CallbackQuery):
    """Переключить закрепление для шаблона"""
    try:
        template_name = callback.data.replace("toggle_pin_", "")
        
        template_manager = get_template_manager()
        template = await template_manager.get_template(template_name)
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        # Получаем текущее состояние закрепления из БД через TemplateManager
        current_pin = await template_manager.get_template_pin_enabled(template_name)
        new_pin = not current_pin
        
        # Сохраняем новое состояние в БД
        success = await template_manager.set_template_pin_enabled(template_name, new_pin)
        
        if not success:
            await callback.answer("❌ Ошибка изменения закрепления", show_alert=True)
            return
        
        pin_text = "включено" if new_pin else "отключено"
        pin_icon = "📌" if new_pin else "📄"
        
        await callback.answer(f"{pin_icon} Закрепление {pin_text}!")
        
        # Обновляем интерфейс
        await refresh_template_preview(callback, template_name)
        
        logger.info("Пользователь {} {} закрепление для шаблона '{}'", 
                   callback.from_user.id, "включил" if new_pin else "отключил", template_name)
        
    except Exception as e:
        logger.error("Ошибка переключения закрепления шаблона: {}", str(e))
        await callback.answer("❌ Ошибка изменения закрепления", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("set_template_time_"))
async def set_template_time(callback: CallbackQuery):
    """Настроить время автопубликации для шаблона"""
    try:
        template_name = callback.data.replace("set_template_time_", "")
        
        template_manager = get_template_manager()
        template = await template_manager.get_template(template_name)
        
        if not template:
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return
        
        current_time = await template_manager.get_template_auto_time(template_name)
        current_time_text = current_time if current_time else "не установлено"
        
        text = f"⏰ <b>Время публикации для шаблона {template_name}</b>\n\n"
        text += f"📅 <b>Текущее время:</b> {current_time_text}\n\n"
        text += f"🎯 <b>Выберите новое время публикации:</b>\n"
        text += f"Время указывается в часовом поясе <b>UTC+3</b>"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🌅 08:00", callback_data=f"set_tmpl_time_{template_name}_08:00"),
                InlineKeyboardButton(text="🌞 09:00", callback_data=f"set_tmpl_time_{template_name}_09:00"),
                InlineKeyboardButton(text="☀️ 10:00", callback_data=f"set_tmpl_time_{template_name}_10:00")
            ],
            [
                InlineKeyboardButton(text="🌤 11:00", callback_data=f"set_tmpl_time_{template_name}_11:00"),
                InlineKeyboardButton(text="🌝 12:00", callback_data=f"set_tmpl_time_{template_name}_12:00"),
                InlineKeyboardButton(text="🌆 18:00", callback_data=f"set_tmpl_time_{template_name}_18:00")
            ],
            [
                InlineKeyboardButton(text="❌ Убрать время", callback_data=f"set_tmpl_time_{template_name}_reset"),
                InlineKeyboardButton(text="⏰ Свое время", callback_data=f"set_tmpl_time_{template_name}_custom")
            ],
            [InlineKeyboardButton(text="🔙 К шаблону", callback_data=f"manage_template_{template_name}")]
        ])
        
        await safe_edit_message(callback, text, keyboard, "HTML")
        
    except Exception as e:
        logger.error("Ошибка настройки времени шаблона: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(lambda c: c.data.startswith("set_tmpl_time_"))
async def process_template_time(callback: CallbackQuery, state: FSMContext):
    """Обработать выбор времени для шаблона"""
    try:
        # Парсим callback_data: set_tmpl_time_{template_name}_{time}
        data_without_prefix = callback.data.replace("set_tmpl_time_", "")
        parts = data_without_prefix.rsplit("_", 1)
        if len(parts) != 2:
            await callback.answer("❌ Ошибка парсинга данных", show_alert=True)
            return
            
        template_name, time_action = parts
        
        if time_action == "reset":
            # Убираем время автопубликации
            new_time = None
            time_text = "время убрано"
        elif time_action == "custom":
            # Запускаем FSM для ввода кастомного времени
            await start_custom_time_input(callback, template_name, state)
            return
        else:
            # Устанавливаем конкретное время
            new_time = time_action
            time_text = time_action
        
        # Обновляем в БД через TemplateManager
        from src.scheduler.templates import get_template_manager
        template_manager = get_template_manager()
        
        success = await template_manager.set_template_auto_time(template_name, new_time)
        
        if not success:
            await callback.answer("❌ Ошибка установки времени", show_alert=True)
            return
        
        await callback.answer(f"⏰ Время установлено: {time_text}")
        
        # Возвращаемся к управлению шаблоном
        await refresh_template_preview(callback, template_name)
        
        logger.info("Пользователь {} установил время '{}' для шаблона '{}'", 
                   callback.from_user.id, time_text, template_name)
        
    except Exception as e:
        logger.error("Ошибка установки времени шаблона: {}", str(e))
        await callback.answer("❌ Ошибка установки времени", show_alert=True)


async def start_custom_time_input(callback: CallbackQuery, template_name: str, state: FSMContext):
    """Начать ввод кастомного времени для шаблона"""
    try:
        # Создаем глобальную переменную для передачи template_name
        # (временное решение для простоты)
        global _current_template_name
        _current_template_name = template_name
        
        # КРИТИЧНО: Устанавливаем FSM состояние для ввода времени
        await state.set_state(DailyPostStates.setting_template_time)
        logger.info("Установлено FSM состояние setting_template_time для пользователя {}", callback.from_user.id)
        
        await safe_edit_message(
            callback,
            f"⏰ **Настройка времени для шаблона '{template_name}'**\n\n"
            f"Введите время в формате **HH:MM**\n\n"
            f"Примеры:\n"
            f"• `09:30` - каждый день в 09:30\n"
            f"• `14:15` - каждый день в 14:15\n"
            f"• `21:00` - каждый день в 21:00\n\n"
            f"⏰ Время указывается в UTC+3\n"
            f"📅 Шаблон будет автоматически публиковаться каждый день в это время",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"template_time_{template_name}")]
            ])
        )
        
        logger.info("Начат ввод кастомного времени для шаблона '{}' пользователем {}", 
                   template_name, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка запуска ввода кастомного времени: {}", str(e))
        await callback.answer("❌ Ошибка", show_alert=True)


# Глобальная переменная для текущего template_name (временное решение)
_current_template_name = None


# ============================================================================
# ОБРАБОТЧИКИ FSM СОСТОЯНИЙ
# ============================================================================

@router.message(DailyPostStates.setting_template_time)
async def process_template_custom_time(message: Message, state: FSMContext):
    """Обработка ввода кастомного времени для шаблона"""
    global _current_template_name
    
    try:
        time_input = message.text.strip()
        
        # Парсим введенное время
        import re
        
        # Удаляем сообщение пользователя
        try:
            await message.delete()
        except:
            pass
        
        # Проверяем формат HH:MM
        if not re.match(r'^\d{1,2}:\d{2}$', time_input):
            await message.answer(
                f"❌ **Ошибка формата времени!**\n\n"
                f"Используйте формат **HH:MM**\n"
                f"Примеры: 09:30, 14:15, 21:00",
                parse_mode="Markdown"
            )
            return
        
        hour, minute = map(int, time_input.split(':'))
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            await message.answer(
                f"❌ **Неверное время!**\n\n"
                f"Часы: 0-23, минуты: 0-59\n"
                f"Попробуйте еще раз",
                parse_mode="Markdown"
            )
            return
        
        # Получаем имя шаблона из глобальной переменной
        template_name = _current_template_name
        
        if not template_name:
            await message.answer("❌ Ошибка: не найдено имя шаблона")
            return
        
        # Обновляем в БД через TemplateManager
        from src.scheduler.templates import get_template_manager
        template_manager = get_template_manager()
        
        success = await template_manager.set_template_auto_time(template_name, time_input)
        
        if not success:
            await message.answer("❌ Ошибка сохранения времени в базе данных")
            return
        
        # Отправляем подтверждение
        confirmation_msg = await message.answer(
            f"✅ **Время установлено!**\n\n"
            f"🏷 Шаблон: **{template_name}**\n"
            f"⏰ Время: **{time_input}** (UTC+3)\n"
            f"📅 Автопубликация: каждый день\n\n"
            f"Возвращаюсь к управлению шаблоном...",
            parse_mode="Markdown"
        )
        
        # Возвращаемся к управлению шаблоном через небольшую задержку
        import asyncio
        await asyncio.sleep(2)
        
        # Создаем поддельный callback для refresh_template_preview
        class FakeCallback:
            def __init__(self, message, user_id):
                self.message = confirmation_msg
                self.from_user = type('obj', (object,), {'id': user_id})
                self.data = None
            
            async def answer(self, *args, **kwargs):
                pass
        
        fake_callback = FakeCallback(confirmation_msg, message.from_user.id)
        await refresh_template_preview(fake_callback, template_name)
        
        # Очищаем глобальную переменную и FSM состояние
        _current_template_name = None
        await state.clear()
        
        logger.info("Пользователь {} установил кастомное время '{}' для шаблона '{}'", 
                   message.from_user.id, time_input, template_name)
        
    except Exception as e:
        logger.error("Ошибка обработки кастомного времени шаблона: {}", str(e))
        await message.answer("❌ Ошибка обработки времени")
        # Очищаем глобальную переменную и FSM состояние
        _current_template_name = None
        await state.clear()


@router.message(DailyPostStates.entering_copy_name)
async def process_copy_template_name(message: Message, state: FSMContext):
    """Обработка названия для копируемого шаблона"""
    try:
        new_name = message.text.strip()
        data = await state.get_data()
        
        if not new_name:
            await message.answer(
                "❌ Название не может быть пустым!\n"
                "Введите название для нового шаблона:"
            )
            return
        
        # Проверяем на допустимые символы
        if not new_name.replace('_', '').replace('-', '').isalnum():
            await message.answer(
                "❌ Название содержит недопустимые символы!\n"
                "Используйте только буквы, цифры, дефисы и подчеркивания.\n"
                "Введите другое название:"
            )
            return
        
        # Проверяем уникальность
        template_manager = get_template_manager()
        existing_template = await template_manager.get_template(new_name)
        
        if existing_template:
            await message.answer(
                f"❌ Шаблон с названием **`{new_name}`** уже существует!\n"
                "Выберите другое название:",
                parse_mode="Markdown"
            )
            return
        
        # Создаем копию шаблона
        source_template_text = data.get('template_text', '')
        source_description = data.get('source_description', '')
        copy_from = data.get('copy_from', '')
        
        new_description = f"Копия шаблона '{copy_from}'"
        if source_description:
            new_description += f" - {source_description}"
        
        success = await template_manager.add_custom_template(
            new_name,
            source_template_text,
            new_description
        )
        
        if success:
            await state.clear()
            
            text = f"✅ **Шаблон скопирован!**\n\n"
            text += f"📋 **Новый шаблон:** `{new_name}`\n"
            text += f"📝 **Описание:** {new_description}\n"
            text += f"📏 **Размер:** {len(source_template_text)} символов\n\n"
            text += f"💡 Шаблон готов к использованию!"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👀 Посмотреть шаблон", callback_data=f"manage_template_{new_name}")],
                [InlineKeyboardButton(text="🚀 Создать пост", callback_data=f"test_template_{new_name}")],
                [InlineKeyboardButton(text="🔙 К списку шаблонов", callback_data="daily_templates")]
            ])
            
            await message.answer(
                text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
            logger.info("Пользователь {} скопировал шаблон '{}' как '{}'", 
                       message.from_user.id, copy_from, new_name)
        else:
            await message.answer(
                "❌ **Ошибка копирования**\n\n"
                "Не удалось создать копию шаблона.\n"
                "Попробуйте еще раз или обратитесь к администратору.",
                parse_mode="Markdown"
            )
            await state.clear()
        
    except Exception as e:
        logger.error("Ошибка копирования шаблона: {}", str(e))
        await message.answer("❌ Произошла ошибка при копировании шаблона")
        await state.clear()