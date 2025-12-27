"""
CRUD операции для пользовательских примеров постов
Управление примерами стиля пользователя для AI анализа
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from ..connection import get_db_connection, get_db_transaction
from ..models.user_post import UserPost, UserPostStatus
from src.utils.exceptions import DatabaseError

# Настройка логгера модуля
logger = logger.bind(module="user_post_crud")


def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """
    Безопасно конвертировать строку даты/времени в datetime объект
    
    Args:
        dt_str: Строка даты/времени из SQLite
        
    Returns:
        datetime объект или None если конвертация невозможна
    """
    if not dt_str:
        return None
    
    if isinstance(dt_str, datetime):
        return dt_str
    
    if not isinstance(dt_str, str):
        return None
    
    try:
        # Пытаемся парсить как ISO формат
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except:
        try:
            # Пытаемся парсить как SQLite datetime формат
            return datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        except:
            try:
                # Пытаемся парсить без времени
                return datetime.strptime(dt_str, '%Y-%m-%d')
            except:
                logger.warning("Не удалось парсить дату: {}", dt_str)
                return None


class UserPostCRUD:
    """CRUD операции для пользовательских постов"""
    
    def __init__(self):
        """Инициализация CRUD"""
        logger.debug("Инициализирован UserPost CRUD")
    
    async def create_user_post(
        self,
        text: str,
        category: Optional[str] = None,
        style_tags: Optional[List[str]] = None,
        quality_score: Optional[int] = None,
        source_link: Optional[str] = None
    ) -> Optional[UserPost]:
        """
        Создать новый пользовательский пост
        
        Args:
            text: Текст поста
            category: Категория (crypto, macro, web3, telegram, gamefi)
            style_tags: Теги стиля
            quality_score: Оценка качества (1-10)
            source_link: Ссылка на источник
            
        Returns:
            Созданный UserPost или None при ошибке
        """
        try:
            # Подготавливаем данные
            style_tags_json = json.dumps(style_tags) if style_tags else None
            
            async with get_db_transaction() as conn:
                cursor = await conn.execute(
                    """INSERT INTO user_posts 
                       (text, category, style_tags, quality_score, source_link, is_active) 
                       VALUES (?, ?, ?, ?, ?, TRUE)""",
                    (text, category, style_tags_json, quality_score, source_link)
                )
                
                post_id = cursor.lastrowid
                
                # Получаем созданный пост
                user_post = await self._get_user_post_by_id(conn, post_id)
                
                if user_post:
                    logger.info("Создан пользовательский пост ID: {}, категория: {}", 
                              post_id, category or 'общая')
                
                return user_post
                
        except Exception as e:
            logger.error("Ошибка создания пользовательского поста: {}", str(e))
            raise DatabaseError(f"Не удалось создать пользовательский пост: {str(e)}")
    
    async def get_user_post_by_id(self, post_id: int) -> Optional[UserPost]:
        """Получить пользовательский пост по ID"""
        try:
            async with get_db_connection() as conn:
                return await self._get_user_post_by_id(conn, post_id)
        except Exception as e:
            logger.error("Ошибка получения пользовательского поста {}: {}", post_id, str(e))
            return None
    
    async def _get_user_post_by_id(self, conn, post_id: int) -> Optional[UserPost]:
        """Внутренний метод получения поста по ID"""
        cursor = await conn.execute(
            """SELECT id, text, is_active, category, style_tags, usage_count, 
                      quality_score, source_link, created_at, updated_at, added_date
               FROM user_posts WHERE id = ?""",
            (post_id,)
        )
        
        row = await cursor.fetchone()
        if not row:
            return None
        
        return UserPost(
            id=row[0],
            text=row[1],
            is_active=bool(row[2]),
            category=row[3],
            style_tags=json.loads(row[4]) if row[4] else None,
            usage_count=row[5],
            quality_score=row[6],
            source_link=row[7],
            created_at=parse_datetime(row[8]),
            updated_at=parse_datetime(row[9]),
            added_date=parse_datetime(row[10])
        )
    
    async def get_active_user_posts(
        self,
        category: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[UserPost]:
        """
        Получить активные пользовательские посты
        
        Args:
            category: Фильтр по категории
            limit: Максимальное количество
            
        Returns:
            Список активных постов
        """
        try:
            query = """SELECT id, text, is_active, category, style_tags, usage_count, 
                              quality_score, source_link, created_at, updated_at, added_date
                       FROM user_posts 
                       WHERE is_active = 1"""
            params = []
            
            if category:
                query += " AND category = ?"
                params.append(category)
            
            query += " ORDER BY quality_score DESC, usage_count ASC, created_at DESC"
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            async with get_db_connection() as conn:
                cursor = await conn.execute(query, params)
                rows = await cursor.fetchall()
            
            user_posts = []
            for row in rows:
                user_posts.append(UserPost(
                    id=row[0],
                    text=row[1],
                    is_active=bool(row[2]),
                    category=row[3],
                    style_tags=json.loads(row[4]) if row[4] else None,
                    usage_count=row[5],
                    quality_score=row[6],
                    source_link=row[7],
                    created_at=parse_datetime(row[8]),
                    updated_at=parse_datetime(row[9]),
                    added_date=parse_datetime(row[10])
                ))
            
            logger.debug("Получено {} активных пользовательских постов", len(user_posts))
            return user_posts
            
        except Exception as e:
            logger.error("Ошибка получения активных пользовательских постов: {}", str(e))
            return []
    
    async def update_user_post(
        self,
        post_id: int,
        text: Optional[str] = None,
        category: Optional[str] = None,
        style_tags: Optional[List[str]] = None,
        quality_score: Optional[int] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """
        Обновить пользовательский пост
        
        Args:
            post_id: ID поста
            text: Новый текст (опционально)
            category: Новая категория (опционально)
            style_tags: Новые теги (опционально)  
            quality_score: Новая оценка качества (опционально)
            is_active: Новый статус активности (опционально)
            
        Returns:
            True если обновление успешно
        """
        try:
            # Подготавливаем данные для обновления
            update_fields = []
            params = []
            
            if text is not None:
                update_fields.append("text = ?")
                params.append(text)
            
            if category is not None:
                update_fields.append("category = ?")
                params.append(category)
            
            if style_tags is not None:
                update_fields.append("style_tags = ?")
                params.append(json.dumps(style_tags))
            
            if quality_score is not None:
                update_fields.append("quality_score = ?")
                params.append(quality_score)
            
            if is_active is not None:
                update_fields.append("is_active = ?")
                params.append(is_active)
            
            if not update_fields:
                logger.warning("Нет полей для обновления поста {}", post_id)
                return False
            
            update_fields.append("updated_at = datetime('now')")
            params.append(post_id)
            
            query = f"UPDATE user_posts SET {', '.join(update_fields)} WHERE id = ?"
            
            async with get_db_connection() as conn:
                cursor = await conn.execute(query, params)
                await conn.commit()
                
                updated = cursor.rowcount > 0
                
                if updated:
                    logger.info("Обновлен пользовательский пост {}", post_id)
                else:
                    logger.warning("Пользовательский пост {} не найден для обновления", post_id)
                
                return updated
                
        except Exception as e:
            logger.error("Ошибка обновления пользовательского поста {}: {}", post_id, str(e))
            return False
    
    async def delete_user_post(self, post_id: int) -> bool:
        """
        Удалить пользовательский пост (мягкое удаление)
        
        Args:
            post_id: ID поста
            
        Returns:
            True если удаление успешно
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "UPDATE user_posts SET is_active = 0, updated_at = datetime('now') WHERE id = ?",
                    (post_id,)
                )
                await conn.commit()
                
                deleted = cursor.rowcount > 0
                
                if deleted:
                    logger.info("Пользовательский пост {} помечен как неактивный", post_id)
                else:
                    logger.warning("Пользовательский пост {} не найден для удаления", post_id)
                
                return deleted
                
        except Exception as e:
            logger.error("Ошибка удаления пользовательского поста {}: {}", post_id, str(e))
            return False
    
    async def increment_usage_count(self, post_id: int) -> bool:
        """
        Увеличить счетчик использования поста
        
        Args:
            post_id: ID поста
            
        Returns:
            True если обновление успешно
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """UPDATE user_posts 
                       SET usage_count = usage_count + 1, updated_at = datetime('now') 
                       WHERE id = ?""",
                    (post_id,)
                )
                await conn.commit()
                
                updated = cursor.rowcount > 0
                
                if updated:
                    logger.debug("Увеличен счетчик использования поста {}", post_id)
                
                return updated
                
        except Exception as e:
            logger.error("Ошибка увеличения счетчика использования поста {}: {}", post_id, str(e))
            return False
    
    async def get_posts_by_category(self, category: str) -> List[UserPost]:
        """Получить посты по категории"""
        return await self.get_active_user_posts(category=category)
    
    async def get_best_examples(self, limit: int = 10) -> List[UserPost]:
        """Получить лучшие примеры постов (по quality_score)"""
        return await self.get_active_user_posts(limit=limit)
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику пользовательских постов"""
        try:
            async with get_db_connection() as conn:
                # Общая статистика
                cursor = await conn.execute(
                    "SELECT COUNT(*), COUNT(CASE WHEN is_active THEN 1 END) FROM user_posts"
                )
                total_posts, active_posts = await cursor.fetchone()
                
                # Статистика по категориям
                cursor = await conn.execute(
                    """SELECT category, COUNT(*) as count 
                       FROM user_posts 
                       WHERE is_active = 1 AND category IS NOT NULL
                       GROUP BY category 
                       ORDER BY count DESC"""
                )
                categories = dict(await cursor.fetchall())
                
                # Средняя оценка качества
                cursor = await conn.execute(
                    "SELECT AVG(quality_score) FROM user_posts WHERE is_active = 1 AND quality_score IS NOT NULL"
                )
                avg_quality = await cursor.fetchone()
                avg_quality = avg_quality[0] if avg_quality[0] else 0
                
                return {
                    "total_posts": total_posts,
                    "active_posts": active_posts,
                    "inactive_posts": total_posts - active_posts,
                    "categories": categories,
                    "average_quality_score": round(avg_quality, 2)
                }
                
        except Exception as e:
            logger.error("Ошибка получения статистики пользовательских постов: {}", str(e))
            return {}


# Глобальный экземпляр CRUD
_user_post_crud: Optional[UserPostCRUD] = None


def get_user_post_crud() -> UserPostCRUD:
    """Получить глобальный экземпляр UserPost CRUD"""
    global _user_post_crud
    
    if _user_post_crud is None:
        _user_post_crud = UserPostCRUD()
    
    return _user_post_crud