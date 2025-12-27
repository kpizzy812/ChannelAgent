"""
Модель канала для мониторинга
Представляет отслеживаемый Telegram канал
"""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты  
from .base import BaseModel

# Настройка логгера модуля
logger = logger.bind(module="models")


@dataclass
class Channel(BaseModel):
    """
    Модель отслеживаемого канала
    
    Attributes:
        channel_id: ID канала в Telegram (отрицательное число для каналов)
        username: Username канала без @
        title: Название канала
        is_active: Активен ли мониторинг канала
        last_message_id: ID последнего обработанного сообщения
        added_date: Дата добавления канала (deprecated, используем created_at)
        posts_processed: Количество обработанных постов
        posts_approved: Количество одобренных постов
        posts_rejected: Количество отклоненных постов
    """
    
    channel_id: int = 0
    username: Optional[str] = None
    title: Optional[str] = None
    is_active: bool = True
    last_message_id: int = 0
    added_date: Optional[datetime] = None  # Для совместимости со схемой БД
    posts_processed: int = 0
    posts_approved: int = 0
    posts_rejected: int = 0
    
    def __post_init__(self):
        """Дополнительная инициализация"""
        super().__post_init__()
        
        # Синхронизируем added_date с created_at для совместимости
        if self.added_date is None:
            self.added_date = self.created_at
    
    def validate(self) -> bool:
        """Валидация модели канала"""
        
        # channel_id должен быть отрицательным (каналы в Telegram)
        if self.channel_id >= 0:
            logger.error("channel_id должен быть отрицательным для каналов: {}", self.channel_id)
            return False
        
        # username должен быть валидным (только буквы, цифры, подчеркивания)
        if self.username:
            if not self.username.replace('_', '').isalnum():
                logger.error("Неверный формат username: {}", self.username)
                return False
            
            # Убираем @ если есть
            if self.username.startswith('@'):
                self.username = self.username[1:]
        
        # last_message_id не может быть отрицательным
        if self.last_message_id < 0:
            logger.error("last_message_id не может быть отрицательным: {}", self.last_message_id)
            return False
        
        # Счетчики постов не могут быть отрицательными
        if any(count < 0 for count in [self.posts_processed, self.posts_approved, self.posts_rejected]):
            logger.error("Счетчики постов не могут быть отрицательными")
            return False
        
        # posts_approved + posts_rejected не может быть больше posts_processed
        if self.posts_approved + self.posts_rejected > self.posts_processed:
            logger.error("Сумма одобренных и отклоненных постов больше общего количества")
            return False
        
        logger.debug("Валидация канала {} прошла успешно", self.display_name)
        return True
    
    @property
    def display_name(self) -> str:
        """Отображаемое имя канала"""
        if self.title:
            return self.title
        elif self.username:
            return f"@{self.username}"
        else:
            return f"Channel {self.channel_id}"
    
    @property
    def telegram_link(self) -> str:
        """Ссылка на канал в Telegram"""
        if self.username:
            return f"https://t.me/{self.username}"
        else:
            return f"tg://resolve?domain={abs(self.channel_id)}"
    
    @property
    def approval_rate(self) -> float:
        """Процент одобренных постов"""
        if self.posts_processed == 0:
            return 0.0
        return (self.posts_approved / self.posts_processed) * 100
    
    @property
    def rejection_rate(self) -> float:
        """Процент отклоненных постов"""
        if self.posts_processed == 0:
            return 0.0
        return (self.posts_rejected / self.posts_processed) * 100
    
    def activate(self) -> None:
        """Активировать мониторинг канала"""
        if not self.is_active:
            self.is_active = True
            self.update_timestamp()
            logger.info("Активирован мониторинг канала {}", self.display_name)
    
    def deactivate(self) -> None:
        """Деактивировать мониторинг канала"""
        if self.is_active:
            self.is_active = False
            self.update_timestamp()
            logger.info("Деактивирован мониторинг канала {}", self.display_name)
    
    def update_last_message_id(self, message_id: int) -> None:
        """Обновить ID последнего сообщения"""
        if message_id > self.last_message_id:
            old_id = self.last_message_id
            self.last_message_id = message_id
            self.update_timestamp()
            logger.debug("Обновлен last_message_id для {}: {} -> {}", 
                        self.display_name, old_id, message_id)
    
    def increment_processed(self) -> None:
        """Увеличить счетчик обработанных постов"""
        self.posts_processed += 1
        self.update_timestamp()
        logger.debug("Увеличен счетчик обработанных постов для {}: {}", 
                    self.display_name, self.posts_processed)
    
    def increment_approved(self) -> None:
        """Увеличить счетчик одобренных постов"""
        self.posts_approved += 1
        self.update_timestamp()
        logger.debug("Увеличен счетчик одобренных постов для {}: {}", 
                    self.display_name, self.posts_approved)
    
    def increment_rejected(self) -> None:
        """Увеличить счетчик отклоненных постов"""
        self.posts_rejected += 1
        self.update_timestamp()
        logger.debug("Увеличен счетчик отклоненных постов для {}: {}", 
                    self.display_name, self.posts_rejected)
    
    def get_stats_summary(self) -> str:
        """Получить сводную статистику канала"""
        return (
            f"📊 Статистика канала {self.display_name}:\n"
            f"• Обработано постов: {self.posts_processed}\n" 
            f"• Одобрено: {self.posts_approved} ({self.approval_rate:.1f}%)\n"
            f"• Отклонено: {self.posts_rejected} ({self.rejection_rate:.1f}%)\n"
            f"• Статус: {'🟢 Активен' if self.is_active else '🔴 Неактивен'}"
        )
    
    def __repr__(self) -> str:
        """Строковое представление канала"""
        status = "active" if self.is_active else "inactive"
        return (
            f"Channel(id={self.id}, channel_id={self.channel_id}, "
            f"username={self.username}, title='{self.title}', "
            f"status={status}, processed={self.posts_processed})"
        )