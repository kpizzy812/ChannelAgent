"""
Клиент Telethon для подключения к Telegram UserBot
Управляет соединением и базовой конфигурацией
"""

import asyncio
from pathlib import Path
from typing import Optional, List, Callable, Any
from datetime import datetime

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Сторонние библиотеки
from telethon import TelegramClient, events
from telethon.errors import (
    ApiIdInvalidError,
    FloodWaitError
)
from telethon.tl.types import User, Channel, Chat
from telethon.sessions import StringSession

# Локальные импорты
from src.utils.config import get_config
from src.utils.exceptions import (
    TelethonConnectionError,
    ChannelAccessError,
    ConfigurationError
)

# Настройка логгера модуля
logger = logger.bind(module="userbot")

# Глобальный клиент UserBot
_userbot_client: Optional['UserbotClient'] = None


class UserbotClient:
    """
    Клиент Telethon для работы с Telegram UserBot API
    Обеспечивает подключение и базовые операции
    """
    
    def __init__(self):
        """Инициализация клиента UserBot"""
        self.config = get_config()
        self.client: Optional[TelegramClient] = None
        self.is_running = False
        self.session_string_file = Path("data/userbot_session.txt")
        
        # Создаем директорию для сессии если не существует
        self.session_string_file.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info("Инициализирован UserBot клиент с StringSession")
    
    def _load_session_string(self) -> str:
        """Загрузить строковую сессию из файла"""
        try:
            if self.session_string_file.exists():
                session_string = self.session_string_file.read_text().strip()
                logger.debug("Загружена строковая сессия из файла")
                return session_string
            else:
                logger.debug("Файл строковой сессии не найден, создается новая")
                return ""
        except Exception as e:
            logger.warning("Ошибка загрузки строковой сессии: {}, создается новая", str(e))
            return ""
    
    def _save_session_string(self, session_string: str) -> None:
        """Сохранить строковую сессию в файл"""
        try:
            self.session_string_file.write_text(session_string)
            logger.debug("Строковая сессия сохранена в файл")
        except Exception as e:
            logger.error("Ошибка сохранения строковой сессии: {}", str(e))
    
    async def initialize(self) -> None:
        """Инициализировать Telethon клиент"""
        try:
            # Загружаем строковую сессию
            session_string = self._load_session_string()
            
            # Создаем клиент с StringSession
            self.client = TelegramClient(
                StringSession(session_string),
                self.config.API_ID,
                self.config.API_HASH,
                sequential_updates=True,  # Последовательная обработка обновлений
                timeout=30,
                retry_delay=1,
                flood_sleep_threshold=60
            )
            
            logger.info("Telethon клиент создан с StringSession")
            
        except ApiIdInvalidError as e:
            error_msg = f"Неверный API_ID: {self.config.API_ID}"
            logger.error(error_msg)
            raise TelethonConnectionError(error_msg)
        except Exception as e:
            error_msg = f"Ошибка создания Telethon клиента: {str(e)}"
            logger.error(error_msg)
            raise TelethonConnectionError(error_msg)
    
    async def connect(self) -> None:
        """Подключиться к Telegram"""
        if not self.client:
            raise TelethonConnectionError("Клиент не инициализирован")
        
        try:
            logger.info("Подключение к Telegram...")
            
            # Если уже подключен, сначала отключаемся
            if self.client.is_connected():
                logger.debug("Клиент уже подключен, переподключаемся...")
                await self.client.disconnect()
                await asyncio.sleep(1)  # Небольшая задержка
            
            await self.client.connect()
            
            # Проверяем успешность подключения
            if not self.client.is_connected():
                raise TelethonConnectionError("Не удалось установить соединение")
                
            logger.info("Подключение к серверам Telegram установлено")
            
        except Exception as e:
            error_msg = f"Ошибка подключения к Telegram: {str(e)}"
            logger.error(error_msg)
            raise TelethonConnectionError(error_msg)
    
    async def is_user_authorized(self) -> bool:
        """Проверить авторизован ли пользователь"""
        if not self.client:
            return False
        return await self.client.is_user_authorized()
    
    async def send_code_request(self, phone: str) -> Any:
        """Запросить SMS код"""
        if not self.client:
            raise TelethonConnectionError("Клиент не инициализирован")
        
        logger.info("Запрос SMS кода для номера: {}", phone)
        return await self.client.send_code_request(phone)
    
    async def sign_in(self, phone: str = None, code: str = None, password: str = None) -> Any:
        """Войти в систему с кодом или паролем"""
        if not self.client:
            raise TelethonConnectionError("Клиент не инициализирован")
        
        if password:
            logger.info("Вход с 2FA паролем")
            return await self.client.sign_in(password=password)
        elif phone and code:
            logger.info("Вход с SMS кодом")
            return await self.client.sign_in(phone, code)
        else:
            raise ValueError("Необходимо указать либо телефон+код, либо пароль")
    
    async def get_me(self) -> Any:
        """Получить информацию о текущем пользователе"""
        if not self.client:
            raise TelethonConnectionError("Клиент не инициализирован")
        
        return await self.client.get_me()
    
    async def save_session(self) -> None:
        """Сохранить текущую сессию"""
        try:
            if self.client and hasattr(self.client.session, 'save'):
                session_string = self.client.session.save()
                if session_string:
                    self._save_session_string(session_string)
                    logger.info("Сессия успешно сохранена")
                else:
                    logger.warning("Пустая строка сессии, не сохраняем")
        except Exception as e:
            logger.error("Ошибка сохранения сессии: {}", str(e))
    
    async def disconnect(self) -> None:
        """Отключиться от Telegram"""
        if self.client and self.client.is_connected():
            try:
                # Сохраняем сессию перед отключением
                await self.save_session()
                
                await self.client.disconnect()
                logger.info("Отключение от Telegram выполнено")
            except Exception as e:
                logger.error("Ошибка при отключении: {}", str(e))
        
        self.is_running = False
    
    async def start_monitoring(self) -> None:
        """Запустить улучшенный мониторинг с heartbeat проверками"""
        if not self.client:
            raise TelethonConnectionError("Клиент не инициализирован")
        
        self.is_running = True
        logger.info("Запуск улучшенного мониторинга UserBot...")
        
        last_heartbeat = datetime.now()
        heartbeat_interval = 300  # 5 минут
        connection_issues_count = 0
        max_connection_issues = 5
        
        try:
            # Основной цикл мониторинга с проверками
            while self.is_running:
                try:
                    # Базовая проверка соединения
                    if not self.client.is_connected():
                        logger.warning("Соединение потеряно в процессе мониторинга")
                        connection_issues_count += 1
                        
                        if connection_issues_count >= max_connection_issues:
                            logger.error("Слишком много проблем с соединением ({}), завершаем мониторинг", 
                                       connection_issues_count)
                            break
                        
                        # Пытаемся переподключиться
                        reconnect_success = await self.ensure_connected()
                        if not reconnect_success:
                            logger.error("Не удалось восстановить соединение, пауза перед повтором")
                            await asyncio.sleep(30)
                            continue
                        else:
                            # Сбрасываем счетчик проблем при успешном переподключении
                            connection_issues_count = 0
                    
                    # Периодическая heartbeat проверка
                    now = datetime.now()
                    if (now - last_heartbeat).total_seconds() > heartbeat_interval:
                        try:
                            logger.debug("Выполняем heartbeat проверку...")
                            await asyncio.wait_for(self.client.get_me(), timeout=15)
                            last_heartbeat = now
                            logger.debug("Heartbeat проверка прошла успешно")
                            
                            # Сбрасываем счетчик проблем при успешном heartbeat
                            if connection_issues_count > 0:
                                connection_issues_count = 0
                                logger.info("Соединение стабилизировалось, счетчик проблем сброшен")
                                
                        except Exception as heartbeat_error:
                            logger.warning("Heartbeat проверка не удалась: {}", str(heartbeat_error))
                            connection_issues_count += 1
                            
                            # При проблемах с heartbeat пытаемся переподключиться
                            if connection_issues_count >= 2:
                                logger.info("Проблемы с heartbeat, принудительное переподключение")
                                await self.ensure_connected()
                    
                    # Основная пауза цикла
                    await asyncio.sleep(5)
                    
                except asyncio.CancelledError:
                    logger.info("Мониторинг UserBot отменен")
                    raise
                    
                except Exception as loop_error:
                    logger.error("Ошибка в цикле мониторинга: {}", str(loop_error))
                    connection_issues_count += 1
                    
                    if connection_issues_count >= max_connection_issues:
                        logger.error("Критическое количество ошибок в цикле мониторинга, завершаем")
                        break
                    
                    # Пауза перед продолжением
                    await asyncio.sleep(10)
                
        except asyncio.CancelledError:
            logger.info("Мониторинг UserBot отменен")
            raise
        except Exception as e:
            logger.error("Критическая ошибка в процессе мониторинга: {}", str(e))
            raise
        finally:
            self.is_running = False
            logger.info("Мониторинг UserBot завершен (issues: {})", connection_issues_count)
    
    async def stop_monitoring(self) -> None:
        """Остановить мониторинг"""
        logger.info("Остановка мониторинга UserBot...")
        self.is_running = False
        await self.disconnect()
    
    def add_event_handler(
        self, 
        callback: Callable, 
        event: events.common.EventBuilder
    ) -> None:
        """Добавить обработчик события"""
        if not self.client:
            raise TelethonConnectionError("Клиент не инициализирован")
        
        self.client.add_event_handler(callback, event)
        logger.debug("Добавлен обработчик события: {}", event.__class__.__name__)
    
    async def get_entity_info(self, entity_id: int) -> dict:
        """Получить информацию о сущности (канал/чат/пользователь)"""
        if not self.client:
            raise TelethonConnectionError("Клиент не инициализирован")
        
        try:
            entity = await self.client.get_entity(entity_id)
            
            if isinstance(entity, Channel):
                return {
                    "type": "channel",
                    "id": entity.id,
                    "title": entity.title,
                    "username": entity.username,
                    "participants_count": getattr(entity, 'participants_count', None)
                }
            elif isinstance(entity, Chat):
                return {
                    "type": "chat", 
                    "id": entity.id,
                    "title": entity.title,
                    "participants_count": getattr(entity, 'participants_count', None)
                }
            elif isinstance(entity, User):
                return {
                    "type": "user",
                    "id": entity.id,
                    "first_name": entity.first_name,
                    "last_name": entity.last_name,
                    "username": entity.username
                }
            else:
                return {"type": "unknown", "id": entity_id}
                
        except Exception as e:
            logger.error("Ошибка получения информации о сущности {}: {}", entity_id, str(e))
            raise ChannelAccessError(str(entity_id), str(e))
    
    async def check_channel_access(self, channel_id: int) -> bool:
        """Проверить доступ к каналу"""
        try:
            entity = await self.client.get_entity(channel_id)
            # Пытаемся получить последнее сообщение
            async for message in self.client.iter_messages(entity, limit=1):
                break
            
            logger.debug("Доступ к каналу {} подтвержден", channel_id)
            return True
            
        except Exception as e:
            logger.warning("Нет доступа к каналу {}: {}", channel_id, str(e))
            return False
    
    @property
    def is_connected(self) -> bool:
        """Проверить состояние подключения"""
        return self.client is not None and self.client.is_connected()
    
    async def ensure_connected(self) -> bool:
        """
        Улучшенная проверка и восстановление соединения с множественными попытками
        
        Returns:
            True если соединение активно, False при ошибке
        """
        try:
            if not self.client:
                logger.error("Клиент не инициализирован")
                return False
            
            # Проверяем текущее соединение через простой API вызов
            try:
                if self.client.is_connected():
                    # Дополнительная проверка - пытаемся сделать простой запрос
                    await asyncio.wait_for(self.client.get_me(), timeout=10)
                    logger.debug("Соединение проверено и активно")
                    return True
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning("Проблема с соединением обнаружена: {}", str(e))
                # Продолжаем к переподключению
                
            logger.warning("Соединение потеряно, пытаемся восстановить...")
            
            # Множественные попытки переподключения с экспоненциальной задержкой
            max_attempts = 5
            base_delay = 2
            
            for attempt in range(max_attempts):
                try:
                    logger.info("Попытка переподключения {}/{}", attempt + 1, max_attempts)
                    
                    # Отключаемся если еще подключены
                    if self.client.is_connected():
                        await self.client.disconnect()
                        await asyncio.sleep(1)
                    
                    # Переподключаемся
                    await self.connect()
                    
                    # Проверяем что соединение работает
                    if self.client.is_connected():
                        # Дополнительная проверка через API вызов
                        await asyncio.wait_for(self.client.get_me(), timeout=15)
                        logger.info("Соединение восстановлено успешно за {} попыток", attempt + 1)
                        return True
                    
                except Exception as attempt_error:
                    logger.warning("Ошибка попытки переподключения {}: {}", attempt + 1, str(attempt_error))
                    
                    # Ждем перед следующей попыткой (экспоненциальная задержка)
                    if attempt < max_attempts - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.info("Ожидание {} сек перед следующей попыткой", delay)
                        await asyncio.sleep(delay)
            
            logger.error("Не удалось восстановить соединение после {} попыток", max_attempts)
            return False
                
        except Exception as e:
            logger.error("Критическая ошибка при проверке/восстановлении соединения: {}", str(e))
            return False
    
    async def safe_api_call(self, func, *args, **kwargs):
        """
        Улучшенный безопасный вызов Telegram API с автоматическим переподключением
        
        Args:
            func: Функция API для вызова
            *args: Аргументы для функции
            **kwargs: Именованные аргументы
            
        Returns:
            Результат вызова функции или None при ошибке
        """
        max_retries = 5
        base_delay = 1
        
        for attempt in range(max_retries):
            try:
                # Проверяем соединение перед вызовом
                if not await self.ensure_connected():
                    logger.error("Не удалось установить соединение для API вызова (попытка {})", attempt + 1)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(base_delay * (2 ** attempt))
                        continue
                    return None
                
                # Выполняем API вызов с таймаутом
                try:
                    result = await asyncio.wait_for(func(*args, **kwargs), timeout=30)
                    logger.debug("API вызов выполнен успешно за {} попыток", attempt + 1)
                    return result
                except asyncio.TimeoutError:
                    logger.warning("Таймаут API вызова на попытке {}/{}", attempt + 1, max_retries)
                    raise  # Будет обработан как сетевая ошибка ниже
                
            except Exception as e:
                error_str = str(e).lower()
                error_type = type(e).__name__
                
                # Расширенная классификация ошибок
                network_errors = [
                    "disconnect", "connection", "timeout", "network", "unreachable",
                    "timeouterror", "connectionerror", "gaierror", "oserror"
                ]
                
                telegram_rate_limit_errors = [
                    "floodwaiterror", "slowmodewaiterror", "ratelimiterror"
                ]
                
                permanent_errors = [
                    "unauthorized", "forbidden", "notfound", "badrequest"
                ]
                
                # Проверяем тип ошибки
                is_network_error = any(err in error_str for err in network_errors)
                is_rate_limit = any(err in error_str for err in telegram_rate_limit_errors)
                is_permanent = any(err in error_str for err in permanent_errors)
                
                if is_rate_limit:
                    # Для rate limit ошибок ждем дольше
                    logger.warning("Rate limit ошибка на попытке {}/{}: {}", attempt + 1, max_retries, str(e))
                    if attempt < max_retries - 1:
                        wait_time = 60 + (attempt * 30)  # Прогрессивно увеличиваем время ожидания
                        logger.info("Ожидание {} сек из-за rate limit", wait_time)
                        await asyncio.sleep(wait_time)
                        continue
                    
                elif is_network_error:
                    logger.warning("Сетевая ошибка на попытке {}/{}: {} ({})", 
                                 attempt + 1, max_retries, error_type, str(e))
                    
                    if attempt < max_retries - 1:
                        # Экспоненциальная задержка для сетевых ошибок
                        delay = base_delay * (2 ** attempt)
                        logger.info("Ожидание {} сек перед повтором", delay)
                        await asyncio.sleep(delay)
                        continue
                        
                elif is_permanent:
                    # Перманентные ошибки - не повторяем
                    logger.error("Перманентная ошибка API: {} - {}", error_type, str(e))
                    return None
                    
                else:
                    # Неизвестная ошибка - логируем и повторяем с осторожностью
                    logger.warning("Неизвестная ошибка API на попытке {}/{}: {} - {}", 
                                 attempt + 1, max_retries, error_type, str(e))
                    
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                        continue
        
        logger.error("Все {} попыток API вызова исчерпаны", max_retries)
        return None


async def get_userbot_client() -> UserbotClient:
    """Получить глобальный экземпляр UserBot клиента"""
    global _userbot_client
    
    if _userbot_client is None:
        _userbot_client = UserbotClient()
        await _userbot_client.initialize()
    
    return _userbot_client


async def initialize_userbot() -> UserbotClient:
    """Инициализировать и подключить UserBot"""
    logger.info("Инициализация UserBot...")
    
    client = await get_userbot_client()
    await client.connect()
    
    logger.info("UserBot инициализирован и подключен")
    return client


async def shutdown_userbot() -> None:
    """Завершить работу UserBot"""
    global _userbot_client
    
    if _userbot_client:
        logger.info("Завершение работы UserBot...")
        await _userbot_client.stop_monitoring()
        _userbot_client = None
        logger.info("UserBot завершен")


async def reset_userbot_session() -> bool:
    """Принудительно сбросить сессию UserBot и удалить файл сессии"""
    global _userbot_client
    
    try:
        logger.info("Принудительный сброс сессии UserBot...")
        
        # Отключаем текущий клиент если есть
        if _userbot_client:
            try:
                if _userbot_client.client and _userbot_client.client.is_connected():
                    await _userbot_client.client.disconnect()
            except Exception as e:
                logger.warning("Ошибка отключения клиента при сбросе: {}", str(e))
            
            # Сбрасываем глобальный клиент
            _userbot_client = None
        
        # Удаляем файл сессии
        session_file = Path("data/userbot_session.txt")
        if session_file.exists():
            session_file.unlink()
            logger.info("Файл сессии удален: {}", session_file)
        else:
            logger.debug("Файл сессии не существует: {}", session_file)
        
        logger.info("✅ Сессия UserBot сброшена полностью")
        return True
        
    except Exception as e:
        logger.error("Ошибка сброса сессии UserBot: {}", str(e))
        return False