"""
CRUD операции для модели Post
Создание, чтение, обновление и удаление постов
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.database.connection import get_db_connection, get_db_transaction
from src.database.models.post import Post, PostStatus, PostSentiment
from src.utils.exceptions import DatabaseError, RecordNotFoundError, DuplicateRecordError

# Настройка логгера модуля
logger = logger.bind(module="crud_post")


class PostCRUD:
    """CRUD операции для постов"""
    
    @staticmethod
    async def create(post: Post) -> Post:
        """
        Создать новый пост
        
        Args:
            post: Объект поста для создания
            
        Returns:
            Созданный пост с установленным ID
        """
        if not post.validate():
            raise ValueError("Данные поста не прошли валидацию")
        
        try:
            async with get_db_transaction() as conn:
                # Проверяем на дубликаты
                cursor = await conn.execute(
                    "SELECT id FROM posts WHERE channel_id = ? AND message_id = ?",
                    (post.channel_id, post.message_id)
                )
                existing = await cursor.fetchone()
                
                if existing:
                    raise DuplicateRecordError("posts", "channel_id+message_id", 
                                             f"{post.channel_id}+{post.message_id}")
                
                # Вставляем пост
                cursor = await conn.execute(
                    """INSERT INTO posts
                       (channel_id, message_id, original_text, processed_text,
                        photo_file_id, photo_path, relevance_score, sentiment, status,
                        source_link, posted_date, scheduled_date, moderation_notes,
                        ai_analysis, error_message, created_at, updated_at, created_date,
                        published_message_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        post.channel_id,
                        post.message_id,
                        post.original_text,
                        post.processed_text,
                        post.photo_file_id,
                        post.photo_path,
                        post.relevance_score,
                        post.sentiment.value if post.sentiment else None,
                        post.status.value,
                        post.source_link,
                        post.posted_date.isoformat() if post.posted_date else None,
                        post.scheduled_date.isoformat() if post.scheduled_date else None,
                        post.moderation_notes,
                        post.ai_analysis,
                        post.error_message,
                        post.created_at.isoformat(),
                        post.updated_at.isoformat() if post.updated_at else None,
                        post.created_date.isoformat() if post.created_date else post.created_at.isoformat(),
                        post.published_message_id
                    )
                )
                
                post_id = cursor.lastrowid
                post.id = post_id
                
                post.log_creation()
                logger.info("Создан пост: {}", post.unique_id)
                
                return post
                
        except Exception as e:
            if isinstance(e, DuplicateRecordError):
                raise
            logger.error("Ошибка создания поста: {}", str(e))
            raise DatabaseError(f"Не удалось создать пост: {str(e)}")
    
    @staticmethod
    async def get_by_id(post_id: int) -> Optional[Post]:
        """
        Получить пост по ID
        
        Args:
            post_id: ID поста
            
        Returns:
            Объект поста или None
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, channel_id, message_id, original_text, processed_text,
                              photo_file_id, relevance_score, sentiment, status,
                              source_link, posted_date, scheduled_date, moderation_notes,
                              ai_analysis, error_message, pin_post, created_at, updated_at,
                              created_date, photo_path, video_file_id, video_path, media_type,
                              video_duration, video_width, video_height, extracted_links, media_items,
                              retry_count, published_message_id
                       FROM posts WHERE id = ?""",
                    (post_id,)
                )
                row = await cursor.fetchone()
                
                if not row:
                    return None
                
                return PostCRUD._row_to_post(row)
                
        except Exception as e:
            logger.error("Ошибка получения поста по ID {}: {}", post_id, str(e))
            raise DatabaseError(f"Не удалось получить пост: {str(e)}")
    
    @staticmethod
    async def get_by_channel_message(channel_id: int, message_id: int) -> Optional[Post]:
        """
        Получить пост по channel_id и message_id
        
        Args:
            channel_id: ID канала
            message_id: ID сообщения
            
        Returns:
            Объект поста или None
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, channel_id, message_id, original_text, processed_text,
                              photo_file_id, relevance_score, sentiment, status,
                              source_link, posted_date, scheduled_date, moderation_notes,
                              ai_analysis, error_message, pin_post, created_at, updated_at,
                              created_date, photo_path, video_file_id, video_path, media_type,
                              video_duration, video_width, video_height, extracted_links, media_items,
                              retry_count, published_message_id
                       FROM posts WHERE channel_id = ? AND message_id = ?""",
                    (channel_id, message_id)
                )
                row = await cursor.fetchone()
                
                if not row:
                    return None
                
                return PostCRUD._row_to_post(row)
                
        except Exception as e:
            logger.error("Ошибка получения поста {}/{}: {}", channel_id, message_id, str(e))
            raise DatabaseError(f"Не удалось получить пост: {str(e)}")
    
    @staticmethod
    async def get_by_status(status: PostStatus, limit: int = 500) -> List[Post]:
        """
        Получить посты по статусу
        
        Args:
            status: Статус постов
            limit: Максимальное количество постов
            
        Returns:
            Список постов
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, channel_id, message_id, original_text, processed_text,
                              photo_file_id, relevance_score, sentiment, status,
                              source_link, posted_date, scheduled_date, moderation_notes,
                              ai_analysis, error_message, pin_post, created_at, updated_at,
                              created_date, photo_path, video_file_id, video_path, media_type,
                              video_duration, video_width, video_height, extracted_links, media_items,
                              retry_count, published_message_id
                       FROM posts WHERE status = ?
                       ORDER BY created_at DESC
                       LIMIT ?""",
                    (status.value, limit)
                )
                rows = await cursor.fetchall()
                
                return [PostCRUD._row_to_post(row) for row in rows]
                
        except Exception as e:
            logger.error("Ошибка получения постов по статусу {}: {}", status.value, str(e))
            raise DatabaseError(f"Не удалось получить посты: {str(e)}")
    
    @staticmethod
    async def get_pending_posts(limit: int = 20) -> List[Post]:
        """
        Получить посты, ожидающие модерации
        
        Args:
            limit: Максимальное количество постов
            
        Returns:
            Список постов для модерации
        """
        return await PostCRUD.get_by_status(PostStatus.PENDING, limit)
    
    @staticmethod
    async def get_scheduled_posts() -> List[Post]:
        """
        Получить запланированные посты, готовые к публикации
        
        Returns:
            Список постов готовых к публикации
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, channel_id, message_id, original_text, processed_text,
                              photo_file_id, relevance_score, sentiment, status,
                              source_link, posted_date, scheduled_date, moderation_notes,
                              ai_analysis, error_message, pin_post, created_at, updated_at,
                              created_date, photo_path, video_file_id, video_path, media_type,
                              video_duration, video_width, video_height, extracted_links, media_items,
                              retry_count, published_message_id
                       FROM posts
                       WHERE status = ? AND scheduled_date <= datetime('now')
                       ORDER BY scheduled_date ASC""",
                    (PostStatus.SCHEDULED.value,)
                )
                rows = await cursor.fetchall()
                
                return [PostCRUD._row_to_post(row) for row in rows]
                
        except Exception as e:
            logger.error("Ошибка получения запланированных постов: {}", str(e))
            raise DatabaseError(f"Не удалось получить запланированные посты: {str(e)}")
    
    @staticmethod
    async def update(post: Post) -> Post:
        """
        Обновить пост
        
        Args:
            post: Объект поста для обновления
            
        Returns:
            Обновленный пост
        """
        if not post.id:
            raise ValueError("ID поста не установлен")
        
        if not post.validate():
            raise ValueError("Данные поста не прошли валидацию")
        
        try:
            post.update_timestamp()
            
            async with get_db_transaction() as conn:
                cursor = await conn.execute(
                    """UPDATE posts SET
                       original_text = ?, processed_text = ?, photo_file_id = ?,
                       relevance_score = ?, sentiment = ?, status = ?,
                       posted_date = ?, scheduled_date = ?, moderation_notes = ?,
                       ai_analysis = ?, error_message = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        post.original_text,
                        post.processed_text,
                        post.photo_file_id,
                        post.relevance_score,
                        post.sentiment.value if post.sentiment else None,
                        post.status.value,
                        post.posted_date.isoformat() if post.posted_date else None,
                        post.scheduled_date.isoformat() if post.scheduled_date else None,
                        post.moderation_notes,
                        post.ai_analysis,
                        post.error_message,
                        post.updated_at.isoformat(),
                        post.id
                    )
                )
                
                if cursor.rowcount == 0:
                    raise RecordNotFoundError("posts", post.id)
                
                post.log_update()
                logger.debug("Обновлен пост ID={}: {}", post.id, post.unique_id)
                
                return post
                
        except Exception as e:
            if isinstance(e, RecordNotFoundError):
                raise
            logger.error("Ошибка обновления поста ID={}: {}", post.id, str(e))
            raise DatabaseError(f"Не удалось обновить пост: {str(e)}")
    
    @staticmethod
    async def delete(post_id: int) -> bool:
        """
        Удалить пост
        
        Args:
            post_id: ID поста
            
        Returns:
            True если пост удален
        """
        try:
            async with get_db_transaction() as conn:
                cursor = await conn.execute(
                    "DELETE FROM posts WHERE id = ?",
                    (post_id,)
                )
                
                if cursor.rowcount == 0:
                    raise RecordNotFoundError("posts", post_id)
                
                logger.info("Пост ID={} удален", post_id)
                return True
                
        except Exception as e:
            if isinstance(e, RecordNotFoundError):
                raise
            logger.error("Ошибка удаления поста ID={}: {}", post_id, str(e))
            raise DatabaseError(f"Не удалось удалить пост: {str(e)}")
    
    @staticmethod
    async def get_statistics() -> Dict[str, Any]:
        """
        Получить статистику по постам
        
        Returns:
            Словарь со статистикой
        """
        try:
            async with get_db_connection() as conn:
                # Общая статистика по статусам
                cursor = await conn.execute(
                    """SELECT status, COUNT(*) as count
                       FROM posts 
                       GROUP BY status"""
                )
                status_stats = {row[0]: row[1] for row in await cursor.fetchall()}
                
                # Статистика по релевантности
                cursor = await conn.execute(
                    """SELECT 
                       AVG(relevance_score) as avg_relevance,
                       COUNT(CASE WHEN relevance_score >= 6 THEN 1 END) as high_relevance_count,
                       COUNT(CASE WHEN relevance_score IS NOT NULL THEN 1 END) as analyzed_count
                       FROM posts"""
                )
                relevance_stats = await cursor.fetchone()
                
                # Статистика по каналам
                cursor = await conn.execute(
                    """SELECT channel_id, COUNT(*) as post_count
                       FROM posts
                       GROUP BY channel_id
                       ORDER BY post_count DESC
                       LIMIT 5"""
                )
                channel_stats = await cursor.fetchall()
                
                return {
                    "status_distribution": status_stats,
                    "total_posts": sum(status_stats.values()),
                    "average_relevance": round(relevance_stats[0], 2) if relevance_stats[0] else 0,
                    "high_relevance_posts": relevance_stats[1] or 0,
                    "analyzed_posts": relevance_stats[2] or 0,
                    "top_channels_by_posts": [
                        {"channel_id": row[0], "post_count": row[1]}
                        for row in channel_stats
                    ]
                }
                
        except Exception as e:
            logger.error("Ошибка получения статистики постов: {}", str(e))
            raise DatabaseError(f"Не удалось получить статистику: {str(e)}")
    
    @staticmethod
    async def get_posts_by_date_and_type(date, post_type: str) -> List[Post]:
        """
        Получить посты по дате и типу
        
        Args:
            date: Дата для поиска
            post_type: Тип поста (например 'daily_post')
            
        Returns:
            Список постов
        """
        try:
            async with get_db_connection() as conn:
                # Ищем посты по типу в поле ai_analysis за указанную дату
                cursor = await conn.execute(
                    """SELECT * FROM posts 
                       WHERE DATE(created_at) = DATE(?) 
                       AND ai_analysis LIKE ?
                       ORDER BY created_at DESC""",
                    (date, f"%{post_type}%")
                )
                rows = await cursor.fetchall()
                
                return [PostCRUD._row_to_post(row) for row in rows]
                
        except Exception as e:
            logger.error("Ошибка получения постов по дате и типу: {}", str(e))
            raise DatabaseError(f"Не удалось получить посты: {str(e)}")

    @staticmethod
    async def get_posts_by_week_and_type(year: int, week: int, post_type: str) -> List[Post]:
        """
        Получить посты по номеру недели и типу

        Args:
            year: Год
            week: Номер недели (1-53)
            post_type: Тип поста (например 'weekly_analytics')

        Returns:
            Список постов
        """
        try:
            async with get_db_connection() as conn:
                # Ищем посты по типу в поле ai_analysis за указанную неделю
                cursor = await conn.execute(
                    """SELECT * FROM posts
                       WHERE strftime('%Y', created_at) = ?
                       AND strftime('%W', created_at) = ?
                       AND ai_analysis LIKE ?
                       ORDER BY created_at DESC""",
                    (str(year), str(week).zfill(2), f"%{post_type}%")
                )
                rows = await cursor.fetchall()

                return [PostCRUD._row_to_post(row) for row in rows]

        except Exception as e:
            logger.error("Ошибка получения постов по неделе и типу: {}", str(e))
            raise DatabaseError(f"Не удалось получить посты: {str(e)}")

    @staticmethod
    async def add_post_tag(post_id: int, tag: str) -> bool:
        """
        Добавить тег к посту
        
        Args:
            post_id: ID поста
            tag: Тег для добавления
            
        Returns:
            True если тег добавлен успешно
        """
        try:
            async with get_db_transaction() as conn:
                # Создаем таблицу для тегов если не существует
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS post_tags (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        post_id INTEGER NOT NULL,
                        tag TEXT NOT NULL,
                        created_at TEXT DEFAULT (datetime('now')),
                        FOREIGN KEY (post_id) REFERENCES posts (id),
                        UNIQUE(post_id, tag)
                    )
                """)
                
                # Добавляем тег
                await conn.execute(
                    "INSERT OR IGNORE INTO post_tags (post_id, tag) VALUES (?, ?)",
                    (post_id, tag)
                )
                
                await conn.commit()
                logger.debug("Добавлен тег '{}' к посту {}", tag, post_id)
                return True
                
        except Exception as e:
            logger.error("Ошибка добавления тега к посту: {}", str(e))
            return False
    
    @staticmethod
    async def get_posts_before_date_by_status(cutoff_date: datetime, status: PostStatus) -> List[Post]:
        """Получить посты до определенной даты с определенным статусом"""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT * FROM posts 
                       WHERE created_at < ? AND status = ?
                       ORDER BY created_at ASC""",
                    (cutoff_date.isoformat(), status.value)
                )
                rows = await cursor.fetchall()
                return [PostCRUD._row_to_post(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка получения старых постов по статусу: {}", str(e))
            return []
    
    @staticmethod
    async def mark_post_as_archived(post_id: int) -> bool:
        """Пометить пост как архивированный"""
        try:
            async with get_db_transaction() as conn:
                await conn.execute(
                    "UPDATE posts SET ai_analysis = ai_analysis || '\nARCHIVED: true' WHERE id = ?",
                    (post_id,)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error("Ошибка архивирования поста: {}", str(e))
            return False
    
    @staticmethod
    async def delete_post_permanently(post_id: int) -> bool:
        """Окончательно удалить пост"""
        try:
            async with get_db_transaction() as conn:
                # Удаляем связанные теги
                await conn.execute("DELETE FROM post_tags WHERE post_id = ?", (post_id,))
                # Удаляем сам пост
                await conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
                await conn.commit()
                return True
        except Exception as e:
            logger.error("Ошибка удаления поста: {}", str(e))
            return False
    
    @staticmethod
    async def get_posts_with_errors() -> List[Post]:
        """Получить посты с ошибками"""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT * FROM posts 
                       WHERE error_message IS NOT NULL AND error_message != ''
                       ORDER BY created_at DESC""")
                rows = await cursor.fetchall()
                return [PostCRUD._row_to_post(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка получения постов с ошибками: {}", str(e))
            return []
    
    @staticmethod
    async def clear_post_error(post_id: int) -> bool:
        """Очистить ошибку поста"""
        try:
            async with get_db_transaction() as conn:
                await conn.execute(
                    "UPDATE posts SET error_message = NULL WHERE id = ?",
                    (post_id,)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error("Ошибка очистки ошибки поста: {}", str(e))
            return False
    
    @staticmethod
    async def add_post_error(post_id: int, error_message: str) -> bool:
        """Добавить ошибку к посту"""
        try:
            async with get_db_transaction() as conn:
                await conn.execute(
                    "UPDATE posts SET error_message = ? WHERE id = ?",
                    (error_message, post_id)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error("Ошибка добавления ошибки к посту: {}", str(e))
            return False
    
    @staticmethod
    async def get_posts_by_channel_since(channel_id: int, since_date: datetime) -> List[Post]:
        """Получить посты канала после определенной даты"""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT * FROM posts 
                       WHERE channel_id = ? AND created_at >= ?
                       ORDER BY created_at DESC""",
                    (channel_id, since_date.isoformat())
                )
                rows = await cursor.fetchall()
                return [PostCRUD._row_to_post(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка получения постов канала по дате: {}", str(e))
            return []
    
    @staticmethod
    async def get_posts_by_status(status: PostStatus, limit: int = 500) -> List[Post]:
        """
        Алиас для get_by_status для обратной совместимости
        
        Args:
            status: Статус постов
            limit: Максимальное количество постов
            
        Returns:
            Список постов
        """
        return await PostCRUD.get_by_status(status, limit)
    
    @staticmethod
    async def get_all_posts(limit: Optional[int] = None) -> List[Post]:
        """
        Получить все посты
        
        Args:
            limit: Максимальное количество постов
            
        Returns:
            Список всех постов
        """
        try:
            async with get_db_connection() as conn:
                if limit:
                    cursor = await conn.execute(
                        "SELECT * FROM posts ORDER BY created_at DESC LIMIT ?",
                        (limit,)
                    )
                else:
                    cursor = await conn.execute(
                        "SELECT * FROM posts ORDER BY created_at DESC"
                    )
                rows = await cursor.fetchall()
                return [PostCRUD._row_to_post(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка получения всех постов: {}", str(e))
            return []
    
    @staticmethod
    async def get_posts_before_date(cutoff_date: datetime) -> List[Post]:
        """
        Получить посты до определенной даты
        
        Args:
            cutoff_date: Граничная дата
            
        Returns:
            Список постов до указанной даты
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM posts WHERE created_at < ? ORDER BY created_at DESC",
                    (cutoff_date.isoformat(),)
                )
                rows = await cursor.fetchall()
                return [PostCRUD._row_to_post(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка получения постов по дате: {}", str(e))
            return []
    
    @staticmethod
    async def get_posts_since(since_date: datetime) -> List[Post]:
        """
        Получить посты после определенной даты
        
        Args:
            since_date: Дата с которой искать
            
        Returns:
            Список постов после указанной даты
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM posts WHERE created_at >= ? ORDER BY created_at DESC",
                    (since_date.isoformat(),)
                )
                rows = await cursor.fetchall()
                return [PostCRUD._row_to_post(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка получения постов с даты: {}", str(e))
            return []
    
    @staticmethod
    async def get_posts_without_ai_analysis(limit: int = 500) -> List[Post]:
        """
        Получить посты без AI анализа
        
        Args:
            limit: Максимальное количество постов
            
        Returns:
            Список постов без AI анализа
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT * FROM posts 
                       WHERE (ai_analysis IS NULL OR ai_analysis = '' OR relevance_score IS NULL)
                       AND status IN (?, ?)
                       ORDER BY created_at DESC
                       LIMIT ?""",
                    (PostStatus.PENDING.value, PostStatus.APPROVED.value, limit)
                )
                rows = await cursor.fetchall()
                return [PostCRUD._row_to_post(row) for row in rows]
        except Exception as e:
            logger.error("Ошибка получения постов без AI анализа: {}", str(e))
            return []
    
    @staticmethod
    async def update_post_status(post_id: int, status: PostStatus) -> bool:
        """
        Обновить статус поста
        
        Args:
            post_id: ID поста
            status: Новый статус
            
        Returns:
            True если статус обновлен успешно
        """
        try:
            async with get_db_transaction() as conn:
                cursor = await conn.execute(
                    "UPDATE posts SET status = ?, updated_at = ? WHERE id = ?",
                    (status.value, datetime.now().isoformat(), post_id)
                )
                
                if cursor.rowcount == 0:
                    logger.warning("Пост с ID {} не найден для обновления статуса", post_id)
                    return False
                
                logger.debug("Статус поста {} обновлен на {}", post_id, status.value)
                return True
                
        except Exception as e:
            logger.error("Ошибка обновления статуса поста {}: {}", post_id, str(e))
            return False
    
    @staticmethod
    async def update_post(post_id: int, **updates) -> bool:
        """
        Обновить поля поста
        
        Args:
            post_id: ID поста
            **updates: Поля для обновления
            
        Returns:
            True если обновление успешно
        """
        try:
            if not updates:
                return True
                
            # Добавляем updated_at
            updates['updated_at'] = datetime.now().isoformat()
            
            # Формируем SQL запрос
            set_clause = ", ".join(f"{key} = ?" for key in updates.keys())
            values = list(updates.values()) + [post_id]
            
            async with get_db_transaction() as conn:
                cursor = await conn.execute(
                    f"UPDATE posts SET {set_clause} WHERE id = ?",
                    values
                )
                
                if cursor.rowcount == 0:
                    logger.warning("Пост с ID {} не найден для обновления", post_id)
                    return False
                
                logger.debug("Пост {} обновлен: {}", post_id, list(updates.keys()))
                return True
                
        except Exception as e:
            logger.error("Ошибка обновления поста {}: {}", post_id, str(e))
            return False
    
    @staticmethod
    async def get_post_by_id(post_id: int) -> Optional[Post]:
        """
        Алиас для get_by_id для обратной совместимости
        
        Args:
            post_id: ID поста
            
        Returns:
            Объект поста или None
        """
        return await PostCRUD.get_by_id(post_id)
    
    @staticmethod
    def _row_to_post(row) -> Post:
        """Преобразовать строку БД в объект Post"""
        # Индексы колонок таблицы posts (порядок создания + ALTER TABLE):
        # 0:id, 1:channel_id, 2:message_id, 3:original_text, 4:processed_text,
        # 5:photo_file_id, 6:relevance_score, 7:sentiment, 8:status, 9:source_link,
        # 10:posted_date, 11:scheduled_date, 12:moderation_notes, 13:ai_analysis,
        # 14:error_message, 15:pin_post, 16:created_at, 17:updated_at, 18:created_date,
        # 19:photo_path (v3), 20:video_file_id (v4), 21:video_path (v4), 22:media_type (v4),
        # 23:video_duration (v4), 24:video_width (v4), 25:video_height (v4),
        # 26:extracted_links (v6), 27:media_items (v7), 28:retry_count (v8),
        # 29:published_message_id (v9)

        return Post(
            id=row[0],
            channel_id=row[1],
            message_id=row[2],
            original_text=row[3],
            processed_text=row[4],
            photo_file_id=row[5],
            photo_path=row[19] if len(row) > 19 else None,
            video_file_id=row[20] if len(row) > 20 else None,
            video_path=row[21] if len(row) > 21 else None,
            media_type=row[22] if len(row) > 22 else None,
            video_duration=row[23] if len(row) > 23 else None,
            video_width=row[24] if len(row) > 24 else None,
            video_height=row[25] if len(row) > 25 else None,
            relevance_score=row[6],
            sentiment=PostSentiment(row[7]) if row[7] else None,
            status=PostStatus(row[8]),
            source_link=row[9],
            posted_date=datetime.fromisoformat(row[10]) if row[10] else None,
            scheduled_date=datetime.fromisoformat(row[11]) if row[11] else None,
            moderation_notes=row[12],
            ai_analysis=row[13],
            error_message=row[14],
            pin_post=row[15] if len(row) > 15 else False,
            created_at=datetime.fromisoformat(row[16]) if row[16] else datetime.now(),
            updated_at=datetime.fromisoformat(row[17]) if row[17] else None,
            created_date=datetime.fromisoformat(row[18]) if row[18] else datetime.now(),
            extracted_links=row[26] if len(row) > 26 else None,
            media_items=row[27] if len(row) > 27 else None,
            retry_count=row[28] if len(row) > 28 else 0,
            published_message_id=row[29] if len(row) > 29 else None
        )

    @staticmethod
    async def get_published_posts_by_date(
        date: datetime,
        exclude_types: Optional[List[str]] = None
    ) -> List[Post]:
        """
        Получить опубликованные посты за день с фильтрацией по типам

        Args:
            date: Дата для фильтрации (берется только дата, время игнорируется)
            exclude_types: Список типов постов для исключения (маркеры из ai_analysis)
                          Например: ["daily_post", "weekly_analytics", "summary_post"]

        Returns:
            Список опубликованных постов за день с published_message_id
        """
        try:
            async with get_db_connection() as conn:
                # Формируем базовый запрос
                query = """SELECT id, channel_id, message_id, original_text, processed_text,
                                  photo_file_id, relevance_score, sentiment, status,
                                  source_link, posted_date, scheduled_date, moderation_notes,
                                  ai_analysis, error_message, pin_post, created_at, updated_at,
                                  created_date, photo_path, video_file_id, video_path, media_type,
                                  video_duration, video_width, video_height, extracted_links, media_items,
                                  retry_count, published_message_id
                           FROM posts
                           WHERE DATE(posted_date) = DATE(?)
                           AND status = ?
                           AND published_message_id IS NOT NULL"""

                params = [date.isoformat(), PostStatus.POSTED.value]

                # Добавляем фильтрацию по типам если указаны
                if exclude_types:
                    # Добавляем условия для исключения каждого типа
                    for exclude_type in exclude_types:
                        query += " AND (ai_analysis NOT LIKE ? OR ai_analysis IS NULL)"
                        params.append(f"%{exclude_type}%")

                query += " ORDER BY posted_date DESC"

                cursor = await conn.execute(query, tuple(params))
                rows = await cursor.fetchall()

                posts = [PostCRUD._row_to_post(row) for row in rows]

                logger.debug(
                    "Найдено {} опубликованных постов за {} (исключены типы: {})",
                    len(posts), date.date(), exclude_types or "нет"
                )

                return posts

        except Exception as e:
            logger.error(
                "Ошибка получения опубликованных постов за {}: {}",
                date.date(), str(e)
            )
            raise DatabaseError(f"Не удалось получить опубликованные посты: {str(e)}")


# Глобальный экземпляр CRUD
def get_post_crud() -> PostCRUD:
    """Получить экземпляр PostCRUD"""
    return PostCRUD()