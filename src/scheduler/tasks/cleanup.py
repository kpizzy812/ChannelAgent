"""
Задача очистки старых данных
Периодическое удаление устаревших записей и файлов
"""

import os
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.database.connection import get_db_connection
from src.database.crud.post import get_post_crud
from src.database.crud.channel import get_channel_crud
from src.database.crud.user_post import get_user_post_crud
from src.database.models.post import PostStatus
from src.utils.config import get_config
from src.utils.exceptions import TaskExecutionError

# Настройка логгера модуля
logger = logger.bind(module="scheduler_cleanup")


async def cleanup_old_posts() -> None:
    """Основная задача очистки старых постов и данных"""
    try:
        logger.info("🧹 Запуск задачи очистки старых данных")
        
        cleanup_stats = {
            "deleted_posts": 0,
            "archived_posts": 0,
            "deleted_files": 0,
            "cleaned_logs": False,
            "database_optimized": False
        }
        
        # 1. Очистка старых постов
        deleted_posts = await cleanup_old_database_posts()
        cleanup_stats["deleted_posts"] = deleted_posts
        
        # 2. Архивирование старых постов
        archived_posts = await archive_old_posts()
        cleanup_stats["archived_posts"] = archived_posts
        
        # 3. Очистка файлов медиа
        deleted_files = await cleanup_media_files()
        cleanup_stats["deleted_files"] = deleted_files
        
        # 4. Очистка логов
        cleaned_logs = await cleanup_log_files()
        cleanup_stats["cleaned_logs"] = cleaned_logs
        
        # 5. Оптимизация БД
        optimized = await optimize_database()
        cleanup_stats["database_optimized"] = optimized
        
        # 6. Очистка временных файлов
        await cleanup_temp_files()
        
        logger.info("✅ Очистка завершена: {} постов удалено, {} архивировано, {} файлов удалено",
                   cleanup_stats["deleted_posts"], 
                   cleanup_stats["archived_posts"],
                   cleanup_stats["deleted_files"])
        
    except Exception as e:
        logger.error("❌ Ошибка в задаче очистки: {}", str(e))
        raise TaskExecutionError("cleanup_task", str(e))


async def cleanup_old_database_posts() -> int:
    """
    Очистка старых постов из базы данных
    
    Returns:
        Количество удаленных постов
    """
    try:
        logger.debug("🗑️ Очистка старых постов из БД")
        
        # Удаляем посты старше 30 дней
        cutoff_date = datetime.now() - timedelta(days=30)
        
        post_crud = get_post_crud()
        
        # Получаем старые отклоненные посты
        old_rejected_posts = await post_crud.get_posts_before_date_by_status(
            cutoff_date, PostStatus.REJECTED
        )
        
        deleted_count = 0
        
        # Удаляем только отклоненные посты (опубликованные оставляем для истории)
        for post in old_rejected_posts:
            try:
                success = await post_crud.delete_post_permanently(post.id)
                if success:
                    deleted_count += 1
                    logger.debug("Удален старый отклоненный пост {}", post.id)
                
            except Exception as e:
                logger.warning("Не удалось удалить пост {}: {}", post.id, str(e))
                continue
        
        # Также очищаем очень старые pending посты (старше 7 дней)
        old_pending_cutoff = datetime.now() - timedelta(days=7)
        old_pending_posts = await post_crud.get_posts_before_date_by_status(
            old_pending_cutoff, PostStatus.PENDING
        )
        
        for post in old_pending_posts:
            try:
                # Переводим в rejected вместо полного удаления
                await post_crud.update_post_status(post.id, PostStatus.REJECTED)
                logger.debug("Старый pending пост {} помечен как rejected", post.id)
                
            except Exception as e:
                logger.warning("Не удалось обновить статус поста {}: {}", post.id, str(e))
        
        if deleted_count > 0:
            logger.info("Удалено {} старых отклоненных постов", deleted_count)
        
        return deleted_count
        
    except Exception as e:
        logger.error("Ошибка очистки старых постов: {}", str(e))
        return 0


async def archive_old_posts() -> int:
    """
    Архивирование старых опубликованных постов
    Перемещение в архивную таблицу вместо удаления
    
    Returns:
        Количество архивированных постов
    """
    try:
        logger.debug("📦 Архивирование старых опубликованных постов")
        
        # Архивируем опубликованные посты старше 90 дней
        archive_cutoff = datetime.now() - timedelta(days=90)
        
        post_crud = get_post_crud()
        old_published_posts = await post_crud.get_posts_before_date_by_status(
            archive_cutoff, PostStatus.POSTED
        )
        
        archived_count = 0
        
        for post in old_published_posts:
            try:
                # Здесь можно реализовать перенос в архивную таблицу
                # Пока просто помечаем флагом
                await post_crud.mark_post_as_archived(post.id)
                archived_count += 1
                logger.debug("Архивирован пост {}", post.id)
                
            except Exception as e:
                logger.warning("Не удалось архивировать пост {}: {}", post.id, str(e))
                continue
        
        if archived_count > 0:
            logger.info("Архивировано {} старых опубликованных постов", archived_count)
        
        return archived_count
        
    except Exception as e:
        logger.error("Ошибка архивирования постов: {}", str(e))
        return 0


async def cleanup_media_files() -> int:
    """
    Очистка старых медиа файлов
    
    Returns:
        Количество удаленных файлов
    """
    try:
        logger.debug("🖼️ Очистка старых медиа файлов")
        
        deleted_count = 0
        media_dirs = ["media", "photos", "temp", "downloads"]
        
        for dir_name in media_dirs:
            media_path = Path(dir_name)
            
            if not media_path.exists():
                continue
                
            cutoff_time = datetime.now() - timedelta(days=7)  # Файлы старше недели
            
            try:
                for file_path in media_path.rglob("*"):
                    if file_path.is_file():
                        file_modified = datetime.fromtimestamp(file_path.stat().st_mtime)
                        
                        if file_modified < cutoff_time:
                            try:
                                file_path.unlink()
                                deleted_count += 1
                                logger.debug("Удален старый медиа файл: {}", file_path.name)
                                
                            except Exception as e:
                                logger.warning("Не удалось удалить файл {}: {}", file_path, str(e))
                
            except Exception as e:
                logger.warning("Ошибка очистки директории {}: {}", dir_name, str(e))
        
        if deleted_count > 0:
            logger.info("Удалено {} старых медиа файлов", deleted_count)
        
        return deleted_count
        
    except Exception as e:
        logger.error("Ошибка очистки медиа файлов: {}", str(e))
        return 0


async def cleanup_log_files() -> bool:
    """
    Очистка старых лог файлов
    
    Returns:
        True если очистка выполнена
    """
    try:
        logger.debug("📋 Очистка старых лог файлов")
        
        logs_path = Path("logs")
        if not logs_path.exists():
            logger.debug("Директория логов не найдена")
            return True
        
        # Удаляем логи старше 30 дней
        cutoff_time = datetime.now() - timedelta(days=30)
        deleted_count = 0
        
        for log_file in logs_path.glob("*.log*"):
            try:
                file_modified = datetime.fromtimestamp(log_file.stat().st_mtime)
                
                if file_modified < cutoff_time:
                    log_file.unlink()
                    deleted_count += 1
                    logger.debug("Удален старый лог файл: {}", log_file.name)
                    
            except Exception as e:
                logger.warning("Не удалось удалить лог файл {}: {}", log_file, str(e))
        
        if deleted_count > 0:
            logger.info("Удалено {} старых лог файлов", deleted_count)
        
        return True
        
    except Exception as e:
        logger.error("Ошибка очистки лог файлов: {}", str(e))
        return False


async def cleanup_temp_files() -> None:
    """Очистка временных файлов"""
    try:
        logger.debug("🗂️ Очистка временных файлов")
        
        temp_dirs = ["tmp", "temp", ".temp", "cache"]
        deleted_count = 0
        
        for dir_name in temp_dirs:
            temp_path = Path(dir_name)
            
            if not temp_path.exists():
                continue
            
            try:
                for temp_file in temp_path.rglob("*"):
                    if temp_file.is_file():
                        temp_file.unlink()
                        deleted_count += 1
                        
            except Exception as e:
                logger.warning("Ошибка очистки временной директории {}: {}", dir_name, str(e))
        
        if deleted_count > 0:
            logger.debug("Удалено {} временных файлов", deleted_count)
            
    except Exception as e:
        logger.error("Ошибка очистки временных файлов: {}", str(e))


async def optimize_database() -> bool:
    """
    Оптимизация базы данных
    
    Returns:
        True если оптимизация выполнена
    """
    try:
        logger.debug("⚡ Оптимизация базы данных")
        
        async with get_db_connection() as conn:
            # VACUUM - перестраивает БД, уменьшает размер
            await conn.execute("VACUUM")
            
            # ANALYZE - обновляет статистику для оптимизатора запросов
            await conn.execute("ANALYZE")
            
            await conn.commit()
        
        logger.info("✅ База данных оптимизирована")
        return True
        
    except Exception as e:
        logger.error("Ошибка оптимизации базы данных: {}", str(e))
        return False


async def cleanup_inactive_channels() -> int:
    """
    Очистка неактивных каналов
    Деактивация каналов без активности более месяца
    
    Returns:
        Количество деактивированных каналов
    """
    try:
        logger.debug("📺 Проверка неактивных каналов")
        
        channel_crud = get_channel_crud()
        post_crud = get_post_crud()
        
        # Получаем все активные каналы
        active_channels = await channel_crud.get_active_channels()
        
        inactive_cutoff = datetime.now() - timedelta(days=30)  # 30 дней без активности
        deactivated_count = 0
        
        for channel in active_channels:
            # Проверяем есть ли посты за последний месяц
            recent_posts = await post_crud.get_posts_by_channel_since(
                channel.channel_id, 
                inactive_cutoff
            )
            
            if not recent_posts:
                # Деактивируем канал
                await channel_crud.deactivate_channel(channel.id)
                deactivated_count += 1
                
                channel_name = channel.title or channel.username or f"ID: {channel.channel_id}"
                logger.info("Деактивирован неактивный канал: {}", channel_name)
        
        if deactivated_count > 0:
            logger.info("Деактивировано {} неактивных каналов", deactivated_count)
        
        return deactivated_count
        
    except Exception as e:
        logger.error("Ошибка очистки неактивных каналов: {}", str(e))
        return 0


async def cleanup_user_posts() -> int:
    """
    Очистка неактивных примеров постов пользователя
    
    Returns:
        Количество удаленных примеров
    """
    try:
        logger.debug("📝 Очистка старых примеров постов")
        
        user_post_crud = get_user_post_crud()
        
        # Удаляем неактивные примеры старше 90 дней
        cutoff_date = datetime.now() - timedelta(days=90)
        
        # Получаем все неактивные примеры
        all_user_posts = await user_post_crud.get_active_user_posts()
        old_inactive_posts = [
            post for post in all_user_posts 
            if not post.is_active and post.created_at and post.created_at < cutoff_date
        ]
        
        deleted_count = 0
        
        for user_post in old_inactive_posts:
            try:
                success = await user_post_crud.delete_user_post(user_post.id)
                if success:
                    deleted_count += 1
                    logger.debug("Удален старый пример поста {}", user_post.id)
                    
            except Exception as e:
                logger.warning("Не удалось удалить пример поста {}: {}", user_post.id, str(e))
        
        if deleted_count > 0:
            logger.info("Удалено {} старых примеров постов", deleted_count)
        
        return deleted_count
        
    except Exception as e:
        logger.error("Ошибка очистки примеров постов: {}", str(e))
        return 0


async def get_cleanup_statistics() -> Dict[str, Any]:
    """Получить статистику для очистки"""
    try:
        post_crud = get_post_crud()
        channel_crud = get_channel_crud()
        
        # Статистика постов
        total_posts = len(await post_crud.get_all_posts())
        rejected_posts = len(await post_crud.get_posts_by_status(PostStatus.REJECTED))
        old_posts = len(await post_crud.get_posts_before_date(
            datetime.now() - timedelta(days=30)
        ))
        
        # Статистика каналов
        total_channels = len(await channel_crud.get_all_channels())
        active_channels = len(await channel_crud.get_active_channels())
        
        # Размер базы данных
        db_path = Path(get_config().DATABASE_PATH or "./data/channel_agent.db")
        db_size = db_path.stat().st_size if db_path.exists() else 0
        
        return {
            "total_posts": total_posts,
            "rejected_posts": rejected_posts,
            "old_posts": old_posts,
            "total_channels": total_channels,
            "active_channels": active_channels,
            "database_size_bytes": db_size,
            "database_size_mb": round(db_size / (1024 * 1024), 2)
        }
        
    except Exception as e:
        logger.error("Ошибка получения статистики очистки: {}", str(e))
        return {}