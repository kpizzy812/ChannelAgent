"""
Задача создания еженедельных аналитических постов
Публикация глобального обзора рынка раз в неделю через SyntraAI API
"""

import time
from datetime import datetime
from typing import Dict, Any, Optional

from loguru import logger

from src.scheduler.syntra_client import get_syntra_client
from src.database.crud.post import get_post_crud
from src.database.models.post import PostStatus, PostSentiment, create_post
from src.bot.main import get_bot_instance
from src.utils.config import get_config
from src.utils.exceptions import TaskExecutionError
from src.utils.post_footer import add_footer_to_post

# Настройка логгера модуля
logger = logger.bind(module="scheduler_weekly_posts")


async def create_weekly_market_overview() -> None:
    """
    Создать еженедельный обзор рынка с данными от SyntraAI

    Включает:
    - Фазу рынка (цикл)
    - BTC/ETH цены и недельные изменения
    - Доминацию альткоинов (OTHERS.D)
    - Fear & Greed Index
    - AI-анализ для инвесторов
    """
    try:
        logger.info("📊 Создание еженедельного обзора рынка")

        # Проверяем включена ли функция
        from src.database.crud.setting import get_bool_setting
        weekly_enabled = await get_bool_setting("weekly_analytics.enabled", False)
        if not weekly_enabled:
            logger.debug("Еженедельная аналитика отключена в настройках")
            return

        # Проверяем не создавали ли мы уже пост на этой неделе
        if await check_weekly_post_exists():
            logger.info("Еженедельный пост уже создан на этой неделе")
            return

        # Получаем данные от SyntraAI
        syntra_client = get_syntra_client()
        weekly_data = await syntra_client.get_weekly_analytics()

        if not weekly_data:
            logger.error("❌ Не удалось получить данные от SyntraAI")
            raise TaskExecutionError("weekly_market_overview", "Нет данных от SyntraAI")

        # Генерируем контент поста
        content = generate_weekly_content(weekly_data)

        if not content:
            logger.error("❌ Не удалось сгенерировать контент поста")
            raise TaskExecutionError("weekly_market_overview", "Ошибка генерации контента")

        # Получаем фото из настроек шаблона (если есть)
        photo_file_id = await get_weekly_photo_file_id()

        # Создаем и публикуем пост
        post = await save_weekly_post(content, auto_publish=True, photo_file_id=photo_file_id)

        if post:
            logger.info("✅ Еженедельный обзор рынка опубликован: ID {}", post.id)
            await notify_owner_about_weekly_post(post)
        else:
            logger.error("❌ Не удалось сохранить еженедельный пост")

    except Exception as e:
        logger.exception("❌ Ошибка создания еженедельного обзора: {}", str(e))
        raise TaskExecutionError("weekly_market_overview", str(e))


async def check_weekly_post_exists() -> bool:
    """Проверить существует ли уже еженедельный пост на этой неделе"""
    try:
        post_crud = get_post_crud()

        # Получаем номер текущей недели
        today = datetime.now()
        week_number = today.isocalendar()[1]
        year = today.year

        # Проверяем посты за эту неделю с меткой weekly_analytics
        weekly_posts = await post_crud.get_posts_by_week_and_type(year, week_number, "weekly_analytics")

        return len(weekly_posts) > 0

    except Exception as e:
        logger.error("Ошибка проверки существования еженедельного поста: {}", str(e))
        return False


def generate_weekly_content(data: Dict[str, Any]) -> Optional[str]:
    """
    Сгенерировать контент еженедельного поста из данных SyntraAI

    Args:
        data: Данные от SyntraAI API

    Returns:
        Отформатированный текст поста
    """
    try:
        logger.debug("📝 Генерация контента еженедельного поста")

        # Извлекаем данные
        market_cycle = data.get("market_cycle", {})
        btc = data.get("btc", {})
        eth = data.get("eth", {})
        others = data.get("others_dominance", {})
        fear_greed = data.get("fear_greed", {})
        ai_analysis = data.get("ai_analysis", "")

        # Форматируем дату
        today = datetime.now()
        weekday_names = [
            "Понедельник", "Вторник", "Среда", "Четверг",
            "Пятница", "Суббота", "Воскресенье"
        ]
        weekday = weekday_names[today.weekday()]
        date_str = today.strftime("%d.%m.%Y")

        # Собираем пост (HTML формат для blockquote)
        lines = []

        # Заголовок
        lines.append(f"📊 <b>Еженедельный обзор рынка</b>")
        lines.append(f"🗓 {weekday}, {date_str}")
        lines.append("")

        # Фаза рынка
        phase_ru = market_cycle.get("phase_ru", "Неизвестно")
        lines.append(f"<b>🔄 Фаза рынка:</b> {phase_ru}")
        lines.append("")

        # Bitcoin + индикаторы компактно
        indicators = btc.get("indicators", {})
        btc_info = f"<b>₿ BTC:</b> {btc.get('price_formatted', 'N/A')} ({btc.get('weekly_change_formatted', 'N/A')})"
        lines.append(btc_info)

        # Индикаторы в одну строку
        ind_parts = []
        if indicators.get("rsi"):
            rsi = indicators["rsi"]
            rsi_signal = indicators.get("rsi_signal", "")
            rsi_icon = "🔴" if rsi_signal == "overbought" else "🟢" if rsi_signal == "oversold" else ""
            ind_parts.append(f"RSI {rsi}{rsi_icon}")

        if indicators.get("macd") is not None:
            macd_signal = indicators.get("macd_crossover", "")
            macd_icon = "🟢" if macd_signal == "bullish" else "🔴"
            ind_parts.append(f"MACD {macd_icon}")

        if indicators.get("ema_trend"):
            ema_trend = indicators.get("ema_trend", "")
            ema_icon = "🟢" if "up" in ema_trend else "🔴" if "down" in ema_trend else "⚪"
            ind_parts.append(f"EMA {ema_icon}")

        if ind_parts:
            lines.append(f"📊 {' · '.join(ind_parts)}")

        # Ethereum компактно
        eth_info = f"<b>Ξ ETH:</b> {eth.get('price_formatted', 'N/A')} ({eth.get('weekly_change_formatted', 'N/A')})"
        lines.append(eth_info)
        lines.append("")

        # Доминация в одну строку
        lines.append(f"👑 BTC.D: {btc.get('dominance_formatted', 'N/A')} · OTHERS.D: {others.get('formatted', 'N/A')}")

        # Fear & Greed компактно
        fg_emoji = fear_greed.get("emoji", "😐")
        fg_current = fear_greed.get("current", "N/A")
        lines.append(f"{fg_emoji} Fear & Greed: {fg_current}")
        lines.append("")

        # AI анализ с подписью Syntra AI в blockquote
        if ai_analysis:
            lines.append("<b>🤖 Syntra AI:</b>")
            lines.append(f"<blockquote>{ai_analysis}</blockquote>")

        content = "\n".join(lines)

        logger.debug("Контент еженедельного поста сгенерирован: {} символов", len(content))
        return content

    except Exception as e:
        logger.exception("Ошибка генерации контента еженедельного поста: {}", str(e))
        return None


async def get_weekly_photo_file_id() -> Optional[str]:
    """Получить file_id фото для еженедельного поста из настроек"""
    try:
        from src.database.crud.setting import get_setting_crud
        setting_crud = get_setting_crud()
        photo_file_id = await setting_crud.get_setting("weekly_analytics.photo_file_id")
        return photo_file_id if photo_file_id else None
    except Exception as e:
        logger.warning("Не удалось получить фото для еженедельного поста: {}", str(e))
        return None


async def save_weekly_post(
    content: str,
    auto_publish: bool = True,
    photo_file_id: Optional[str] = None
) -> Optional[Any]:
    """
    Сохранить еженедельный пост в БД и опционально опубликовать

    Args:
        content: Текст поста
        auto_publish: Автоматически публиковать
        photo_file_id: ID фото для публикации

    Returns:
        Объект созданного поста или None
    """
    try:
        config = get_config()

        # Генерируем уникальный message_id
        message_id = int(time.time())

        # Проверяем и создаем канал в БД если не существует
        from src.database.crud.channel import get_channel_crud
        channel_crud = get_channel_crud()

        existing_channel = await channel_crud.get_by_channel_id(config.TARGET_CHANNEL_ID)
        if not existing_channel:
            from src.database.models.channel import Channel
            system_channel = Channel(
                channel_id=config.TARGET_CHANNEL_ID,
                username="weekly_posts_system",
                title="Системные еженедельные посты",
                is_active=True
            )
            await channel_crud.create(system_channel)
            logger.info("Создан системный канал для еженедельных постов")

        # Определяем статус
        if auto_publish:
            post_status = PostStatus.APPROVED
            posted_date = datetime.now()
        else:
            post_status = PostStatus.PENDING
            posted_date = None

        post = create_post(
            channel_id=config.TARGET_CHANNEL_ID,
            message_id=message_id,
            original_text=content,
            processed_text=content,
            photo_file_id=photo_file_id,
            status=post_status,
            relevance_score=10,
            sentiment=PostSentiment.NEUTRAL,
            ai_analysis="Еженедельный аналитический пост от SyntraAI",
            posted_date=posted_date,
            scheduled_date=None
        )

        post_crud = get_post_crud()
        created_post = await post_crud.create(post)

        if created_post and auto_publish:
            success = await publish_weekly_post(created_post, content)
            if success:
                logger.info("✅ Еженедельный пост опубликован: ID {}", created_post.id)
            else:
                logger.error("❌ Ошибка публикации еженедельного поста: ID {}", created_post.id)

        return created_post

    except Exception as e:
        logger.exception("Ошибка сохранения еженедельного поста: {}", str(e))
        return None


async def publish_weekly_post(post, content: str) -> bool:
    """
    Опубликовать еженедельный пост в целевой канал

    Args:
        post: Объект поста из БД
        content: Содержимое поста

    Returns:
        True если пост опубликован успешно
    """
    try:
        logger.info("📤 Публикация еженедельного поста в канал")

        config = get_config()
        bot = get_bot_instance()

        # Добавляем футер
        content = add_footer_to_post(content, parse_mode="HTML")

        # Публикуем с фото или без
        if post.photo_file_id:
            logger.info("📷 Публикация поста с фото")
            sent_message = await bot.send_photo(
                chat_id=config.TARGET_CHANNEL_ID,
                photo=post.photo_file_id,
                caption=content,
                parse_mode="HTML"
            )
        else:
            logger.info("📝 Публикация текстового поста")
            sent_message = await bot.send_message(
                chat_id=config.TARGET_CHANNEL_ID,
                text=content,
                parse_mode="HTML"
            )

        if sent_message:
            # Обновляем статус в БД
            post_crud = get_post_crud()
            current_post = await post_crud.get_by_id(post.id)
            if current_post:
                current_post.status = PostStatus.POSTED
                current_post.posted_date = datetime.now()
                await post_crud.update(current_post)

            # Проверяем настройку закрепления
            try:
                from src.database.crud.setting import get_bool_setting
                pin_enabled = await get_bool_setting("weekly_analytics.pin_enabled", False)

                if pin_enabled:
                    await bot.pin_chat_message(
                        chat_id=config.TARGET_CHANNEL_ID,
                        message_id=sent_message.message_id,
                        disable_notification=True
                    )
                    logger.info("📌 Еженедельный пост закреплен")

            except Exception as pin_error:
                logger.warning("⚠️ Не удалось закрепить пост: {}", str(pin_error))

            logger.info("✅ Еженедельный пост опубликован: message_id {}", sent_message.message_id)
            return True

        return False

    except Exception as e:
        logger.exception("❌ Ошибка публикации еженедельного поста: {}", str(e))
        return False


async def notify_owner_about_weekly_post(post) -> None:
    """Отправить уведомление владельцу о еженедельном посте"""
    try:
        config = get_config()
        bot = get_bot_instance()

        notification_text = f"""📊 <b>Еженедельный обзор рынка опубликован!</b>

🆔 ID поста: {post.id}
🕐 Время: {datetime.now().strftime('%H:%M')}
📏 Длина: {len(post.processed_text)} символов

Данные получены от SyntraAI."""

        await bot.send_message(
            chat_id=config.OWNER_ID,
            text=notification_text,
            parse_mode="HTML"
        )

        logger.info("Уведомление о еженедельном посте отправлено владельцу")

    except Exception as e:
        logger.warning("Ошибка отправки уведомления: {}", str(e))


async def create_test_weekly_post() -> Optional[str]:
    """
    Создать тестовый еженедельный пост и отправить ВЛАДЕЛЬЦУ для превью
    (не публикует в канал, только показывает владельцу)

    Returns:
        Текст контента или None при ошибке
    """
    try:
        logger.info("🧪 Создание тестового еженедельного поста (превью для владельца)")

        # Получаем данные от SyntraAI
        syntra_client = get_syntra_client()
        weekly_data = await syntra_client.get_weekly_analytics()

        if not weekly_data:
            logger.error("❌ Не удалось получить данные от SyntraAI")
            return None

        # Генерируем контент
        content = generate_weekly_content(weekly_data)
        if not content:
            return None

        # Получаем фото
        photo_file_id = await get_weekly_photo_file_id()

        # Добавляем футер
        content_with_footer = add_footer_to_post(content, parse_mode="HTML")

        # Отправляем ВЛАДЕЛЬЦУ (не в канал!)
        config = get_config()
        bot = get_bot_instance()

        if photo_file_id:
            await bot.send_photo(
                chat_id=config.OWNER_ID,
                photo=photo_file_id,
                caption=content_with_footer,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                chat_id=config.OWNER_ID,
                text=content_with_footer,
                parse_mode="HTML"
            )

        logger.info("✅ Тестовый пост отправлен владельцу (ID: {})", config.OWNER_ID)
        return content

    except Exception as e:
        logger.exception("Ошибка создания тестового поста: {}", str(e))
        return None
