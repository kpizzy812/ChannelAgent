"""
Менеджер авторизации UserBot
Координирует процесс авторизации между ботом и Telethon клиентом
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any
from datetime import datetime, timedelta

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.utils.exceptions import UserbotError

# Настройка логгера модуля
logger = logger.bind(module="userbot_auth_manager")


class AuthStatus(Enum):
    """Статусы авторизации UserBot"""
    DISCONNECTED = "disconnected"    # Не подключен
    CONNECTING = "connecting"        # Процесс подключения
    WAITING_CODE = "waiting_code"    # Ожидание SMS кода
    WAITING_PASSWORD = "waiting_password"  # Ожидание 2FA пароля
    CONNECTED = "connected"          # Подключен и работает
    ERROR = "error"                  # Ошибка подключения


@dataclass
class AuthResult:
    """Результат операции авторизации"""
    success: bool
    error: Optional[str] = None
    phone_number: Optional[str] = None
    requires_password: bool = False
    data: Optional[Any] = None


class UserbotAuthManager:
    """Менеджер авторизации UserBot"""
    
    def __init__(self):
        """Инициализация менеджера авторизации"""
        self.status = AuthStatus.DISCONNECTED
        self.client = None
        self.auth_phone = None
        self.last_error = None
        
        # Таймауты
        self.code_timeout = 300  # 5 минут на ввод кода
        self.password_timeout = 120  # 2 минуты на ввод пароля
        
        logger.info("Инициализирован менеджер авторизации UserBot")
    
    async def _check_existing_session(self) -> None:
        """Проверить существующую сессию и установить статус"""
        try:
            # Импортируем клиент здесь чтобы избежать циклических импортов
            from src.userbot.client import get_userbot_client
            
            # Создаем клиент и пытаемся подключиться
            client = await get_userbot_client()
            await client.connect()
            
            # Проверяем авторизацию
            if await client.is_user_authorized():
                self.status = AuthStatus.CONNECTED
                self.client = client
                # Получаем номер телефона из конфигурации
                from src.utils.config import get_config
                config = get_config()
                self.auth_phone = config.PHONE_NUMBER
                logger.info("UserBot уже авторизован - статус установлен как CONNECTED")
            else:
                # Отключаемся, если не авторизован
                await client.disconnect()
                logger.debug("Сессия найдена, но пользователь не авторизован")
                
        except Exception as e:
            logger.debug("Не удалось проверить существующую сессию: {}", str(e))
    
    async def get_status(self) -> AuthStatus:
        """Получить текущий статус авторизации"""
        # Если статус не определен, проверяем существующую сессию
        if self.status == AuthStatus.DISCONNECTED:
            try:
                # Проверяем наличие сохраненной сессии
                await self._check_existing_session()
            except Exception as e:
                logger.debug("Ошибка проверки существующей сессии: {}", str(e))
        
        return self.status
    
    async def start_auth(self) -> AuthResult:
        """Начать процесс авторизации (устаревший метод, используется для обратной совместимости)"""
        try:
            if self.status == AuthStatus.CONNECTED:
                return AuthResult(success=False, error="UserBot уже подключен")
            
            if self.status == AuthStatus.CONNECTING:
                return AuthResult(success=False, error="Авторизация уже в процессе")
            
            logger.info("Начало процесса авторизации UserBot")
            
            # Импортируем клиент здесь чтобы избежать циклических импортов
            from src.userbot.client import get_userbot_client
            
            self.status = AuthStatus.CONNECTING
            self.client = await get_userbot_client()
            
            if not self.client:
                raise UserbotError("Не удалось создать UserBot клиент")
            
            # Получаем номер телефона из конфигурации
            from src.utils.config import get_config
            config = get_config()
            self.auth_phone = config.PHONE_NUMBER
            
            # Запускаем процесс авторизации
            await self.client.connect()
            
            # Проверяем, не авторизованы ли уже
            if await self.client.is_user_authorized():
                self.status = AuthStatus.CONNECTED
                # Сохраняем сессию после успешной проверки авторизации
                await self.client.save_session()
                logger.info("UserBot уже авторизован")
                return AuthResult(success=True, phone_number=self.auth_phone)
            
            # Отправляем запрос на SMS код
            self.status = AuthStatus.WAITING_CODE
            sent_code = await self.client.send_code_request(self.auth_phone)
            
            logger.info("SMS код запрошен для номера: {}", self.auth_phone)
            
            return AuthResult(
                success=True, 
                phone_number=self.auth_phone,
                data=sent_code
            )
            
        except Exception as e:
            self.status = AuthStatus.ERROR
            self.last_error = str(e)
            logger.error("Ошибка начала авторизации: {}", str(e))
            return AuthResult(success=False, error=str(e))
    
    async def start_auth_with_phone(self, phone_number: str) -> AuthResult:
        """Начать процесс авторизации с указанным номером телефона"""
        try:
            if self.status == AuthStatus.CONNECTED:
                return AuthResult(success=False, error="UserBot уже подключен")
            
            if self.status == AuthStatus.CONNECTING:
                return AuthResult(success=False, error="Авторизация уже в процессе")
            
            logger.info("Начало процесса авторизации UserBot с номером: {}", phone_number)
            
            # Импортируем клиент здесь чтобы избежать циклических импортов
            from src.userbot.client import get_userbot_client
            
            self.status = AuthStatus.CONNECTING
            self.client = await get_userbot_client()
            
            if not self.client:
                raise UserbotError("Не удалось создать UserBot клиент")
            
            # Используем переданный номер телефона
            self.auth_phone = phone_number
            
            # Запускаем процесс авторизации
            await self.client.connect()
            
            # Проверяем, не авторизованы ли уже
            if await self.client.is_user_authorized():
                self.status = AuthStatus.CONNECTED
                # Сохраняем сессию после успешной проверки авторизации
                await self.client.save_session()
                logger.info("UserBot уже авторизован")
                return AuthResult(success=True, phone_number=self.auth_phone)
            
            # Отправляем запрос на SMS код
            self.status = AuthStatus.WAITING_CODE
            sent_code = await self.client.send_code_request(self.auth_phone)
            
            logger.info("SMS код запрошен для номера: {}", self.auth_phone)
            
            return AuthResult(
                success=True, 
                phone_number=self.auth_phone,
                data=sent_code
            )
            
        except Exception as e:
            self.status = AuthStatus.ERROR
            self.last_error = str(e)
            logger.error("Ошибка начала авторизации с номером {}: {}", phone_number, str(e))
            return AuthResult(success=False, error=str(e))
    
    async def submit_code(self, code: str) -> AuthResult:
        """Отправить SMS код для авторизации"""
        try:
            if self.status != AuthStatus.WAITING_CODE:
                return AuthResult(success=False, error="Не ожидается ввод кода")
            
            if not self.client:
                return AuthResult(success=False, error="Клиент не инициализирован")
            
            logger.info("Проверка SMS кода: {}", code)
            
            try:
                # Попытка входа с кодом
                user = await self.client.sign_in(
                    phone=self.auth_phone,
                    code=code
                )
                
                # Успешная авторизация
                self.status = AuthStatus.CONNECTED
                # Сохраняем сессию после успешной авторизации
                await self.client.save_session()
                logger.info("Успешная авторизация UserBot")
                
                return AuthResult(success=True)
                
            except Exception as sign_in_error:
                # Проверяем, нужен ли 2FA пароль
                error_msg = str(sign_in_error).lower()
                
                if "password" in error_msg or "2fa" in error_msg:
                    self.status = AuthStatus.WAITING_PASSWORD
                    logger.info("Требуется 2FA пароль")
                    
                    return AuthResult(
                        success=True,
                        requires_password=True
                    )
                else:
                    # Неверный код или другая ошибка
                    logger.warning("Ошибка входа с кодом: {}", str(sign_in_error))
                    return AuthResult(
                        success=False,
                        error=f"Неверный код или ошибка входа: {str(sign_in_error)}"
                    )
                    
        except Exception as e:
            self.status = AuthStatus.ERROR
            self.last_error = str(e)
            logger.error("Ошибка отправки кода: {}", str(e))
            return AuthResult(success=False, error=str(e))
    
    async def submit_password(self, password: str) -> AuthResult:
        """Отправить 2FA пароль для авторизации"""
        try:
            if self.status != AuthStatus.WAITING_PASSWORD:
                return AuthResult(success=False, error="Не ожидается ввод пароля")
            
            if not self.client:
                return AuthResult(success=False, error="Клиент не инициализирован")
            
            logger.info("Проверка 2FA пароля")
            
            try:
                # Вход с 2FA паролем
                user = await self.client.sign_in(password=password)
                
                # Успешная авторизация
                self.status = AuthStatus.CONNECTED
                # Сохраняем сессию после успешной авторизации с 2FA
                await self.client.save_session()
                logger.info("Успешная авторизация UserBot с 2FA")
                
                return AuthResult(success=True)
                
            except Exception as sign_in_error:
                logger.warning("Ошибка входа с паролем: {}", str(sign_in_error))
                return AuthResult(
                    success=False,
                    error=f"Неверный пароль: {str(sign_in_error)}"
                )
                
        except Exception as e:
            self.status = AuthStatus.ERROR
            self.last_error = str(e)
            logger.error("Ошибка отправки пароля: {}", str(e))
            return AuthResult(success=False, error=str(e))
    
    async def disconnect(self) -> AuthResult:
        """Отключить UserBot"""
        try:
            logger.info("Отключение UserBot")
            
            # Используем принудительный сброс для полной очистки
            return await self.force_reset()
            
        except Exception as e:
            logger.error("Ошибка отключения UserBot: {}", str(e))
            return AuthResult(success=False, error=str(e))
    
    async def is_connected(self) -> bool:
        """Проверить подключен ли UserBot"""
        return self.status == AuthStatus.CONNECTED and self.client is not None
    
    async def get_client(self):
        """Получить подключенный клиент UserBot"""
        if await self.is_connected():
            return self.client
        return None
    
    def get_last_error(self) -> Optional[str]:
        """Получить последнюю ошибку"""
        return self.last_error
    
    async def reset_auth(self) -> None:
        """Сбросить состояние авторизации"""
        logger.info("Сброс состояния авторизации")
        
        self.status = AuthStatus.DISCONNECTED
        self.auth_phone = None
        self.last_error = None

    async def force_reset(self) -> AuthResult:
        """Принудительный полный сброс UserBot - удаление сессии и сброс всех состояний"""
        try:
            logger.info("🔄 Принудительный полный сброс UserBot...")
            
            # Импортируем функцию сброса сессии
            from src.userbot.client import reset_userbot_session
            
            # Сбрасываем состояние менеджера авторизации
            self.status = AuthStatus.DISCONNECTED
            self.client = None
            self.auth_phone = None
            self.last_error = None
            
            # Сбрасываем клиент и удаляем файл сессии
            success = await reset_userbot_session()
            
            if success:
                logger.info("✅ Принудительный сброс UserBot выполнен успешно")
                return AuthResult(success=True)
            else:
                logger.error("❌ Ошибка при принудительном сбросе UserBot")
                return AuthResult(success=False, error="Не удалось сбросить сессию")
                
        except Exception as e:
            logger.error("Ошибка принудительного сброса UserBot: {}", str(e))
            return AuthResult(success=False, error=str(e))


# Глобальный экземпляр менеджера авторизации
_auth_manager: Optional[UserbotAuthManager] = None


def get_auth_manager() -> UserbotAuthManager:
    """Получить глобальный экземпляр менеджера авторизации"""
    global _auth_manager
    
    if _auth_manager is None:
        _auth_manager = UserbotAuthManager()
    
    return _auth_manager


async def initialize_auth_manager() -> UserbotAuthManager:
    """Инициализировать менеджер авторизации"""
    manager = get_auth_manager()
    logger.info("Менеджер авторизации UserBot инициализирован")
    return manager


async def reset_auth_manager() -> AuthResult:
    """Полный сброс менеджера авторизации - создает новый экземпляр"""
    global _auth_manager
    
    try:
        logger.info("🔄 Полный сброс менеджера авторизации...")
        
        # Если есть существующий менеджер, принудительно сбрасываем его
        if _auth_manager:
            await _auth_manager.force_reset()
        
        # Создаем новый экземпляр менеджера авторизации
        _auth_manager = UserbotAuthManager()
        
        logger.info("✅ Менеджер авторизации полностью сброшен")
        return AuthResult(success=True)
        
    except Exception as e:
        logger.error("Ошибка полного сброса менеджера авторизации: {}", str(e))
        return AuthResult(success=False, error=str(e))