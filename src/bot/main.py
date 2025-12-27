"""
Основной модуль Telegram бота
Интерфейс управления и модерации Channel Agent
"""

import asyncio
from typing import Optional

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# aiogram 3.x импорты
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

# Локальные импорты
from src.utils.config import get_config
from src.bot.handlers.commands import get_commands_router
from src.bot.handlers.moderation import get_moderation_router
from src.bot.handlers.channels import get_channels_router
from src.bot.handlers.user_posts import get_user_posts_router
from src.bot.handlers.userbot_auth import get_userbot_auth_router
from src.bot.handlers.daily_posts import router as daily_posts_router
from src.bot.handlers.weekly_analytics import router as weekly_analytics_router
from src.bot.filters.owner import owner_filter
from src.utils.exceptions import BotError
from src.utils.html_formatter import get_parse_mode

# Настройка логгера модуля
logger = logger.bind(module="telegram_bot")


class ChannelAgentBot:
    """Основной класс Telegram бота для Channel Agent"""
    
    def __init__(self):
        """Инициализация бота"""
        self.config = get_config()
        
        # Проверяем обязательные параметры
        if not self.config.BOT_TOKEN:
            raise BotError("BOT_TOKEN не найден в конфигурации")
        if not self.config.OWNER_ID:
            raise BotError("OWNER_ID не найден в конфигурации")
        
        # Создаем бота с настройками по умолчанию
        self.bot = Bot(
            token=self.config.BOT_TOKEN,
            default=DefaultBotProperties(
                parse_mode=ParseMode.HTML,
                link_preview_is_disabled=True
            )
        )
        
        # Создаем диспетчер с хранилищем состояний
        self.dp = Dispatcher(storage=MemoryStorage())
        
        # Флаги состояния
        self.is_running = False
        self.startup_complete = False
        self.handlers_setup = False
        
        logger.info("Инициализирован Telegram бот: OWNER_ID={}", self.config.OWNER_ID)
    
    async def setup_handlers(self) -> None:
        """Настройка обработчиков команд"""
        try:
            # Проверяем, не настроены ли уже обработчики
            if self.handlers_setup:
                logger.debug("Обработчики уже настроены, пропускаем")
                return
                
            logger.info("Регистрация обработчиков бота...")
            
            # Регистрируем роутеры в правильном порядке (более специфичные первыми)
            
            # 1. Авторизация UserBot (высокий приоритет)
            userbot_auth_router = get_userbot_auth_router()
            self.dp.include_router(userbot_auth_router)
            logger.debug("Зарегистрирован роутер авторизации UserBot")
            
            # 2. Команды пользователей (примеры постов)
            user_posts_router = get_user_posts_router()
            self.dp.include_router(user_posts_router)
            logger.debug("Зарегистрирован роутер примеров постов")
            
            # 3. Модерация постов
            moderation_router = get_moderation_router()
            self.dp.include_router(moderation_router)
            logger.debug("Зарегистрирован роутер модерации")
            
            # 4. Управление каналами
            channels_router = get_channels_router()
            self.dp.include_router(channels_router)
            logger.debug("Зарегистрирован роутер каналов")
            
            # 5. Ежедневные посты
            self.dp.include_router(daily_posts_router)
            logger.debug("Зарегистрирован роутер ежедневных постов")

            # 6. Еженедельная аналитика (SyntraAI)
            self.dp.include_router(weekly_analytics_router)
            logger.debug("Зарегистрирован роутер еженедельной аналитики")

            # 7. Основные команды (менее специфичные)
            commands_router = get_commands_router()
            self.dp.include_router(commands_router)
            logger.debug("Зарегистрирован роутер команд")
            
            self.handlers_setup = True
            logger.info("Все обработчики зарегистрированы успешно")
            
        except Exception as e:
            logger.error("Ошибка настройки обработчиков бота: {}", str(e))
            raise BotError(f"Не удалось настроить обработчики: {str(e)}")
    
    async def setup_commands(self) -> None:
        """Настройка меню команд бота"""
        try:
            from aiogram.types import BotCommand, BotCommandScopeDefault
            
            # Команды для владельца
            commands = [
                BotCommand(command="start", description="🏠 Главное меню"),
                BotCommand(command="status", description="📊 Статус системы"),
                BotCommand(command="connect_userbot", description="🔐 Подключить UserBot"),
                BotCommand(command="channels", description="📺 Управление каналами"),
                BotCommand(command="moderation", description="⚖️ Модерация постов"),
                BotCommand(command="daily", description="📊 Ежедневные посты"),
                BotCommand(command="weekly", description="📈 Еженедельная аналитика"),
                BotCommand(command="examples", description="📝 Примеры постов"),
                BotCommand(command="settings", description="⚙️ Настройки"),
                BotCommand(command="stats", description="📈 Статистика"),
                BotCommand(command="help", description="❓ Помощь")
            ]
            
            await self.bot.set_my_commands(
                commands=commands,
                scope=BotCommandScopeDefault()
            )
            
            logger.info("Настроено {} команд в меню бота", len(commands))
            
        except Exception as e:
            logger.error("Ошибка настройки команд бота: {}", str(e))
            # Не критичная ошибка, продолжаем работу
    
    async def startup(self) -> None:
        """Действия при запуске бота"""
        try:
            logger.info("Запуск Telegram бота...")
            
            # Настраиваем обработчики
            await self.setup_handlers()
            
            # Настраиваем команды меню
            await self.setup_commands()
            
            # Получаем информацию о боте
            bot_info = await self.bot.get_me()
            logger.info("Бот запущен: @{} (ID: {})", bot_info.username, bot_info.id)
            
            # Отправляем уведомление владельцу о запуске
            try:
                await self.bot.send_message(
                    chat_id=self.config.OWNER_ID,
                    text="🤖 <b>Channel Agent Bot запущен!</b>\n\n"
                         f"🆔 Bot ID: {bot_info.id}\n"
                         f"👤 Username: @{bot_info.username}\n"
                         f"📅 Время запуска: сейчас\n\n"
                         "Используйте /start для начала работы",
                    parse_mode=ParseMode.HTML
                )
                logger.info("Уведомление о запуске отправлено владельцу")
                
            except Exception as e:
                logger.warning("Не удалось отправить уведомление о запуске: {}", str(e))
            
            self.startup_complete = True
            logger.info("✅ Telegram бот успешно запущен")
            
        except Exception as e:
            logger.error("Ошибка запуска Telegram бота: {}", str(e))
            raise BotError(f"Не удалось запустить бота: {str(e)}")
    
    async def shutdown(self) -> None:
        """Действия при остановке бота"""
        try:
            logger.info("Остановка Telegram бота...")
            
            self.is_running = False
            
            # Отправляем уведомление владельцу об остановке
            try:
                if self.startup_complete:
                    await self.bot.send_message(
                        chat_id=self.config.OWNER_ID,
                        text="🛑 <b>Channel Agent Bot остановлен</b>\n\n"
                             "📅 Время остановки: сейчас\n"
                             "🔄 Перезапустите для продолжения работы",
                        parse_mode=get_parse_mode()
                    )
                    logger.info("Уведомление об остановке отправлено владельцу")
                    
            except Exception as e:
                logger.warning("Не удалось отправить уведомление об остановке: {}", str(e))
            
            # Закрываем сессию бота
            await self.bot.session.close()
            
            logger.info("🛑 Telegram бот остановлен")
            
        except Exception as e:
            logger.error("Ошибка остановки Telegram бота: {}", str(e))
    
    async def start_polling(self) -> None:
        """Запуск бота в режиме long polling"""
        try:
            self.is_running = True
            
            # Выполняем стартовые действия
            await self.startup()
            
            # Начинаем polling
            logger.info("Начало polling...")
            await self.dp.start_polling(
                self.bot,
                allowed_updates=self.dp.resolve_used_update_types()
            )
            
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки (Ctrl+C)")
        except Exception as e:
            logger.error("Ошибка в polling: {}", str(e))
            raise
        finally:
            await self.shutdown()
    
    async def start_webhook(self, webhook_url: str, webhook_path: str = "/webhook") -> None:
        """Запуск бота в режиме webhook"""
        try:
            self.is_running = True
            
            # Выполняем стартовые действия
            await self.startup()
            
            # Настраиваем webhook
            await self.bot.set_webhook(
                url=f"{webhook_url}{webhook_path}",
                allowed_updates=self.dp.resolve_used_update_types()
            )
            
            logger.info("Webhook настроен: {}{}", webhook_url, webhook_path)
            
        except Exception as e:
            logger.error("Ошибка настройки webhook: {}", str(e))
            raise BotError(f"Не удалось настроить webhook: {str(e)}")
    
    def get_bot(self) -> Bot:
        """Получить экземпляр бота"""
        return self.bot
    
    def get_dispatcher(self) -> Dispatcher:
        """Получить диспетчер"""
        return self.dp
    
    def is_bot_running(self) -> bool:
        """Проверить запущен ли бот"""
        return self.is_running


# Глобальный экземпляр бота
_channel_agent_bot: Optional[ChannelAgentBot] = None


def get_bot_instance() -> Bot:
    """Получить глобальный экземпляр aiogram Bot"""
    global _channel_agent_bot
    
    if _channel_agent_bot is None:
        _channel_agent_bot = ChannelAgentBot()
    
    return _channel_agent_bot.bot


def get_channel_agent_bot() -> ChannelAgentBot:
    """Получить глобальный экземпляр ChannelAgentBot"""
    global _channel_agent_bot
    
    if _channel_agent_bot is None:
        _channel_agent_bot = ChannelAgentBot()
    
    return _channel_agent_bot


async def start_bot() -> None:
    """Запустить бота в режиме polling"""
    bot_instance = get_channel_agent_bot()
    await bot_instance.start_polling()


async def initialize_bot() -> ChannelAgentBot:
    """Инициализировать бота без запуска"""
    bot_instance = get_channel_agent_bot()
    await bot_instance.setup_handlers()
    return bot_instance


if __name__ == "__main__":
    # Запуск бота напрямую
    logger.info("Прямой запуск Telegram бота...")
    
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error("Критическая ошибка бота: {}", str(e))
        exit(1)