"""
Задача мониторинга каналов
Периодическая проверка и запуск мониторинга новых постов
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.userbot.monitor import get_channel_monitor
from src.userbot.auth_manager import get_auth_manager
from src.database.crud.channel import get_channel_crud
from src.database.crud.post import get_post_crud
from src.database.models.post import PostStatus
from src.ai.processor import get_ai_processor
from src.utils.exceptions import TaskExecutionError

# Настройка логгера модуля
logger = logger.bind(module="scheduler_monitoring")


async def check_monitoring_health() -> None:
    """
    Проверка состояния мониторинга каналов БЕЗ перезапуска
    Мониторинг запускается в main.py как постоянная фоновая задача
    """
    try:
        logger.info("🔄 Проверка состояния мониторинга каналов")
        
        # Получаем монитор каналов
        monitor = get_channel_monitor()
        
        # Проверяем статус мониторинга
        monitor_status = monitor.get_status()
        
        if not monitor_status.get("is_monitoring"):
            logger.warning("⚠️ Мониторинг остановлен!")
            
            # Попытка автоматического восстановления
            recovery_success = await attempt_monitoring_recovery(monitor)
            
            if not recovery_success:
                logger.warning("💡 Требуется ручной перезапуск или проверка UserBot авторизации")
                # Отправляем уведомление владельцу только если автовосстановление не сработало
                await send_monitoring_alert("Мониторинг каналов остановлен - требуется ручное вмешательство")
            else:
                logger.info("✅ Мониторинг автоматически восстановлен")
            
        else:
            logger.debug("✅ Мониторинг активен")
            
            # Проверяем время работы
            uptime_seconds = monitor_status.get("uptime_seconds", 0)
            if uptime_seconds > 3600:  # Больше часа
                uptime_hours = uptime_seconds / 3600
                logger.debug("📈 Мониторинг работает стабильно: {:.1f} часов", uptime_hours)
                
                # 🔄 АВТОМАТИЧЕСКАЯ ПЕРЕРЕГИСТРАЦИЯ каждые 2 часа для предотвращения потери событий
                if uptime_hours >= 2.0 and (int(uptime_hours * 10) % 20) == 0:  # Каждые 2 часа
                    logger.warning("🔄 Время автоматической перерегистрации обработчиков (uptime: {:.1f}h)", uptime_hours)
                    try:
                        reregister_success = await monitor.force_reregister_handlers()
                        
                        if reregister_success:
                            logger.info("✅ Автоматическая перерегистрация успешна")
                        else:
                            logger.error("❌ Автоматическая перерегистрация не удалась")
                            await send_monitoring_alert("Ошибка автоматической перерегистрации Telethon")
                    except Exception as e:
                        logger.error("❌ Критическая ошибка автоперерегистрации: {}", str(e))
            
            # Проверяем качество соединения ТОЛЬКО если мониторинг активен
            await perform_connection_health_check(monitor)
        
        # Получаем статистику выполнения
        execution_stats = await get_monitoring_statistics()
        
        active_channels_count = execution_stats.get("active_channels", 0)
        processed_posts_count = execution_stats.get("processed_posts", 0)
        pending_posts_count = execution_stats.get("pending_posts", 0)
        
        logger.info("📊 Статистика мониторинга: {} каналов, {} постов обработано, {} на модерации", 
                   active_channels_count, processed_posts_count, pending_posts_count)
        
        if active_channels_count == 0:
            logger.info("🎯 Для начала работы:")
            logger.info("   1. Добавьте каналы: /channels в боте")
            logger.info("   2. Подключите UserBot: /start -> 'Подключить UserBot'") 
            logger.info("   3. Добавьте примеры стиля: /examples в боте")
        
        # Проверяем нет ли проблем с каналами
        await check_channels_health()
        
        logger.info("✅ Проверка состояния завершена")
        
    except Exception as e:
        logger.error("❌ Ошибка проверки мониторинга: {}", str(e))
        raise TaskExecutionError("monitoring_check", str(e))


async def send_monitoring_alert(message: str) -> None:
    """Отправить уведомление владельцу о проблемах с мониторингом"""
    try:
        from src.utils.config import get_config
        from src.bot.main import get_bot_instance
        
        config = get_config()
        bot = get_bot_instance()
        
        alert_text = f"⚠️ <b>Внимание!</b>\n\n{message}\n\n⚙️ Проверьте состояние системы: /status"
        
        await bot.send_message(
            chat_id=config.OWNER_ID,
            text=alert_text,
            parse_mode="HTML"
        )
        
        logger.info("Уведомление о проблеме отправлено владельцу")
        
    except Exception as e:
        logger.error("Не удалось отправить уведомление: {}", str(e))


async def get_monitoring_statistics() -> Dict[str, Any]:
    """Получить статистику мониторинга"""
    try:
        channel_crud = get_channel_crud()
        post_crud = get_post_crud()
        
        # Активные каналы
        active_channels = await channel_crud.get_active_channels()
        
        # Посты за последние 24 часа
        yesterday = datetime.now() - timedelta(days=1)
        recent_posts = await post_crud.get_posts_since(yesterday)
        
        # Посты на модерации
        pending_posts = await post_crud.get_posts_by_status(PostStatus.PENDING)
        
        return {
            "active_channels": len(active_channels),
            "processed_posts": len(recent_posts),
            "pending_posts": len(pending_posts),
            "channels_with_posts": len(set(post.channel_id for post in recent_posts)),
            "last_check": datetime.now()
        }
        
    except Exception as e:
        logger.error("Ошибка получения статистики мониторинга: {}", str(e))
        return {}


async def check_channels_health() -> None:
    """Проверить здоровье каналов"""
    try:
        logger.debug("🔍 Проверка здоровья каналов")
        
        channel_crud = get_channel_crud()
        active_channels = await channel_crud.get_active_channels()
        
        if not active_channels:
            logger.warning("⚠️ Нет активных каналов для мониторинга")
            logger.info("💡 Добавьте каналы через бот командой /channels")
            return
        
        # Проверяем каналы без активности за последние 24 часа
        yesterday = datetime.now() - timedelta(days=1)
        inactive_channels = []
        
        for channel in active_channels:
            post_crud = get_post_crud()
            recent_posts = await post_crud.get_posts_by_channel_since(
                channel.channel_id, 
                yesterday
            )
            
            if not recent_posts:
                inactive_channels.append(channel)
        
        if inactive_channels:
            logger.warning("📺 Каналы без активности за 24 часа: {}", 
                          len(inactive_channels))
            
            for channel in inactive_channels[:3]:  # Показываем первые 3
                channel_name = channel.title or channel.username or f"ID: {channel.channel_id}"
                logger.warning("  • {}", channel_name)
        
        # Проверяем каналы с высокой активностью
        high_activity_channels = []
        for channel in active_channels:
            post_crud = get_post_crud()
            recent_posts = await post_crud.get_posts_by_channel_since(
                channel.channel_id, 
                yesterday
            )
            
            if len(recent_posts) > 10:  # Более 10 постов за день
                high_activity_channels.append((channel, len(recent_posts)))
        
        if high_activity_channels:
            logger.info("🔥 Каналы с высокой активностью:")
            for channel, count in high_activity_channels[:3]:
                channel_name = channel.title or channel.username or f"ID: {channel.channel_id}"
                logger.info("  • {}: {} постов за 24ч", channel_name, count)
        
    except Exception as e:
        logger.error("Ошибка проверки здоровья каналов: {}", str(e))




async def check_monitoring_performance() -> Dict[str, Any]:
    """Проверить производительность мониторинга"""
    try:
        monitor = get_channel_monitor()
        status = monitor.get_status()
        
        performance_metrics = {
            "is_running": status.get("is_monitoring", False),
            "uptime_seconds": status.get("uptime_seconds", 0),
            "handler_statistics": status.get("handler_statistics", {}),
            "memory_usage": None,  # Здесь можно добавить мониторинг памяти
            "cpu_usage": None      # И CPU если нужно
        }
        
        # Проверяем нет ли проблем с производительностью
        if performance_metrics["uptime_seconds"] > 86400:  # Более 24 часов
            logger.info("✅ Мониторинг стабильно работает {} часов", 
                       performance_metrics["uptime_seconds"] // 3600)
        
        return performance_metrics
        
    except Exception as e:
        logger.error("Ошибка проверки производительности: {}", str(e))
        return {}


async def cleanup_monitoring_data() -> None:
    """Очистка старых данных мониторинга"""
    try:
        logger.debug("🧹 Очистка старых данных мониторинга")
        
        # Здесь можно добавить логику очистки:
        # - Старых логов
        # - Временных файлов
        # - Кэша изображений
        # Пока оставляем пустым
        
        logger.debug("Очистка данных мониторинга завершена")
        
    except Exception as e:
        logger.error("Ошибка очистки данных мониторинга: {}", str(e))


async def perform_connection_health_check(monitor) -> None:
    """
    Выполнить проверку здоровья соединения UserBot
    
    Args:
        monitor: Экземпляр ChannelMonitor
    """
    try:
        logger.debug("💗 Проверка здоровья соединения UserBot")
        
        status = monitor.get_status()
        
        if not status.get("client_connected"):
            logger.warning("⚠️ Клиент не подключен, пропускаем health check")
            return
        
        # Получаем клиент и проверяем его состояние
        if hasattr(monitor, 'client') and monitor.client:
            try:
                # Пытаемся сделать простой API вызов для проверки соединения
                me = await monitor.client.client.get_me()
                logger.debug("✅ Health check пройден: пользователь {}", getattr(me, 'username', 'unknown'))
                
            except Exception as health_error:
                logger.warning("⚠️ Health check не прошел: {}", str(health_error))
                
                # Если соединение проблемное, пытаемся переподключиться
                try:
                    reconnect_success = await monitor.client.ensure_connected()
                    if reconnect_success:
                        logger.info("🔄 Соединение восстановлено после health check")
                    else:
                        logger.error("❌ Не удалось восстановить соединение после health check")
                except Exception as reconnect_error:
                    logger.error("❌ Ошибка переподключения после health check: {}", str(reconnect_error))
        
    except Exception as e:
        logger.error("Ошибка проверки здоровья соединения: {}", str(e))


async def attempt_monitoring_recovery(monitor) -> bool:
    """
    Попытка автоматического восстановления мониторинга
    
    Args:
        monitor: Экземпляр ChannelMonitor
        
    Returns:
        True если мониторинг успешно восстановлен
    """
    try:
        logger.info("🔄 Попытка автоматического восстановления мониторинга...")
        
        # Проверяем состояние авторизации UserBot
        auth_manager = get_auth_manager()
        auth_status = await auth_manager.get_status()
        
        logger.debug("Статус авторизации UserBot: {}", auth_status)
        
        # Если UserBot не подключен, проверяем возможность восстановления
        if not await auth_manager.is_connected():
            logger.info("🔌 UserBot не подключен, пытаемся восстановить соединение...")
            
            # Пытаемся проверить существующую сессию
            from src.userbot.auth_manager import AuthStatus
            if auth_status == AuthStatus.DISCONNECTED:
                # Попытка автоматического подключения с существующей сессией
                auth_result = await auth_manager.start_auth()
                if not auth_result.success:
                    logger.warning("❌ Не удалось автоматически восстановить авторизацию: {}", auth_result.error)
                    return False
            else:
                logger.warning("❌ UserBot требует ручной переавторизации (статус: {})", auth_status)
                return False
        
        # Если авторизация успешна, пытаемся перезапустить мониторинг
        logger.info("✅ UserBot авторизован, перезапускаем мониторинг...")
        
        # Останавливаем текущий мониторинг если он частично работает
        if monitor.is_monitoring:
            try:
                await monitor.stop_monitoring()
                logger.debug("Старый мониторинг остановлен")
            except Exception as stop_error:
                logger.debug("Ошибка остановки старого мониторинга: {}", str(stop_error))
        
        # Небольшая пауза для стабилизации
        await asyncio.sleep(2)
        
        # Запускаем мониторинг заново
        await monitor.start_monitoring()
        
        # Проверяем что мониторинг действительно запустился
        new_status = monitor.get_status()
        if new_status.get("is_monitoring"):
            logger.info("🎉 Мониторинг успешно восстановлен автоматически!")
            
            # Отправляем уведомление об успешном восстановлении
            await send_monitoring_alert("✅ Мониторинг автоматически восстановлен")
            
            # Проверяем на пропущенные сообщения во время простоя
            try:
                await check_for_missed_messages()
            except Exception as missed_error:
                logger.warning("Ошибка проверки пропущенных сообщений: {}", str(missed_error))
            
            return True
        else:
            logger.error("❌ Мониторинг не запустился после попытки восстановления")
            return False
            
    except Exception as e:
        logger.error("❌ Критическая ошибка автоматического восстановления: {}", str(e))
        return False


async def check_for_missed_messages() -> None:
    """
    Проверить на пропущенные сообщения после восстановления соединения
    Реализует backfill логику для обнаружения пропущенных постов
    """
    try:
        logger.info("🔍 Проверка на пропущенные сообщения после переподключения")
        
        monitor = get_channel_monitor()
        
        if not monitor.client or not monitor.client.is_connected:
            logger.warning("Клиент не подключен, пропускаем проверку пропущенных сообщений")
            return
        
        # Получаем список активных каналов
        channel_crud = get_channel_crud()
        active_channels = await channel_crud.get_active_channels()
        
        if not active_channels:
            logger.debug("Нет активных каналов для проверки")
            return
        
        missed_count = 0
        
        for channel in active_channels[:5]:  # Проверяем максимум 5 каналов за раз чтобы не перегрузить
            try:
                # Получаем последний сохраненный message_id для канала
                last_saved_message_id = channel.last_message_id or 0
                
                logger.debug("Проверка канала {} с last_message_id={}", 
                           channel.channel_id, last_saved_message_id)
                
                # Получаем последние сообщения из канала через UserBot
                entity = await monitor.client.client.get_entity(channel.channel_id)
                
                # Проверяем последние 10 сообщений
                message_count = 0
                async for message in monitor.client.client.iter_messages(entity, limit=10):
                    message_count += 1
                    
                    # Если message_id больше последнего сохраненного
                    if message.id > last_saved_message_id:
                        # Проверяем что это подходящий пост (с фото)
                        if hasattr(message, 'media') and message.media:
                            from telethon.tl.types import MessageMediaPhoto
                            if isinstance(message.media, MessageMediaPhoto):
                                logger.warning("🔍 Найдено пропущенное сообщение {} в канале {}", 
                                             message.id, channel.channel_id)
                                missed_count += 1
                    else:
                        # Если дошли до сообщений которые уже обрабатывали, прекращаем
                        break
                
                if message_count == 0:
                    logger.debug("Канал {} пустой или недоступен", channel.channel_id)
                
                # Небольшая задержка между каналами
                await asyncio.sleep(1)
                
            except Exception as channel_error:
                logger.warning("Ошибка проверки канала {}: {}", channel.channel_id, str(channel_error))
                continue
        
        if missed_count > 0:
            logger.warning("⚠️ Обнаружено {} потенциально пропущенных сообщений", missed_count)
            logger.info("💡 Пропущенные сообщения будут обработаны при следующем поступлении событий")
        else:
            logger.info("✅ Пропущенных сообщений не обнаружено")
        
    except Exception as e:
        logger.error("Ошибка проверки пропущенных сообщений: {}", str(e))


