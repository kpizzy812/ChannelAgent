"""
Модель пользовательского поста для обучения стиля
Хранит примеры постов пользователя для AI анализа стиля
"""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from enum import Enum

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from .base import BaseModel

# Настройка логгера модуля
logger = logger.bind(module="models")


class UserPostStatus(Enum):
    """Статусы пользовательского поста"""
    ACTIVE = "active"      # Активный пример для обучения
    INACTIVE = "inactive"  # Неактивный пример
    PENDING = "pending"    # Ожидает модерации


@dataclass
class UserPost(BaseModel):
    """
    Модель пользовательского поста для обучения стиля
    
    Attributes:
        text: Текст поста пользователя
        is_active: Используется ли пост для обучения стиля
        category: Категория поста (crypto, macro, web3, telegram, gamefi)
        style_tags: Теги стиля (эмодзи, форматирование, тон)
        usage_count: Количество использований в промптах
        quality_score: Оценка качества примера (1-10)
        source_link: Ссылка на оригинальный пост
        photo_file_id: ID фото в Telegram (если есть)
        added_date: Дата добавления (для совместимости с БД)
    """
    
    text: str = ""
    is_active: bool = True
    category: Optional[str] = None  # crypto, macro, web3, telegram, gamefi
    style_tags: Optional[str] = None
    usage_count: int = 0
    quality_score: Optional[int] = None  # 1-10
    source_link: Optional[str] = None  # Ссылка на оригинальный пост
    photo_file_id: Optional[str] = None  # ID фото в Telegram
    added_date: Optional[datetime] = None  # Для совместимости с БД
    
    def __post_init__(self):
        """Дополнительная инициализация"""
        super().__post_init__()
        
        # Синхронизируем added_date с created_at
        if self.added_date is None:
            self.added_date = self.created_at
        
        # Анализируем стиль поста при создании
        if not self.style_tags:
            self.style_tags = self._analyze_style_tags()
    
    def validate(self) -> bool:
        """Валидация модели пользовательского поста"""
        
        # Текст обязателен и не должен быть пустым
        if not self.text or not self.text.strip():
            logger.error("Текст пользовательского поста не может быть пустым")
            return False
        
        # Текст не должен быть слишком коротким
        if len(self.text.strip()) < 10:
            logger.error("Текст пользовательского поста слишком короткий: {} символов", 
                        len(self.text.strip()))
            return False
        
        # Текст не должен быть слишком длинным для Telegram
        if len(self.text) > 4000:
            logger.error("Текст пользовательского поста слишком длинный: {} символов", 
                        len(self.text))
            return False
        
        # quality_score должен быть от 1 до 10
        if self.quality_score is not None:
            if not 1 <= self.quality_score <= 10:
                logger.error("quality_score должен быть от 1 до 10: {}", self.quality_score)
                return False
        
        # usage_count не может быть отрицательным
        if self.usage_count < 0:
            logger.error("usage_count не может быть отрицательным: {}", self.usage_count)
            return False
        
        logger.debug("Валидация пользовательского поста прошла успешно")
        return True
    
    def _analyze_style_tags(self) -> str:
        """Анализ стилевых особенностей поста"""
        tags = []
        
        # Проверяем наличие эмодзи
        if any(ord(char) > 127 for char in self.text):
            emoji_count = sum(1 for char in self.text if ord(char) > 127)
            if emoji_count > 5:
                tags.append("много_эмодзи")
            elif emoji_count > 0:
                tags.append("эмодзи")
        
        # Проверяем форматирование Telegram
        if "**" in self.text or "*" in self.text:
            tags.append("жирный_курсив")
        if "__" in self.text:
            tags.append("подчеркнутый")
        if "```" in self.text or "`" in self.text:
            tags.append("код")
        if ">" in self.text:
            tags.append("цитаты")
        
        # Проверяем структуру
        lines = self.text.split('\n')
        if len(lines) > 3:
            tags.append("многострочный")
        if any(line.startswith('•') or line.startswith('-') for line in lines):
            tags.append("списки")
        
        # Проверяем хештеги
        if "#" in self.text:
            hashtag_count = self.text.count('#')
            if hashtag_count > 3:
                tags.append("много_хештегов")
            else:
                tags.append("хештеги")
        
        # Проверяем ссылки
        if "http" in self.text.lower() or "t.me" in self.text.lower():
            tags.append("ссылки")
        
        # Проверяем длину
        if len(self.text) > 1000:
            tags.append("длинный")
        elif len(self.text) < 200:
            tags.append("короткий")
        else:
            tags.append("средний")
        
        return ",".join(tags)
    
    @property
    def preview_text(self) -> str:
        """Превью текста для отображения"""
        if len(self.text) <= 100:
            return self.text
        return self.text[:97] + "..."
    
    def get_preview(self, length: int = 80) -> str:
        """
        Получить превью текста поста
        
        Args:
            length: Максимальная длина превью
            
        Returns:
            Обрезанный текст с многоточием если нужно
        """
        if len(self.text) <= length:
            return self.text
        return self.text[:length-3] + "..."
    
    @property
    def word_count(self) -> int:
        """Количество слов в тексте"""
        return len(self.text.split())
    
    @property
    def char_count(self) -> int:
        """Количество символов в тексте"""
        return len(self.text)
    
    @property
    def has_emoji(self) -> bool:
        """Содержит ли пост эмодзи"""
        return "эмодзи" in (self.style_tags or "")
    
    @property
    def has_formatting(self) -> bool:
        """Содержит ли пост форматирование"""
        format_tags = ["жирный_курсив", "подчеркнутый", "код", "цитаты"]
        return any(tag in (self.style_tags or "") for tag in format_tags)
    
    def activate(self) -> None:
        """Активировать пост для обучения стиля"""
        if not self.is_active:
            self.is_active = True
            self.update_timestamp()
            logger.info("Активирован пользовательский пост ID={}", self.id)
    
    def deactivate(self) -> None:
        """Деактивировать пост для обучения стиля"""
        if self.is_active:
            self.is_active = False
            self.update_timestamp()
            logger.info("Деактивирован пользовательский пост ID={}", self.id)
    
    def increment_usage(self) -> None:
        """Увеличить счетчик использования"""
        self.usage_count += 1
        self.update_timestamp()
        logger.debug("Увеличен счетчик использования поста ID={}: {}", 
                    self.id, self.usage_count)
    
    def set_quality_score(self, score: int) -> None:
        """Установить оценку качества"""
        if not 1 <= score <= 10:
            logger.error("Оценка качества должна быть от 1 до 10: {}", score)
            return
        
        old_score = self.quality_score
        self.quality_score = score
        self.update_timestamp()
        
        logger.info("Обновлена оценка качества поста ID={}: {} -> {}", 
                   self.id, old_score, score)
    
    def update_category(self, category: str) -> None:
        """Обновить категорию поста"""
        old_category = self.category
        self.category = category
        self.update_timestamp()
        
        logger.info("Обновлена категория поста ID={}: {} -> {}", 
                   self.id, old_category, category)
    
    def __repr__(self) -> str:
        """Строковое представление пользовательского поста"""
        return (
            f"UserPost(id={self.id}, preview='{self.preview_text}', "
            f"active={self.is_active}, usage={self.usage_count}, "
            f"quality={self.quality_score})"
        )