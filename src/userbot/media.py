"""
Модуль работы с медиа файлами Telethon
Загрузка, сохранение и обработка фото из сообщений
"""

import asyncio
import os
from pathlib import Path
from typing import Optional, Dict, Any, Union
from io import BytesIO

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Сторонние библиотеки
from telethon import TelegramClient
from telethon.tl.types import (
    MessageMediaPhoto,
    MessageMediaDocument,
    Photo,
    PhotoSize,
    PhotoSizeEmpty,
    PhotoSizeProgressive,
    PhotoStrippedSize,
    Document,
    DocumentAttributeVideo,
    DocumentAttributeFilename
)
from telethon.errors import (
    FloodWaitError,
    FileReferenceExpiredError,
    MediaEmptyError
)
from PIL import Image

# Локальные импорты
from src.utils.config import get_config
from src.utils.exceptions import MediaProcessingError

# Настройка логгера модуля
logger = logger.bind(module="userbot_media")


class TelethonMediaProcessor:
    """
    Класс для обработки медиа файлов из Telethon
    Загружает, сохраняет и обрабатывает фото согласно требованиям
    """
    
    def __init__(self, client: TelegramClient):
        """
        Инициализация процессора медиа
        
        Args:
            client: Экземпляр Telethon клиента
        """
        self.client = client
        self.config = get_config()
        
        # Создаем директории для медиа
        self.media_dir = Path("data/media")
        self.media_dir.mkdir(parents=True, exist_ok=True)
        
        self.photos_dir = self.media_dir / "photos"
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        
        self.videos_dir = self.media_dir / "videos"
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        
        self.thumbnails_dir = self.media_dir / "thumbnails"  
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug("Инициализирован процессор медиа")
    
    async def download_photo(
        self,
        message_media: MessageMediaPhoto,
        post_id: int,
        max_retries: int = 3,
        file_suffix: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Загрузить фото из сообщения

        Args:
            message_media: Медиа объект сообщения
            post_id: ID поста для именования файлов
            max_retries: Количество повторных попыток
            file_suffix: Суффикс для имени файла (для медиа-групп)

        Returns:
            Словарь с информацией о загруженном фото или None
        """
        for attempt in range(max_retries):
            try:
                logger.debug("Загрузка фото для поста {} (попытка {})", post_id, attempt + 1)
                
                # Проверяем что медиа содержит фото
                if not isinstance(message_media, MessageMediaPhoto):
                    logger.error("Медиа не является фото: {}", type(message_media))
                    return None
                
                photo = message_media.photo
                if not isinstance(photo, Photo):
                    logger.error("Неверный тип фото: {}", type(photo))
                    return None
                
                # Получаем лучшее качество фото
                photo_size = self._get_best_photo_size(photo)
                if not photo_size:
                    logger.error("Не найден подходящий размер фото")
                    return None
                
                # Создаем имена файлов (с учётом суффикса для медиа-групп)
                photo_filename = f"photo_{post_id}_{photo.id}{file_suffix}.jpg"
                thumbnail_filename = f"thumb_{post_id}_{photo.id}{file_suffix}.jpg"
                
                photo_path = self.photos_dir / photo_filename
                thumbnail_path = self.thumbnails_dir / thumbnail_filename
                
                # Загружаем оригинальное фото
                photo_bytes = await self.client.download_media(
                    message_media,
                    file=BytesIO()
                )
                
                if not photo_bytes:
                    logger.error("Не удалось загрузить фото")
                    return None
                
                # Сохраняем оригинальное фото
                photo_bytes.seek(0)
                with open(photo_path, 'wb') as f:
                    f.write(photo_bytes.read())
                
                # Создаем миниатюру
                thumbnail_info = await self._create_thumbnail(
                    photo_bytes, thumbnail_path
                )
                
                # Получаем информацию о фото
                photo_info = self._analyze_photo(photo_path)
                
                result = {
                    "photo_id": str(photo.id),
                    "access_hash": str(photo.access_hash),
                    "file_reference": photo.file_reference.hex() if photo.file_reference else None,
                    "photo_path": str(photo_path),
                    "thumbnail_path": str(thumbnail_path),
                    "file_size": os.path.getsize(photo_path),
                    "width": photo_info.get("width"),
                    "height": photo_info.get("height"),
                    "format": photo_info.get("format"),
                    "thumbnail_info": thumbnail_info,
                    "download_date": photo_info.get("download_date")
                }
                
                logger.info("Фото загружено успешно: {} байт", result["file_size"])
                return result
                
            except FloodWaitError as e:
                logger.warning("Flood wait при загрузке фото: {} сек", e.seconds)
                await asyncio.sleep(e.seconds)
                continue
                
            except FileReferenceExpiredError:
                logger.warning("File reference истек, попытка {}", attempt + 1)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
                
            except Exception as e:
                logger.error("Ошибка загрузки фото (попытка {}): {}", attempt + 1, str(e))
                if attempt == max_retries - 1:
                    raise MediaProcessingError(f"Не удалось загрузить фото: {str(e)}")
                await asyncio.sleep(1)
        
        return None
    
    async def download_video(
        self,
        message_media: MessageMediaDocument,
        post_id: int,
        max_retries: int = 3,
        file_suffix: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Загрузить видео из сообщения

        Args:
            message_media: Медиа объект сообщения
            post_id: ID поста для именования файлов
            max_retries: Количество повторных попыток
            file_suffix: Суффикс для имени файла (для медиа-групп)

        Returns:
            Словарь с информацией о загруженном видео или None
        """
        for attempt in range(max_retries):
            try:
                logger.debug("Загрузка видео для поста {} (попытка {})", post_id, attempt + 1)
                
                # Проверяем что медиа содержит документ
                if not isinstance(message_media, MessageMediaDocument):
                    logger.error("Медиа не является документом: {}", type(message_media))
                    return None
                
                document = message_media.document
                if not isinstance(document, Document):
                    logger.error("Неверный тип документа: {}", type(document))
                    return None
                
                # Проверяем что это видео
                video_attribute = None
                filename_attribute = None
                
                for attr in document.attributes:
                    if isinstance(attr, DocumentAttributeVideo):
                        video_attribute = attr
                    elif isinstance(attr, DocumentAttributeFilename):
                        filename_attribute = attr
                
                if not video_attribute:
                    logger.debug("Документ не содержит видео атрибута")
                    return None
                
                # Определяем расширение файла
                file_ext = ".mp4"  # По умолчанию
                if filename_attribute and filename_attribute.file_name:
                    file_name = filename_attribute.file_name.lower()
                    if file_name.endswith(('.mov', '.avi', '.mkv', '.mp4', '.webm')):
                        file_ext = Path(file_name).suffix
                elif document.mime_type:
                    mime_to_ext = {
                        'video/mp4': '.mp4',
                        'video/quicktime': '.mov',
                        'video/x-msvideo': '.avi',
                        'video/x-matroska': '.mkv',
                        'video/webm': '.webm'
                    }
                    file_ext = mime_to_ext.get(document.mime_type, '.mp4')
                
                # Создаем имена файлов (с учётом суффикса для медиа-групп)
                video_filename = f"video_{post_id}_{document.id}{file_suffix}{file_ext}"
                thumbnail_filename = f"thumb_{post_id}_{document.id}{file_suffix}.jpg"
                
                video_path = self.videos_dir / video_filename
                thumbnail_path = self.thumbnails_dir / thumbnail_filename
                
                # Загружаем видео файл
                logger.info("Загружаем видео {} (размер: {} байт)", video_filename, document.size)
                video_bytes = await self.client.download_media(
                    message_media,
                    file=BytesIO()
                )
                
                if not video_bytes:
                    logger.error("Не удалось загрузить видео")
                    return None
                
                # Сохраняем видео файл
                video_bytes.seek(0)
                with open(video_path, 'wb') as f:
                    f.write(video_bytes.read())
                
                # Пытаемся создать миниатюру из видео (если есть thumbnail в документе)
                thumbnail_info = await self._create_video_thumbnail(
                    document, video_path, thumbnail_path
                )
                
                result = {
                    "video_id": str(document.id),
                    "access_hash": str(document.access_hash),
                    "file_reference": document.file_reference.hex() if document.file_reference else None,
                    "video_path": str(video_path),
                    "thumbnail_path": str(thumbnail_path) if thumbnail_info.get("created") else None,
                    "file_size": document.size,
                    "duration": video_attribute.duration,
                    "width": video_attribute.w,
                    "height": video_attribute.h,
                    "mime_type": document.mime_type,
                    "thumbnail_info": thumbnail_info,
                    "download_date": video_bytes.tell() and video_bytes.tell() > 0
                }
                
                logger.info("Видео загружено успешно: {} байт, длительность: {}с", 
                           result["file_size"], result["duration"])
                return result
                
            except FloodWaitError as e:
                logger.warning("Flood wait при загрузке видео: {} сек", e.seconds)
                await asyncio.sleep(e.seconds)
                continue
                
            except FileReferenceExpiredError:
                logger.warning("File reference истек, попытка {}", attempt + 1)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
                
            except Exception as e:
                logger.error("Ошибка загрузки видео (попытка {}): {}", attempt + 1, str(e))
                if attempt == max_retries - 1:
                    raise MediaProcessingError(f"Не удалось загрузить видео: {str(e)}")
                await asyncio.sleep(1)
        
        return None
    
    def _get_best_photo_size(self, photo: Photo) -> Optional[PhotoSize]:
        """
        Получить наилучший размер фото
        
        Args:
            photo: Объект фото Telethon
            
        Returns:
            Лучший размер фото или None
        """
        if not photo.sizes:
            return None
        
        # Сортируем размеры по площади (приоритет большим размерам)
        valid_sizes = [
            size for size in photo.sizes
            if isinstance(size, PhotoSize) and hasattr(size, 'w') and hasattr(size, 'h')
        ]
        
        if not valid_sizes:
            return None
        
        # Выбираем размер с максимальной площадью
        best_size = max(valid_sizes, key=lambda s: s.w * s.h)
        
        logger.debug("Выбран размер фото: {}x{}", best_size.w, best_size.h)
        return best_size
    
    async def _create_thumbnail(
        self,
        photo_bytes: BytesIO,
        thumbnail_path: Path,
        size: tuple = (150, 150)
    ) -> Dict[str, Any]:
        """
        Создать миниатюру из фото
        
        Args:
            photo_bytes: Байты оригинального фото
            thumbnail_path: Путь для сохранения миниатюры
            size: Размер миниатюры (ширина, высота)
            
        Returns:
            Информация о созданной миниатюре
        """
        try:
            photo_bytes.seek(0)
            
            # Открываем изображение с помощью PIL
            with Image.open(photo_bytes) as img:
                # Конвертируем в RGB если нужно
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Создаем миниатюру с сохранением пропорций
                img.thumbnail(size, Image.Resampling.LANCZOS)
                
                # Сохраняем миниатюру
                img.save(thumbnail_path, "JPEG", quality=85, optimize=True)
            
            thumbnail_size = os.path.getsize(thumbnail_path)
            
            logger.debug("Создана миниатюра: {} байт", thumbnail_size)
            
            return {
                "path": str(thumbnail_path),
                "size": thumbnail_size,
                "dimensions": size
            }
            
        except Exception as e:
            logger.error("Ошибка создания миниатюры: {}", str(e))
            return {"error": str(e)}
    
    async def _create_video_thumbnail(
        self,
        document: Document,
        video_path: Path,
        thumbnail_path: Path
    ) -> Dict[str, Any]:
        """
        Создать миниатюру для видео
        
        Args:
            document: Документ с видео
            video_path: Путь к видео файлу
            thumbnail_path: Путь для сохранения миниатюры
            
        Returns:
            Информация о созданной миниатюре
        """
        try:
            # Проверяем есть ли встроенная миниатюра в документе
            if document.thumbs:
                for thumb in document.thumbs:
                    if hasattr(thumb, 'bytes') and thumb.bytes:
                        # Есть встроенная миниатюра, сохраняем её
                        with open(thumbnail_path, 'wb') as f:
                            f.write(thumb.bytes)
                        
                        thumbnail_size = os.path.getsize(thumbnail_path)
                        logger.debug("Создана миниатюра из встроенного thumb: {} байт", thumbnail_size)
                        
                        return {
                            "path": str(thumbnail_path),
                            "size": thumbnail_size,
                            "created": True,
                            "source": "embedded"
                        }
            
            # Если встроенной миниатюры нет, создаем простую заглушку
            # TODO: В будущем можно добавить извлечение кадра из видео с помощью ffmpeg
            logger.debug("Встроенной миниатюры нет, создаем заглушку")
            
            # Создаем простую заглушку 150x150 с текстом "VIDEO"
            try:
                from PIL import Image, ImageDraw, ImageFont
                
                # Создаем изображение заглушку
                img = Image.new('RGB', (150, 150), color=(64, 64, 64))
                draw = ImageDraw.Draw(img)
                
                # Добавляем текст "🎥 VIDEO"
                text = "🎥 VIDEO"
                try:
                    # Пытаемся использовать стандартный шрифт
                    bbox = draw.textbbox((0, 0), text)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    
                    x = (150 - text_width) // 2
                    y = (150 - text_height) // 2
                    
                    draw.text((x, y), text, fill=(255, 255, 255))
                except Exception:
                    # Fallback - простой текст без позиционирования
                    draw.text((50, 70), "VIDEO", fill=(255, 255, 255))
                
                # Сохраняем заглушку
                img.save(thumbnail_path, "JPEG", quality=85)
                
                thumbnail_size = os.path.getsize(thumbnail_path)
                logger.debug("Создана заглушка миниатюры: {} байт", thumbnail_size)
                
                return {
                    "path": str(thumbnail_path),
                    "size": thumbnail_size,
                    "created": True,
                    "source": "placeholder"
                }
                
            except ImportError:
                logger.warning("PIL недоступна, не можем создать миниатюру для видео")
                return {
                    "created": False, 
                    "error": "PIL not available"
                }
            
        except Exception as e:
            logger.error("Ошибка создания миниатюры для видео: {}", str(e))
            return {
                "created": False,
                "error": str(e)
            }
    
    def _analyze_photo(self, photo_path: Path) -> Dict[str, Any]:
        """
        Проанализировать загруженное фото
        
        Args:
            photo_path: Путь к фото
            
        Returns:
            Информация о фото
        """
        try:
            from datetime import datetime
            
            with Image.open(photo_path) as img:
                return {
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                    "download_date": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error("Ошибка анализа фото: {}", str(e))
            return {"error": str(e)}
    
    async def get_photo_for_ai(self, photo_path: Union[str, Path]) -> Optional[bytes]:
        """
        Получить фото в формате для AI анализа
        
        Args:
            photo_path: Путь к фото
            
        Returns:
            Байты фото для AI или None
        """
        try:
            photo_path = Path(photo_path)
            
            if not photo_path.exists():
                logger.error("Фото не найдено: {}", photo_path)
                return None
            
            # Читаем фото
            with open(photo_path, 'rb') as f:
                photo_bytes = f.read()
            
            # Проверяем размер (для OpenAI Vision API лимит ~20MB)
            if len(photo_bytes) > 20 * 1024 * 1024:
                logger.warning("Фото слишком большое для AI: {} байт", len(photo_bytes))
                # Сжимаем фото для AI
                return await self._compress_for_ai(photo_path)
            
            return photo_bytes
            
        except Exception as e:
            logger.error("Ошибка подготовки фото для AI: {}", str(e))
            return None
    
    async def get_video_thumbnail_for_ai(self, video_path: Union[str, Path]) -> Optional[bytes]:
        """
        Получить миниатюру видео для AI анализа
        
        Args:
            video_path: Путь к видео
            
        Returns:
            Байты миниатюры или None
        """
        try:
            video_path = Path(video_path)
            
            if not video_path.exists():
                logger.error("Видео не найдено: {}", video_path)
                return None
            
            # Ищем соответствующую миниатюру
            video_filename = video_path.stem
            thumbnail_pattern = f"thumb_*_{video_filename.split('_')[-1]}.jpg"
            
            thumbnail_files = list(self.thumbnails_dir.glob(thumbnail_pattern))
            
            if thumbnail_files:
                thumbnail_path = thumbnail_files[0]
                logger.debug("Найдена миниатюра для видео: {}", thumbnail_path)
                
                # Читаем миниатюру
                with open(thumbnail_path, 'rb') as f:
                    thumbnail_bytes = f.read()
                
                logger.debug("Получены байты миниатюры для AI: {} байт", len(thumbnail_bytes))
                return thumbnail_bytes
            else:
                logger.warning("Миниатюра для видео не найдена: {}", video_path)
                return None
            
        except Exception as e:
            logger.error("Ошибка получения миниатюры видео для AI: {}", str(e))
            return None
    
    async def _compress_for_ai(self, photo_path: Path, max_size: int = 15 * 1024 * 1024) -> Optional[bytes]:
        """
        Сжать фото для AI анализа
        
        Args:
            photo_path: Путь к фото
            max_size: Максимальный размер в байтах
            
        Returns:
            Сжатые байты фото или None
        """
        try:
            with Image.open(photo_path) as img:
                # Конвертируем в RGB
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Уменьшаем размер пропорционально
                original_size = img.size
                scale_factor = 0.8
                
                while True:
                    new_size = (
                        int(original_size[0] * scale_factor),
                        int(original_size[1] * scale_factor)
                    )
                    
                    # Изменяем размер
                    resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    # Сохраняем во временный буфер
                    buffer = BytesIO()
                    resized_img.save(buffer, format='JPEG', quality=85, optimize=True)
                    
                    # Проверяем размер
                    if len(buffer.getvalue()) <= max_size:
                        logger.info("Фото сжато с {} до {} байт", 
                                   os.path.getsize(photo_path), len(buffer.getvalue()))
                        return buffer.getvalue()
                    
                    # Уменьшаем коэффициент
                    scale_factor *= 0.9
                    
                    if scale_factor < 0.1:
                        logger.error("Не удалось сжать фото до требуемого размера")
                        return None
            
        except Exception as e:
            logger.error("Ошибка сжатия фото: {}", str(e))
            return None
    
    def cleanup_old_media(self, days: int = 30) -> int:
        """
        Очистка старых медиа файлов
        
        Args:
            days: Количество дней для хранения
            
        Returns:
            Количество удаленных файлов
        """
        try:
            from datetime import datetime, timedelta
            
            cutoff_time = datetime.now() - timedelta(days=days)
            deleted_count = 0
            
            # Очистка фото
            for file_path in self.photos_dir.glob("*"):
                if file_path.stat().st_mtime < cutoff_time.timestamp():
                    file_path.unlink()
                    deleted_count += 1
            
            # Очистка видео
            for file_path in self.videos_dir.glob("*"):
                if file_path.stat().st_mtime < cutoff_time.timestamp():
                    file_path.unlink()
                    deleted_count += 1
            
            # Очистка миниатюр
            for file_path in self.thumbnails_dir.glob("*"):
                if file_path.stat().st_mtime < cutoff_time.timestamp():
                    file_path.unlink()
                    deleted_count += 1
            
            logger.info("Удалено {} старых медиа файлов", deleted_count)
            return deleted_count
            
        except Exception as e:
            logger.error("Ошибка очистки медиа: {}", str(e))
            return 0


# Глобальный экземпляр процессора
_media_processor: Optional[TelethonMediaProcessor] = None


def get_media_processor(client: TelegramClient) -> TelethonMediaProcessor:
    """Получить глобальный экземпляр процессора медиа"""
    global _media_processor
    
    if _media_processor is None:
        _media_processor = TelethonMediaProcessor(client)
    
    return _media_processor