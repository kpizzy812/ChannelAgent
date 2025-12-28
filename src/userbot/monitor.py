"""
Основной модуль мониторинга каналов
Координирует работу всех компонентов UserBot
"""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.userbot.client import get_userbot_client, UserbotClient
from src.userbot.filters import get_message_filters, MessageFilters
from src.userbot.handlers.new_message import register_message_handlers, get_new_message_handler
from src.database.connection import get_db_connection
from src.utils.config import get_config
from src.utils.exceptions import TelethonConnectionError, DatabaseError

# Настройка логгера модуля
logger = logger.bind(module="userbot_monitor")


class ChannelMonitor:
    """
    Главный класс мониторинга каналов
    Управляет всем процессом мониторинга и координирует компоненты
    """
    
    def __init__(self):
        """Инициализация монитора каналов"""
        self.config = get_config()
        self.client: Optional[UserbotClient] = None
        self.message_filters: Optional[MessageFilters] = None
        self.is_monitoring = False
        self.start_time: Optional[datetime] = None
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Восстанавливаем состояние мониторинга из файла состояния
        asyncio.create_task(self._load_monitoring_state())
        
        logger.debug("Инициализирован монитор каналов")
    
    async def initialize(self) -> None:
        """Инициализировать все компоненты"""
        try:
            logger.info("Инициализация компонентов UserBot...")
            
            # Инициализируем клиент
            self.client = await get_userbot_client()
            logger.debug("UserBot клиент инициализирован")
            
            # Инициализируем фильтры
            self.message_filters = get_message_filters()
            logger.debug("Фильтры сообщений инициализированы")
            
            # Проверяем наличие каналов для мониторинга
            monitored_channels = await self.message_filters.get_monitored_channels()
            if not monitored_channels:
                logger.warning("Нет активных каналов для мониторинга")
                await self._add_sample_channels()
            
            logger.info("Компоненты UserBot инициализированы успешно")
            
        except Exception as e:
            logger.error("Ошибка инициализации UserBot: {}", str(e))
            raise TelethonConnectionError(f"Не удалось инициализировать UserBot: {str(e)}")
    
    async def start_monitoring(self) -> None:
        """Запустить мониторинг каналов"""
        if self.is_monitoring:
            logger.warning("Мониторинг уже запущен")
            return
        
        if not self.client:
            raise TelethonConnectionError("Клиент не инициализирован")
        
        try:
            logger.info("Запуск мониторинга каналов...")
            
            # Подключаемся к Telegram
            await self.client.connect()
            logger.info("Подключение к Telegram установлено")
            
            # Проверяем доступ к каналам
            await self._check_channel_access()
            
            # Регистрируем обработчики событий
            await register_message_handlers(self.client.client)
            logger.info("Обработчики событий зарегистрированы")
            
            # Отмечаем начало мониторинга
            self.is_monitoring = True
            self.start_time = datetime.now()
            
            # Сохраняем состояние мониторинга
            await self._save_monitoring_state()
            
            # Запускаем мониторинг в отдельной задаче
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            logger.info("✅ Мониторинг каналов запущен успешно")
            
        except Exception as e:
            self.is_monitoring = False
            logger.error("Ошибка запуска мониторинга: {}", str(e))
            raise TelethonConnectionError(f"Не удалось запустить мониторинг: {str(e)}")
    
    async def stop_monitoring(self) -> None:
        """Остановить мониторинг каналов"""
        if not self.is_monitoring:
            logger.warning("Мониторинг не запущен")
            return
        
        logger.info("Остановка мониторинга каналов...")
        
        try:
            # Отменяем задачу мониторинга
            if self.monitoring_task and not self.monitoring_task.done():
                self.monitoring_task.cancel()
                try:
                    await self.monitoring_task
                except asyncio.CancelledError:
                    logger.debug("Задача мониторинга отменена")
            
            # Отключаемся от Telegram
            if self.client:
                await self.client.stop_monitoring()
            
            # Сбрасываем состояние
            self.is_monitoring = False
            self.start_time = None
            self.monitoring_task = None
            
            # Сохраняем состояние мониторинга
            await self._save_monitoring_state()
            
            logger.info("🛑 Мониторинг каналов остановлен")
            
        except Exception as e:
            logger.error("Ошибка остановки мониторинга: {}", str(e))
    
    async def _monitoring_loop(self) -> None:
        """Основной цикл мониторинга"""
        try:
            logger.info("Основной цикл мониторинга запущен")
            
            # Запускаем клиент в режиме мониторинга
            await self.client.start_monitoring()
            
        except asyncio.CancelledError:
            logger.info("Цикл мониторинга отменен")
            raise
        except Exception as e:
            logger.error("Критическая ошибка в цикле мониторинга: {}", str(e))
            self.is_monitoring = False
            raise
    
    async def _check_channel_access(self) -> None:
        """Проверить доступ ко всем отслеживаемым каналам"""
        if not self.client or not self.message_filters:
            return
        
        monitored_channels = await self.message_filters.get_monitored_channels()
        accessible_channels = []
        inaccessible_channels = []
        
        logger.info("Проверка доступа к {} каналам", len(monitored_channels))
        
        for channel_id in monitored_channels:
            try:
                if await self.client.check_channel_access(channel_id):
                    accessible_channels.append(channel_id)
                else:
                    inaccessible_channels.append(channel_id)
            except Exception as e:
                logger.warning("Ошибка проверки канала {}: {}", channel_id, str(e))
                inaccessible_channels.append(channel_id)
        
        logger.info("Доступные каналы: {}, недоступные: {}", 
                   len(accessible_channels), len(inaccessible_channels))
        
        if inaccessible_channels:
            logger.warning("Недоступные каналы: {}", inaccessible_channels)
    
    async def force_reregister_handlers(self) -> bool:
        """
        🔄 ПРИНУДИТЕЛЬНАЯ ПЕРЕРЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
        Фикс для проблемы с потерей событий от Telethon
        """
        try:
            if not self.client or not self.client.client:
                logger.error("Клиент не инициализирован для перерегистрации")
                return False
            
            logger.warning("🔄 ПРИНУДИТЕЛЬНАЯ ПЕРЕРЕГИСТРАЦИЯ обработчиков Telethon...")
            
            # 1. Удаляем все существующие обработчики
            try:
                # Очищаем обработчики Telethon
                self.client.client.list_event_handlers().clear()
                logger.info("✅ Старые обработчики очищены")
            except Exception as e:
                logger.warning("Ошибка очистки обработчиков: {}", str(e))
            
            # 2. Проверяем соединение
            if not await self.client.ensure_connected():
                logger.error("❌ Соединение потеряно, не можем перерегистрировать")
                return False
            
            # 3. Перерегистрируем обработчики
            from src.userbot.handlers.new_message import register_message_handlers
            await register_message_handlers(self.client.client)
            logger.info("✅ Обработчики перерегистрированы")
            
            # 4. Проверяем доступ к каналам
            await self._check_channel_access()
            
            # 5. Тестируем получение сообщений
            await self._test_channel_connectivity()
            
            logger.info("🎯 Перерегистрация обработчиков завершена успешно")
            return True
            
        except Exception as e:
            logger.error("❌ Критическая ошибка перерегистрации: {}", str(e))
            return False
    
    async def _test_channel_connectivity(self) -> None:
        """Тестировать получение последних сообщений из каналов"""
        try:
            if not self.client or not self.message_filters:
                return
            
            monitored_channels = await self.message_filters.get_monitored_channels()
            logger.info("🧪 Тестирование подключения к {} каналам", len(monitored_channels))
            
            working_channels = 0
            
            for channel_id in list(monitored_channels)[:5]:  # Тестируем первые 5 каналов
                try:
                    entity = await self.client.client.get_entity(channel_id)
                    
                    # Пытаемся получить последнее сообщение
                    async for message in self.client.client.iter_messages(entity, limit=1):
                        if message:
                            working_channels += 1
                            logger.debug("✅ Канал {} отвечает (последнее сообщение: {})", 
                                       channel_id, message.id)
                        break
                    
                    # Небольшая задержка между проверками
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.warning("❌ Канал {} не отвечает: {}", channel_id, str(e))
            
            logger.info("🧪 Результат теста: {}/{} каналов отвечают", 
                       working_channels, min(5, len(monitored_channels)))
            
        except Exception as e:
            logger.error("Ошибка тестирования подключения: {}", str(e))
    
    async def _add_sample_channels(self) -> None:
        """Добавить примеры каналов для тестирования (если нет активных)"""
        logger.info("Добавление примеров каналов для тестирования...")
        
        # Это примеры - в реальном использовании каналы должен добавить пользователь
        sample_channels = [
            # Примеры популярных крипто каналов (ID нужно заменить на реальные)
            # -1001234567890,  # Пример ID канала
        ]
        
        if not sample_channels:
            logger.warning("Нет каналов для добавления. Добавьте каналы через бот")
            return
        
        try:
            for channel_id in sample_channels:
                await self.message_filters.add_channel_to_monitoring(channel_id)
                logger.debug("Добавлен канал: {}", channel_id)
            
            logger.info("Добавлено {} примеров каналов", len(sample_channels))
            
        except Exception as e:
            logger.error("Ошибка добавления примеров каналов: {}", str(e))
    
    async def add_channel(self, channel_identifier: str) -> bool:
        """
        Добавить канал в мониторинг с ретроактивным сканированием
        
        Args:
            channel_identifier: Username канала или ID
            
        Returns:
            True если канал добавлен успешно
        """
        try:
            if not self.client:
                raise TelethonConnectionError("Клиент не инициализирован")
            
            # Получаем информацию о канале
            if channel_identifier.startswith('@'):
                channel_identifier = channel_identifier[1:]

            entity = await self.client.client.get_entity(channel_identifier)

            # ИСПРАВЛЕНО: Правильная конвертация channel_id
            if entity.id < 0:
                # ID уже правильный (например -1001234567890)
                channel_id = entity.id
            else:
                # ID положительный, добавляем префикс -100
                channel_id = int(f"-100{entity.id}")

            logger.info("Попытка добавить канал: {} (ID: {})", entity.title or channel_identifier, channel_id)
            
            # Проверяем и подписываемся на канал если нужно
            subscription_result = await self._ensure_channel_subscription(entity)
            if not subscription_result:
                logger.warning("Не удалось подписаться на канал {}", channel_identifier)
                # Продолжаем даже если подписка не удалась
            
            # Проверяем доступ к сообщениям канала
            if not await self.client.check_channel_access(channel_id):
                logger.error("Нет доступа к сообщениям канала {}", channel_identifier)
                return False
            
            # Добавляем в мониторинг
            await self.message_filters.add_channel_to_monitoring(channel_id)
            
            # Сохраняем информацию о канале в БД
            await self._save_channel_info(entity)
            
            logger.info("✅ Канал {} успешно добавлен в мониторинг", entity.title or channel_identifier)
            return True
            
        except Exception as e:
            logger.error("Ошибка добавления канала {}: {}", channel_identifier, str(e))
            return False
    
    async def _ensure_channel_subscription(self, entity) -> bool:
        """
        Убедиться что UserBot подписан на канал
        
        Args:
            entity: Сущность канала Telethon
            
        Returns:
            True если подписка успешна или уже существует
        """
        try:
            from telethon.tl.functions.channels import JoinChannelRequest
            from telethon.errors import (
                ChannelPrivateError, 
                ChannelInvalidError,
                UserAlreadyParticipantError,
                InviteHashExpiredError
            )
            
            # Проверяем, является ли это каналом (не чатом)
            if not hasattr(entity, 'broadcast'):
                logger.debug("Сущность {} не является каналом", getattr(entity, 'title', 'unknown'))
                return True  # Для чатов подписка не нужна
            
            # Если канал публичный, пытаемся подписаться
            if hasattr(entity, 'username') and entity.username:
                try:
                    await self.client.client(JoinChannelRequest(entity))
                    logger.info("✅ Успешно подписались на канал @{}", entity.username)
                    return True
                    
                except UserAlreadyParticipantError:
                    logger.debug("Уже подписаны на канал @{}", entity.username)
                    return True
                    
                except ChannelPrivateError:
                    logger.warning("Канал @{} приватный, нужна ссылка-приглашение", entity.username)
                    return False
                    
                except Exception as e:
                    logger.warning("Не удалось подписаться на канал @{}: {}", entity.username, str(e))
                    return False
            else:
                # Приватный канал - проверяем доступ без подписки
                logger.debug("Канал {} приватный, проверяем существующий доступ", 
                           getattr(entity, 'title', 'unknown'))
                
                # Пытаемся получить несколько сообщений для проверки доступа
                try:
                    message_count = 0
                    async for message in self.client.client.iter_messages(entity, limit=1):
                        message_count += 1
                        break
                    
                    if message_count > 0:
                        logger.debug("Доступ к приватному каналу подтвержден")
                        return True
                    else:
                        logger.warning("Нет доступа к приватному каналу")
                        return False
                        
                except Exception as e:
                    logger.warning("Нет доступа к приватному каналу: {}", str(e))
                    return False
            
        except Exception as e:
            logger.error("Ошибка проверки подписки на канал: {}", str(e))
            return False
    
    async def join_channel_by_invite_link(self, invite_link: str) -> bool:
        """
        Присоединиться к каналу по ссылке-приглашению
        
        Args:
            invite_link: Ссылка-приглашение (t.me/joinchat/...)
            
        Returns:
            True если успешно присоединились
        """
        try:
            from telethon.tl.functions.messages import ImportChatInviteRequest
            from telethon.errors import InviteHashExpiredError, InviteHashInvalidError
            
            # Извлекаем hash из ссылки
            if "joinchat/" in invite_link:
                invite_hash = invite_link.split("joinchat/")[-1]
            elif "+" in invite_link:
                invite_hash = invite_link.split("+")[-1]  # Для новых ссылок t.me/+hash
            else:
                logger.error("Неверный формат ссылки-приглашения: {}", invite_link)
                return False
            
            # Присоединяемся к каналу
            result = await self.client.client(ImportChatInviteRequest(invite_hash))
            
            logger.info("✅ Успешно присоединились к каналу по приглашению")
            return True
            
        except InviteHashExpiredError:
            logger.error("Ссылка-приглашение истекла: {}", invite_link)
            return False
        except InviteHashInvalidError:
            logger.error("Неверная ссылка-приглашение: {}", invite_link)
            return False
        except Exception as e:
            logger.error("Ошибка присоединения по ссылке {}: {}", invite_link, str(e))
            return False
    
    async def auto_join_channel(self, channel_data) -> bool:
        """
        Автоматически присоединиться к каналу используя данные из БД

        Args:
            channel_data: Объект Channel из БД с username/title/channel_id

        Returns:
            True если успешно присоединились или уже были участниками
        """
        try:
            if not self.client:
                logger.error("Клиент не инициализирован для присоединения к каналу")
                return False

            logger.info("Попытка присоединиться к каналу: {}",
                       channel_data.username or channel_data.title or channel_data.channel_id)

            # Пытаемся получить entity канала
            entity = None

            # Сначала пробуем по username если есть
            if channel_data.username:
                try:
                    entity = await self.client.client.get_entity(channel_data.username)
                    logger.debug("Получен entity по username: @{}", channel_data.username)
                except Exception as e:
                    logger.warning("Не удалось получить entity по username @{}: {}",
                                 channel_data.username, str(e))

            # Если не получилось, пробуем по channel_id
            if not entity and channel_data.channel_id:
                try:
                    entity = await self.client.client.get_entity(channel_data.channel_id)
                    logger.debug("Получен entity по channel_id: {}", channel_data.channel_id)
                except Exception as e:
                    logger.warning("Не удалось получить entity по channel_id {}: {}",
                                 channel_data.channel_id, str(e))

            # Если не получили entity - не можем присоединиться
            if not entity:
                logger.error("Не удалось получить entity для канала {}",
                           channel_data.username or channel_data.channel_id)
                return False

            # Используем существующий метод для обеспечения подписки
            subscription_result = await self._ensure_channel_subscription(entity)

            if subscription_result:
                logger.info("✅ Успешно присоединились к каналу: {}",
                           channel_data.username or channel_data.title)
                return True
            else:
                logger.warning("❌ Не удалось присоединиться к каналу: {}",
                             channel_data.username or channel_data.title)
                return False

        except Exception as e:
            logger.error("Ошибка автоматического присоединения к каналу: {}", str(e))
            return False

    async def join_all_channels(self) -> Dict[str, Any]:
        """
        Массовое вступление во все каналы из БД

        Returns:
            Dict с результатами: joined, failed, already_member, total
        """
        results = {
            "joined": 0,
            "failed": 0,
            "already_member": 0,
            "total": 0,
            "failed_channels": []
        }

        try:
            if not self.client or not self.client.is_connected:
                logger.error("Клиент не подключен для вступления в каналы")
                return results

            # Получаем все каналы из БД
            from src.database.crud.channel import get_channel_crud
            channel_crud = get_channel_crud()
            channels = await channel_crud.get_all_active()

            results["total"] = len(channels)
            logger.info("🔄 Начинаем вступление в {} каналов...", len(channels))

            from telethon.tl.functions.channels import JoinChannelRequest
            from telethon.errors import UserAlreadyParticipantError, ChannelPrivateError
            import asyncio

            for channel in channels:
                try:
                    # Пробуем получить entity по username
                    entity = None

                    if channel.username:
                        try:
                            entity = await self.client.client.get_entity(f"@{channel.username}")
                        except Exception:
                            pass

                    if not entity and channel.channel_id:
                        try:
                            entity = await self.client.client.get_entity(channel.channel_id)
                        except Exception:
                            pass

                    if not entity:
                        logger.warning("❌ Не найден канал: {} ({})",
                                     channel.username or channel.title, channel.channel_id)
                        results["failed"] += 1
                        results["failed_channels"].append(channel.username or str(channel.channel_id))
                        continue

                    # Пытаемся вступить
                    try:
                        await self.client.client(JoinChannelRequest(entity))
                        logger.info("✅ Вступили в канал: @{}", channel.username or channel.title)
                        results["joined"] += 1
                    except UserAlreadyParticipantError:
                        logger.debug("👍 Уже в канале: @{}", channel.username or channel.title)
                        results["already_member"] += 1
                    except ChannelPrivateError:
                        logger.warning("🔒 Приватный канал: @{}", channel.username or channel.title)
                        results["failed"] += 1
                        results["failed_channels"].append(channel.username or str(channel.channel_id))

                    # Небольшая задержка между вступлениями
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.warning("❌ Ошибка вступления в {}: {}",
                                 channel.username or channel.channel_id, str(e))
                    results["failed"] += 1
                    results["failed_channels"].append(channel.username or str(channel.channel_id))

            logger.info("📊 Результат вступления: joined={}, already={}, failed={}, total={}",
                       results["joined"], results["already_member"], results["failed"], results["total"])

            return results

        except Exception as e:
            logger.error("Ошибка массового вступления в каналы: {}", str(e))
            return results

    async def _save_channel_info(self, entity) -> None:
        """Сохранить информацию о канале в БД"""
        try:
            # ИСПРАВЛЕНО: Правильная конвертация channel_id для Telethon
            # Если entity.id уже отрицательный - используем как есть
            # Если положительный - добавляем префикс -100
            if hasattr(entity, 'id'):
                if entity.id < 0:
                    # ID уже правильный (например -1001234567890)
                    channel_id = entity.id
                else:
                    # ID положительный, добавляем префикс -100
                    channel_id = int(f"-100{entity.id}")
            else:
                logger.error("Entity не имеет атрибута id")
                return

            async with get_db_connection() as conn:
                await conn.execute(
                    """INSERT OR REPLACE INTO channels
                       (channel_id, username, title, is_active, created_at, updated_at)
                       VALUES (?, ?, ?, TRUE, datetime('now'), datetime('now'))""",
                    (channel_id, getattr(entity, 'username', None), getattr(entity, 'title', None))
                )
                await conn.commit()

            logger.debug("Информация о канале {} сохранена в БД", channel_id)

        except Exception as e:
            logger.error("Ошибка сохранения информации о канале: {}", str(e))
    
    
    def get_status(self) -> Dict[str, Any]:
        """Получить статус мониторинга"""
        uptime = None
        if self.start_time:
            uptime = datetime.now() - self.start_time
        
        try:
            handler_stats = get_new_message_handler().get_statistics() if self.is_monitoring else {}
        except:
            handler_stats = {}
        
        return {
            "is_monitoring": self.is_monitoring,
            "start_time": self.start_time,
            "uptime_seconds": uptime.total_seconds() if uptime else None,
            "client_connected": self.client.is_connected if self.client else False,
            "handler_statistics": handler_stats
        }
    
    async def _save_monitoring_state(self) -> None:
        """Сохранить состояние мониторинга в файл"""
        try:
            from pathlib import Path
            import json
            
            state_file = Path("data") / "monitoring_state.json"
            state_file.parent.mkdir(exist_ok=True)
            
            state = {
                "is_monitoring": self.is_monitoring,
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "last_updated": datetime.now().isoformat()
            }
            
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
                
            logger.debug("Состояние мониторинга сохранено: is_monitoring={}", self.is_monitoring)
            
        except Exception as e:
            logger.error("Ошибка сохранения состояния мониторинга: {}", str(e))
    
    async def _load_monitoring_state(self) -> None:
        """Загрузить состояние мониторинга из файла"""
        try:
            from pathlib import Path
            import json
            
            state_file = Path("data") / "monitoring_state.json"
            
            if not state_file.exists():
                logger.debug("Файл состояния мониторинга не найден, используем значения по умолчанию")
                return
            
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            # Восстанавливаем состояние
            self.is_monitoring = state.get("is_monitoring", False)
            
            if state.get("start_time"):
                try:
                    self.start_time = datetime.fromisoformat(state["start_time"])
                except:
                    self.start_time = None
            
            logger.debug("Состояние мониторинга загружено: is_monitoring={}", self.is_monitoring)
            
            # Если мониторинг был активен, но прошло много времени, сбрасываем
            if self.is_monitoring and self.start_time:
                hours_since_start = (datetime.now() - self.start_time).total_seconds() / 3600
                if hours_since_start > 24:  # Если прошло больше 24 часов
                    logger.warning("Сброс состояния мониторинга - прошло {} часов", int(hours_since_start))
                    self.is_monitoring = False
                    self.start_time = None
                    await self._save_monitoring_state()
            
        except Exception as e:
            logger.error("Ошибка загрузки состояния мониторинга: {}", str(e))
            # В случае ошибки используем безопасные значения по умолчанию
            self.is_monitoring = False
            self.start_time = None


# Глобальный экземпляр монитора
_channel_monitor: Optional[ChannelMonitor] = None


def get_channel_monitor() -> ChannelMonitor:
    """Получить глобальный экземпляр монитора каналов"""
    global _channel_monitor
    
    if _channel_monitor is None:
        _channel_monitor = ChannelMonitor()
    
    return _channel_monitor


async def initialize_channel_monitoring() -> ChannelMonitor:
    """Инициализировать систему мониторинга каналов"""
    logger.info("Инициализация системы мониторинга каналов...")
    
    monitor = get_channel_monitor()
    await monitor.initialize()
    
    logger.info("Система мониторинга каналов инициализирована")
    return monitor


async def start_channel_monitoring() -> None:
    """Запустить мониторинг каналов"""
    monitor = get_channel_monitor()
    await monitor.start_monitoring()


async def stop_channel_monitoring() -> None:
    """Остановить мониторинг каналов"""
    global _channel_monitor
    
    if _channel_monitor:
        await _channel_monitor.stop_monitoring()
        _channel_monitor = None