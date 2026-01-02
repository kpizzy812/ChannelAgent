"""
Задача обработки отложенных постов
Автоматическая публикация постов по расписанию
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.database.crud.post import get_post_crud
from src.database.models.post import PostStatus
from src.bot.main import get_bot_instance
from src.utils.config import get_config
from src.utils.exceptions import TaskExecutionError
from src.utils.post_footer import add_footer_to_post

# Настройка логгера модуля
logger = logger.bind(module="scheduler_delayed_posts")


async def process_scheduled_posts() -> None:
    """
    Обработка отложенных постов
    Проверяет и публикует посты по расписанию
    """
    try:
        logger.debug("⏰ Проверка отложенных постов")
        
        # Получаем посты готовые к публикации
        ready_posts = await get_posts_ready_for_publishing()
        
        if not ready_posts:
            logger.debug("Нет постов готовых к публикации")
            return
        
        logger.info("📤 Найдено {} постов готовых к публикации", len(ready_posts))
        
        published_count = 0
        failed_count = 0
        
        for post in ready_posts:
            try:
                success = await publish_scheduled_post(post)
                
                if success:
                    published_count += 1
                    logger.info("✅ Опубликован отложенный пост {}", post.id)
                else:
                    failed_count += 1
                    logger.error("❌ Не удалось опубликовать пост {}", post.id)
                
                # Небольшая задержка между публикациями
                if len(ready_posts) > 1:
                    await asyncio.sleep(2)
                
            except Exception as e:
                failed_count += 1
                logger.error("Ошибка публикации поста {}: {}", post.id, str(e))
                continue
        
        if published_count > 0 or failed_count > 0:
            logger.info("Обработка отложенных постов завершена: {} опубликовано, {} ошибок",
                       published_count, failed_count)
        
    except Exception as e:
        logger.error("❌ Ошибка в задаче отложенных постов: {}", str(e))
        raise TaskExecutionError("scheduled_posts", str(e))


async def get_posts_ready_for_publishing() -> List[Any]:
    """
    Получить посты готовые к публикации
    
    Returns:
        Список постов готовых к публикации
    """
    try:
        post_crud = get_post_crud()
        
        # Получаем все запланированные посты
        scheduled_posts = await post_crud.get_posts_by_status(PostStatus.SCHEDULED)
        
        # Фильтруем по времени
        ready_posts = []
        current_time = datetime.now()
        
        for post in scheduled_posts:
            if post.scheduled_date and post.scheduled_date <= current_time:
                ready_posts.append(post)
                logger.debug("Пост {} готов к публикации (запланирован на {})", 
                           post.id, post.scheduled_date.strftime("%H:%M %d.%m.%Y"))
        
        return ready_posts
        
    except Exception as e:
        logger.error("Ошибка получения постов готовых к публикации: {}", str(e))
        return []


async def publish_scheduled_post(post, use_premium_emoji: bool = True) -> bool:
    """
    Опубликовать отложенный пост

    Args:
        post: Объект поста для публикации
        use_premium_emoji: Использовать Premium Custom Emoji через UserBot

    Returns:
        True если пост опубликован успешно
    """
    try:
        config = get_config()
        target_channel_id = config.TARGET_CHANNEL_ID

        if not target_channel_id:
            logger.error("TARGET_CHANNEL_ID не настроен")
            return False

        # Подготавливаем контент для публикации
        content = post.processed_text or post.original_text

        if not content or not content.strip():
            logger.error("Пост {} не имеет текста для публикации", post.id)
            return False

        # Пробуем опубликовать через UserBot с Premium Emoji
        if use_premium_emoji:
            try:
                from src.userbot.publisher import get_userbot_publisher

                publisher = await get_userbot_publisher()

                if publisher and publisher.is_available:
                    logger.info("Публикуем отложенный пост {} через UserBot с Premium Emoji", post.id)

                    # Получаем пути к медиа
                    photo_path = post.photo_path if hasattr(post, 'photo_path') and post.photo_path else None
                    video_path = post.video_path if hasattr(post, 'video_path') and post.video_path else None

                    # Получаем media_items для альбомов (если есть)
                    media_items = None
                    if hasattr(post, 'get_media_items'):
                        media_items = post.get_media_items()
                        if media_items and len(media_items) > 1:
                            logger.info("Публикуем альбом с {} медиа через UserBot", len(media_items))

                    message_id = await publisher.publish_post(
                        channel_id=target_channel_id,
                        text=content,
                        photo_path=photo_path,
                        video_path=video_path,
                        media_items=media_items if media_items and len(media_items) > 1 else None,
                        pin_post=getattr(post, 'pin_post', False),
                        add_footer=True
                    )

                    if message_id:
                        # Обновляем статус поста
                        post_crud = get_post_crud()
                        await post_crud.update_post_status(post.id, PostStatus.POSTED)
                        await post_crud.update_post(post.id, posted_date=datetime.now(), published_message_id=message_id)

                        logger.info("Отложенный пост {} опубликован через UserBot, message_id: {}",
                                   post.id, message_id)

                        # Отправляем подтверждение владельцу
                        await notify_owner_about_publication(post)
                        return True
                    else:
                        logger.warning("Не удалось опубликовать через UserBot, fallback на Bot API")
                else:
                    logger.debug("UserbotPublisher недоступен, используем Bot API")

            except Exception as userbot_error:
                logger.warning("Ошибка публикации через UserBot: {}, fallback на Bot API",
                              str(userbot_error))

        # Fallback: публикация через Bot API (без Premium Emoji)
        logger.info("Публикуем отложенный пост {} через Bot API", post.id)

        # Получаем экземпляр бота
        bot = get_bot_instance()

        # Добавляем футер с полезными ссылками (Markdown режим)
        content_with_footer = add_footer_to_post(content, parse_mode="Markdown")

        # Публикуем пост в зависимости от типа медиа
        try:
            sent_message = None

            # Получаем медиа через media_handler (поддержка фото и видео)
            from src.bot.media_handler import get_media_handler
            media_handler = get_media_handler()

            # Проверяем наличие альбома
            if hasattr(post, 'has_album') and post.has_album:
                logger.info("Публикуем отложенный альбом с {} медиа через Bot API", post.album_count)
                media_group = media_handler.get_media_group_for_send(
                    post, content_with_footer, parse_mode="Markdown"
                )

                if len(media_group) >= 2:
                    messages = await bot.send_media_group(
                        chat_id=target_channel_id,
                        media=media_group
                    )
                    # Берем первое сообщение
                    sent_message = messages[0] if messages else None
                else:
                    logger.warning("Недостаточно медиа для альбома, публикуем как обычный пост")
                    # Fallback на обычную логику ниже

            # Если не альбом или альбом не удалось отправить
            if sent_message is None:
                media_for_send, media_type = media_handler.get_media_for_send(post)

                if media_for_send and media_type == 'photo':
                    logger.info("Публикуем отложенный пост с фото")
                    sent_message = await bot.send_photo(
                        chat_id=target_channel_id,
                        photo=media_for_send,
                        caption=content_with_footer,
                        parse_mode="Markdown"
                    )
                elif media_for_send and media_type == 'video':
                    logger.info("Публикуем отложенный пост с видео")
                    sent_message = await bot.send_video(
                        chat_id=target_channel_id,
                        video=media_for_send,
                        caption=content_with_footer,
                        parse_mode="Markdown"
                    )
                else:
                    logger.info("Публикуем текстовый отложенный пост")
                    sent_message = await bot.send_message(
                        chat_id=target_channel_id,
                        text=content_with_footer,
                        parse_mode="Markdown"
                    )

            # Проверяем нужно ли закрепить пост
            if sent_message and hasattr(post, 'pin_post') and post.pin_post:
                try:
                    await bot.pin_chat_message(
                        chat_id=target_channel_id,
                        message_id=sent_message.message_id,
                        disable_notification=True
                    )
                    logger.info("Пост {} закреплен в канале", post.id)
                except Exception as pin_error:
                    logger.warning("Не удалось закрепить пост {}: {}", post.id, str(pin_error))

            # Обновляем статус поста
            post_crud = get_post_crud()
            await post_crud.update_post_status(post.id, PostStatus.POSTED)
            await post_crud.update_post(post.id, posted_date=datetime.now(), published_message_id=sent_message.message_id)

            logger.info("Пост {} успешно опубликован в канале {}",
                       post.id, target_channel_id)

            # Отправляем подтверждение владельцу
            await notify_owner_about_publication(post)

            return True

        except Exception as e:
            logger.error("Ошибка публикации поста {} в Telegram: {}", post.id, str(e))

            # Помечаем пост как проблемный
            post_crud = get_post_crud()
            await post_crud.add_post_error(post.id, f"Ошибка публикации: {str(e)}")

            return False

    except Exception as e:
        logger.error("Ошибка публикации отложенного поста {}: {}", post.id, str(e))
        return False


async def notify_owner_about_publication(post) -> None:
    """Уведомить владельца об автоматической публикации"""
    try:
        config = get_config()
        
        bot = get_bot_instance()
        
        # Короткое превью текста
        preview = (post.processed_text or post.original_text)[:100]
        if len(preview) < len(post.processed_text or post.original_text):
            preview += "..."
        
        notification_text = f"""📤 <b>Пост опубликован автоматически</b>

🆔 ID поста: {post.id}
🕐 Время публикации: {datetime.now().strftime('%H:%M %d.%m.%Y')}
📝 Превью: {preview}

Пост успешно опубликован в целевом канале."""
        
        await bot.send_message(
            chat_id=config.OWNER_ID,
            text=notification_text,
            parse_mode="HTML"
        )
        
        logger.debug("Уведомление о публикации поста {} отправлено владельцу", post.id)
        
    except Exception as e:
        logger.error("Ошибка отправки уведомления о публикации: {}", str(e))
        # Не критичная ошибка


async def schedule_post(post_id: int, publish_time: datetime) -> bool:
    """
    Запланировать пост на определенное время
    
    Args:
        post_id: ID поста
        publish_time: Время публикации
        
    Returns:
        True если пост запланирован успешно
    """
    try:
        post_crud = get_post_crud()
        
        # Обновляем статус и время
        success = await post_crud.update_post(
            post_id,
            status=PostStatus.SCHEDULED,
            scheduled_date=publish_time
        )
        
        if success:
            logger.info("Пост {} запланирован на {}", 
                       post_id, publish_time.strftime("%H:%M %d.%m.%Y"))
            return True
        else:
            logger.error("Не удалось запланировать пост {}", post_id)
            return False
            
    except Exception as e:
        logger.error("Ошибка планирования поста {}: {}", post_id, str(e))
        return False


async def cancel_scheduled_post(post_id: int) -> bool:
    """
    Отменить запланированную публикацию
    
    Args:
        post_id: ID поста
        
    Returns:
        True если публикация отменена
    """
    try:
        post_crud = get_post_crud()
        
        # Возвращаем в статус одобрен
        success = await post_crud.update_post(
            post_id,
            status=PostStatus.APPROVED,
            scheduled_date=None
        )
        
        if success:
            logger.info("Запланированная публикация поста {} отменена", post_id)
            return True
        else:
            logger.error("Не удалось отменить публикацию поста {}", post_id)
            return False
            
    except Exception as e:
        logger.error("Ошибка отмены публикации поста {}: {}", post_id, str(e))
        return False


async def reschedule_post(post_id: int, new_time: datetime) -> bool:
    """
    Перенести время публикации поста
    
    Args:
        post_id: ID поста
        new_time: Новое время публикации
        
    Returns:
        True если время изменено успешно
    """
    try:
        post_crud = get_post_crud()
        
        success = await post_crud.update_post(
            post_id,
            scheduled_date=new_time
        )
        
        if success:
            logger.info("Время публикации поста {} изменено на {}", 
                       post_id, new_time.strftime("%H:%M %d.%m.%Y"))
            return True
        else:
            logger.error("Не удалось изменить время публикации поста {}", post_id)
            return False
            
    except Exception as e:
        logger.error("Ошибка изменения времени публикации поста {}: {}", post_id, str(e))
        return False


async def get_scheduled_posts_summary() -> Dict[str, Any]:
    """
    Получить сводку по запланированным постам
    
    Returns:
        Статистика запланированных постов
    """
    try:
        post_crud = get_post_crud()
        scheduled_posts = await post_crud.get_posts_by_status(PostStatus.SCHEDULED)
        
        if not scheduled_posts:
            return {
                "total_scheduled": 0,
                "ready_now": 0,
                "next_24h": 0,
                "next_post_time": None
            }
        
        current_time = datetime.now()
        tomorrow = current_time + timedelta(days=1)
        
        # Считаем посты
        ready_now = len([p for p in scheduled_posts if p.scheduled_date and p.scheduled_date <= current_time])
        next_24h = len([p for p in scheduled_posts if p.scheduled_date and p.scheduled_date <= tomorrow])
        
        # Находим ближайший пост
        future_posts = [p for p in scheduled_posts if p.scheduled_date and p.scheduled_date > current_time]
        next_post_time = None
        
        if future_posts:
            next_post = min(future_posts, key=lambda x: x.scheduled_date)
            next_post_time = next_post.scheduled_date
        
        return {
            "total_scheduled": len(scheduled_posts),
            "ready_now": ready_now,
            "next_24h": next_24h,
            "next_post_time": next_post_time
        }
        
    except Exception as e:
        logger.error("Ошибка получения сводки запланированных постов: {}", str(e))
        return {}


async def handle_failed_publications() -> None:
    """Обработка неудачных публикаций"""
    try:
        logger.debug("🔄 Обработка неудачных публикаций")
        
        post_crud = get_post_crud()
        
        # Ищем посты которые должны были быть опубликованы, но имеют ошибки
        failed_posts = await post_crud.get_posts_with_errors()
        
        if not failed_posts:
            return
        
        logger.info("Найдено {} постов с ошибками публикации", len(failed_posts))
        
        retry_count = 0
        max_retries = 3
        
        for post in failed_posts[:max_retries]:  # Пробуем только первые 3
            try:
                # Пробуем опубликовать еще раз
                success = await publish_scheduled_post(post)
                
                if success:
                    # Очищаем ошибку
                    await post_crud.clear_post_error(post.id)
                    retry_count += 1
                    logger.info("✅ Пост {} успешно опубликован после повторной попытки", post.id)
                
                await asyncio.sleep(1)  # Задержка между попытками
                
            except Exception as e:
                logger.error("Повторная попытка публикации поста {} не удалась: {}", post.id, str(e))
        
        if retry_count > 0:
            logger.info("Повторно опубликовано {} постов", retry_count)
            
    except Exception as e:
        logger.error("Ошибка обработки неудачных публикаций: {}", str(e))


def format_schedule_time(target_time: datetime) -> str:
    """
    Форматировать время для отображения
    
    Args:
        target_time: Время для форматирования
        
    Returns:
        Отформатированная строка времени
    """
    try:
        now = datetime.now()
        
        # Если сегодня
        if target_time.date() == now.date():
            return f"сегодня в {target_time.strftime('%H:%M')}"
        
        # Если завтра
        elif target_time.date() == (now + timedelta(days=1)).date():
            return f"завтра в {target_time.strftime('%H:%M')}"
        
        # Если на этой неделе
        elif (target_time - now).days < 7:
            weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
            weekday = weekdays[target_time.weekday()]
            return f"{weekday} в {target_time.strftime('%H:%M')}"
        
        # Иначе полная дата
        else:
            return target_time.strftime('%H:%M %d.%m.%Y')
            
    except Exception:
        return target_time.strftime('%H:%M %d.%m.%Y')