"""
Модуль кастомных исключений приложения
Содержит специализированные исключения для разных модулей
"""

from typing import Optional, Any

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Настройка логгера модуля
logger = logger.bind(module="exceptions")


class ChannelAgentError(Exception):
    """Базовое исключение для всех ошибок приложения"""
    
    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)
        
        # Логируем все исключения
        if details:
            logger.error("ChannelAgentError: {} | Детали: {}", message, details)
        else:
            logger.error("ChannelAgentError: {}", message)


# ==============================================
# ИСКЛЮЧЕНИЯ КОНФИГУРАЦИИ
# ==============================================

class ConfigurationError(ChannelAgentError):
    """Ошибки конфигурации приложения"""
    pass


class MissingEnvironmentVariableError(ConfigurationError):
    """Отсутствует обязательная переменная окружения"""
    
    def __init__(self, variable_name: str):
        message = f"Отсутствует обязательная переменная окружения: {variable_name}"
        super().__init__(message)
        self.variable_name = variable_name


class InvalidConfigValueError(ConfigurationError):
    """Неверное значение в конфигурации"""
    
    def __init__(self, parameter: str, value: Any, expected: str):
        message = f"Неверное значение параметра '{parameter}': {value}. Ожидается: {expected}"
        super().__init__(message)
        self.parameter = parameter
        self.value = value
        self.expected = expected


# ==============================================
# ИСКЛЮЧЕНИЯ USERBOT (TELETHON)
# ==============================================

class UserbotError(ChannelAgentError):
    """Базовое исключение для UserBot"""
    pass


class TelethonConnectionError(UserbotError):
    """Ошибка подключения к Telegram через Telethon"""
    
    def __init__(self, details: Optional[str] = None):
        message = "Не удалось подключиться к Telegram через UserBot"
        super().__init__(message, details)


class ChannelAccessError(UserbotError):
    """Нет доступа к каналу"""
    
    def __init__(self, channel_username: str, details: Optional[str] = None):
        message = f"Нет доступа к каналу @{channel_username}"
        super().__init__(message, details)
        self.channel_username = channel_username


class MessageProcessingError(UserbotError):
    """Ошибка обработки сообщения"""
    
    def __init__(self, message_id: int, channel: str, details: Optional[str] = None):
        message = f"Ошибка обработки сообщения {message_id} из канала {channel}"
        super().__init__(message, details)
        self.message_id = message_id
        self.channel = channel


class MediaProcessingError(UserbotError):
    """Ошибка обработки медиа файлов"""
    
    def __init__(self, media_type: str, details: Optional[str] = None):
        message = f"Ошибка обработки медиа: {media_type}"
        super().__init__(message, details)
        self.media_type = media_type


# ==============================================
# ИСКЛЮЧЕНИЯ BOT (AIOGRAM)
# ==============================================

class BotError(ChannelAgentError):
    """Базовое исключение для Bot"""
    pass


class AiogramConnectionError(BotError):
    """Ошибка подключения бота aiogram"""
    
    def __init__(self, details: Optional[str] = None):
        message = "Не удалось подключиться к Telegram Bot API"
        super().__init__(message, details)


class UnauthorizedUserError(BotError):
    """Попытка доступа неавторизованного пользователя"""
    
    def __init__(self, user_id: int):
        message = f"Неавторизованный доступ от пользователя {user_id}"
        super().__init__(message)
        self.user_id = user_id


class PostModerationError(BotError):
    """Ошибка в процессе модерации поста"""
    
    def __init__(self, post_id: int, details: Optional[str] = None):
        message = f"Ошибка модерации поста {post_id}"
        super().__init__(message, details)
        self.post_id = post_id


# ==============================================
# ИСКЛЮЧЕНИЯ AI МОДУЛЯ (OPENAI)
# ==============================================

class AIError(ChannelAgentError):
    """Базовое исключение для AI модуля"""
    pass


class OpenAIAPIError(AIError):
    """Ошибка OpenAI API"""
    
    def __init__(self, status_code: Optional[int] = None, details: Optional[str] = None):
        if status_code:
            message = f"Ошибка OpenAI API (код {status_code})"
        else:
            message = "Ошибка OpenAI API"
        super().__init__(message, details)
        self.status_code = status_code


class ContentAnalysisError(AIError):
    """Ошибка анализа контента"""
    
    def __init__(self, content_type: str, details: Optional[str] = None):
        message = f"Ошибка анализа {content_type}"
        super().__init__(message, details)
        self.content_type = content_type


class RelevanceScoreError(AIError):
    """Ошибка вычисления релевантности"""
    
    def __init__(self, score: Optional[int] = None, details: Optional[str] = None):
        message = f"Неверная оценка релевантности: {score}"
        super().__init__(message, details)


class AIProcessingError(AIError):
    """Ошибка обработки AI"""
    
    def __init__(self, details: Optional[str] = None):
        message = "Ошибка обработки AI"
        super().__init__(message, details)


class ContentStylingError(AIError):
    """Ошибка стилизации контента"""
    
    def __init__(self, details: Optional[str] = None):
        message = "Ошибка рестайлинга контента"
        super().__init__(message, details)


# ==============================================
# ИСКЛЮЧЕНИЯ БАЗЫ ДАННЫХ
# ==============================================

class DatabaseError(ChannelAgentError):
    """Базовое исключение для базы данных"""
    pass


class DatabaseConnectionError(DatabaseError):
    """Ошибка подключения к базе данных"""
    
    def __init__(self, database_path: str, details: Optional[str] = None):
        message = f"Не удалось подключиться к базе данных: {database_path}"
        super().__init__(message, details)
        self.database_path = database_path


class DatabaseMigrationError(DatabaseError):
    """Ошибка миграции базы данных"""
    
    def __init__(self, migration_name: str, details: Optional[str] = None):
        message = f"Ошибка миграции: {migration_name}"
        super().__init__(message, details)
        self.migration_name = migration_name


class RecordNotFoundError(DatabaseError):
    """Запись не найдена в базе данных"""
    
    def __init__(self, table: str, record_id: Any):
        message = f"Запись не найдена в таблице {table}: ID={record_id}"
        super().__init__(message)
        self.table = table
        self.record_id = record_id


class DuplicateRecordError(DatabaseError):
    """Попытка создать дублирующуюся запись"""
    
    def __init__(self, table: str, field: str, value: Any):
        message = f"Запись уже существует в таблице {table}: {field}={value}"
        super().__init__(message)
        self.table = table
        self.field = field
        self.value = value


# ==============================================
# ИСКЛЮЧЕНИЯ TELEGRAM ПАРСИНГА
# ==============================================

class TelegramParsingError(ChannelAgentError):
    """Ошибка парсинга ссылок Telegram"""
    
    def __init__(self, link: str, details: Optional[str] = None):
        message = f"Ошибка парсинга ссылки Telegram: {link}"
        super().__init__(message, details)
        self.link = link


# ==============================================
# ИСКЛЮЧЕНИЯ ПЛАНИРОВЩИКА
# ==============================================

class SchedulerError(ChannelAgentError):
    """Базовое исключение для планировщика"""
    pass


class TaskExecutionError(SchedulerError):
    """Ошибка выполнения задачи планировщика"""
    
    def __init__(self, task_name: str, details: Optional[str] = None):
        message = f"Ошибка выполнения задачи: {task_name}"
        super().__init__(message, details)
        self.task_name = task_name


class CoinGeckoAPIError(SchedulerError):
    """Ошибка API CoinGecko"""
    
    def __init__(self, status_code: Optional[int] = None, details: Optional[str] = None):
        if status_code:
            message = f"Ошибка CoinGecko API (код {status_code})"
        else:
            message = "Ошибка CoinGecko API"
        super().__init__(message, details)
        self.status_code = status_code