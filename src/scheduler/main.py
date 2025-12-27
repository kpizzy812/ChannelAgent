"""
Основной модуль планировщика задач
Управление всеми запланированными задачами Channel Agent
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# APScheduler импорты
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.job import Job

# Локальные импорты
from src.scheduler.tasks.monitoring import check_monitoring_health
from src.scheduler.tasks.daily_posts import create_daily_crypto_post
from src.scheduler.tasks.weekly_posts import create_weekly_market_overview
from src.scheduler.tasks.cleanup import cleanup_old_posts
from src.scheduler.tasks.delayed_posts import process_scheduled_posts
from src.scheduler.tasks.template_autopublish import process_template_autopublish
from src.scheduler.coingecko import get_coingecko_data
from src.utils.config import get_config
from src.utils.exceptions import SchedulerError, TaskExecutionError

# Настройка логгера модуля
logger = logger.bind(module="scheduler")


class ChannelAgentScheduler:
    """Планировщик задач для Channel Agent"""
    
    def __init__(self):
        """Инициализация планировщика"""
        self.config = get_config()
        
        # Конфигурация планировщика
        jobstores = {
            'default': MemoryJobStore()
        }
        
        executors = {
            'default': AsyncIOExecutor()
        }
        
        job_defaults = {
            'coalesce': False,
            'max_instances': 1,
            'misfire_grace_time': 30
        }
        
        # Создаем планировщик с timezone UTC+3 (Московское время)
        moscow_tz = timezone(timedelta(hours=3))
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=moscow_tz
        )
        
        # Статистика
        self.stats = {
            'total_jobs': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'missed_executions': 0,
            'last_execution': None
        }
        
        # Флаги состояния
        self.is_running = False
        self.startup_complete = False
        
        # Настройка обработчиков событий
        self._setup_event_handlers()
        
        logger.info("Инициализирован планировщик задач")
    
    def _setup_event_handlers(self) -> None:
        """Настройка обработчиков событий планировщика"""
        
        def job_executed_handler(event):
            """Обработчик успешного выполнения задачи"""
            self.stats['successful_executions'] += 1
            self.stats['last_execution'] = datetime.now()
            logger.info("Задача выполнена успешно: {} за {:.2f}с", 
                       event.job_id, event.scheduled_run_time.timestamp() if event.scheduled_run_time else 0)
        
        def job_error_handler(event):
            """Обработчик ошибок выполнения задач"""
            self.stats['failed_executions'] += 1
            logger.error("Ошибка выполнения задачи {}: {}", 
                        event.job_id, str(event.exception))
            
            # Логируем детали ошибки
            if hasattr(event, 'traceback') and event.traceback:
                logger.error("Traceback задачи {}:\n{}", event.job_id, event.traceback)
        
        def job_missed_handler(event):
            """Обработчик пропущенных задач"""
            self.stats['missed_executions'] += 1
            logger.warning("Пропущена задача: {} (время выполнения: {})", 
                          event.job_id, event.scheduled_run_time)
        
        # Регистрируем обработчики
        self.scheduler.add_listener(job_executed_handler, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(job_error_handler, EVENT_JOB_ERROR)
        self.scheduler.add_listener(job_missed_handler, EVENT_JOB_MISSED)
        
        logger.debug("Настроены обработчики событий планировщика")
    
    async def start(self) -> None:
        """Запуск планировщика"""
        try:
            logger.info("Запуск планировщика задач...")
            
            # Добавляем все задачи
            await self._add_all_jobs()
            
            # Запускаем планировщик
            self.scheduler.start()
            self.is_running = True
            self.startup_complete = True
            
            logger.info("✅ Планировщик задач запущен, активных задач: {}", 
                       len(self.scheduler.get_jobs()))
            
            # Показываем список задач
            await self._log_scheduled_jobs()
            
        except Exception as e:
            logger.error("Ошибка запуска планировщика: {}", str(e))
            raise SchedulerError(f"Не удалось запустить планировщик: {str(e)}")
    
    async def stop(self) -> None:
        """Остановка планировщика"""
        try:
            logger.info("Остановка планировщика задач...")
            
            self.is_running = False
            
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
            
            logger.info("🛑 Планировщик задач остановлен")
            
        except Exception as e:
            logger.error("Ошибка остановки планировщика: {}", str(e))
    
    async def _add_all_jobs(self) -> None:
        """Добавить все запланированные задачи"""
        try:
            # 1. Проверка состояния мониторинга каналов (каждые 5 минут - мониторинг работает постоянно)
            health_check_interval = 300  # 5 минут, поскольку мониторинг работает 24/7
            self.scheduler.add_job(
                check_monitoring_health,
                'interval',
                seconds=health_check_interval,
                id='monitoring_health_check',
                name='Проверка состояния мониторинга',
                replace_existing=True
            )
            
            # 2. Обработка отложенных постов (каждую минуту)
            self.scheduler.add_job(
                process_scheduled_posts,
                'interval',
                minutes=1,
                id='scheduled_posts',
                name='Обработка отложенных постов',
                replace_existing=True
            )
            
            # 3. Очистка старых данных (ежедневно в 2:00 UTC)
            self.scheduler.add_job(
                cleanup_old_posts,
                'cron',
                hour=2,
                minute=0,
                id='cleanup_task',
                name='Очистка старых данных',
                replace_existing=True
            )
            
            # 4. Удаляем старые задачи template_autopublish если есть
            try:
                self.scheduler.remove_job('template_autopublish')
                logger.info("🗑️ Удалена старая задача template_autopublish из планировщика")
            except Exception:
                pass  # Задача не существует - это нормально
            
            # 5. Ежедневный пост с криптовалютами - читаем время из БД
            await self._add_daily_crypto_post_job()
            
            # 6. Обновление данных CoinGecko (каждые 30 минут)
            self.scheduler.add_job(
                get_coingecko_data,
                'interval',
                minutes=30,
                id='coingecko_update',
                name='Обновление данных CoinGecko',
                replace_existing=True
            )

            # 7. Еженедельный обзор рынка (SyntraAI) - читаем день и время из БД
            await self._add_weekly_analytics_job()

            # 8. Автопубликация шаблонов (ОТКЛЮЧЕНО чтобы избежать дублирования с daily_posts)
            # self.scheduler.add_job(
            #     process_template_autopublish,
            #     'interval',
            #     minutes=1,
            #     id='template_autopublish',
            #     name='Автопубликация шаблонов',
            #     replace_existing=True
            # )
            
            self.stats['total_jobs'] = len(self.scheduler.get_jobs())
            logger.info("Добавлено {} задач в планировщик", self.stats['total_jobs'])
            
        except Exception as e:
            logger.error("Ошибка добавления задач в планировщик: {}", str(e))
            raise SchedulerError(f"Не удалось добавить задачи: {str(e)}")
    
    async def _add_daily_crypto_post_job(self) -> None:
        """Добавить задачу ежедневного крипто-поста с временем из БД"""
        try:
            from src.database.crud.setting import get_setting_crud, get_bool_setting
            
            # Проверяем включен ли ежедневный пост
            daily_post_enabled = await get_bool_setting("daily_post.enabled", True)
            if not daily_post_enabled:
                logger.info("Ежедневные посты отключены в настройках, задача не добавлена")
                return
            
            # Читаем время из БД
            setting_crud = get_setting_crud()
            time_setting = await setting_crud.get_setting("daily_post.time")
            daily_time = time_setting.strip('"') if time_setting else "09:00"  # Убираем кавычки если есть
            
            logger.info("Время ежедневного поста из БД: {}", daily_time)
            
            try:
                hour, minute = map(int, daily_time.split(':'))
                self.scheduler.add_job(
                    create_daily_crypto_post,
                    'cron',
                    hour=hour,
                    minute=minute,
                    id='daily_crypto_post',
                    name='Ежедневный крипто-пост',
                    replace_existing=True
                )
                logger.info("✅ Добавлена задача ежедневного крипто-поста на {}:{:02d} UTC+3", hour, minute)
            except ValueError:
                logger.warning("⚠️ Неверный формат времени для ежедневного поста: {}, используется 09:00", daily_time)
                self.scheduler.add_job(
                    create_daily_crypto_post,
                    'cron',
                    hour=9,
                    minute=0,
                    id='daily_crypto_post',
                    name='Ежедневный крипто-пост (fallback)',
                    replace_existing=True
                )
                
        except Exception as e:
            logger.error("Ошибка добавления задачи ежедневного поста: {}", str(e))
            # Fallback к времени по умолчанию
            try:
                self.scheduler.add_job(
                    create_daily_crypto_post,
                    'cron',
                    hour=9,
                    minute=0,
                    id='daily_crypto_post',
                    name='Ежедневный крипто-пост (fallback)',
                    replace_existing=True
                )
                logger.info("Добавлена задача ежедневного поста с временем по умолчанию 09:00")
            except Exception as fallback_error:
                logger.error("Ошибка добавления fallback задачи: {}", str(fallback_error))

    async def _add_weekly_analytics_job(self) -> None:
        """Добавить задачу еженедельного обзора рынка от SyntraAI"""
        try:
            from src.database.crud.setting import get_setting_crud, get_bool_setting

            # Проверяем включена ли еженедельная аналитика
            weekly_enabled = await get_bool_setting("weekly_analytics.enabled", False)
            if not weekly_enabled:
                logger.info("Еженедельная аналитика отключена в настройках, задача не добавлена")
                return

            # Читаем день недели и время из БД
            setting_crud = get_setting_crud()

            # День недели (0=пн, 6=вс), по умолчанию воскресенье
            day_setting = await setting_crud.get_setting("weekly_analytics.day")
            day_of_week = int(day_setting) if day_setting else 6

            # Время публикации, по умолчанию 18:00
            time_setting = await setting_crud.get_setting("weekly_analytics.time")
            weekly_time = time_setting.strip('"') if time_setting else "18:00"

            try:
                hour, minute = map(int, weekly_time.split(':'))

                # Маппинг дней недели для APScheduler (0=пн, 6=вс)
                day_names = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
                day_name = day_names[day_of_week] if 0 <= day_of_week <= 6 else 'sun'

                self.scheduler.add_job(
                    create_weekly_market_overview,
                    'cron',
                    day_of_week=day_name,
                    hour=hour,
                    minute=minute,
                    id='weekly_market_overview',
                    name='Еженедельный обзор рынка (SyntraAI)',
                    replace_existing=True
                )
                day_ru = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
                logger.info(
                    "✅ Добавлена задача еженедельного обзора: {} в {}:{:02d} UTC+3",
                    day_ru[day_of_week], hour, minute
                )
            except ValueError:
                logger.warning(
                    "⚠️ Неверный формат времени для еженедельного обзора: {}, используется вс 18:00",
                    weekly_time
                )
                self.scheduler.add_job(
                    create_weekly_market_overview,
                    'cron',
                    day_of_week='sun',
                    hour=18,
                    minute=0,
                    id='weekly_market_overview',
                    name='Еженедельный обзор рынка (fallback)',
                    replace_existing=True
                )

        except Exception as e:
            logger.error("Ошибка добавления задачи еженедельного обзора: {}", str(e))

    async def _log_scheduled_jobs(self) -> None:
        """Вывести информацию о запланированных задачах"""
        try:
            jobs = self.scheduler.get_jobs()
            logger.info("Запланированные задачи:")
            
            for job in jobs:
                next_run = job.next_run_time.strftime('%H:%M:%S %d.%m.%Y') if job.next_run_time else 'Не запланирована'
                logger.info("  • {} ({}): следующий запуск {}", 
                           job.name, job.id, next_run)
            
        except Exception as e:
            logger.error("Ошибка вывода списка задач: {}", str(e))
    
    def add_job(
        self,
        func,
        trigger,
        job_id: str,
        name: str,
        **kwargs
    ) -> Optional[Job]:
        """
        Добавить новую задачу в планировщик
        
        Args:
            func: Функция для выполнения
            trigger: Тип триггера ('interval', 'cron', 'date')
            job_id: Уникальный ID задачи
            name: Человеко-читаемое имя задачи
            **kwargs: Дополнительные параметры для задачи
            
        Returns:
            Объект Job или None при ошибке
        """
        try:
            job = self.scheduler.add_job(
                func=func,
                trigger=trigger,
                id=job_id,
                name=name,
                replace_existing=True,
                **kwargs
            )
            
            logger.info("Добавлена новая задача: {} ({})", name, job_id)
            return job
            
        except Exception as e:
            logger.error("Ошибка добавления задачи {}: {}", job_id, str(e))
            return None
    
    def remove_job(self, job_id: str) -> bool:
        """
        Удалить задачу из планировщика
        
        Args:
            job_id: ID задачи
            
        Returns:
            True если задача удалена
        """
        try:
            self.scheduler.remove_job(job_id)
            logger.info("Задача удалена: {}", job_id)
            return True
            
        except Exception as e:
            logger.error("Ошибка удаления задачи {}: {}", job_id, str(e))
            return False
    
    def pause_job(self, job_id: str) -> bool:
        """Приостановить задачу"""
        try:
            self.scheduler.pause_job(job_id)
            logger.info("Задача приостановлена: {}", job_id)
            return True
        except Exception as e:
            logger.error("Ошибка приостановки задачи {}: {}", job_id, str(e))
            return False
    
    def resume_job(self, job_id: str) -> bool:
        """Возобновить задачу"""
        try:
            self.scheduler.resume_job(job_id)
            logger.info("Задача возобновлена: {}", job_id)
            return True
        except Exception as e:
            logger.error("Ошибка возобновления задачи {}: {}", job_id, str(e))
            return False
    
    def get_job_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Получить информацию о задаче"""
        try:
            job = self.scheduler.get_job(job_id)
            if not job:
                return None
            
            return {
                'id': job.id,
                'name': job.name,
                'func': job.func.__name__ if job.func else None,
                'trigger': str(job.trigger),
                'next_run_time': job.next_run_time,
                'pending': job.pending
            }
        except Exception as e:
            logger.error("Ошибка получения информации о задаче {}: {}", job_id, str(e))
            return None
    
    def get_all_jobs_info(self) -> List[Dict[str, Any]]:
        """Получить информацию обо всех задачах"""
        try:
            jobs_info = []
            for job in self.scheduler.get_jobs():
                job_info = {
                    'id': job.id,
                    'name': job.name,
                    'func': job.func.__name__ if job.func else None,
                    'trigger': str(job.trigger),
                    'next_run_time': job.next_run_time,
                    'pending': job.pending
                }
                jobs_info.append(job_info)
            
            return jobs_info
        except Exception as e:
            logger.error("Ошибка получения информации о задачах: {}", str(e))
            return []
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику планировщика"""
        return {
            'is_running': self.is_running,
            'total_jobs': len(self.scheduler.get_jobs()) if self.scheduler else 0,
            'successful_executions': self.stats['successful_executions'],
            'failed_executions': self.stats['failed_executions'],
            'missed_executions': self.stats['missed_executions'],
            'last_execution': self.stats['last_execution'],
            'startup_complete': self.startup_complete
        }
    
    async def execute_job_now(self, job_id: str) -> bool:
        """
        Выполнить задачу немедленно
        
        Args:
            job_id: ID задачи
            
        Returns:
            True если задача выполнена успешно
        """
        try:
            job = self.scheduler.get_job(job_id)
            if not job:
                logger.error("Задача не найдена: {}", job_id)
                return False
            
            logger.info("Немедленное выполнение задачи: {}", job_id)
            
            # Выполняем функцию задачи
            if asyncio.iscoroutinefunction(job.func):
                await job.func()
            else:
                job.func()
            
            logger.info("Задача {} выполнена успешно", job_id)
            return True
            
        except Exception as e:
            logger.error("Ошибка немедленного выполнения задачи {}: {}", job_id, str(e))
            raise TaskExecutionError(job_id, str(e))


# Глобальный экземпляр планировщика
_scheduler: Optional[ChannelAgentScheduler] = None


def get_scheduler() -> ChannelAgentScheduler:
    """Получить глобальный экземпляр планировщика"""
    global _scheduler
    
    if _scheduler is None:
        _scheduler = ChannelAgentScheduler()
    
    return _scheduler


async def start_scheduler() -> ChannelAgentScheduler:
    """Запустить планировщик"""
    scheduler = get_scheduler()
    await scheduler.start()
    return scheduler


async def stop_scheduler() -> None:
    """Остановить планировщик"""
    global _scheduler
    
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None