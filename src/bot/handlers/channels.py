"""
Обработчики управления каналами
Добавление, удаление и настройка каналов для мониторинга
"""

import asyncio
from typing import Optional, List

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# aiogram 3.x импорты
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Локальные импорты
from src.bot.filters.owner import OwnerFilter
from src.bot.keyboards.inline import (
    get_channels_menu_keyboard,
    get_channel_list_keyboard,
    get_confirmation_keyboard
)
from src.database.crud.channel import get_channel_crud
from src.userbot.monitor import get_channel_monitor
from src.utils.telegram_parser import get_telegram_parser
from src.utils.html_formatter import (
    bold, format_list_items, get_parse_mode, safe_edit_message
)

# Настройка логгера модуля
logger = logger.bind(module="bot_channels")

# Роутер для управления каналами
channels_router = Router()


class ChannelStates(StatesGroup):
    """Состояния FSM для управления каналами"""
    adding_channel = State()
    adding_channel_by_invite = State()
    removing_channel = State()


@channels_router.message(Command("channels"), OwnerFilter())
async def channels_command(message: Message):
    """Команда /channels - управление каналами"""
    try:
        channel_crud = get_channel_crud()
        
        # Получаем статистику каналов
        all_channels = await channel_crud.get_all_channels()
        active_channels = await channel_crud.get_active_channels()
        
        total_processed = sum(channel.posts_processed for channel in all_channels)
        
        channels_text = f"""📺 {bold('Управление каналами')}

📊 {bold('Статистика:')}
{format_list_items([
    f'Всего каналов: {len(all_channels)}',
    f'Активных: {len(active_channels)}', 
    f'Обработано постов: {total_processed}'
])}

🔧 {bold('Возможности:')}
{format_list_items([
    'Добавление/удаление каналов',
    'Проверка доступа UserBot',
    'Автоматическая подписка',
    'Мониторинг активности'
])}

Выберите действие из меню ниже:"""
        
        keyboard = get_channels_menu_keyboard()
        
        await message.answer(
            channels_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info("Пользователь {} открыл управление каналами", message.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка открытия управления каналами: {}", str(e))
        await message.answer("❌ Произошла ошибка при загрузке каналов")


@channels_router.callback_query(F.data == "channels_menu", OwnerFilter())
async def channels_menu_callback(callback: CallbackQuery):
    """Возврат в меню каналов"""
    try:
        await callback.answer()
        
        channel_crud = get_channel_crud()
        all_channels = await channel_crud.get_all_channels()
        active_channels = await channel_crud.get_active_channels()
        total_processed = sum(channel.posts_processed for channel in all_channels)
        
        channels_text = f"""📺 {bold('Управление каналами')}

📊 {bold('Статистика:')}
{format_list_items([
    f'Всего каналов: {len(all_channels)}',
    f'Активных: {len(active_channels)}', 
    f'Обработано постов: {total_processed}'
])}

🔧 {bold('Возможности:')}
{format_list_items([
    'Добавление/удаление каналов',
    'Проверка доступа UserBot',
    'Автоматическая подписка',
    'Мониторинг активности'
])}

Выберите действие из меню ниже:"""
        
        keyboard = get_channels_menu_keyboard()
        
        await callback.message.edit_text(
            channels_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.debug("Пользователь {} вернулся в меню каналов", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка возврата в меню каналов: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@channels_router.callback_query(F.data == "list_channels", OwnerFilter())
async def list_channels_callback(callback: CallbackQuery):
    """Показать список всех каналов"""
    try:
        await callback.answer()
        
        channel_crud = get_channel_crud()
        channels = await channel_crud.get_all_channels()
        
        if not channels:
            await callback.message.edit_text(
                "📺 <b>Список каналов пуст</b>\n\n"
                "У вас пока нет добавленных каналов для мониторинга.\n"
                "Используйте кнопку \"Добавить канал\" для начала мониторинга.",
                parse_mode="HTML"
            )
            return
        
        channels_text = f"📺 <b>Ваши каналы ({len(channels)})</b>\n\n"
        channels_text += "Выберите канал для просмотра деталей:"
        
        keyboard = get_channel_list_keyboard(channels, page=1)
        
        await callback.message.edit_text(
            channels_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info("Показан список каналов: {} каналов", len(channels))
        
    except Exception as e:
        logger.error("Ошибка получения списка каналов: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@channels_router.callback_query(F.data.startswith("channels_page_"), OwnerFilter())
async def channels_navigation_callback(callback: CallbackQuery):
    """Навигация по страницам списка каналов"""
    try:
        await callback.answer()
        
        # Извлекаем номер страницы из callback_data
        page = int(callback.data.replace("channels_page_", ""))
        
        # Получаем список каналов
        channel_crud = get_channel_crud()
        channels = await channel_crud.get_all_channels()
        
        if not channels:
            await safe_edit_message(
                callback,
                "📺 <b>Список каналов пуст</b>\n\n"
                "Добавьте каналы для мониторинга через меню управления."
            )
            return
        
        # Формируем клавиатуру с пагинацией
        keyboard = get_channel_list_keyboard(channels, page=page)
        
        # Редактируем сообщение с новой страницей
        await safe_edit_message(
            callback,
            f"📺 <b>Список каналов для мониторинга</b>\n"
            f"Всего каналов: {len(channels)}\n\n"
            f"Выберите канал для подробной информации:",
            keyboard
        )
        
        logger.info("Показана страница {} списка каналов", page)
        
    except Exception as e:
        logger.error("Ошибка навигации по страницам каналов: {}", str(e))
        await callback.answer("❌ Произошла ошибка навигации", show_alert=True)


@channels_router.callback_query(F.data == "refresh_channels", OwnerFilter())
async def refresh_channels_callback(callback: CallbackQuery):
    """Обновить список каналов"""
    try:
        await callback.answer("🔄 Обновляем список каналов...")
        
        # Получаем список каналов
        channel_crud = get_channel_crud()
        channels = await channel_crud.get_all_channels()
        
        if not channels:
            await safe_edit_message(
                callback,
                "📺 <b>Список каналов пуст</b>\n\n"
                "Добавьте каналы для мониторинга через меню управления."
            )
            return
        
        # Формируем клавиатуру (начинаем с первой страницы)
        keyboard = get_channel_list_keyboard(channels, page=1)
        
        # Редактируем сообщение
        await safe_edit_message(
            callback,
            f"📺 <b>Список каналов для мониторинга</b>\n"
            f"Всего каналов: {len(channels)}\n\n"
            f"Выберите канал для подробной информации:",
            keyboard
        )
        
        logger.info("Список каналов обновлен: {} каналов", len(channels))
        
    except Exception as e:
        logger.error("Ошибка обновления списка каналов: {}", str(e))
        await callback.answer("❌ Произошла ошибка обновления", show_alert=True)


@channels_router.callback_query(F.data == "add_channel", OwnerFilter())
async def add_channel_callback(callback: CallbackQuery, state: FSMContext):
    """Добавить новый канал"""
    try:
        await callback.answer()
        
        add_text = """➕ <b>Добавление канала</b>

📝 Отправьте один из вариантов:

🔸 <b>Username канала:</b> @channel_name
🔸 <b>Ссылку на канал:</b> https://t.me/channel_name
🔸 <b>ID канала:</b> -1001234567890

💡 <b>Примечания:</b>
• UserBot автоматически попытается подписаться на канал
• Для приватных каналов может потребоваться ссылка-приглашение
• Убедитесь что у UserBot есть доступ к каналу

❌ /cancel - отменить добавление"""
        
        await callback.message.edit_text(
            add_text,
            parse_mode="HTML"
        )
        
        await state.set_state(ChannelStates.adding_channel)
        logger.debug("Пользователь {} начал добавление канала", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка начала добавления канала: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@channels_router.message(ChannelStates.adding_channel, OwnerFilter())
async def process_add_channel(message: Message, state: FSMContext):
    """Обработать добавление канала"""
    try:
        channel_input = message.text.strip()
        
        # Показываем процесс добавления
        loading_message = await message.answer("⏳ Добавляю канал...")
        
        # Добавляем канал через монитор
        monitor = get_channel_monitor()
        success = await monitor.add_channel(channel_input)
        
        if success:
            await loading_message.edit_text(
                f"✅ <b>Канал добавлен!</b>\n\n"
                f"Канал <code>{channel_input}</code> успешно добавлен в мониторинг.\n\n"
                f"🤖 UserBot проверил доступ и подписался на канал\n"
                f"📡 Мониторинг новых постов активен\n\n"
                f"Используйте /channels для управления каналами.",
                parse_mode="HTML"
            )
        else:
            await loading_message.edit_text(
                f"❌ <b>Не удалось добавить канал</b>\n\n"
                f"Канал <code>{channel_input}</code> не удалось добавить.\n\n"
                f"Возможные причины:\n"
                f"• Канал не существует или заблокирован\n"
                f"• У UserBot нет доступа к каналу\n"
                f"• Неверный формат ссылки/ID\n\n"
                f"Попробуйте еще раз или используйте ссылку-приглашение.",
                parse_mode="HTML"
            )
        
        await state.clear()
        logger.info("Пользователь {} добавил канал {}: {}", 
                   message.from_user.id, channel_input, "успешно" if success else "ошибка")
        
    except Exception as e:
        logger.error("Ошибка обработки добавления канала: {}", str(e))
        await message.answer("❌ Произошла ошибка при добавлении канала")
        await state.clear()


@channels_router.callback_query(F.data.startswith("channel_info_"), OwnerFilter())
async def channel_info_callback(callback: CallbackQuery):
    """Показать информацию о канале"""
    try:
        await callback.answer()
        
        channel_id = int(callback.data.replace("channel_info_", ""))
        
        channel_crud = get_channel_crud()
        channel = await channel_crud.get_channel_by_id(channel_id)
        
        if not channel:
            await callback.answer("❌ Канал не найден", show_alert=True)
            return
        
        # Формируем информацию о канале
        info_text = format_channel_info(channel)
        
        # Клавиатура с действиями для канала
        keyboard = get_channel_management_keyboard(channel_id)
        
        await callback.message.edit_text(
            info_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info("Показана информация о канале {}", channel_id)
        
    except Exception as e:
        logger.error("Ошибка показа информации о канале: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@channels_router.callback_query(F.data == "check_channels_access", OwnerFilter())
async def check_channels_access_callback(callback: CallbackQuery):
    """Проверить доступ ко всем каналам с автоматическим присоединением"""
    try:
        await callback.answer("🔍 Проверяю доступ к каналам...")

        # Показываем процесс проверки
        loading_message = await callback.message.edit_text(
            "🔍 <b>Проверка доступа к каналам</b>\n\n"
            "⏳ Проверяю доступ UserBot ко всем каналам...\n"
            "Это может занять некоторое время.",
            parse_mode="HTML"
        )

        # Получаем все каналы
        channel_crud = get_channel_crud()
        channels = await channel_crud.get_all_channels()

        if not channels:
            await loading_message.edit_text(
                "📺 <b>Нет каналов для проверки</b>\n\n"
                "У вас пока нет добавленных каналов.",
                parse_mode="HTML"
            )
            return

        # Проверяем доступ к каждому каналу
        accessible = []
        inaccessible = []
        rejoined = []  # Каналы к которым удалось присоединиться повторно

        monitor = get_channel_monitor()

        for channel in channels:
            try:
                # Проверяем доступ
                has_access = await check_channel_access(channel.channel_id)

                if has_access:
                    accessible.append(channel)
                else:
                    # Если доступа нет - пытаемся присоединиться
                    logger.info("Нет доступа к каналу {}, пытаюсь присоединиться...",
                               channel.username or channel.channel_id)

                    join_success = await monitor.auto_join_channel(channel)

                    if join_success:
                        # Проверяем доступ снова после присоединения
                        await asyncio.sleep(1)  # Небольшая задержка
                        has_access_after_join = await check_channel_access(channel.channel_id)

                        if has_access_after_join:
                            accessible.append(channel)
                            rejoined.append(channel)
                            logger.info("✅ Успешно присоединились к каналу {}",
                                       channel.username or channel.title)
                        else:
                            inaccessible.append(channel)
                            logger.warning("Присоединились, но доступ все еще недоступен: {}",
                                         channel.username or channel.title)
                    else:
                        inaccessible.append(channel)

            except Exception as e:
                logger.warning("Ошибка проверки канала {}: {}", channel.channel_id, str(e))
                inaccessible.append(channel)
        
        # Формируем результат
        result_text = f"""✅ <b>Проверка доступа завершена</b>

📊 <b>Результаты:</b>
🟢 Доступные: {len(accessible)}
🔴 Недоступные: {len(inaccessible)}
"""

        if rejoined:
            result_text += f"🔄 Повторно присоединились: {len(rejoined)}\n"

        result_text += "\n"

        if accessible:
            result_text += "🟢 <b>Доступные каналы:</b>\n"
            for channel in accessible[:5]:  # Показываем первые 5
                name = channel.title or channel.username or f"ID: {channel.channel_id}"
                # Помечаем каналы к которым повторно присоединились
                if channel in rejoined:
                    result_text += f"• {name} 🔄\n"
                else:
                    result_text += f"• {name}\n"
            if len(accessible) > 5:
                result_text += f"• ... и еще {len(accessible) - 5}\n"
            result_text += "\n"

        if inaccessible:
            result_text += "🔴 <b>Недоступные каналы:</b>\n"
            for channel in inaccessible[:5]:  # Показываем первые 5
                name = channel.title or channel.username or f"ID: {channel.channel_id}"
                result_text += f"• {name}\n"
            if len(inaccessible) > 5:
                result_text += f"• ... и еще {len(inaccessible) - 5}\n"
            result_text += "\n💡 <i>Для приватных каналов используйте ссылку-приглашение</i>\n"
        
        # Кнопки для дальнейших действий
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Проверить еще раз",
                    callback_data="check_channels_access"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📺 Список каналов",
                    callback_data="list_channels"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К управлению каналами",
                    callback_data="channels_menu"
                )
            ]
        ])
        
        await loading_message.edit_text(
            result_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info("Проверен доступ к каналам: {} доступных, {} недоступных", 
                   len(accessible), len(inaccessible))
        
    except Exception as e:
        logger.error("Ошибка проверки доступа к каналам: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@channels_router.callback_query(F.data.startswith("remove_channel_"), OwnerFilter())
async def remove_channel_callback(callback: CallbackQuery):
    """Удалить канал"""
    try:
        await callback.answer()
        
        channel_id = int(callback.data.replace("remove_channel_", ""))
        
        channel_crud = get_channel_crud()
        channel = await channel_crud.get_channel_by_id(channel_id)
        
        if not channel:
            await callback.answer("❌ Канал не найден", show_alert=True)
            return
        
        channel_name = channel.title or channel.username or f"ID: {channel.channel_id}"
        
        confirmation_text = f"""🗑️ <b>Удалить канал?</b>

📺 <b>Канал:</b> {channel_name}
📊 <b>Обработано постов:</b> {channel.posts_processed}

⚠️ <b>Внимание:</b>
• Канал будет удален из мониторинга
• История постов останется в базе данных
• UserBot останется подписанным на канал

Подтвердите удаление:"""
        
        keyboard = get_confirmation_keyboard(
            "remove_channel", 
            channel_id, 
            "🗑️ Да, удалить", 
            "❌ Отменить"
        )
        
        await callback.message.edit_text(
            confirmation_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.debug("Запрос подтверждения удаления канала {}", channel_id)
        
    except Exception as e:
        logger.error("Ошибка удаления канала: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@channels_router.callback_query(F.data.startswith("confirm_remove_channel_"), OwnerFilter())
async def confirm_remove_channel(callback: CallbackQuery):
    """Подтвердить удаление канала"""
    try:
        await callback.answer("🗑️ Удаляю канал...")
        
        channel_id = int(callback.data.replace("confirm_remove_channel_", ""))
        
        channel_crud = get_channel_crud()
        success = await channel_crud.delete_channel(channel_id)
        
        if success:
            await callback.message.edit_text(
                "✅ <b>Канал удален</b>\n\n"
                "Канал успешно удален из мониторинга.\n"
                "Возвращаемся к списку каналов...",
                parse_mode="HTML"
            )
            
            # Показываем обновленный список
            await asyncio.sleep(2)
            await list_channels_callback(callback)
            
        else:
            await callback.message.edit_text(
                "❌ <b>Ошибка удаления</b>\n\n"
                "Не удалось удалить канал из базы данных.",
                parse_mode="HTML"
            )
        
        logger.info("Канал {} удален пользователем {}", channel_id, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка подтверждения удаления канала {}: {}", channel_id, str(e))
        await callback.answer("❌ Ошибка удаления", show_alert=True)


@channels_router.message(Command("cancel"), ChannelStates.adding_channel, OwnerFilter())
async def cancel_adding_channel(message: Message, state: FSMContext):
    """Отменить добавление канала"""
    await state.clear()
    await message.answer("❌ Добавление канала отменено")
    logger.debug("Пользователь {} отменил добавление канала", message.from_user.id)


def get_channel_management_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    """Клавиатура управления конкретным каналом"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📊 Статистика канала",
                callback_data=f"channel_stats_{channel_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔍 Проверить доступ",
                callback_data=f"check_channel_{channel_id}"
            ),
            InlineKeyboardButton(
                text="🔄 Обновить информацию",
                callback_data=f"refresh_channel_{channel_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⏸️ Приостановить",
                callback_data=f"pause_channel_{channel_id}"
            ),
            InlineKeyboardButton(
                text="🗑️ Удалить",
                callback_data=f"remove_channel_{channel_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ К списку каналов",
                callback_data="list_channels"
            )
        ]
    ])
    
    return keyboard


def format_channel_info(channel) -> str:
    """Форматировать информацию о канале"""
    try:
        # Базовая информация
        info_text = f"""📺 <b>Информация о канале</b>

🆔 <b>ID:</b> <code>{channel.channel_id}</code>
"""
        
        # Название
        if channel.title:
            info_text += f"📝 <b>Название:</b> {channel.title}\n"
        
        # Username
        if channel.username:
            info_text += f"👤 <b>Username:</b> @{channel.username}\n"
        
        # Статус
        status_icon = "🟢" if channel.is_active else "🔴"
        status_text = "Активен" if channel.is_active else "Приостановлен"
        info_text += f"{status_icon} <b>Статус:</b> {status_text}\n"
        
        # Статистика
        info_text += f"\n📊 <b>Статистика:</b>\n"
        info_text += f"📝 Обработано постов: {channel.posts_processed}\n"
        info_text += f"✅ Одобрено: {channel.posts_approved}\n"
        info_text += f"❌ Отклонено: {channel.posts_rejected}\n"
        
        # Последнее сообщение
        if channel.last_message_id:
            info_text += f"📬 Последнее сообщение: {channel.last_message_id}\n"
        
        # Даты
        if channel.created_at:
            info_text += f"\n📅 <b>Добавлен:</b> {channel.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        if channel.updated_at:
            info_text += f"🔄 <b>Обновлен:</b> {channel.updated_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        return info_text
        
    except Exception as e:
        logger.error("Ошибка форматирования информации о канале: {}", str(e))
        return f"❌ Ошибка отображения информации о канале"


async def check_channel_access(channel_id: int) -> bool:
    """
    Проверить доступ к каналу
    
    Args:
        channel_id: ID канала
        
    Returns:
        True если доступ есть
    """
    try:
        # Здесь будет реальная проверка через UserBot
        monitor = get_channel_monitor()
        if monitor.client:
            return await monitor.client.check_channel_access(channel_id)
        return False
        
    except Exception as e:
        logger.error("Ошибка проверки доступа к каналу {}: {}", channel_id, str(e))
        return False


def get_channels_router() -> Router:
    """Получить роутер каналов"""
    return channels_router