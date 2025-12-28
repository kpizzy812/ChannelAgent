"""
Словарь Custom Emoji с кешированием
Управление маппингом стандартных эмодзи на Premium версии
"""

from typing import Optional, Dict, List, Tuple
from datetime import datetime

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.database.crud.emoji import get_emoji_crud, EmojiCRUD
from src.database.models.emoji import CustomEmoji, create_custom_emoji

# Настройка логгера модуля
logger = logger.bind(module="emoji_dictionary")


class EmojiDictionary:
    """
    Словарь Custom Emoji с кешированием в памяти
    Обеспечивает быстрый доступ к маппингу эмодзи
    """

    def __init__(self):
        """Инициализация словаря"""
        # Кеш: стандартный_эмодзи -> (document_id, alt_text, emoji_id)
        self._cache: Dict[str, Tuple[int, str, int]] = {}
        self._loaded: bool = False
        self._last_refresh: Optional[datetime] = None
        self._crud: EmojiCRUD = get_emoji_crud()

    async def load(self) -> None:
        """Загрузить словарь из БД в кеш"""
        try:
            emojis = await self._crud.get_all(active_only=True)

            self._cache.clear()
            for emoji in emojis:
                self._cache[emoji.standard_emoji] = (
                    emoji.document_id,
                    emoji.alt_text,
                    emoji.id
                )

            self._loaded = True
            self._last_refresh = datetime.now()

            logger.info("Загружено {} Custom Emoji в кеш", len(self._cache))

        except Exception as e:
            logger.error("Ошибка загрузки словаря эмодзи: {}", str(e))
            self._loaded = False

    async def ensure_loaded(self) -> None:
        """Убедиться что словарь загружен"""
        if not self._loaded:
            await self.load()

    async def refresh(self) -> None:
        """Принудительно обновить кеш из БД"""
        await self.load()
        logger.info("Кеш словаря эмодзи обновлен")

    async def get_document_id(self, standard_emoji: str) -> Optional[int]:
        """
        Получить document_id для стандартного эмодзи

        Args:
            standard_emoji: Стандартный эмодзи

        Returns:
            document_id или None если не найден
        """
        await self.ensure_loaded()

        if standard_emoji in self._cache:
            doc_id, _, emoji_id = self._cache[standard_emoji]
            # Увеличиваем счетчик использований асинхронно
            await self._crud.increment_usage(emoji_id)
            return doc_id

        return None

    async def get_replacement(self, standard_emoji: str) -> Optional[Tuple[int, str]]:
        """
        Получить данные для замены эмодзи

        Args:
            standard_emoji: Стандартный эмодзи

        Returns:
            (document_id, alt_text) или None
        """
        await self.ensure_loaded()

        if standard_emoji in self._cache:
            doc_id, alt_text, emoji_id = self._cache[standard_emoji]
            await self._crud.increment_usage(emoji_id)
            return (doc_id, alt_text)

        return None

    async def add_emoji(
        self,
        standard_emoji: str,
        document_id: int,
        alt_text: str,
        category: str = "general",
        description: str = ""
    ) -> bool:
        """
        Добавить новый эмодзи в словарь

        Args:
            standard_emoji: Стандартный эмодзи для замены
            document_id: Telegram document_id
            alt_text: Alt-text (должен быть эмодзи)
            category: Категория
            description: Описание

        Returns:
            True если добавление успешно
        """
        try:
            emoji = create_custom_emoji(
                standard_emoji=standard_emoji,
                document_id=document_id,
                alt_text=alt_text,
                category=category,
                description=description
            )

            saved_emoji = await self._crud.create(emoji)

            # Обновляем кеш
            self._cache[standard_emoji] = (document_id, alt_text, saved_emoji.id)

            logger.info("Добавлен Custom Emoji: {} -> {}", standard_emoji, document_id)
            return True

        except Exception as e:
            logger.error("Ошибка добавления Custom Emoji: {}", str(e))
            return False

    async def remove_emoji(self, standard_emoji: str) -> bool:
        """
        Удалить эмодзи из словаря

        Args:
            standard_emoji: Стандартный эмодзи

        Returns:
            True если удаление успешно
        """
        try:
            emoji = await self._crud.get_by_standard_emoji(standard_emoji)
            if emoji:
                await self._crud.delete(emoji.id)
                self._cache.pop(standard_emoji, None)
                logger.info("Удален Custom Emoji: {}", standard_emoji)
                return True
            return False

        except Exception as e:
            logger.error("Ошибка удаления Custom Emoji: {}", str(e))
            return False

    def get_all(self) -> Dict[str, int]:
        """
        Получить весь словарь (из кеша)

        Returns:
            Словарь {эмодзи: document_id}
        """
        return {emoji: data[0] for emoji, data in self._cache.items()}

    def get_all_with_details(self) -> Dict[str, Tuple[int, str]]:
        """
        Получить словарь с деталями

        Returns:
            Словарь {эмодзи: (document_id, alt_text)}
        """
        return {emoji: (data[0], data[1]) for emoji, data in self._cache.items()}

    async def get_categories(self) -> List[str]:
        """Получить список всех категорий"""
        try:
            emojis = await self._crud.get_all(active_only=True)
            categories = set(emoji.category for emoji in emojis)
            return sorted(list(categories))
        except Exception as e:
            logger.error("Ошибка получения категорий: {}", str(e))
            return []

    def has_emoji(self, standard_emoji: str) -> bool:
        """Проверить есть ли эмодзи в словаре"""
        return standard_emoji in self._cache

    @property
    def count(self) -> int:
        """Количество эмодзи в кеше"""
        return len(self._cache)

    @property
    def is_loaded(self) -> bool:
        """Загружен ли словарь"""
        return self._loaded


# Глобальный экземпляр словаря
_emoji_dictionary: Optional[EmojiDictionary] = None


async def get_emoji_dictionary() -> EmojiDictionary:
    """Получить экземпляр EmojiDictionary"""
    global _emoji_dictionary
    if _emoji_dictionary is None:
        _emoji_dictionary = EmojiDictionary()
        await _emoji_dictionary.load()
    return _emoji_dictionary


async def reload_emoji_dictionary() -> None:
    """Перезагрузить словарь эмодзи"""
    global _emoji_dictionary
    if _emoji_dictionary is not None:
        await _emoji_dictionary.refresh()
