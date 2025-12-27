"""
CRUD операции для модели Channel
Создание, чтение, обновление и удаление каналов
"""

from typing import Optional, List
from datetime import datetime

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.database.connection import get_db_connection, get_db_transaction
from src.database.models.channel import Channel
from src.utils.exceptions import DatabaseError, RecordNotFoundError, DuplicateRecordError

# Настройка логгера модуля
logger = logger.bind(module="crud_channel")


class ChannelCRUD:
    """CRUD операции для каналов"""
    
    @staticmethod
    async def get_active_channels(limit: int = 500) -> List[Channel]:
        """
        Получить активные каналы для мониторинга
        
        Args:
            limit: Максимальное количество каналов
            
        Returns:
            Список активных каналов
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, channel_id, username, title, is_active,
                              last_message_id, posts_processed, posts_approved, posts_rejected,
                              created_at, updated_at, added_date
                       FROM channels 
                       WHERE is_active = 1
                       ORDER BY created_at DESC
                       LIMIT ?""",
                    (limit,)
                )
                rows = await cursor.fetchall()
                
                channels = []
                for row in rows:
                    channels.append(Channel(
                        id=row[0],
                        channel_id=row[1],
                        username=row[2],
                        title=row[3],
                        is_active=bool(row[4]),
                        last_message_id=row[5],
                        posts_processed=row[6],
                        posts_approved=row[7], 
                        posts_rejected=row[8],
                        created_at=row[9],
                        updated_at=row[10],
                        added_date=row[11]
                    ))
                
                logger.debug("Получено {} активных каналов", len(channels))
                return channels
                
        except Exception as e:
            logger.error("Ошибка получения активных каналов: {}", str(e))
            raise DatabaseError(f"Не удалось получить активные каналы: {str(e)}")

    @staticmethod
    async def create(channel: Channel) -> Channel:
        """
        Создать новый канал
        
        Args:
            channel: Объект канала для создания
            
        Returns:
            Созданный канал с установленным ID
        """
        if not channel.validate():
            raise ValueError("Данные канала не прошли валидацию")
        
        try:
            async with get_db_transaction() as conn:
                # Проверяем на дубликаты
                cursor = await conn.execute(
                    "SELECT id FROM channels WHERE channel_id = ?",
                    (channel.channel_id,)
                )
                existing = await cursor.fetchone()
                
                if existing:
                    raise DuplicateRecordError("channels", "channel_id", channel.channel_id)
                
                # Вставляем канал
                cursor = await conn.execute(
                    """INSERT INTO channels 
                       (channel_id, username, title, is_active, last_message_id,
                        posts_processed, posts_approved, posts_rejected,
                        created_at, updated_at, added_date)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        channel.channel_id,
                        channel.username,
                        channel.title,
                        channel.is_active,
                        channel.last_message_id,
                        channel.posts_processed,
                        channel.posts_approved,
                        channel.posts_rejected,
                        channel.created_at.isoformat(),
                        channel.updated_at.isoformat() if channel.updated_at else None,
                        channel.added_date.isoformat() if channel.added_date else channel.created_at.isoformat()
                    )
                )
                
                channel_id = cursor.lastrowid
                channel.id = channel_id
                
                channel.log_creation()
                logger.info("Создан канал: {}", channel.display_name)
                
                return channel
                
        except Exception as e:
            if isinstance(e, DuplicateRecordError):
                raise
            logger.error("Ошибка создания канала: {}", str(e))
            raise DatabaseError(f"Не удалось создать канал: {str(e)}")
    
    @staticmethod
    async def get_by_id(channel_id: int) -> Optional[Channel]:
        """
        Получить канал по ID записи
        
        Args:
            channel_id: ID записи в таблице
            
        Returns:
            Объект канала или None
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, channel_id, username, title, is_active, last_message_id,
                              posts_processed, posts_approved, posts_rejected,
                              created_at, updated_at, added_date
                       FROM channels WHERE id = ?""",
                    (channel_id,)
                )
                row = await cursor.fetchone()
                
                if not row:
                    return None
                
                return ChannelCRUD._row_to_channel(row)
                
        except Exception as e:
            logger.error("Ошибка получения канала по ID {}: {}", channel_id, str(e))
            raise DatabaseError(f"Не удалось получить канал: {str(e)}")
    
    @staticmethod
    async def get_by_channel_id(channel_id: int) -> Optional[Channel]:
        """
        Получить канал по Telegram ID
        
        Args:
            channel_id: ID канала в Telegram
            
        Returns:
            Объект канала или None
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, channel_id, username, title, is_active, last_message_id,
                              posts_processed, posts_approved, posts_rejected,
                              created_at, updated_at, added_date
                       FROM channels WHERE channel_id = ?""",
                    (channel_id,)
                )
                row = await cursor.fetchone()
                
                if not row:
                    return None
                
                return ChannelCRUD._row_to_channel(row)
                
        except Exception as e:
            logger.error("Ошибка получения канала по channel_id {}: {}", channel_id, str(e))
            raise DatabaseError(f"Не удалось получить канал: {str(e)}")
    
    @staticmethod
    async def get_all_active() -> List[Channel]:
        """
        Получить все активные каналы
        
        Returns:
            Список активных каналов
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, channel_id, username, title, is_active, last_message_id,
                              posts_processed, posts_approved, posts_rejected,
                              created_at, updated_at, added_date
                       FROM channels WHERE is_active = 1
                       ORDER BY created_at DESC"""
                )
                rows = await cursor.fetchall()
                
                return [ChannelCRUD._row_to_channel(row) for row in rows]
                
        except Exception as e:
            logger.error("Ошибка получения активных каналов: {}", str(e))
            raise DatabaseError(f"Не удалось получить каналы: {str(e)}")

    @staticmethod
    async def get_all_channels() -> List[Channel]:
        """
        Получить все каналы (активные и неактивные)
        
        Returns:
            Список всех каналов
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, channel_id, username, title, is_active, last_message_id,
                              posts_processed, posts_approved, posts_rejected,
                              created_at, updated_at, added_date
                       FROM channels 
                       ORDER BY created_at DESC"""
                )
                rows = await cursor.fetchall()
                
                return [ChannelCRUD._row_to_channel(row) for row in rows]
                
        except Exception as e:
            logger.error("Ошибка получения всех каналов: {}", str(e))
            raise DatabaseError(f"Не удалось получить каналы: {str(e)}")

    @staticmethod
    async def get_channel_by_id(channel_id: int) -> Optional[Channel]:
        """
        Получить канал по ID (алиас для get_by_id)
        
        Args:
            channel_id: ID записи в таблице
            
        Returns:
            Объект канала или None
        """
        return await ChannelCRUD.get_by_id(channel_id)

    @staticmethod
    async def delete_channel(channel_id: int) -> bool:
        """
        Удалить канал (алиас для delete)
        
        Args:
            channel_id: ID канала
            
        Returns:
            True если канал удален
        """
        return await ChannelCRUD.delete(channel_id)
    
    @staticmethod
    async def update(channel: Channel) -> Channel:
        """
        Обновить канал
        
        Args:
            channel: Объект канала для обновления
            
        Returns:
            Обновленный канал
        """
        if not channel.id:
            raise ValueError("ID канала не установлен")
        
        if not channel.validate():
            raise ValueError("Данные канала не прошли валидацию")
        
        try:
            channel.update_timestamp()
            
            async with get_db_transaction() as conn:
                cursor = await conn.execute(
                    """UPDATE channels SET
                       username = ?, title = ?, is_active = ?, last_message_id = ?,
                       posts_processed = ?, posts_approved = ?, posts_rejected = ?,
                       updated_at = ?
                       WHERE id = ?""",
                    (
                        channel.username,
                        channel.title,
                        channel.is_active,
                        channel.last_message_id,
                        channel.posts_processed,
                        channel.posts_approved,
                        channel.posts_rejected,
                        channel.updated_at.isoformat(),
                        channel.id
                    )
                )
                
                if cursor.rowcount == 0:
                    raise RecordNotFoundError("channels", channel.id)
                
                channel.log_update()
                logger.debug("Обновлен канал ID={}: {}", channel.id, channel.display_name)
                
                return channel
                
        except Exception as e:
            if isinstance(e, RecordNotFoundError):
                raise
            logger.error("Ошибка обновления канала ID={}: {}", channel.id, str(e))
            raise DatabaseError(f"Не удалось обновить канал: {str(e)}")
    
    @staticmethod
    async def delete(channel_id: int) -> bool:
        """
        Удалить канал (мягкое удаление - деактивация)
        
        Args:
            channel_id: ID канала
            
        Returns:
            True если канал удален
        """
        try:
            async with get_db_transaction() as conn:
                cursor = await conn.execute(
                    "UPDATE channels SET is_active = 0, updated_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), channel_id)
                )
                
                if cursor.rowcount == 0:
                    raise RecordNotFoundError("channels", channel_id)
                
                logger.info("Канал ID={} деактивирован", channel_id)
                return True
                
        except Exception as e:
            if isinstance(e, RecordNotFoundError):
                raise
            logger.error("Ошибка удаления канала ID={}: {}", channel_id, str(e))
            raise DatabaseError(f"Не удалось удалить канал: {str(e)}")
    
    @staticmethod
    async def get_statistics() -> dict:
        """
        Получить статистику по каналам
        
        Returns:
            Словарь со статистикой
        """
        try:
            async with get_db_connection() as conn:
                # Общая статистика
                cursor = await conn.execute(
                    """SELECT 
                       COUNT(*) as total_channels,
                       COUNT(CASE WHEN is_active THEN 1 END) as active_channels,
                       SUM(posts_processed) as total_posts_processed,
                       SUM(posts_approved) as total_posts_approved,
                       SUM(posts_rejected) as total_posts_rejected
                       FROM channels"""
                )
                stats = await cursor.fetchone()
                
                # Топ каналы по активности
                cursor = await conn.execute(
                    """SELECT channel_id, username, title, posts_processed
                       FROM channels 
                       WHERE is_active = 1
                       ORDER BY posts_processed DESC
                       LIMIT 5"""
                )
                top_channels = await cursor.fetchall()
                
                return {
                    "total_channels": stats[0],
                    "active_channels": stats[1],
                    "total_posts_processed": stats[2] or 0,
                    "total_posts_approved": stats[3] or 0,
                    "total_posts_rejected": stats[4] or 0,
                    "top_channels": [
                        {
                            "channel_id": row[0],
                            "username": row[1],
                            "title": row[2],
                            "posts_processed": row[3]
                        }
                        for row in top_channels
                    ]
                }
                
        except Exception as e:
            logger.error("Ошибка получения статистики каналов: {}", str(e))
            raise DatabaseError(f"Не удалось получить статистику: {str(e)}")
    
    @staticmethod
    async def deactivate_channel(channel_id: int) -> bool:
        """
        Деактивировать канал
        
        Args:
            channel_id: ID канала для деактивации
            
        Returns:
            True если канал деактивирован успешно
        """
        try:
            async with get_db_transaction() as conn:
                await conn.execute(
                    "UPDATE channels SET is_active = 0, updated_at = datetime('now') WHERE id = ?",
                    (channel_id,)
                )
                await conn.commit()
                logger.info("Канал ID={} деактивирован", channel_id)
                return True
                
        except Exception as e:
            logger.error("Ошибка деактивации канала ID={}: {}", channel_id, str(e))
            return False
    
    @staticmethod
    def _row_to_channel(row) -> Channel:
        """Преобразовать строку БД в объект Channel"""
        return Channel(
            id=row[0],
            channel_id=row[1],
            username=row[2],
            title=row[3],
            is_active=bool(row[4]),
            last_message_id=row[5],
            posts_processed=row[6],
            posts_approved=row[7],
            posts_rejected=row[8],
            created_at=datetime.fromisoformat(row[9]) if row[9] else datetime.now(),
            updated_at=datetime.fromisoformat(row[10]) if row[10] else None,
            added_date=datetime.fromisoformat(row[11]) if row[11] else datetime.now()
        )


# Глобальный экземпляр CRUD
def get_channel_crud() -> ChannelCRUD:
    """Получить экземпляр ChannelCRUD"""
    return ChannelCRUD()