"""
CRUD операции для модели CustomEmoji
Создание, чтение, обновление и удаление Custom Emoji
"""

from typing import Optional, List, Dict
from datetime import datetime

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.database.connection import get_db_connection, get_db_transaction
from src.database.models.emoji import CustomEmoji
from src.utils.exceptions import DatabaseError, RecordNotFoundError, DuplicateRecordError

# Настройка логгера модуля
logger = logger.bind(module="crud_emoji")


class EmojiCRUD:
    """CRUD операции для Custom Emoji"""

    @staticmethod
    async def create(emoji: CustomEmoji) -> CustomEmoji:
        """
        Создать новый Custom Emoji

        Args:
            emoji: Объект CustomEmoji для создания

        Returns:
            Созданный эмодзи с установленным ID
        """
        if not emoji.validate():
            raise ValueError("Данные эмодзи не прошли валидацию")

        try:
            async with get_db_transaction() as conn:
                # Проверяем на дубликаты
                cursor = await conn.execute(
                    "SELECT id FROM custom_emojis WHERE standard_emoji = ?",
                    (emoji.standard_emoji,)
                )
                existing = await cursor.fetchone()

                if existing:
                    raise DuplicateRecordError(
                        "custom_emojis", "standard_emoji", emoji.standard_emoji
                    )

                # Вставляем эмодзи
                cursor = await conn.execute(
                    """INSERT INTO custom_emojis
                       (standard_emoji, document_id, alt_text, category,
                        description, is_active, usage_count, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        emoji.standard_emoji,
                        emoji.document_id,
                        emoji.alt_text,
                        emoji.category,
                        emoji.description,
                        emoji.is_active,
                        emoji.usage_count,
                        emoji.created_at.isoformat(),
                        emoji.updated_at.isoformat() if emoji.updated_at else None
                    )
                )

                emoji_id = cursor.lastrowid
                emoji.id = emoji_id

                emoji.log_creation()
                logger.info("Создан Custom Emoji: {} -> {}", emoji.standard_emoji, emoji.document_id)

                return emoji

        except Exception as e:
            if isinstance(e, DuplicateRecordError):
                raise
            logger.error("Ошибка создания Custom Emoji: {}", str(e))
            raise DatabaseError(f"Не удалось создать Custom Emoji: {str(e)}")

    @staticmethod
    async def get_by_id(emoji_id: int) -> Optional[CustomEmoji]:
        """
        Получить Custom Emoji по ID

        Args:
            emoji_id: ID эмодзи

        Returns:
            Объект CustomEmoji или None
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, standard_emoji, document_id, alt_text, category,
                              description, is_active, usage_count, created_at, updated_at
                       FROM custom_emojis WHERE id = ?""",
                    (emoji_id,)
                )
                row = await cursor.fetchone()

                if not row:
                    return None

                return EmojiCRUD._row_to_emoji(row)

        except Exception as e:
            logger.error("Ошибка получения Custom Emoji по ID {}: {}", emoji_id, str(e))
            raise DatabaseError(f"Не удалось получить Custom Emoji: {str(e)}")

    @staticmethod
    async def get_by_standard_emoji(standard_emoji: str) -> Optional[CustomEmoji]:
        """
        Получить Custom Emoji по стандартному эмодзи

        Args:
            standard_emoji: Стандартный эмодзи для поиска

        Returns:
            Объект CustomEmoji или None
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, standard_emoji, document_id, alt_text, category,
                              description, is_active, usage_count, created_at, updated_at
                       FROM custom_emojis WHERE standard_emoji = ? AND is_active = TRUE""",
                    (standard_emoji,)
                )
                row = await cursor.fetchone()

                if not row:
                    return None

                return EmojiCRUD._row_to_emoji(row)

        except Exception as e:
            logger.error("Ошибка получения Custom Emoji по эмодзи {}: {}", standard_emoji, str(e))
            raise DatabaseError(f"Не удалось получить Custom Emoji: {str(e)}")

    @staticmethod
    async def get_all(active_only: bool = True) -> List[CustomEmoji]:
        """
        Получить все Custom Emoji

        Args:
            active_only: Только активные эмодзи

        Returns:
            Список CustomEmoji
        """
        try:
            async with get_db_connection() as conn:
                if active_only:
                    cursor = await conn.execute(
                        """SELECT id, standard_emoji, document_id, alt_text, category,
                                  description, is_active, usage_count, created_at, updated_at
                           FROM custom_emojis WHERE is_active = TRUE
                           ORDER BY usage_count DESC, created_at DESC"""
                    )
                else:
                    cursor = await conn.execute(
                        """SELECT id, standard_emoji, document_id, alt_text, category,
                                  description, is_active, usage_count, created_at, updated_at
                           FROM custom_emojis ORDER BY usage_count DESC, created_at DESC"""
                    )

                rows = await cursor.fetchall()
                return [EmojiCRUD._row_to_emoji(row) for row in rows]

        except Exception as e:
            logger.error("Ошибка получения списка Custom Emoji: {}", str(e))
            raise DatabaseError(f"Не удалось получить список Custom Emoji: {str(e)}")

    @staticmethod
    async def get_by_category(category: str) -> List[CustomEmoji]:
        """
        Получить Custom Emoji по категории

        Args:
            category: Категория эмодзи

        Returns:
            Список CustomEmoji
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT id, standard_emoji, document_id, alt_text, category,
                              description, is_active, usage_count, created_at, updated_at
                       FROM custom_emojis WHERE category = ? AND is_active = TRUE
                       ORDER BY usage_count DESC""",
                    (category,)
                )
                rows = await cursor.fetchall()
                return [EmojiCRUD._row_to_emoji(row) for row in rows]

        except Exception as e:
            logger.error("Ошибка получения Custom Emoji по категории {}: {}", category, str(e))
            raise DatabaseError(f"Не удалось получить Custom Emoji: {str(e)}")

    @staticmethod
    async def get_dictionary() -> Dict[str, int]:
        """
        Получить словарь для быстрой замены: standard_emoji -> document_id

        Returns:
            Словарь {эмодзи: document_id}
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT standard_emoji, document_id
                       FROM custom_emojis WHERE is_active = TRUE"""
                )
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}

        except Exception as e:
            logger.error("Ошибка получения словаря Custom Emoji: {}", str(e))
            return {}

    @staticmethod
    async def update(emoji_id: int, **kwargs) -> bool:
        """
        Обновить Custom Emoji

        Args:
            emoji_id: ID эмодзи
            **kwargs: Поля для обновления

        Returns:
            True если обновление успешно
        """
        if not kwargs:
            return False

        try:
            # Формируем SET часть запроса
            set_parts = []
            values = []

            for key, value in kwargs.items():
                if key in ['standard_emoji', 'document_id', 'alt_text', 'category',
                           'description', 'is_active', 'usage_count']:
                    set_parts.append(f"{key} = ?")
                    values.append(value)

            if not set_parts:
                return False

            # Добавляем updated_at
            set_parts.append("updated_at = ?")
            values.append(datetime.now().isoformat())

            values.append(emoji_id)

            async with get_db_transaction() as conn:
                await conn.execute(
                    f"UPDATE custom_emojis SET {', '.join(set_parts)} WHERE id = ?",
                    values
                )

            logger.info("Обновлен Custom Emoji ID {}", emoji_id)
            return True

        except Exception as e:
            logger.error("Ошибка обновления Custom Emoji {}: {}", emoji_id, str(e))
            raise DatabaseError(f"Не удалось обновить Custom Emoji: {str(e)}")

    @staticmethod
    async def increment_usage(emoji_id: int) -> None:
        """
        Увеличить счетчик использований

        Args:
            emoji_id: ID эмодзи
        """
        try:
            async with get_db_transaction() as conn:
                await conn.execute(
                    """UPDATE custom_emojis
                       SET usage_count = usage_count + 1, updated_at = ?
                       WHERE id = ?""",
                    (datetime.now().isoformat(), emoji_id)
                )
                logger.debug("Увеличен счетчик использований для Emoji ID {}", emoji_id)

        except Exception as e:
            logger.error("Ошибка увеличения счетчика Emoji {}: {}", emoji_id, str(e))

    @staticmethod
    async def delete(emoji_id: int) -> bool:
        """
        Удалить Custom Emoji

        Args:
            emoji_id: ID эмодзи

        Returns:
            True если удаление успешно
        """
        try:
            async with get_db_transaction() as conn:
                cursor = await conn.execute(
                    "DELETE FROM custom_emojis WHERE id = ?",
                    (emoji_id,)
                )
                deleted = cursor.rowcount > 0

                if deleted:
                    logger.info("Удален Custom Emoji ID {}", emoji_id)
                else:
                    logger.warning("Custom Emoji ID {} не найден для удаления", emoji_id)

                return deleted

        except Exception as e:
            logger.error("Ошибка удаления Custom Emoji {}: {}", emoji_id, str(e))
            raise DatabaseError(f"Не удалось удалить Custom Emoji: {str(e)}")

    @staticmethod
    async def deactivate(emoji_id: int) -> bool:
        """
        Деактивировать Custom Emoji (мягкое удаление)

        Args:
            emoji_id: ID эмодзи

        Returns:
            True если деактивация успешна
        """
        return await EmojiCRUD.update(emoji_id, is_active=False)

    @staticmethod
    async def get_count() -> int:
        """Получить количество активных Custom Emoji"""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM custom_emojis WHERE is_active = TRUE"
                )
                result = await cursor.fetchone()
                return result[0] if result else 0

        except Exception as e:
            logger.error("Ошибка подсчета Custom Emoji: {}", str(e))
            return 0

    @staticmethod
    def _row_to_emoji(row) -> CustomEmoji:
        """
        Преобразовать строку БД в объект CustomEmoji

        Args:
            row: Строка результата запроса

        Returns:
            Объект CustomEmoji
        """
        created_at = row[8]
        updated_at = row[9]

        # Преобразуем строки в datetime если нужно
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if isinstance(updated_at, str) and updated_at:
            updated_at = datetime.fromisoformat(updated_at)

        return CustomEmoji(
            id=row[0],
            standard_emoji=row[1],
            document_id=row[2],
            alt_text=row[3],
            category=row[4] or "general",
            description=row[5] or "",
            is_active=bool(row[6]),
            usage_count=row[7] or 0,
            created_at=created_at,
            updated_at=updated_at
        )


# Глобальный экземпляр CRUD
_emoji_crud: Optional[EmojiCRUD] = None


def get_emoji_crud() -> EmojiCRUD:
    """Получить экземпляр EmojiCRUD"""
    global _emoji_crud
    if _emoji_crud is None:
        _emoji_crud = EmojiCRUD()
    return _emoji_crud
