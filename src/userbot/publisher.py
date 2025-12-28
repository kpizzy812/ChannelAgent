"""
Публикатор постов через UserBot с поддержкой Premium Custom Emoji
Использует Telethon для публикации в каналы от имени пользователя
"""

import asyncio
from pathlib import Path
from typing import Optional, List

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Сторонние библиотеки
from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChannelPrivateError, ChatWriteForbiddenError
from telethon.tl.types import PeerChannel

# Локальные импорты
from src.utils.config import get_config
from src.utils.xtelethon import CustomParseMode
from src.emoji.processor import get_emoji_processor
from src.utils.post_footer import add_footer_to_post

# Настройка логгера модуля
logger = logger.bind(module="userbot_publisher")


class UserbotPublisher:
    """
    Публикатор постов через UserBot с Premium Custom Emoji

    Использует CustomParseMode для парсинга синтаксиса [emoji](emoji/DOC_ID)
    и публикует посты от имени пользователя с Premium подпиской
    """

    def __init__(self, client: TelegramClient):
        """
        Инициализация публикатора

        Args:
            client: Инициализированный TelegramClient
        """
        self.client = client
        self.config = get_config()
        self._parse_mode: Optional[CustomParseMode] = None
        self._initialized = False
        self._publish_count = 0
        self._target_entity = None  # Кешированная entity целевого канала

    async def initialize(self) -> bool:
        """
        Инициализировать публикатор

        Returns:
            True если инициализация успешна
        """
        try:
            if not self.client:
                logger.error("TelegramClient не предоставлен")
                return False

            if not self.client.is_connected():
                await self.client.connect()

            # Выводим информацию о подключённом UserBot
            me = await self.client.get_me()
            logger.info("🤖 UserBot подключён: @{} ({} {}) ID:{}",
                       me.username or "no_username",
                       me.first_name or "",
                       me.last_name or "",
                       me.id)

            # ВАЖНО: Загружаем диалоги чтобы заполнить кеш entities
            # Это позволяет Telethon узнать о всех каналах где UserBot админ
            logger.info("Загрузка диалогов для заполнения кеша entities...")
            dialogs = await self.client.get_dialogs(limit=100)
            logger.info("Загружено {} диалогов в кеш", len(dialogs))

            # Устанавливаем CustomParseMode для поддержки Premium Emoji
            # ВАЖНО: Устанавливаем parse_mode на клиенте - это правильный подход
            # согласно документации TelethonPremiumEmoji
            self._parse_mode = CustomParseMode()
            self.client.parse_mode = self._parse_mode

            # Проверяем доступ к целевому каналу
            target_channel = self.config.TARGET_CHANNEL_ID
            if target_channel:
                target_pure_id = self._extract_channel_id(target_channel)
                logger.info("🎯 Ищем целевой канал: config={} -> pure_id={}", target_channel, target_pure_id)

                # Ищем канал в загруженных диалогах
                self._target_entity = None
                channels_found = []

                for dialog in dialogs:
                    entity = dialog.entity
                    if hasattr(entity, 'id'):
                        # Собираем список каналов для диагностики
                        if hasattr(entity, 'broadcast') or hasattr(entity, 'megagroup'):
                            channels_found.append({
                                'id': entity.id,
                                'title': getattr(entity, 'title', 'unknown'),
                                'username': getattr(entity, 'username', None)
                            })

                        # Проверяем совпадение ID
                        if entity.id == target_pure_id:
                            self._target_entity = entity
                            logger.info("✅ Целевой канал найден в диалогах: {} (@{}) ID:{}",
                                       getattr(entity, 'title', 'unknown'),
                                       getattr(entity, 'username', 'no_username'),
                                       entity.id)

                if not self._target_entity:
                    logger.warning("❌ Целевой канал {} НЕ найден в диалогах UserBot!", target_pure_id)
                    logger.warning("📋 Доступные каналы UserBot ({}):", len(channels_found))
                    for ch in channels_found[:15]:
                        logger.warning("   • {} (@{}) ID:{}", ch['title'], ch['username'], ch['id'])

            self._initialized = True
            logger.info("UserbotPublisher инициализирован успешно")
            return True

        except Exception as e:
            logger.error("Ошибка инициализации UserbotPublisher: {}", str(e))
            return False

    @property
    def is_available(self) -> bool:
        """Проверить доступность публикатора"""
        return (
            self._initialized and
            self.client is not None and
            self.client.is_connected()
        )

    async def publish_post(
        self,
        channel_id,
        text: str,
        photo_path: Optional[str] = None,
        video_path: Optional[str] = None,
        media_items: Optional[List[dict]] = None,
        pin_post: bool = False,
        add_footer: bool = True
    ) -> Optional[int]:
        """
        Опубликовать пост в канал через UserBot

        Args:
            channel_id: ID канала (int) или username (str, например "@Kpeezy4L")
            text: Текст поста (с обычными эмодзи)
            photo_path: Путь к фото (опционально)
            video_path: Путь к видео (опционально)
            media_items: Список медиа для альбома [{"type": "photo", "path": "..."}]
            pin_post: Закрепить пост
            add_footer: Добавить футер к посту

        Returns:
            message_id опубликованного сообщения или None при ошибке
        """
        if not self.is_available:
            logger.error("UserbotPublisher недоступен")
            return None

        # Если передан альбом - используем publish_album
        if media_items and len(media_items) > 1:
            return await self.publish_album(
                channel_id, text, media_items, pin_post, add_footer
            )

        try:
            # Сначала добавляем футер (чтобы эмодзи в нём тоже заменились)
            full_text = text
            if add_footer:
                full_text = add_footer_to_post(text, parse_mode="Markdown")

            # Обрабатываем текст - заменяем эмодзи на Premium версии
            processor = await get_emoji_processor()
            processed_text, emoji_count = await processor.process_text(full_text)

            if emoji_count > 0:
                logger.info("Заменено {} эмодзи на Premium версии", emoji_count)

            # Получаем entity канала через PeerChannel
            channel_entity = await self._get_channel_entity(channel_id)

            # Логируем обработанный текст для отладки
            logger.info("📝 Текст после обработки эмодзи (первые 300 символов):")
            logger.info(processed_text[:300] if len(processed_text) > 300 else processed_text)

            # Проверяем что parse_mode установлен
            logger.info("🔧 client.parse_mode = {}", type(self.client.parse_mode).__name__)

            # Публикуем в зависимости от типа медиа
            message = None

            if photo_path and Path(photo_path).exists():
                message = await self._send_photo(
                    channel_entity,
                    photo_path,
                    processed_text  # Форматированный текст, клиент сам распарсит
                )
            elif video_path and Path(video_path).exists():
                message = await self._send_video(
                    channel_entity,
                    video_path,
                    processed_text  # Форматированный текст
                )
            else:
                message = await self._send_text(
                    channel_entity,
                    processed_text  # Форматированный текст
                )

            if message:
                self._publish_count += 1

                # Закрепляем пост если требуется
                if pin_post:
                    await self._pin_message(channel_entity, message.id)

                logger.info(
                    "Пост опубликован через UserBot: channel={}, message_id={}",
                    channel_id, message.id
                )
                return message.id

            return None

        except FloodWaitError as e:
            logger.warning("FloodWait: ожидание {} секунд", e.seconds)
            await asyncio.sleep(e.seconds)
            return await self.publish_post(
                channel_id, text, photo_path, video_path, media_items, pin_post, add_footer
            )

        except ChannelPrivateError:
            logger.error("Канал {} приватный или недоступен", channel_id)
            return None

        except ChatWriteForbiddenError:
            logger.error("Нет прав на запись в канал {}", channel_id)
            return None

        except Exception as e:
            logger.error("Ошибка публикации через UserBot: {}", str(e))
            return None

    async def publish_album(
        self,
        channel_id,
        text: str,
        media_items: List[dict],
        pin_post: bool = False,
        add_footer: bool = True
    ) -> Optional[int]:
        """
        Опубликовать альбом (несколько медиа) в канал через UserBot

        Args:
            channel_id: ID канала (int) или username (str)
            text: Текст поста (caption для альбома)
            media_items: Список медиа [{"type": "photo"|"video", "path": "..."}]
            pin_post: Закрепить пост
            add_footer: Добавить футер к посту

        Returns:
            message_id первого сообщения альбома или None при ошибке
        """
        if not self.is_available:
            logger.error("UserbotPublisher недоступен")
            return None

        try:
            # Сначала добавляем футер
            full_text = text
            if add_footer:
                full_text = add_footer_to_post(text, parse_mode="Markdown")

            # Обрабатываем текст - заменяем эмодзи на Premium версии
            processor = await get_emoji_processor()
            processed_text, emoji_count = await processor.process_text(full_text)

            if emoji_count > 0:
                logger.info("Заменено {} эмодзи на Premium версии в альбоме", emoji_count)

            # Получаем entity канала
            channel_entity = await self._get_channel_entity(channel_id)

            # Собираем список файлов для альбома
            files = []
            for item in media_items:
                file_path = Path(item.get('path', ''))
                if file_path.exists():
                    files.append(str(file_path))
                else:
                    logger.warning("Файл не найден для альбома: {}", file_path)

            if len(files) < 2:
                logger.warning("Недостаточно файлов для альбома ({}), публикуем как обычный пост", len(files))
                if files:
                    # Определяем тип первого файла
                    first_item = media_items[0]
                    if first_item.get('type') == 'photo':
                        return await self.publish_post(
                            channel_id, text, photo_path=files[0], pin_post=pin_post, add_footer=add_footer
                        )
                    else:
                        return await self.publish_post(
                            channel_id, text, video_path=files[0], pin_post=pin_post, add_footer=add_footer
                        )
                return None

            logger.info("📎 Публикация альбома с {} медиа файлами", len(files))

            # Telethon поддерживает отправку списка файлов как альбома
            messages = await self.client.send_file(
                channel_entity,
                file=files,
                caption=processed_text  # Caption будет на первом элементе
            )

            if messages:
                self._publish_count += 1

                # messages может быть списком или одним сообщением
                if isinstance(messages, list):
                    first_message = messages[0]
                else:
                    first_message = messages

                # Закрепляем первое сообщение если требуется
                if pin_post:
                    await self._pin_message(channel_entity, first_message.id)

                logger.info(
                    "📎 Альбом опубликован через UserBot: channel={}, message_id={}, медиа={}",
                    channel_id, first_message.id, len(files)
                )
                return first_message.id

            return None

        except FloodWaitError as e:
            logger.warning("FloodWait при публикации альбома: ожидание {} секунд", e.seconds)
            await asyncio.sleep(e.seconds)
            return await self.publish_album(
                channel_id, text, media_items, pin_post, add_footer
            )

        except ChannelPrivateError:
            logger.error("Канал {} приватный или недоступен для альбома", channel_id)
            return None

        except ChatWriteForbiddenError:
            logger.error("Нет прав на запись альбома в канал {}", channel_id)
            return None

        except Exception as e:
            logger.error("Ошибка публикации альбома через UserBot: {}", str(e))
            return None

    async def _send_photo(
        self,
        entity,
        photo_path: str,
        caption: str
    ):
        """Отправить фото с подписью (parse_mode на клиенте обработает форматирование)"""
        try:
            return await self.client.send_file(
                entity,
                file=photo_path,
                caption=caption,
                force_document=False
            )
        except Exception as e:
            logger.error("Ошибка отправки фото: {}", str(e))
            raise

    async def _send_video(
        self,
        entity,
        video_path: str,
        caption: str
    ):
        """Отправить видео с подписью (parse_mode на клиенте обработает форматирование)"""
        try:
            return await self.client.send_file(
                entity,
                file=video_path,
                caption=caption,
                force_document=False,
                supports_streaming=True
            )
        except Exception as e:
            logger.error("Ошибка отправки видео: {}", str(e))
            raise

    async def _send_text(
        self,
        entity,
        text: str
    ):
        """Отправить текстовое сообщение (parse_mode на клиенте обработает форматирование)"""
        try:
            return await self.client.send_message(
                entity,
                message=text,
                link_preview=False  # Отключаем предпросмотр ссылок
            )
        except Exception as e:
            logger.error("Ошибка отправки сообщения: {}", str(e))
            raise

    async def _pin_message(self, entity, message_id: int) -> bool:
        """Закрепить сообщение"""
        try:
            await self.client.pin_message(entity, message_id, notify=False)
            logger.info("Сообщение {} закреплено", message_id)
            return True
        except Exception as e:
            logger.warning("Не удалось закрепить сообщение: {}", str(e))
            return False

    def _extract_channel_id(self, channel_id: int) -> int:
        """
        Извлечь чистый channel_id для PeerChannel

        Telegram API использует разные форматы ID:
        - Bot API / Config: -1001234567890 (с -100 префиксом)
        - PeerChannel: требует ПОЗИТИВНЫЙ ID без префикса (1234567890)

        Args:
            channel_id: ID канала в любом формате

        Returns:
            Позитивный channel_id для PeerChannel
        """
        # Если ID отрицательный с -100 префиксом — извлекаем чистый ID
        if channel_id < 0:
            # -1003167531927 -> "1003167531927" -> убираем "100" -> 3167531927
            str_id = str(abs(channel_id))
            if str_id.startswith("100") and len(str_id) > 3:
                return int(str_id[3:])
            return abs(channel_id)

        # Если ID уже положительный — возвращаем как есть
        return channel_id

    async def _get_channel_entity(self, channel_id):
        """
        Получить entity канала

        Args:
            channel_id: ID канала (int) или username (str, например "@Kpeezy4L")

        Returns:
            Entity канала для Telethon
        """
        # Если это username (строка) - используем напрямую
        if isinstance(channel_id, str):
            logger.info("Получение entity канала по username: {}", channel_id)
            return await self.client.get_entity(channel_id)

        pure_id = self._extract_channel_id(channel_id)

        # Используем кешированную entity если это целевой канал
        if self._target_entity and hasattr(self._target_entity, 'id'):
            if self._target_entity.id == pure_id:
                logger.info("Используем кешированную entity канала: {}",
                           getattr(self._target_entity, 'title', pure_id))
                return self._target_entity

        # Fallback: пробуем через PeerChannel
        logger.info("Получение entity канала: {} -> PeerChannel({})", channel_id, pure_id)
        peer = PeerChannel(channel_id=pure_id)
        return await self.client.get_entity(peer)

    async def send_test_message(
        self,
        channel_id,
        test_text: str = "Тестовое сообщение с Premium Emoji"
    ) -> Optional[int]:
        """
        Отправить тестовое сообщение для проверки работы

        Args:
            channel_id: ID канала (int) или username (str, например "@Kpeezy4L")
            test_text: Текст сообщения

        Returns:
            message_id или None
        """
        logger.info("Отправка тестового сообщения в канал {}", channel_id)
        return await self.publish_post(
            channel_id=channel_id,
            text=test_text,
            add_footer=False
        )

    @property
    def stats(self) -> dict:
        """Статистика публикаций"""
        return {
            "publish_count": self._publish_count,
            "is_available": self.is_available
        }


# Глобальный экземпляр публикатора
_userbot_publisher: Optional[UserbotPublisher] = None


async def get_userbot_publisher() -> Optional[UserbotPublisher]:
    """
    Получить экземпляр UserbotPublisher

    Returns:
        UserbotPublisher или None если недоступен
    """
    global _userbot_publisher

    if _userbot_publisher is not None and _userbot_publisher.is_available:
        return _userbot_publisher

    try:
        # Импортируем здесь чтобы избежать циклических импортов
        from src.userbot.client import get_userbot_client

        client_wrapper = await get_userbot_client()
        if client_wrapper and client_wrapper.client:
            _userbot_publisher = UserbotPublisher(client_wrapper.client)
            await _userbot_publisher.initialize()
            return _userbot_publisher

    except Exception as e:
        logger.error("Ошибка получения UserbotPublisher: {}", str(e))

    return None


async def initialize_userbot_publisher() -> bool:
    """
    Инициализировать UserbotPublisher

    Returns:
        True если инициализация успешна
    """
    publisher = await get_userbot_publisher()
    return publisher is not None and publisher.is_available


def reset_userbot_publisher() -> None:
    """
    Сбросить кеш UserbotPublisher

    Вызывается при сбросе сессии UserBot для того чтобы
    при следующем запросе создался новый экземпляр с новым клиентом
    """
    global _userbot_publisher

    if _userbot_publisher is not None:
        logger.info("🔄 Сброс кеша UserbotPublisher")
        _userbot_publisher = None
