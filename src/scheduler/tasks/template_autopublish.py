"""
Задача автопубликации шаблонов по расписанию
Автоматическая публикация постов из активных шаблонов в указанное время
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.scheduler.templates import get_template_manager
from src.database.crud.post import get_post_crud
from src.database.models.post import PostStatus, PostSentiment, create_post
from src.bot.main import get_bot_instance
from src.utils.config import get_config
from src.utils.exceptions import TaskExecutionError
from src.utils.post_footer import add_footer_to_post

# Настройка логгера модуля
logger = logger.bind(module="scheduler_template_autopublish")


async def process_template_autopublish() -> None:
    """
    Обработка автопубликации шаблонов
    Проверяет активные шаблоны с временем и публикует их автоматически
    """
    try:
        logger.debug("⏰ Проверка автопубликации шаблонов")
        
        # Получаем активные шаблоны с настроенным временем
        template_manager = get_template_manager()
        templates_to_publish = await get_templates_ready_for_publishing()
        
        if not templates_to_publish:
            logger.debug("Нет шаблонов готовых к автопубликации")
            return
        
        logger.info("📤 Найдено {} шаблонов готовых к автопубликации", len(templates_to_publish))
        
        published_count = 0
        failed_count = 0
        
        for template_info in templates_to_publish:
            try:
                # Проверяем не публиковали ли мы уже этот шаблон сегодня
                if await check_template_published_today(template_info['name']):
                    logger.debug("Шаблон '{}' уже публиковался сегодня", template_info['name'])
                    continue
                
                success = await publish_template_post(template_info)
                
                if success:
                    published_count += 1
                    logger.info("✅ Автопубликован пост из шаблона '{}'", template_info['name'])
                else:
                    failed_count += 1
                    logger.error("❌ Не удалось автопубликовать шаблон '{}'", template_info['name'])
                
                # Небольшая задержка между публикациями
                if len(templates_to_publish) > 1:
                    await asyncio.sleep(2)
                
            except Exception as e:
                failed_count += 1
                logger.error("Ошибка автопубликации шаблона '{}': {}", template_info['name'], str(e))
                continue
        
        if published_count > 0 or failed_count > 0:
            logger.info("Автопубликация шаблонов завершена: {} опубликовано, {} ошибок",
                       published_count, failed_count)
        
    except Exception as e:
        logger.error("❌ Ошибка в задаче автопубликации шаблонов: {}", str(e))
        raise TaskExecutionError("template_autopublish", str(e))


async def get_templates_ready_for_publishing() -> List[Dict[str, Any]]:
    """
    Получить шаблоны готовые к публикации
    
    Returns:
        Список шаблонов готовых к публикации
    """
    try:
        template_manager = get_template_manager()
        
        # Получаем все активные шаблоны с временем
        active_templates = await template_manager.get_active_templates_with_time()
        
        if not active_templates:
            return []
        
        # Фильтруем по времени
        ready_templates = []
        current_time = datetime.now()
        current_hour = current_time.hour
        current_minute = current_time.minute
        
        for template in active_templates:
            auto_time = template.get('auto_time')
            if not auto_time:
                continue
            
            try:
                # Парсим время из формата "HH:MM"
                hour, minute = map(int, auto_time.split(':'))
                
                # Проверяем совпадает ли текущее время (с точностью до минуты)
                if hour == current_hour and minute == current_minute:
                    ready_templates.append(template)
                    logger.debug("Шаблон '{}' готов к публикации (время {})", 
                               template['name'], auto_time)
            
            except (ValueError, AttributeError) as e:
                logger.warning("Неверный формат времени '{}' для шаблона '{}': {}", 
                             auto_time, template['name'], str(e))
                continue
        
        return ready_templates
        
    except Exception as e:
        logger.error("Ошибка получения шаблонов готовых к публикации: {}", str(e))
        return []


async def check_template_published_today(template_name: str) -> bool:
    """Проверить публиковался ли шаблон сегодня"""
    try:
        post_crud = get_post_crud()
        
        # Проверяем посты за сегодня с меткой template_auto
        today = datetime.now().date()
        auto_posts = await post_crud.get_posts_by_date_and_type(today, f"template_auto_{template_name}")
        
        return len(auto_posts) > 0
        
    except Exception as e:
        logger.error("Ошибка проверки публикации шаблона '{}' за сегодня: {}", template_name, str(e))
        return False


async def publish_template_post(template_info: Dict[str, Any]) -> bool:
    """
    Опубликовать пост из шаблона через UserBot (с fallback на Bot API)

    Args:
        template_info: Информация о шаблоне

    Returns:
        True если пост опубликован успешно
    """
    try:
        logger.info("📤 Автопубликация поста из шаблона '{}'", template_info['name'])

        config = get_config()
        target_channel_id = config.TARGET_CHANNEL_ID

        if not target_channel_id:
            logger.error("TARGET_CHANNEL_ID не настроен")
            return False

        # Рендерим шаблон
        template_manager = get_template_manager()
        post_content = await template_manager.render_template(template_info['name'])

        if not post_content:
            logger.error("Не удалось отрендерить шаблон '{}'", template_info['name'])
            return False

        # Создаем пост в БД
        post = await save_template_auto_post(
            template_info['name'],
            post_content,
            template_info.get('pin_enabled', False)
        )

        if not post:
            logger.error("Не удалось сохранить пост в БД")
            return False

        # Получаем информацию о фото из шаблона
        template = await template_manager.get_template(template_info['name'])
        photo_file_id = None
        if template and template.photo_info:
            photo_file_id = template.photo_info.get('file_id')

        sent_message = None
        pin_enabled = template_info.get('pin_enabled', False)

        # Пробуем опубликовать через UserBot с Premium Emoji
        try:
            from src.userbot.publisher import get_userbot_publisher

            publisher = await get_userbot_publisher()

            if publisher and publisher.is_available:
                logger.info("Публикуем автопост из шаблона '{}' через UserBot с Premium Emoji",
                           template_info['name'])

                # Получаем путь к фото если есть
                photo_path = None
                if photo_file_id:
                    try:
                        from src.bot.media_handler import get_media_handler
                        media_handler = get_media_handler()
                        photo_path = await media_handler.download_photo_by_file_id(photo_file_id)
                        if photo_path:
                            logger.info("Фото скачано для UserBot публикации: {}", photo_path)
                    except Exception as download_error:
                        logger.warning("Не удалось скачать фото: {}", str(download_error))

                # Публикуем через UserBot (футер добавляется внутри publisher.publish_post)
                message_id = await publisher.publish_post(
                    channel_id=target_channel_id,
                    text=post_content,
                    photo_path=photo_path,
                    pin_post=pin_enabled,
                    add_footer=True
                )

                if message_id:
                    logger.info("✅ Автопост из шаблона '{}' опубликован через UserBot, message_id: {}",
                               template_info['name'], message_id)
                    # Создаём фейковый объект для совместимости
                    class FakeMessage:
                        def __init__(self, msg_id):
                            self.message_id = msg_id
                    sent_message = FakeMessage(message_id)
                else:
                    logger.warning("Не удалось опубликовать через UserBot, fallback на Bot API")
            else:
                logger.debug("UserbotPublisher недоступен, используем Bot API")

        except Exception as userbot_error:
            logger.warning("Ошибка публикации через UserBot: {}, fallback на Bot API",
                          str(userbot_error))

        # Fallback: публикация через Bot API (без Premium Emoji)
        if not sent_message:
            logger.info("Публикуем автопост через Bot API (без Premium Emoji)")

            # Получаем экземпляр бота
            bot = get_bot_instance()

            # Конвертируем Telethon Markdown -> HTML для Bot API
            from src.utils.post_footer import convert_markdown_to_html
            content_html = convert_markdown_to_html(post_content)

            # Добавляем футер (HTML режим для Bot API)
            content_with_footer = add_footer_to_post(content_html, parse_mode="HTML")

            if photo_file_id:
                # Публикуем с фото
                logger.info("📸 Публикуем автопост с фото из шаблона '{}'", template_info['name'])
                sent_message = await bot.send_photo(
                    chat_id=target_channel_id,
                    photo=photo_file_id,
                    caption=content_with_footer,
                    parse_mode="HTML"
                )
            else:
                # Публикуем текстовый пост
                logger.info("📝 Публикуем текстовый автопост из шаблона '{}'", template_info['name'])
                sent_message = await bot.send_message(
                    chat_id=target_channel_id,
                    text=content_with_footer,
                    parse_mode="HTML"
                )

            # Закрепляем пост через Bot API (UserBot делает это сам)
            if sent_message and pin_enabled:
                try:
                    await bot.pin_chat_message(
                        chat_id=target_channel_id,
                        message_id=sent_message.message_id,
                        disable_notification=True
                    )
                    logger.info("📌 Пост из шаблона '{}' закреплен через Bot API", template_info['name'])
                except Exception as pin_error:
                    logger.warning("⚠️ Не удалось закрепить пост: {}", str(pin_error))

        # Проверяем успешность публикации
        if not sent_message:
            logger.error("Не удалось опубликовать пост из шаблона '{}'", template_info['name'])
            post_crud = get_post_crud()
            await post_crud.add_post_error(post.id, "Ошибка публикации: sent_message is None")
            return False

        # Обновляем статус поста в БД
        post_crud = get_post_crud()
        await post_crud.update_post_status(post.id, PostStatus.POSTED)
        await post_crud.update_post(post.id, posted_date=datetime.now())

        logger.info("✅ Пост из шаблона '{}' успешно опубликован в канале {}",
                   template_info['name'], target_channel_id)

        # Отправляем уведомление владельцу
        await notify_owner_about_auto_publication(template_info['name'], post)

        return True

    except Exception as e:
        logger.error("Ошибка автопубликации шаблона '{}': {}", template_info['name'], str(e))
        return False


async def save_template_auto_post(template_name: str, content: str, pin_enabled: bool) -> Optional[Any]:
    """Сохранить автопост из шаблона в БД"""
    try:
        # Создаем пост с специальной меткой
        import time
        message_id = int(time.time())  # Unix timestamp как уникальный ID
        
        config = get_config()
        
        # Получаем информацию о фото из шаблона
        photo_file_id = None
        template_manager = get_template_manager()
        template = await template_manager.get_template(template_name)
        if template and template.photo_info:
            photo_file_id = template.photo_info.get('file_id')
            logger.info("📸 Автопост из шаблона '{}' с фото: {}", template_name, photo_file_id)
        
        # Проверяем и создаем канал в БД если не существует
        from src.database.crud.channel import get_channel_crud
        channel_crud = get_channel_crud()
        
        existing_channel = await channel_crud.get_by_channel_id(config.TARGET_CHANNEL_ID)
        if not existing_channel:
            # Создаем системный канал для автопостов
            from src.database.models.channel import Channel
            system_channel = Channel(
                channel_id=config.TARGET_CHANNEL_ID,
                username="template_auto_posts",
                title="Автопосты из шаблонов",
                is_active=True
            )
            await channel_crud.create(system_channel)
            logger.info("Создан системный канал для автопостов из шаблонов: {}", config.TARGET_CHANNEL_ID)
        
        post = create_post(
            channel_id=config.TARGET_CHANNEL_ID,
            message_id=message_id,
            original_text=content,
            processed_text=content,
            status=PostStatus.APPROVED,  # Автоматически одобренные
            relevance_score=10,  # Максимальная релевантность
            sentiment=PostSentiment.NEUTRAL,
            ai_analysis=f"Автопост из шаблона '{template_name}'",
            pin_post=pin_enabled,
            photo_file_id=photo_file_id  # Добавляем фото если есть
        )
        
        post_crud = get_post_crud()
        created_post = await post_crud.create(post)
        
        if created_post:
            logger.info("📋 Автопост из шаблона '{}' сохранен в БД: ID {}", template_name, created_post.id)
        
        return created_post
        
    except Exception as e:
        logger.error("Ошибка сохранения автопоста из шаблона '{}': {}", template_name, str(e))
        return None


async def notify_owner_about_auto_publication(template_name: str, post) -> None:
    """Уведомить владельца об автоматической публикации из шаблона"""
    try:
        config = get_config()
        
        bot = get_bot_instance()
        
        # Короткое превью текста
        preview = (post.processed_text or post.original_text)[:100]
        if len(preview) < len(post.processed_text or post.original_text):
            preview += "..."
        
        notification_text = f"""📤 <b>Автопост из шаблона опубликован</b>

🏷 Шаблон: <code>{template_name}</code>
🆔 ID поста: {post.id}
🕐 Время публикации: {datetime.now().strftime('%H:%M %d.%m.%Y')}
📝 Превью: {preview}

Пост успешно опубликован в целевом канале по расписанию."""
        
        await bot.send_message(
            chat_id=config.OWNER_ID,
            text=notification_text,
            parse_mode="HTML"
        )
        
        logger.debug("Уведомление об автопубликации шаблона '{}' отправлено владельцу", template_name)
        
    except Exception as e:
        logger.error("Ошибка отправки уведомления об автопубликации: {}", str(e))
        # Не критичная ошибка


async def get_template_autopublish_summary() -> Dict[str, Any]:
    """
    Получить сводку по автопубликации шаблонов
    
    Returns:
        Статистика автопубликации шаблонов
    """
    try:
        template_manager = get_template_manager()
        active_templates = await template_manager.get_active_templates_with_time()
        
        if not active_templates:
            return {
                "total_templates": 0,
                "ready_now": 0,
                "next_24h": 0,
                "next_publication_time": None
            }
        
        current_time = datetime.now()
        current_hour = current_time.hour
        current_minute = current_time.minute
        
        # Считаем готовые к публикации
        ready_now = 0
        next_24h_publications = []
        
        for template in active_templates:
            auto_time = template.get('auto_time')
            if not auto_time:
                continue
            
            try:
                hour, minute = map(int, auto_time.split(':'))
                
                # Проверяем текущее время
                if hour == current_hour and minute == current_minute:
                    ready_now += 1
                
                # Считаем на следующие 24 часа
                today_publication = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
                tomorrow_publication = today_publication + timedelta(days=1)
                
                # Если время публикации еще не прошло сегодня
                if today_publication > current_time:
                    next_24h_publications.append(today_publication)
                else:
                    # Иначе завтра
                    next_24h_publications.append(tomorrow_publication)
                    
            except (ValueError, AttributeError):
                continue
        
        # Находим ближайшую публикацию
        next_publication_time = None
        if next_24h_publications:
            next_publication_time = min(next_24h_publications)
        
        return {
            "total_templates": len(active_templates),
            "ready_now": ready_now,
            "next_24h": len(next_24h_publications),
            "next_publication_time": next_publication_time
        }
        
    except Exception as e:
        logger.error("Ошибка получения сводки автопубликации шаблонов: {}", str(e))
        return {}