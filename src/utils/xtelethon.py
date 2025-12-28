"""
CustomParseMode для Telethon с поддержкой Premium Custom Emoji
Основано на https://github.com/Vinddictive/TelethonPremiumEmoji

Поддерживает синтаксис:
- [emoji](emoji/DOCUMENT_ID) - Custom Emoji
- [text](spoiler) - Спойлер
- Стандартный Markdown форматирование
"""

import re
from typing import List, Tuple, Optional

# Telethon импорты
from telethon.extensions import markdown
from telethon.tl.types import (
    MessageEntityBold,
    MessageEntityItalic,
    MessageEntityCode,
    MessageEntityPre,
    MessageEntityStrike,
    MessageEntityUnderline,
    MessageEntitySpoiler,
    MessageEntityCustomEmoji,
    MessageEntityTextUrl,
    TypeMessageEntity
)

# Логирование
from loguru import logger

logger = logger.bind(module="xtelethon")


class CustomParseMode:
    """
    Кастомный парсер для Telethon с поддержкой Premium Custom Emoji

    Использование:
        client.parse_mode = CustomParseMode()
        await client.send_message(chat, "Hello [fire](emoji/5368324170671202286)!")
    """

    def __init__(self, mode: str = 'markdown'):
        """
        Инициализация парсера

        Args:
            mode: Базовый режим парсинга ('markdown' или 'html')
        """
        self.mode = mode.lower()

        # Паттерн для Custom Emoji: [emoji](emoji/DOCUMENT_ID)
        self._emoji_pattern = re.compile(r'\[([^\]]+)\]\(emoji/(\d+)\)')

        # Паттерн для спойлеров: [text](spoiler)
        self._spoiler_pattern = re.compile(r'\[([^\]]+)\]\(spoiler\)')

        # Паттерн для ссылок (чтобы не путать с emoji): [text](url)
        self._link_pattern = re.compile(r'\[([^\]]+)\]\((?!emoji/|spoiler)(https?://[^\)]+)\)')

    def parse(self, text: str) -> Tuple[str, List[TypeMessageEntity]]:
        """
        Парсинг текста с извлечением entities

        Использует подход оригинального TelethonPremiumEmoji:
        1. Сначала вызывает встроенный markdown парсер
        2. Затем конвертирует MessageEntityTextUrl в специальные типы

        Args:
            text: Текст для парсинга

        Returns:
            (очищенный_текст, список_entities)
        """
        if not text:
            return '', []

        logger.info("🔍 CustomParseMode.parse() ВЫЗВАН! Длина текста: {}", len(text))

        # 1. Парсим через встроенный markdown парсер Telethon
        try:
            parsed_text, entities = markdown.parse(text)
            entities = list(entities) if entities else []
        except Exception as e:
            logger.warning("Ошибка markdown парсинга: {}", str(e))
            return text, []

        logger.debug("После markdown.parse: {} entities", len(entities))

        # 2. Конвертируем MessageEntityTextUrl в специальные типы
        converted_entities = []
        emoji_count = 0
        spoiler_count = 0

        for entity in entities:
            if isinstance(entity, MessageEntityTextUrl):
                url = entity.url

                # Конвертируем emoji/DOCUMENT_ID в MessageEntityCustomEmoji
                if url.startswith('emoji/'):
                    try:
                        doc_id = int(url[6:])  # убираем "emoji/"
                        converted_entities.append(MessageEntityCustomEmoji(
                            offset=entity.offset,
                            length=entity.length,
                            document_id=doc_id
                        ))
                        emoji_count += 1
                        continue
                    except ValueError:
                        logger.warning("Некорректный emoji ID: {}", url)

                # Конвертируем spoiler в MessageEntitySpoiler
                elif url == 'spoiler':
                    converted_entities.append(MessageEntitySpoiler(
                        offset=entity.offset,
                        length=entity.length
                    ))
                    spoiler_count += 1
                    continue

            # Все остальные entities оставляем как есть
            converted_entities.append(entity)

        logger.info("✅ parse() завершён: {} entities (emoji: {}, spoiler: {})",
                   len(converted_entities), emoji_count, spoiler_count)

        return parsed_text, converted_entities

    def _parse_custom_emoji(self, text: str) -> Tuple[str, List[TypeMessageEntity]]:
        """
        Парсинг Custom Emoji

        Args:
            text: Исходный текст

        Returns:
            (текст_без_разметки, список_MessageEntityCustomEmoji)
        """
        entities = []
        offset_correction = 0

        for match in self._emoji_pattern.finditer(text):
            emoji_char = match.group(1)  # Символ эмодзи
            document_id = int(match.group(2))  # Document ID

            # Позиция в результирующем тексте
            start = match.start() - offset_correction
            length = len(emoji_char)

            entities.append(MessageEntityCustomEmoji(
                offset=start,
                length=length,
                document_id=document_id
            ))

            # Корректируем offset для следующих матчей
            # Разница = длина полного матча - длина символа эмодзи
            offset_correction += len(match.group(0)) - length

        # Удаляем разметку, оставляем только эмодзи
        result_text = self._emoji_pattern.sub(r'\1', text)

        return result_text, entities

    def _parse_spoilers(self, text: str) -> Tuple[str, List[TypeMessageEntity]]:
        """
        Парсинг спойлеров

        Args:
            text: Исходный текст

        Returns:
            (текст_без_разметки, список_MessageEntitySpoiler)
        """
        entities = []
        offset_correction = 0

        for match in self._spoiler_pattern.finditer(text):
            spoiler_text = match.group(1)

            start = match.start() - offset_correction
            length = len(spoiler_text)

            entities.append(MessageEntitySpoiler(
                offset=start,
                length=length
            ))

            offset_correction += len(match.group(0)) - length

        result_text = self._spoiler_pattern.sub(r'\1', text)

        return result_text, entities

    def _parse_markdown(self, text: str) -> Tuple[str, List[TypeMessageEntity]]:
        """
        Парсинг стандартного Markdown

        Args:
            text: Текст для парсинга

        Returns:
            (очищенный_текст, entities)
        """
        try:
            # Используем встроенный парсер Telethon
            parsed_text, entities = markdown.parse(text)
            return parsed_text, entities or []
        except Exception as e:
            logger.warning("Ошибка парсинга Markdown: {}", str(e))
            return text, []

    def unparse(self, text: str, entities: List[TypeMessageEntity]) -> str:
        """
        Обратное преобразование: текст + entities -> размеченный текст

        Args:
            text: Чистый текст
            entities: Список entities

        Returns:
            Текст с разметкой
        """
        if not entities:
            return text

        # Сортируем по offset в обратном порядке для корректной вставки
        sorted_entities = sorted(entities, key=lambda e: e.offset, reverse=True)

        result = text

        for entity in sorted_entities:
            start = entity.offset
            end = start + entity.length
            entity_text = text[start:end]

            if isinstance(entity, MessageEntityCustomEmoji):
                # Custom Emoji -> [emoji](emoji/DOCUMENT_ID)
                replacement = f"[{entity_text}](emoji/{entity.document_id})"
            elif isinstance(entity, MessageEntitySpoiler):
                replacement = f"[{entity_text}](spoiler)"
            elif isinstance(entity, MessageEntityBold):
                replacement = f"**{entity_text}**"
            elif isinstance(entity, MessageEntityItalic):
                replacement = f"__{entity_text}__"
            elif isinstance(entity, MessageEntityCode):
                replacement = f"`{entity_text}`"
            elif isinstance(entity, MessageEntityStrike):
                replacement = f"~~{entity_text}~~"
            elif isinstance(entity, MessageEntityUnderline):
                replacement = f"__{entity_text}__"
            elif isinstance(entity, MessageEntityTextUrl):
                replacement = f"[{entity_text}]({entity.url})"
            else:
                continue

            result = result[:start] + replacement + result[end:]

        return result

    @staticmethod
    def format_custom_emoji(emoji_char: str, document_id: int) -> str:
        """
        Форматировать Custom Emoji для отправки

        Args:
            emoji_char: Символ эмодзи (alt-text)
            document_id: Telegram document_id

        Returns:
            Отформатированная строка
        """
        return f"[{emoji_char}](emoji/{document_id})"

    @staticmethod
    def format_spoiler(text: str) -> str:
        """
        Форматировать текст как спойлер

        Args:
            text: Текст для скрытия

        Returns:
            Отформатированная строка
        """
        return f"[{text}](spoiler)"


# Глобальный экземпляр для удобства
_default_parse_mode: Optional[CustomParseMode] = None


def get_custom_parse_mode() -> CustomParseMode:
    """Получить экземпляр CustomParseMode"""
    global _default_parse_mode
    if _default_parse_mode is None:
        _default_parse_mode = CustomParseMode()
    return _default_parse_mode
