"""
Система шаблонов для ежедневных постов
Автозамена переменных с криптовалютными данными
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import json

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.scheduler.coingecko import get_template_variables, apply_template_variables

# Настройка логгера модуля
logger = logger.bind(module="scheduler_templates")


class DailyPostTemplate:
    """Класс для работы с шаблонами ежедневных постов"""
    
    def __init__(self, name: str, template: str, description: str = "", photo_info: Optional[Dict[str, Any]] = None):
        """
        Инициализация шаблона
        
        Args:
            name: Название шаблона
            template: Текст шаблона с переменными (может содержать HTML разметку)
            description: Описание шаблона
            photo_info: Информация о фото если есть (file_id, width, height и т.д.)
        """
        self.name = name
        self.template = template
        self.description = description
        self.photo_info = photo_info
        self.has_photo = bool(photo_info)
        self.created_at = datetime.now()
    
    async def render(self, custom_variables: Optional[Dict[str, str]] = None) -> str:
        """
        Отрендерить шаблон с подстановкой переменных
        
        Args:
            custom_variables: Дополнительные переменные
            
        Returns:
            Отрендеренный текст
        """
        try:
            # Получаем переменные из CoinGecko
            variables = await get_template_variables()
            
            # Добавляем пользовательские переменные
            if custom_variables:
                variables.update(custom_variables)
            
            # Применяем переменные к шаблону
            rendered = apply_template_variables(self.template, variables)
            
            logger.debug("Шаблон '{}' отрендерен: {} символов", self.name, len(rendered))
            return rendered
            
        except Exception as e:
            logger.error("Ошибка рендеринга шаблона '{}': {}", self.name, str(e))
            return self.template


# Захардкоженные шаблоны убраны - используются только пользовательские
DEFAULT_TEMPLATES = {}


class TemplateManager:
    """Менеджер шаблонов ежедневных постов"""
    
    def __init__(self):
        """Инициализация менеджера"""
        self.templates: Dict[str, DailyPostTemplate] = DEFAULT_TEMPLATES.copy()
        self.custom_templates: Dict[str, DailyPostTemplate] = {}
        self._templates_loaded = False
        
        logger.debug("Инициализирован менеджер шаблонов: {} стандартных шаблонов", len(self.templates))
    
    async def _ensure_templates_loaded(self) -> None:
        """Убедиться что пользовательские шаблоны загружены из БД"""
        if not self._templates_loaded:
            try:
                await self._load_templates_from_db()
                self._templates_loaded = True
            except Exception as e:
                logger.error("Ошибка загрузки шаблонов из БД: {}", str(e))
    
    async def get_template(self, name: str) -> Optional[DailyPostTemplate]:
        """Получить шаблон по имени"""
        await self._ensure_templates_loaded()
        return self.templates.get(name) or self.custom_templates.get(name)
    
    async def list_templates(self) -> List[Dict[str, Any]]:
        """Получить список всех доступных шаблонов"""
        await self._ensure_templates_loaded()
        
        templates = []
        
        # Стандартные шаблоны
        for name, template in self.templates.items():
            templates.append({
                'name': name,
                'description': template.description,
                'type': 'default',
                'created_at': template.created_at
            })
        
        # Пользовательские шаблоны
        for name, template in self.custom_templates.items():
            templates.append({
                'name': name,
                'description': template.description,
                'type': 'custom',
                'created_at': template.created_at
            })
        
        return templates
    
    def list_templates_sync(self) -> List[Dict[str, Any]]:
        """Синхронное получение списка шаблонов (без загрузки из БД)"""
        templates = []
        
        # Стандартные шаблоны
        for name, template in self.templates.items():
            templates.append({
                'name': name,
                'description': template.description,
                'type': 'default',
                'created_at': template.created_at
            })
        
        # Пользовательские шаблоны (уже загруженные)
        for name, template in self.custom_templates.items():
            templates.append({
                'name': name,
                'description': template.description,
                'type': 'custom',
                'created_at': template.created_at
            })
        
        return templates
    
    async def add_custom_template(
        self, 
        name: str, 
        template_text: str, 
        description: str = "", 
        photo_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Добавить пользовательский шаблон
        
        Args:
            name: Название шаблона
            template_text: Текст шаблона (может содержать HTML разметку)
            description: Описание
            photo_info: Информация о фото если есть
            
        Returns:
            True если шаблон добавлен успешно
        """
        try:
            await self._ensure_templates_loaded()
            
            if name in self.templates:
                logger.warning("Попытка перезаписать стандартный шаблон: {}", name)
                return False
            
            template = DailyPostTemplate(name, template_text, description, photo_info)
            
            # Добавляем в память
            self.custom_templates[name] = template
            
            # Сохраняем в БД синхронно
            success = await self._save_template_to_db(name, template_text, description, photo_info)
            
            if success:
                photo_text = " (с фото)" if photo_info else ""
                logger.info("Добавлен пользовательский шаблон: {}{}", name, photo_text)
                return True
            else:
                # Если не удалось сохранить в БД, удаляем из памяти
                del self.custom_templates[name]
                logger.error("Не удалось сохранить шаблон '{}' в БД", name)
                return False
            
        except Exception as e:
            logger.error("Ошибка добавления шаблона '{}': {}", name, str(e))
            return False
    
    def add_custom_template_sync(
        self, 
        name: str, 
        template_text: str, 
        description: str = "", 
        photo_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Синхронное добавление пользовательского шаблона (только в память)
        
        Args:
            name: Название шаблона
            template_text: Текст шаблона
            description: Описание
            photo_info: Информация о фото если есть
            
        Returns:
            True если шаблон добавлен успешно
        """
        try:
            if name in self.templates:
                logger.warning("Попытка перезаписать стандартный шаблон: {}", name)
                return False
            
            template = DailyPostTemplate(name, template_text, description, photo_info)
            
            # Добавляем только в память
            self.custom_templates[name] = template
            
            # Сохраняем в БД асинхронно
            asyncio.create_task(self._save_template_to_db(name, template_text, description, photo_info))
            
            photo_text = " (с фото)" if photo_info else ""
            logger.info("Добавлен пользовательский шаблон: {}{}", name, photo_text)
            return True
            
        except Exception as e:
            logger.error("Ошибка добавления шаблона '{}': {}", name, str(e))
            return False
    
    async def remove_custom_template(self, name: str) -> bool:
        """Удалить пользовательский шаблон"""
        try:
            await self._ensure_templates_loaded()
            
            if name in self.custom_templates:
                # Удаляем из памяти
                del self.custom_templates[name]
                
                # Удаляем из БД синхронно
                success = await self._delete_template_from_db(name)
                
                if success:
                    logger.info("Удален пользовательский шаблон: {}", name)
                    return True
                else:
                    logger.error("Не удалось удалить шаблон '{}' из БД", name)
                    return False
            else:
                logger.warning("Шаблон '{}' не найден среди пользовательских", name)
                return False
                
        except Exception as e:
            logger.error("Ошибка удаления шаблона '{}': {}", name, str(e))
            return False
    
    def remove_custom_template_sync(self, name: str) -> bool:
        """Синхронное удаление пользовательского шаблона"""
        try:
            if name in self.custom_templates:
                # Удаляем из памяти
                del self.custom_templates[name]
                
                # Удаляем из БД асинхронно
                asyncio.create_task(self._delete_template_from_db(name))
                
                logger.info("Удален пользовательский шаблон: {}", name)
                return True
            else:
                logger.warning("Шаблон '{}' не найден среди пользовательских", name)
                return False
                
        except Exception as e:
            logger.error("Ошибка удаления шаблона '{}': {}", name, str(e))
            return False
    
    async def render_template(
        self, 
        template_name: str, 
        custom_variables: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        Отрендерить шаблон по имени
        
        Args:
            template_name: Название шаблона
            custom_variables: Дополнительные переменные
            
        Returns:
            Отрендеренный текст или None
        """
        try:
            template = await self.get_template(template_name)
            
            if not template:
                logger.error("Шаблон '{}' не найден", template_name)
                return None
            
            return await template.render(custom_variables)
            
        except Exception as e:
            logger.error("Ошибка рендеринга шаблона '{}': {}", template_name, str(e))
            return None
    
    async def is_template_active(self, template_name: str) -> bool:
        """Проверить активен ли шаблон"""
        try:
            from src.database.connection import get_db_connection
            
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT is_active FROM templates WHERE name = ?",
                    (template_name,)
                )
                result = await cursor.fetchone()
                
                if result:
                    return bool(result[0])
                else:
                    # По умолчанию все шаблоны активны
                    return True
                    
        except Exception as e:
            logger.error("Ошибка проверки активности шаблона '{}': {}", template_name, str(e))
            return True
    
    async def get_template_auto_time(self, template_name: str) -> Optional[str]:
        """Получить время автопубликации шаблона"""
        try:
            from src.database.connection import get_db_connection
            
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT auto_time FROM templates WHERE name = ?",
                    (template_name,)
                )
                result = await cursor.fetchone()
                
                auto_time = result[0] if result and result[0] else None
                logger.debug("Время автопубликации шаблона '{}' из БД: {}", template_name, auto_time)
                
                return auto_time
                    
        except Exception as e:
            logger.error("Ошибка получения времени автопубликации шаблона '{}': {}", template_name, str(e))
            return None
    
    async def get_template_pin_enabled(self, template_name: str) -> bool:
        """Проверить нужно ли закреплять посты из шаблона"""
        try:
            from src.database.connection import get_db_connection
            
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT pin_enabled FROM templates WHERE name = ?",
                    (template_name,)
                )
                result = await cursor.fetchone()
                
                return bool(result[0]) if result and result[0] is not None else False
                    
        except Exception as e:
            logger.error("Ошибка получения настройки закрепления шаблона '{}': {}", template_name, str(e))
            return False
    
    async def set_template_active(self, template_name: str, is_active: bool) -> bool:
        """Установить активность шаблона"""
        try:
            from src.database.connection import get_db_connection
            
            async with get_db_connection() as conn:
                await conn.execute(
                    "UPDATE templates SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
                    (is_active, template_name)
                )
                await conn.commit()
            
            logger.info("Активность шаблона '{}' установлена: {}", template_name, is_active)
            return True
                
        except Exception as e:
            logger.error("Ошибка установки активности шаблона '{}': {}", template_name, str(e))
            return False
    
    async def set_template_pin_enabled(self, template_name: str, pin_enabled: bool) -> bool:
        """Установить закрепление постов шаблона"""
        try:
            from src.database.connection import get_db_connection
            
            async with get_db_connection() as conn:
                await conn.execute(
                    "UPDATE templates SET pin_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
                    (pin_enabled, template_name)
                )
                await conn.commit()
            
            logger.info("Закрепление шаблона '{}' установлено: {}", template_name, pin_enabled)
            return True
                
        except Exception as e:
            logger.error("Ошибка установки закрепления шаблона '{}': {}", template_name, str(e))
            return False
    
    async def set_template_auto_time(self, template_name: str, auto_time: Optional[str]) -> bool:
        """Установить время автопубликации шаблона"""
        try:
            from src.database.connection import get_db_connection
            
            async with get_db_connection() as conn:
                await conn.execute(
                    "UPDATE templates SET auto_time = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
                    (auto_time, template_name)
                )
                await conn.commit()
            
            logger.info("Время автопубликации шаблона '{}' установлено: {}", template_name, auto_time)
            return True
                
        except Exception as e:
            logger.error("Ошибка установки времени шаблона '{}': {}", template_name, str(e))
            return False

    async def get_active_templates_with_time(self) -> List[Dict[str, Any]]:
        """Получить список активных шаблонов с настроенным временем автопубликации"""
        try:
            from src.database.connection import get_db_connection
            
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT name, auto_time, pin_enabled, template_text, description 
                       FROM templates 
                       WHERE is_active = 1 AND auto_time IS NOT NULL AND auto_time != ''"""
                )
                results = await cursor.fetchall()
                
                templates = []
                for row in results:
                    templates.append({
                        'name': row[0],
                        'auto_time': row[1],
                        'pin_enabled': bool(row[2]) if row[2] is not None else False,
                        'template_text': row[3],
                        'description': row[4] or ''
                    })
                
                logger.debug("Найдено {} активных шаблонов с временем автопубликации", len(templates))
                return templates
                    
        except Exception as e:
            logger.error("Ошибка получения активных шаблонов с временем: {}", str(e))
            return []
    
    async def get_first_available_template(self) -> Optional[str]:
        """
        Получить первый доступный пользовательский шаблон
        
        Returns:
            Название первого найденного шаблона или None
        """
        try:
            await self._ensure_templates_loaded()
            
            # Ищем только в пользовательских шаблонах
            for name in self.custom_templates.keys():
                if await self.is_template_active(name):
                    return name
            
            # Если нет активных пользовательских шаблонов
            logger.warning("Нет доступных пользовательских шаблонов для создания поста")
            return None
                
        except Exception as e:
            logger.error("Ошибка поиска доступного шаблона: {}", str(e))
            return None
    
    async def get_template_preview(self, template_name: str) -> Optional[str]:
        """Получить превью шаблона (первые 200 символов)"""
        template = await self.get_template(template_name)
        if template:
            preview = template.template.replace('\n', ' ')[:200]
            if len(template.template) > 200:
                preview += "..."
            return preview
        return None
    
    async def _save_template_to_db(
        self, 
        name: str, 
        template_text: str, 
        description: str, 
        photo_info: Optional[Dict[str, Any]]
    ) -> bool:
        """Сохранить шаблон в БД в таблицу templates"""
        try:
            from src.database.connection import get_db_connection
            
            # Извлекаем данные о фото если есть
            photo_file_id = None
            photo_width = None
            photo_height = None
            photo_size = None
            
            if photo_info:
                photo_file_id = photo_info.get('file_id')
                photo_width = photo_info.get('width')
                photo_height = photo_info.get('height')
                photo_size = photo_info.get('file_size')
            
            async with get_db_connection() as conn:
                await conn.execute(
                    """INSERT OR REPLACE INTO templates 
                       (name, template_text, description, photo_file_id, photo_width, 
                        photo_height, photo_size, is_active, template_type, usage_count,
                        created_at, updated_at) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (name, template_text, description, photo_file_id, photo_width,
                     photo_height, photo_size, True, 'custom', 0,
                     datetime.now().isoformat(), datetime.now().isoformat())
                )
                await conn.commit()
            
            logger.info("Шаблон '{}' сохранен в БД", name)
            return True
            
        except Exception as e:
            logger.error("Ошибка сохранения шаблона '{}' в БД: {}", name, str(e))
            return False
    
    async def _load_templates_from_db(self) -> None:
        """Загрузить пользовательские шаблоны из БД"""
        try:
            from src.database.connection import get_db_connection
            
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT name, template_text, description, photo_file_id, 
                              photo_width, photo_height, photo_size 
                       FROM templates WHERE template_type = 'custom'"""
                )
                rows = await cursor.fetchall()
                
                loaded_count = 0
                for row in rows:
                    try:
                        template_name = row[0]
                        template_text = row[1]
                        description = row[2] or ''
                        
                        # Собираем информацию о фото если есть
                        photo_info = None
                        if row[3]:  # photo_file_id
                            photo_info = {
                                'file_id': row[3],
                                'width': row[4],
                                'height': row[5],
                                'file_size': row[6]
                            }
                        
                        # Создаем объект шаблона
                        template = DailyPostTemplate(
                            name=template_name,
                            template=template_text,
                            description=description,
                            photo_info=photo_info
                        )
                        
                        # Добавляем в память
                        self.custom_templates[template_name] = template
                        loaded_count += 1
                        
                    except Exception as e:
                        logger.error("Ошибка загрузки шаблона из БД: {}", str(e))
                
                if loaded_count > 0:
                    logger.info("Загружено {} пользовательских шаблонов из БД", loaded_count)
                
        except Exception as e:
            logger.error("Ошибка загрузки шаблонов из БД: {}", str(e))
    
    async def _delete_template_from_db(self, name: str) -> bool:
        """Удалить шаблон из БД"""
        try:
            from src.database.connection import get_db_connection
            
            async with get_db_connection() as conn:
                await conn.execute("DELETE FROM templates WHERE name = ?", (name,))
                await conn.commit()
            
            logger.info("Шаблон '{}' удален из БД", name)
            return True
            
        except Exception as e:
            logger.error("Ошибка удаления шаблона '{}' из БД: {}", name, str(e))
            return False


# Глобальный экземпляр менеджера
_template_manager: Optional[TemplateManager] = None


def get_template_manager() -> TemplateManager:
    """Получить глобальный экземпляр менеджера шаблонов"""
    global _template_manager
    
    if _template_manager is None:
        _template_manager = TemplateManager()
    
    return _template_manager


async def create_daily_post_from_template(
    template_name: Optional[str] = None,
    custom_variables: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """
    Создать ежедневный пост из пользовательского шаблона
    
    Args:
        template_name: Название шаблона (если None, используется первый доступный)
        custom_variables: Дополнительные переменные
        
    Returns:
        Готовый пост или None при ошибке
    """
    try:
        logger.info("📝 Создание ежедневного поста из пользовательского шаблона")
        
        template_manager = get_template_manager()
        
        # Если шаблон не указан, используем первый доступный пользовательский
        if template_name is None:
            template_name = await template_manager.get_first_available_template()
            if not template_name:
                logger.error("❌ Нет доступных пользовательских шаблонов для создания поста")
                return None
            logger.info("Выбран первый доступный шаблон: {}", template_name)
        
        # Проверяем что шаблон существует
        template = await template_manager.get_template(template_name)
        if not template:
            logger.error("❌ Шаблон '{}' не найден", template_name)
            return None
        
        # Рендерим шаблон
        post_content = await template_manager.render_template(
            template_name, 
            custom_variables
        )
        
        if post_content:
            logger.info("✅ Пост создан из шаблона '{}': {} символов", 
                       template_name, len(post_content))
            return post_content
        else:
            logger.error("❌ Не удалось создать пост из шаблона '{}'", template_name)
            return None
            
    except Exception as e:
        logger.error("❌ Ошибка создания поста из шаблона: {}", str(e))
        return None


def get_available_variables() -> List[str]:
    """Получить список доступных переменных для шаблонов"""
    return [
        # Криптовалюты
        'BTC', 'BTC_PRICE', 'BTC_CHANGE', 'BTC_CHANGE_NUM',
        'ETH', 'ETH_PRICE', 'ETH_CHANGE', 'ETH_CHANGE_NUM',
        'SOL', 'SOL_PRICE', 'SOL_CHANGE', 'SOL_CHANGE_NUM',
        'ADA', 'ADA_PRICE', 'ADA_CHANGE', 'ADA_CHANGE_NUM',
        'DOT', 'DOT_PRICE', 'DOT_CHANGE', 'DOT_CHANGE_NUM',
        
        # Рынок
        'MARKET_CAP', 'MARKET_CHANGE', 'MARKET_CHANGE_NUM',
        'BTC_DOMINANCE', 'BITCOIN_DOMINANCE',
        
        # Время
        'DATE', 'TIME', 'WEEKDAY', 'WEEKDAY_RU'
    ]