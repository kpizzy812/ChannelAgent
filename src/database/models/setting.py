"""
Модель настроек приложения
Хранит конфигурационные параметры в базе данных
"""

from datetime import datetime
from typing import Optional, Any, Union
from dataclasses import dataclass
import json

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
# from .base import BaseModel  # Не используется для Setting

# Настройка логгера модуля
logger = logger.bind(module="models")


@dataclass
class Setting:
    """
    Модель настройки приложения
    
    Attributes:
        key: Ключ настройки (первичный ключ)
        value: Значение настройки (JSON строка)
        description: Описание настройки
        category: Категория настройки
        is_system: Системная настройка (нельзя удалить)
        updated_date: Дата последнего обновления (для совместимости с БД)
        created_at: Дата создания (для совместимости)
        updated_at: Дата обновления (для совместимости)
    """
    
    key: str
    value: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_system: bool = False
    updated_date: Optional[datetime] = None  # Для совместимости с БД
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Дополнительная инициализация"""
        # Для модели Setting не нужен ID, используем key как PK
        # Поэтому переопределяем базовое поведение
        if self.updated_date is None:
            self.updated_date = datetime.now()
        
        if not hasattr(self, 'created_at') or self.created_at is None:
            self.created_at = datetime.now()
    
    def validate(self) -> bool:
        """Валидация модели настройки"""
        
        # Ключ обязателен и не должен быть пустым
        if not self.key or not self.key.strip():
            logger.error("Ключ настройки не может быть пустым")
            return False
        
        # Ключ должен состоять только из букв, цифр и подчеркиваний
        if not self.key.replace('_', '').replace('.', '').isalnum():
            logger.error("Ключ настройки должен содержать только буквы, цифры, точки и подчеркивания: {}", 
                        self.key)
            return False
        
        # Ключ не должен быть слишком длинным
        if len(self.key) > 255:
            logger.error("Ключ настройки слишком длинный: {} символов", len(self.key))
            return False
        
        # Если есть значение, проверяем что это валидный JSON
        if self.value is not None:
            try:
                json.loads(self.value)
            except json.JSONDecodeError as e:
                logger.error("Значение настройки '{}' не является валидным JSON: {}", 
                           self.key, str(e))
                return False
        
        logger.debug("Валидация настройки '{}' прошла успешно", self.key)
        return True
    
    def get_value(self, default: Any = None) -> Any:
        """Получить десериализованное значение настройки"""
        if self.value is None:
            return default
        
        try:
            return json.loads(self.value)
        except json.JSONDecodeError:
            logger.error("Ошибка десериализации значения настройки '{}'", self.key)
            return default
    
    def set_value(self, value: Any) -> None:
        """Установить значение настройки (с сериализацией в JSON)"""
        try:
            old_value = self.value
            self.value = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
            self.updated_date = datetime.now()
            self.updated_at = datetime.now()
            
            logger.info("Обновлена настройка '{}': {} -> {}", 
                       self.key, old_value, self.value)
        except (TypeError, ValueError) as e:
            logger.error("Ошибка сериализации значения настройки '{}': {}", 
                        self.key, str(e))
            raise
    
    def get_string_value(self, default: str = "") -> str:
        """Получить строковое значение настройки"""
        value = self.get_value(default)
        return str(value) if value is not None else default
    
    def get_int_value(self, default: int = 0) -> int:
        """Получить целочисленное значение настройки"""
        value = self.get_value(default)
        try:
            return int(value) if value is not None else default
        except (ValueError, TypeError):
            logger.warning("Не удалось преобразовать значение настройки '{}' в int: {}", 
                          self.key, value)
            return default
    
    def get_float_value(self, default: float = 0.0) -> float:
        """Получить дробное значение настройки"""
        value = self.get_value(default)
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            logger.warning("Не удалось преобразовать значение настройки '{}' в float: {}", 
                          self.key, value)
            return default
    
    def get_bool_value(self, default: bool = False) -> bool:
        """Получить булево значение настройки"""
        value = self.get_value(default)
        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            return value.lower() in ['true', '1', 'yes', 'on', 'enabled']
        elif isinstance(value, (int, float)):
            return bool(value)
        else:
            return default
    
    def get_list_value(self, default: Optional[list] = None) -> list:
        """Получить список из значения настройки"""
        if default is None:
            default = []
        
        value = self.get_value(default)
        return value if isinstance(value, list) else default
    
    def get_dict_value(self, default: Optional[dict] = None) -> dict:
        """Получить словарь из значения настройки"""
        if default is None:
            default = {}
        
        value = self.get_value(default)
        return value if isinstance(value, dict) else default
    
    @property
    def is_empty(self) -> bool:
        """Является ли настройка пустой"""
        return self.value is None or self.value.strip() == ""
    
    @property
    def category_display(self) -> str:
        """Отображаемая категория настройки"""
        return self.category or "Общие"
    
    def mark_as_system(self) -> None:
        """Отметить настройку как системную"""
        if not self.is_system:
            self.is_system = True
            self.updated_date = datetime.now()
            logger.info("Настройка '{}' отмечена как системная", self.key)
    
    def __repr__(self) -> str:
        """Строковое представление настройки"""
        value_preview = self.value[:50] + "..." if self.value and len(self.value) > 50 else self.value
        return (
            f"Setting(key='{self.key}', value='{value_preview}', "
            f"category='{self.category}', system={self.is_system})"
        )
    
    def __str__(self) -> str:
        """Строковое представление для пользователя"""
        return f"{self.key} = {self.get_value()}"