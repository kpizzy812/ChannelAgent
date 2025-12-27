"""
Главный файл запуска Channel Agent v2.0
Координирует работу всех модулей системы
"""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

# Стандартные импорты
from dotenv import load_dotenv

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.utils.logging_config import setup_logging
from src.utils.config import get_config
from src.database.connection import initialize_database, close_database
from src.database.migrations import initialize_database_schema
from src.userbot.monitor import initialize_channel_monitoring
from src.bot.main import initialize_bot
from src.scheduler.main import start_scheduler
from src.ai.processor import get_ai_processor


class ChannelAgent:
    """Главный класс Channel Agent системы"""
    
    def __init__(self):
        """Инициализация системы"""
        load_dotenv()  # Загружаем переменные окружения
        
        self.config = get_config()
        self.is_running = False
        self.components = {
            'database': False,
            'userbot': False,
            'bot': False,
            'ai': False,
            'scheduler': False
        }
        
        # Обработчики сигналов для graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("🤖 Channel Agent v2.0 инициализирован")
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов остановки"""
        logger.info("Получен сигнал остановки: {}", signum)
        self.is_running = False
    
    async def startup(self) -> bool:
        """Запуск всех компонентов системы"""
        try:
            logger.info("🚀 Запуск Channel Agent системы...")
            
            # 1. Инициализация базы данных
            logger.info("📊 Инициализация базы данных...")
            
            # Сначала инициализируем подключение к БД
            db_path = Path("data") / "channel_agent.db"
            await initialize_database(str(db_path))
            
            # Затем создаем схему
            await initialize_database_schema()
            
            self.components['database'] = True
            logger.info("✅ База данных готова")
            
            # 2. Тестирование AI модуля
            logger.info("🤖 Проверка AI модуля...")
            try:
                ai_processor = get_ai_processor()
                # Простая проверка доступности
                logger.info("✅ AI модуль готов")
                self.components['ai'] = True
            except Exception as e:
                logger.warning("⚠️ AI модуль недоступен: {}", str(e))
                logger.warning("Система продолжит работу без AI функций")
            
            # 3. Инициализация и запуск UserBot мониторинга
            logger.info("📡 Инициализация UserBot мониторинга...")
            try:
                monitor = await initialize_channel_monitoring()
                # Запускаем мониторинг как фоновую задачу
                from src.userbot.monitor import start_channel_monitoring
                asyncio.create_task(start_channel_monitoring())
                self.components['userbot'] = True
                logger.info("✅ UserBot мониторинг запущен как фоновая задача")
            except Exception as e:
                logger.error("❌ Ошибка инициализации UserBot: {}", str(e))
                logger.warning("Система продолжит работу без мониторинга")
            
            # 4. Инициализация бота
            logger.info("🤖 Инициализация Telegram бота...")
            try:
                bot_instance = await initialize_bot()
                self.components['bot'] = True
                logger.info("✅ Telegram бот готов")
            except Exception as e:
                logger.error("❌ Ошибка инициализации бота: {}", str(e))
                return False
            
            # 5. Запуск планировщика
            logger.info("⏰ Запуск планировщика задач...")
            try:
                scheduler = await start_scheduler()
                self.components['scheduler'] = True
                logger.info("✅ Планировщик готов")
            except Exception as e:
                logger.error("❌ Ошибка запуска планировщика: {}", str(e))
                logger.warning("Система продолжит работу без автоматических задач")
            
            # Показываем итоговый статус
            self._show_startup_status()
            
            self.is_running = True
            return True
            
        except Exception as e:
            logger.error("💥 Критическая ошибка запуска: {}", str(e))
            return False
    
    def _show_startup_status(self):
        """Показать статус запуска компонентов"""
        logger.info("📋 Статус компонентов Channel Agent:")
        
        status_icons = {True: "✅", False: "❌"}
        
        for component, status in self.components.items():
            icon = status_icons[status]
            component_names = {
                'database': 'База данных',
                'userbot': 'UserBot мониторинг',
                'bot': 'Telegram бот',
                'ai': 'AI модуль',
                'scheduler': 'Планировщик'
            }
            
            logger.info("  {} {}", icon, component_names.get(component, component))
        
        # Подсчитываем готовые компоненты
        ready_count = sum(self.components.values())
        total_count = len(self.components)
        
        if ready_count == total_count:
            logger.info("🎉 Все компоненты запущены успешно!")
        elif ready_count >= 3:  # Минимум: БД, бот и еще что-то
            logger.info("⚠️ Система частично готова: {}/{} компонентов", ready_count, total_count)
        else:
            logger.error("💥 Критические ошибки: готово только {}/{} компонентов", ready_count, total_count)
    
    async def shutdown(self):
        """Остановка всех компонентов"""
        try:
            logger.info("🛑 Остановка Channel Agent...")
            
            # Останавливаем планировщик
            if self.components['scheduler']:
                try:
                    from src.scheduler.main import stop_scheduler
                    await stop_scheduler()
                    logger.info("✅ Планировщик остановлен")
                except Exception as e:
                    logger.error("Ошибка остановки планировщика: {}", str(e))
            
            # Останавливаем мониторинг
            if self.components['userbot']:
                try:
                    from src.userbot.monitor import stop_channel_monitoring
                    await stop_channel_monitoring()
                    logger.info("✅ UserBot мониторинг остановлен")
                except Exception as e:
                    logger.error("Ошибка остановки мониторинга: {}", str(e))
            
            # Останавливаем бота
            if self.components['bot']:
                try:
                    from src.bot.main import get_channel_agent_bot
                    bot_instance = get_channel_agent_bot()
                    await bot_instance.shutdown()
                    logger.info("✅ Telegram бот остановлен")
                except Exception as e:
                    logger.error("Ошибка остановки бота: {}", str(e))
            
            # Закрываем подключение к БД
            if self.components['database']:
                try:
                    await close_database()
                    logger.info("✅ База данных закрыта")
                except Exception as e:
                    logger.error("Ошибка закрытия БД: {}", str(e))
            
            logger.info("🏁 Channel Agent остановлен")
            
        except Exception as e:
            logger.error("Ошибка остановки системы: {}", str(e))
    
    async def run(self):
        """Главный цикл выполнения"""
        try:
            # Запуск системы
            success = await self.startup()
            
            if not success:
                logger.error("💥 Не удалось запустить систему")
                return False
            
            # Запускаем бота в режиме polling
            logger.info("🔄 Запуск основного цикла...")
            
            if self.components['bot']:
                from src.bot.main import get_channel_agent_bot
                bot_instance = get_channel_agent_bot()
                
                # Запускаем бота в polling режиме
                await bot_instance.start_polling()
            else:
                # Если бот не запустился, просто ждем
                while self.is_running:
                    await asyncio.sleep(1)
            
            return True
            
        except KeyboardInterrupt:
            logger.info("Получен Ctrl+C, остановка системы...")
        except Exception as e:
            logger.error("Ошибка в главном цикле: {}", str(e))
        finally:
            await self.shutdown()


async def test_system_components() -> bool:
    """Тестирование всех компонентов системы"""
    try:
        logger.info("🧪 Запуск тестирования системы")
        
        test_results = {
            'config': False,
            'database': False,
            'ai': False,
            'coingecko': False,
            'userbot_auth': False
        }
        
        # 1. Тест конфигурации
        logger.info("📋 Тест конфигурации...")
        try:
            config = get_config()
            config.validate()
            test_results['config'] = True
            logger.info("✅ Конфигурация корректна")
        except Exception as e:
            logger.error("❌ Ошибка конфигурации: {}", str(e))
        
        # 2. Тест базы данных
        logger.info("💾 Тест базы данных...")
        try:
            # Инициализируем подключение к БД
            db_path = Path("data") / "channel_agent.db"
            await initialize_database(str(db_path))
            
            # Создаем схему
            await initialize_database_schema()
            
            # Простая проверка
            from src.database.connection import get_db_connection
            async with get_db_connection() as conn:
                cursor = await conn.execute("SELECT 1")
                await cursor.fetchone()
            test_results['database'] = True
            logger.info("✅ База данных работает")
        except Exception as e:
            logger.error("❌ Ошибка базы данных: {}", str(e))
        
        # 3. Тест AI модуля
        logger.info("🤖 Тест AI модуля...")
        try:
            from src.ai.client import get_openai_client
            ai_client = get_openai_client()
            # Простая проверка инициализации
            test_results['ai'] = True
            logger.info("✅ AI модуль доступен")
        except Exception as e:
            logger.error("❌ AI модуль недоступен: {}", str(e))
        
        # 4. Тест CoinGecko API
        logger.info("📊 Тест CoinGecko API...")
        try:
            from src.scheduler.coingecko import test_coingecko_connection
            coingecko_ok = await test_coingecko_connection()
            test_results['coingecko'] = coingecko_ok
            if coingecko_ok:
                logger.info("✅ CoinGecko API работает")
            else:
                logger.error("❌ CoinGecko API недоступен")
        except Exception as e:
            logger.error("❌ Ошибка CoinGecko: {}", str(e))
        
        # 5. Тест конфигурации UserBot (БЕЗ подключения)
        logger.info("📱 Тест конфигурации UserBot...")
        try:
            from pathlib import Path
            
            # Проверяем наличие файла сессии
            session_file = Path("data/userbot_session.session")
            if session_file.exists():
                test_results['userbot_auth'] = True
                logger.info("✅ UserBot сессия найдена")
            else:
                logger.info("⚠️ UserBot сессия не найдена - требуется авторизация")
                test_results['userbot_auth'] = False
                
        except Exception as e:
            logger.error("❌ Ошибка проверки UserBot: {}", str(e))
        
        # Итоги тестирования
        passed_tests = sum(test_results.values())
        total_tests = len(test_results)
        
        logger.info("📊 Результаты тестирования: {}/{} тестов пройдено", passed_tests, total_tests)
        
        for test_name, result in test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info("  {} {}", status, test_name)
        
        if passed_tests >= 3:  # Минимум для работы
            logger.info("🎉 Система готова к работе!")
            return True
        else:
            logger.error("💥 Критические ошибки! Система не готова")
            return False
            
    except Exception as e:
        logger.error("Критическая ошибка тестирования: {}", str(e))
        return False


async def main():
    """Главная функция"""
    
    # Настраиваем логирование
    setup_logging()
    
    logger.info("🤖 Channel Agent v2.0 запуск...")
    logger.info("📂 Рабочая директория: {}", Path.cwd())
    
    # Проверяем аргументы командной строки
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "test":
            # Режим тестирования
            logger.info("🧪 Режим тестирования системы")
            success = await test_system_components()
            return 0 if success else 1
        
        elif command == "setup":
            # Режим первичной настройки
            logger.info("⚙️ Режим первичной настройки")
            try:
                # Инициализируем подключение к БД
                db_path = Path("data") / "channel_agent.db"
                await initialize_database(str(db_path))
                
                # Создаем схему
                await initialize_database_schema()
                logger.info("✅ Первичная настройка завершена")
                return 0
            except Exception as e:
                logger.error("❌ Ошибка настройки: {}", str(e))
                return 1
        
        else:
            logger.error("Неизвестная команда: {}", command)
            logger.info("Доступные команды: test, setup")
            return 1
    
    # Обычный режим работы
    try:
        agent = ChannelAgent()
        success = await agent.run()
        return 0 if success else 1
        
    except Exception as e:
        logger.error("💥 Критическая ошибка: {}", str(e))
        return 1


if __name__ == "__main__":
    """Точка входа в приложение"""
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        logger.info("👋 Программа завершена пользователем")
        sys.exit(0)
        
    except Exception as e:
        logger.error("💥 Фатальная ошибка: {}", str(e))
        sys.exit(1)