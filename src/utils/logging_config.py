"""
Модуль настройки логирования через loguru
Конфигурирует все обработчики логов для приложения
"""

import sys
from pathlib import Path
from typing import Optional

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Настройка логгера модуля
logger = logger.bind(module="logging_config")


def setup_logging(
    log_level: str = "INFO",
    log_rotation: str = "10 MB", 
    log_retention: str = "30 days"
) -> None:
    """
    Настройка логирования через loguru
    
    Args:
        log_level: Уровень логирования
        log_rotation: Размер файла для ротации
        log_retention: Время хранения логов
    """
    
    # Создаем директорию для логов
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Удаляем стандартный handler
    logger.remove()
    
    # Console handler с цветной подсветкой
    logger.add(
        sys.stdout,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[module]}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        enqueue=True,
        filter=lambda record: record["extra"].get("module") is not None
    )
    
    # Fallback console handler для записей без модуля
    logger.add(
        sys.stdout,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}:{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        enqueue=True,
        filter=lambda record: record["extra"].get("module") is None
    )
    
    # File handler для всех логов
    logger.add(
        logs_dir / "agent.log",
        level="DEBUG",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{extra[module]} | "
            "{message}"
        ),
        rotation=log_rotation,
        retention=log_retention,
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        filter=lambda record: record["extra"].get("module") is not None
    )
    
    # Fallback file handler для записей без модуля
    logger.add(
        logs_dir / "agent.log",
        level="DEBUG", 
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        rotation=log_rotation,
        retention=log_retention,
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        filter=lambda record: record["extra"].get("module") is None
    )
    
    # Отдельный файл для ошибок
    logger.add(
        logs_dir / "errors.log",
        level="ERROR",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{extra[module]} | "
            "{message} | "
            "{exception}"
        ),
        rotation="5 MB",
        retention="60 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        filter=lambda record: record["extra"].get("module") is not None
    )
    
    # Fallback error handler для записей без модуля
    logger.add(
        logs_dir / "errors.log",
        level="ERROR",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message} | "
            "{exception}"
        ),
        rotation="5 MB", 
        retention="60 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        filter=lambda record: record["extra"].get("module") is None
    )
    
    logger.info("Логирование настроено успешно")
    logger.debug("Уровень логирования: {}", log_level)
    logger.debug("Ротация файлов: {}", log_rotation)
    logger.debug("Время хранения: {}", log_retention)


def setup_logging_from_config() -> None:
    """Настройка логирования из конфигурации"""
    try:
        # Импортируем здесь чтобы избежать циклических импортов
        from src.utils.config import get_config
        
        config = get_config()
        setup_logging(
            log_level=config.LOG_LEVEL,
            log_rotation=config.LOG_ROTATION,
            log_retention=config.LOG_RETENTION
        )
        
    except Exception as e:
        # Используем базовую настройку при ошибке загрузки конфигурации
        setup_logging()
        logger.error("Ошибка загрузки конфигурации для логирования: {}", str(e))


def get_module_logger(module_name: str):
    """
    Получить логгер для конкретного модуля
    
    Args:
        module_name: Имя модуля
        
    Returns:
        Настроенный логгер с привязкой к модулю
    """
    return logger.bind(module=module_name)


def log_startup_info() -> None:
    """Логирование информации о запуске приложения"""
    startup_logger = get_module_logger("startup")
    
    startup_logger.info("🚀 Запуск Telegram Channel Agent")
    startup_logger.info("Python version: {}", sys.version.split()[0])
    startup_logger.info("Platform: {}", sys.platform)
    startup_logger.info("Working directory: {}", Path.cwd())


def log_shutdown_info() -> None:
    """Логирование информации о завершении приложения"""
    shutdown_logger = get_module_logger("shutdown")
    
    shutdown_logger.info("🛑 Завершение работы Telegram Channel Agent")
    shutdown_logger.info("Все модули остановлены")
    shutdown_logger.info("👋 До свидания!")


# Функции для удобного логирования по модулям
def log_userbot_event(message: str, **kwargs) -> None:
    """Логирование событий userbot"""
    userbot_logger = get_module_logger("userbot")
    userbot_logger.info(message, **kwargs)


def log_bot_event(message: str, **kwargs) -> None:
    """Логирование событий bot"""
    bot_logger = get_module_logger("bot")
    bot_logger.info(message, **kwargs)


def log_ai_event(message: str, **kwargs) -> None:
    """Логирование событий AI модуля"""
    ai_logger = get_module_logger("ai")
    ai_logger.info(message, **kwargs)


def log_database_event(message: str, **kwargs) -> None:
    """Логирование событий базы данных"""
    db_logger = get_module_logger("database")
    db_logger.info(message, **kwargs)


def log_scheduler_event(message: str, **kwargs) -> None:
    """Логирование событий планировщика"""
    scheduler_logger = get_module_logger("scheduler")
    scheduler_logger.info(message, **kwargs)