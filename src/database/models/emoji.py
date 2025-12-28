"""
Модель Custom Emoji для Premium эмодзи
Хранит маппинг стандартных эмодзи на Premium версии
"""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from .base import BaseModel

# Настройка логгера модуля
logger = logger.bind(module="models_emoji")


@dataclass
class CustomEmoji(BaseModel):
    """
    Модель Custom Emoji для Premium эмодзи

    Attributes:
        standard_emoji: Стандартный эмодзи для замены (например: fire)
        document_id: Telegram document_id для Premium эмодзи
        alt_text: Альтернативный текст (должен быть валидным эмодзи)
        category: Категория эмодзи (positive, negative, crypto, etc.)
        description: Описание для удобства управления
        is_active: Активен ли эмодзи для замены
        usage_count: Счетчик использований
    """

    # Основные поля
    standard_emoji: str = ""  # Стандартный эмодзи
    document_id: int = 0      # Telegram document_id
    alt_text: str = ""        # Alt-text (должен быть эмодзи)

    # Дополнительные поля
    category: str = "general"
    description: str = ""
    is_active: bool = True
    usage_count: int = 0

    def validate(self) -> bool:
        """Валидация модели Custom Emoji"""

        # standard_emoji не должен быть пустым
        if not self.standard_emoji:
            logger.error("standard_emoji не может быть пустым")
            return False

        # document_id должен быть положительным
        if self.document_id <= 0:
            logger.error("document_id должен быть положительным: {}", self.document_id)
            return False

        # alt_text не должен быть пустым
        if not self.alt_text:
            logger.error("alt_text не может быть пустым")
            return False

        logger.debug("Валидация Custom Emoji {} прошла успешно", self.standard_emoji)
        return True

    @property
    def telethon_format(self) -> str:
        """
        Получить формат для Telethon CustomParseMode
        Формат: [emoji](emoji/DOCUMENT_ID)
        """
        return f"[{self.alt_text}](emoji/{self.document_id})"

    @property
    def markdown_format(self) -> str:
        """
        Получить Markdown формат для Telethon
        Формат: [emoji](tg://emoji?id=DOCUMENT_ID)
        """
        return f"[{self.alt_text}](tg://emoji?id={self.document_id})"

    def increment_usage(self) -> None:
        """Увеличить счетчик использований"""
        self.usage_count += 1
        self.update_timestamp()

    def __repr__(self) -> str:
        """Строковое представление"""
        return (
            f"CustomEmoji(id={self.id}, emoji='{self.standard_emoji}', "
            f"doc_id={self.document_id}, category='{self.category}')"
        )


def create_custom_emoji(
    standard_emoji: str,
    document_id: int,
    alt_text: str,
    category: str = "general",
    description: str = ""
) -> CustomEmoji:
    """
    Фабричная функция для создания Custom Emoji

    Args:
        standard_emoji: Стандартный эмодзи для замены
        document_id: Telegram document_id
        alt_text: Альтернативный текст (должен быть эмодзи)
        category: Категория эмодзи
        description: Описание

    Returns:
        Созданный объект CustomEmoji
    """
    # Преобразуем document_id в int если передан как строка
    if isinstance(document_id, str):
        document_id = int(document_id)

    emoji = CustomEmoji(
        standard_emoji=standard_emoji,
        document_id=document_id,
        alt_text=alt_text,
        category=category,
        description=description
    )

    if not emoji.validate():
        logger.error("Невалидный Custom Emoji: {}", standard_emoji)

    return emoji
