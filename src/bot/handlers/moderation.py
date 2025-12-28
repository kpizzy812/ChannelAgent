"""
Обработчики модерации постов
Интерфейс для одобрения, отклонения и редактирования постов
"""

import asyncio
from datetime import datetime, timedelta

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
    get_moderation_menu_keyboard,
    get_post_moderation_keyboard,
    get_posts_list_keyboard,
    get_confirmation_keyboard,
    get_time_selection_keyboard,
    get_ai_analysis_keyboard
)
from src.database.crud.post import get_post_crud
from src.database.models.post import PostStatus
from src.ai.processor import get_ai_processor
from src.utils.config import get_config
from src.utils.html_formatter import (
    bold, format_success_message, format_error_message, format_warning_message,
    format_info_message, format_list_items, get_parse_mode, link, code,
    safe_edit_message
)
from src.bot.media_handler import get_media_handler
from src.utils.post_footer import add_footer_to_post

# Настройка логгера модуля
logger = logger.bind(module="bot_moderation")

# Роутер для модерации
moderation_router = Router()


class ModerationStates(StatesGroup):
    """Состояния FSM для модерации"""
    editing_post_text = State()
    editing_post_photo = State()
    setting_schedule_time = State()
    adding_moderation_note = State()


@moderation_router.message(Command("moderation"), OwnerFilter())
async def moderation_command(message: Message):
    """Команда /moderation - меню модерации"""
    try:
        post_crud = get_post_crud()
        
        # Получаем количество постов на модерации
        pending_posts = await post_crud.get_posts_by_status(PostStatus.PENDING)
        pending_count = len(pending_posts)
        
        moderation_text = f"""⚖️ {bold('Модерация постов')}

📊 {bold('Текущая ситуация:')}
⏳ На модерации: {pending_count} постов

🔧 {bold('Возможности модерации:')}
{format_list_items([
    'Просмотр и одобрение постов',
    'Редактирование текста и фото',
    'Отложенная публикация',
    'AI рестайлинг под ваш стиль',
    'Отклонение нерелевантных постов'
])}

Выберите действие из меню ниже:"""
        
        keyboard = get_moderation_menu_keyboard(pending_count)
        
        await message.answer(
            moderation_text,
            reply_markup=keyboard, 
            parse_mode=get_parse_mode())
        
        logger.info("Пользователь {} открыл меню модерации", message.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка открытия меню модерации: {}", str(e))
        await message.answer("❌ Произошла ошибка при загрузке модерации")


@moderation_router.callback_query(F.data == "moderation_menu", OwnerFilter())
async def moderation_menu_callback(callback: CallbackQuery):
    """Возврат в меню модерации"""
    try:
        await callback.answer()
        
        post_crud = get_post_crud()
        pending_posts = await post_crud.get_posts_by_status(PostStatus.PENDING)
        pending_count = len(pending_posts)
        
        moderation_text = f"""⚖️ {bold('Модерация постов')}

📊 {bold('Текущая ситуация:')}
⏳ На модерации: {pending_count} постов

🔧 {bold('Возможности модерации:')}
{format_list_items([
    'Просмотр и одобрение постов',
    'Редактирование текста и фото',
    'Отложенная публикация',
    'AI рестайлинг под ваш стиль',
    'Отклонение нерелевантных постов'
])}

Выберите действие из меню ниже:"""
        
        keyboard = get_moderation_menu_keyboard(pending_count)
        
        await safe_edit_message(callback, moderation_text, keyboard, get_parse_mode())
        
        logger.debug("Пользователь {} вернулся в меню модерации", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка возврата в меню модерации: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data == "pending_posts", OwnerFilter())
async def pending_posts_callback(callback: CallbackQuery):
    """Показать посты на модерации"""
    try:
        await callback.answer()
        
        post_crud = get_post_crud()
        pending_posts = await post_crud.get_posts_by_status(PostStatus.PENDING)
        
        if not pending_posts:
            success_text = format_success_message(
                "Нет постов на модерации",
                "Все посты обработаны!\nНовые посты будут появляться здесь автоматически."
            )
            await safe_edit_message(callback, success_text, None, get_parse_mode())
            return
        
        posts_text = f"⏳ {bold(f'Посты на модерации ({len(pending_posts)})')}\n\n"
        posts_text += "Выберите пост для модерации:"
        
        keyboard = get_posts_list_keyboard(pending_posts, "pending", page=1)
        
        await safe_edit_message(callback, posts_text, keyboard, get_parse_mode())
        
        logger.info("Показаны посты на модерации: {} постов", len(pending_posts))
        
    except Exception as e:
        logger.error("Ошибка получения постов на модерации: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data.startswith("view_post_"), OwnerFilter())
async def view_post_callback(callback: CallbackQuery):
    """Просмотр конкретного поста для модерации с исходным фото и форматированием"""
    try:
        await callback.answer()
        
        post_id = int(callback.data.replace("view_post_", ""))
        
        post_crud = get_post_crud()
        post = await post_crud.get_post_by_id(post_id)
        
        if not post:
            await callback.answer("❌ Пост не найден", show_alert=True)
            return
        
        keyboard = get_post_moderation_keyboard(post_id)

        # Проверяем есть ли медиа у поста
        media_handler = get_media_handler()

        # Проверяем наличие альбома (более 1 медиа)
        if post.has_album:
            try:
                from src.bot.main import get_bot_instance
                bot = get_bot_instance()

                # Формируем подпись для альбома
                caption = format_post_caption_for_moderation(post)
                if len(caption) > 1024:
                    caption = f"📎 {bold(f'Альбом #{post.id}')} ({post.album_count} медиа)\n📄 Текст слишком длинный"

                # Получаем media_group
                media_group = media_handler.get_media_group_for_send(post, caption, get_parse_mode())

                if len(media_group) >= 2:
                    # Отправляем альбом
                    await bot.send_media_group(
                        chat_id=callback.message.chat.id,
                        media=media_group
                    )

                    # Кнопки отправляем отдельным сообщением
                    buttons_text = f"📎 {bold(f'Альбом #{post.id}')} ({len(media_group)} медиа)\n⚡️ Выберите действие:"
                    await bot.send_message(
                        chat_id=callback.message.chat.id,
                        text=buttons_text,
                        reply_markup=keyboard,
                        parse_mode=get_parse_mode()
                    )

                    # Удаляем старое сообщение
                    try:
                        await callback.message.delete()
                    except Exception:
                        pass

                    logger.info("Альбом {} ({} медиа) отправлен на модерацию", post_id, len(media_group))
                    return
                else:
                    logger.warning("Недостаточно медиа для альбома поста {}, показываем как обычный", post_id)

            except Exception as album_error:
                logger.error("Ошибка отправки альбома для поста {}: {}", post_id, str(album_error))
                # Продолжаем с обычной логикой

        media_for_send, media_type = media_handler.get_media_for_send(post)

        if media_for_send:
            # Пост с медиа - отправляем медиа с подписью
            try:
                # Формируем подпись с информацией о модерации + исходный текст
                caption = format_post_caption_for_moderation(post)
                
                # Отправляем новое сообщение с медиа
                from src.bot.main import get_bot_instance
                bot = get_bot_instance()
                
                if media_type == 'photo':
                    media_message = await bot.send_photo(
                        chat_id=callback.message.chat.id,
                        photo=media_for_send,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode=get_parse_mode()
                    )
                elif media_type == 'video':
                    media_message = await bot.send_video(
                        chat_id=callback.message.chat.id,
                        video=media_for_send,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode=get_parse_mode()
                    )
                else:
                    # Fallback - отправляем как текст
                    raise ValueError(f"Неподдерживаемый тип медиа: {media_type}")
                
                # Удаляем старое текстовое сообщение
                try:
                    await callback.message.delete()
                except Exception as delete_error:
                    logger.debug("Не удалось удалить старое сообщение: {}", str(delete_error))
                
                logger.info("Пост с фото {} отправлен на модерацию пользователю {}", 
                           post_id, callback.from_user.id)
                
            except Exception as photo_error:
                # Детальная обработка ошибок с фото
                error_details = str(photo_error)
                
                # Определяем тип ошибки
                if "wrong remote file identifier" in error_details.lower() or "wrong padding" in error_details.lower():
                    # Ошибка с file_id - очищаем только если используется file_id
                    if isinstance(photo_for_send, str):  # photo_file_id
                        logger.error("Некорректный photo_file_id для поста {}: {}", post_id, post.photo_file_id)
                        error_message = "Некорректный ID фото (файл устарел)"
                        
                        # Очищаем photo_file_id в базе данных
                        try:
                            post_crud = get_post_crud()
                            await post_crud.update_post(post_id, photo_file_id=None)
                            logger.info("Очищен некорректный photo_file_id для поста {}", post_id)
                        except Exception as clear_error:
                            logger.error("Ошибка очистки photo_file_id: {}", str(clear_error))
                    else:
                        # Ошибка с локальным файлом
                        logger.error("Ошибка отправки локального фото для поста {}: {}", post_id, error_details)
                        error_message = "Ошибка локального файла фото"
                else:
                    logger.error("Общая ошибка отправки фото для поста {}: {}", post_id, error_details)
                    error_message = f"Ошибка загрузки фото: {error_details}"
                
                # Если не удалось отправить фото, показываем как текст
                post_text = format_post_for_moderation(post)
                post_text += f"\n\n⚠️ {bold('Ошибка фото')}: {error_message}"
                
                await safe_edit_message(callback, post_text, keyboard, get_parse_mode())
        else:
            # Пост без фото - обычное текстовое сообщение
            post_text = format_post_for_moderation(post)
            
            await safe_edit_message(callback,
                post_text,
                reply_markup=keyboard,
                parse_mode=get_parse_mode()
            )
            
            logger.info("Текстовый пост {} отправлен на модерацию пользователю {}", 
                       post_id, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка просмотра поста: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data.startswith("show_full_post_"), OwnerFilter())
async def show_full_post_callback(callback: CallbackQuery):
    """Показать полный пост с форматированием"""
    try:
        await callback.answer()
        
        post_id = int(callback.data.replace("show_full_post_", ""))
        
        # Получаем пост
        post_crud = get_post_crud()
        post = await post_crud.get_by_id(post_id)
        
        if not post:
            await callback.answer("❌ Пост не найден", show_alert=True)
            return
        
        # Отправляем полный пост отдельным сообщением
        post_text = format_post_for_moderation(post)
        
        # Добавляем кнопку "Назад к модерации"
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔙 К модерации",
                callback_data=f"view_post_{post_id}"
            )]
        ])
        
        await callback.message.answer(
            post_text,
            reply_markup=back_keyboard,
            parse_mode=get_parse_mode())
        
        logger.info("Показан полный пост {} пользователю {}", post_id, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа полного поста: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data.startswith("show_post_"), OwnerFilter())
async def show_post_callback(callback: CallbackQuery):
    """Показать обработанный пост отдельным сообщением"""
    try:
        await callback.answer()
        
        post_id = int(callback.data.replace("show_post_", ""))
        
        # Получаем пост
        post_crud = get_post_crud()
        post = await post_crud.get_post_by_id(post_id)
        
        if not post:
            await callback.answer("❌ Пост не найден", show_alert=True)
            return
        
        # Используем обработанный текст или оригинальный если нет обработанного
        text_to_show = post.processed_text or post.original_text or "Текст отсутствует"
        
        # Отправляем пост с медиа или без
        media_handler = get_media_handler()
        media_for_send, media_type = media_handler.get_media_for_send(post)
        
        if media_for_send:
            try:
                # Отправляем медиа с текстом
                if media_type == 'photo':
                    await callback.message.answer_photo(
                        photo=media_for_send,
                        caption=text_to_show,
                        parse_mode=get_parse_mode()
                    )
                elif media_type == 'video':
                    await callback.message.answer_video(
                        video=media_for_send,
                        caption=text_to_show,
                        parse_mode=get_parse_mode()
                    )
                else:
                    # Fallback к тексту
                    await callback.message.answer(
                        text=text_to_show,
                        parse_mode=get_parse_mode()
                    )
                logger.info("📄 Показан пост {} с фото пользователю {}", post_id, callback.from_user.id)
                
            except Exception as photo_error:
                logger.warning("Ошибка отправки фото для поста {}: {}, отправляем только текст", 
                             post_id, str(photo_error))
                # Если ошибка с фото - отправляем только текст
                await callback.message.answer(
                    text_to_show,
                    parse_mode=get_parse_mode()
                )
        else:
            # Отправляем только текст
            await callback.message.answer(
                text_to_show,
                parse_mode=get_parse_mode()
            )
            logger.info("📄 Показан текст поста {} пользователю {}", post_id, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа поста {}: {}", post_id, str(e))
        await callback.answer("❌ Произошла ошибка при показе поста", show_alert=True)


@moderation_router.callback_query(F.data.startswith("approve_post_"), OwnerFilter())
async def approve_post_callback(callback: CallbackQuery):
    """Одобрить пост (опубликовать сейчас)"""
    try:
        await callback.answer("📤 Публикуем пост...")
        
        post_id = int(callback.data.replace("approve_post_", ""))
        
        # Здесь будет логика публикации в целевой канал
        success = await publish_post_now(post_id)
        
        if success:
            success_text = format_success_message(
                "Пост опубликован!",
                f"Пост успешно опубликован в целевом канале.\n🕐 Время публикации: {datetime.now().strftime('%H:%M')}\n\nПереходим к следующему посту..."
            )
            
            # Для сообщений с медиа используем safe_edit_message
            await safe_edit_message(callback, success_text, None, get_parse_mode())
            
            # Автоматически показываем следующий пост через 3 секунды
            await asyncio.sleep(3)
            await show_next_pending_post(callback)
            
        else:
            error_text = format_error_message(
                "Ошибка публикации",
                "Не удалось опубликовать пост.\nПроверьте настройки целевого канала."
            )
            
            # Для сообщений с медиа используем safe_edit_message  
            await safe_edit_message(callback, error_text, None, get_parse_mode())
        
        logger.info("Пост {} одобрен пользователем {}", post_id, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка одобрения поста {}: {}", post_id, str(e))
        await callback.answer("❌ Ошибка публикации", show_alert=True)


@moderation_router.callback_query(F.data.startswith("schedule_post_"), OwnerFilter())
async def schedule_post_callback(callback: CallbackQuery):
    """Запланировать пост на потом"""
    try:
        await callback.answer()
        
        post_id = int(callback.data.replace("schedule_post_", ""))
        
        schedule_text = f"⏰ {bold('Отложенная публикация')}\n\n" \
                       "Выберите время для публикации поста:"
        
        keyboard = get_time_selection_keyboard(post_id)
        
        await safe_edit_message(callback, schedule_text, keyboard, get_parse_mode())
        
        # Переводим в состояние планирования и сохраняем ID поста (в данном случае используем callback_data)
        # Сохраняем post_id в callback_data кнопок времени через обновление клавиатуры
        
        # TODO: Реализовать FSM для более надежного хранения состояния
        # await state.set_state(PostModerationStates.scheduling_post) 
        # await state.update_data(post_id=post_id)
        
        logger.debug("Пользователь {} планирует пост {}", callback.from_user.id, post_id)
        
    except Exception as e:
        logger.error("Ошибка планирования поста: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# 🆕 ОБРАБОТЧИКИ КНОПОК ВРЕМЕНИ ДЛЯ ПЛАНИРОВАНИЯ ПОСТОВ

@moderation_router.callback_query(F.data.startswith("schedule_1h_"), OwnerFilter())
async def schedule_1h_callback(callback: CallbackQuery):
    """Запланировать пост через 1 час"""
    await _schedule_post_by_interval(callback, hours=1)

@moderation_router.callback_query(F.data.startswith("schedule_3h_"), OwnerFilter())
async def schedule_3h_callback(callback: CallbackQuery):
    """Запланировать пост через 3 часа"""
    await _schedule_post_by_interval(callback, hours=3)

@moderation_router.callback_query(F.data.startswith("schedule_6h_"), OwnerFilter())
async def schedule_6h_callback(callback: CallbackQuery):
    """Запланировать пост через 6 часов"""
    await _schedule_post_by_interval(callback, hours=6)

@moderation_router.callback_query(F.data.startswith("schedule_12h_"), OwnerFilter())
async def schedule_12h_callback(callback: CallbackQuery):
    """Запланировать пост через 12 часов"""
    await _schedule_post_by_interval(callback, hours=12)

@moderation_router.callback_query(F.data.startswith("schedule_tomorrow_"), OwnerFilter())
async def schedule_tomorrow_callback(callback: CallbackQuery):
    """Запланировать пост завтра в 9:00"""
    await _schedule_post_fixed_time(callback, hour=9, days_offset=1)

@moderation_router.callback_query(F.data.startswith("schedule_evening_"), OwnerFilter())
async def schedule_evening_callback(callback: CallbackQuery):
    """Запланировать пост завтра в 18:00"""
    await _schedule_post_fixed_time(callback, hour=18, days_offset=1)

@moderation_router.callback_query(F.data.startswith("cancel_schedule_"), OwnerFilter())
async def cancel_schedule_callback(callback: CallbackQuery):
    """Отменить планирование поста"""
    try:
        await callback.answer("❌ Планирование отменено")
        
        # Извлекаем post_id из callback_data
        post_id = int(callback.data.replace("cancel_schedule_", ""))
        
        # Возвращаемся к посту
        await show_single_post(callback, post_id)
        
        logger.debug("Пользователь {} отменил планирование поста {}", callback.from_user.id, post_id)
        
    except Exception as e:
        logger.error("Ошибка отмены планирования: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)

async def _schedule_post_by_interval(callback: CallbackQuery, hours: int):
    """Запланировать пост через указанное количество часов"""
    try:
        await callback.answer(f"⏰ Планирую публикацию через {hours} час(а)...")
        
        # Извлекаем post_id из callback_data
        post_id_str = callback.data.split("_")[-1]  # Последний элемент после разделения по "_"
        post_id = int(post_id_str)
        
        # Вычисляем время публикации в UTC+3 (московское время)
        from datetime import timezone
        moscow_tz = timezone(timedelta(hours=3))
        now_moscow = datetime.now(moscow_tz)
        publish_time = now_moscow + timedelta(hours=hours)
        
        # Обновляем пост в БД
        success = await _update_post_schedule(post_id, publish_time)
        
        if success:
            # Форматируем время для отображения
            time_str = publish_time.strftime("%H:%M %d.%m.%Y")
            
            success_text = f"✅ {bold('Пост запланирован!')}\n\n" \
                          f"📅 Время публикации: {time_str} (UTC+3)\n" \
                          f"⏰ Через {hours} час(а)\n\n" \
                          "Пост будет автоматически опубликован в указанное время."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 К списку постов", callback_data="pending_posts")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            
            await safe_edit_message(callback, success_text, keyboard, get_parse_mode())
            
            logger.info("Пост {} запланирован на {}", post_id, time_str)
        else:
            await callback.message.edit_text(
                "❌ Ошибка планирования поста. Попробуйте еще раз.",
                reply_markup=get_moderation_menu_keyboard(),
                parse_mode=get_parse_mode()
            )
        
    except Exception as e:
        logger.error("Ошибка планирования поста через {} часов: {}", hours, str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)

async def _schedule_post_fixed_time(callback: CallbackQuery, hour: int, days_offset: int = 1):
    """Запланировать пост на фиксированное время"""
    try:
        await callback.answer(f"⏰ Планирую публикацию на {hour:02d}:00...")
        
        # Извлекаем post_id из callback_data
        post_id_str = callback.data.split("_")[-1]
        post_id = int(post_id_str)
        
        # Вычисляем время публикации в UTC+3
        from datetime import timezone
        moscow_tz = timezone(timedelta(hours=3))
        now_moscow = datetime.now(moscow_tz)
        
        # Устанавливаем время на завтра (или указанное количество дней) в нужный час
        publish_time = now_moscow.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days_offset)
        
        # Обновляем пост в БД
        success = await _update_post_schedule(post_id, publish_time)
        
        if success:
            # Форматируем время для отображения
            time_str = publish_time.strftime("%H:%M %d.%m.%Y")
            
            success_text = f"✅ {bold('Пост запланирован!')}\n\n" \
                          f"📅 Время публикации: {time_str} (UTC+3)\n\n" \
                          "Пост будет автоматически опубликован в указанное время."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 К списку постов", callback_data="pending_posts")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ])
            
            await safe_edit_message(callback, success_text, keyboard, get_parse_mode())
            
            logger.info("Пост {} запланирован на {}", post_id, time_str)
        else:
            await callback.message.edit_text(
                "❌ Ошибка планирования поста. Попробуйте еще раз.",
                reply_markup=get_moderation_menu_keyboard(),
                parse_mode=get_parse_mode()
            )
        
    except Exception as e:
        logger.error("Ошибка планирования поста на фиксированное время: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)

async def _update_post_schedule(post_id: int, publish_time: datetime) -> bool:
    """Обновить расписание поста в БД"""
    try:
        post_crud = get_post_crud()
        
        # Получаем пост
        post = await post_crud.get_by_id(post_id)
        if not post:
            logger.error("Пост {} не найден для планирования", post_id)
            return False
        
        # Обновляем статус и время публикации
        post.status = PostStatus.SCHEDULED
        post.scheduled_date = publish_time
        post.updated_at = datetime.now()
        
        # Сохраняем в БД
        await post_crud.update(post)
        
        logger.info("Пост {} успешно запланирован на {}", post_id, publish_time.strftime("%H:%M %d.%m.%Y"))
        return True
        
    except Exception as e:
        logger.error("Ошибка обновления расписания поста {}: {}", post_id, str(e))
        return False

@moderation_router.callback_query(F.data.startswith("reject_post_"), OwnerFilter())
async def reject_post_callback(callback: CallbackQuery):
    """Отклонить пост"""
    try:
        await callback.answer()
        
        post_id = int(callback.data.replace("reject_post_", ""))
        
        confirmation_text = f"❌ {bold('Отклонить пост?')}\n\n" \
                           "Пост будет помечен как отклоненный и не будет опубликован.\n" \
                           "Это действие можно отменить позже."
        
        keyboard = get_confirmation_keyboard("reject", post_id, "❌ Да, отклонить", "↩️ Отменить")
        
        await safe_edit_message(callback, confirmation_text, keyboard, get_parse_mode())
        
        logger.debug("Запрос подтверждения отклонения поста {}", post_id)
        
    except Exception as e:
        logger.error("Ошибка отклонения поста: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data.startswith("confirm_reject_") & (F.data != "confirm_reject_all"), OwnerFilter())
async def confirm_reject_post(callback: CallbackQuery):
    """Подтвердить отклонение поста"""
    post_id = None  # Инициализируем переменную
    try:
        await callback.answer("❌ Пост отклонен")
        
        post_id = int(callback.data.replace("confirm_reject_", ""))
        
        post_crud = get_post_crud()
        success = await post_crud.update_post_status(post_id, PostStatus.REJECTED)
        
        if success:
            await safe_edit_message(callback,
                format_error_message(
                    "Пост отклонен",
                    "Пост помечен как отклоненный.\nПереходим к следующему посту..."
                ),
                parse_mode=get_parse_mode()
            )
            
            # Показываем следующий пост
            await asyncio.sleep(2)
            await show_next_pending_post(callback)
            
        else:
            await safe_edit_message(callback,
                format_error_message(
                    "Ошибка отклонения",
                    "Не удалось отклонить пост."
                ),
                parse_mode=get_parse_mode()
            )
        
        logger.info("Пост {} отклонен пользователем {}", post_id, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка подтверждения отклонения поста {}: {}", post_id, str(e))
        await callback.answer("❌ Ошибка отклонения", show_alert=True)


@moderation_router.callback_query(F.data.startswith("cancel_reject_"), OwnerFilter())
async def cancel_reject_post(callback: CallbackQuery):
    """Отменить отклонение поста"""
    try:
        await callback.answer()
        
        post_id = int(callback.data.replace("cancel_reject_", ""))
        
        # Получаем пост для отображения
        post_crud = get_post_crud()
        post = await post_crud.get_post_by_id(post_id)
        
        if not post:
            await callback.answer("❌ Пост не найден", show_alert=True)
            return
        
        # Возвращаемся к обычному меню модерации поста
        keyboard = get_post_moderation_keyboard(post_id)
        post_text = format_post_for_moderation(post)
        
        await safe_edit_message(callback, post_text, keyboard, get_parse_mode())
        
        logger.debug("Отклонение поста {} отменено", post_id)
        
    except Exception as e:
        logger.error("Ошибка отмены отклонения поста {}: {}", post_id, str(e))
        await callback.answer("❌ Ошибка отмены", show_alert=True)


@moderation_router.callback_query(F.data.startswith("restyle_post_"), OwnerFilter())
async def restyle_post_callback(callback: CallbackQuery):
    """Двухэтапный рестайлинг поста через AI"""
    try:
        await callback.answer("🔄 Запускаю двухэтапный рестайлинг...")
        
        post_id = int(callback.data.replace("restyle_post_", ""))
        
        # Получаем пост
        post_crud = get_post_crud()
        post = await post_crud.get_post_by_id(post_id)
        
        if not post:
            await callback.answer("❌ Пост не найден", show_alert=True)
            return
        
        # Запускаем двухэтапный AI рестайлинг
        ai_processor = get_ai_processor()
        
        # Показываем статус загрузки
        loading_message = await safe_edit_message(callback,
            f"🔄 {bold('Двухэтапный AI Рестайлинг')}\n\n"
            f"🎯 {bold('ЭТАП 1:')} Максимальная уникализация контента...\n"
            f"⏳ Кардинально переделываем пост, сохраняя смысл\n\n"
            f"Это займет 15-30 секунд для качественной обработки.",
            parse_mode=get_parse_mode())
        
        try:
            # Запускаем двухэтапный рестайлинг
            restyle_result = await ai_processor.two_stage_restyle_post(post)
            
            if restyle_result.get("success"):
                # Обновляем статус - показываем этап 2
                if loading_message:
                    await loading_message.edit_text(
                        f"🔄 {bold('Двухэтапный AI Рестайлинг')}\n\n"
                        f"✅ {bold('ЭТАП 1:')} Уникализация завершена\n"
                        f"🎨 {bold('ЭТАП 2:')} HTML форматирование...\n\n"
                        f"Применяем красивое оформление с тегами и структурой.",
                        parse_mode=get_parse_mode()
                    )
                
                # Ждем немного чтобы пользователь увидел прогресс
                await asyncio.sleep(1)
                
                # Обновляем пост в БД с финальным результатом
                await post_crud.update_post(
                    post_id,
                    processed_text=restyle_result["final_text"],
                    ai_analysis=f"Двухэтапный рестайлинг: {restyle_result.get('processing_stages', 2)} этапа завершено"
                )
                
                # Показываем результат
                final_text = restyle_result["final_text"]
                
                # Формируем базовое сообщение о результате
                base_message = f"✅ {bold('ЭТАП 1:')} Уникализация - {bold('завершена')}\n" \
                              f"✅ {bold('ЭТАП 2:')} HTML форматирование - {bold('завершена')}\n\n" \
                              f"📊 {bold('Статистика:')}\n" \
                              f"• Исходный размер: {restyle_result.get('original_length', 0)} символов\n" \
                              f"• Финальный размер: {restyle_result.get('final_length', 0)} символов\n\n" \
                              f"🔄 Пост полностью переделан и готов к публикации!"
                
                # Проверяем есть ли фото у поста
                post = await post_crud.get_post_by_id(post_id)
                has_media = bool(post and post.has_media)
                
                # Определяем лимиты Telegram
                message_limit = 1000 if has_media else 4000
                
                # Рассчитываем длину сообщения с результатом поста
                success_title = "🎉 Двухэтапный рестайлинг завершен!"
                total_length = len(success_title) + len(base_message) + len(final_text)
                
                # Если общая длина превышает лимит - НЕ включаем текст поста
                if total_length > message_limit:
                    result_text = format_success_message(success_title, base_message)
                    # Используем клавиатуру с кнопкой "Показать пост"
                    from src.bot.keyboards.inline import get_post_moderation_keyboard_with_preview
                    keyboard = get_post_moderation_keyboard_with_preview(post_id)
                    logger.info("📏 Пост слишком длинный ({} символов > {} лимит), показываем кнопку 'Показать пост'", 
                               total_length, message_limit)
                else:
                    # Если помещается - включаем полный текст
                    result_text = format_success_message(
                        success_title,
                        f"{base_message}\n\n📝 {bold('Результат:')}\n{final_text}"
                    )
                    # Используем обычную клавиатуру
                    keyboard = get_post_moderation_keyboard(post_id)
                    logger.info("📏 Пост помещается в сообщение ({} символов <= {} лимит)", 
                               total_length, message_limit)
                
                if loading_message:
                    await loading_message.edit_text(
                        result_text,
                        reply_markup=keyboard,
                        parse_mode=get_parse_mode()
                    )
                
                # Отправляем дополнительное уведомление с обработанным контентом
                await _send_updated_post_notification(callback, post_crud, post_id, restyle_result)
                
                logger.info("✅ Двухэтапный рестайлинг поста {} завершен успешно", post_id)
                
            else:
                # Показываем ошибку с подробностями
                error_details = restyle_result.get("error", "Неизвестная ошибка")
                stage_info = ""
                
                if "stage_1_result" in restyle_result:
                    stage_1_success = restyle_result["stage_1_result"].get("success", False)
                    stage_info += f"• Этап 1 (уникализация): {'✅ завершен' if stage_1_success else '❌ ошибка'}\n"
                
                if "stage_2_result" in restyle_result:
                    stage_2_success = restyle_result["stage_2_result"].get("success", False)
                    stage_info += f"• Этап 2 (форматирование): {'✅ завершен' if stage_2_success else '❌ ошибка'}\n"
                
                if loading_message:
                    await loading_message.edit_text(
                        format_error_message(
                            "❌ Ошибка двухэтапного рестайлинга",
                            f"Не удалось завершить обработку:\n\n"
                            f"📊 {bold('Статус этапов:')}\n{stage_info}\n"
                            f"🚫 {bold('Ошибка:')} {error_details}\n\n"
                            f"💡 Попробуйте еще раз или отредактируйте пост вручную."
                        ),
                        parse_mode=get_parse_mode()
                    )
        
        except Exception as ai_error:
            logger.error("Критическая ошибка двухэтапного рестайлинга поста {}: {}", post_id, str(ai_error))
            
            if loading_message:
                await loading_message.edit_text(
                    format_error_message(
                        "💥 Критическая ошибка рестайлинга",
                        f"Произошла серьезная ошибка при обработке поста:\n\n"
                        f"🚫 {bold('Ошибка:')} {str(ai_error)}\n\n"
                        f"🔧 Обратитесь к администратору или попробуйте позже."
                    ),
                    parse_mode=get_parse_mode()
                )
            else:
                # Если loading_message недоступен, отправляем callback answer
                await callback.answer(
                    f"💥 Критическая ошибка рестайлинга: {str(ai_error)}",
                    show_alert=True
                )
        
        logger.info("Запущен двухэтапный рестайлинг поста {} пользователем {}", post_id, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка запуска двухэтапного рестайлинга: {}", str(e))
        await callback.answer("❌ Произошла ошибка при запуске", show_alert=True)


@moderation_router.callback_query(F.data.startswith("ai_analysis_"), OwnerFilter())
async def ai_analysis_callback(callback: CallbackQuery):
    """Показать AI анализ поста"""
    try:
        await callback.answer()
        
        post_id = int(callback.data.replace("ai_analysis_", ""))
        
        post_crud = get_post_crud()
        post = await post_crud.get_post_by_id(post_id)
        
        if not post:
            await callback.answer("❌ Пост не найден", show_alert=True)
            return
        
        # Формируем анализ
        analysis_text = format_ai_analysis(post)
        keyboard = get_ai_analysis_keyboard(post_id)
        
        await safe_edit_message(callback,
            analysis_text,
            keyboard, get_parse_mode())
        
        logger.debug("Показан AI анализ поста {}", post_id)
        
    except Exception as e:
        logger.error("Ошибка показа AI анализа: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data.startswith("edit_post_"), OwnerFilter())
async def edit_post_callback(callback: CallbackQuery, state: FSMContext):
    """Редактирование поста - переход в режим редактирования"""
    try:
        await callback.answer("✏️ Режим редактирования")
        
        post_id = int(callback.data.replace("edit_post_", ""))
        
        # Получаем пост
        post_crud = get_post_crud()
        post = await post_crud.get_post_by_id(post_id)
        
        if not post:
            await callback.answer("❌ Пост не найден", show_alert=True)
            return
        
        # Сохраняем ID поста в состояние
        await state.set_data({"editing_post_id": post_id})
        await state.set_state(ModerationStates.editing_post_text)
        
        # Показываем текущий текст и инструкции
        current_text = post.processed_text or post.original_text or ""
        
        edit_text = f"""✏️ {bold('Редактирование поста')}

📝 {bold('Текущий текст:')}

{current_text}

📋 {bold('Инструкции:')}
{format_list_items([
    'Отправьте новый текст поста с желаемым форматированием',
    'Можно использовать жирный, курсив, подчеркнутый текст',
    'Форматирование из Telegram будет сохранено 1:1',
    'Для отмены используйте /cancel'
])}

💡 {bold('Совет:')} Используйте форматирование прямо в Telegram - оно автоматически сохранится!"""

        await safe_edit_message(callback,
            edit_text,
            parse_mode=get_parse_mode())
        
        logger.info("Пользователь {} начал редактирование поста {}", callback.from_user.id, post_id)
        
    except Exception as e:
        logger.error("Ошибка начала редактирования поста: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.message(ModerationStates.editing_post_text, OwnerFilter())
async def handle_edit_post_text(message: Message, state: FSMContext):
    """Обработка отредактированного текста с перехватом форматирования"""
    try:
        # Получаем ID поста из состояния
        data = await state.get_data()
        post_id = data.get("editing_post_id")
        
        if not post_id:
            await message.answer("❌ Ошибка: не найден ID поста для редактирования")
            await state.clear()
            return
        
        # Перехватываем форматирование из Telegram
        formatted_text = ""
        if message.text and message.entities:
            # Используем парсер форматирования
            from src.utils.telegram_parser import format_entities_to_html, extract_formatted_text
            
            # Извлекаем форматированный текст согласно entities
            formatted_text = extract_formatted_text(message.text, message.entities)
            
            logger.info("Перехвачено форматирование: {} entities, длина текста: {}", 
                       len(message.entities), len(formatted_text))
            
        elif message.text:
            # Если нет форматирования, используем обычный текст
            formatted_text = message.text
            logger.info("Получен текст без форматирования: {} символов", len(formatted_text))
        else:
            await message.answer("❌ Не удалось получить текст сообщения")
            return
        
        # Обновляем пост в БД
        post_crud = get_post_crud()
        success = await post_crud.update_post(
            post_id,
            processed_text=formatted_text
        )
        
        if success:
            # Краткое подтверждение редактирования с информацией о форматировании
            entities_info = []
            if message.entities:
                # Подсчитываем типы entities
                entity_types = {}
                for entity in message.entities:
                    entity_types[entity.type] = entity_types.get(entity.type, 0) + 1
                
                # Формируем красивое описание
                for etype, count in entity_types.items():
                    type_name = {
                        "bold": "жирный", "italic": "курсив", "underline": "подчеркнутый",
                        "strikethrough": "зачеркнутый", "spoiler": "спойлер", 
                        "code": "код", "pre": "блок кода", "blockquote": "цитата",
                        "text_link": "ссылка"
                    }.get(etype, etype)
                    entities_info.append(f"• {type_name}: {count}")
            
            # Краткое подтверждение редактирования
            confirmation_text = f"✅ Форматирование из Telegram сохранено!\n" \
                              f"📝 Символов: {len(formatted_text)}\n"
            
            if entities_info:
                confirmation_text += f"🎨 Форматирование:\n" + "\n".join(entities_info) + "\n"
            
            confirmation_text += f"\n⏳ Возвращаемся к обновленному посту..."
            
            await message.answer(
                format_success_message("Пост отредактирован!", confirmation_text),
                parse_mode=get_parse_mode()
            )
            
            # Небольшая задержка для читаемости
            await asyncio.sleep(1)
            
            # Показываем обновленный пост через view_post_callback
            # Создаем фейковый callback для перенаправления
            from aiogram.types import CallbackQuery as FakeCallbackQuery
            from types import SimpleNamespace
            
            # Создаем минимальный callback объект для перенаправления
            fake_callback = SimpleNamespace()
            fake_callback.data = f"view_post_{post_id}"
            fake_callback.from_user = message.from_user
            fake_callback.message = message
            fake_callback.answer = lambda text="", show_alert=False: asyncio.create_task(asyncio.sleep(0))
            
            # Показываем обновленный пост (фото или текст)
            post = await post_crud.get_post_by_id(post_id)
            if not post:
                await message.answer("❌ Ошибка: не удалось найти обновленный пост")
                return
                
            # Определяем какую клавиатуру использовать для постов с фото
            if post.has_media:
                # Проверяем длину отредактированного текста для лимита caption
                display_text = post.processed_text or post.original_text or ""
                base_info_length = 150  # Примерная длина заголовка и доп.информации
                
                if len(display_text) + base_info_length > 1024:
                    # Текст слишком длинный для caption - используем клавиатуру с кнопкой "Показать пост"
                    from src.bot.keyboards.inline import get_post_moderation_keyboard_with_preview
                    keyboard = get_post_moderation_keyboard_with_preview(post_id)
                    logger.info("📏 Отредактированный пост слишком длинный для caption, используем кнопку 'Показать пост'")
                else:
                    # Текст помещается в caption
                    keyboard = get_post_moderation_keyboard(post_id)
            else:
                # Пост без фото
                keyboard = get_post_moderation_keyboard(post_id)
            
            # Показываем обновленное уведомление с исправленным текстом
            media_handler = get_media_handler()
            media_for_send, media_type = media_handler.get_media_for_send(post)
            
            if media_for_send:
                try:
                    # Отправляем медиа с обновленной подписью
                    caption = format_post_caption_for_moderation(post)
                    
                    from src.bot.main import get_bot_instance
                    bot = get_bot_instance()
                    
                    if media_type == 'photo':
                        await bot.send_photo(
                            chat_id=message.chat.id,
                            photo=media_for_send,
                            caption=caption,
                            reply_markup=keyboard,
                            parse_mode=get_parse_mode()
                        )
                    elif media_type == 'video':
                        await bot.send_video(
                            chat_id=message.chat.id,
                            video=media_for_send,
                            caption=caption,
                            reply_markup=keyboard,
                            parse_mode=get_parse_mode()
                        )
                    
                    logger.info("Обновленный пост с {} {} показан после редактирования", media_type, post_id)
                    
                except Exception as photo_error:
                    # Детальная обработка ошибок с фото
                    error_details = str(photo_error)
                    if "wrong remote file identifier" in error_details.lower() or "wrong padding" in error_details.lower():
                        logger.error("Некорректный photo_file_id для поста {}: {}", post_id, post.photo_file_id)
                        
                        # Очищаем photo_file_id в базе данных
                        try:
                            await post_crud.update_post(post_id, photo_file_id=None)
                            logger.info("Очищен некорректный photo_file_id для поста {}", post_id)
                        except Exception as clear_error:
                            logger.error("Ошибка очистки photo_file_id: {}", str(clear_error))
                    else:
                        logger.error("Ошибка отправки обновленного фото для поста {}: {}", post_id, error_details)
                    # Показываем как текст при ошибке фото
                    post_text = format_post_for_moderation(post)
                    await message.answer(
                        post_text,
                        reply_markup=keyboard,
                        parse_mode=get_parse_mode()
                    )
            else:
                # Пост без фото - показываем как текст
                post_text = format_post_for_moderation(post)
                await message.answer(
                    post_text,
                    reply_markup=keyboard,
                    parse_mode=get_parse_mode()
                )
            
            logger.info("Пост {} отредактирован пользователем {}: {} entities, {} символов", 
                       post_id, message.from_user.id, 
                       len(message.entities) if message.entities else 0, len(formatted_text))
        else:
            await message.answer(
                format_error_message(
                    "Ошибка сохранения",
                    "Не удалось сохранить изменения в пост."
                ),
                parse_mode=get_parse_mode()
            )
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error("Ошибка обработки редактирования поста: {}", str(e))
        await message.answer("❌ Произошла ошибка при сохранении изменений")
        await state.clear()


@moderation_router.callback_query(F.data.startswith("edit_photo_"), OwnerFilter())
async def edit_photo_callback(callback: CallbackQuery, state: FSMContext):
    """Редактирование фото поста - переход в режим редактирования медиа"""
    try:
        await callback.answer("🖼️ Режим редактирования фото")
        
        post_id = int(callback.data.replace("edit_photo_", ""))
        
        # Получаем пост
        post_crud = get_post_crud()
        post = await post_crud.get_post_by_id(post_id)
        
        if not post:
            await callback.answer("❌ Пост не найден", show_alert=True)
            return
        
        # Сохраняем ID поста в состояние
        await state.set_data({"editing_post_id": post_id})
        await state.set_state(ModerationStates.editing_post_photo)
        
        # Показываем инструкции по редактированию фото
        photo_text = f"""🖼️ {bold('Редактирование фото поста')}

📝 {bold('Пост:')} #{post_id}

📋 {bold('Инструкции:')}
{format_list_items([
    'Отправьте новое фото для замены',
    'Можно отправить фото как документ или изображение',
    'Старое фото будет заменено новым',
    'Для отмены используйте /cancel'
])}

💡 {bold('Совет:')} Отправьте фото в лучшем качестве для лучшего результата!

⚠️ {bold('Важно:')} Telegram не позволяет редактировать медиа в сообщениях. При публикации пост будет пересоздан с новым фото."""

        await safe_edit_message(callback,
            photo_text,
            parse_mode=get_parse_mode())
        
        logger.info("Пользователь {} начал редактирование фото поста {}", callback.from_user.id, post_id)
        
    except Exception as e:
        logger.error("Ошибка начала редактирования фото: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.message(ModerationStates.editing_post_photo, F.photo, OwnerFilter())
async def handle_edit_post_photo(message: Message, state: FSMContext):
    """Обработка нового фото для поста"""
    try:
        # Получаем ID поста из состояния
        data = await state.get_data()
        post_id = data.get("editing_post_id")
        
        if not post_id:
            await message.answer("❌ Ошибка: не найден ID поста для редактирования")
            await state.clear()
            return
        
        # Получаем наибольшее фото из сообщения
        photo = message.photo[-1]  # Последнее фото в массиве - наибольшего размера
        
        # Получаем информацию о фото
        photo_file_id = photo.file_id
        photo_width = photo.width
        photo_height = photo.height
        photo_file_size = photo.file_size
        
        logger.info("Получено новое фото: {}x{}, размер: {} байт", 
                   photo_width, photo_height, photo_file_size)
        
        # Обновляем file_id в БД (Bot API автоматически управляет файлами)
        try:
            post_crud = get_post_crud()
            success = await post_crud.update_post(
                post_id,
                photo_file_id=photo_file_id
            )
            
            if success:
                # Показываем результат
                result_text = format_success_message(
                    "Фото обновлено!",
                    f"🖼️ {bold('Новое фото установлено')}\n"
                    f"📐 Размер: {photo_width}x{photo_height}\n"
                    f"📊 Размер файла: {photo_file_size // 1024 if photo_file_size else '?'} КБ\n"
                    f"🆔 File ID: {code(photo_file_id[:20] + '...')}\n\n"
                    f"✅ Фото будет использовано при публикации поста"
                )
                
                # Возвращаем кнопки модерации
                keyboard = get_post_moderation_keyboard(post_id)
                
                await message.answer(
                    result_text,
                    reply_markup=keyboard,
                    parse_mode=get_parse_mode()
                )
                
                logger.info("Фото поста {} обновлено пользователем {}: {}", 
                           post_id, message.from_user.id, photo_file_id)
            else:
                await message.answer(
                    format_error_message(
                        "Ошибка сохранения",
                        "Не удалось сохранить новое фото."
                    ),
                    parse_mode=get_parse_mode()
                )
                
        except Exception as media_error:
            logger.error("Ошибка обработки медиа: {}", str(media_error))
            await message.answer(
                format_error_message(
                    "Ошибка обработки фото", 
                    "Не удалось обработать загруженное фото."
                ),
                parse_mode=get_parse_mode()
            )
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error("Ошибка обработки нового фото: {}", str(e))
        await message.answer("❌ Произошла ошибка при загрузке фото")
        await state.clear()


@moderation_router.message(ModerationStates.editing_post_photo, ~F.photo, OwnerFilter())
async def handle_edit_photo_invalid(message: Message, state: FSMContext):
    """Обработка неправильного типа контента при редактировании фото"""
    try:
        await message.answer(
            f"❌ {bold('Неверный тип контента')}\n\n"
            f"Пожалуйста, отправьте {bold('фото')} для замены.\n"
            f"Для отмены используйте /cancel",
            parse_mode=get_parse_mode())
        
    except Exception as e:
        logger.error("Ошибка обработки неверного контента: {}", str(e))


@moderation_router.message(ModerationStates.editing_post_photo, F.document, OwnerFilter())
async def handle_edit_post_document(message: Message, state: FSMContext):
    """Обработка документа (фото) для поста"""
    try:
        # Проверяем что это изображение
        document = message.document
        if not document.mime_type.startswith('image/'):
            await message.answer(
                f"❌ {bold('Неверный тип файла')}\n\n"
                f"Пожалуйста, отправьте изображение (фото).\n"
                f"Получен: {code(document.mime_type)}",
                parse_mode=get_parse_mode()
            )
            return
        
        # Получаем ID поста из состояния
        data = await state.get_data()
        post_id = data.get("editing_post_id")
        
        if not post_id:
            await message.answer("❌ Ошибка: не найден ID поста для редактирования")
            await state.clear()
            return
        
        # Получаем информацию о документе
        doc_file_id = document.file_id
        doc_file_name = document.file_name or "image"
        doc_file_size = document.file_size
        
        logger.info("Получен документ как фото: {}, размер: {} байт", 
                   doc_file_name, doc_file_size)
        
        # Обновляем file_id в БД
        post_crud = get_post_crud()
        success = await post_crud.update_post(
            post_id,
            photo_file_id=doc_file_id
        )
        
        if success:
            # Показываем результат
            result_text = format_success_message(
                "Фото обновлено!",
                f"🖼️ {bold('Новое фото установлено (документ)')}\n"
                f"📄 Имя файла: {code(doc_file_name)}\n"
                f"📊 Размер: {doc_file_size // 1024 if doc_file_size else '?'} КБ\n"
                f"🆔 File ID: {code(doc_file_id[:20] + '...')}\n\n"
                f"✅ Фото будет использовано при публикации поста"
            )
            
            # Возвращаем кнопки модерации
            keyboard = get_post_moderation_keyboard(post_id)
            
            await message.answer(
                result_text,
                reply_markup=keyboard,
                parse_mode=get_parse_mode()
            )
            
            logger.info("Фото поста {} обновлено документом пользователем {}: {}", 
                       post_id, message.from_user.id, doc_file_id)
        else:
            await message.answer(
                format_error_message(
                    "Ошибка сохранения",
                    "Не удалось сохранить новое фото."
                ),
                parse_mode=get_parse_mode()
            )
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error("Ошибка обработки документа как фото: {}", str(e))
        await message.answer("❌ Произошла ошибка при загрузке документа")
        await state.clear()


@moderation_router.message(Command("cancel"), OwnerFilter())
async def cancel_moderation_action(message: Message, state: FSMContext):
    """Отмена текущего действия модерации"""
    try:
        current_state = await state.get_state()
        
        if current_state:
            await state.clear()
            
            state_names = {
                "ModerationStates:editing_post_text": "редактирования текста",
                "ModerationStates:editing_post_photo": "редактирования фото",
                "ModerationStates:setting_schedule_time": "настройки времени",
                "ModerationStates:adding_moderation_note": "добавления заметки"
            }
            
            action_name = state_names.get(current_state, "действия")
            
            await message.answer(
                format_success_message(
                    "Действие отменено",
                    f"Режим {action_name} отменен.\nВы можете продолжить модерацию постов."
                ),
                parse_mode=get_parse_mode()
            )
            
            logger.info("Пользователь {} отменил действие: {}", message.from_user.id, current_state)
        else:
            await message.answer(
                "ℹ️ Нет активных действий для отмены",
                parse_mode=get_parse_mode()
            )
            
    except Exception as e:
        logger.error("Ошибка отмены действия: {}", str(e))
        await message.answer("❌ Произошла ошибка при отмене действия")


async def publish_post_now(post_id: int, use_premium_emoji: bool = True) -> bool:
    """
    Опубликовать пост в целевом канале

    Args:
        post_id: ID поста
        use_premium_emoji: Использовать Premium Custom Emoji через UserBot

    Returns:
        True если публикация успешна
    """
    try:
        post_crud = get_post_crud()
        post = await post_crud.get_post_by_id(post_id)

        if not post:
            logger.error("Пост {} не найден для публикации", post_id)
            return False

        config = get_config()
        target_channel_id = config.TARGET_CHANNEL_ID

        if not target_channel_id:
            logger.error("TARGET_CHANNEL_ID не настроен")
            return False

        # Текст для публикации (используем обработанный или оригинальный)
        post_text = post.processed_text or post.original_text or ""

        if not post_text.strip():
            logger.error("Пост {} не имеет текста для публикации", post_id)
            return False

        # Пробуем опубликовать через UserBot с Premium Emoji
        if use_premium_emoji:
            try:
                from src.userbot.publisher import get_userbot_publisher

                publisher = await get_userbot_publisher()

                if publisher and publisher.is_available:
                    logger.info("Публикуем пост {} через UserBot с Premium Emoji", post_id)

                    # Получаем пути к медиа
                    photo_path = post.photo_path if post.has_photo else None
                    video_path = post.video_path if post.has_video else None

                    message_id = await publisher.publish_post(
                        channel_id=target_channel_id,
                        text=post_text,
                        photo_path=photo_path,
                        video_path=video_path,
                        pin_post=post.pin_post,
                        add_footer=True
                    )

                    if message_id:
                        # Обновляем статус поста
                        await post_crud.update_post_status(post_id, PostStatus.POSTED)
                        await post_crud.update_post(post_id, posted_date=datetime.now())
                        logger.info("Пост {} опубликован через UserBot, message_id: {}",
                                   post_id, message_id)
                        return True
                    else:
                        logger.warning("Не удалось опубликовать через UserBot, fallback на Bot API")
                else:
                    logger.debug("UserbotPublisher недоступен, используем Bot API")

            except Exception as userbot_error:
                logger.warning("Ошибка публикации через UserBot: {}, fallback на Bot API",
                              str(userbot_error))

        # Fallback: публикация через Bot API (без Premium Emoji)
        logger.info("Публикуем пост {} в канал {} через Bot API", post_id, target_channel_id)
        
        # Получаем экземпляр бота
        from src.bot.main import get_bot_instance
        bot = get_bot_instance()

        # Добавляем футер с полезными ссылками (HTML режим для Bot API)
        post_text_with_footer = add_footer_to_post(post_text, parse_mode="HTML")

        try:
            # Публикуем в зависимости от наличия медиа
            media_handler = get_media_handler()
            media_for_send, media_type = media_handler.get_media_for_send(post)
            
            if media_for_send and media_type == 'photo':
                # Публикуем фото с подписью
                sent_message = await bot.send_photo(
                    chat_id=target_channel_id,
                    photo=media_for_send,
                    caption=post_text_with_footer,
                    parse_mode=get_parse_mode()
                )
                logger.info("Фото пост {} опубликован в канал {}, message_id: {}",
                           post_id, target_channel_id, sent_message.message_id)
            elif media_for_send and media_type == 'video':
                # Публикуем видео с подписью
                sent_message = await bot.send_video(
                    chat_id=target_channel_id,
                    video=media_for_send,
                    caption=post_text_with_footer,
                    parse_mode=get_parse_mode()
                )
                logger.info("Видео пост {} опубликован в канал {}, message_id: {}",
                           post_id, target_channel_id, sent_message.message_id)
            else:
                # Публикуем только текст
                sent_message = await bot.send_message(
                    chat_id=target_channel_id,
                    text=post_text_with_footer,
                    parse_mode=get_parse_mode()
                )
                logger.info("Текст пост {} опубликован в канал {}, message_id: {}",
                           post_id, target_channel_id, sent_message.message_id)
            
            # Обновляем статус поста
            await post_crud.update_post_status(post_id, PostStatus.POSTED)
            await post_crud.update_post(post_id, posted_date=datetime.now())
            
            # Проверяем нужно ли закрепить пост (только для ежедневных постов)
            try:
                # Получаем информацию о посте для проверки флага pin_post
                post_data = await post_crud.get_by_id(post_id)
                
                # Закрепляем только если у поста установлен флаг pin_post
                if post_data and post_data.pin_post:
                    from src.database.crud.setting import get_setting_crud
                    setting_crud = get_setting_crud()
                    pin_enabled_setting = await setting_crud.get_setting("daily_post.pin_enabled")
                    pin_enabled = pin_enabled_setting and pin_enabled_setting.lower() == 'true'
                    
                    if pin_enabled:
                        # Закрепляем пост
                        await bot.pin_chat_message(
                            chat_id=target_channel_id,
                            message_id=sent_message.message_id,
                            disable_notification=True  # Не уведомляем подписчиков о закреплении
                        )
                        logger.info("📌 Ежедневный пост {} закреплен в канале", post_id)
                        
            except Exception as pin_error:
                # Ошибка закрепления не критична
                logger.warning("⚠️ Не удалось закрепить пост {}: {}", post_id, str(pin_error))
            
            logger.info("Пост {} успешно опубликован в канал {}", post_id, target_channel_id)
            return True
            
        except Exception as publish_error:
            logger.error("Ошибка публикации поста {} в канал {}: {}", 
                        post_id, target_channel_id, str(publish_error))
            
            # Добавляем детализацию ошибки
            error_type = type(publish_error).__name__
            if "Forbidden" in str(publish_error) or "403" in str(publish_error):
                logger.error("❌ ОШИБКА ДОСТУПА: Бот не является администратором канала {} или не имеет права на отправку сообщений", target_channel_id)
            elif "Bad Request" in str(publish_error) or "400" in str(publish_error):
                logger.error("❌ ОШИБКА ЗАПРОСА: Неверный ID канала {} или проблема с контентом поста", target_channel_id)
            elif "file_id" in str(publish_error).lower() or "wrong remote file identifier" in str(publish_error).lower() or "wrong padding" in str(publish_error).lower():
                logger.error("❌ ОШИБКА МЕДИА: Некорректный photo_file_id: {}", post.photo_file_id)
                
                # Очищаем некорректный photo_file_id в базе данных
                try:
                    post_crud = get_post_crud()
                    await post_crud.update_post(post_id, photo_file_id=None)
                    logger.info("Очищен некорректный photo_file_id при публикации поста {}", post_id)
                except Exception as clear_error:
                    logger.error("Ошибка очистки photo_file_id при публикации: {}", str(clear_error))
            else:
                logger.error("❌ НЕИЗВЕСТНАЯ ОШИБКА [{}]: {}", error_type, str(publish_error))
            
            return False
        
    except Exception as e:
        logger.error("Ошибка публикации поста {}: {}", post_id, str(e))
        return False


async def show_next_pending_post(callback: CallbackQuery) -> None:
    """Показать следующий пост на модерации"""
    try:
        post_crud = get_post_crud()
        pending_posts = await post_crud.get_posts_by_status(PostStatus.PENDING)
        
        if not pending_posts:
            success_text = format_success_message(
                "Все посты обработаны!",
                "Нет больше постов на модерации.\nНовые посты будут появляться автоматически."
            )
            await safe_edit_message(callback, success_text, None, get_parse_mode())
            return
        
        # Показываем первый пост из списка с поддержкой фото
        next_post = pending_posts[0]
        keyboard = get_post_moderation_keyboard(next_post.id)
        
        # Проверяем есть ли медиа у следующего поста
        media_handler = get_media_handler()
        media_for_send, media_type = media_handler.get_media_for_send(next_post)
        
        if media_for_send:
            try:
                # Формируем подпись для медиа
                caption = format_post_caption_for_moderation(next_post)
                
                # Отправляем медиа с подписью
                from src.bot.main import get_bot_instance
                bot = get_bot_instance()
                
                if media_type == 'photo':
                    await bot.send_photo(
                        chat_id=callback.message.chat.id,
                        photo=media_for_send,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode=get_parse_mode()
                    )
                elif media_type == 'video':
                    await bot.send_video(
                        chat_id=callback.message.chat.id,
                        video=media_for_send,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode=get_parse_mode()
                    )
                
                # Удаляем старое сообщение
                try:
                    await callback.message.delete()
                except Exception as delete_error:
                    logger.debug("Не удалось удалить старое сообщение: {}", str(delete_error))
                
                logger.info("Следующий пост с фото {} показан на модерацию", next_post.id)
                
            except Exception as photo_error:
                logger.error("Ошибка отправки фото для следующего поста {}: {}", next_post.id, str(photo_error))
                # Показываем как текст при ошибке фото
                post_text = format_post_for_moderation(next_post)
                post_text += f"\n\n⚠️ {bold('Ошибка загрузки фото')}: {str(photo_error)}"
                
                await safe_edit_message(callback, post_text, keyboard, get_parse_mode())
        else:
            # Пост без фото
            post_text = format_post_for_moderation(next_post)
            
            await safe_edit_message(callback,
                post_text,
                reply_markup=keyboard,
                parse_mode=get_parse_mode()
            )
        
        logger.debug("Показан следующий пост на модерации: {}", next_post.id)
        
    except Exception as e:
        logger.error("Ошибка показа следующего поста: {}", str(e))


def _get_channel_display_name(channel_id: int) -> str:
    """Получить красивое имя канала для отображения"""
    try:
        from src.database.connection import get_db_connection
        
        # Пытаемся получить username из БД
        import asyncio
        async def get_channel_info():
            try:
                async with get_db_connection() as conn:
                    cursor = await conn.execute(
                        "SELECT username, title FROM channels WHERE channel_id = ?",
                        (channel_id,)
                    )
                    row = await cursor.fetchone()
                    
                    if row:
                        username, title = row
                        if username:
                            return f"@{username}"
                        elif title:
                            return f'"{title}"'
                    
                    return f"ID {channel_id}"
                    
            except Exception:
                return f"ID {channel_id}"
        
        # Выполняем async функцию в sync контексте
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Если уже в async контексте, используем синхронную версию
                return f"ID {channel_id}"
            else:
                return loop.run_until_complete(get_channel_info())
        except Exception:
            return f"ID {channel_id}"
            
    except Exception:
        return f"ID {channel_id}"


def format_post_caption_for_moderation(post) -> str:
    """Форматировать подпись к фото для модерации (max 1024 символа)"""
    try:
        # Определяем есть ли обработанный текст (прошел рестайлинг)
        has_processed = post.processed_text and post.processed_text.strip()
        post_status = "🎨 Обработан" if has_processed else "📄 Оригинал"
        
        # Краткая информация о посте для caption
        header = f"""📝 {bold(f'Пост #{post.id}')} ({post_status})
📺 Канал: {_get_channel_display_name(post.channel_id)}
🕐 {post.created_at.strftime('%d.%m %H:%M') if post.created_at else 'неизвестно'}"""
        
        # Релевантность если есть
        if post.relevance_score:
            relevance_emoji = "🟢" if post.relevance_score >= 7 else "🟡" if post.relevance_score >= 5 else "🔴"
            header += f"\n{relevance_emoji} Релевантность: {post.relevance_score}/10"
        
        # Используем либо обработанный, либо оригинальный текст
        display_text = post.processed_text if has_processed else post.original_text
        display_text = display_text or "Нет текста"
        
        # Формируем базовый caption
        base_caption = f"{header}\n\n{display_text}"
        
        # Подготавливаем дополнительный текст
        extra_text = ""
        if not has_processed:
            extra_text = "\n\n⚡️ Нажмите 'Рестайлинг' для AI обработки"
        elif post.source_link:
            extra_text = f"\n\n🔗 {link('Источник', post.source_link)}"
        
        # Формируем полный caption с дополнительным текстом
        full_caption = base_caption + extra_text
        
        # Проверяем лимит Telegram для caption к фото (1024 символа)
        if len(full_caption) > 1024:
            # Если превышает лимит, проверяем базовый caption без дополнительного текста
            if len(base_caption) > 1024:
                # НЕ обрезаем HTML (ломает теги), показываем краткую версию
                display_text = f"📄 Текст слишком длинный ({len(display_text)} символов)\n⬇️ Используйте кнопку 'Показать пост' для просмотра"
                caption = f"{header}\n\n{display_text}"
            else:
                # Используем базовый caption без дополнительного текста
                caption = base_caption
        else:
            # Полный caption помещается в лимит
            caption = full_caption
        
        return caption
        
    except Exception as e:
        logger.error("Ошибка форматирования подписи поста для модерации: {}", str(e))
        return f"❌ Ошибка отображения поста #{post.id if post else 'неизвестно'}"


def format_post_for_moderation(post) -> str:
    """Форматировать пост для модерации (полная версия для текстовых сообщений)"""
    try:
        # Определяем есть ли обработанный текст (прошел рестайлинг)
        has_processed = post.processed_text and post.processed_text.strip()
        processing_status = "🎨 AI обработан" if has_processed else "📄 Оригинальный"
        
        # Получаем информацию о канале с username
        channel_info = f"📺 Канал: {_get_channel_display_name(post.channel_id)}"
        
        # Релевантность и тональность (только если есть обработка)
        ai_analysis_text = ""
        if post.relevance_score or post.sentiment:
            relevance_text = ""
            if post.relevance_score:
                relevance_emoji = "🟢" if post.relevance_score >= 7 else "🟡" if post.relevance_score >= 5 else "🔴"
                relevance_text = f"{relevance_emoji} Релевантность: {post.relevance_score}/10"
            
            sentiment_text = ""
            if post.sentiment:
                sentiment_emoji = {"positive": "😊", "negative": "😔", "neutral": "😐"}.get(post.sentiment, "❓")
                sentiment_text = f"{sentiment_emoji} Тональность: {post.sentiment}"
            
            if relevance_text or sentiment_text:
                ai_analysis_text = f"\n🤖 {bold('AI анализ:')}\n{relevance_text}\n{sentiment_text}\n"
        
        # Текст поста - показываем соответствующий версии
        post_text_display = post.processed_text if has_processed else post.original_text
        post_text_display = post_text_display or "Нет текста"
        
        # Формируем итоговое сообщение
        result = f"""📝 {bold(f'Пост на модерации #{post.id}')}

{channel_info}
🕐 Получен: {post.created_at.strftime('%d.%m.%Y %H:%M') if post.created_at else 'неизвестно'}
📋 Статус: {processing_status}{ai_analysis_text}

📄 {bold('Текст поста:')}
{post_text_display}"""
        
        # Добавляем информацию о фото если есть
        if post.has_media:
            result += f"\n\n🖼️ {bold('Содержит изображение')}"
        
        # Добавляем ссылку на источник
        if post.source_link:
            result += f"\n\n🔗 {link('Ссылка на оригинал', post.source_link)}"
        
        # Добавляем призыв к действию если пост не обработан
        if not has_processed:
            result += f"\n\n⚡️ {bold('Используйте кнопку Рестайлинг для AI обработки')}"
        
        return result
        
    except Exception as e:
        logger.error("Ошибка форматирования поста для модерации: {}", str(e))
        return f"❌ Ошибка отображения поста #{post.id if post else 'неизвестно'}"


def format_ai_analysis(post) -> str:
    """Форматировать AI анализ поста"""
    try:
        analysis_text = f"""🤖 <b>AI Анализ поста #{post.id}</b>

📊 <b>Результаты анализа:</b>"""
        
        # Релевантность
        if post.relevance_score is not None:
            relevance_emoji = "🟢" if post.relevance_score >= 7 else "🟡" if post.relevance_score >= 5 else "🔴"
            analysis_text += f"\n{relevance_emoji} <b>Релевантность:</b> {post.relevance_score}/10"
        
        # Тональность
        if post.sentiment:
            sentiment_emoji = {"positive": "😊", "negative": "😔", "neutral": "😐"}.get(post.sentiment, "❓")
            sentiment_names = {"positive": "Позитивная", "negative": "Негативная", "neutral": "Нейтральная"}
            analysis_text += f"\n{sentiment_emoji} <b>Тональность:</b> {sentiment_names.get(post.sentiment, post.sentiment)}"
        
        # AI анализ если есть
        if post.ai_analysis:
            analysis_text += f"\n\n🔍 <b>Детальный анализ:</b>\n{post.ai_analysis[:500]}{'...' if len(post.ai_analysis) > 500 else ''}"
        
        # Рекомендации
        analysis_text += "\n\n💡 <b>Рекомендации:</b>"
        if post.relevance_score and post.relevance_score >= 7:
            analysis_text += "\n✅ Пост релевантен - рекомендуется к публикации"
        elif post.relevance_score and post.relevance_score >= 5:
            analysis_text += "\n🤔 Средняя релевантность - рассмотрите редактирование"
        else:
            analysis_text += "\n❌ Низкая релевантность - рекомендуется отклонить"
        
        return analysis_text
        
    except Exception as e:
        logger.error("Ошибка форматирования AI анализа: {}", str(e))
        return f"❌ Ошибка отображения анализа поста #{post.id if post else 'неизвестно'}"


@moderation_router.callback_query(F.data.startswith("show_full_post_"), OwnerFilter())
async def show_full_post_callback(callback: CallbackQuery):
    """Показать полный текст поста без ограничений"""
    try:
        await callback.answer()
        
        post_id = int(callback.data.replace("show_full_post_", ""))
        
        # Получаем пост из БД
        post_crud = get_post_crud()
        post = await post_crud.get_post_by_id(post_id)
        
        if not post:
            await callback.message.answer("❌ Пост не найден")
            return
        
        # Формируем полный текст поста
        full_post_text = post.processed_text if post.processed_text else post.original_text
        
        # Формируем сообщение с полным текстом
        full_message = f"""📄 {bold(f'Полный текст поста #{post.id}')}

📺 Канал: {_get_channel_display_name(post.channel_id)}

{full_post_text}"""
        
        # Если текст все еще слишком длинный для одного сообщения, разбиваем на части
        if len(full_message) > 4048:
            # Отправляем заголовок
            header = f"""📄 {bold(f'Полный текст поста #{post.id}')}

📺 Канал: {_get_channel_display_name(post.channel_id)}

Текст разбит на несколько сообщений:
"""
            await callback.message.answer(header, parse_mode=get_parse_mode())
            
            # Разбиваем текст на части по 3800 символов (с запасом для заголовков)
            text_parts = []
            current_part = ""
            
            for line in full_post_text.split('\n'):
                if len(current_part + line + '\n') > 3800:
                    if current_part:
                        text_parts.append(current_part.strip())
                        current_part = line + '\n'
                    else:
                        # Если даже одна строка слишком длинная, НЕ обрезаем (может ломать HTML)
                        # Добавляем как есть - Telegram сам обрежет если нужно
                        text_parts.append(line)
                        current_part = ""
                else:
                    current_part += line + '\n'
            
            if current_part.strip():
                text_parts.append(current_part.strip())
            
            # Отправляем части
            for i, part in enumerate(text_parts, 1):
                part_message = f"""📄 {bold(f'Часть {i}/{len(text_parts)}')}

{part}"""
                await callback.message.answer(part_message, parse_mode=get_parse_mode())
        else:
            # Отправляем как одно сообщение
            await callback.message.answer(full_message, parse_mode=get_parse_mode())
        
        logger.info("Показан полный текст поста {} пользователю {}", post_id, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа полного поста: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data.startswith("reanalyze_post_"), OwnerFilter())
async def reanalyze_post_callback(callback: CallbackQuery):
    """Повторный AI анализ поста"""
    try:
        await callback.answer()
        
        # Извлекаем ID поста из callback_data
        post_id = int(callback.data.split("_")[-1])
        
        # Получаем пост из БД
        post_crud = get_post_crud()
        post = await post_crud.get_post_by_id(post_id)
        
        if not post:
            await safe_edit_message(callback,
                "❌ Пост не найден",
                parse_mode=get_parse_mode()
            )
            return
        
        # Показываем индикатор загрузки
        await safe_edit_message(callback,
            f"🔄 <b>Повторный AI анализ поста #{post_id}</b>\n\n"
            "⏳ Пожалуйста, подождите...\n"
            "Пост анализируется заново с учетом актуальных примеров стиля.",
            parse_mode=get_parse_mode())
        
        try:
            # Запускаем повторный AI анализ
            from src.ai.processor import get_ai_processor
            ai_processor = get_ai_processor()
            
            # Сбрасываем предыдущие результаты анализа
            post.relevance_score = None
            post.sentiment = None
            post.processed_text = None
            post.ai_analysis = None
            
            # Запускаем новый анализ
            processing_result = await ai_processor.process_post(post)
            
            if processing_result.get("is_relevant"):
                result_text = f"""✅ <b>Повторный анализ завершен!</b>

🔄 Пост переанализирован с новыми результатами:
🟢 Релевантность: {processing_result.get('relevance_score', 0)}/10
{processing_result.get('sentiment', 'neutral')} Тональность: {processing_result.get('sentiment', 'неизвестно')}

📝 Обновленный текст готов к модерации."""
            else:
                result_text = f"""❌ <b>Повторный анализ завершен</b>

🔄 После переанализа:  
🔴 Релевантность: {processing_result.get('relevance_score', 0)}/10
❌ Пост по-прежнему не соответствует критериям

Рекомендуется отклонить пост."""
            
            # Обновляем клавиатуру
            keyboard = get_post_moderation_keyboard(post_id)
            
            # Добавляем кнопку повторного анализа снова
            from aiogram.types import InlineKeyboardButton
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text="🔄 Повторный AI анализ",
                    callback_data=f"reanalyze_post_{post_id}"
                )
            ])
            
            await safe_edit_message(callback,
                result_text,
                reply_markup=keyboard,
                parse_mode=get_parse_mode()
            )
            
            logger.info("Повторный AI анализ поста {} завершен для пользователя {}", 
                       post_id, callback.from_user.id)
            
        except Exception as ai_error:
            logger.error("Ошибка повторного AI анализа поста {}: {}", post_id, str(ai_error))
            
            await safe_edit_message(callback,
                f"❌ <b>Ошибка повторного анализа</b>\n\n"
                f"Не удалось выполнить повторный AI анализ поста #{post_id}.\n"
                f"Попробуйте позже или обратитесь к администратору.\n\n"
                f"Ошибка: {str(ai_error)}",
                parse_mode=get_parse_mode()
            )
        
    except Exception as e:
        logger.error("Ошибка обработки повторного анализа: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data == "approved_posts", OwnerFilter())
async def approved_posts_callback(callback: CallbackQuery):
    """Показать одобренные посты"""
    try:
        await callback.answer()
        
        post_crud = get_post_crud()
        approved_posts = await post_crud.get_posts_by_status(PostStatus.APPROVED)
        
        if not approved_posts:
            await safe_edit_message(callback,
                format_success_message(
                    "Нет одобренных постов",
                    "Пока нет постов со статусом 'одобрен'.\nОдобренные посты будут появляться здесь."
                ),
                parse_mode=get_parse_mode()
            )
            return
        
        posts_text = f"✅ {bold(f'Одобренные посты ({len(approved_posts)})')}\n\n"
        posts_text += "Выберите пост для просмотра:"
        
        keyboard = get_posts_list_keyboard(approved_posts, "approved", page=1)
        
        await safe_edit_message(callback, posts_text, keyboard, get_parse_mode())
        
        logger.info("Показаны одобренные посты: {} постов", len(approved_posts))
        
    except Exception as e:
        logger.error("Ошибка получения одобренных постов: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data == "rejected_posts", OwnerFilter())
async def rejected_posts_callback(callback: CallbackQuery):
    """Показать отклоненные посты"""
    try:
        await callback.answer()
        
        post_crud = get_post_crud()
        rejected_posts = await post_crud.get_posts_by_status(PostStatus.REJECTED)
        
        if not rejected_posts:
            await safe_edit_message(callback,
                format_success_message(
                    "Нет отклоненных постов",
                    "Пока нет постов со статусом 'отклонен'.\nОтклоненные посты будут появляться здесь."
                ),
                parse_mode=get_parse_mode()
            )
            return
        
        posts_text = f"❌ {bold(f'Отклоненные посты ({len(rejected_posts)})')}\n\n"
        posts_text += "Выберите пост для просмотра:"
        
        keyboard = get_posts_list_keyboard(rejected_posts, "rejected", page=1)
        
        await safe_edit_message(callback, posts_text, keyboard, get_parse_mode())
        
        logger.info("Показаны отклоненные посты: {} постов", len(rejected_posts))
        
    except Exception as e:
        logger.error("Ошибка получения отклоненных постов: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data == "published_posts", OwnerFilter())
async def published_posts_callback(callback: CallbackQuery):
    """Показать опубликованные посты"""
    try:
        await callback.answer()
        
        post_crud = get_post_crud()
        published_posts = await post_crud.get_posts_by_status(PostStatus.POSTED)
        
        if not published_posts:
            await safe_edit_message(callback,
                format_success_message(
                    "Нет опубликованных постов",
                    "Пока нет постов со статусом 'опубликован'.\nОпубликованные посты будут появляться здесь."
                ),
                parse_mode=get_parse_mode()
            )
            return
        
        posts_text = f"📤 {bold(f'Опубликованные посты ({len(published_posts)})')}\n\n"
        posts_text += "Выберите пост для просмотра:"
        
        keyboard = get_posts_list_keyboard(published_posts, "published", page=1)
        
        await safe_edit_message(callback, posts_text, keyboard, get_parse_mode())
        
        logger.info("Показаны опубликованные посты: {} постов", len(published_posts))
        
    except Exception as e:
        logger.error("Ошибка получения опубликованных постов: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data == "scheduled_posts", OwnerFilter())
async def scheduled_posts_callback(callback: CallbackQuery):
    """Показать запланированные посты"""
    try:
        await callback.answer()
        
        post_crud = get_post_crud()
        scheduled_posts = await post_crud.get_posts_by_status(PostStatus.SCHEDULED)
        
        if not scheduled_posts:
            await safe_edit_message(callback,
                format_success_message(
                    "Нет запланированных постов",
                    "Пока нет постов со статусом 'запланирован'.\nЗапланированные посты будут появляться здесь."
                ),
                parse_mode=get_parse_mode()
            )
            return
        
        posts_text = f"⏰ {bold(f'Запланированные посты ({len(scheduled_posts)})')}\n\n"
        posts_text += "Выберите пост для просмотра:"
        
        keyboard = get_posts_list_keyboard(scheduled_posts, "scheduled", page=1)
        
        await safe_edit_message(callback, posts_text, keyboard, get_parse_mode())
        
        logger.info("Показаны запланированные посты: {} постов", len(scheduled_posts))

    except Exception as e:
        logger.error("Ошибка получения запланированных постов: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data.regexp(r"^posts_(pending|approved|rejected|published|scheduled)_page_(\d+)$"), OwnerFilter())
async def posts_pagination_callback(callback: CallbackQuery):
    """Обработчик пагинации списков постов"""
    try:
        await callback.answer()

        # Парсим статус и номер страницы из callback_data
        # Формат: posts_{status}_page_{page_number}
        data = callback.data
        parts = data.split("_page_")
        status_part = parts[0].replace("posts_", "")
        page = int(parts[1])

        # Маппинг статусов
        status_map = {
            "pending": PostStatus.PENDING,
            "approved": PostStatus.APPROVED,
            "rejected": PostStatus.REJECTED,
            "published": PostStatus.POSTED,
            "scheduled": PostStatus.SCHEDULED
        }

        status_titles = {
            "pending": ("⏳", "Посты на модерации"),
            "approved": ("✅", "Одобренные посты"),
            "rejected": ("❌", "Отклоненные посты"),
            "published": ("📤", "Опубликованные посты"),
            "scheduled": ("⏰", "Запланированные посты")
        }

        post_status = status_map.get(status_part)
        if not post_status:
            await callback.answer("❌ Неизвестный статус", show_alert=True)
            return

        post_crud = get_post_crud()
        posts = await post_crud.get_posts_by_status(post_status)

        if not posts:
            await callback.answer("❌ Посты не найдены", show_alert=True)
            return

        icon, title = status_titles.get(status_part, ("📄", "Посты"))
        posts_text = f"{icon} {bold(f'{title} ({len(posts)})')}\n\n"
        posts_text += "Выберите пост для просмотра:"

        keyboard = get_posts_list_keyboard(posts, status_part, page=page)

        await safe_edit_message(callback, posts_text, keyboard, get_parse_mode())

        logger.info("Пагинация постов {}: страница {}", status_part, page)

    except Exception as e:
        logger.error("Ошибка пагинации постов: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data == "search_posts", OwnerFilter())
async def search_posts_callback(callback: CallbackQuery):
    """Поиск по постам (пока заглушка)"""
    try:
        await callback.answer("🔍 Поиск в разработке")
        
        search_text = f"""🔍 {bold('Поиск по постам')}

🚧 {bold('Функция в разработке')}

Планируемые возможности поиска:
• По тексту поста
• По релевантности (баллы)
• По дате создания
• По каналу-источнику
• По статусу поста

⚙️ Функция будет добавлена в следующих обновлениях."""
        
        from src.bot.keyboards.inline import get_moderation_menu_keyboard
        post_crud = get_post_crud()
        pending_posts = await post_crud.get_posts_by_status(PostStatus.PENDING)
        keyboard = get_moderation_menu_keyboard(len(pending_posts))
        
        await safe_edit_message(callback,
            search_text,
            keyboard, get_parse_mode())
        
        logger.debug("Показана заглушка поиска постов пользователю {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа поиска постов: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data == "moderation_settings", OwnerFilter())
async def moderation_settings_callback(callback: CallbackQuery):
    """Настройки модерации (пока заглушка)"""
    try:
        await callback.answer()
        
        config = get_config()
        
        settings_text = f"""⚙️ {bold('Настройки модерации')}

📊 {bold('Текущие настройки:')}
• Порог релевантности: {config.RELEVANCE_THRESHOLD}/10
• AI модель: {config.OPENAI_MODEL}
• Интервал мониторинга: {config.MONITORING_INTERVAL} сек

🔧 {bold('Возможности (в разработке):')}
• Изменение порога релевантности
• Настройка автоодобрения
• Фильтры по каналам
• Уведомления о новых постах
• Настройки AI анализа

⚙️ Полные настройки будут добавлены в следующих обновлениях."""
        
        from src.bot.keyboards.inline import get_moderation_menu_keyboard
        post_crud = get_post_crud()
        pending_posts = await post_crud.get_posts_by_status(PostStatus.PENDING)
        keyboard = get_moderation_menu_keyboard(len(pending_posts))
        
        await safe_edit_message(callback,
            settings_text,
            keyboard, get_parse_mode())
        
        logger.debug("Показаны настройки модерации пользователю {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа настроек модерации: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


async def _send_updated_post_notification(callback: CallbackQuery, post_crud, post_id: int, restyle_result: dict) -> None:
    """
    Отправить обновленное уведомление с обработанным контентом
    
    Args:
        callback: Callback query для получения chat_id
        post_crud: CRUD для работы с постами
        post_id: ID поста
        restyle_result: Результат рестайлинга
    """
    try:
        logger.info("📬 Отправка обновленного уведомления для поста {}", post_id)
        
        # Получаем обновленный пост из БД
        updated_post = await post_crud.get_post_by_id(post_id)
        if not updated_post:
            logger.error("Не удалось получить обновленный пост {} из БД", post_id)
            return
        
        # Создаем уведомление с обработанным контентом
        notification_text = f"""🎉 {bold('Пост успешно обработан!')}

📝 Пост #{post_id} - {bold('AI рестайлинг завершен')}

✅ {bold('ЭТАПЫ ОБРАБОТКИ:')}
• Этап 1: Максимальная уникализация - {bold('завершена')}
• Этап 2: HTML форматирование - {bold('завершена')}

📊 {bold('Статистика:')}
• Исходный размер: {restyle_result.get('original_length', 0)} символов
• Финальный размер: {restyle_result.get('final_length', 0)} символов

📄 {bold('ОБРАБОТАННЫЙ ТЕКСТ:')}
{updated_post.processed_text or 'Ошибка получения текста'}"""

        # Получаем клавиатуру модерации для итогового уведомления
        keyboard = get_post_moderation_keyboard(post_id)
        
        # Если есть медиа, отправляем с медиа
        media_handler = get_media_handler()
        media_for_send, media_type = media_handler.get_media_for_send(updated_post)
        
        if media_for_send:
            try:
                # Создаем caption с обработанным текстом
                caption = _format_processed_post_caption(updated_post, restyle_result)
                
                # Telegram ограничение: 1024 символа для caption к фото
                if len(caption) > 1024:
                    # НЕ обрезаем HTML (ломает теги), показываем краткую информацию
                    caption = f"""🎉 {bold(f'Пост #{post_id} - AI обработан!')}
✅ Двухэтапный рестайлинг завершен
📊 {restyle_result.get('original_length', 0)} → {restyle_result.get('final_length', 0)} символов

📄 Полный обработанный текст доступен по кнопке ниже ⬇️"""
                    
                    # Добавляем кнопку "Показать полный пост"
                    from aiogram.types import InlineKeyboardButton
                    show_post_button = InlineKeyboardButton(
                        text="📄 Показать полный пост",
                        callback_data=f"show_full_post_{post_id}"
                    )
                    keyboard.inline_keyboard.insert(0, [show_post_button])
                
                from src.bot.main import get_bot_instance
                bot = get_bot_instance()
                
                # Отправляем медиа в зависимости от типа
                if media_type == 'photo':
                    await bot.send_photo(
                        chat_id=callback.message.chat.id,
                        photo=media_for_send,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    logger.info("🖼️ Обновленное уведомление с фото отправлено для поста {}", post_id)
                elif media_type == 'video':
                    await bot.send_video(
                        chat_id=callback.message.chat.id,
                        video=media_for_send,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    logger.info("🎥 Обновленное уведомление с видео отправлено для поста {}", post_id)
                
            except Exception as media_error:
                logger.warning("Ошибка отправки медиа для обновленного уведомления: {}, отправляем как текст", str(media_error))
                
                # Fallback к текстовому сообщению с той же логикой обрезания
                await _send_long_text_notification(callback, notification_text, keyboard, post_id)
        else:
            # Отправляем как текстовое сообщение с проверкой длины
            await _send_long_text_notification(callback, notification_text, keyboard, post_id)
            
        logger.info("📬 Обновленное уведомление для поста {} отправлено успешно", post_id)
        
    except Exception as e:
        logger.error("Ошибка отправки обновленного уведомления для поста {}: {}", post_id, str(e))
        # Не критичная ошибка - не прерываем основной процесс


def _format_processed_post_caption(post, restyle_result: dict) -> str:
    """Создать caption для фото с обработанным текстом"""
    try:
        # Краткий заголовок
        header = f"""🎉 {bold(f'Пост #{post.id} - AI обработан!')}

✅ Двухэтапный рестайлинг завершен
📊 {restyle_result.get('original_length', 0)} → {restyle_result.get('final_length', 0)} символов

📄 {bold('ОБРАБОТАННЫЙ ТЕКСТ:')}"""
        
        # Сначала формируем полный caption, потом проверяем длину
        processed_text = post.processed_text or "Ошибка получения текста"
        full_caption = f"{header}\n{processed_text}"
        
        # Проверяем лимит Telegram для caption к фото (1024 символа)
        if len(full_caption) > 1024:
            # НЕ обрезаем HTML (ломает теги), показываем краткую версию
            processed_text = f"📄 Обработанный текст слишком длинный ({len(processed_text)} символов)\n⬇️ Используйте кнопку 'Показать пост' для просмотра"
            caption = f"{header}\n{processed_text}"
        else:
            caption = full_caption
        
        return caption
        
    except Exception as e:
        logger.error("Ошибка создания caption для обработанного поста: {}", str(e))
        return f"🎉 Пост #{post.id} успешно обработан через AI!"


async def _send_long_text_notification(callback: CallbackQuery, notification_text: str, keyboard, post_id: int) -> None:
    """Отправить длинное текстовое уведомление с автоматическим обрезанием"""
    try:
        # Проверяем длину сообщения (лимит Telegram: 4096 символов)
        if len(notification_text) > 4048:
            logger.info("Текстовое сообщение слишком длинное ({} символов), показываю краткую версию", 
                       len(notification_text))
            
            # НЕ обрезаем HTML (ломает теги), показываем краткую информацию
            truncated_text = f"""📄 {bold('Уведомление о посте слишком длинное')}

📊 Размер уведомления: {len(notification_text)} символов
⬇️ Используйте кнопку 'Показать пост' для просмотра полного текста"""
            
            # Добавляем кнопку "Показать полный пост"
            from aiogram.types import InlineKeyboardButton
            show_post_button = InlineKeyboardButton(
                text="📄 Показать полный пост",
                callback_data=f"show_full_post_{post_id}"
            )
            keyboard.inline_keyboard.insert(0, [show_post_button])
            
            notification_text = truncated_text
        
        await callback.message.answer(
            notification_text,
            reply_markup=keyboard, 
            parse_mode=get_parse_mode())
        
        logger.info("📝 Длинное текстовое уведомление о посте {} отправлено", post_id)
        
    except Exception as e:
        logger.error("Ошибка отправки длинного текстового уведомления: {}", str(e))


@moderation_router.callback_query(F.data == "reject_all_pending", OwnerFilter())
async def reject_all_pending_callback(callback: CallbackQuery):
    """Отклонить все посты на модерации"""
    try:
        await callback.answer()
        
        # Получаем количество постов на модерации
        post_crud = get_post_crud()
        pending_posts = await post_crud.get_posts_by_status(PostStatus.PENDING)
        
        if not pending_posts:
            await safe_edit_message(callback,
                format_info_message(
                    "Нечего отклонять",
                    "На модерации нет постов."
                ),
                reply_markup=get_moderation_menu_keyboard(0),
                parse_mode=get_parse_mode()
            )
            return
        
        # Подтверждение массового отклонения
        rejected_section = 'Это действие можно будет отменить позже через раздел "Отклоненные"'
        confirmation_text = format_warning_message(
            "Подтверждение массового отклонения",
            f"Вы действительно хотите отклонить {bold(f'{len(pending_posts)} постов')} на модерации?\n\n"
            f"⚠️ {bold(rejected_section)}\n\n"
            f"Все посты будут помечены как отклоненные и не будут опубликованы."
        )
        
        keyboard = get_confirmation_keyboard(
            "reject_all", 
            None, 
            "🗑️ Да, отклонить все", 
            "❌ Отменить"
        )
        
        await safe_edit_message(callback,
            confirmation_text,
            keyboard, get_parse_mode())
        
        logger.info("Пользователь {} запросил отклонение всех {} постов на модерации", 
                   callback.from_user.id, len(pending_posts))
        
    except Exception as e:
        logger.error("Ошибка запроса отклонения всех постов: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@moderation_router.callback_query(F.data == "confirm_reject_all", OwnerFilter())
async def confirm_reject_all_posts(callback: CallbackQuery):
    """Подтвердить отклонение всех постов на модерации"""
    try:
        await callback.answer("🗑️ Отклоняю все посты...")
        
        # Получаем все посты на модерации
        post_crud = get_post_crud()
        pending_posts = await post_crud.get_posts_by_status(PostStatus.PENDING)
        
        if not pending_posts:
            await safe_edit_message(callback,
                format_info_message(
                    "Нечего отклонять",
                    "На модерации больше нет постов."
                ),
                reply_markup=get_moderation_menu_keyboard(0),
                parse_mode=get_parse_mode()
            )
            return
        
        # Отклоняем все посты
        rejected_count = 0
        failed_count = 0
        
        for post in pending_posts:
            try:
                success = await post_crud.update_post_status(
                    post.id,
                    PostStatus.REJECTED
                )
                
                if success:
                    rejected_count += 1
                    logger.info("Пост {} отклонен через массовое отклонение", post.id)
                else:
                    failed_count += 1
                    logger.warning("Не удалось отклонить пост {} при массовом отклонении", post.id)
                    
            except Exception as post_error:
                failed_count += 1
                logger.error("Ошибка отклонения поста {} при массовом отклонении: {}", 
                           post.id, str(post_error))
        
        # Показываем результат
        if failed_count == 0:
            result_text = format_success_message(
                "Массовое отклонение завершено",
                f"✅ Успешно отклонено: {bold(f'{rejected_count} постов')}\n\n"
                f"Все посты помечены как отклоненные и не будут опубликованы.\n"
                f"При необходимости их можно вернуть через раздел \"Отклоненные\"."
            )
        else:
            result_text = format_warning_message(
                "Массовое отклонение завершено с ошибками",
                f"✅ Успешно отклонено: {bold(f'{rejected_count} постов')}\n"
                f"❌ Ошибки при отклонении: {bold(f'{failed_count} постов')}\n\n"
                f"Проверьте логи для получения подробной информации об ошибках."
            )
        
        # Обновляем меню модерации
        keyboard = get_moderation_menu_keyboard(0)  # 0 потому что все посты отклонены
        
        await safe_edit_message(callback,
            result_text,
            keyboard, get_parse_mode())
        
        logger.info("Массовое отклонение завершено: {} успешно, {} с ошибками", 
                   rejected_count, failed_count)
        
    except Exception as e:
        logger.error("Ошибка массового отклонения постов: {}", str(e))
        
        # Показываем ошибку и возвращаем в меню
        await safe_edit_message(callback,
            format_error_message(
                "Ошибка массового отклонения",
                "Не удалось отклонить посты. Попробуйте позже."
            ),
            reply_markup=get_moderation_menu_keyboard(),
            parse_mode=get_parse_mode())


@moderation_router.callback_query(F.data == "cancel_reject_all", OwnerFilter())
async def cancel_reject_all_posts(callback: CallbackQuery):
    """Отменить массовое отклонение постов"""
    try:
        await callback.answer("❌ Отменено")
        
        # Получаем актуальное количество постов и возвращаемся в меню
        post_crud = get_post_crud()
        pending_count = await post_crud.get_posts_count_by_status("pending")
        
        await safe_edit_message(callback,
            f"⚖️ {bold('Модерация постов')}\n\n"
            f"📊 {bold('Текущая ситуация:')}\n"
            f"⏳ На модерации: {pending_count} постов\n\n"
            f"❌ Массовое отклонение отменено.",
            reply_markup=get_moderation_menu_keyboard(pending_count),
            parse_mode=get_parse_mode())
        
        logger.info("Пользователь {} отменил массовое отклонение постов", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка отмены массового отклонения: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


def get_moderation_router() -> Router:
    """Получить роутер модерации"""
    return moderation_router