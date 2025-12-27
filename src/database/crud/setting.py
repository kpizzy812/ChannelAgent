"""
CRUD операции для настроек приложения
Управление конфигурационными параметрами
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты  
from src.database.connection import get_db_connection
from src.database.models.setting import Setting
from src.utils.exceptions import DatabaseError

# Настройка логгера модуля
logger = logger.bind(module="crud_setting")


class SettingCRUD:
    """CRUD операции для настроек"""
    
    def __init__(self):
        """Инициализация CRUD для настроек"""
        logger.debug("Инициализирован SettingCRUD")
    
    async def get_setting(self, key: str) -> Optional[str]:
        """Получить значение настройки по ключу"""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT value FROM settings WHERE key = ?",
                    (key,)
                )
                result = await cursor.fetchone()
                
                if result:
                    logger.debug("Получена настройка '{}': {}", key, result[0])
                    return result[0]
                else:
                    logger.debug("Настройка '{}' не найдена", key)
                    return None
                    
        except Exception as e:
            logger.error("Ошибка получения настройки '{}': {}", key, str(e))
            return None
    
    async def set_setting(
        self, 
        key: str, 
        value: str, 
        description: Optional[str] = None,
        category: Optional[str] = None,
        is_system: bool = False
    ) -> bool:
        """Установить значение настройки"""
        try:
            async with get_db_connection() as conn:
                # Проверяем существует ли настройка
                cursor = await conn.execute(
                    "SELECT key FROM settings WHERE key = ?",
                    (key,)
                )
                exists = await cursor.fetchone()
                
                if exists:
                    # Обновляем существующую
                    await conn.execute(
                        """UPDATE settings 
                           SET value = ?, description = COALESCE(?, description), 
                               category = COALESCE(?, category), is_system = ?,
                               updated_at = CURRENT_TIMESTAMP 
                           WHERE key = ?""",
                        (value, description, category, is_system, key)
                    )
                    logger.info("Обновлена настройка '{}': {}", key, value)
                else:
                    # Создаем новую
                    await conn.execute(
                        """INSERT INTO settings (key, value, description, category, is_system, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                        (key, value, description or f"Настройка {key}", category or "general", is_system)
                    )
                    logger.info("Создана настройка '{}': {}", key, value)
                
                await conn.commit()
                return True
                
        except Exception as e:
            logger.error("Ошибка установки настройки '{}': {}", key, str(e))
            return False
    
    async def get_setting_object(self, key: str) -> Optional[Setting]:
        """Получить объект настройки целиком"""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT key, value, description, category, is_system, updated_at FROM settings WHERE key = ?",
                    (key,)
                )
                result = await cursor.fetchone()
                
                if result:
                    updated_at = datetime.fromisoformat(result[5]) if result[5] else datetime.now()
                    
                    setting = Setting(
                        key=result[0],
                        value=result[1],
                        description=result[2],
                        category=result[3],
                        is_system=bool(result[4]),
                        updated_date=updated_at
                    )
                    
                    logger.debug("Получен объект настройки '{}'", key)
                    return setting
                else:
                    return None
                    
        except Exception as e:
            logger.error("Ошибка получения объекта настройки '{}': {}", key, str(e))
            return None
    
    async def get_settings_by_category(self, category: str) -> List[Setting]:
        """Получить все настройки в категории"""
        try:
            settings = []
            
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT key, value, description, category, is_system, updated_at FROM settings WHERE category = ? ORDER BY key",
                    (category,)
                )
                results = await cursor.fetchall()
                
                for result in results:
                    updated_at = datetime.fromisoformat(result[5]) if result[5] else datetime.now()
                    
                    setting = Setting(
                        key=result[0],
                        value=result[1],
                        description=result[2],
                        category=result[3],
                        is_system=bool(result[4]),
                        updated_date=updated_at
                    )
                    settings.append(setting)
                
                logger.debug("Получено {} настроек в категории '{}'", len(settings), category)
                return settings
                
        except Exception as e:
            logger.error("Ошибка получения настроек категории '{}': {}", category, str(e))
            return []
    
    async def delete_setting(self, key: str) -> bool:
        """Удалить настройку"""
        try:
            async with get_db_connection() as conn:
                # Проверяем что настройка не системная
                cursor = await conn.execute(
                    "SELECT is_system FROM settings WHERE key = ?",
                    (key,)
                )
                result = await cursor.fetchone()
                
                if not result:
                    logger.warning("Попытка удалить несуществующую настройку '{}'", key)
                    return False
                
                if result[0]:  # is_system = True
                    logger.warning("Попытка удалить системную настройку '{}'", key)
                    return False
                
                # Удаляем настройку
                await conn.execute("DELETE FROM settings WHERE key = ?", (key,))
                await conn.commit()
                
                logger.info("Удалена настройка '{}'", key)
                return True
                
        except Exception as e:
            logger.error("Ошибка удаления настройки '{}': {}", key, str(e))
            return False
    
    async def get_all_settings(self) -> Dict[str, str]:
        """Получить все настройки как словарь ключ-значение"""
        try:
            settings = {}
            
            async with get_db_connection() as conn:
                cursor = await conn.execute("SELECT key, value FROM settings ORDER BY key")
                results = await cursor.fetchall()
                
                for result in results:
                    settings[result[0]] = result[1]
                
                logger.debug("Получено {} настроек", len(settings))
                return settings
                
        except Exception as e:
            logger.error("Ошибка получения всех настроек: {}", str(e))
            return {}
    
    async def get_settings_by_prefix(self, prefix: str) -> Dict[str, str]:
        """Получить настройки по префиксу ключа"""
        try:
            settings = {}
            
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT key, value FROM settings WHERE key LIKE ? ORDER BY key",
                    (f"{prefix}%",)
                )
                results = await cursor.fetchall()
                
                for result in results:
                    settings[result[0]] = result[1]
                
                logger.debug("Получено {} настроек с префиксом '{}'", len(settings), prefix)
                return settings
                
        except Exception as e:
            logger.error("Ошибка получения настроек с префиксом '{}': {}", prefix, str(e))
            return {}
    
    async def create_default_settings(self) -> None:
        """Создать настройки по умолчанию"""
        try:
            default_settings = [
                ("daily_post.enabled", "true", "Включить ежедневные посты", "daily_posts", True),
                ("daily_post.time", "09:00", "Время публикации ежедневных постов", "daily_posts", True),
                ("daily_post.pin_enabled", "false", "Закреплять ежедневные посты", "daily_posts", True),
                ("daily_post.template", "crypto_morning", "Шаблон ежедневных постов по умолчанию", "daily_posts", True),
                ("monitoring.interval", "300", "Интервал мониторинга каналов (сек)", "monitoring", True),
                ("ai.relevance_threshold", "6", "Минимальный порог релевантности", "ai", True),
            ]
            
            created_count = 0
            
            for key, value, description, category, is_system in default_settings:
                existing = await self.get_setting(key)
                if not existing:
                    success = await self.set_setting(key, value, description, category, is_system)
                    if success:
                        created_count += 1
            
            if created_count > 0:
                logger.info("Создано {} настроек по умолчанию", created_count)
            else:
                logger.debug("Все настройки по умолчанию уже существуют")
                
        except Exception as e:
            logger.error("Ошибка создания настроек по умолчанию: {}", str(e))


# Глобальный экземпляр CRUD
_setting_crud: Optional[SettingCRUD] = None


def get_setting_crud() -> SettingCRUD:
    """Получить глобальный экземпляр SettingCRUD"""
    global _setting_crud
    
    if _setting_crud is None:
        _setting_crud = SettingCRUD()
    
    return _setting_crud


# Вспомогательные функции для упрощения использования
async def get_setting_value(key: str, default: str = "") -> str:
    """Быстро получить значение настройки"""
    crud = get_setting_crud()
    value = await crud.get_setting(key)
    return value if value is not None else default


async def set_setting_value(key: str, value: str, description: Optional[str] = None) -> bool:
    """Быстро установить значение настройки"""
    crud = get_setting_crud()
    return await crud.set_setting(key, value, description)


async def get_bool_setting(key: str, default: bool = False) -> bool:
    """Получить булево значение настройки"""
    value = await get_setting_value(key)
    if not value:
        return default
    return value.lower() in ['true', '1', 'yes', 'on', 'enabled']


async def get_int_setting(key: str, default: int = 0) -> int:
    """Получить целочисленное значение настройки"""
    value = await get_setting_value(key)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Некорректное целочисленное значение настройки '{}': {}", key, value)
        return default