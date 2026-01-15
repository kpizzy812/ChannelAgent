"""
Задача создания ежедневных Summary постов
Генерация сводки новостей за день с гиперссылками на опубликованные посты
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.database.crud.post import get_post_crud
from src.database.models.post import PostStatus, PostSentiment, create_post
from src.ai.summary_generator import get_summary_generator
from src.scheduler.tasks.manual_posts import sync_manual_posts
from src.utils.config import get_config
from src.utils.exceptions import TaskExecutionError

# Настройка логгера модуля
logger = logger.bind(module="scheduler_summary_posts")

# Константы
MIN_POSTS_FOR_SUMMARY = 3
EXCLUDED_POST_TYPES = ["daily_post", "weekly_analytics", "summary_post", "template_auto"]


async def create_daily_summary_post() -> Optional[int]:
    """
    Создать ежедневный Summary пост с гиперссылками на посты за день

    Returns:
        ID созданного поста или None если не удалось создать
    """
    try:
        logger.info("📰 Создание ежедневного Summary поста")

        # Проверяем не создавали ли мы уже summary сегодня
        if await check_summary_exists_today():
            logger.info("Summary пост уже создан сегодня")
            return None

        # Синхронизируем ручные посты из целевого канала перед сборкой summary
        try:
            await sync_manual_posts()
        except Exception as sync_error:
            logger.warning(
                "⚠️ Синхронизация ручных постов не удалась, продолжаем без них: {}",
                str(sync_error)
            )

        # Получаем посты за сегодня (опубликованные с published_message_id)
        today = datetime.now()
        post_crud = get_post_crud()

        posts = await post_crud.get_published_posts_by_date(
            date=today,
            exclude_types=EXCLUDED_POST_TYPES
        )

        if not posts:
            logger.info("Нет опубликованных постов за сегодня для создания summary")
            return None

        # Проверяем минимальное количество постов
        if len(posts) < MIN_POSTS_FOR_SUMMARY:
            logger.info(
                "Недостаточно постов для summary: {} (минимум {})",
                len(posts),
                MIN_POSTS_FOR_SUMMARY
            )
            return None

        logger.info("Найдено {} постов для summary", len(posts))

        # Генерируем Summary пост через AI
        summary_generator = get_summary_generator()
        summary_content = await summary_generator.create_summary_post(posts, today)

        if not summary_content:
            logger.error("❌ Не удалось сгенерировать Summary контент")
            return None

        logger.debug("Summary контент сгенерирован: {} символов", len(summary_content))

        # Сохраняем Summary пост в БД
        post = await save_summary_post(summary_content)

        if not post:
            logger.error("❌ Не удалось сохранить Summary пост в БД")
            return None

        logger.info("✅ Summary пост создан в БД: ID {}", post.id)

        # Публикуем Summary пост в канал
        success = await publish_summary_to_channel(post, summary_content)

        if success:
            logger.info("✅ Summary пост успешно опубликован")
            return post.id
        else:
            logger.error("❌ Не удалось опубликовать Summary пост")
            return None

    except Exception as e:
        logger.error("❌ Ошибка создания Summary поста: {}", str(e))
        logger.exception("Детали ошибки:")
        raise TaskExecutionError("daily_summary_post", str(e))


async def check_summary_exists_today() -> bool:
    """
    Проверить существует ли уже Summary пост за сегодня

    Returns:
        True если Summary пост уже создан
    """
    try:
        post_crud = get_post_crud()

        # Проверяем посты за сегодня с меткой summary_post
        today = datetime.now().date()
        summary_posts = await post_crud.get_posts_by_date_and_type(today, "summary_post")

        return len(summary_posts) > 0

    except Exception as e:
        logger.error("Ошибка проверки существования Summary поста: {}", str(e))
        return False


async def save_summary_post(content: str) -> Optional[any]:
    """
    Сохранить Summary пост в БД

    Args:
        content: Контент поста (Markdown)

    Returns:
        Объект поста или None если не удалось сохранить
    """
    try:
        # Генерируем уникальный message_id на основе времени
        import time
        message_id = int(time.time())  # Unix timestamp как уникальный ID

        # Используем целевой канал из конфигурации
        config = get_config()

        # Проверяем и создаем канал в БД если не существует
        from src.database.crud.channel import get_channel_crud
        channel_crud = get_channel_crud()

        # Проверяем существует ли канал
        existing_channel = await channel_crud.get_by_channel_id(config.TARGET_CHANNEL_ID)
        if not existing_channel:
            # Создаем системный канал для summary постов
            from src.database.models.channel import Channel
            system_channel = Channel(
                channel_id=config.TARGET_CHANNEL_ID,
                username="summary_posts_system",
                title="Системные Summary посты",
                is_active=True
            )
            await channel_crud.create(system_channel)
            logger.info("Создан системный канал для Summary постов: {}", config.TARGET_CHANNEL_ID)

        # Создаем Summary пост со статусом APPROVED (публикуем немедленно)
        post = create_post(
            channel_id=config.TARGET_CHANNEL_ID,
            message_id=message_id,
            original_text=content,
            processed_text=content,
            status=PostStatus.APPROVED,
            relevance_score=10,  # Максимальная релевантность
            sentiment=PostSentiment.NEUTRAL,
            ai_analysis="Ежедневный Summary пост с гиперссылками на новости за день (summary_post)",
            scheduled_date=None,
            posted_date=datetime.now(),
            pin_post=False  # НЕ закрепляем Summary посты
        )

        # Сохраняем в БД
        post_crud = get_post_crud()
        created_post = await post_crud.create(post)

        if created_post:
            logger.info("Summary пост сохранен в БД: ID {}", created_post.id)
            return created_post
        else:
            logger.error("Не удалось сохранить Summary пост в БД")
            return None

    except Exception as e:
        logger.error("Ошибка сохранения Summary поста: {}", str(e))
        logger.exception("Детали ошибки:")
        return None


async def publish_summary_to_channel(post, content: str) -> bool:
    """
    Опубликовать Summary пост в целевой канал
    Приоритет: UserBot с Premium Emoji
    Fallback: Bot API

    Args:
        post: Объект поста из БД
        content: Содержимое поста (Markdown)

    Returns:
        True если пост опубликован успешно
    """
    try:
        logger.info("📤 Публикация Summary поста в канал")

        config = get_config()
        sent_message = None
        published_message_id = None

        # Пробуем опубликовать через UserBot с Premium Emoji
        try:
            from src.userbot.publisher import get_userbot_publisher

            publisher = await get_userbot_publisher()

            if publisher and publisher.is_available:
                logger.info("Публикуем Summary пост через UserBot с Premium Emoji")

                # Публикуем через UserBot (футер уже добавлен в content от SummaryGenerator)
                message_id = await publisher.publish_post(
                    channel_id=config.TARGET_CHANNEL_ID,
                    text=content,
                    photo_path=None,  # Summary посты без фото
                    pin_post=False,  # НЕ закрепляем
                    add_footer=False  # Футер уже есть в контенте
                )

                if message_id:
                    published_message_id = message_id
                    logger.info("✅ Summary пост опубликован через UserBot, message_id: {}", message_id)
                else:
                    logger.warning("Не удалось опубликовать через UserBot, fallback на Bot API")
            else:
                logger.debug("UserbotPublisher недоступен, используем Bot API")

        except Exception as userbot_error:
            logger.warning("Ошибка публикации через UserBot: {}, fallback на Bot API", str(userbot_error))

        # Fallback: публикация через Bot API
        if not published_message_id:
            logger.info("Публикуем Summary пост через Bot API")

            from src.bot.main import get_bot_instance
            bot = get_bot_instance()

            try:
                # Публикуем только текст (Summary посты без медиа)
                sent_message = await bot.send_message(
                    chat_id=config.TARGET_CHANNEL_ID,
                    text=content,
                    parse_mode="Markdown"  # Summary использует Markdown
                )

                if sent_message:
                    published_message_id = sent_message.message_id
                    logger.info("Summary пост опубликован через Bot API, message_id: {}", sent_message.message_id)

            except Exception as bot_api_error:
                logger.error("Ошибка публикации Summary через Bot API: {}", str(bot_api_error))
                return False

        # Обновляем статус поста и сохраняем published_message_id
        if published_message_id:
            post_crud = get_post_crud()
            await post_crud.update_post_status(post.id, PostStatus.POSTED)
            await post_crud.update_post(
                post.id,
                posted_date=datetime.now(),
                published_message_id=published_message_id
            )
            logger.info("✅ Summary пост опубликован успешно, published_message_id: {}", published_message_id)
            return True
        else:
            logger.error("❌ Не удалось опубликовать Summary пост")
            return False

    except Exception as e:
        logger.error("❌ Ошибка публикации Summary поста: {}", str(e))
        logger.exception("Детали ошибки:")
        return False
