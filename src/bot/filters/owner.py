"""
Фильтр для проверки владельца бота
Проверяет что команды выполняет только владелец (OWNER_ID из .env)
"""

from typing import Union

# aiogram 3.x импорты
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.utils.config import get_config

# Настройка логгера модуля
logger = logger.bind(module="bot_filters")


class OwnerFilter(BaseFilter):
    """
    Фильтр для проверки владельца бота
    Пропускает только сообщения от пользователя с OWNER_ID
    """
    
    def __init__(self):
        """Инициализация фильтра"""
        self.config = get_config()
        self.owner_id = self.config.OWNER_ID
        
        logger.debug("Инициализирован фильтр владельца: OWNER_ID={}", self.owner_id)
    
    async def __call__(self, update: Union[Message, CallbackQuery]) -> bool:
        """
        Проверить является ли пользователь владельцем
        
        Args:
            update: Сообщение или callback query
            
        Returns:
            True если пользователь владелец
        """
        try:
            # Получаем ID пользователя в зависимости от типа update
            if isinstance(update, Message):
                user_id = update.from_user.id if update.from_user else None
                username = update.from_user.username if update.from_user else None
            elif isinstance(update, CallbackQuery):
                user_id = update.from_user.id if update.from_user else None
                username = update.from_user.username if update.from_user else None
            else:
                logger.warning("Неизвестный тип update для фильтра владельца: {}", type(update))
                return False
            
            if not user_id:
                logger.warning("Не удалось получить user_id из update")
                return False
            
            # Проверяем что это владелец
            is_owner = user_id == self.owner_id
            
            if is_owner:
                logger.debug("Владелец {} (@{}) получил доступ", user_id, username or "unknown")
            else:
                logger.warning("Пользователь {} (@{}) попытался выполнить команду владельца", 
                             user_id, username or "unknown")
            
            return is_owner
            
        except Exception as e:
            logger.error("Ошибка в фильтре владельца: {}", str(e))
            return False


class AdminFilter(BaseFilter):
    """
    Фильтр для проверки администратора
    Расширенная версия - можно добавить список админов
    """
    
    def __init__(self, admin_ids: list = None):
        """
        Инициализация фильтра админов
        
        Args:
            admin_ids: Список ID администраторов (опционально)
        """
        self.config = get_config()
        self.owner_id = self.config.OWNER_ID
        
        # Список админов всегда включает владельца
        self.admin_ids = {self.owner_id}
        
        if admin_ids:
            self.admin_ids.update(admin_ids)
        
        logger.debug("Инициализирован фильтр админов: {} админов", len(self.admin_ids))
    
    async def __call__(self, update: Union[Message, CallbackQuery]) -> bool:
        """
        Проверить является ли пользователь администратором
        
        Args:
            update: Сообщение или callback query
            
        Returns:
            True если пользователь администратор
        """
        try:
            # Получаем ID пользователя
            if isinstance(update, Message):
                user_id = update.from_user.id if update.from_user else None
            elif isinstance(update, CallbackQuery):
                user_id = update.from_user.id if update.from_user else None
            else:
                return False
            
            if not user_id:
                return False
            
            is_admin = user_id in self.admin_ids
            
            if not is_admin:
                logger.warning("Пользователь {} попытался выполнить команду администратора", user_id)
            
            return is_admin
            
        except Exception as e:
            logger.error("Ошибка в фильтре администратора: {}", str(e))
            return False


def create_owner_filter() -> OwnerFilter:
    """Создать экземпляр фильтра владельца"""
    return OwnerFilter()


def create_admin_filter(admin_ids: list = None) -> AdminFilter:
    """
    Создать экземпляр фильтра администратора
    
    Args:
        admin_ids: Дополнительные ID администраторов
        
    Returns:
        Экземпляр AdminFilter
    """
    return AdminFilter(admin_ids)


# Глобальные экземпляры для удобства
owner_filter = OwnerFilter()
admin_filter = AdminFilter()