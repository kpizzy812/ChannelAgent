"""
Экстрактор Custom Emoji из сообщений Telegram
Извлекает document_id и связанный стандартный эмодзи из Premium эмодзи
"""

from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Telethon типы
try:
    from telethon.tl.types import MessageEntityCustomEmoji
    from telethon.tl.functions.messages import GetCustomEmojiDocumentsRequest
    from telethon.tl.types import DocumentAttributeCustomEmoji
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False
    logger.warning("Telethon не установлен, извлечение Custom Emoji недоступно")


@dataclass
class ExtractedEmoji:
    """Извлечённый Custom Emoji с полной информацией"""
    document_id: int          # ID документа Premium эмодзи
    premium_char: str         # Символ Premium эмодзи (как отображается)
    standard_emoji: str       # Связанный стандартный эмодзи (alt)
    is_free: bool = False     # Доступен ли без Premium

# Локальные импорты
from .dictionary import EmojiDictionary, get_emoji_dictionary

# Настройка логгера модуля
logger = logger.bind(module="emoji_extractor")


class EmojiExtractor:
    """
    Экстрактор Custom Emoji из Telegram сообщений
    Позволяет извлечь document_id и связанный стандартный эмодзи
    """

    def __init__(self, dictionary: EmojiDictionary):
        """
        Инициализация экстрактора

        Args:
            dictionary: Словарь для добавления эмодзи
        """
        self.dictionary = dictionary
        self._client = None  # Telethon клиент для API запросов

    def set_client(self, client) -> None:
        """Установить Telethon клиент для API запросов"""
        self._client = client

    async def get_emoji_info(self, document_ids: List[int]) -> Dict[int, ExtractedEmoji]:
        """
        Получить полную информацию о Custom Emoji через Telegram API

        Args:
            document_ids: Список document_id для запроса

        Returns:
            Словарь {document_id: ExtractedEmoji}
        """
        if not TELETHON_AVAILABLE or not self._client:
            logger.warning("Telethon клиент недоступен для получения информации об эмодзи")
            return {}

        try:
            # Запрашиваем информацию о документах эмодзи
            documents = await self._client(GetCustomEmojiDocumentsRequest(
                document_id=document_ids
            ))

            result = {}
            for doc in documents:
                doc_id = doc.id

                # Ищем атрибут CustomEmoji
                standard_emoji = ""
                is_free = False

                for attr in doc.attributes:
                    if isinstance(attr, DocumentAttributeCustomEmoji):
                        standard_emoji = attr.alt  # Связанный стандартный эмодзи
                        is_free = getattr(attr, 'free', False)
                        break

                if standard_emoji:
                    result[doc_id] = ExtractedEmoji(
                        document_id=doc_id,
                        premium_char=standard_emoji,  # Premium показывает тот же символ
                        standard_emoji=standard_emoji,
                        is_free=is_free
                    )
                    logger.debug("Получена информация: doc_id={} -> alt='{}'", doc_id, standard_emoji)

            return result

        except Exception as e:
            logger.error("Ошибка получения информации об эмодзи: {}", str(e))
            return {}

    async def extract_with_info(self, message) -> List[ExtractedEmoji]:
        """
        Извлечь Custom Emoji из сообщения с полной информацией

        Args:
            message: Объект сообщения Telethon

        Returns:
            Список ExtractedEmoji с document_id и связанным стандартным эмодзи
        """
        # Сначала извлекаем базовую информацию
        basic_emojis = self.extract_from_message(message)

        if not basic_emojis:
            return []

        # Получаем document_ids
        doc_ids = [doc_id for _, doc_id in basic_emojis]

        # Запрашиваем полную информацию через API
        emoji_info = await self.get_emoji_info(doc_ids)

        result = []
        for emoji_char, doc_id in basic_emojis:
            if doc_id in emoji_info:
                result.append(emoji_info[doc_id])
            else:
                # Fallback - используем символ из сообщения как alt
                result.append(ExtractedEmoji(
                    document_id=doc_id,
                    premium_char=emoji_char,
                    standard_emoji=emoji_char,  # Fallback
                    is_free=False
                ))

        return result

    def extract_from_message(self, message) -> List[Tuple[str, int]]:
        """
        Извлечь все Custom Emoji из сообщения Telethon

        Args:
            message: Объект сообщения Telethon

        Returns:
            Список кортежей (emoji_char, document_id)
        """
        if not TELETHON_AVAILABLE:
            logger.error("Telethon не доступен для извлечения эмодзи")
            return []

        custom_emojis = []

        if not message or not hasattr(message, 'entities') or not message.entities:
            return []

        text = message.message or message.text or ""
        if not text:
            return []

        for entity in message.entities:
            if isinstance(entity, MessageEntityCustomEmoji):
                try:
                    # Извлекаем символ эмодзи из текста по позиции
                    emoji_char = text[entity.offset:entity.offset + entity.length]
                    document_id = entity.document_id

                    custom_emojis.append((emoji_char, document_id))

                    logger.debug("Извлечен Custom Emoji: {} -> {}", emoji_char, document_id)

                except Exception as e:
                    logger.error("Ошибка извлечения эмодзи из entity: {}", str(e))
                    continue

        if custom_emojis:
            logger.info("Извлечено {} Custom Emoji из сообщения", len(custom_emojis))

        return custom_emojis

    def extract_from_entities(
        self,
        text: str,
        entities: list
    ) -> List[Tuple[str, int]]:
        """
        Извлечь Custom Emoji из текста и списка entities

        Args:
            text: Текст сообщения
            entities: Список entities

        Returns:
            Список кортежей (emoji_char, document_id)
        """
        if not TELETHON_AVAILABLE:
            return []

        custom_emojis = []

        if not entities:
            return []

        for entity in entities:
            if isinstance(entity, MessageEntityCustomEmoji):
                try:
                    emoji_char = text[entity.offset:entity.offset + entity.length]
                    document_id = entity.document_id
                    custom_emojis.append((emoji_char, document_id))
                except Exception as e:
                    logger.error("Ошибка извлечения: {}", str(e))

        return custom_emojis

    async def auto_add_to_dictionary(
        self,
        emojis: List[Tuple[str, int]],
        category: str = "extracted",
        description_prefix: str = "Автоизвлечено"
    ) -> int:
        """
        Автоматически добавить извлеченные эмодзи в словарь

        Args:
            emojis: Список (emoji_char, document_id)
            category: Категория для новых эмодзи
            description_prefix: Префикс описания

        Returns:
            Количество добавленных эмодзи
        """
        added_count = 0

        for emoji_char, document_id in emojis:
            # Проверяем есть ли уже такой эмодзи
            if self.dictionary.has_emoji(emoji_char):
                logger.debug("Эмодзи {} уже в словаре, пропускаем", emoji_char)
                continue

            try:
                success = await self.dictionary.add_emoji(
                    standard_emoji=emoji_char,
                    document_id=document_id,
                    alt_text=emoji_char,  # Alt-text = сам эмодзи
                    category=category,
                    description=f"{description_prefix}: {emoji_char}"
                )

                if success:
                    added_count += 1
                    logger.info("Автодобавлен Custom Emoji: {} -> {}", emoji_char, document_id)

            except Exception as e:
                logger.error("Ошибка автодобавления эмодзи {}: {}", emoji_char, str(e))

        return added_count

    async def extract_and_add(
        self,
        message,
        category: str = "extracted"
    ) -> Tuple[int, int]:
        """
        Извлечь эмодзи из сообщения и добавить в словарь

        Args:
            message: Сообщение Telethon
            category: Категория для новых эмодзи

        Returns:
            (количество_извлеченных, количество_добавленных)
        """
        extracted = self.extract_from_message(message)

        if not extracted:
            return 0, 0

        added = await self.auto_add_to_dictionary(
            extracted,
            category=category,
            description_prefix="Извлечено из сообщения"
        )

        return len(extracted), added


# Глобальный экземпляр экстрактора
_emoji_extractor: Optional[EmojiExtractor] = None


async def get_emoji_extractor() -> EmojiExtractor:
    """Получить экземпляр EmojiExtractor"""
    global _emoji_extractor
    if _emoji_extractor is None:
        dictionary = await get_emoji_dictionary()
        _emoji_extractor = EmojiExtractor(dictionary)
    return _emoji_extractor
