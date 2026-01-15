"""
Синхронизация ручных постов из целевого канала
Добавляет отсутствующие посты в БД для участия в Daily Summary
"""

from datetime import datetime, timedelta

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.database.crud.post import get_post_crud
from src.database.models.post import PostStatus, create_post
from src.userbot.client import get_userbot_client
from src.utils.config import get_config
from src.utils.exceptions import DuplicateRecordError
from src.utils.post_footer import remove_footer_from_post

# Настройка логгера модуля
logger = logger.bind(module="scheduler_manual_posts")

# Типы автопостов для исключения (по меткам в ai_analysis)
AUTO_POST_TYPES = ["daily_post", "weekly_analytics", "summary_post", "template_auto"]


def _to_local_naive(dt: datetime) -> datetime:
    """Привести datetime к локальному времени без tzinfo для совместимости с БД"""
    if dt.tzinfo:
        return dt.astimezone().replace(tzinfo=None)
    return dt


async def sync_manual_posts(hours: int = 24) -> int:
    """
    Синхронизировать ручные посты из целевого канала в БД

    Args:
        hours: Глубина синхронизации в часах (по умолчанию 24)

    Returns:
        Количество добавленных постов
    """
    try:
        config = get_config()
        target_channel_id = config.TARGET_CHANNEL_ID

        if not target_channel_id:
            logger.warning("TARGET_CHANNEL_ID не настроен, синхронизация ручных постов пропущена")
            return 0

        client_wrapper = await get_userbot_client()
        if not client_wrapper or not client_wrapper.client:
            logger.warning("UserBot клиент недоступен, синхронизация ручных постов пропущена")
            return 0

        if not client_wrapper.client.is_connected():
            await client_wrapper.connect()

        if not await client_wrapper.is_user_authorized():
            logger.warning("UserBot не авторизован, синхронизация ручных постов пропущена")
            return 0

        entity = await client_wrapper.client.get_entity(target_channel_id)

        now = datetime.now()
        start_time = now - timedelta(hours=hours)

        post_crud = get_post_crud()
        existing_ids = set(
            await post_crud.get_published_message_ids_by_date(date=now, hours=hours)
        )
        auto_ids = set(
            await post_crud.get_published_message_ids_by_date(
                date=now,
                hours=hours,
                include_types=AUTO_POST_TYPES
            )
        )
        skip_ids = existing_ids | auto_ids

        added_count = 0

        async for message in client_wrapper.client.iter_messages(entity):
            message_time = _to_local_naive(message.date)

            if message_time < start_time:
                break

            if message.id in skip_ids:
                continue

            raw_text = message.raw_text or ""
            if not raw_text.strip():
                continue

            cleaned_text = remove_footer_from_post(raw_text)

            post = create_post(
                channel_id=target_channel_id,
                message_id=message.id,
                original_text=raw_text,
                processed_text=cleaned_text,
                status=PostStatus.POSTED,
                ai_analysis="manual_post",
                posted_date=message_time,
                published_message_id=message.id
            )

            try:
                await post_crud.create(post)
                added_count += 1
                skip_ids.add(message.id)
            except DuplicateRecordError:
                skip_ids.add(message.id)
                continue

        if added_count:
            logger.info("✅ Синхронизировано ручных постов: {}", added_count)
        else:
            logger.debug("Новых ручных постов для синхронизации не найдено")

        return added_count

    except Exception as e:
        logger.error("Ошибка синхронизации ручных постов: {}", str(e))
        return 0
