"""
Базовая модель для всех моделей базы данных
Содержит общие поля и методы
"""

from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

# Логирование (ОБЯЗАТЕЛЬНО loguru)  
from loguru import logger

# Настройка логгера модуля
logger = logger.bind(module="models")


@dataclass
class BaseModel:
    """
    Базовая модель для всех таблиц БД
    Содержит общие поля и методы
    """
    
    id: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Инициализация после создания объекта"""
        if self.id is not None and self.updated_at is None:
            self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование модели в словарь"""
        result = {}
        
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, datetime):
                # Преобразуем datetime в строку ISO
                result[field_name] = field_value.isoformat() if field_value else None
            else:
                result[field_name] = field_value
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """Создание модели из словаря"""
        # Преобразуем строки datetime обратно
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        
        if 'updated_at' in data and isinstance(data['updated_at'], str) and data['updated_at']:
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        return cls(**data)
    
    def update_timestamp(self) -> None:
        """Обновить timestamp изменения"""
        self.updated_at = datetime.now()
    
    def is_new(self) -> bool:
        """Проверить, является ли запись новой (без ID)"""
        return self.id is None
    
    def validate(self) -> bool:
        """
        Базовая валидация модели
        Переопределяется в наследниках
        """
        return True
    
    def __repr__(self) -> str:
        """Строковое представление модели"""
        class_name = self.__class__.__name__
        fields = []
        
        # Показываем только основные поля
        for field_name, field_value in self.__dict__.items():
            if field_name in ['id', 'created_at']:
                if field_name == 'created_at' and field_value:
                    # Укороченный формат даты
                    formatted_date = field_value.strftime('%Y-%m-%d %H:%M')
                    fields.append(f"{field_name}='{formatted_date}'")
                else:
                    fields.append(f"{field_name}={field_value}")
        
        return f"{class_name}({', '.join(fields)})"
    
    def log_creation(self) -> None:
        """Логирование создания записи"""
        logger.debug("Создана запись {}: ID={}", self.__class__.__name__, self.id)
    
    def log_update(self) -> None:
        """Логирование обновления записи"""
        logger.debug("Обновлена запись {}: ID={}", self.__class__.__name__, self.id)
    
    def log_deletion(self) -> None:
        """Логирование удаления записи"""
        logger.debug("Удалена запись {}: ID={}", self.__class__.__name__, self.id)