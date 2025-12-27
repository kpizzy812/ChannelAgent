"""
Основные inline клавиатуры для бота
Клавиатуры главного меню и навигации
"""

from typing import Optional, List

# aiogram 3.x импорты
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Настройка логгера модуля
logger = logger.bind(module="bot_keyboards_inline")


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📺 Управление каналами",
                callback_data="channels_menu"
            )
        ],
        [
            InlineKeyboardButton(
                text="⚖️ Модерация постов",
                callback_data="moderation_menu"
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 Примеры постов",
                callback_data="examples_menu"
            )
        ],
        [
            InlineKeyboardButton(
                text="📊 Статус системы",
                callback_data="system_status"
            ),
            InlineKeyboardButton(
                text="📈 Статистика",
                callback_data="show_statistics"
            )
        ],
        [
            InlineKeyboardButton(
                text="⚙️ Настройки",
                callback_data="settings_menu"
            ),
            InlineKeyboardButton(
                text="❓ Помощь",
                callback_data="show_help"
            )
        ]
    ])
    
    return keyboard


def get_status_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура статуса системы"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔄 Обновить статус",
                callback_data="refresh_status"
            )
        ],
        [
            InlineKeyboardButton(
                text="🤖 UserBot",
                callback_data="userbot_status"
            ),
            InlineKeyboardButton(
                text="🧠 AI Модуль",
                callback_data="ai_status"
            )
        ],
        [
            InlineKeyboardButton(
                text="💾 База данных",
                callback_data="database_status"
            ),
            InlineKeyboardButton(
                text="📊 Мониторинг",
                callback_data="monitoring_status"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 Главное меню",
                callback_data="main_menu"
            )
        ]
    ])
    
    return keyboard


def get_channels_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню управления каналами"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📺 Список каналов",
                callback_data="list_channels"
            )
        ],
        [
            InlineKeyboardButton(
                text="➕ Добавить канал",
                callback_data="add_channel"
            ),
            InlineKeyboardButton(
                text="❌ Удалить канал",
                callback_data="remove_channel"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Проверить доступ",
                callback_data="check_channels_access"
            )
        ],
        [
            InlineKeyboardButton(
                text="⚙️ Настройки мониторинга",
                callback_data="monitoring_settings"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 Главное меню",
                callback_data="main_menu"
            )
        ]
    ])
    
    return keyboard


def get_moderation_menu_keyboard(pending_count: int = 0) -> InlineKeyboardMarkup:
    """Меню модерации постов"""
    
    pending_text = f"⏳ На модерации ({pending_count})" if pending_count > 0 else "⏳ На модерации"
    
    # Собираем клавиатуру динамически
    keyboard_rows = [
        [
            InlineKeyboardButton(
                text=pending_text,
                callback_data="pending_posts"
            )
        ],
        [
            InlineKeyboardButton(
                text="✅ Одобренные",
                callback_data="approved_posts"
            ),
            InlineKeyboardButton(
                text="❌ Отклоненные", 
                callback_data="rejected_posts"
            )
        ],
        [
            InlineKeyboardButton(
                text="📤 Опубликованные",
                callback_data="published_posts"
            ),
            InlineKeyboardButton(
                text="⏰ Запланированные",
                callback_data="scheduled_posts"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔍 Поиск по постам",
                callback_data="search_posts"
            )
        ]
    ]
    
    # Добавляем кнопку "Отклонить все" только если есть посты на модерации
    if pending_count > 0:
        keyboard_rows.append([
            InlineKeyboardButton(
                text="🗑️ Отклонить все",
                callback_data="reject_all_pending"
            )
        ])
    
    # Добавляем остальные кнопки
    keyboard_rows.extend([
        [
            InlineKeyboardButton(
                text="⚙️ Настройки модерации",
                callback_data="moderation_settings"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 Главное меню",
                callback_data="main_menu"
            )
        ]
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    return keyboard


def get_post_moderation_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """Клавиатура модерации конкретного поста"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📤 Запостить сейчас",
                callback_data=f"approve_post_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⏰ Запостить позже",
                callback_data=f"schedule_post_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Редактировать",
                callback_data=f"edit_post_{post_id}"
            ),
            InlineKeyboardButton(
                text="🖼️ Изменить фото",
                callback_data=f"edit_photo_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔍 AI анализ", 
                callback_data=f"ai_analysis_{post_id}"
            ),
            InlineKeyboardButton(
                text="📊 Рестайлинг",
                callback_data=f"restyle_post_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"reject_post_{post_id}"
            ),
            InlineKeyboardButton(
                text="🗑️ Удалить",
                callback_data=f"delete_post_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ К списку постов",
                callback_data="pending_posts"
            )
        ]
    ])
    
    return keyboard


def get_post_moderation_keyboard_with_preview(post_id: int) -> InlineKeyboardMarkup:
    """Клавиатура модерации поста с кнопкой 'Показать пост' для длинных постов"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📄 Показать пост",
                callback_data=f"show_post_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📤 Запостить сейчас",
                callback_data=f"approve_post_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⏰ Запостить позже",
                callback_data=f"schedule_post_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Редактировать",
                callback_data=f"edit_post_{post_id}"
            ),
            InlineKeyboardButton(
                text="🖼️ Изменить фото",
                callback_data=f"edit_photo_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔍 AI анализ", 
                callback_data=f"ai_analysis_{post_id}"
            ),
            InlineKeyboardButton(
                text="📊 Рестайлинг",
                callback_data=f"restyle_post_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"reject_post_{post_id}"
            ),
            InlineKeyboardButton(
                text="🗑️ Удалить",
                callback_data=f"delete_post_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ К списку постов",
                callback_data="pending_posts"
            )
        ]
    ])
    
    return keyboard


def get_settings_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню настроек"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🤖 AI Настройки",
                callback_data="ai_settings"
            ),
            InlineKeyboardButton(
                text="📺 Каналы",
                callback_data="channel_settings"
            )
        ],
        [
            InlineKeyboardButton(
                text="⏰ Расписание",
                callback_data="schedule_settings"
            ),
            InlineKeyboardButton(
                text="📊 Мониторинг",
                callback_data="monitor_settings"
            )
        ],
        [
            InlineKeyboardButton(
                text="💰 CoinGecko",
                callback_data="coingecko_settings"
            ),
            InlineKeyboardButton(
                text="📝 Примеры",
                callback_data="examples_settings"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Сбросить настройки",
                callback_data="reset_settings"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 Главное меню",
                callback_data="main_menu"
            )
        ]
    ])
    
    return keyboard


def get_confirmation_keyboard(
    action: str, 
    item_id: Optional[int] = None,
    yes_text: str = "✅ Да",
    no_text: str = "❌ Нет"
) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    
    yes_callback = f"confirm_{action}"
    no_callback = f"cancel_{action}"
    
    if item_id is not None:
        yes_callback += f"_{item_id}"
        no_callback += f"_{item_id}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=yes_text, callback_data=yes_callback),
            InlineKeyboardButton(text=no_text, callback_data=no_callback)
        ]
    ])
    
    return keyboard


def get_pagination_keyboard(
    current_page: int,
    total_pages: int,
    callback_prefix: str,
    per_page: int = 5
) -> List[InlineKeyboardButton]:
    """Создать кнопки пагинации"""
    
    buttons = []
    
    # Кнопка "Назад"
    if current_page > 1:
        buttons.append(
            InlineKeyboardButton(
                text="⬅️ Пред",
                callback_data=f"{callback_prefix}_page_{current_page - 1}"
            )
        )
    
    # Информация о странице
    buttons.append(
        InlineKeyboardButton(
            text=f"📄 {current_page}/{total_pages}",
            callback_data="current_page"
        )
    )
    
    # Кнопка "Вперед"
    if current_page < total_pages:
        buttons.append(
            InlineKeyboardButton(
                text="След ➡️", 
                callback_data=f"{callback_prefix}_page_{current_page + 1}"
            )
        )
    
    return buttons


def get_channel_list_keyboard(
    channels: List,
    page: int = 1,
    per_page: int = 5
) -> InlineKeyboardMarkup:
    """Клавиатура со списком каналов"""
    
    keyboard_rows = []
    
    # Кнопки каналов
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_channels = channels[start_idx:end_idx]
    
    for channel in page_channels:
        status_icon = "🟢" if channel.is_active else "🔴"
        channel_name = channel.title or channel.username or f"ID: {channel.channel_id}"
        
        button_text = f"{status_icon} {channel_name}"
        if channel.posts_processed > 0:
            button_text += f" ({channel.posts_processed})"
        
        keyboard_rows.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"channel_info_{channel.id}"
            )
        ])
    
    # Пагинация
    total_pages = (len(channels) + per_page - 1) // per_page
    if total_pages > 1:
        pagination_buttons = get_pagination_keyboard(page, total_pages, "channels")
        keyboard_rows.append(pagination_buttons)
    
    # Управляющие кнопки
    keyboard_rows.extend([
        [
            InlineKeyboardButton(
                text="➕ Добавить канал",
                callback_data="add_channel"
            ),
            InlineKeyboardButton(
                text="🔄 Обновить список",
                callback_data="refresh_channels"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ К управлению каналами",
                callback_data="channels_menu"
            )
        ]
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    return keyboard


def get_posts_list_keyboard(
    posts: List,
    status: str,
    page: int = 1,
    per_page: int = 3
) -> InlineKeyboardMarkup:
    """Клавиатура со списком постов"""
    
    keyboard_rows = []
    
    # Кнопки постов
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_posts = posts[start_idx:end_idx]
    
    for post in page_posts:
        # Иконка статуса
        status_icons = {
            "pending": "⏳",
            "approved": "✅", 
            "rejected": "❌",
            "published": "📤",
            "scheduled": "⏰"
        }
        
        status_icon = status_icons.get(post.status.value, "❓")
        
        # Превью текста
        preview = post.original_text[:30] + "..." if len(post.original_text) > 30 else post.original_text
        
        # Релевантность
        relevance_text = ""
        if post.relevance_score:
            relevance_text = f" ({post.relevance_score}/10)"
        
        button_text = f"{status_icon} {preview}{relevance_text}"
        
        keyboard_rows.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"view_post_{post.id}"
            )
        ])
    
    # Пагинация
    total_pages = (len(posts) + per_page - 1) // per_page
    if total_pages > 1:
        pagination_buttons = get_pagination_keyboard(page, total_pages, f"posts_{status}")
        keyboard_rows.append(pagination_buttons)
    
    # Управляющие кнопки
    keyboard_rows.extend([
        [
            InlineKeyboardButton(
                text="🔄 Обновить список",
                callback_data=f"refresh_{status}_posts"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ К модерации",
                callback_data="moderation_menu"
            )
        ]
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    return keyboard


def get_time_selection_keyboard(post_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора времени для отложенной публикации"""
    
    # Если post_id передан, добавляем его к callback_data
    post_suffix = f"_{post_id}" if post_id else ""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ Через 1 час", callback_data=f"schedule_1h{post_suffix}"),
            InlineKeyboardButton(text="⏰ Через 3 часа", callback_data=f"schedule_3h{post_suffix}")
        ],
        [
            InlineKeyboardButton(text="⏰ Через 6 часов", callback_data=f"schedule_6h{post_suffix}"),
            InlineKeyboardButton(text="⏰ Через 12 часов", callback_data=f"schedule_12h{post_suffix}")
        ],
        [
            InlineKeyboardButton(text="📅 Завтра в 9:00", callback_data=f"schedule_tomorrow{post_suffix}"),
            InlineKeyboardButton(text="📅 Завтра в 18:00", callback_data=f"schedule_evening{post_suffix}")
        ],
        [
            InlineKeyboardButton(text="📅 Выбрать время", callback_data=f"schedule_custom{post_suffix}")
        ],
        [
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_schedule{post_suffix}")
        ]
    ])
    
    return keyboard


def get_ai_analysis_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для AI анализа поста"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔍 Повторить анализ",
                callback_data=f"reanalyze_post_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📊 Изменить стиль",
                callback_data=f"change_style_{post_id}"
            ),
            InlineKeyboardButton(
                text="🎯 Изменить категорию",
                callback_data=f"change_category_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Рестайлинг",
                callback_data=f"restyle_post_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ К посту",
                callback_data=f"view_post_{post_id}"
            )
        ]
    ])
    
    return keyboard