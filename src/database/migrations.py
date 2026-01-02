"""
Модуль миграций базы данных
Создание и обновление схемы базы данных
"""

from typing import List, Dict, Any

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from .connection import get_db_connection, get_db_transaction
from src.utils.exceptions import DatabaseMigrationError

# Настройка логгера модуля
logger = logger.bind(module="migrations")


# SQL запросы для создания таблиц
CREATE_TABLES_SQL = {
    "channels": """
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id BIGINT UNIQUE NOT NULL,
            username VARCHAR(255),
            title VARCHAR(255),
            is_active BOOLEAN DEFAULT TRUE,
            last_message_id BIGINT DEFAULT 0,
            posts_processed INTEGER DEFAULT 0,
            posts_approved INTEGER DEFAULT 0,
            posts_rejected INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            added_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    
    "posts": """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            original_text TEXT,
            processed_text TEXT,
            photo_file_id VARCHAR(255),
            relevance_score INTEGER,
            sentiment VARCHAR(20),
            status VARCHAR(20) DEFAULT 'pending',
            source_link VARCHAR(500),
            posted_date DATETIME,
            scheduled_date DATETIME,
            moderation_notes TEXT,
            ai_analysis TEXT,
            error_message TEXT,
            pin_post BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(channel_id, message_id),
            FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
        )
    """,
    
    "user_posts": """
        CREATE TABLE IF NOT EXISTS user_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            category VARCHAR(100),
            style_tags VARCHAR(500),
            usage_count INTEGER DEFAULT 0,
            quality_score INTEGER,
            source_link VARCHAR(500),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            added_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    
    "settings": """
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR(255) PRIMARY KEY,
            value TEXT,
            description TEXT,
            category VARCHAR(100),
            is_system BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            updated_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    
    "templates": """
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) UNIQUE NOT NULL,
            template_text TEXT NOT NULL,
            description TEXT,
            photo_file_id VARCHAR(255),
            photo_width INTEGER,
            photo_height INTEGER,
            photo_size INTEGER,
            is_active BOOLEAN DEFAULT TRUE,
            template_type VARCHAR(50) DEFAULT 'custom',
            usage_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME
        )
    """
}

# SQL запросы для создания индексов
CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_channels_channel_id ON channels(channel_id)",
    "CREATE INDEX IF NOT EXISTS idx_channels_username ON channels(username)",
    "CREATE INDEX IF NOT EXISTS idx_channels_active ON channels(is_active)",
    
    "CREATE INDEX IF NOT EXISTS idx_posts_channel_message ON posts(channel_id, message_id)",
    "CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status)",
    "CREATE INDEX IF NOT EXISTS idx_posts_relevance ON posts(relevance_score)",
    "CREATE INDEX IF NOT EXISTS idx_posts_created_date ON posts(created_date)",
    "CREATE INDEX IF NOT EXISTS idx_posts_scheduled_date ON posts(scheduled_date)",
    
    "CREATE INDEX IF NOT EXISTS idx_user_posts_active ON user_posts(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_user_posts_category ON user_posts(category)",
    "CREATE INDEX IF NOT EXISTS idx_user_posts_quality ON user_posts(quality_score)",
    
    "CREATE INDEX IF NOT EXISTS idx_settings_category ON settings(category)",
    "CREATE INDEX IF NOT EXISTS idx_settings_system ON settings(is_system)",
    
    "CREATE INDEX IF NOT EXISTS idx_templates_name ON templates(name)",
    "CREATE INDEX IF NOT EXISTS idx_templates_type ON templates(template_type)",
    "CREATE INDEX IF NOT EXISTS idx_templates_active ON templates(is_active)"
]

# Начальные данные
INITIAL_DATA = {
    "settings": [
        ("ai.model", '"gpt-4o-mini"', "Модель OpenAI для анализа", "AI", True),
        ("ai.relevance_threshold", "6", "Минимальный порог релевантности", "AI", True),
        ("monitoring.interval", "300", "Интервал мониторинга в секундах", "Мониторинг", True),
        ("posts.max_per_day", "10", "Максимум постов в день", "Посты", False),
        ("daily_post.enabled", "true", "Включить ежедневные посты", "Ежедневные посты", False),
        ("daily_post.time", '"09:00"', "Время ежедневных постов UTC+3", "Ежедневные посты", False),
        ("daily_post.pin_enabled", "false", "Закреплять ежедневные посты", "Ежедневные посты", False),
        ("coingecko.coins", '"bitcoin,ethereum,solana"', "Монеты для отслеживания", "CoinGecko", False)
    ]
}


class DatabaseMigrator:
    """Класс для управления миграциями базы данных"""
    
    def __init__(self):
        """Инициализация мигратора"""
        self.version_table = "schema_versions"
    
    async def create_version_table(self) -> None:
        """Создать таблицу версий схемы"""
        sql = f"""
            CREATE TABLE IF NOT EXISTS {self.version_table} (
                version INTEGER PRIMARY KEY,
                description TEXT,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        
        async with get_db_connection() as conn:
            await conn.execute(sql)
            await conn.commit()
        
        logger.debug("Создана таблица версий схемы")
    
    async def get_current_version(self) -> int:
        """Получить текущую версию схемы"""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    f"SELECT MAX(version) FROM {self.version_table}"
                )
                result = await cursor.fetchone()
                return result[0] if result[0] is not None else 0
        except Exception:
            return 0
    
    async def set_version(self, version: int, description: str) -> None:
        """Установить версию схемы"""
        async with get_db_connection() as conn:
            await conn.execute(
                f"INSERT OR REPLACE INTO {self.version_table} (version, description) VALUES (?, ?)",
                (version, description)
            )
            await conn.commit()
        
        logger.info("Установлена версия схемы: {} - {}", version, description)
    
    async def create_tables(self) -> None:
        """Создать все таблицы"""
        async with get_db_transaction() as conn:
            # Создаем таблицы в правильном порядке (учитывая FK)
            table_order = ["channels", "posts", "user_posts", "settings", "templates"]
            
            for table_name in table_order:
                sql = CREATE_TABLES_SQL[table_name]
                await conn.execute(sql)
                logger.debug("Создана таблица: {}", table_name)
        
        logger.info("Все таблицы созданы успешно")
    
    async def create_indexes(self) -> None:
        """Создать все индексы"""
        async with get_db_transaction() as conn:
            for sql in CREATE_INDEXES_SQL:
                await conn.execute(sql)
                logger.debug("Выполнен SQL: {}", sql.split("ON")[0] + "ON...")
        
        logger.info("Все индексы созданы успешно")
    
    async def insert_initial_data(self) -> None:
        """Вставить начальные данные"""
        async with get_db_transaction() as conn:
            # Вставляем настройки
            for key, value, description, category, is_system in INITIAL_DATA["settings"]:
                # Проверяем, существует ли настройка
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM settings WHERE key = ?", (key,)
                )
                exists = (await cursor.fetchone())[0] > 0
                
                if not exists:
                    await conn.execute(
                        """INSERT INTO settings 
                           (key, value, description, category, is_system) 
                           VALUES (?, ?, ?, ?, ?)""",
                        (key, value, description, category, is_system)
                    )
                    logger.debug("Добавлена настройка: {}", key)
        
        logger.info("Начальные данные добавлены успешно")
    
    async def run_migration_v1(self) -> None:
        """Миграция версии 1 - создание базовой схемы"""
        logger.info("Выполняется миграция v1: создание базовой схемы")
        
        try:
            await self.create_tables()
            await self.create_indexes()
            await self.insert_initial_data()
            await self.set_version(1, "Базовая схема БД")
            
            logger.info("Миграция v1 выполнена успешно")
            
        except Exception as e:
            error_msg = f"Ошибка выполнения миграции v1: {str(e)}"
            logger.error(error_msg)
            raise DatabaseMigrationError("v1", error_msg)

    async def run_migration_v2(self) -> None:
        """Миграция версии 2 - добавление полей для индивидуальных настроек шаблонов"""
        logger.info("Выполняется миграция v2: индивидуальные настройки шаблонов")
        
        try:
            async with get_db_transaction() as conn:
                # Проверяем существует ли таблица templates
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='templates'"
                )
                table_exists = await cursor.fetchone()
                
                if not table_exists:
                    logger.info("Таблица templates не существует, пропускаем миграцию v2")
                    await self.set_version(2, "Пропущена - таблица не создана")
                    return
                
                # Проверяем существуют ли уже поля (для безопасности)
                cursor = await conn.execute("PRAGMA table_info(templates)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]
                
                fields_added = 0
                
                # Добавляем поле auto_time если его нет
                if 'auto_time' not in column_names:
                    await conn.execute("ALTER TABLE templates ADD COLUMN auto_time VARCHAR(10)")
                    logger.debug("Добавлено поле auto_time в таблицу templates")
                    fields_added += 1
                
                # Добавляем поле pin_enabled если его нет  
                if 'pin_enabled' not in column_names:
                    await conn.execute("ALTER TABLE templates ADD COLUMN pin_enabled BOOLEAN DEFAULT FALSE")
                    logger.debug("Добавлено поле pin_enabled в таблицу templates")
                    fields_added += 1
                
                if fields_added > 0:
                    logger.info("Добавлено {} новых полей в таблицу templates", fields_added)
                else:
                    logger.info("Все поля уже существуют в таблице templates")
                
            await self.set_version(2, "Индивидуальные настройки шаблонов")
            logger.info("Миграция v2 выполнена успешно")
            
        except Exception as e:
            error_msg = f"Ошибка выполнения миграции v2: {str(e)}"
            logger.error(error_msg)
            raise DatabaseMigrationError("v2", error_msg)
    
    async def run_migration_v3(self) -> None:
        """Миграция версии 3 - добавление поля photo_path для локального хранения фото"""
        logger.info("Выполняется миграция v3: добавление поля photo_path")
        
        try:
            async with get_db_transaction() as conn:
                # Проверяем существует ли таблица posts
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='posts'"
                )
                table_exists = await cursor.fetchone()
                
                if not table_exists:
                    logger.info("Таблица posts не существует, пропускаем миграцию v3")
                    await self.set_version(3, "Пропущена - таблица не создана")
                    return
                
                # Проверяем существует ли уже поле photo_path
                cursor = await conn.execute("PRAGMA table_info(posts)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]
                
                if 'photo_path' not in column_names:
                    await conn.execute("ALTER TABLE posts ADD COLUMN photo_path VARCHAR(500)")
                    logger.debug("Добавлено поле photo_path в таблицу posts")
                    logger.info("Поле photo_path добавлено для локального хранения фото")
                else:
                    logger.info("Поле photo_path уже существует в таблице posts")
                
            await self.set_version(3, "Добавлено поле photo_path для локального хранения фото")
            logger.info("Миграция v3 выполнена успешно")
            
        except Exception as e:
            error_msg = f"Ошибка выполнения миграции v3: {str(e)}"
            logger.error(error_msg)
            raise DatabaseMigrationError("v3", error_msg)
    
    async def run_migration_v4(self) -> None:
        """Миграция версии 4 - добавление поддержки видео в таблицу posts"""
        logger.info("Выполняется миграция v4: добавление поддержки видео")
        
        try:
            async with get_db_transaction() as conn:
                # Проверяем существует ли таблица posts
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='posts'"
                )
                table_exists = await cursor.fetchone()
                
                if not table_exists:
                    logger.info("Таблица posts не существует, пропускаем миграцию v4")
                    await self.set_version(4, "Пропущена - таблица не создана")
                    return
                
                # Проверяем существующие поля
                cursor = await conn.execute("PRAGMA table_info(posts)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]
                
                fields_added = 0
                
                # Добавляем поле video_file_id если его нет
                if 'video_file_id' not in column_names:
                    await conn.execute("ALTER TABLE posts ADD COLUMN video_file_id VARCHAR(255)")
                    logger.debug("Добавлено поле video_file_id в таблицу posts")
                    fields_added += 1
                
                # Добавляем поле video_path если его нет
                if 'video_path' not in column_names:
                    await conn.execute("ALTER TABLE posts ADD COLUMN video_path VARCHAR(500)")
                    logger.debug("Добавлено поле video_path в таблицу posts")
                    fields_added += 1
                
                # Добавляем поле media_type если его нет (photo, video, или null)
                if 'media_type' not in column_names:
                    await conn.execute("ALTER TABLE posts ADD COLUMN media_type VARCHAR(20)")
                    logger.debug("Добавлено поле media_type в таблицу posts")
                    fields_added += 1
                
                # Добавляем поле video_duration если его нет (в секундах)
                if 'video_duration' not in column_names:
                    await conn.execute("ALTER TABLE posts ADD COLUMN video_duration INTEGER")
                    logger.debug("Добавлено поле video_duration в таблицу posts")
                    fields_added += 1
                
                # Добавляем поле video_width если его нет
                if 'video_width' not in column_names:
                    await conn.execute("ALTER TABLE posts ADD COLUMN video_width INTEGER")
                    logger.debug("Добавлено поле video_width в таблицу posts")
                    fields_added += 1
                
                # Добавляем поле video_height если его нет  
                if 'video_height' not in column_names:
                    await conn.execute("ALTER TABLE posts ADD COLUMN video_height INTEGER")
                    logger.debug("Добавлено поле video_height в таблицу posts")
                    fields_added += 1
                
                if fields_added > 0:
                    logger.info("Добавлено {} новых полей для поддержки видео", fields_added)
                else:
                    logger.info("Все поля для видео уже существуют в таблице posts")
                
                # Устанавливаем media_type для существующих постов с фото
                await conn.execute("""
                    UPDATE posts 
                    SET media_type = 'photo' 
                    WHERE (photo_file_id IS NOT NULL OR photo_path IS NOT NULL) 
                    AND media_type IS NULL
                """)
                
            await self.set_version(4, "Добавлена поддержка видео в таблицу posts")
            logger.info("Миграция v4 выполнена успешно")
            
        except Exception as e:
            error_msg = f"Ошибка выполнения миграции v4: {str(e)}"
            logger.error(error_msg)
            raise DatabaseMigrationError("v4", error_msg)
    
    async def run_migration_v5(self) -> None:
        """Миграция версии 5 - добавление таблицы custom_emojis для Premium эмодзи"""
        logger.info("Выполняется миграция v5: таблица custom_emojis")

        try:
            async with get_db_transaction() as conn:
                # Создаем таблицу custom_emojis
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS custom_emojis (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        standard_emoji VARCHAR(20) UNIQUE NOT NULL,
                        document_id BIGINT NOT NULL,
                        alt_text VARCHAR(20) NOT NULL,
                        category VARCHAR(50) DEFAULT 'general',
                        description VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE,
                        usage_count INTEGER DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME
                    )
                """)
                logger.debug("Создана таблица custom_emojis")

                # Создаем индексы
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_emoji_standard ON custom_emojis(standard_emoji)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_emoji_category ON custom_emojis(category)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_emoji_active ON custom_emojis(is_active)"
                )
                logger.debug("Созданы индексы для таблицы custom_emojis")

            await self.set_version(5, "Добавлена таблица custom_emojis для Premium эмодзи")
            logger.info("Миграция v5 выполнена успешно")

        except Exception as e:
            error_msg = f"Ошибка выполнения миграции v5: {str(e)}"
            logger.error(error_msg)
            raise DatabaseMigrationError("v5", error_msg)

    async def run_migration_v6(self) -> None:
        """Миграция версии 6 - добавление поля extracted_links для хранения ссылок из постов"""
        logger.info("Выполняется миграция v6: добавление поля extracted_links")

        try:
            async with get_db_transaction() as conn:
                # Проверяем существует ли таблица posts
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='posts'"
                )
                table_exists = await cursor.fetchone()

                if not table_exists:
                    logger.info("Таблица posts не существует, пропускаем миграцию v6")
                    await self.set_version(6, "Пропущена - таблица не создана")
                    return

                # Проверяем существует ли уже поле extracted_links
                cursor = await conn.execute("PRAGMA table_info(posts)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

                if 'extracted_links' not in column_names:
                    await conn.execute("ALTER TABLE posts ADD COLUMN extracted_links TEXT")
                    logger.debug("Добавлено поле extracted_links в таблицу posts")
                    logger.info("Поле extracted_links добавлено для хранения ссылок из постов")
                else:
                    logger.info("Поле extracted_links уже существует в таблице posts")

            await self.set_version(6, "Добавлено поле extracted_links для хранения ссылок")
            logger.info("Миграция v6 выполнена успешно")

        except Exception as e:
            error_msg = f"Ошибка выполнения миграции v6: {str(e)}"
            logger.error(error_msg)
            raise DatabaseMigrationError("v6", error_msg)

    async def run_migration_v8(self) -> None:
        """Миграция версии 8 - добавление таблицы coingecko_cache и поля retry_count"""
        logger.info("Выполняется миграция v8: кэш CoinGecko и retry для постов")

        try:
            async with get_db_transaction() as conn:
                # Создаем таблицу coingecko_cache для персистентного хранения данных
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS coingecko_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cache_key VARCHAR(100) UNIQUE NOT NULL,
                        data TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                logger.debug("Создана таблица coingecko_cache")

                # Создаем индекс для быстрого поиска
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_coingecko_cache_key ON coingecko_cache(cache_key)"
                )

                # Добавляем поле retry_count в таблицу posts для отслеживания попыток публикации
                cursor = await conn.execute("PRAGMA table_info(posts)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

                if 'retry_count' not in column_names:
                    await conn.execute("ALTER TABLE posts ADD COLUMN retry_count INTEGER DEFAULT 0")
                    logger.debug("Добавлено поле retry_count в таблицу posts")

            await self.set_version(8, "Добавлен кэш CoinGecko и retry_count для постов")
            logger.info("Миграция v8 выполнена успешно")

        except Exception as e:
            error_msg = f"Ошибка выполнения миграции v8: {str(e)}"
            logger.error(error_msg)
            raise DatabaseMigrationError("v8", error_msg)

    async def run_migration_v7(self) -> None:
        """Миграция версии 7 - добавление поля media_items для хранения множественных медиа (альбомов)"""
        logger.info("Выполняется миграция v7: добавление поля media_items для альбомов")

        try:
            async with get_db_transaction() as conn:
                # Проверяем существует ли таблица posts
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='posts'"
                )
                table_exists = await cursor.fetchone()

                if not table_exists:
                    logger.info("Таблица posts не существует, пропускаем миграцию v7")
                    await self.set_version(7, "Пропущена - таблица не создана")
                    return

                # Проверяем существует ли уже поле media_items
                cursor = await conn.execute("PRAGMA table_info(posts)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

                if 'media_items' not in column_names:
                    await conn.execute("ALTER TABLE posts ADD COLUMN media_items TEXT")
                    logger.debug("Добавлено поле media_items в таблицу posts")
                    logger.info("Поле media_items добавлено для хранения множественных медиа (альбомов)")

                    # Мигрируем существующие данные: конвертируем photo_path/video_path в media_items
                    # Для постов с photo_path
                    await conn.execute("""
                        UPDATE posts
                        SET media_items = json_array(json_object(
                            'type', 'photo',
                            'path', photo_path,
                            'position', 0
                        ))
                        WHERE photo_path IS NOT NULL
                        AND media_items IS NULL
                    """)
                    logger.debug("Мигрированы существующие посты с фото в media_items")

                    # Для постов с video_path (без photo_path)
                    await conn.execute("""
                        UPDATE posts
                        SET media_items = json_array(json_object(
                            'type', 'video',
                            'path', video_path,
                            'position', 0
                        ))
                        WHERE video_path IS NOT NULL
                        AND photo_path IS NULL
                        AND media_items IS NULL
                    """)
                    logger.debug("Мигрированы существующие посты с видео в media_items")
                else:
                    logger.info("Поле media_items уже существует в таблице posts")

            await self.set_version(7, "Добавлено поле media_items для хранения альбомов")
            logger.info("Миграция v7 выполнена успешно")

        except Exception as e:
            error_msg = f"Ошибка выполнения миграции v7: {str(e)}"
            logger.error(error_msg)
            raise DatabaseMigrationError("v7", error_msg)

    async def run_migration_v9(self) -> None:
        """Миграция версии 9 - добавление поля published_message_id для хранения ID опубликованного поста"""
        logger.info("Выполняется миграция v9: добавление поля published_message_id")

        try:
            async with get_db_transaction() as conn:
                # Проверяем существует ли таблица posts
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='posts'"
                )
                table_exists = await cursor.fetchone()

                if not table_exists:
                    logger.info("Таблица posts не существует, пропускаем миграцию v9")
                    await self.set_version(9, "Пропущена - таблица не создана")
                    return

                # Проверяем существует ли уже поле published_message_id
                cursor = await conn.execute("PRAGMA table_info(posts)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

                if 'published_message_id' not in column_names:
                    await conn.execute("ALTER TABLE posts ADD COLUMN published_message_id BIGINT")
                    logger.debug("Добавлено поле published_message_id в таблицу posts")
                    logger.info("Поле published_message_id добавлено для хранения ID опубликованных постов")
                else:
                    logger.info("Поле published_message_id уже существует в таблице posts")

            await self.set_version(9, "Добавлено поле published_message_id для ссылок на опубликованные посты")
            logger.info("Миграция v9 выполнена успешно")

        except Exception as e:
            error_msg = f"Ошибка выполнения миграции v9: {str(e)}"
            logger.error(error_msg)
            raise DatabaseMigrationError("v9", error_msg)

    async def run_all_migrations(self) -> None:
        """Выполнить все необходимые миграции"""
        logger.info("Начало выполнения миграций БД")
        
        try:
            # Создаем таблицу версий
            await self.create_version_table()
            
            # Получаем текущую версию
            current_version = await self.get_current_version()
            logger.info("Текущая версия схемы БД: {}", current_version)
            
            # Выполняем миграции по порядку
            migrations = [
                (1, self.run_migration_v1, "Создание базовой схемы"),
                (2, self.run_migration_v2, "Индивидуальные настройки шаблонов"),
                (3, self.run_migration_v3, "Добавление поля photo_path для локального хранения фото"),
                (4, self.run_migration_v4, "Добавление поддержки видео в таблицу posts"),
                (5, self.run_migration_v5, "Добавление таблицы custom_emojis для Premium эмодзи"),
                (6, self.run_migration_v6, "Добавление поля extracted_links для ссылок из постов"),
                (7, self.run_migration_v7, "Добавление поля media_items для хранения альбомов"),
                (8, self.run_migration_v8, "Добавление кэша CoinGecko и retry_count для постов"),
                (9, self.run_migration_v9, "Добавление поля published_message_id для ссылок на опубликованные посты")
            ]
            
            for version, migration_func, description in migrations:
                if current_version < version:
                    logger.info("Применяется миграция v{}: {}", version, description)
                    await migration_func()
                else:
                    logger.debug("Миграция v{} уже применена", version)
            
            logger.info("Все миграции выполнены успешно")
            
        except Exception as e:
            error_msg = f"Критическая ошибка при выполнении миграций: {str(e)}"
            logger.error(error_msg)
            raise DatabaseMigrationError("all", error_msg)


# Глобальный экземпляр мигратора
_migrator: DatabaseMigrator = DatabaseMigrator()


async def initialize_database_schema() -> None:
    """Инициализировать схему базы данных"""
    logger.info("Инициализация схемы базы данных")
    await _migrator.run_all_migrations()
    logger.info("Схема базы данных инициализирована")


async def get_database_info() -> Dict[str, Any]:
    """Получить информацию о состоянии БД"""
    try:
        current_version = await _migrator.get_current_version()
        
        # Получаем количество записей в основных таблицах
        async with get_db_connection() as conn:
            tables_info = {}
            for table in ["channels", "posts", "user_posts", "settings", "templates"]:
                try:
                    cursor = await conn.execute(f"SELECT COUNT(*) FROM {table}")
                    count = (await cursor.fetchone())[0]
                    tables_info[table] = count
                except Exception:
                    tables_info[table] = "ERROR"
        
        return {
            "schema_version": current_version,
            "tables": tables_info,
            "status": "OK"
        }
    
    except Exception as e:
        logger.error("Ошибка получения информации о БД: {}", str(e))
        return {
            "schema_version": None,
            "tables": {},
            "status": f"ERROR: {str(e)}"
        }