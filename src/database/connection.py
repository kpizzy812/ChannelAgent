"""
Модуль подключения к базе данных SQLite
Управляет соединениями и транзакциями
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, AsyncGenerator

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Сторонние библиотеки
import aiosqlite

# Локальные импорты
from src.utils.exceptions import DatabaseConnectionError, DatabaseError

# Настройка логгера модуля
logger = logger.bind(module="database")

# Глобальное соединение с БД
_connection: Optional[aiosqlite.Connection] = None
_connection_lock = asyncio.Lock()


class DatabaseConnection:
    """Менеджер подключения к базе данных"""
    
    def __init__(self, database_path: str):
        """
        Инициализация подключения к БД
        
        Args:
            database_path: Путь к файлу базы данных
        """
        self.database_path = Path(database_path)
        self.connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self) -> None:
        """Установить соединение с базой данных"""
        try:
            # Создаем директорию если не существует
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Подключаемся к БД
            self.connection = await aiosqlite.connect(
                str(self.database_path),
                timeout=30.0,
                check_same_thread=False
            )
            
            # Включаем поддержку foreign keys
            await self.connection.execute("PRAGMA foreign_keys = ON")
            
            # Настраиваем WAL mode для лучшей производительности
            # Альтернативно: "PRAGMA journal_mode = DELETE" - не оставляет файлы, но медленнее
            await self.connection.execute("PRAGMA journal_mode = WAL")
            
            # Настраиваем таймауты
            await self.connection.execute("PRAGMA busy_timeout = 30000")
            
            await self.connection.commit()
            
            logger.info("Подключение к БД установлено: {}", self.database_path)
            
        except Exception as e:
            error_msg = f"Ошибка подключения к БД {self.database_path}: {str(e)}"
            logger.error(error_msg)
            raise DatabaseConnectionError(str(self.database_path), error_msg)
    
    async def disconnect(self) -> None:
        """Закрыть соединение с базой данных"""
        if self.connection:
            try:
                # Принудительно записываем WAL в основную БД и очищаем
                await self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                await self.connection.commit()
                
                await self.connection.close()
                logger.info("Соединение с БД закрыто: {}", self.database_path)
            except Exception as e:
                logger.error("Ошибка при закрытии соединения с БД: {}", str(e))
            finally:
                self.connection = None
    
    async def is_connected(self) -> bool:
        """Проверить активность соединения"""
        if not self.connection:
            return False
        
        try:
            await self.connection.execute("SELECT 1")
            return True
        except Exception:
            return False
    
    async def execute(self, query: str, parameters: tuple = ()) -> aiosqlite.Cursor:
        """Выполнить SQL запрос"""
        if not self.connection:
            raise DatabaseError("Нет активного соединения с БД")
        
        try:
            cursor = await self.connection.execute(query, parameters)
            logger.debug("Выполнен SQL запрос: {} с параметрами: {}", 
                        query[:100] + "..." if len(query) > 100 else query, parameters)
            return cursor
        except Exception as e:
            logger.error("Ошибка выполнения SQL запроса: {}", str(e))
            raise DatabaseError(f"Ошибка выполнения запроса: {str(e)}")
    
    async def commit(self) -> None:
        """Зафиксировать транзакцию"""
        if self.connection:
            await self.connection.commit()
            logger.debug("Транзакция зафиксирована")
    
    async def rollback(self) -> None:
        """Откатить транзакцию"""
        if self.connection:
            await self.connection.rollback()
            logger.debug("Транзакция откачена")


# Глобальный менеджер подключения
_db_manager: Optional[DatabaseConnection] = None


async def initialize_database(database_path: str) -> None:
    """Инициализировать подключение к базе данных"""
    global _db_manager
    
    async with _connection_lock:
        if _db_manager is not None:
            await _db_manager.disconnect()
        
        _db_manager = DatabaseConnection(database_path)
        await _db_manager.connect()
        
        logger.info("База данных инициализирована: {}", database_path)


async def close_database() -> None:
    """Закрыть подключение к базе данных"""
    global _db_manager
    
    async with _connection_lock:
        if _db_manager:
            await _db_manager.disconnect()
            _db_manager = None
            logger.info("Подключение к базе данных закрыто")


def get_db_manager() -> DatabaseConnection:
    """Получить менеджер базы данных"""
    if _db_manager is None:
        raise DatabaseError("База данных не инициализирована")
    return _db_manager


@asynccontextmanager
async def get_db_connection() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Получить соединение с базой данных (context manager)"""
    db_manager = get_db_manager()
    
    if not await db_manager.is_connected():
        raise DatabaseError("Нет активного соединения с БД")
    
    try:
        yield db_manager.connection
    except Exception as e:
        logger.error("Ошибка при работе с БД: {}", str(e))
        raise


@asynccontextmanager
async def get_db_transaction() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Получить соединение с БД в рамках транзакции"""
    db_manager = get_db_manager()
    
    if not await db_manager.is_connected():
        raise DatabaseError("Нет активного соединения с БД")
    
    try:
        # Начинаем транзакцию
        await db_manager.connection.execute("BEGIN")
        logger.debug("Начата транзакция")
        
        yield db_manager.connection
        
        # Коммитим транзакцию при успешном завершении
        await db_manager.commit()
        logger.debug("Транзакция успешно завершена")
        
    except Exception as e:
        # Откатываем транзакцию при ошибке
        await db_manager.rollback()
        logger.error("Ошибка в транзакции, откат: {}", str(e))
        raise