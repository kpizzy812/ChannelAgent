"""
Фильтры сообщений для UserBot
Определяют какие сообщения должны быть обработаны
"""

from datetime import datetime, timedelta
from typing import List, Set, Optional, Callable

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Сторонние библиотеки
from telethon import events
from telethon.tl.types import MessageMediaPhoto, Message, Channel, Chat

# Локальные импорты
from src.database.connection import get_db_connection
from src.utils.exceptions import DatabaseError, MessageProcessingError

# Настройка логгера модуля
logger = logger.bind(module="userbot_filters")


class MessageFilters:
    """
    Класс фильтров для сообщений UserBot
    Определяет логику фильтрации входящих сообщений
    """
    
    def __init__(self):
        """Инициализация фильтров"""
        self._monitored_channels: Set[int] = set()
        # Устанавливаем старую дату чтобы кеш обновился при первом запросе
        self._last_channel_update = datetime.now() - timedelta(hours=1)
        self._channel_cache_ttl = timedelta(minutes=5)  # Кеш на 5 минут
        
        logger.debug("Инициализированы фильтры сообщений")
    
    async def should_process_message(self, event: events.NewMessage.Event) -> bool:
        """
        Главная функция проверки - должно ли сообщение быть обработано
        
        Args:
            event: Событие нового сообщения
            
        Returns:
            True если сообщение должно быть обработано
        """
        try:
            message = event.message
            channel_id = message.peer_id.channel_id if hasattr(message.peer_id, 'channel_id') else None
            
            logger.info("🔍 Проверка сообщения {} из канала {}", message.id, channel_id)
            
            # Базовые проверки
            if not await self._basic_message_checks(message):
                logger.debug("❌ Сообщение не прошло базовые проверки")
                return False
            
            # Проверка канала
            if not await self._is_monitored_channel(message.peer_id.channel_id):
                logger.debug("❌ Канал {} не отслеживается", message.peer_id.channel_id)
                return False
            
            # Проверка медиа
            if not self._has_required_media(message):
                logger.debug("❌ Сообщение не прошло проверку медиа")
                return False
            
            # Проверка новизны сообщения
            if not self._is_recent_message(message):
                logger.debug("❌ Сообщение слишком старое")
                return False
            
            # Проверка на дубликаты
            if await self._is_already_processed(message):
                logger.debug("❌ Сообщение уже обработано")
                return False
            
            logger.info("✅ Сообщение {} из канала {} прошло все фильтры", 
                        message.id, message.peer_id.channel_id)
            return True
            
        except Exception as e:
            logger.error("Ошибка при фильтрации сообщения: {}", str(e))
            return False
    
    async def _basic_message_checks(self, message: Message) -> bool:
        """Базовые проверки сообщения"""
        
        # Сообщение должно существовать
        if not message:
            logger.debug("Сообщение пустое")
            return False
        
        # Должен быть из канала
        if not hasattr(message.peer_id, 'channel_id'):
            logger.debug("Сообщение не из канала")
            return False
        
        # Не должно быть сервисным сообщением  
        if hasattr(message, 'service') and message.service:
            logger.debug("Сервисное сообщение пропущено")
            return False
        
        # Должен быть текст или медиа
        if not message.text and not message.media:
            logger.debug("Сообщение без текста и медиа")
            return False
        
        return True
    
    async def _is_monitored_channel(self, channel_id: int) -> bool:
        """Проверка, отслеживается ли канал"""
        
        # Преобразуем в полный ID канала (с префиксом -100)
        full_channel_id = int(f"-100{channel_id}")
        
        # Исключаем целевой канал бота из мониторинга
        from src.utils.config import get_config
        config = get_config()
        target_channel_id = getattr(config, 'TARGET_CHANNEL_ID', None)
        
        if target_channel_id and full_channel_id == target_channel_id:
            logger.debug("❌ Пропускаем целевой канал бота: {}", full_channel_id)
            return False
        
        # Обновляем кеш каналов если нужно
        if self._should_update_channel_cache():
            await self._update_monitored_channels()
        
        is_monitored = full_channel_id in self._monitored_channels
        
        if not is_monitored:
            logger.debug("Канал {} не отслеживается", full_channel_id)
        
        return is_monitored
    
    def _has_required_media(self, message: Message) -> bool:
        """Проверка медиа сообщения (принимаем любые посты - с медиа и без)"""
        
        if not message.media:
            logger.debug("Сообщение без медиа (текстовый пост)")
            return True
        
        # Логируем тип медиа для отладки
        if isinstance(message.media, MessageMediaPhoto):
            logger.debug("Сообщение содержит фото")
        else:
            logger.debug("Сообщение содержит медиа: {}", type(message.media).__name__)
        
        # Принимаем любые посты - с медиа и без
        return True
    
    def _is_recent_message(self, message: Message, max_age_hours: int = 24) -> bool:
        """Проверка свежести сообщения"""
        
        if not message.date:
            logger.debug("У сообщения нет даты")
            return False
        
        message_age = datetime.now() - message.date.replace(tzinfo=None)
        max_age = timedelta(hours=max_age_hours)
        
        if message_age > max_age:
            logger.debug("Сообщение слишком старое: {} часов", message_age.total_seconds() / 3600)
            return False
        
        return True
    
    async def _is_already_processed(self, message: Message) -> bool:
        """Проверка на дубликаты в базе данных"""
        
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM posts WHERE channel_id = ? AND message_id = ?",
                    (int(f"-100{message.peer_id.channel_id}"), message.id)
                )
                count = (await cursor.fetchone())[0]
                
                if count > 0:
                    logger.debug("Сообщение уже обработано: канал {}, сообщение {}", 
                               message.peer_id.channel_id, message.id)
                    return True
                
                return False
                
        except Exception as e:
            logger.error("Ошибка проверки дубликатов: {}", str(e))
            # В случае ошибки БД не блокируем обработку
            return False
    
    def _should_update_channel_cache(self) -> bool:
        """Проверка необходимости обновления кеша каналов"""
        return datetime.now() - self._last_channel_update > self._channel_cache_ttl
    
    async def _update_monitored_channels(self) -> None:
        """Обновление списка отслеживаемых каналов из БД"""
        
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT channel_id FROM channels WHERE is_active = 1"
                )
                channels = await cursor.fetchall()
                
                old_count = len(self._monitored_channels)
                self._monitored_channels = {row[0] for row in channels}
                new_count = len(self._monitored_channels)
                
                self._last_channel_update = datetime.now()
                
                logger.info("Обновлен кеш каналов: {} -> {} каналов", old_count, new_count)
                
        except Exception as e:
            logger.error("Ошибка обновления списка каналов: {}", str(e))
            raise DatabaseError(f"Не удалось загрузить список каналов: {str(e)}")
    
    def create_channel_filter(self, channel_ids: List[int]) -> Callable:
        """
        Создать фильтр для конкретных каналов
        
        Args:
            channel_ids: Список ID каналов для фильтрации
            
        Returns:
            Функция-фильтр для Telethon events
        """
        def filter_func(event):
            if not hasattr(event.message.peer_id, 'channel_id'):
                return False
            
            full_channel_id = int(f"-100{event.message.peer_id.channel_id}")
            return full_channel_id in channel_ids
        
        return filter_func
    
    def create_media_filter(self, media_types: List[type]) -> Callable:
        """
        Создать фильтр по типам медиа
        
        Args:
            media_types: Список типов медиа для фильтрации
            
        Returns:
            Функция-фильтр для Telethon events
        """
        def filter_func(event):
            if not event.message.media:
                return False
            
            return any(isinstance(event.message.media, media_type) for media_type in media_types)
        
        return filter_func
    
    async def get_monitored_channels(self) -> Set[int]:
        """Получить список отслеживаемых каналов"""
        if self._should_update_channel_cache():
            await self._update_monitored_channels()
        
        return self._monitored_channels.copy()
    
    async def add_channel_to_monitoring(self, channel_id: int) -> None:
        """Добавить канал в мониторинг"""
        try:
            async with get_db_connection() as conn:
                # Проверяем существование канала
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM channels WHERE channel_id = ?",
                    (channel_id,)
                )
                exists = (await cursor.fetchone())[0] > 0
                
                if exists:
                    # Активируем существующий канал
                    await conn.execute(
                        "UPDATE channels SET is_active = 1 WHERE channel_id = ?",
                        (channel_id,)
                    )
                else:
                    # Добавляем новый канал
                    await conn.execute(
                        """INSERT INTO channels 
                           (channel_id, is_active, created_at) 
                           VALUES (?, 1, datetime('now'))""",
                        (channel_id,)
                    )
                
                await conn.commit()
                
                # Обновляем кеш
                self._monitored_channels.add(channel_id)
                
                logger.info("Канал {} добавлен в мониторинг", channel_id)
                
        except Exception as e:
            logger.error("Ошибка добавления канала в мониторинг: {}", str(e))
            raise DatabaseError(f"Не удалось добавить канал {channel_id}: {str(e)}")
    
    async def remove_channel_from_monitoring(self, channel_id: int) -> None:
        """Удалить канал из мониторинга"""
        try:
            async with get_db_connection() as conn:
                await conn.execute(
                    "UPDATE channels SET is_active = 0 WHERE channel_id = ?",
                    (channel_id,)
                )
                await conn.commit()
                
                # Обновляем кеш
                self._monitored_channels.discard(channel_id)
                
                logger.info("Канал {} удален из мониторинга", channel_id)
                
        except Exception as e:
            logger.error("Ошибка удаления канала из мониторинга: {}", str(e))
            raise DatabaseError(f"Не удалось удалить канал {channel_id}: {str(e)}")


# Глобальный экземпляр фильтров
_message_filters: Optional[MessageFilters] = None


def get_message_filters() -> MessageFilters:
    """Получить глобальный экземпляр фильтров"""
    global _message_filters
    
    if _message_filters is None:
        _message_filters = MessageFilters()
    
    return _message_filters