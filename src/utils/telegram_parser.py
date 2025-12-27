"""
Парсер ссылок Telegram для извлечения постов
Поддерживает извлечение постов по ссылкам для добавления в примеры стиля
"""

import re
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.utils.exceptions import TelegramParsingError

# Настройка логгера модуля
logger = logger.bind(module="telegram_parser")


class TelegramLinkParser:
    """Парсер ссылок Telegram"""
    
    def __init__(self):
        """Инициализация парсера"""
        # Паттерны ссылок Telegram
        self.link_patterns = {
            # https://t.me/channel_name/123
            "public_channel": re.compile(r'https?://t\.me/([^/]+)/(\d+)'),
            # https://t.me/c/1234567890/123 (приватные каналы)
            "private_channel": re.compile(r'https?://t\.me/c/(\d+)/(\d+)'),
            # tg://resolve?domain=channel_name&post=123
            "tg_protocol": re.compile(r'tg://resolve\?domain=([^&]+)&post=(\d+)'),
            # https://telegram.me/channel_name/123 (старый формат)
            "telegram_me": re.compile(r'https?://telegram\.me/([^/]+)/(\d+)')
        }
        
        logger.debug("Инициализирован парсер ссылок Telegram")
    
    def parse_telegram_link(self, link: str) -> Optional[Dict[str, Any]]:
        """
        Парсит ссылку Telegram и извлекает информацию
        
        Args:
            link: Ссылка на пост в Telegram
            
        Returns:
            Словарь с информацией о посте или None при ошибке
        """
        try:
            link = link.strip()
            logger.debug("Парсинг ссылки: {}", link)
            
            # Проверяем каждый паттерн
            for link_type, pattern in self.link_patterns.items():
                match = pattern.match(link)
                if match:
                    return self._extract_link_info(link_type, match, link)
            
            logger.warning("Не удалось распознать формат ссылки: {}", link)
            return None
            
        except Exception as e:
            logger.error("Ошибка парсинга ссылки {}: {}", link, str(e))
            return None
    
    def _extract_link_info(self, link_type: str, match, original_link: str) -> Dict[str, Any]:
        """Извлечь информацию из распознанной ссылки"""
        
        if link_type == "public_channel":
            channel_username = match.group(1)
            message_id = int(match.group(2))
            
            return {
                "type": "public_channel",
                "channel_username": channel_username,
                "message_id": message_id,
                "channel_id": None,
                "original_link": original_link,
                "is_private": False
            }
        
        elif link_type == "private_channel":
            channel_id = int(match.group(1))
            message_id = int(match.group(2))
            
            # Конвертируем ID в полный формат
            full_channel_id = int(f"-100{channel_id}")
            
            return {
                "type": "private_channel", 
                "channel_username": None,
                "message_id": message_id,
                "channel_id": full_channel_id,
                "original_link": original_link,
                "is_private": True
            }
        
        elif link_type == "tg_protocol":
            channel_username = match.group(1)
            message_id = int(match.group(2))
            
            return {
                "type": "tg_protocol",
                "channel_username": channel_username,
                "message_id": message_id,
                "channel_id": None,
                "original_link": original_link,
                "is_private": False
            }
        
        elif link_type == "telegram_me":
            channel_username = match.group(1)
            message_id = int(match.group(2))
            
            return {
                "type": "telegram_me",
                "channel_username": channel_username,
                "message_id": message_id,
                "channel_id": None,
                "original_link": original_link,
                "is_private": False
            }
        
        return None
    
    def validate_telegram_link(self, link: str) -> bool:
        """
        Проверить, является ли ссылка валидной ссылкой Telegram
        
        Args:
            link: Ссылка для проверки
            
        Returns:
            True если ссылка валидна
        """
        return self.parse_telegram_link(link) is not None
    
    def extract_channel_info(self, link: str) -> Optional[Dict[str, Any]]:
        """
        Извлечь информацию о канале из ссылки
        
        Args:
            link: Ссылка на пост
            
        Returns:
            Информация о канале
        """
        link_info = self.parse_telegram_link(link)
        if not link_info:
            return None
        
        return {
            "username": link_info.get("channel_username"),
            "channel_id": link_info.get("channel_id"),
            "is_private": link_info.get("is_private", False)
        }
    
    def normalize_telegram_link(self, link: str) -> Optional[str]:
        """
        Нормализовать ссылку Telegram к стандартному формату
        
        Args:
            link: Исходная ссылка
            
        Returns:
            Нормализованная ссылка или None при ошибке
        """
        link_info = self.parse_telegram_link(link)
        if not link_info:
            return None
        
        if link_info["is_private"]:
            # Для приватных каналов используем c/ формат
            channel_id = str(link_info["channel_id"])[4:]  # Убираем -100
            return f"https://t.me/c/{channel_id}/{link_info['message_id']}"
        else:
            # Для публичных каналов используем username формат
            return f"https://t.me/{link_info['channel_username']}/{link_info['message_id']}"
    
    def is_supported_link(self, link: str) -> bool:
        """Проверить, поддерживается ли формат ссылки"""
        return any(pattern.match(link.strip()) for pattern in self.link_patterns.values())


class TelegramPostExtractor:
    """Извлекатель постов Telegram через UserBot"""
    
    def __init__(self):
        """Инициализация извлекателя"""
        self.parser = TelegramLinkParser()
        logger.debug("Инициализирован извлекатель постов Telegram")
    
    def _extract_formatted_text(self, message) -> str:
        """
        Извлекает текст с сохранением форматирования в HTML формате для Telegram
        
        Args:
            message: Объект сообщения Telethon
            
        Returns:
            Текст в HTML формате для правильного отображения в Telegram боте
        """
        try:
            # Получаем чистый текст
            raw_text = message.message or message.text or ""
            if not raw_text:
                return ""
            
            # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ для отладки различий
            message_type = type(message).__name__
            has_entities = hasattr(message, 'entities') and message.entities
            entities_count = len(message.entities) if has_entities else 0
            
            logger.debug("Парсинг сообщения: тип={}, текст={} символов, entities={}", 
                        message_type, len(raw_text), entities_count)
            
            if has_entities and entities_count > 0:
                # Логируем типы entities для отладки
                entity_types = [type(entity).__name__ for entity in message.entities[:3]]  # Первые 3
                logger.debug("Типы entities: {}", entity_types)
            
            # Если нет entities, возвращаем чистый текст
            if not has_entities:
                logger.debug("Нет entities, возвращаем чистый текст")
                return raw_text
            
            # Используем простой подход - конвертируем в HTML для Telegram
            return self._convert_to_telegram_html(raw_text, message.entities)
                
        except Exception as e:
            logger.error("Ошибка извлечения форматированного текста: {}", str(e))
            # В случае ошибки возвращаем чистый текст без форматирования
            return message.message or message.text or ""
    
    def _convert_to_telegram_html(self, text: str, entities) -> str:
        """
        Конвертирует entities в HTML формат используя встроенный парсер Telethon
        
        Args:
            text: Исходный текст сообщения
            entities: Список entities из Telethon
            
        Returns:
            Текст в HTML формате для Telegram
        """
        try:
            # Используем встроенный HTML парсер Telethon для корректного форматирования
            from telethon.extensions import html
            
            logger.debug("Начинается конвертация через html.unparse: текст={} символов, entities={}", 
                        len(text), len(entities) if entities else 0)
            
            # Встроенный парсер правильно обрабатывает все entities
            formatted_text = html.unparse(text, entities or [])
            
            logger.debug("Конвертация завершена успешно: {} символов", len(formatted_text))
            return formatted_text
            
        except Exception as e:
            logger.error("Ошибка конвертации в HTML через встроенный парсер: {} | Текст: '{}' | Entities: {}", 
                        str(e), text[:100] + "..." if len(text) > 100 else text, 
                        len(entities) if entities else 0)
            # Fallback к исходному тексту при ошибке
            return text
    
    
    
    
    async def extract_post_from_link(self, link: str, userbot_client) -> Optional[Dict[str, Any]]:
        """
        Извлечь пост по ссылке через UserBot
        
        Args:
            link: Ссылка на пост
            userbot_client: Клиент UserBot (Telethon)
            
        Returns:
            Данные поста или None при ошибке
        """
        try:
            # Парсим ссылку
            link_info = self.parser.parse_telegram_link(link)
            if not link_info:
                logger.error("Не удалось распарсить ссылку: {}", link)
                return None
            
            logger.info("Извлечение поста: канал={}, сообщение={}", 
                       link_info.get("channel_username") or link_info.get("channel_id"),
                       link_info["message_id"])
            
            # Получаем сущность канала с использованием безопасного метода
            entity = None
            if link_info["channel_username"]:
                entity = await userbot_client.safe_api_call(
                    userbot_client.client.get_entity,
                    link_info["channel_username"]
                )
            elif link_info["channel_id"]:
                entity = await userbot_client.safe_api_call(
                    userbot_client.client.get_entity,
                    link_info["channel_id"]
                )
            else:
                logger.error("Не удалось определить канал из ссылки: {}", link)
                return None
            
            if not entity:
                logger.error("Не удалось получить сущность канала для ссылки: {}", link)
                return None
            
            # Получаем сообщение с использованием безопасного метода
            message = await userbot_client.safe_api_call(
                userbot_client.client.get_messages,
                entity,
                ids=link_info["message_id"]
            )
            
            if not message:
                logger.error("Сообщение {} не найдено в канале", link_info["message_id"])
                return None
            
            # Извлекаем текст с сохранением оригинального форматирования
            formatted_text = self._extract_formatted_text(message)
            
            # Извлекаем данные поста
            post_data = {
                "text": formatted_text,
                "raw_text": message.message or message.text or "",  # Сохраняем сырой текст
                "message_id": message.id,
                "channel_id": int(f"-100{entity.id}") if hasattr(entity, 'id') else None,
                "channel_title": getattr(entity, 'title', None),
                "channel_username": getattr(entity, 'username', None),
                "date": message.date,
                "has_media": bool(message.media),
                "media_type": type(message.media).__name__ if message.media else None,
                "source_link": self.parser.normalize_telegram_link(link),
                "views": getattr(message, 'views', None),
                "forwards": getattr(message, 'forwards', None),
                "entities": getattr(message, 'entities', None)  # Сохраняем entities для форматирования
            }
            
            logger.info("Пост успешно извлечен: {} символов, медиа: {}", 
                       len(post_data["text"]), post_data["has_media"])
            
            return post_data
            
        except Exception as e:
            logger.error("Ошибка извлечения поста из ссылки {}: {}", link, str(e))
            return None  # Возвращаем None вместо exception для более graceful handling
    
    async def extract_multiple_posts(
        self, 
        links: list[str], 
        userbot_client
    ) -> Dict[str, Any]:
        """
        Извлечь несколько постов по ссылкам
        
        Args:
            links: Список ссылок
            userbot_client: Клиент UserBot
            
        Returns:
            Результаты извлечения
        """
        results = {
            "successful": [],
            "failed": [],
            "total": len(links)
        }
        
        for i, link in enumerate(links, 1):
            try:
                logger.info("Обработка ссылки {}/{}: {}", i, len(links), link[:50])
                
                post_data = await self.extract_post_from_link(link, userbot_client)
                if post_data:
                    results["successful"].append({
                        "link": link,
                        "post": post_data
                    })
                    logger.debug("Пост {} успешно извлечен", i)
                else:
                    results["failed"].append({
                        "link": link,
                        "error": "Не удалось извлечь пост"
                    })
                    logger.warning("Не удалось извлечь пост {}", i)
                    
            except Exception as e:
                logger.error("Ошибка обработки ссылки {}: {}", i, str(e))
                results["failed"].append({
                    "link": link,
                    "error": str(e)
                })
        
        logger.info("Извлечение завершено: успешно={}, ошибок={}", 
                   len(results["successful"]), len(results["failed"]))
        
        return results


# Глобальные экземпляры
_telegram_parser: Optional[TelegramLinkParser] = None
_post_extractor: Optional[TelegramPostExtractor] = None


def get_telegram_parser() -> TelegramLinkParser:
    """Получить глобальный экземпляр парсера"""
    global _telegram_parser
    
    if _telegram_parser is None:
        _telegram_parser = TelegramLinkParser()
    
    return _telegram_parser


def get_post_extractor() -> TelegramPostExtractor:
    """Получить глобальный экземпляр извлекателя постов"""
    global _post_extractor
    
    if _post_extractor is None:
        _post_extractor = TelegramPostExtractor()
    
    return _post_extractor


def format_entities_to_html(text: str, entities: list) -> str:
    """
    Конвертирует MessageEntity в HTML формат для Telegram
    
    Args:
        text: Исходный текст
        entities: Список MessageEntity из aiogram
        
    Returns:
        Текст в HTML формате
    """
    try:
        if not entities:
            return text
        
        # Сортируем entities по offset для правильной обработки
        sorted_entities = sorted(entities, key=lambda e: e.offset)
        
        # Список для накопления результата
        result = []
        last_offset = 0
        
        for entity in sorted_entities:
            # Добавляем текст до entity
            if entity.offset > last_offset:
                result.append(text[last_offset:entity.offset])
            
            # Извлекаем текст entity
            entity_text = text[entity.offset:entity.offset + entity.length]
            
            # Экранируем HTML символы в тексте
            from html import escape
            escaped_text = escape(entity_text)
            
            # Добавляем соответствующие теги
            if entity.type == "bold":
                result.append(f"<b>{escaped_text}</b>")
            elif entity.type == "italic":
                result.append(f"<i>{escaped_text}</i>")
            elif entity.type == "underline":
                result.append(f"<u>{escaped_text}</u>")
            elif entity.type == "strikethrough":
                result.append(f"<s>{escaped_text}</s>")
            elif entity.type == "spoiler":
                result.append(f"<span class=\"tg-spoiler\">{escaped_text}</span>")
            elif entity.type == "code":
                result.append(f"<code>{escaped_text}</code>")
            elif entity.type == "pre":
                result.append(f"<pre>{escaped_text}</pre>")
            elif entity.type == "text_link":
                url = getattr(entity, 'url', '')
                result.append(f"<a href=\"{escape(url)}\">{escaped_text}</a>")
            elif entity.type == "blockquote":
                result.append(f"<blockquote>{escaped_text}</blockquote>")
            else:
                # Для неизвестных типов просто добавляем текст
                logger.debug("Неизвестный тип entity: {}, добавляем как обычный текст", entity.type)
                result.append(escaped_text)
            
            last_offset = entity.offset + entity.length
        
        # Добавляем оставшийся текст
        if last_offset < len(text):
            result.append(text[last_offset:])
        
        return ''.join(result)
        
    except Exception as e:
        logger.error("Ошибка конвертации entities в HTML: {}", str(e))
        from html import escape
        return escape(text)  # Fallback к экранированному тексту


def extract_formatted_text(text: str, entities: list) -> str:
    """
    Извлекает форматированный текст из Telegram message
    
    Args:
        text: Исходный текст сообщения
        entities: Список MessageEntity
        
    Returns:
        Форматированный HTML текст
    """
    try:
        logger.debug("Извлечение форматированного текста: {} символов, {} entities", 
                    len(text), len(entities) if entities else 0)
        
        if not entities:
            from html import escape
            return escape(text)
        
        # Используем format_entities_to_html для конвертации
        html_text = format_entities_to_html(text, entities)
        
        logger.debug("Форматированный текст готов: {} символов", len(html_text))
        return html_text
        
    except Exception as e:
        logger.error("Ошибка извлечения форматированного текста: {}", str(e))
        from html import escape
        return escape(text)


def validate_telegram_html(html_text: str) -> str:
    """
    Валидирует и исправляет HTML для Telegram
    Убирает вложенные теги и некорректные конструкции
    
    Args:
        html_text: HTML текст для валидации
        
    Returns:
        Исправленный HTML текст
    """
    try:
        import re
        from html import escape
        
        # Логируем входящий HTML для отладки
        logger.debug("Валидация HTML: {} символов", len(html_text))
        
        # Убираем вложенные теги одного типа
        # Например: <b>text1 <b>text2</b> text3</b> -> <b>text1 text2 text3</b>
        
        # Обрабатываем вложенные bold теги
        html_text = re.sub(r'<b>([^<]*)<b>([^<]*)</b>([^<]*)</b>', r'<b>\1\2\3</b>', html_text)
        
        # Обрабатываем вложенные italic теги  
        html_text = re.sub(r'<i>([^<]*)<i>([^<]*)</i>([^<]*)</i>', r'<i>\1\2\3</i>', html_text)
        
        # Убираем пересекающиеся теги: <b>text1 <i>text2</b> text3</i> -> <b>text1</b> <i>text2 text3</i>
        # Это более сложная задача, используем простой подход
        
        # Подсчитываем открывающие и закрывающие теги
        tags_to_check = ['b', 'i', 'u', 's', 'code', 'pre']
        
        for tag in tags_to_check:
            open_count = len(re.findall(f'<{tag}>', html_text))
            close_count = len(re.findall(f'</{tag}>', html_text))
            
            if open_count != close_count:
                logger.warning("Несоответствие тегов {}: открывающих={}, закрывающих={}", 
                             tag, open_count, close_count)
                
                # Простое исправление - убираем все теги этого типа
                html_text = re.sub(f'</?{tag}>', '', html_text)
        
        # Убираем пустые теги
        for tag in tags_to_check:
            html_text = re.sub(f'<{tag}></{tag}>', '', html_text)
            html_text = re.sub(f'<{tag}>\\s*</{tag}>', '', html_text)
        
        # Проверяем финальную валидность базовым парсером
        try:
            import xml.etree.ElementTree as ET
            # Оборачиваем в корневой элемент для валидации
            wrapped = f"<root>{html_text}</root>"
            ET.fromstring(wrapped)
            logger.debug("HTML прошел валидацию")
        except ET.ParseError as e:
            logger.warning("HTML не прошел валидацию XML: {}, возвращаем plain text", str(e))
            # В случае ошибки возвращаем текст без тегов
            clean_text = re.sub(r'<[^>]+>', '', html_text)
            return escape(clean_text)
        
        return html_text
        
    except Exception as e:
        logger.error("Ошибка валидации HTML: {}", str(e))
        # В случае критической ошибки возвращаем экранированный plain text
        from html import escape
        clean_text = re.sub(r'<[^>]+>', '', html_text)
        return escape(clean_text)