"""
Модуль конфигурации приложения
Загружает и валидирует переменные окружения
"""

import os
from typing import List, Optional
from pathlib import Path

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Сторонние библиотеки
try:
    # Для pydantic v2
    from pydantic_settings import BaseSettings
    from pydantic import field_validator
    PYDANTIC_V2 = True
except ImportError:
    try:
        # Для pydantic v1
        from pydantic import BaseSettings, validator
        field_validator = validator
        PYDANTIC_V2 = False
    except ImportError:
        raise ImportError("Необходимо установить pydantic: pip install pydantic>=1.10.0")
import pytz

# Настройка логгера модуля
logger = logger.bind(module="config")


class Config(BaseSettings):
    """Конфигурация приложения с валидацией"""
    
    # Telegram Bot
    BOT_TOKEN: str
    OWNER_ID: int
    
    # Telegram UserBot
    API_ID: int
    API_HASH: str
    PHONE_NUMBER: Optional[str] = None  # Теперь вводится через бота
    
    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    # Channel settings
    MONITORING_INTERVAL: int = 300
    RELEVANCE_THRESHOLD: int = 6
    
    # Database
    DATABASE_PATH: str = "./data/channel_agent.db"
    
    # Target channel
    TARGET_CHANNEL_ID: int
    
    # Daily posts
    DAILY_POST_ENABLED: bool = False
    DAILY_POST_TIME: str = "09:00"
    TIMEZONE: str = "Europe/Moscow"
    
    # CoinGecko
    COINGECKO_COINS: str = "bitcoin,ethereum,solana"

    # SyntraAI API
    SYNTRA_API_URL: str = "http://localhost:8003"
    SYNTRA_STATS_API_KEY: Optional[str] = None
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_ROTATION: str = "10 MB"
    LOG_RETENTION: str = "30 days"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @field_validator("BOT_TOKEN")
    @classmethod  
    def validate_bot_token(cls, v: str) -> str:
        """Валидация токена бота"""
        if not v or len(v.split(':')) != 2:
            raise ValueError("Неверный формат BOT_TOKEN")
        return v
    
    @field_validator("OWNER_ID")
    @classmethod
    def validate_owner_id(cls, v: int) -> int:
        """Валидация ID владельца"""
        if v <= 0:
            raise ValueError("OWNER_ID должен быть положительным числом")
        return v
    
    @field_validator("API_ID")
    @classmethod
    def validate_api_id(cls, v: int) -> int:
        """Валидация API ID"""
        if v <= 0:
            raise ValueError("API_ID должен быть положительным числом")
        return v
    
    @field_validator("API_HASH")
    @classmethod
    def validate_api_hash(cls, v: str) -> str:
        """Валидация API Hash"""
        if not v or len(v) != 32:
            raise ValueError("API_HASH должен содержать 32 символа")
        return v
    
    # PHONE_NUMBER валидация убрана, так как номер теперь вводится через бота
    
    @field_validator("OPENAI_API_KEY")
    @classmethod
    def validate_openai_key(cls, v: str) -> str:
        """Валидация OpenAI API ключа"""
        if not v.startswith(('sk-', 'sk-proj-')):
            raise ValueError("Неверный формат OPENAI_API_KEY")
        return v
    
    @field_validator("MONITORING_INTERVAL")
    @classmethod
    def validate_monitoring_interval(cls, v: int) -> int:
        """Валидация интервала мониторинга"""
        if v < 60:
            raise ValueError("MONITORING_INTERVAL должен быть не менее 60 секунд")
        return v
    
    @field_validator("RELEVANCE_THRESHOLD")
    @classmethod
    def validate_relevance_threshold(cls, v: int) -> int:
        """Валидация порога релевантности"""
        if not 1 <= v <= 10:
            raise ValueError("RELEVANCE_THRESHOLD должен быть от 1 до 10")
        return v
    
    @field_validator("TARGET_CHANNEL_ID")
    @classmethod
    def validate_target_channel_id(cls, v: int) -> int:
        """Валидация ID целевого канала"""
        if v >= 0:
            raise ValueError("TARGET_CHANNEL_ID должен быть отрицательным (ID канала)")
        return v
    
    @field_validator("DAILY_POST_TIME")
    @classmethod
    def validate_daily_post_time(cls, v: str) -> str:
        """Валидация времени ежедневных постов"""
        try:
            from datetime import datetime
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError("DAILY_POST_TIME должен быть в формате HH:MM")
        return v
    
    @field_validator("TIMEZONE")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Валидация временной зоны"""
        try:
            pytz.timezone(v)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f"Неизвестная временная зона: {v}")
        return v
    
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Валидация уровня логирования"""
        valid_levels = ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL должен быть одним из: {', '.join(valid_levels)}")
        return v.upper()
    
    def get_database_dir(self) -> Path:
        """Получить директорию для базы данных"""
        db_path = Path(self.DATABASE_PATH)
        return db_path.parent
    
    def get_coingecko_coins_list(self) -> List[str]:
        """Получить список монет для CoinGecko"""
        return [coin.strip() for coin in self.COINGECKO_COINS.split(',')]
    
    def validate_all(self) -> bool:
        """Валидация всех обязательных параметров"""
        try:
            # Проверяем обязательные поля (PHONE_NUMBER теперь опциональный)
            required_fields = [
                self.BOT_TOKEN,
                self.OWNER_ID,
                self.API_ID, 
                self.API_HASH,
                self.OPENAI_API_KEY,
                self.TARGET_CHANNEL_ID
            ]
            
            if not all(required_fields):
                missing = []
                if not self.BOT_TOKEN:
                    missing.append("BOT_TOKEN")
                if not self.OWNER_ID:
                    missing.append("OWNER_ID")
                if not self.API_ID:
                    missing.append("API_ID")
                if not self.API_HASH:
                    missing.append("API_HASH")
                if not self.OPENAI_API_KEY:
                    missing.append("OPENAI_API_KEY")
                if not self.TARGET_CHANNEL_ID:
                    missing.append("TARGET_CHANNEL_ID")
                
                raise ValueError(f"Отсутствуют обязательные переменные: {', '.join(missing)}")
            
            # Создаем директории если не существуют
            self.get_database_dir().mkdir(parents=True, exist_ok=True)
            Path("logs").mkdir(exist_ok=True)
            
            logger.info("Конфигурация успешно валидирована")
            logger.debug("Интервал мониторинга: {} секунд", self.MONITORING_INTERVAL)
            logger.debug("Порог релевантности: {}", self.RELEVANCE_THRESHOLD)
            logger.debug("Модель OpenAI: {}", self.OPENAI_MODEL)
            
            return True
            
        except Exception as e:
            logger.error("Ошибка валидации конфигурации: {}", str(e))
            raise


# Глобальный экземпляр конфигурации
_config: Optional[Config] = None


def get_config() -> Config:
    """Получить глобальный экземпляр конфигурации"""
    global _config
    if _config is None:
        _config = Config()
        _config.validate_all()
    return _config


def reload_config() -> Config:
    """Перезагрузить конфигурацию"""
    global _config
    _config = None
    return get_config()