"""
Обработчик новых сообщений из отслеживаемых каналов
Фильтрует, извлекает данные и сохраняет посты для дальнейшей обработки
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from collections import defaultdict
import json

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Сторонние библиотеки
from telethon import events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, DocumentAttributeVideo
from telethon.errors import FloodWaitError

# Локальные импорты
from src.userbot.filters import get_message_filters
from src.userbot.media import get_media_processor
from src.database.connection import get_db_connection, get_db_transaction
from src.database.models.post import Post, PostStatus
from src.database.models.channel import Channel
from src.utils.exceptions import MessageProcessingError, DatabaseError

# Настройка логгера модуля
logger = logger.bind(module="userbot_handler")


class NewMessageHandler:
    """
    Обработчик новых сообщений из Telegram каналов
    Фильтрует сообщения и сохраняет подходящие в БД для модерации
    """
    
    def __init__(self):
        """Инициализация обработчика"""
        self.message_filters = get_message_filters()
        self.processing_count = 0
        self.last_flood_wait = None
        
        # Хранение медиа-групп для обработки множественных медиа
        self.media_groups: Dict[int, Dict[str, Any]] = {}  # grouped_id -> group_data
        self.group_timers: Dict[int, asyncio.Task] = {}    # grouped_id -> task
        
        logger.debug("Инициализирован обработчик новых сообщений")
    
    async def handle_new_message(self, event: events.NewMessage.Event) -> None:
        """
        Главный обработчик нового сообщения
        
        Args:
            event: Событие нового сообщения от Telethon
        """
        try:
            message = event.message
            self.processing_count += 1
            
            # Правильное получение channel_id согласно документации
            channel_id = getattr(message.peer_id, 'channel_id', None)
            
            logger.info("📨 Получено новое сообщение {} из канала {}", 
                        message.id, channel_id or 'unknown')
            
            # Дополнительная проверка - фильтр уже проверил, но для надежности
            if not channel_id:
                logger.debug("Сообщение не из канала, пропускаем")
                return
            
            # Применяем дополнительные фильтры (базовые проверки)
            if not await self.message_filters.should_process_message(event):
                logger.debug("Сообщение {} не прошло фильтры", message.id)
                return
            
            # 🆕 ПРОВЕРЯЕМ GROUPED_ID ДЛЯ МНОЖЕСТВЕННЫХ МЕДИА
            if message.grouped_id:
                logger.info("📎 Сообщение {} является частью медиа-группы {}", 
                           message.id, message.grouped_id)
                await self._handle_grouped_message(event)
                return
            
            # Обрабатываем одиночное сообщение как обычно
            await self._process_single_message(event)
            
        except FloodWaitError as e:
            self.last_flood_wait = datetime.now()
            logger.warning("❌ Flood wait error, ждем {} секунд", e.seconds)
            await asyncio.sleep(e.seconds)
            
        except Exception as e:
            logger.error("❌ Ошибка обработки сообщения {}: {}", 
                        getattr(event.message, 'id', 'unknown'), str(e))
            logger.exception("Детали ошибки:")
    
    async def _process_single_message(self, event: events.NewMessage.Event) -> None:
        """
        Обработка одиночного сообщения (не в группе)
        
        Args:
            event: Событие сообщения
        """
        try:
            message = event.message
            
            # Извлекаем данные из сообщения
            post_data = await self._extract_message_data(event)
            if not post_data:
                logger.warning("Не удалось извлечь данные из сообщения {}", message.id)
                return
            
            # Сохраняем пост в БД
            post = await self._save_post_to_database(post_data)
            if not post:
                logger.error("Не удалось сохранить пост в БД")
                return
            
            # Загружаем и обрабатываем медиа через медиа процессор
            media_info = None
            media_processor = None
            if message.media:
                try:
                    # Получаем медиа процессор (нужен client)
                    client = event.client
                    media_processor = get_media_processor(client)
                    
                    if isinstance(message.media, MessageMediaPhoto):
                        # Загружаем фото
                        media_info = await media_processor.download_photo(
                            message.media, 
                            post.id
                        )
                        
                        if media_info:
                            # Обновляем информацию о фото в БД
                            await self._update_post_media_info(post.id, media_info, 'photo')
                            logger.info("Фото загружено и обработано для поста {}", post.id)
                        else:
                            logger.warning("Не удалось загрузить фото для поста {}", post.id)
                    
                    elif isinstance(message.media, MessageMediaDocument):
                        # Проверяем что это видео
                        document = message.media.document
                        is_video = False
                        
                        if hasattr(document, 'attributes'):
                            for attr in document.attributes:
                                if isinstance(attr, DocumentAttributeVideo):
                                    is_video = True
                                    break
                        
                        if is_video:
                            # Загружаем видео
                            media_info = await media_processor.download_video(
                                message.media,
                                post.id
                            )
                            
                            if media_info:
                                # Обновляем информацию о видео в БД
                                await self._update_post_media_info(post.id, media_info, 'video')
                                logger.info("Видео загружено и обработано для поста {}", post.id)
                            else:
                                logger.warning("Не удалось загрузить видео для поста {}", post.id)
                        else:
                            logger.debug("Документ не является видео для поста {}", post.id)
                    
                except Exception as e:
                    logger.error("Ошибка обработки медиа для поста {}: {}", post.id, str(e))
            
            # Обновляем статистику канала
            await self._update_channel_stats(post.channel_id)
            
            # Обновляем last_message_id для канала
            await self._update_channel_last_message_id(post.channel_id, post.message_id)
            
            logger.info("Новый пост сохранен для модерации: канал {}, сообщение {}, ID поста {}", 
                       post.channel_id, post.message_id, post.id)
            
            # Отправляем уведомление о новом посте БЕЗ AI анализа
            await self._send_notification_to_owner(post, media_processor)
            
        except Exception as e:
            logger.error("Ошибка обработки одиночного сообщения {}: {}", message.id, str(e))
            raise
    
    async def _handle_grouped_message(self, event: events.NewMessage.Event) -> None:
        """
        Обработка сообщения из медиа-группы
        
        Args:
            event: Событие сообщения
        """
        try:
            message = event.message
            grouped_id = message.grouped_id
            
            # Если группа еще не создана, создаем её
            if grouped_id not in self.media_groups:
                self.media_groups[grouped_id] = {
                    'messages': [],
                    'channel_id': getattr(message.peer_id, 'channel_id', None),
                    'created_at': datetime.now()
                }
                logger.info("📁 Создана новая медиа-группа {}", grouped_id)
            
            # Добавляем сообщение в группу
            self.media_groups[grouped_id]['messages'].append(event)
            
            logger.info("📎 Добавлено сообщение {} в медиа-группу {} (всего: {})", 
                       message.id, grouped_id, len(self.media_groups[grouped_id]['messages']))
            
            # Отменяем предыдущий таймер если есть
            if grouped_id in self.group_timers:
                self.group_timers[grouped_id].cancel()
            
            # Устанавливаем новый таймер на 3 секунды
            # Это позволит собрать все сообщения группы
            self.group_timers[grouped_id] = asyncio.create_task(
                self._process_media_group_delayed(grouped_id)
            )
            
        except Exception as e:
            logger.error("Ошибка обработки группированного сообщения: {}", str(e))
    
    async def _process_media_group_delayed(self, grouped_id: int) -> None:
        """
        Обработка медиа-группы с задержкой
        
        Args:
            grouped_id: ID медиа-группы
        """
        try:
            # Ждем 3 секунды для сбора всех сообщений группы
            await asyncio.sleep(3.0)
            
            if grouped_id not in self.media_groups:
                logger.warning("Медиа-группа {} исчезла из очереди", grouped_id)
                return
            
            group_data = self.media_groups[grouped_id]
            messages = group_data['messages']
            
            logger.info("🔄 Обработка медиа-группы {} с {} сообщениями", 
                       grouped_id, len(messages))
            
            # Берем первое сообщение как основное (обычно содержит текст)
            main_event = messages[0]
            main_message = main_event.message
            
            # Извлекаем данные из основного сообщения
            post_data = await self._extract_message_data(main_event)
            if not post_data:
                logger.warning("Не удалось извлечь данные из основного сообщения группы {}", grouped_id)
                return
            
            # Добавляем информацию о медиа-группе в пост
            post_data['ai_analysis'] = f"Медиа-группа {grouped_id} с {len(messages)} элементами"
            
            # Сохраняем пост в БД
            post = await self._save_post_to_database(post_data)
            if not post:
                logger.error("Не удалось сохранить медиа-группу в БД")
                return
            
            # Обрабатываем все медиа файлы из группы
            media_processor = None
            processed_media_count = 0
            
            for i, msg_event in enumerate(messages):
                msg = msg_event.message
                
                if not msg.media:
                    continue
                
                try:
                    # Инициализируем медиа процессор если еще не создан
                    if not media_processor:
                        media_processor = get_media_processor(msg_event.client)
                    
                    # Создаем уникальный суффикс для файлов из группы
                    file_suffix = f"_group_{i + 1}"
                    
                    if isinstance(msg.media, MessageMediaPhoto):
                        # Загружаем фото
                        media_info = await media_processor.download_photo(
                            msg.media,
                            post.id,
                            file_suffix=file_suffix
                        )

                        if media_info:
                            # Передаём позицию для сохранения в альбоме
                            await self._update_post_media_info(post.id, media_info, 'photo', position=i)
                            processed_media_count += 1
                            logger.info("📸 Фото {} загружено для медиа-группы {}", i + 1, grouped_id)

                    elif isinstance(msg.media, MessageMediaDocument):
                        # Проверяем что это видео
                        document = msg.media.document
                        is_video = False

                        if hasattr(document, 'attributes'):
                            for attr in document.attributes:
                                if isinstance(attr, DocumentAttributeVideo):
                                    is_video = True
                                    break

                        if is_video:
                            # Загружаем видео
                            media_info = await media_processor.download_video(
                                msg.media,
                                post.id,
                                file_suffix=file_suffix
                            )

                            if media_info:
                                # Передаём позицию для сохранения в альбоме
                                await self._update_post_media_info(post.id, media_info, 'video', position=i)
                                processed_media_count += 1
                                logger.info("🎥 Видео {} загружено для медиа-группы {}", i + 1, grouped_id)
                
                except Exception as e:
                    logger.error("Ошибка обработки медиа {} из группы {}: {}", i + 1, grouped_id, str(e))
                    continue
            
            logger.info("✅ Медиа-группа {} обработана: {} из {} медиа файлов", 
                       grouped_id, processed_media_count, len(messages))
            
            # Обновляем статистику канала
            await self._update_channel_stats(post.channel_id)
            
            # Используем ID первого сообщения как last_message_id
            await self._update_channel_last_message_id(post.channel_id, main_message.id)
            
            logger.info("📝 Медиа-группа сохранена как пост: ID {}, медиа файлов: {}", 
                       post.id, processed_media_count)
            
            # Отправляем уведомление о новом посте
            await self._send_notification_to_owner(post, media_processor)
            
        except Exception as e:
            logger.error("Ошибка обработки медиа-группы {}: {}", grouped_id, str(e))
        
        finally:
            # Очищаем данные группы
            if grouped_id in self.media_groups:
                del self.media_groups[grouped_id]
            if grouped_id in self.group_timers:
                del self.group_timers[grouped_id]
            
            logger.debug("🗑️ Данные медиа-группы {} очищены", grouped_id)
    
    async def _extract_formatted_text_from_message(self, event) -> str:
        """
        Извлечь текст из сообщения Telegram
        
        Args:
            event: Событие сообщения Telethon с доступом к client
            
        Returns:
            Текст сообщения
        """
        try:
            message = event.message
            
            # Простое извлечение текста из сообщения
            text = message.message if hasattr(message, 'message') and message.message else ""
            
            if not text and hasattr(message, 'text') and message.text:
                text = message.text
                
            logger.debug("Извлечен текст из сообщения {}: {} символов", 
                        message.id, len(text) if text else 0)
            
            return text or ""
            
        except Exception as e:
            logger.error("Ошибка извлечения текста из сообщения: {}", str(e))
            return ""
    
    async def _extract_message_data(self, event: events.NewMessage.Event) -> Optional[dict]:
        """
        Извлечь данные из сообщения для сохранения
        
        Args:
            event: Событие сообщения
            
        Returns:
            Словарь с данными поста или None при ошибке
        """
        try:
            message = event.message
            
            # Базовые данные согласно актуальной документации
            channel_id = int(f"-100{message.peer_id.channel_id}")
            message_id = message.id
            
            # Извлекаем текст с сохранением правильного форматирования
            # Используем унифицированный подход с get_messages() (как в парсинге ссылок)
            original_text = await self._extract_formatted_text_from_message(event)
            
            # 🔍 ДЕБАГ ЛОГ: Полный исходный текст поста
            logger.debug("📝 ИСХОДНЫЙ ТЕКСТ ПОСТА (канал={}, сообщение={}): {}", 
                        channel_id, message_id, repr(original_text))
            
            # Проверяем наличие медиа (file_id будет установлен позже в media_processor)
            has_photo = bool(message.media and isinstance(message.media, MessageMediaPhoto))
            has_video = False
            
            if message.media and isinstance(message.media, MessageMediaDocument):
                # Проверяем что документ содержит видео
                document = message.media.document
                if hasattr(document, 'attributes'):
                    for attr in document.attributes:
                        if isinstance(attr, DocumentAttributeVideo):
                            has_video = True
                            break
            
            logger.debug("Сообщение содержит медиа - фото: {}, видео: {}", has_photo, has_video)
            
            # Создаем ссылку на оригинальный пост
            # Для канала -1002797787404 нужно получить 2797787404
            clean_channel_id = str(abs(channel_id))[3:]  # Убираем -100 (3 символа, не 4!)
            source_link = f"https://t.me/c/{clean_channel_id}/{message_id}"

            # Извлекаем ссылки из сообщения (entities)
            extracted_links_json = None
            try:
                from src.userbot.link_extractor import get_link_extractor
                import json

                link_extractor = get_link_extractor()
                extracted_links = link_extractor.extract_links(message)

                if extracted_links:
                    links_data = link_extractor.to_json_list(extracted_links)
                    extracted_links_json = json.dumps(links_data, ensure_ascii=False)
                    logger.debug("Извлечено {} ссылок из поста {}", len(extracted_links), message_id)

            except Exception as e:
                logger.error("Ошибка извлечения ссылок из поста: {}", str(e))

            post_data = {
                "channel_id": channel_id,
                "message_id": message_id,
                "original_text": original_text,
                "photo_file_id": None,  # Будет установлен позже в media_processor
                "source_link": source_link,
                "status": PostStatus.PENDING,
                "extracted_links": extracted_links_json
            }

            logger.debug("Извлечены данные поста: канал={}, сообщение={}, фото={}, ссылок={}",
                        channel_id, message_id, "есть" if has_photo else "нет",
                        len(extracted_links) if extracted_links else 0)
            
            return post_data
            
        except Exception as e:
            logger.error("Ошибка извлечения данных сообщения: {}", str(e))
            return None
    
    async def _save_post_to_database(self, post_data: dict) -> Optional[Post]:
        """
        Сохранить пост в базе данных
        
        Args:
            post_data: Данные поста
            
        Returns:
            Созданный объект Post или None при ошибке
        """
        try:
            async with get_db_transaction() as conn:
                # Проверяем на дубликаты еще раз
                cursor = await conn.execute(
                    "SELECT id FROM posts WHERE channel_id = ? AND message_id = ?",
                    (post_data["channel_id"], post_data["message_id"])
                )
                existing = await cursor.fetchone()
                
                if existing:
                    logger.debug("Пост уже существует в БД: {}", existing[0])
                    return None
                
                # Вставляем новый пост
                cursor = await conn.execute(
                    """INSERT INTO posts
                       (channel_id, message_id, original_text, photo_file_id,
                        source_link, status, extracted_links, created_at, created_date)
                       VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                    (
                        post_data["channel_id"],
                        post_data["message_id"],
                        post_data["original_text"],
                        post_data["photo_file_id"],
                        post_data["source_link"],
                        post_data["status"].value,
                        post_data.get("extracted_links")
                    )
                )
                
                post_id = cursor.lastrowid
                
                # Создаем объект Post
                post = Post(
                    id=post_id,
                    **post_data
                )
                
                logger.debug("Пост сохранен в БД с ID: {}", post_id)
                return post
                
        except Exception as e:
            logger.error("Ошибка сохранения поста в БД: {}", str(e))
            raise DatabaseError(f"Не удалось сохранить пост: {str(e)}")
    
    async def _update_channel_stats(self, channel_id: int) -> None:
        """
        Обновить статистику канала
        
        Args:
            channel_id: ID канала
        """
        try:
            async with get_db_connection() as conn:
                # Увеличиваем счетчик обработанных постов
                await conn.execute(
                    """UPDATE channels 
                       SET posts_processed = posts_processed + 1,
                           updated_at = datetime('now')
                       WHERE channel_id = ?""",
                    (channel_id,)
                )
                await conn.commit()
                
                logger.debug("Обновлена статистика канала {}", channel_id)
                
        except Exception as e:
            logger.error("Ошибка обновления статистики канала {}: {}", channel_id, str(e))
            # Не блокируем основной процесс из-за ошибки статистики
    
    async def _update_channel_last_message_id(self, channel_id: int, message_id: int) -> None:
        """
        Обновить ID последнего сообщения в канале
        
        Args:
            channel_id: ID канала
            message_id: ID последнего сообщения
        """
        try:
            async with get_db_connection() as conn:
                await conn.execute(
                    """UPDATE channels 
                       SET last_message_id = CASE 
                           WHEN last_message_id < ? THEN ? 
                           ELSE last_message_id 
                       END,
                       updated_at = datetime('now')
                       WHERE channel_id = ?""",
                    (message_id, message_id, channel_id)
                )
                await conn.commit()
                
                logger.debug("Обновлен last_message_id для канала {}: {}", channel_id, message_id)
                
        except Exception as e:
            logger.error("Ошибка обновления last_message_id: {}", str(e))
    
    async def _update_post_media_info(self, post_id: int, media_info: dict, media_type: str, position: int = 0) -> None:
        """
        Обновить информацию о медиа для поста (добавить в media_items)

        Args:
            post_id: ID поста
            media_info: Информация о медиа файле
            media_type: Тип медиа ('photo' или 'video')
            position: Позиция медиа в альбоме (0-based)
        """
        try:
            # Определяем путь к файлу
            file_path = media_info.get("photo_path") if media_type == 'photo' else media_info.get("video_path")

            if not file_path:
                logger.warning("Путь к файлу не найден для медиа типа {} поста {}", media_type, post_id)
                return

            # Добавляем медиа в список media_items
            await self._add_media_to_post(post_id, media_type, file_path, position)

            # Для обратной совместимости: первый элемент также сохраняем в старые поля
            if position == 0:
                async with get_db_connection() as conn:
                    if media_type == 'photo':
                        await conn.execute(
                            """UPDATE posts
                               SET photo_path = ?,
                                   media_type = ?
                               WHERE id = ? AND photo_path IS NULL""",
                            (file_path, media_type, post_id)
                        )
                    elif media_type == 'video':
                        await conn.execute(
                            """UPDATE posts
                               SET video_path = ?,
                                   media_type = ?,
                                   video_duration = ?,
                                   video_width = ?,
                                   video_height = ?
                               WHERE id = ? AND video_path IS NULL""",
                            (
                                file_path,
                                media_type,
                                media_info.get("duration"),
                                media_info.get("width"),
                                media_info.get("height"),
                                post_id
                            )
                        )
                    await conn.commit()

            logger.debug("Обновлена информация о {} для поста {} (позиция {})", media_type, post_id, position)

        except Exception as e:
            logger.error("Ошибка обновления информации о медиа: {}", str(e))

    async def _add_media_to_post(self, post_id: int, media_type: str, file_path: str, position: int) -> None:
        """
        Добавить медиа элемент в список media_items поста

        Args:
            post_id: ID поста
            media_type: Тип медиа ('photo' или 'video')
            file_path: Путь к файлу
            position: Позиция в альбоме (0-based)
        """
        try:
            async with get_db_connection() as conn:
                # Получаем текущий media_items
                cursor = await conn.execute(
                    "SELECT media_items FROM posts WHERE id = ?",
                    (post_id,)
                )
                row = await cursor.fetchone()

                if not row:
                    logger.error("Пост {} не найден для добавления медиа", post_id)
                    return

                current_items = row[0]

                # Парсим существующий JSON или создаем новый список
                if current_items:
                    try:
                        items = json.loads(current_items)
                    except json.JSONDecodeError:
                        items = []
                else:
                    items = []

                # Проверяем нет ли уже такого элемента (по пути)
                for item in items:
                    if item.get('path') == file_path:
                        logger.debug("Медиа {} уже добавлен в пост {}", file_path, post_id)
                        return

                # Добавляем новый элемент
                new_item = {
                    "type": media_type,
                    "path": file_path,
                    "position": position
                }
                items.append(new_item)

                # Сортируем по позиции
                items = sorted(items, key=lambda x: x.get('position', 0))

                # Сохраняем обратно в БД
                media_items_json = json.dumps(items, ensure_ascii=False)
                await conn.execute(
                    "UPDATE posts SET media_items = ? WHERE id = ?",
                    (media_items_json, post_id)
                )
                await conn.commit()

                logger.debug("Добавлен медиа элемент в пост {}: {} (позиция {}, всего {})",
                            post_id, media_type, position, len(items))

        except Exception as e:
            logger.error("Ошибка добавления медиа в пост {}: {}", post_id, str(e))
    
    async def _send_notification_to_owner(self, post: Post, media_processor) -> None:
        """
        Отправить уведомление владельцу о новом посте БЕЗ AI анализа
        
        Args:
            post: Объект поста
            media_processor: Медиа процессор (опционально)
        """
        try:
            from src.bot.main import get_bot_instance
            from src.bot.keyboards.inline import get_post_moderation_keyboard
            from src.utils.config import get_config
            
            config = get_config()
            bot = get_bot_instance()
            
            logger.info("Отправка уведомления о новом посте {} владельцу", post.unique_id)

            # Создаем уведомление с оригинальным текстом (БЕЗ AI анализа)
            notification_text = self._format_new_post_notification(post)

            # Получаем клавиатуру модерации
            keyboard = get_post_moderation_keyboard(post.id)

            # Проверяем наличие альбома (более 1 медиа)
            if post.has_album:
                await self._send_album_notification(bot, config, post, keyboard)
                return

            # Если есть медиа, отправляем с медиа (одиночное)
            if post.has_photo:
                try:
                    from pathlib import Path
                    from aiogram.types import FSInputFile
                    
                    # Проверяем что файл фото существует
                    if not post.photo_path:
                        logger.warning("Путь к фото не установлен для поста {}, отправляем как текст", post.id)
                        await self._send_text_notification(bot, config, post, keyboard, notification_text)
                        return
                    
                    photo_path = Path(post.photo_path)
                    if not photo_path.exists():
                        logger.warning("Файл фото не найден: {}, отправляем как текст", photo_path)
                        await self._send_text_notification(bot, config, post, keyboard, notification_text)
                        return
                    
                    # Создаем краткое caption для фото с оригинальным текстом
                    caption = self._format_post_caption_with_original_text(post)
                    
                    # Telegram ограничение: 1024 символа для caption
                    if len(caption) > 1024:
                        # НЕ обрезаем HTML (ломает теги), показываем краткую информацию
                        from src.utils.html_formatter import bold
                        caption = f"""📝 {bold(f'Новый пост #{post.id}')}
📺 Канал: {post.source_channel or 'неизвестно'}

📄 Текст слишком длинный - используйте кнопку ниже ⬇️"""
                        
                        # Добавляем кнопку "Показать полный пост"
                        from aiogram.types import InlineKeyboardButton
                        show_post_button = InlineKeyboardButton(
                            text="📄 Показать полный пост",
                            callback_data=f"show_full_post_{post.id}"
                        )
                        keyboard.inline_keyboard.insert(0, [show_post_button])
                    
                    # Отправляем фото как локальный файл
                    photo_input = FSInputFile(photo_path)
                    await bot.send_photo(
                        chat_id=config.OWNER_ID,
                        photo=photo_input,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    
                    logger.info("🖼️ Уведомление о новом посте с фото {} отправлено владельцу", post.id)
                    
                except Exception as photo_error:
                    logger.warning("Ошибка отправки фото для поста {}: {}, отправляем как текст", 
                                 post.id, str(photo_error))
                    # Отправляем как текстовое уведомление
                    await self._send_text_notification(bot, config, post, keyboard, notification_text)
            
            elif post.has_video:
                try:
                    from pathlib import Path
                    from aiogram.types import FSInputFile
                    
                    # Проверяем что файл видео существует
                    if not post.video_path:
                        logger.warning("Путь к видео не установлен для поста {}, отправляем как текст", post.id)
                        await self._send_text_notification(bot, config, post, keyboard, notification_text)
                        return
                    
                    video_path = Path(post.video_path)
                    if not video_path.exists():
                        logger.warning("Файл видео не найден: {}, отправляем как текст", video_path)
                        await self._send_text_notification(bot, config, post, keyboard, notification_text)
                        return
                    
                    # Создаем краткое caption для видео с оригинальным текстом
                    caption = self._format_post_caption_with_original_text(post)
                    
                    # Telegram ограничение: 1024 символа для caption
                    if len(caption) > 1024:
                        # НЕ обрезаем HTML (ломает теги), показываем краткую информацию
                        from src.utils.html_formatter import bold
                        caption = f"""📝 {bold(f'Новый пост #{post.id}')}
📺 Канал: {post.source_channel or 'неизвестно'}

📄 Текст слишком длинный - используйте кнопку ниже ⬇️"""
                        
                        # Добавляем кнопку "Показать полный пост"
                        from aiogram.types import InlineKeyboardButton
                        show_post_button = InlineKeyboardButton(
                            text="📄 Показать полный пост",
                            callback_data=f"show_full_post_{post.id}"
                        )
                        keyboard.inline_keyboard.insert(0, [show_post_button])
                    
                    # Отправляем видео как локальный файл
                    video_input = FSInputFile(video_path)
                    await bot.send_video(
                        chat_id=config.OWNER_ID,
                        video=video_input,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    
                    logger.info("🎥 Уведомление о новом посте с видео {} отправлено владельцу", post.id)
                    
                except Exception as video_error:
                    logger.warning("Ошибка отправки видео для поста {}: {}, отправляем как текст", 
                                 post.id, str(video_error))
                    # Отправляем как текстовое уведомление
                    await self._send_text_notification(bot, config, post, keyboard, notification_text)
            else:
                # Пост без медиа - отправляем текстовое уведомление
                await self._send_text_notification(bot, config, post, keyboard, notification_text)
                
        except Exception as e:
            logger.error("Ошибка отправки уведомления о новом посте {}: {}", post.unique_id, str(e))
            # Не блокируем основной процесс из-за ошибки уведомления
    
    def _format_new_post_notification(self, post: Post) -> str:
        """Форматировать уведомление о новом посте с оригинальным текстом"""
        try:
            from datetime import datetime
            
            # Заголовок уведомления
            header = f"""🆕 <b>Новый пост для модерации!</b>

📝 Пост на модерации #{post.id}

📺 Канал: ID {post.channel_id}
🕐 Получен: {datetime.now().strftime('%d.%m.%Y %H:%M')}

📄 <b>Оригинальный текст поста:</b>
{post.original_text or "Нет текста"}"""
            
            # Добавляем информацию о медиа если есть
            if post.has_photo:
                header += "\n\n🖼️ <b>Содержит изображение</b>"
            elif post.has_video:
                video_info = "\n\n🎥 <b>Содержит видео"
                if post.video_duration:
                    video_info += f" ({post.media_duration_formatted})"
                video_info += "</b>"
                header += video_info
            
            # Добавляем ссылку на источник
            if post.source_link:
                header += f"\n\n🔗 <a href='{post.source_link}'>Ссылка на оригинал</a>"
            
            header += "\n\n⚡️ <b>Нажмите 'Рестайлинг' для AI обработки</b>"
            
            return header
            
        except Exception as e:
            logger.error("Ошибка форматирования уведомления о новом посте: {}", str(e))
            return f"❌ Ошибка отображения поста #{post.id if post else 'неизвестно'}"
    
    def _format_post_caption_with_original_text(self, post: Post) -> str:
        """Форматировать краткое caption для фото с оригинальным текстом"""
        try:
            from datetime import datetime
            
            # Краткий заголовок
            header = f"""📝 <b>Пост #{post.id}</b>
📺 Канал: ID {post.channel_id}
🕐 {datetime.now().strftime('%d.%m %H:%M')}

📄 <b>Оригинальный текст:</b>"""
            
            # Рассчитываем доступное место для текста (1024 - header - запас)
            available_length = 1024 - len(header) - 80
            
            original_text = post.original_text or "Нет текста"
            if len(original_text) > available_length:
                original_text = original_text[:available_length] + "..."
            
            caption = f"{header}\n{original_text}"
            
            # Добавляем призыв к действию
            if len(caption) < 950:
                caption += "\n\n⚡️ <b>Нажмите 'Рестайлинг' для AI обработки</b>"
            
            return caption
            
        except Exception as e:
            logger.error("Ошибка форматирования caption для поста: {}", str(e))
            return f"❌ Ошибка отображения поста #{post.id if post else 'неизвестно'}"
    
    async def _send_text_notification(self, bot, config, post: Post, keyboard, notification_text: str) -> None:
        """Отправить текстовое уведомление о новом посте"""
        try:
            # Проверяем длину сообщения (лимит Telegram: 4096 символов для текста)
            if len(notification_text) > 4048:
                logger.info("Текстовое уведомление слишком длинное ({} символов), показываю краткую версию", 
                           len(notification_text))
                
                # НЕ обрезаем HTML (ломает теги), показываем краткую информацию  
                from src.utils.html_formatter import bold
                truncated_text = f"""📄 {bold('Уведомление о новом посте слишком длинное')}

📊 Размер уведомления: {len(notification_text)} символов
⬇️ Используйте кнопку 'Показать пост' для просмотра полного текста"""
                
                # Добавляем кнопку "Показать полный пост"
                from aiogram.types import InlineKeyboardButton
                show_post_button = InlineKeyboardButton(
                    text="📄 Показать полный пост",
                    callback_data=f"show_full_post_{post.id}"
                )
                keyboard.inline_keyboard.insert(0, [show_post_button])
                
                notification_text = truncated_text
            
            await bot.send_message(
                chat_id=config.OWNER_ID,
                text=notification_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            logger.info("📝 Текстовое уведомление о новом посте {} отправлено владельцу", post.id)
            
        except Exception as e:
            logger.error("Ошибка отправки текстового уведомления: {}", str(e))

    async def _send_album_notification(self, bot, config, post: Post, keyboard) -> None:
        """
        Отправить уведомление о новом посте с альбомом (media_group)

        Args:
            bot: Экземпляр бота
            config: Конфигурация
            post: Объект поста с альбомом
            keyboard: Клавиатура модерации
        """
        try:
            from pathlib import Path
            from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo

            media_items = post.get_media_items()
            if not media_items:
                logger.warning("Нет медиа элементов для альбома поста {}", post.id)
                await self._send_text_notification(
                    bot, config, post, keyboard,
                    self._format_new_post_notification(post)
                )
                return

            # Формируем caption для первого элемента
            caption = self._format_post_caption_with_original_text(post)

            # Ограничение Telegram на caption в media_group: 1024 символа
            if len(caption) > 1024:
                from src.utils.html_formatter import bold
                caption = f"""📝 {bold(f'Новый альбом #{post.id}')} ({len(media_items)} медиа)
📺 Канал: ID {post.channel_id}

📄 Текст слишком длинный - см. кнопку ниже"""

            # Собираем список InputMedia
            media_group = []
            for i, item in enumerate(media_items):
                file_path = Path(item.get('path', ''))
                media_type = item.get('type', 'photo')

                if not file_path.exists():
                    logger.warning("Файл не найден для альбома: {}", file_path)
                    continue

                file_input = FSInputFile(file_path)

                # Caption только у первого элемента
                item_caption = caption if i == 0 else None
                parse_mode = "HTML" if i == 0 else None

                if media_type == 'photo':
                    media_group.append(InputMediaPhoto(
                        media=file_input,
                        caption=item_caption,
                        parse_mode=parse_mode
                    ))
                elif media_type == 'video':
                    media_group.append(InputMediaVideo(
                        media=file_input,
                        caption=item_caption,
                        parse_mode=parse_mode
                    ))

            if len(media_group) < 2:
                # Если осталось меньше 2 элементов - отправляем как обычный пост
                logger.warning("Недостаточно медиа для альбома поста {}, отправляем как обычный", post.id)
                notification_text = self._format_new_post_notification(post)
                await self._send_text_notification(bot, config, post, keyboard, notification_text)
                return

            # Отправляем альбом
            await bot.send_media_group(
                chat_id=config.OWNER_ID,
                media=media_group
            )

            # Кнопки отправляем отдельным сообщением (media_group не поддерживает reply_markup)
            from src.utils.html_formatter import bold
            buttons_text = f"""📎 {bold(f'Альбом #{post.id}')} ({len(media_group)} медиа)

⚡️ Выберите действие:"""

            await bot.send_message(
                chat_id=config.OWNER_ID,
                text=buttons_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

            logger.info("📎 Уведомление об альбоме {} ({} медиа) отправлено владельцу",
                       post.id, len(media_group))

        except Exception as e:
            logger.error("Ошибка отправки альбома для поста {}: {}", post.id, str(e))
            # Fallback на текстовое уведомление
            try:
                notification_text = self._format_new_post_notification(post)
                await self._send_text_notification(bot, config, post, keyboard, notification_text)
            except Exception as fallback_error:
                logger.error("Fallback также не удался: {}", str(fallback_error))

    def get_statistics(self) -> dict:
        """Получить статистику обработчика"""
        return {
            "processed_messages": self.processing_count,
            "last_flood_wait": self.last_flood_wait,
            "status": "active" if self.processing_count > 0 else "idle"
        }


# Глобальный экземпляр обработчика
_new_message_handler: Optional[NewMessageHandler] = None


def get_new_message_handler() -> NewMessageHandler:
    """Получить глобальный экземпляр обработчика"""
    global _new_message_handler
    
    if _new_message_handler is None:
        _new_message_handler = NewMessageHandler()
    
    return _new_message_handler


async def register_message_handlers(client) -> None:
    """
    Зарегистрировать обработчики сообщений в Telethon клиенте
    
    Args:
        client: Экземпляр Telethon клиента
    """
    handler = get_new_message_handler()
    message_filters = get_message_filters()
    
    # Получаем список отслеживаемых каналов
    monitored_channels = await message_filters.get_monitored_channels()
    
    if not monitored_channels:
        logger.warning("Нет активных каналов для мониторинга")
        return
    
    logger.info("Регистрация обработчиков для {} каналов", len(monitored_channels))
    
    # Согласно актуальной документации Telethon, создаем правильный фильтр событий
    def channel_and_media_filter(event):
        """Комплексный фильтр для каналов и медиа"""
        try:
            message = event.message
            
            logger.debug("🎯 Telethon событие: сообщение {} от {}", message.id, getattr(message.peer_id, 'channel_id', 'unknown'))
            
            # Проверяем что это сообщение из канала
            if not hasattr(message.peer_id, 'channel_id'):
                logger.debug("❌ Сообщение не из канала")
                return False
            
            # Получаем полный ID канала
            full_channel_id = int(f"-100{message.peer_id.channel_id}")
            
            # Проверяем что канал отслеживается
            if full_channel_id not in monitored_channels:
                logger.debug("❌ Канал {} не отслеживается", full_channel_id)
                return False
            
            # Принимаем любые сообщения (с медиа и текстовые)
            # Фильтрация медиа будет происходить в should_process_message()
            logger.debug("✅ Событие прошло фильтр Telethon")
            
            return True
            
        except Exception as e:
            logger.debug("Ошибка в фильтре событий: {}", str(e))
            return False
    
    # Регистрируем обработчик согласно актуальной документации
    # Используем правильный синтаксис events.NewMessage с func parameter
    client.add_event_handler(
        handler.handle_new_message,
        events.NewMessage(func=channel_and_media_filter)
    )
    
    logger.info("Обработчики сообщений зарегистрированы успешно")