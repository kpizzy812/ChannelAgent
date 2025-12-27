"""
Клавиатуры для управления примерами постов пользователя
Inline кнопки для добавления, просмотра и редактирования примеров стиля
"""

from typing import Optional, List

# aiogram 3.x импорты
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Настройка логгера модуля
logger = logger.bind(module="bot_keyboards_user_posts")


def get_user_posts_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню управления примерами постов"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="➕ Добавить текстом",
                callback_data="add_example_text"
            ),
            InlineKeyboardButton(
                text="🔗 Добавить ссылкой", 
                callback_data="add_example_link"
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 Управление примерами",
                callback_data="examples_list"
            ),
            InlineKeyboardButton(
                text="📊 Статистика",
                callback_data="examples_stats"
            )
        ],
        [
            InlineKeyboardButton(
                text="👁️ Просмотр примеров",
                callback_data="view_examples"
            ),
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data="refresh_examples"
            )
        ],
        [
            InlineKeyboardButton(
                text="⚙️ Настройки",
                callback_data="examples_settings"
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


def get_category_selection_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора категории для примера поста"""
    
    categories = [
        ("🚀 Криптовалюты", "category_crypto"),
        ("📊 Макроэкономика", "category_macro"),
        ("🌐 Web3", "category_web3"),
        ("✈️ Telegram", "category_telegram"),
        ("🎮 GameFi", "category_gamefi"),
        ("📌 Общее", "category_general")
    ]
    
    keyboard_rows = []
    
    # Создаем кнопки по 2 в ряд
    for i in range(0, len(categories), 2):
        row = []
        for j in range(2):
            if i + j < len(categories):
                text, callback_data = categories[i + j]
                row.append(InlineKeyboardButton(text=text, callback_data=callback_data))
        keyboard_rows.append(row)
    
    # Кнопка отмены
    keyboard_rows.append([
        InlineKeyboardButton(
            text="❌ Отменить",
            callback_data="cancel_example_adding"
        )
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    return keyboard


def get_quality_score_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора оценки качества (1-10)"""
    
    keyboard_rows = []
    
    # Создаем кнопки с оценками 1-10 по 5 в ряд
    for i in range(0, 10, 5):
        row = []
        for j in range(5):
            if i + j < 10:
                score = i + j + 1
                emoji = ""
                if score <= 3:
                    emoji = "🔴"  # Плохо
                elif score <= 6:
                    emoji = "🟡"  # Средне
                elif score <= 8:
                    emoji = "🟢"  # Хорошо
                else:
                    emoji = "🟣"  # Отлично
                
                row.append(InlineKeyboardButton(
                    text=f"{emoji} {score}",
                    callback_data=f"quality_{score}"
                ))
        keyboard_rows.append(row)
    
    # Кнопка отмены
    keyboard_rows.append([
        InlineKeyboardButton(
            text="❌ Отменить",
            callback_data="cancel_example_adding"
        )
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    return keyboard


def get_user_post_management_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """Клавиатура управления конкретным примером поста"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📝 Редактировать",
                callback_data=f"edit_example_{post_id}"
            ),
            InlineKeyboardButton(
                text="📋 Изменить категорию",
                callback_data=f"change_category_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⭐ Изменить оценку",
                callback_data=f"change_quality_{post_id}"
            ),
            InlineKeyboardButton(
                text="👁️ Превью",
                callback_data=f"preview_example_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="✅ Активировать" if post_id else "❌ Деактивировать",
                callback_data=f"toggle_active_{post_id}"
            ),
            InlineKeyboardButton(
                text="🗑️ Удалить",
                callback_data=f"delete_example_{post_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад к списку",
                callback_data="view_examples"
            )
        ]
    ])
    
    return keyboard



def get_examples_list_keyboard(examples: List, page: int = 1, per_page: int = 5) -> InlineKeyboardMarkup:
    """Клавиатура со списком примеров для управления"""
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_examples = examples[start_idx:end_idx]
    
    keyboard_rows = []
    
    # Кнопки для каждого примера
    for example in page_examples:
        category_emoji = {
            "crypto": "🚀", "macro": "📊", "web3": "🌐",
            "telegram": "✈️", "gamefi": "🎮", "general": "📌"
        }.get(example.category, "📌")
        
        # Сокращенный текст для кнопки
        preview = example.get_preview(30)
        button_text = f"{category_emoji} ID{example.id}: {preview}"
        
        keyboard_rows.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"view_example_{example.id}"
            )
        ])
    
    # Навигация по страницам
    nav_buttons = []
    total_pages = (len(examples) + per_page - 1) // per_page
    
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"examples_page_{page-1}"
        ))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(
            text="Вперед ➡️",
            callback_data=f"examples_page_{page+1}"
        ))
    
    if nav_buttons:
        keyboard_rows.append(nav_buttons)
    
    # Управляющие кнопки
    keyboard_rows.append([
        InlineKeyboardButton(
            text="🔄 Обновить",
            callback_data="refresh_examples_list"
        ),
        InlineKeyboardButton(
            text="🗑️ Очистить все",
            callback_data="clear_all_examples"
        )
    ])
    
    # Возврат к главному меню
    keyboard_rows.append([
        InlineKeyboardButton(
            text="📋 К примерам",
            callback_data="view_examples"
        ),
        InlineKeyboardButton(
            text="🏠 Главное меню",
            callback_data="main_menu"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def get_example_management_keyboard(example_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для управления отдельным примером"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✏️ Редактировать",
                callback_data=f"edit_example_{example_id}"
            ),
            InlineKeyboardButton(
                text="🔄 Изменить категорию",
                callback_data=f"change_category_{example_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⭐ Изменить оценку",
                callback_data=f"change_rating_{example_id}"
            ),
            InlineKeyboardButton(
                text="📊 Статистика",
                callback_data=f"example_stats_{example_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔇 Деактивировать",
                callback_data=f"deactivate_example_{example_id}"
            ),
            InlineKeyboardButton(
                text="🗑️ Удалить",
                callback_data=f"delete_example_{example_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 К списку примеров",
                callback_data="examples_list"
            )
        ]
    ])
    
    return keyboard


def get_confirm_delete_keyboard(example_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления примера"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, удалить",
                callback_data=f"confirm_delete_{example_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"view_example_{example_id}"
            )
        ]
    ])
    
    return keyboard


def get_ai_processing_choice_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора AI обработки поста"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🤖 Применить AI стилизацию",
                callback_data="ai_stylize_yes"
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 Сохранить как есть",
                callback_data="ai_stylize_no"
            )
        ],
        [
            InlineKeyboardButton(
                text="❓ Что такое AI стилизация?",
                callback_data="ai_stylize_info"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data="cancel_example_adding"
            )
        ]
    ])
    
    return keyboard


def get_add_example_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню способов добавления примера"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📝 Ввести текст",
                callback_data="add_example_text"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔗 Загрузить по ссылке", 
                callback_data="add_example_link"
            )
        ],
        [
            InlineKeyboardButton(
                text="📁 Переслать сообщение",
                callback_data="add_example_forward"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Загрузить из канала",
                callback_data="add_example_from_channel"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="view_examples"
            )
        ]
    ])
    
    return keyboard


def get_confirmation_keyboard(action: str, item_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    
    action_texts = {
        "delete": "🗑️ Да, удалить",
        "deactivate": "❌ Да, деактивировать",
        "activate": "✅ Да, активировать"
    }
    
    confirm_text = action_texts.get(action, "✅ Подтвердить")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=confirm_text,
                callback_data=f"confirm_{action}_{item_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"manage_example_{item_id}"
            )
        ]
    ])
    
    return keyboard


def get_examples_stats_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для статистики примеров"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📊 По категориям",
                callback_data="stats_by_category"
            ),
            InlineKeyboardButton(
                text="⭐ По качеству",
                callback_data="stats_by_quality"
            )
        ],
        [
            InlineKeyboardButton(
                text="📈 Использование",
                callback_data="stats_usage"
            ),
            InlineKeyboardButton(
                text="📅 По времени",
                callback_data="stats_by_date"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏆 Лучшие примеры",
                callback_data="show_best_examples"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад к примерам",
                callback_data="view_examples"
            )
        ]
    ])
    
    return keyboard


def get_bulk_actions_keyboard(selected_count: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура для массовых действий с примерами"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"✅ Выбрано: {selected_count}",
                callback_data="show_selected_examples"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Активировать выбранные",
                callback_data="bulk_activate"
            ),
            InlineKeyboardButton(
                text="❌ Деактивировать",
                callback_data="bulk_deactivate"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Изменить категорию",
                callback_data="bulk_change_category"
            ),
            InlineKeyboardButton(
                text="⭐ Изменить качество",
                callback_data="bulk_change_quality"
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑️ Удалить выбранные",
                callback_data="bulk_delete"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отменить выбор",
                callback_data="cancel_bulk_selection"
            ),
            InlineKeyboardButton(
                text="⬅️ К примерам",
                callback_data="view_examples"
            )
        ]
    ])
    
    return keyboard


# Дополнительные утилитарные функции

def create_navigation_keyboard(
    current_page: int,
    total_pages: int,
    callback_prefix: str = "page"
) -> List[InlineKeyboardButton]:
    """Создать кнопки навигации для пагинации"""
    
    buttons = []
    
    if current_page > 1:
        buttons.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"{callback_prefix}_{current_page-1}"
            )
        )
    
    buttons.append(
        InlineKeyboardButton(
            text=f"{current_page}/{total_pages}",
            callback_data=f"{callback_prefix}_current"
        )
    )
    
    if current_page < total_pages:
        buttons.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"{callback_prefix}_{current_page+1}"
            )
        )
    
    return buttons