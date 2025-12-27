"""
Модуль обработки медиа для бота
Работа с локальными файлами фото через aiogram FSInputFile
"""

import os
from pathlib import Path
from typing import Optional, Union

# aiogram 3.x импорты
from aiogram.types import FSInputFile, BufferedInputFile

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.database.models.post import Post

# Настройка логгера модуля
logger = logger.bind(module="bot_media_handler")


class BotMediaHandler:
    """
    Класс для работы с медиа файлами в боте
    Преобразует локальные пути в объекты для отправки через aiogram
    """
    
    def __init__(self):
        """Инициализация обработчика медиа"""
        self.media_dir = Path("data/media")
        logger.debug("Инициализирован обработчик медиа для бота")
    
    def get_photo_for_send(self, post: Post) -> Optional[Union[FSInputFile, str]]:
        """
        Получить фото для отправки через бот
        
        Args:
            post: Объект поста с медиа
            
        Returns:
            FSInputFile для локального файла, photo_file_id для Telegram или None
        """
        # Приоритет: локальный файл -> file_id
        if post.photo_path:
            photo_path = Path(post.photo_path)
            
            # Проверяем существует ли локальный файл
            if photo_path.exists() and photo_path.is_file():
                try:
                    # Создаем FSInputFile для отправки
                    return FSInputFile(
                        path=str(photo_path),
                        filename=f"photo_{post.id}.jpg"
                    )
                    
                except Exception as e:
                    logger.error("Ошибка создания FSInputFile для {}: {}", photo_path, str(e))
            else:
                logger.warning("Локальный файл фото не найден: {}", photo_path)
        
        # Fallback к photo_file_id если локальный файл недоступен
        if post.photo_file_id:
            # Проверяем что photo_file_id - это действительно file_id, а не путь к файлу
            if not post.photo_file_id.startswith(('/', './', 'data/')):
                logger.debug("Используется photo_file_id для поста {}", post.id)
                return post.photo_file_id
            else:
                logger.warning("photo_file_id содержит путь к файлу вместо file_id: {}", post.photo_file_id)
        
        logger.debug("Нет доступного фото для поста {}", post.id)
        return None
    
    def get_video_for_send(self, post: Post) -> Optional[Union[FSInputFile, str]]:
        """
        Получить видео для отправки через бот
        
        Args:
            post: Объект поста с медиа
            
        Returns:
            FSInputFile для локального файла, video_file_id для Telegram или None
        """
        # Приоритет: локальный файл -> file_id
        if post.video_path:
            video_path = Path(post.video_path)
            
            # Проверяем существует ли локальный файл
            if video_path.exists() and video_path.is_file():
                try:
                    # Создаем FSInputFile для отправки
                    return FSInputFile(
                        path=str(video_path),
                        filename=f"video_{post.id}{video_path.suffix}"
                    )
                    
                except Exception as e:
                    logger.error("Ошибка создания FSInputFile для видео {}: {}", video_path, str(e))
            else:
                logger.warning("Локальный файл видео не найден: {}", video_path)
        
        # Fallback к video_file_id если локальный файл недоступен
        if post.video_file_id:
            # Проверяем что video_file_id - это действительно file_id, а не путь к файлу
            if not post.video_file_id.startswith(('/', './', 'data/')):
                logger.debug("Используется video_file_id для поста {}", post.id)
                return post.video_file_id
            else:
                logger.warning("video_file_id содержит путь к файлу вместо file_id: {}", post.video_file_id)
        
        logger.debug("Нет доступного видео для поста {}", post.id)
        return None
    
    def get_media_for_send(self, post: Post) -> tuple[Optional[Union[FSInputFile, str]], str]:
        """
        Получить медиа для отправки (фото или видео)
        
        Args:
            post: Объект поста с медиа
            
        Returns:
            Tuple (медиа_объект, тип_медиа) где тип_медиа = 'photo', 'video' или None
        """
        if post.has_photo:
            photo = self.get_photo_for_send(post)
            return photo, 'photo' if photo else None
        elif post.has_video:
            video = self.get_video_for_send(post)
            return video, 'video' if video else None
        else:
            return None, None
    
    def get_photo_bytes(self, post: Post) -> Optional[bytes]:
        """
        Получить байты фото для AI анализа
        
        Args:
            post: Объект поста с медиа
            
        Returns:
            Байты фото или None
        """
        if not post.photo_path:
            logger.debug("Нет пути к фото для поста {}", post.id)
            return None
        
        photo_path = Path(post.photo_path)
        
        if not photo_path.exists():
            logger.warning("Файл фото не существует: {}", photo_path)
            return None
        
        try:
            with open(photo_path, 'rb') as f:
                photo_bytes = f.read()
            
            logger.debug("Получены байты фото для поста {}: {} байт", post.id, len(photo_bytes))
            return photo_bytes
            
        except Exception as e:
            logger.error("Ошибка чтения файла фото {}: {}", photo_path, str(e))
            return None
    
    def validate_photo_file(self, photo_path: Union[str, Path]) -> bool:
        """
        Проверить валидность файла фото
        
        Args:
            photo_path: Путь к файлу фото
            
        Returns:
            True если файл валиден
        """
        try:
            photo_path = Path(photo_path)
            
            # Проверяем существование
            if not photo_path.exists():
                logger.debug("Файл не существует: {}", photo_path)
                return False
            
            # Проверяем что это файл
            if not photo_path.is_file():
                logger.debug("Путь не является файлом: {}", photo_path)
                return False
            
            # Проверяем размер (не должен быть 0)
            if photo_path.stat().st_size == 0:
                logger.debug("Файл пустой: {}", photo_path)
                return False
            
            # Проверяем расширение
            valid_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
            if photo_path.suffix.lower() not in valid_extensions:
                logger.debug("Неподдерживаемое расширение: {}", photo_path.suffix)
                return False
            
            logger.debug("Файл фото валиден: {}", photo_path)
            return True
            
        except Exception as e:
            logger.error("Ошибка валидации файла фото {}: {}", photo_path, str(e))
            return False
    
    def validate_video_file(self, video_path: Union[str, Path]) -> bool:
        """
        Проверить валидность файла видео
        
        Args:
            video_path: Путь к файлу видео
            
        Returns:
            True если файл валиден
        """
        try:
            video_path = Path(video_path)
            
            # Проверяем существование
            if not video_path.exists():
                logger.debug("Файл не существует: {}", video_path)
                return False
            
            # Проверяем что это файл
            if not video_path.is_file():
                logger.debug("Путь не является файлом: {}", video_path)
                return False
            
            # Проверяем размер (не должен быть 0)
            if video_path.stat().st_size == 0:
                logger.debug("Файл пустой: {}", video_path)
                return False
            
            # Проверяем расширение
            valid_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
            if video_path.suffix.lower() not in valid_extensions:
                logger.debug("Неподдерживаемое расширение: {}", video_path.suffix)
                return False
            
            logger.debug("Файл видео валиден: {}", video_path)
            return True
            
        except Exception as e:
            logger.error("Ошибка валидации файла видео {}: {}", video_path, str(e))
            return False
    
    def cleanup_invalid_media(self) -> int:
        """
        Очистка невалидных медиа файлов (фото и видео)
        
        Returns:
            Количество удаленных файлов
        """
        try:
            removed_count = 0
            
            # Очистка невалидных фото
            photos_dir = self.media_dir / "photos"
            if photos_dir.exists():
                for photo_file in photos_dir.glob("*"):
                    if not self.validate_photo_file(photo_file):
                        try:
                            photo_file.unlink()
                            removed_count += 1
                            logger.debug("Удален невалидный файл фото: {}", photo_file)
                        except Exception as e:
                            logger.error("Ошибка удаления файла {}: {}", photo_file, str(e))
            
            # Очистка невалидных видео
            videos_dir = self.media_dir / "videos"
            if videos_dir.exists():
                for video_file in videos_dir.glob("*"):
                    if not self.validate_video_file(video_file):
                        try:
                            video_file.unlink()
                            removed_count += 1
                            logger.debug("Удален невалидный файл видео: {}", video_file)
                        except Exception as e:
                            logger.error("Ошибка удаления файла {}: {}", video_file, str(e))
            
            if removed_count > 0:
                logger.info("Удалено {} невалидных медиа файлов", removed_count)
            
            return removed_count
            
        except Exception as e:
            logger.error("Ошибка очистки невалидных медиа: {}", str(e))
            return 0
    
    def cleanup_invalid_photos(self) -> int:
        """
        Очистка невалидных файлов фото (устаревший метод, используйте cleanup_invalid_media)
        
        Returns:
            Количество удаленных файлов
        """
        logger.warning("cleanup_invalid_photos устарел, используйте cleanup_invalid_media")
        return self.cleanup_invalid_media()


# Глобальный экземпляр обработчика
_media_handler: Optional[BotMediaHandler] = None


def get_media_handler() -> BotMediaHandler:
    """Получить глобальный экземпляр обработчика медиа"""
    global _media_handler
    
    if _media_handler is None:
        _media_handler = BotMediaHandler()
    
    return _media_handler