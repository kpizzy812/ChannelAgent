"""
Задача создания ежедневных постов
Генерация постов с криптовалютными данными и рыночными сводками
С retry механизмом при сетевых ошибках
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.scheduler.coingecko import get_coingecko_data, format_crypto_summary
from src.database.crud.post import get_post_crud
from src.database.models.post import PostStatus, PostSentiment, create_post
from src.ai.styler.formatter import ContentFormatter
from src.bot.main import get_bot_instance
from src.utils.config import get_config
from src.utils.exceptions import TaskExecutionError
from src.utils.post_footer import add_footer_to_post

# Настройка логгера модуля
logger = logger.bind(module="scheduler_daily_posts")

# Константы для retry механизма
MAX_PUBLISH_RETRIES = 3  # Максимум попыток публикации
RETRY_DELAY_MINUTES = 5  # Задержка между попытками в минутах


async def create_daily_crypto_post() -> None:
    """Создать ежедневный пост с криптовалютными данными"""
    try:
        logger.info("📊 Создание ежедневного крипто-поста")
        
        # Проверяем включена ли функция из БД
        from src.database.crud.setting import get_bool_setting
        daily_post_enabled = await get_bool_setting("daily_post.enabled", True)  # По умолчанию включено
        if not daily_post_enabled:
            logger.debug("Ежедневные посты отключены в настройках")
            return
        
        # Проверяем не создавали ли мы уже пост сегодня
        if await check_daily_post_exists():
            logger.info("Ежедневный пост уже создан сегодня")
            return
        
        # Получаем данные криптовалют
        crypto_data = await get_coingecko_data()
        
        if not crypto_data:
            logger.error("❌ Не удалось получить данные криптовалют")
            raise TaskExecutionError("daily_crypto_post", "Нет данных CoinGecko")
        
        # Создаем контент поста ТОЛЬКО из пользовательских шаблонов
        from src.scheduler.templates import create_daily_post_from_template, get_template_manager
        
        # Проверяем есть ли пользовательские шаблоны
        template_manager = get_template_manager()
        templates = await template_manager.list_templates()
        user_templates = [t for t in templates if t.get('type') == 'custom']
        
        if not user_templates:
            logger.warning("❌ Нет пользовательских шаблонов для создания ежедневного поста")
            logger.info("Используется fallback к генерации контента без шаблона")
            post_content = await generate_daily_crypto_content(crypto_data)
        else:
            # Используем первый доступный пользовательский шаблон
            post_content = await create_daily_post_from_template(
                template_name=None,  # Автовыбор первого доступного
                custom_variables=None
            )
            
            if not post_content:
                logger.error("❌ Не удалось сгенерировать контент из пользовательского шаблона")
                # Fallback к генерации без шаблона
                post_content = await generate_daily_crypto_content(crypto_data)
        
        if not post_content:
            logger.error("❌ Не удалось сгенерировать контент поста")
            raise TaskExecutionError("daily_crypto_post", "Ошибка генерации контента")
        
        # Получаем информацию о шаблоне для передачи photo_file_id
        photo_file_id = None
        if user_templates:
            template_manager = get_template_manager()
            first_template_name = await template_manager.get_first_available_template()
            if first_template_name:
                template = await template_manager.get_template(first_template_name)
                if template and template.photo_info:
                    photo_file_id = template.photo_info.get('file_id')
                    logger.info("Найдено фото в шаблоне '{}': {}", first_template_name, photo_file_id)
        
        # Создаем пост в БД (по умолчанию автоматически публикуем)
        post = await save_daily_post(post_content, auto_publish=True, photo_file_id=photo_file_id)
        
        if post:
            logger.info("✅ Ежедневный крипто-пост создан: ID {}", post.id)
            
            # Отправляем уведомление владельцу
            await notify_owner_about_daily_post(post)
            
        else:
            logger.error("❌ Не удалось сохранить ежедневный пост")
        
    except Exception as e:
        logger.error("❌ Ошибка создания ежедневного поста: {}", str(e))
        raise TaskExecutionError("daily_crypto_post", str(e))


async def check_daily_post_exists() -> bool:
    """Проверить существует ли уже ежедневный пост за сегодня"""
    try:
        post_crud = get_post_crud()
        
        # Проверяем посты за сегодня с меткой daily_post
        today = datetime.now().date()
        daily_posts = await post_crud.get_posts_by_date_and_type(today, "daily_post")
        
        return len(daily_posts) > 0
        
    except Exception as e:
        logger.error("Ошибка проверки существования ежедневного поста: {}", str(e))
        return False


async def generate_daily_crypto_content(crypto_data: Dict[str, Any]) -> Optional[str]:
    """Сгенерировать контент ежедневного поста"""
    try:
        logger.debug("📝 Генерация контента ежедневного поста")
        
        # Базовые данные
        today = datetime.now()
        weekday_names = [
            "Понедельник", "Вторник", "Среда", "Четверг", 
            "Пятница", "Суббота", "Воскресенье"
        ]
        weekday = weekday_names[today.weekday()]
        date_str = today.strftime("%d.%m.%Y")
        
        # Формируем заголовок
        header = f"📊 **Крипто-сводка на {weekday}, {date_str}**"
        
        # Получаем топ криптовалют
        top_coins = get_top_coins_summary(crypto_data)
        
        # Анализ рынка
        market_analysis = get_market_analysis(crypto_data)
        
        # Интересные факты/данные
        market_insights = get_market_insights(crypto_data)
        
        # Собираем пост
        content_parts = [header]
        
        if top_coins:
            content_parts.append("\n🚀 **Топ криптовалюты:**")
            content_parts.append(top_coins)
        
        if market_analysis:
            content_parts.append("\n📈 **Анализ рынка:**")
            content_parts.append(market_analysis)
        
        if market_insights:
            content_parts.append("\n💡 **Интересное:**")
            content_parts.append(market_insights)
        
        # Добавляем призыв к действию
        content_parts.append("\n#криптовалюты #рынок #анализ")
        
        raw_content = "\n".join(content_parts)
        
        # Форматируем через наш стилизатор
        formatter = ContentFormatter()
        formatted_content = formatter.format_post(
            content=raw_content,
            post_type="analysis"
        )
        
        logger.debug("Контент ежедневного поста сгенерирован: {} символов", 
                    len(formatted_content))
        
        return formatted_content
        
    except Exception as e:
        logger.error("Ошибка генерации контента ежедневного поста: {}", str(e))
        return None


def get_top_coins_summary(crypto_data: Dict[str, Any]) -> str:
    """Получить сводку по топ криптовалютам"""
    try:
        coins = crypto_data.get('coins', [])
        if not coins:
            return ""
        
        summary_lines = []
        
        for coin in coins[:5]:  # Топ 5 монет
            name = coin.get('name', 'Unknown')
            symbol = coin.get('symbol', '').upper()
            price = coin.get('current_price', 0)
            change_24h = coin.get('price_change_percentage_24h', 0)
            
            # Форматирование цены
            if price >= 1:
                price_str = f"${price:,.2f}"
            else:
                price_str = f"${price:.6f}".rstrip('0').rstrip('.')
            
            # Эмодзи для изменения
            if change_24h > 0:
                change_emoji = "📈"
                change_color = "+"
            else:
                change_emoji = "📉"
                change_color = ""
            
            summary_lines.append(
                f"• **{symbol}** ({name}): {price_str} "
                f"{change_emoji} {change_color}{change_24h:.2f}%"
            )
        
        return "\n".join(summary_lines)
        
    except Exception as e:
        logger.error("Ошибка формирования сводки топ монет: {}", str(e))
        return ""


def get_market_analysis(crypto_data: Dict[str, Any]) -> str:
    """Получить анализ рынка"""
    try:
        global_data = crypto_data.get('global', {})
        if not global_data:
            return ""
        
        market_cap = global_data.get('total_market_cap', {}).get('usd', 0)
        market_cap_change = global_data.get('market_cap_change_percentage_24h_usd', 0)
        btc_dominance = global_data.get('market_cap_percentage', {}).get('btc', 0)
        
        analysis_lines = []
        
        # Общая капитализация
        if market_cap:
            market_cap_trillions = market_cap / 1_000_000_000_000
            change_emoji = "📈" if market_cap_change > 0 else "📉"
            
            analysis_lines.append(
                f"💰 Общая капитализация: **${market_cap_trillions:.2f}T** "
                f"{change_emoji} {market_cap_change:+.2f}%"
            )
        
        # Доминация Bitcoin
        if btc_dominance:
            analysis_lines.append(f"👑 Доминация BTC: **{btc_dominance:.1f}%**")
        
        # Оценка настроения рынка
        if market_cap_change > 2:
            sentiment = "🟢 Рынок в зеленой зоне"
        elif market_cap_change < -2:
            sentiment = "🔴 Медвежьи настроения"
        else:
            sentiment = "🟡 Боковое движение"
        
        analysis_lines.append(f"📊 {sentiment}")
        
        return "\n".join(analysis_lines)
        
    except Exception as e:
        logger.error("Ошибка формирования анализа рынка: {}", str(e))
        return ""


def get_market_insights(crypto_data: Dict[str, Any]) -> str:
    """Получить интересные инсайты о рынке"""
    try:
        insights = []
        coins = crypto_data.get('coins', [])
        
        if not coins:
            return ""
        
        # Найдем самую растущую монету
        best_performer = max(coins, key=lambda x: x.get('price_change_percentage_24h', -999))
        if best_performer.get('price_change_percentage_24h', 0) > 10:
            insights.append(
                f"🚀 Лидер роста: **{best_performer['symbol'].upper()}** "
                f"+{best_performer['price_change_percentage_24h']:.1f}%"
            )
        
        # Найдем самую падающую
        worst_performer = min(coins, key=lambda x: x.get('price_change_percentage_24h', 999))
        if worst_performer.get('price_change_percentage_24h', 0) < -10:
            insights.append(
                f"📉 Аутсайдер: **{worst_performer['symbol'].upper()}** "
                f"{worst_performer['price_change_percentage_24h']:.1f}%"
            )
        
        # Случайный факт
        random_facts = [
            "💎 За последние 24 часа было торгов на миллиарды долларов",
            "🌍 Криптовалютный рынок работает 24/7 без выходных",
            "⚡ Каждые 10 минут создается новый блок Bitcoin",
            "🔗 Блокчейн — это цепочка блоков с историей всех транзакций"
        ]
        
        import random
        insights.append(random.choice(random_facts))
        
        return "\n".join(insights)
        
    except Exception as e:
        logger.error("Ошибка формирования инсайтов: {}", str(e))
        return ""


async def save_daily_post(content: str, auto_publish: bool = True, photo_file_id: Optional[str] = None) -> Optional[Any]:
    """Сохранить ежедневный пост в БД"""
    try:
        # Создаем пост с специальной меткой
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
            # Создаем системный канал для ежедневных постов
            from src.database.models.channel import Channel
            system_channel = Channel(
                channel_id=config.TARGET_CHANNEL_ID,
                username="daily_posts_system",
                title="Системные ежедневные посты",
                is_active=True
            )
            await channel_crud.create(system_channel)
            logger.info("Создан системный канал для ежедневных постов: {}", config.TARGET_CHANNEL_ID)
        
        # Определяем статус и время публикации
        if auto_publish:
            # Для автоматических ежедневных постов - публикуем немедленно
            post_status = PostStatus.APPROVED
            scheduled_date = None
            posted_date = datetime.now()
        else:
            # Для ручного создания - отправляем на модерацию
            post_status = PostStatus.PENDING
            scheduled_date = None
            posted_date = None
        
        post = create_post(
            channel_id=config.TARGET_CHANNEL_ID,  # Используем существующий целевой канал
            message_id=message_id,  # Уникальный положительный ID
            original_text=content,
            processed_text=content,
            photo_file_id=photo_file_id,  # Фото из шаблона если есть
            status=post_status,  # Статус зависит от auto_publish
            relevance_score=10,  # Максимальная релевантность
            sentiment=PostSentiment.NEUTRAL,
            ai_analysis="Ежедневный системный пост с криптовалютными данными",
            posted_date=posted_date,
            scheduled_date=scheduled_date
        )
        
        post_crud = get_post_crud()
        created_post = await post_crud.create(post)
        
        if created_post:
            if auto_publish:
                # Автоматически публикуем пост в целевой канал
                success = await publish_daily_post_to_channel(created_post, content)
                if success:
                    logger.info("✅ Ежедневный пост автоматически опубликован: ID {}", created_post.id)
                else:
                    logger.error("❌ Ошибка автоматической публикации поста: ID {}", created_post.id)
            else:
                logger.info("📋 Ежедневный пост сохранен в БД для модерации: ID {}", created_post.id)
        
        return created_post
        
    except Exception as e:
        logger.error("Ошибка сохранения ежедневного поста: {}", str(e))
        return None


async def publish_daily_post_to_channel(post, content: str) -> bool:
    """
    Опубликовать ежедневный пост в целевой канал через UserBot с Premium Emoji
    При ошибке планирует повторную попытку через RETRY_DELAY_MINUTES минут

    Args:
        post: Объект поста из БД
        content: Содержимое поста

    Returns:
        True если пост опубликован успешно
    """
    try:
        logger.info("📤 Публикация ежедневного поста в канал")

        config = get_config()
        sent_message = None

        # Пробуем опубликовать через UserBot с Premium Emoji
        try:
            from src.userbot.publisher import get_userbot_publisher

            publisher = await get_userbot_publisher()

            if publisher and publisher.is_available:
                logger.info("Публикуем ежедневный пост через UserBot с Premium Emoji")

                # Получаем путь к фото если есть
                photo_path = None
                if post.photo_file_id:
                    # Для daily posts фото хранится как file_id, пробуем скачать
                    try:
                        from src.bot.media_handler import get_media_handler
                        media_handler = get_media_handler()
                        photo_path = await media_handler.download_photo_by_file_id(post.photo_file_id)
                        if photo_path:
                            logger.info("Фото скачано для UserBot публикации: {}", photo_path)
                    except Exception as download_error:
                        logger.warning("Не удалось скачать фото: {}", str(download_error))

                # Публикуем через UserBot (футер добавляется внутри publisher.publish_post)
                message_id = await publisher.publish_post(
                    channel_id=config.TARGET_CHANNEL_ID,
                    text=content,
                    photo_path=photo_path,
                    pin_post=False,  # Закрепление обработаем отдельно
                    add_footer=True
                )

                if message_id:
                    logger.info("✅ Ежедневный пост опубликован через UserBot, message_id: {}", message_id)
                    # Создаём фейковый объект для совместимости с дальнейшим кодом
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
            logger.info("Публикуем ежедневный пост через Bot API (без Premium Emoji)")

            # Получаем экземпляр бота
            bot = get_bot_instance()

            # Конвертируем Markdown -> HTML для Bot API
            from src.utils.post_footer import convert_markdown_to_html
            content_html = convert_markdown_to_html(content)

            # Добавляем футер с полезными ссылками (HTML режим для Bot API)
            content_with_footer = add_footer_to_post(content_html, parse_mode="HTML")

            # Проверяем есть ли фото у поста
            if post.photo_file_id:
                logger.info("📷 Публикация поста с фото: {}", post.photo_file_id)
                # Публикуем пост с фото
                sent_message = await bot.send_photo(
                    chat_id=config.TARGET_CHANNEL_ID,
                    photo=post.photo_file_id,
                    caption=content_with_footer,
                    parse_mode="HTML"
                )
            else:
                logger.info("📝 Публикация текстового поста")
                # Публикуем обычный текстовый пост
                sent_message = await bot.send_message(
                    chat_id=config.TARGET_CHANNEL_ID,
                    text=content_with_footer,
                    parse_mode="HTML"
                )

        if sent_message:
            # Обновляем пост в БД - отмечаем как опубликованный
            post_crud = get_post_crud()

            # Получаем текущий пост для обновления
            current_post = await post_crud.get_by_id(post.id)
            if current_post:
                # Обновляем статус и дату публикации, сбрасываем retry_count
                current_post.status = PostStatus.POSTED
                current_post.posted_date = datetime.now()
                if hasattr(current_post, 'retry_count'):
                    current_post.retry_count = 0
                # Сохраняем ID опубликованного сообщения для гиперссылок
                current_post.published_message_id = sent_message.message_id
                await post_crud.update(current_post)

            # Проверяем настройку закрепления постов
            try:
                from src.database.crud.setting import get_setting_crud
                setting_crud = get_setting_crud()
                pin_enabled_setting = await setting_crud.get_setting("daily_post.pin_enabled")
                pin_enabled = pin_enabled_setting and pin_enabled_setting.lower() == 'true'

                if pin_enabled:
                    # Закрепляем пост
                    await bot.pin_chat_message(
                        chat_id=config.TARGET_CHANNEL_ID,
                        message_id=sent_message.message_id,
                        disable_notification=True  # Не уведомляем подписчиков о закреплении
                    )
                    logger.info("📌 Ежедневный пост закреплен в канале")

            except Exception as pin_error:
                # Ошибка закрепления не критична
                logger.warning("⚠️ Не удалось закрепить пост: {}", str(pin_error))

            logger.info("✅ Ежедневный пост опубликован в канал: message_id {}", sent_message.message_id)
            return True
        else:
            logger.error("❌ Не удалось отправить пост в канал")
            await schedule_post_retry(post)
            return False

    except Exception as e:
        logger.error("❌ Ошибка публикации ежедневного поста: {}", str(e))
        # Планируем повторную попытку
        await schedule_post_retry(post)
        return False


async def schedule_post_retry(post) -> bool:
    """
    Запланировать повторную попытку публикации поста

    Args:
        post: Объект поста

    Returns:
        True если retry запланирован, False если лимит исчерпан
    """
    try:
        post_crud = get_post_crud()
        current_post = await post_crud.get_by_id(post.id)

        if not current_post:
            logger.error("Пост {} не найден для retry", post.id)
            return False

        # Получаем текущий retry_count
        retry_count = getattr(current_post, 'retry_count', 0) or 0

        if retry_count >= MAX_PUBLISH_RETRIES:
            logger.error("❌ Пост {} достиг лимита retry ({}/{}), уведомляем владельца",
                        post.id, retry_count, MAX_PUBLISH_RETRIES)
            await notify_owner_about_failed_post(current_post)
            return False

        # Планируем следующую попытку
        next_retry = datetime.now() + timedelta(minutes=RETRY_DELAY_MINUTES)
        new_retry_count = retry_count + 1

        # Обновляем пост: статус SCHEDULED, время = now + RETRY_DELAY_MINUTES
        current_post.status = PostStatus.SCHEDULED
        current_post.scheduled_date = next_retry
        if hasattr(current_post, 'retry_count'):
            current_post.retry_count = new_retry_count
        await post_crud.update(current_post)

        logger.warning("⏰ Пост {} запланирован на retry #{} в {}",
                      post.id, new_retry_count, next_retry.strftime("%H:%M:%S"))
        return True

    except Exception as e:
        logger.error("Ошибка планирования retry для поста {}: {}", post.id, str(e))
        return False


async def notify_owner_about_failed_post(post) -> None:
    """Уведомить владельца о неудачной публикации после всех retry"""
    try:
        config = get_config()
        bot = get_bot_instance()

        notification_text = f"""❌ <b>Ошибка публикации ежедневного поста</b>

🆔 ID поста: {post.id}
🔄 Попыток публикации: {MAX_PUBLISH_RETRIES}
🕐 Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}

Публикация не удалась после {MAX_PUBLISH_RETRIES} попыток.
Возможные причины: сетевые проблемы, Telegram API недоступен.

Используйте /moderation для ручной публикации."""

        await bot.send_message(
            chat_id=config.OWNER_ID,
            text=notification_text,
            parse_mode="HTML"
        )

        logger.info("Уведомление о неудачной публикации отправлено владельцу")

    except Exception as e:
        logger.error("Ошибка отправки уведомления о неудачной публикации: {}", str(e))


async def notify_owner_about_daily_post(post) -> None:
    """Отправить уведомление владельцу о создании ежедневного поста"""
    try:
        config = get_config()
        
        # Получаем экземпляр бота
        bot = get_bot_instance()
        
        notification_text = f"""📊 <b>Ежедневный пост создан!</b>

🆔 ID поста: {post.id}
🕐 Время: {datetime.now().strftime('%H:%M')}
📏 Длина: {len(post.processed_text)} символов

Пост готов к публикации в целевом канале.
Используйте /moderation для просмотра."""
        
        await bot.send_message(
            chat_id=config.OWNER_ID,
            text=notification_text,
            parse_mode="HTML"
        )
        
        logger.info("Уведомление о ежедневном посте отправлено владельцу")
        
    except Exception as e:
        logger.error("Ошибка отправки уведомления о ежедневном посте: {}", str(e))
        # Не критичная ошибка, не прерываем выполнение


async def create_weekly_summary_post() -> None:
    """Создать еженедельный пост-сводку (по воскресеньям)"""
    try:
        logger.info("📅 Создание еженедельной сводки")
        
        # Проверяем что сегодня воскресенье
        if datetime.now().weekday() != 6:  # 6 = воскресенье
            logger.debug("Еженедельная сводка создается только по воскресеньям")
            return
        
        # Получаем данные за неделю
        week_ago = datetime.now() - timedelta(days=7)
        
        # Здесь можно добавить логику анализа недели
        # Пока оставляем заглушку
        
        logger.info("✅ Еженедельная сводка создана")
        
    except Exception as e:
        logger.error("❌ Ошибка создания еженедельной сводки: {}", str(e))


async def create_monthly_report() -> None:
    """Создать месячный отчет (1 числа каждого месяца)"""
    try:
        logger.info("📊 Создание месячного отчета")
        
        # Проверяем что сегодня первое число
        if datetime.now().day != 1:
            logger.debug("Месячный отчет создается только 1 числа")
            return
        
        # Анализ месяца
        # Здесь можно добавить детальную статистику
        
        logger.info("✅ Месячный отчет создан")
        
    except Exception as e:
        logger.error("❌ Ошибка создания месячного отчета: {}", str(e))