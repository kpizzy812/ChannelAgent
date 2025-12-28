"""
Процессор замены эмодзи в тексте
Заменяет стандартные эмодзи на Premium Custom Emoji формат
"""

import re
from typing import Tuple, Optional, List

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from .dictionary import EmojiDictionary, get_emoji_dictionary

# Настройка логгера модуля
logger = logger.bind(module="emoji_processor")

# Регулярное выражение для поиска эмодзи в тексте
# Покрывает основные блоки Unicode с эмодзи
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # Эмотиконы
    "\U0001F300-\U0001F5FF"  # Символы и пиктограммы
    "\U0001F680-\U0001F6FF"  # Транспорт и символы
    "\U0001F700-\U0001F77F"  # Алхимические символы
    "\U0001F780-\U0001F7FF"  # Геометрические фигуры
    "\U0001F800-\U0001F8FF"  # Дополнительные стрелки
    "\U0001F900-\U0001F9FF"  # Дополнительные символы
    "\U0001FA00-\U0001FA6F"  # Шахматные символы
    "\U0001FA70-\U0001FAFF"  # Символы и пиктограммы Extended-A
    "\U00002702-\U000027B0"  # Dingbats
    "\U0001F1E0-\U0001F1FF"  # Флаги
    "\U00002600-\U000026FF"  # Разные символы
    "\U00002700-\U000027BF"  # Dingbats
    "\U0000FE00-\U0000FE0F"  # Variation Selectors
    "\U0001F000-\U0001F02F"  # Mahjong tiles
    "]+"
)


class EmojiProcessor:
    """
    Процессор для замены стандартных эмодзи на Premium Custom Emoji
    Использует синтаксис [emoji](emoji/DOCUMENT_ID) для Telethon
    """

    def __init__(self, dictionary: EmojiDictionary):
        """
        Инициализация процессора

        Args:
            dictionary: Словарь Custom Emoji
        """
        self.dictionary = dictionary
        self._stats_processed = 0
        self._stats_replaced = 0

    async def process_text(self, text: str) -> Tuple[str, int]:
        """
        Обработать текст и заменить эмодзи на Premium версии

        Args:
            text: Исходный текст с эмодзи

        Returns:
            (обработанный_текст, количество_замен)
        """
        if not text:
            return text, 0

        await self.dictionary.ensure_loaded()

        replacements = 0
        result = text

        # Находим все эмодзи в тексте
        emoji_matches = EMOJI_PATTERN.findall(text)

        # Уникальные эмодзи для обработки
        unique_emojis = set(emoji_matches)

        for emoji in unique_emojis:
            replacement_data = await self.dictionary.get_replacement(emoji)

            if replacement_data:
                doc_id, alt_text = replacement_data

                # Формат для CustomParseMode: [emoji](emoji/DOCUMENT_ID)
                premium_format = f"[{alt_text}](emoji/{doc_id})"

                # Заменяем все вхождения этого эмодзи
                count = result.count(emoji)
                result = result.replace(emoji, premium_format)
                replacements += count

                logger.debug("Заменено {} эмодзи '{}' на Premium формат", count, emoji)

        self._stats_processed += 1
        self._stats_replaced += replacements

        if replacements > 0:
            logger.info("Обработан текст: {} замен эмодзи", replacements)

        # Логируем эмодзи которые не были заменены (нет в словаре)
        missing = [e for e in unique_emojis if not self.dictionary.has_emoji(e)]
        if missing:
            logger.warning("⚠️ Эмодзи БЕЗ Premium версии (не в словаре): {}", " ".join(missing))

        return result, replacements

    async def process_text_markdown(self, text: str) -> Tuple[str, int]:
        """
        Обработать текст с использованием Markdown формата
        Использует синтаксис [emoji](tg://emoji?id=DOCUMENT_ID)

        Args:
            text: Исходный текст

        Returns:
            (обработанный_текст, количество_замен)
        """
        if not text:
            return text, 0

        await self.dictionary.ensure_loaded()

        replacements = 0
        result = text

        emoji_matches = EMOJI_PATTERN.findall(text)
        unique_emojis = set(emoji_matches)

        for emoji in unique_emojis:
            replacement_data = await self.dictionary.get_replacement(emoji)

            if replacement_data:
                doc_id, alt_text = replacement_data

                # Markdown формат: [emoji](tg://emoji?id=DOCUMENT_ID)
                markdown_format = f"[{alt_text}](tg://emoji?id={doc_id})"

                count = result.count(emoji)
                result = result.replace(emoji, markdown_format)
                replacements += count

        return result, replacements

    def find_emojis(self, text: str) -> List[str]:
        """
        Найти все эмодзи в тексте

        Args:
            text: Текст для поиска

        Returns:
            Список найденных эмодзи
        """
        return EMOJI_PATTERN.findall(text)

    async def get_missing_emojis(self, text: str) -> List[str]:
        """
        Найти эмодзи которых нет в словаре

        Args:
            text: Текст для анализа

        Returns:
            Список эмодзи без Premium версий
        """
        await self.dictionary.ensure_loaded()

        emojis = set(self.find_emojis(text))
        missing = []

        for emoji in emojis:
            if not self.dictionary.has_emoji(emoji):
                missing.append(emoji)

        return missing

    async def get_coverage_stats(self, text: str) -> dict:
        """
        Получить статистику покрытия эмодзи

        Args:
            text: Текст для анализа

        Returns:
            Статистика покрытия
        """
        await self.dictionary.ensure_loaded()

        emojis = self.find_emojis(text)
        unique = set(emojis)

        covered = sum(1 for e in unique if self.dictionary.has_emoji(e))
        missing = len(unique) - covered

        return {
            "total_emojis": len(emojis),
            "unique_emojis": len(unique),
            "covered": covered,
            "missing": missing,
            "coverage_percent": (covered / len(unique) * 100) if unique else 100
        }

    @property
    def stats(self) -> dict:
        """Статистика обработки"""
        return {
            "texts_processed": self._stats_processed,
            "emojis_replaced": self._stats_replaced
        }


# Глобальный экземпляр процессора
_emoji_processor: Optional[EmojiProcessor] = None


async def get_emoji_processor() -> EmojiProcessor:
    """Получить экземпляр EmojiProcessor"""
    global _emoji_processor
    if _emoji_processor is None:
        dictionary = await get_emoji_dictionary()
        _emoji_processor = EmojiProcessor(dictionary)
    return _emoji_processor
