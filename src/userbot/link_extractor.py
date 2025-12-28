"""
Извлечение ссылок из постов Telegram
Поддерживает MessageEntityUrl и MessageEntityTextUrl
"""

from dataclasses import dataclass
from typing import List, Optional

from loguru import logger
from telethon.tl.types import (
    Message,
    MessageEntityUrl,
    MessageEntityTextUrl,
)

# Настройка логгера модуля
logger = logger.bind(module="link_extractor")


@dataclass
class ExtractedLink:
    """Извлеченная ссылка из поста"""
    url: str                      # URL ссылки
    display_text: Optional[str]   # Текст ссылки (для TextUrl)
    offset: int                   # Позиция в тексте
    length: int                   # Длина
    is_hyperlink: bool            # True если TextUrl (гиперссылка)


class LinkExtractor:
    """Извлекатель ссылок из Telethon сообщений"""

    def extract_links(self, message: Message) -> List[ExtractedLink]:
        """
        Извлечь все ссылки из сообщения

        Args:
            message: Telethon Message объект

        Returns:
            Список ExtractedLink объектов
        """
        links: List[ExtractedLink] = []

        if not message.entities:
            return links

        text = message.message or ""

        for entity in message.entities:
            try:
                if isinstance(entity, MessageEntityUrl):
                    # Обычная URL в тексте (https://example.com)
                    url = text[entity.offset:entity.offset + entity.length]
                    links.append(ExtractedLink(
                        url=url,
                        display_text=None,
                        offset=entity.offset,
                        length=entity.length,
                        is_hyperlink=False
                    ))
                    logger.debug("Найдена URL: {}", url[:50])

                elif isinstance(entity, MessageEntityTextUrl):
                    # Гиперссылка [текст](url)
                    display_text = text[entity.offset:entity.offset + entity.length]
                    links.append(ExtractedLink(
                        url=entity.url,
                        display_text=display_text,
                        offset=entity.offset,
                        length=entity.length,
                        is_hyperlink=True
                    ))
                    logger.debug("Найдена гиперссылка: '{}' -> {}", display_text, entity.url[:50])

            except Exception as e:
                logger.error("Ошибка извлечения entity: {}", str(e))
                continue

        logger.debug("Извлечено {} ссылок из сообщения", len(links))
        return links

    def to_json_list(self, links: List[ExtractedLink]) -> List[dict]:
        """
        Преобразовать список ссылок в JSON-сериализуемый формат

        Args:
            links: Список ExtractedLink

        Returns:
            Список словарей для JSON
        """
        return [
            {
                "url": link.url,
                "display_text": link.display_text,
                "offset": link.offset,
                "is_hyperlink": link.is_hyperlink
            }
            for link in links
        ]


# Глобальный экземпляр
_link_extractor: Optional[LinkExtractor] = None


def get_link_extractor() -> LinkExtractor:
    """Получить экземпляр LinkExtractor"""
    global _link_extractor
    if _link_extractor is None:
        _link_extractor = LinkExtractor()
        logger.debug("Инициализирован LinkExtractor")
    return _link_extractor
