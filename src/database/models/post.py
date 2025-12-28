"""
Модель поста для обработки и модерации
Представляет пост из канала на разных стадиях обработки
"""

from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum
import json

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from .base import BaseModel

# Настройка логгера модуля
logger = logger.bind(module="models")


class PostStatus(Enum):
    """Статусы поста в процессе обработки"""
    PENDING = "pending"        # Ожидает модерации
    APPROVED = "approved"      # Одобрен, ждет публикации
    REJECTED = "rejected"      # Отклонен
    POSTED = "posted"         # Опубликован
    SCHEDULED = "scheduled"   # Запланирован к публикации
    FAILED = "failed"         # Ошибка публикации


class PostSentiment(Enum):
    """Тональность поста"""
    POSITIVE = "позитивная"
    NEGATIVE = "негативная"  
    NEUTRAL = "нейтральная"


@dataclass
class Post(BaseModel):
    """
    Модель поста для обработки
    
    Attributes:
        channel_id: ID канала источника
        message_id: ID сообщения в канале
        original_text: Оригинальный текст поста
        processed_text: Обработанный AI текст
        photo_file_id: ID файла фото в Telegram (устарело)
        photo_path: Путь к локальному файлу фото
        relevance_score: Оценка релевантности (1-10)
        sentiment: Тональность поста
        status: Статус обработки
        source_link: Ссылка на оригинальный пост
        posted_date: Дата публикации (если опубликован)
        scheduled_date: Дата запланированной публикации
        moderation_notes: Заметки модератора
        ai_analysis: Подробный анализ от AI
        error_message: Сообщение об ошибке (если есть)
    """
    
    # Обязательные поля - даём им default значения чтобы работало с BaseModel
    channel_id: int = 0
    message_id: int = 0
    
    # Опциональные поля с default значениями
    original_text: Optional[str] = None
    processed_text: Optional[str] = None
    
    # Медиа поля
    photo_file_id: Optional[str] = None  # Устарело - используем photo_path
    photo_path: Optional[str] = None     # Путь к локальному файлу фото
    video_file_id: Optional[str] = None  # Устарело - используем video_path  
    video_path: Optional[str] = None     # Путь к локальному файлу видео
    media_type: Optional[str] = None     # 'photo', 'video' или None
    video_duration: Optional[int] = None # Длительность видео в секундах
    video_width: Optional[int] = None    # Ширина видео
    video_height: Optional[int] = None   # Высота видео
    
    relevance_score: Optional[int] = None
    sentiment: Optional[PostSentiment] = None
    status: PostStatus = PostStatus.PENDING
    source_link: Optional[str] = None
    posted_date: Optional[datetime] = None
    scheduled_date: Optional[datetime] = None
    moderation_notes: Optional[str] = None
    ai_analysis: Optional[str] = None
    error_message: Optional[str] = None
    pin_post: bool = False  # Нужно ли закрепить пост при публикации

    # Извлечённые ссылки из поста (JSON)
    extracted_links: Optional[str] = None

    # Множественные медиа (альбомы) - JSON массив
    # Формат: [{"type": "photo", "path": "...", "position": 0}, ...]
    media_items: Optional[str] = None

    # Счётчик попыток публикации для retry механизма
    retry_count: int = 0

    # Для совместимости со схемой БД
    created_date: Optional[datetime] = None
    
    def __post_init__(self):
        """Дополнительная инициализация"""
        super().__post_init__()
        
        # Синхронизируем created_date с created_at
        if self.created_date is None:
            self.created_date = self.created_at
        
        # Генерируем source_link если не задан
        if not self.source_link and self.channel_id and self.message_id:
            # Для каналов используем формат t.me/c/channel_id/message_id  
            # Для канала -1002797787404 нужно получить 2797787404
            clean_channel_id = str(abs(self.channel_id))[3:]  # Убираем -100 (3 символа, не 4!)
            self.source_link = f"https://t.me/c/{clean_channel_id}/{self.message_id}"
    
    def validate(self) -> bool:
        """Валидация модели поста"""
        
        # channel_id должен быть отрицательным для каналов
        if self.channel_id >= 0:
            logger.error("channel_id должен быть отрицательным: {}", self.channel_id)
            return False
        
        # message_id должен быть положительным
        if self.message_id <= 0:
            logger.error("message_id должен быть положительным: {}", self.message_id)
            return False
        
        # relevance_score должен быть от 1 до 10
        if self.relevance_score is not None:
            if not 1 <= self.relevance_score <= 10:
                logger.error("relevance_score должен быть от 1 до 10: {}", self.relevance_score)
                return False
        
        # Если пост опубликован, должна быть дата публикации
        if self.status == PostStatus.POSTED and self.posted_date is None:
            logger.error("Опубликованный пост должен иметь posted_date")
            return False
        
        # Если пост запланирован, должна быть дата публикации
        if self.status == PostStatus.SCHEDULED and self.scheduled_date is None:
            logger.error("Запланированный пост должен иметь scheduled_date")
            return False
        
        logger.debug("Валидация поста {} прошла успешно", self.unique_id)
        return True
    
    @property
    def unique_id(self) -> str:
        """Уникальный идентификатор поста"""
        return f"{abs(self.channel_id)}_{self.message_id}"
    
    @property
    def is_processed_by_ai(self) -> bool:
        """Обработан ли пост AI"""
        return (
            self.processed_text is not None and
            self.relevance_score is not None and
            self.sentiment is not None
        )
    
    @property
    def is_relevant(self) -> bool:
        """Соответствует ли пост порогу релевантности"""
        if self.relevance_score is None:
            return False
        return self.relevance_score >= 6  # TODO: брать из конфига
    
    @property
    def has_media(self) -> bool:
        """Есть ли у поста медиа"""
        return (self.photo_path is not None or 
                self.photo_file_id is not None or
                self.video_path is not None or 
                self.video_file_id is not None)
    
    @property
    def has_photo(self) -> bool:
        """Есть ли у поста фото"""
        return (self.photo_path is not None or 
                self.photo_file_id is not None or
                self.media_type == 'photo')
    
    @property
    def has_video(self) -> bool:
        """Есть ли у поста видео"""
        return (self.video_path is not None or 
                self.video_file_id is not None or
                self.media_type == 'video')
    
    @property
    def media_duration_formatted(self) -> str:
        """Форматированная длительность видео"""
        if self.video_duration is None:
            return "неизвестно"

        minutes = self.video_duration // 60
        seconds = self.video_duration % 60
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def media_list(self) -> List[dict]:
        """Парсинг JSON media_items в список словарей"""
        if not self.media_items:
            return []
        try:
            items = json.loads(self.media_items)
            # Сортируем по позиции
            return sorted(items, key=lambda x: x.get('position', 0))
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("Ошибка парсинга media_items для поста {}: {}", self.id, str(e))
            return []

    @property
    def has_album(self) -> bool:
        """Проверка наличия альбома (более 1 медиа)"""
        return len(self.get_media_items()) > 1

    @property
    def album_count(self) -> int:
        """Количество медиа в альбоме"""
        return len(self.get_media_items())

    def get_media_items(self) -> List[dict]:
        """
        Получить список медиа с fallback на старые поля

        Returns:
            Список словарей с информацией о медиа
        """
        # Если есть media_items - используем его
        if self.media_items:
            return self.media_list

        # Fallback для старых постов с одним медиа
        if self.photo_path:
            return [{"type": "photo", "path": self.photo_path, "position": 0}]
        if self.video_path:
            return [{"type": "video", "path": self.video_path, "position": 0}]

        return []

    def add_media_item(self, media_type: str, path: str, position: int) -> None:
        """
        Добавить медиа элемент в список

        Args:
            media_type: Тип медиа ('photo' или 'video')
            path: Путь к файлу
            position: Позиция в альбоме (0-based)
        """
        items = self.media_list.copy()

        new_item = {
            "type": media_type,
            "path": path,
            "position": position
        }

        # Проверяем нет ли уже такого элемента
        for item in items:
            if item.get('path') == path:
                logger.debug("Медиа {} уже добавлен в пост {}", path, self.id)
                return

        items.append(new_item)
        # Сортируем по позиции
        items = sorted(items, key=lambda x: x.get('position', 0))

        self.media_items = json.dumps(items, ensure_ascii=False)
        logger.debug("Добавлен медиа элемент в пост {}: {} (позиция {})",
                    self.id, media_type, position)
    
    @property
    def can_be_approved(self) -> bool:
        """Может ли пост быть одобрен"""
        return (
            self.status == PostStatus.PENDING and
            self.is_processed_by_ai and
            self.is_relevant
        )
    
    @property
    def display_text(self) -> str:
        """Текст для отображения (обработанный или оригинальный)"""
        return self.processed_text or self.original_text or "[Без текста]"
    
    def approve(self, notes: Optional[str] = None) -> None:
        """Одобрить пост"""
        if self.status != PostStatus.PENDING:
            logger.warning("Попытка одобрить пост в статусе {}", self.status.value)
            return
        
        self.status = PostStatus.APPROVED
        if notes:
            self.moderation_notes = notes
        self.update_timestamp()
        
        logger.info("Одобрен пост {}", self.unique_id)
    
    def reject(self, notes: Optional[str] = None) -> None:
        """Отклонить пост"""
        if self.status != PostStatus.PENDING:
            logger.warning("Попытка отклонить пост в статусе {}", self.status.value)
            return
        
        self.status = PostStatus.REJECTED
        if notes:
            self.moderation_notes = notes
        self.update_timestamp()
        
        logger.info("Отклонен пост {}", self.unique_id)
    
    def schedule(self, scheduled_date: datetime, notes: Optional[str] = None) -> None:
        """Запланировать пост к публикации"""
        if self.status not in [PostStatus.PENDING, PostStatus.APPROVED]:
            logger.warning("Попытка запланировать пост в статусе {}", self.status.value)
            return
        
        self.status = PostStatus.SCHEDULED
        self.scheduled_date = scheduled_date
        if notes:
            self.moderation_notes = notes
        self.update_timestamp()
        
        logger.info("Запланирован пост {} на {}", self.unique_id, scheduled_date)
    
    def mark_as_posted(self) -> None:
        """Отметить пост как опубликованный"""
        if self.status not in [PostStatus.APPROVED, PostStatus.SCHEDULED]:
            logger.warning("Попытка опубликовать пост в статусе {}", self.status.value)
            return
        
        self.status = PostStatus.POSTED
        self.posted_date = datetime.now()
        self.update_timestamp()
        
        logger.info("Опубликован пост {}", self.unique_id)
    
    def mark_as_failed(self, error_message: str) -> None:
        """Отметить пост как неудачный"""
        self.status = PostStatus.FAILED
        self.error_message = error_message
        self.update_timestamp()
        
        logger.error("Ошибка публикации поста {}: {}", self.unique_id, error_message)
    
    def set_ai_analysis(
        self, 
        processed_text: str, 
        relevance_score: int, 
        sentiment: PostSentiment,
        analysis_details: Optional[str] = None
    ) -> None:
        """Установить результаты AI анализа"""
        self.processed_text = processed_text
        self.relevance_score = relevance_score
        self.sentiment = sentiment
        
        if analysis_details:
            self.ai_analysis = analysis_details
        
        self.update_timestamp()
        
        logger.info("AI анализ для поста {}: релевантность={}, тональность={}", 
                   self.unique_id, relevance_score, sentiment.value)
    
    def get_moderation_summary(self) -> str:
        """Получить сводку для модерации"""
        summary_parts = [
            f"📄 Пост {self.unique_id}",
            f"📊 Релевантность: {self.relevance_score or 'не оценена'}/10",
            f"😊 Тональность: {self.sentiment.value if self.sentiment else 'не определена'}",
            f"⏰ Создан: {self.created_at.strftime('%Y-%m-%d %H:%M')}"
        ]
        
        # Добавляем информацию о медиа
        if self.has_photo:
            summary_parts.append("🖼 Есть фото")
        elif self.has_video:
            video_info = f"🎥 Есть видео"
            if self.video_duration:
                video_info += f" ({self.media_duration_formatted})"
            if self.video_width and self.video_height:
                video_info += f" {self.video_width}x{self.video_height}"
            summary_parts.append(video_info)
        
        if self.moderation_notes:
            summary_parts.append(f"📝 Заметки: {self.moderation_notes}")
        
        return "\n".join(summary_parts)
    
    def __repr__(self) -> str:
        """Строковое представление поста"""
        return (
            f"Post(id={self.id}, unique_id='{self.unique_id}', "
            f"relevance={self.relevance_score}, sentiment={self.sentiment}, "
            f"status={self.status.value})"
        )


def create_post(
    channel_id: int,
    message_id: int,
    original_text: str = None,
    processed_text: str = None,
    status: PostStatus = PostStatus.PENDING,
    relevance_score: int = None,
    sentiment: str = None,
    ai_analysis: str = None,
    **kwargs
) -> Post:
    """
    Фабричная функция для создания поста
    
    Args:
        channel_id: ID канала источника
        message_id: ID сообщения
        original_text: Оригинальный текст
        processed_text: Обработанный текст
        status: Статус поста
        relevance_score: Оценка релевантности
        sentiment: Тональность
        ai_analysis: Анализ AI
        **kwargs: Дополнительные параметры
    
    Returns:
        Созданный объект Post
    """
    # Преобразуем строковую тональность в enum если нужно
    sentiment_enum = None
    if sentiment:
        if sentiment == "позитивная":
            sentiment_enum = PostSentiment.POSITIVE
        elif sentiment == "негативная":
            sentiment_enum = PostSentiment.NEGATIVE
        else:
            sentiment_enum = PostSentiment.NEUTRAL
    
    return Post(
        channel_id=channel_id,
        message_id=message_id,
        original_text=original_text,
        processed_text=processed_text,
        status=status,
        relevance_score=relevance_score,
        sentiment=sentiment_enum,
        ai_analysis=ai_analysis,
        **kwargs
    )