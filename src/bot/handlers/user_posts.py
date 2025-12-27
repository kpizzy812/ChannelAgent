"""
Обработчики команд для управления примерами постов пользователя
Позволяет добавлять, просматривать и редактировать примеры своего стиля
"""

import asyncio
from typing import Optional, List

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# aiogram 3.x импорты
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode
from aiogram import html

# Локальные импорты
from src.database.crud.user_post import get_user_post_crud
from src.utils.telegram_parser import get_telegram_parser, get_post_extractor
from src.userbot.client import get_userbot_client
from src.ai.processor import get_ai_processor
from src.bot.keyboards.user_posts import (
    get_user_posts_menu_keyboard,
    get_user_post_management_keyboard,
    get_category_selection_keyboard,
    get_quality_score_keyboard,
    get_ai_processing_choice_keyboard
)
from src.bot.filters.owner import OwnerFilter
from src.utils.html_formatter import (
    bold, italic, format_success_message, format_info_message,
    format_list_items, get_parse_mode, link, code, format_error_message
)

# Настройка логгера модуля
logger = logger.bind(module="bot_user_posts")


def _extract_formatted_text_from_aiogram(message) -> str:
    """
    Извлекает текст с форматированием из aiogram Message объекта
    
    Args:
        message: aiogram Message объект с entities
        
    Returns:
        HTML отформатированный текст для Telegram
    """
    try:
        # Используем встроенную возможность aiogram для получения HTML
        if hasattr(message, 'html_text') and message.html_text:
            formatted_text = message.html_text
            logger.debug("Использован message.html_text для извлечения форматирования")
            return formatted_text
        
        # Fallback - если html_text недоступен, конвертируем entities вручную
        text = message.text or ""
        entities = message.entities or []
        
        if not entities:
            logger.debug("Нет entities в сообщении, возвращаем plain text")
            return text
        
        # Конвертируем aiogram entities в HTML
        return _convert_aiogram_entities_to_html(text, entities)
        
    except Exception as e:
        logger.error("Ошибка извлечения форматированного текста из aiogram: {}", str(e))
        # В случае ошибки возвращаем plain text
        return message.text or ""


def _convert_aiogram_entities_to_html(text: str, entities) -> str:
    """
    Конвертирует aiogram entities в HTML формат
    
    Args:
        text: Исходный текст
        entities: Список aiogram entities
        
    Returns:
        HTML отформатированный текст
    """
    try:
        from aiogram.types import MessageEntity
        
        if not entities:
            return text
        
        # Сортируем entities по offset
        sorted_entities = sorted(entities, key=lambda e: e.offset)
        
        # Создаем события начала/конца для каждого entity  
        events = []
        for entity in sorted_entities:
            if entity.offset >= 0 and entity.length > 0 and entity.offset + entity.length <= len(text):
                events.append({
                    'pos': entity.offset,
                    'type': 'start',
                    'entity': entity
                })
                events.append({
                    'pos': entity.offset + entity.length,
                    'type': 'end',
                    'entity': entity
                })
        
        # Сортируем события по позиции
        events.sort(key=lambda e: (e['pos'], e['type'] == 'start'))
        
        result = []
        current_pos = 0
        open_tags = []
        
        for event in events:
            pos = event['pos']
            
            # Добавляем текст до текущей позиции
            if pos > current_pos:
                result.append(text[current_pos:pos])
            
            if event['type'] == 'start':
                # Открываем тег
                tag = _get_aiogram_html_open_tag(event['entity'])
                if tag:
                    result.append(tag)
                    open_tags.append(event['entity'])
            else:
                # Закрываем тег
                if event['entity'] in open_tags:
                    tag = _get_aiogram_html_close_tag(event['entity'])
                    if tag:
                        result.append(tag)
                    open_tags.remove(event['entity'])
            
            current_pos = pos
        
        # Добавляем оставшийся текст
        if current_pos < len(text):
            result.append(text[current_pos:])
        
        # Закрываем незакрытые теги
        for entity in reversed(open_tags):
            tag = _get_aiogram_html_close_tag(entity)
            if tag:
                result.append(tag)
        
        formatted_text = ''.join(result)
        logger.debug("Aiogram entities конвертированы в HTML: {} символов", len(formatted_text))
        
        return formatted_text
        
    except Exception as e:
        logger.error("Ошибка конвертации aiogram entities: {}", str(e))
        return text


def _get_aiogram_html_open_tag(entity) -> str:
    """Получить открывающий HTML тег для aiogram entity"""
    entity_type = entity.type
    
    if entity_type == "bold":
        return "<strong>"
    elif entity_type == "italic":
        return "<i>"
    elif entity_type == "underline":
        return "<u>"
    elif entity_type == "strikethrough":
        return "<s>"
    elif entity_type == "spoiler":
        return "<span class=\"tg-spoiler\">"
    elif entity_type == "code":
        return "<code>"
    elif entity_type == "pre":
        return "<pre>"
    elif entity_type == "text_link":
        url = getattr(entity, 'url', '')
        return f'<a href="{url}">'
    else:
        return ""


def _get_aiogram_html_close_tag(entity) -> str:
    """Получить закрывающий HTML тег для aiogram entity"""
    entity_type = entity.type
    
    if entity_type == "bold":
        return "</strong>"
    elif entity_type == "italic":
        return "</i>"
    elif entity_type == "underline":
        return "</u>"
    elif entity_type == "strikethrough":
        return "</s>"
    elif entity_type == "spoiler":
        return "</span>"
    elif entity_type == "code":
        return "</code>"
    elif entity_type == "pre":
        return "</pre>"
    elif entity_type == "text_link":
        return "</a>"
    else:
        return ""

# Роутер для примеров постов
user_posts_router = Router()


class UserPostStates(StatesGroup):
    """Состояния FSM для управления примерами постов"""
    waiting_for_text = State()
    waiting_for_link = State()
    waiting_for_ai_choice = State()  # Выбор AI стилизации
    waiting_for_category = State()
    waiting_for_quality_score = State()
    editing_post = State()


@user_posts_router.message(Command("examples"), OwnerFilter())
async def examples_menu_command(message: Message):
    """Главное меню примеров постов"""
    try:
        user_post_crud = get_user_post_crud()
        
        # Получаем статистику
        stats = await user_post_crud.get_statistics()
        
        stats_text = f"""
📝 {bold('Примеры ваших постов')}

📊 {bold('Статистика:')}
{format_list_items([
    f'Всего примеров: {stats.get("total_posts", 0)}',
    f'Активных: {stats.get("active_posts", 0)}',
    f'Средняя оценка: {stats.get("average_quality_score", 0)}/10'
])}

{bold('Категории:')}"""
        
        for category, count in stats.get('categories', {}).items():
            category_name = {
                'crypto': '🚀 Криптовалюты',
                'macro': '📊 Макроэкономика', 
                'web3': '🌐 Web3',
                'telegram': '✈️ Telegram',
                'gamefi': '🎮 GameFi'
            }.get(category, f'📌 {category}')
            stats_text += f"\n• {category_name}: {count}"
        
        keyboard = get_user_posts_menu_keyboard()
        
        await message.answer(
            stats_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.info("Показано меню примеров постов пользователю {}", message.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка отображения меню примеров постов: {}", str(e))
        await message.answer("❌ Произошла ошибка при загрузке примеров постов")


@user_posts_router.callback_query(F.data == "add_example_text", OwnerFilter())
async def add_example_text_callback(callback: CallbackQuery, state: FSMContext):
    """Добавить пример поста текстом"""
    await callback.answer()
    
    await callback.message.edit_text(
        "📝 <b>Отправьте текст вашего поста-примера:</b>\n\n"
        "💡 <i>Это может быть пост из вашего канала, который демонстрирует ваш стиль написания. Пост будет использован AI для обучения вашему стилю.</i>\n\n"
        "❌ /cancel - отменить",
        parse_mode=get_parse_mode()
    )
    
    await state.set_state(UserPostStates.waiting_for_text)
    logger.debug("Пользователь {} начал добавление примера текстом", callback.from_user.id)


@user_posts_router.callback_query(F.data == "add_example_link", OwnerFilter())
async def add_example_link_callback(callback: CallbackQuery, state: FSMContext):
    """Добавить пример поста по ссылке"""
    await callback.answer()
    
    await callback.message.edit_text(
        f"""🔗 {bold('Отправьте ссылки на ваши посты в Telegram:')}

{bold('Поддерживаемые форматы:')}
• {code('https://t.me/channel_name/123')}
• {code('https://t.me/c/1234567890/123')}

📝 {bold('Можно отправить:')}
• Одну ссылку
• Несколько ссылок (каждую с новой строки)

💡 {italic('Убедитесь, что UserBot подключен и имеет доступ к каналам')}

❌ /cancel - отменить""",
        parse_mode=get_parse_mode()
    )
    
    await state.set_state(UserPostStates.waiting_for_link)
    logger.debug("Пользователь {} начал добавление примера по ссылке", callback.from_user.id)


@user_posts_router.message(UserPostStates.waiting_for_text, OwnerFilter())
async def process_example_text(message: Message, state: FSMContext):
    """Обработать добавленный текст примера"""
    try:
        # Извлекаем текст с сохранением форматирования из aiogram entities
        formatted_text = _extract_formatted_text_from_aiogram(message)
        
        # Также получаем plain text для проверок
        plain_text = message.text or ""
        
        if not plain_text or len(plain_text.strip()) < 10:
            await message.answer("❌ Текст слишком короткий. Минимум 10 символов.")
            return
        
        if len(plain_text) > 4000:
            await message.answer("❌ Текст слишком длинный. Максимум 4000 символов.")
            return
        
        # Сохраняем форматированный текст в состоянии
        await state.update_data(post_text=formatted_text)
        
        keyboard = get_ai_processing_choice_keyboard()
        
        # Проверяем есть ли форматирование
        has_formatting = len(formatted_text) > len(plain_text)
        formatting_info = " с форматированием ✨" if has_formatting else ""
        
        await message.answer(
            f"📝 <b>Текст получен</b> ({len(plain_text)} символов{formatting_info})\n\n"
            f"🤖 {bold('Хотите применить AI стилизацию?')}\n"
            "AI может уникализировать и адаптировать пост под ваш стиль",
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        await state.set_state(UserPostStates.waiting_for_ai_choice)
        logger.debug("Получен текст примера от пользователя {}: {} символов, форматирование: {}", 
                    message.from_user.id, len(plain_text), "есть" if has_formatting else "нет")
        
    except Exception as e:
        logger.error("Ошибка обработки текста примера: {}", str(e))
        await message.answer("❌ Произошла ошибка при обработке текста")


@user_posts_router.message(UserPostStates.waiting_for_link, OwnerFilter()) 
async def process_example_link(message: Message, state: FSMContext):
    """Обработать ссылки на примеры постов"""
    try:
        input_text = message.text.strip()
        
        # Разбиваем на отдельные строки и извлекаем ссылки
        lines = input_text.split('\n')
        links = []
        
        for line in lines:
            line = line.strip()
            if line:
                links.append(line)
        
        if not links:
            await message.answer("❌ Не найдено ни одной ссылки")
            return
        
        # Валидируем все ссылки
        parser = get_telegram_parser()
        valid_links = []
        invalid_links = []
        
        for link in links:
            if parser.validate_telegram_link(link):
                valid_links.append(link)
            else:
                invalid_links.append(link)
        
        if invalid_links:
            await message.answer(
                f"❌ Некорректные ссылки:\n" + 
                "\n".join([f"• {link}" for link in invalid_links]) +
                "\n\nПоддерживаемые форматы:\n" +
                "• https://t.me/channel_name/123\n" +
                "• https://t.me/c/1234567890/123"
            )
            return
        
        if not valid_links:
            await message.answer("❌ Не найдено корректных ссылок")
            return
        
        # Показываем процесс загрузки
        loading_message = await message.answer(
            f"⏳ Загружаю {len(valid_links)} пост{'ов' if len(valid_links) > 1 else ''}...\n" +
            f"Это может занять некоторое время."
        )
        
        # Проверяем подключение UserBot с автоматическим переподключением
        try:
            from src.userbot.auth_manager import get_auth_manager, AuthStatus
            
            auth_manager = get_auth_manager()
            status = await auth_manager.get_status()
            
            if status != AuthStatus.CONNECTED:
                status_messages = {
                    AuthStatus.DISCONNECTED: "UserBot не подключен",
                    AuthStatus.CONNECTING: "UserBot подключается...",
                    AuthStatus.WAITING_CODE: "Ожидание SMS кода",
                    AuthStatus.WAITING_PASSWORD: "Ожидание 2FA пароля",
                    AuthStatus.ERROR: "Ошибка подключения UserBot"
                }
                
                await loading_message.edit_text(
                    f"❌ {status_messages.get(status, 'Неизвестный статус UserBot')}\n\n" +
                    "Для загрузки постов по ссылкам нужно подключить UserBot.\n\n" +
                    "🔧 Используйте команду /connect_userbot или нажмите кнопку в главном меню"
                )
                return
                
            userbot_client = await get_userbot_client()
            if not userbot_client:
                await loading_message.edit_text(
                    "❌ UserBot не инициализирован\n\n" +
                    "Попробуйте переподключить UserBot: /connect_userbot"
                )
                return
                
            # Проверяем и восстанавливаем соединение Telethon клиента
            if hasattr(userbot_client, 'client') and userbot_client.client:
                if not userbot_client.client.is_connected():
                    logger.warning("Telethon клиент отключен, пытаемся переподключить...")
                    
                    try:
                        # Показываем процесс переподключения
                        await loading_message.edit_text(
                            "🔄 UserBot отключился, восстанавливаем соединение...\n" +
                            "Подождите несколько секунд"
                        )
                        
                        # Пытаемся переподключиться
                        await userbot_client.connect()
                        
                        # Проверяем результат переподключения
                        if not userbot_client.client.is_connected():
                            await loading_message.edit_text(
                                "❌ Не удалось восстановить соединение UserBot\n\n" +
                                "🔧 Попробуйте:\n" +
                                "1. Переподключить UserBot: /connect_userbot\n" +
                                "2. Проверить интернет-соединение\n" +
                                "3. Убедиться что аккаунт не заблокирован"
                            )
                            return
                        
                        logger.info("Соединение UserBot восстановлено успешно")
                        
                        # Обновляем сообщение после успешного переподключения
                        await loading_message.edit_text(
                            f"✅ Соединение восстановлено!\n\n" +
                            f"⏳ Загружаю {len(valid_links)} пост{'ов' if len(valid_links) > 1 else ''}..."
                        )
                        
                    except Exception as reconnect_error:
                        logger.error("Ошибка переподключения UserBot: {}", str(reconnect_error))
                        await loading_message.edit_text(
                            f"❌ Ошибка переподключения: {str(reconnect_error)[:100]}\n\n" +
                            "🔧 Требуется ручное переподключение: /connect_userbot"
                        )
                        return
            else:
                await loading_message.edit_text(
                    "❌ UserBot клиент не инициализирован\n\n" +
                    "🔧 Попробуйте переподключить UserBot: /connect_userbot"
                )
                return
                    
        except Exception as e:
            logger.error("Ошибка проверки статуса UserBot: {}", str(e))
            await loading_message.edit_text(
                f"❌ Ошибка проверки UserBot: {str(e)[:100]}\n\n" +
                "🔧 Попробуйте переподключить UserBot: /connect_userbot"
            )
            return
        
        # Извлекаем посты
        post_extractor = get_post_extractor()
        successful_posts = []
        failed_links = []
        
        for i, link in enumerate(valid_links):
            try:
                await loading_message.edit_text(
                    f"⏳ Загружаю пост {i+1}/{len(valid_links)}...\n" +
                    f"Ссылка: {link[:50]}{'...' if len(link) > 50 else ''}"
                )
                
                post_data = await post_extractor.extract_post_from_link(link, userbot_client)
                
                if not post_data:
                    failed_links.append((link, "Не удалось загрузить"))
                    continue
                
                if not post_data["text"] or len(post_data["text"].strip()) < 10:
                    failed_links.append((link, "Недостаточно текста"))
                    continue
                
                successful_posts.append({
                    "text": post_data["text"],
                    "link": link,
                    "channel_title": post_data.get("channel_title"),
                    "channel_username": post_data.get("channel_username")
                })
                
            except Exception as e:
                logger.error("Ошибка загрузки поста {}: {}", link, str(e))
                failed_links.append((link, f"Ошибка: {str(e)[:50]}"))
        
        # Формируем результат
        if not successful_posts:
            await loading_message.edit_text(
                "❌ Не удалось загрузить ни одного поста\n\n" +
                "Ошибки:\n" + 
                "\n".join([f"• {link}: {error}" for link, error in failed_links])
            )
            return
        
        # Если есть неудачные загрузки - показываем предупреждение
        result_text = f"✅ Загружено {len(successful_posts)} из {len(valid_links)} постов"
        
        if failed_links:
            result_text += f"\n\n⚠️ Не удалось загрузить {len(failed_links)} пост{'ов' if len(failed_links) > 1 else ''}:\n"
            result_text += "\n".join([f"• {error}" for _, error in failed_links[:3]])
            if len(failed_links) > 3:
                result_text += f"\n• и еще {len(failed_links) - 3}..."
        
        # Показываем превью первого поста
        first_post = successful_posts[0]
        preview_text = first_post["text"]
        if len(preview_text) > 300:
            preview_text = preview_text[:300] + "..."
        
        channel_info = ""
        if first_post.get("channel_title"):
            channel_info = f"\n📺 Канал: {html.quote(first_post['channel_title'])}"
        if first_post.get("channel_username"):
            channel_info += f" (@{html.quote(first_post['channel_username'])})"
        
        result_text += f"{channel_info}\n\n📝 Превью первого поста:\n{html.quote(preview_text)}"
        
        if len(successful_posts) > 1:
            result_text += f"\n\n📋 Будет добавлено всего {len(successful_posts)} примеров"
        
        result_text += f"\n\n🤖 {bold('Хотите применить AI стилизацию?')}\nAI может уникализировать и адаптировать посты под ваш стиль"
        
        # Сохраняем все посты в состоянии
        await state.update_data(
            multiple_posts=successful_posts,
            is_multiple=True
        )
        
        keyboard = get_ai_processing_choice_keyboard()
        
        await loading_message.edit_text(
            result_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        await state.set_state(UserPostStates.waiting_for_ai_choice)
        logger.info("Загружено {} постов по ссылкам от пользователя {}", 
                   len(successful_posts), message.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка обработки ссылок: {}", str(e))
        await message.answer("❌ Произошла ошибка при обработке ссылок")


@user_posts_router.callback_query(F.data.startswith("category_"), UserPostStates.waiting_for_category, OwnerFilter())
async def process_category_selection(callback: CallbackQuery, state: FSMContext):
    """Обработать выбор категории"""
    try:
        await callback.answer()
        
        category = callback.data.replace("category_", "")
        await state.update_data(category=category)
        
        category_names = {
            "crypto": "🚀 Криптовалюты",
            "macro": "📊 Макроэкономика",
            "web3": "🌐 Web3", 
            "telegram": "✈️ Telegram",
            "gamefi": "🎮 GameFi",
            "general": "📌 Общее"
        }
        
        data = await state.get_data()
        is_multiple = data.get("is_multiple", False)
        
        keyboard = get_quality_score_keyboard()
        
        if is_multiple:
            posts_count = len(data.get("multiple_posts", []))
            quality_text = f"⭐ Оцените качество этих {posts_count} примеров (1-10):"
        else:
            quality_text = "⭐ Оцените качество этого примера (1-10):"
        
        await callback.message.edit_text(
            f"📋 <b>Категория:</b> {html.quote(category_names.get(category, category))}\n\n"
            f"{quality_text}\n"
            "• 1-3: Плохой пример\n"
            "• 4-6: Средний пример\n" 
            "• 7-8: Хороший пример\n"
            "• 9-10: Отличный пример",
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        await state.set_state(UserPostStates.waiting_for_quality_score)
        logger.debug("Выбрана категория {} для примера пользователя {}", category, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка выбора категории: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@user_posts_router.callback_query(F.data.startswith("quality_"), UserPostStates.waiting_for_quality_score, OwnerFilter())
async def process_quality_score(callback: CallbackQuery, state: FSMContext):
    """Обработать выбор оценки качества и сохранить примеры"""
    try:
        await callback.answer()
        
        quality_score = int(callback.data.replace("quality_", ""))
        
        # Получаем все данные из состояния
        data = await state.get_data()
        category = data["category"]
        is_multiple = data.get("is_multiple", False)
        
        user_post_crud = get_user_post_crud()
        category_names = {
            "crypto": "🚀 Криптовалюты",
            "macro": "📊 Макроэкономика", 
            "web3": "🌐 Web3",
            "telegram": "✈️ Telegram",
            "gamefi": "🎮 GameFi",
            "general": "📌 Общее"
        }
        
        if is_multiple:
            # Обработка множественных постов
            multiple_posts = data.get("multiple_posts", [])
            
            if not multiple_posts:
                await callback.message.edit_text("❌ Нет данных для сохранения")
                await state.clear()
                return
            
            # Показываем процесс сохранения
            await callback.message.edit_text(
                f"💾 Сохраняю {len(multiple_posts)} примеров...\n"
                f"Это может занять некоторое время."
            )
            
            successful_saves = []
            failed_saves = []
            
            for i, post_data in enumerate(multiple_posts):
                try:
                    created_post = await user_post_crud.create_user_post(
                        text=post_data["text"],
                        category=category,
                        quality_score=quality_score,
                        source_link=post_data["link"]
                    )
                    
                    if created_post:
                        successful_saves.append((created_post.id, post_data["link"]))
                    else:
                        failed_saves.append(post_data["link"])
                        
                except Exception as e:
                    logger.error("Ошибка сохранения поста {}: {}", post_data["link"], str(e))
                    failed_saves.append(post_data["link"])
            
            # Формируем результат
            if successful_saves:
                success_text = f"""✅ <b>Сохранено {len(successful_saves)} из {len(multiple_posts)} примеров!</b>

📋 <b>Категория:</b> {html.quote(category_names.get(category, category))}
⭐ <b>Оценка:</b> {quality_score}/10
📊 <b>Общая длина:</b> {sum(len(p["text"]) for p in multiple_posts)} символов

📝 <b>ID примеров:</b> {', '.join([str(post_id) for post_id, _ in successful_saves[:5]])}"""
                
                if len(successful_saves) > 5:
                    success_text += f" и еще {len(successful_saves) - 5}..."
                
                if failed_saves:
                    success_text += f"\n\n⚠️ <b>Не удалось сохранить {len(failed_saves)} примеров</b>"
                
                await callback.message.edit_text(success_text, parse_mode="HTML")
                
                logger.info("Создано {} примеров постов от пользователя {}: категория={}, оценка={}", 
                           len(successful_saves), callback.from_user.id, category, quality_score)
            else:
                await callback.message.edit_text("❌ Не удалось сохранить ни одного примера")
        
        else:
            # Обработка одиночного поста
            post_text = data["post_text"]
            source_link = data.get("source_link")
            
            created_post = await user_post_crud.create_user_post(
                text=post_text,
                category=category,
                quality_score=quality_score,
                source_link=source_link
            )
            
            if created_post:
                success_text = f"""✅ <b>Пример поста сохранен!</b>

📝 <b>ID:</b> {created_post.id}
📋 <b>Категория:</b> {html.quote(category_names.get(category, category))}
⭐ <b>Оценка:</b> {quality_score}/10
📏 <b>Длина:</b> {len(post_text)} символов"""
                
                if source_link:
                    success_text += f"\n🔗 <b>Источник:</b> <a href=\"{source_link}\">ссылка</a>"
                
                await callback.message.edit_text(success_text, parse_mode="HTML")
                
                logger.info("Создан пример поста ID={} от пользователя {}: категория={}, оценка={}", 
                           created_post.id, callback.from_user.id, category, quality_score)
            else:
                await callback.message.edit_text("❌ Не удалось сохранить пример поста")
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logger.error("Ошибка сохранения примеров постов: {}", str(e))
        await callback.answer("❌ Произошла ошибка при сохранении", show_alert=True)


@user_posts_router.callback_query(F.data == "view_examples", OwnerFilter())
async def view_examples_callback(callback: CallbackQuery):
    """Просмотр существующих примеров с фото"""
    try:
        await callback.answer()
        
        user_post_crud = get_user_post_crud()
        examples = await user_post_crud.get_active_user_posts(limit=10)
        
        if not examples:
            await callback.message.edit_text(
                "📝 У вас пока нет примеров постов\n\n"
                "Используйте команду /examples чтобы добавить примеры"
            )
            return

        # Если есть примеры с фото, отправляем их как отдельные сообщения
        examples_with_photos = [ex for ex in examples if ex.photo_file_id]
        examples_text_only = [ex for ex in examples if not ex.photo_file_id]
        
        # Отправляем примеры с фото
        for i, example in enumerate(examples_with_photos, 1):
            category_emoji = {
                "crypto": "🚀",
                "macro": "📊", 
                "web3": "🌐",
                "telegram": "✈️",
                "gamefi": "🎮"
            }.get(example.category, "📌")
            
            # Формируем подпись к фото
            caption = f"""📝 {bold(f'Пример #{example.id}')} {category_emoji}

⭐ Оценка: {example.quality_score or '?'}/10
📂 Категория: {example.category or 'не указана'}

{example.text[:800] + '...' if len(example.text) > 800 else example.text}"""
            
            try:
                # Отправляем фото с подписью
                from aiogram import Bot
                from src.bot.main import get_bot_instance
                
                bot = get_bot_instance()
                await bot.send_photo(
                    chat_id=callback.message.chat.id,
                    photo=example.photo_file_id,
                    caption=caption,
                    parse_mode=get_parse_mode()
                )
                
                logger.debug("Отправлен пример с фото ID {}", example.id)
                
            except Exception as photo_error:
                logger.error("Ошибка отправки фото для примера {}: {}", example.id, str(photo_error))
                # Если не удалось отправить фото, добавляем в текстовый список
                examples_text_only.append(example)
        
        # Если есть текстовые примеры, показываем их списком
        if examples_text_only:
            category_emojis = {"crypto": "🚀", "macro": "📊", "web3": "🌐", "telegram": "✈️", "gamefi": "🎮"}
            text_examples_list = []
            for i, ex in enumerate(examples_text_only):
                emoji = category_emojis.get(ex.category, "📌")
                item = f'{i + len(examples_with_photos) + 1}. {emoji} ID {ex.id} (⭐{ex.quality_score or "?"}): {ex.get_preview(60)}'
                text_examples_list.append(item)
            
            examples_text = f"""📝 {bold('Текстовые примеры постов:')}

{format_list_items(text_examples_list)}"""
            
            keyboard = get_user_posts_menu_keyboard()
            
            await callback.message.edit_text(
                examples_text,
                reply_markup=keyboard,
                parse_mode=get_parse_mode()
            )
        else:
            # Если все примеры были с фото, просто обновим сообщение
            summary_text = f"""📝 {bold('Ваши примеры постов отправлены выше')}

📊 {bold('Статистика:')}
{format_list_items([
    f'Всего примеров: {len(examples)}',
    f'С фотографиями: {len(examples_with_photos)}',
    f'Только текст: {len(examples_text_only)}'
])}"""
            
            keyboard = get_user_posts_menu_keyboard()
            
            await callback.message.edit_text(
                summary_text,
                reply_markup=keyboard,
                parse_mode=get_parse_mode()
            )
        
        logger.info("Показаны примеры постов пользователю {}: {} с фото, {} текстовых", 
                   callback.from_user.id, len(examples_with_photos), len(examples_text_only))
        
    except Exception as e:
        logger.error("Ошибка просмотра примеров: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@user_posts_router.callback_query(F.data == "examples_stats", OwnerFilter())
async def examples_stats_callback(callback: CallbackQuery):
    """Показать подробную статистику примеров"""
    try:
        await callback.answer()
        
        user_post_crud = get_user_post_crud()
        stats = await user_post_crud.get_statistics()
        
        # Получаем топ примеры
        top_examples = await user_post_crud.get_active_user_posts(
            limit=5 
        )
        
        stats_text = f"""📊 {bold('Подробная статистика примеров')}

📈 {bold('Общие показатели:')}
{format_list_items([
    f'Всего примеров: {stats.get("total_posts", 0)}',
    f'Активных: {stats.get("active_posts", 0)}',
    f'Средняя оценка: {stats.get("average_quality_score", 0):.1f}/10',
    f'Общее использование: {stats.get("total_usage", 0)} раз'
])}

🏆 {bold('Категории:')}"""
        
        for category, count in stats.get('categories', {}).items():
            category_name = {
                'crypto': '🚀 Криптовалюты',
                'macro': '📊 Макроэкономика', 
                'web3': '🌐 Web3',
                'telegram': '✈️ Telegram',
                'gamefi': '🎮 GameFi',
                'general': '📌 Общее'
            }.get(category, f'📌 {category}')
            stats_text += f"\n• {category_name}: {count}"
        
        if top_examples:
            stats_text += f"\n\n⭐ {bold('Топ-5 примеров:')}"
            for i, example in enumerate(top_examples, 1):
                category_emoji = {
                    "crypto": "🚀", "macro": "📊", "web3": "🌐",
                    "telegram": "✈️", "gamefi": "🎮"
                }.get(example.category, "📌")
                
                preview = example.get_preview(40)
                stats_text += f"\n{i}. {category_emoji} ID {example.id} (⭐{example.quality_score or '?'}, 🔄{example.usage_count}): {preview}"
        
        keyboard = get_user_posts_menu_keyboard()
        
        await callback.message.edit_text(
            stats_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Показана статистика примеров пользователю {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа статистики примеров: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@user_posts_router.callback_query(F.data == "refresh_examples", OwnerFilter())
async def refresh_examples_callback(callback: CallbackQuery):
    """Обновить меню примеров"""
    try:
        await callback.answer("🔄 Обновлено!")
        
        user_post_crud = get_user_post_crud()
        
        # Получаем статистику
        stats = await user_post_crud.get_statistics()
        
        stats_text = f"""
📝 {bold('Примеры ваших постов')}

📊 {bold('Статистика:')}
{format_list_items([
    f'Всего примеров: {stats.get("total_posts", 0)}',
    f'Активных: {stats.get("active_posts", 0)}',
    f'Средняя оценка: {stats.get("average_quality_score", 0):.1f}/10'
])}

{bold('Категории:')}"""
        
        for category, count in stats.get('categories', {}).items():
            category_name = {
                'crypto': '🚀 Криптовалюты',
                'macro': '📊 Макроэкономика', 
                'web3': '🌐 Web3',
                'telegram': '✈️ Telegram',
                'gamefi': '🎮 GameFi'
            }.get(category, f'📌 {category}')
            stats_text += f"\n• {category_name}: {count}"
        
        keyboard = get_user_posts_menu_keyboard()
        
        await callback.message.edit_text(
            stats_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Обновлено меню примеров для пользователя {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка обновления примеров: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@user_posts_router.callback_query(F.data == "examples_settings", OwnerFilter())
async def examples_settings_callback(callback: CallbackQuery):
    """Настройки примеров постов"""
    try:
        await callback.answer()
        
        settings_text = f"""⚙️ {bold('Настройки примеров постов')}

🎯 {bold('Текущие настройки:')}
{format_list_items([
    'Максимум примеров для AI: 3',
    'Автоматическое обновление рейтинга: включено',
    'Использование неактивных: отключено',
    'Приоритет по категориям: включен'
])}

💡 {bold('Рекомендации:')}
{format_list_items([
    'Добавляйте примеры разных категорий',
    'Оценивайте качество честно (1-10)',
    'Регулярно обновляйте примеры',
    'Удаляйте устаревшие посты'
])}

🔧 Настройки пока в разработке."""
        
        keyboard = get_user_posts_menu_keyboard()
        
        await callback.message.edit_text(
            settings_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Показаны настройки примеров пользователю {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка показа настроек примеров: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@user_posts_router.callback_query(F.data == "examples_list", OwnerFilter())
async def examples_list_callback(callback: CallbackQuery):
    """Показать список примеров для управления"""
    try:
        await callback.answer()
        
        user_post_crud = get_user_post_crud()
        examples = await user_post_crud.get_active_user_posts(limit=50)
        
        if not examples:
            await callback.message.edit_text(
                "📝 У вас пока нет примеров постов\n\n"
                "Используйте команду /examples чтобы добавить примеры"
            )
            return
        
        # Импортируем новую клавиатуру
        from src.bot.keyboards.user_posts import get_examples_list_keyboard
        
        list_text = f"""📝 {bold('Управление примерами постов')}

Всего примеров: {len(examples)}

Выберите пример для просмотра и управления:"""
        
        keyboard = get_examples_list_keyboard(examples, page=1)
        
        await callback.message.edit_text(
            list_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Показан список примеров пользователю {}: {} примеров", 
                    callback.from_user.id, len(examples))
        
    except Exception as e:
        logger.error("Ошибка показа списка примеров: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@user_posts_router.callback_query(F.data.startswith("view_example_"), OwnerFilter())
async def view_example_callback(callback: CallbackQuery):
    """Просмотр отдельного примера поста"""
    try:
        await callback.answer()
        
        example_id = int(callback.data.replace("view_example_", ""))
        
        user_post_crud = get_user_post_crud()
        example = await user_post_crud.get_user_post_by_id(example_id)
        
        if not example:
            await callback.answer("❌ Пример не найден", show_alert=True)
            return
        
        # Импортируем клавиатуру управления
        from src.bot.keyboards.user_posts import get_example_management_keyboard
        
        # Проверяем есть ли фото у примера
        if example.photo_file_id:
            # Отправляем пример с фото
            try:
                category_emoji = {
                    "crypto": "🚀", "macro": "📊", "web3": "🌐",
                    "telegram": "✈️", "gamefi": "🎮", "general": "📌"
                }.get(example.category, "📌")
                
                # Безопасное форматирование даты
                from datetime import datetime
                
                added_date_str = 'неизвестно'
                if example.added_date:
                    if isinstance(example.added_date, datetime):
                        added_date_str = example.added_date.strftime('%d.%m.%Y %H:%M')
                    elif isinstance(example.added_date, str):
                        try:
                            # Пытаемся парсить строку как datetime
                            dt = datetime.fromisoformat(example.added_date.replace('Z', '+00:00'))
                            added_date_str = dt.strftime('%d.%m.%Y %H:%M')
                        except:
                            added_date_str = example.added_date  # Оставляем как есть если не получается парсить
                
                caption = f"""📝 {bold(f'Пример #{example.id}')} {category_emoji}

⭐ Оценка: {example.quality_score or '?'}/10
📂 Категория: {example.category or 'не указана'}
🔄 Использовано: {example.usage_count} раз
📅 Добавлен: {added_date_str}
🔘 Статус: {'✅ Активен' if example.is_active else '❌ Неактивен'}

{example.text}"""
                
                keyboard = get_example_management_keyboard(example_id)
                
                from src.bot.main import get_bot_instance
                bot = get_bot_instance()
                
                await bot.send_photo(
                    chat_id=callback.message.chat.id,
                    photo=example.photo_file_id,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode=get_parse_mode()
                )
                
                # Удаляем старое сообщение
                try:
                    await callback.message.delete()
                except:
                    pass
                
                logger.info("Показан пример с фото {} пользователю {}", example_id, callback.from_user.id)
                
            except Exception as photo_error:
                logger.error("Ошибка отправки фото для примера {}: {}", example_id, str(photo_error))
                # Показываем как текст при ошибке фото
                await _show_example_as_text(callback, example, example_id)
        else:
            # Показываем как текстовое сообщение
            await _show_example_as_text(callback, example, example_id)
        
    except Exception as e:
        logger.error("Ошибка просмотра примера: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


async def _show_example_as_text(callback, example, example_id):
    """Показать пример как текстовое сообщение"""
    from src.bot.keyboards.user_posts import get_example_management_keyboard
    
    category_emoji = {
        "crypto": "🚀", "macro": "📊", "web3": "🌐",
        "telegram": "✈️", "gamefi": "🎮", "general": "📌"
    }.get(example.category, "📌")
    
    # Безопасное форматирование даты
    from datetime import datetime
    
    added_date_str = 'неизвестно'
    if example.added_date:
        if isinstance(example.added_date, datetime):
            added_date_str = example.added_date.strftime('%d.%m.%Y %H:%M')
        elif isinstance(example.added_date, str):
            try:
                # Пытаемся парсить строку как datetime
                dt = datetime.fromisoformat(example.added_date.replace('Z', '+00:00'))
                added_date_str = dt.strftime('%d.%m.%Y %H:%M')
            except:
                added_date_str = example.added_date  # Оставляем как есть если не получается парсить
    
    example_text = f"""📝 {bold(f'Пример #{example.id}')} {category_emoji}

⭐ {bold('Оценка:')} {example.quality_score or '?'}/10
📂 {bold('Категория:')} {example.category or 'не указана'}
🔄 {bold('Использовано:')} {example.usage_count} раз
📅 {bold('Добавлен:')} {added_date_str}
🔘 {bold('Статус:')} {'✅ Активен' if example.is_active else '❌ Неактивен'}

📄 {bold('Текст:')}
{example.text}"""
    
    keyboard = get_example_management_keyboard(example_id)
    
    await callback.message.edit_text(
        example_text,
        reply_markup=keyboard,
        parse_mode=get_parse_mode()
    )
    
    logger.info("Показан текстовый пример {} пользователю {}", example_id, callback.from_user.id)


@user_posts_router.callback_query(F.data.startswith("delete_example_"), OwnerFilter())
async def delete_example_callback(callback: CallbackQuery):
    """Подтверждение удаления примера"""
    try:
        await callback.answer()
        
        example_id = int(callback.data.replace("delete_example_", ""))
        
        user_post_crud = get_user_post_crud()
        example = await user_post_crud.get_user_post_by_id(example_id)
        
        if not example:
            await callback.answer("❌ Пример не найден", show_alert=True)
            return
        
        # Импортируем клавиатуру подтверждения
        from src.bot.keyboards.user_posts import get_confirm_delete_keyboard
        
        confirmation_text = f"""🗑️ {bold('Удаление примера')}

Вы действительно хотите удалить этот пример?

📝 ID: {example.id}
📂 Категория: {example.category or 'не указана'}
⭐ Оценка: {example.quality_score or '?'}/10

⚠️ {bold('Это действие нельзя отменить!')}"""
        
        keyboard = get_confirm_delete_keyboard(example_id)
        
        await callback.message.edit_text(
            confirmation_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.debug("Запрошено подтверждение удаления примера {} пользователем {}", 
                    example_id, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка запроса удаления примера: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@user_posts_router.callback_query(F.data.startswith("confirm_delete_"), OwnerFilter())
async def confirm_delete_callback(callback: CallbackQuery):
    """Подтверждённое удаление примера"""
    try:
        await callback.answer("🗑️ Пример удалён")
        
        example_id = int(callback.data.replace("confirm_delete_", ""))
        
        user_post_crud = get_user_post_crud()
        success = await user_post_crud.delete_user_post(example_id)
        
        if success:
            result_text = format_success_message(
                "Пример удалён!",
                f"Пример #{example_id} успешно удалён из ваших примеров."
            )
        else:
            result_text = format_error_message(
                "Ошибка удаления",
                "Не удалось удалить пример. Возможно, он уже был удалён."
            )
        
        # Возвращаемся к списку примеров
        user_posts = await user_post_crud.get_active_user_posts(limit=50)
        
        if user_posts:
            from src.bot.keyboards.user_posts import get_examples_list_keyboard
            keyboard = get_examples_list_keyboard(user_posts, page=1)
            
            list_text = f"""{result_text}

📝 {bold('Управление примерами постов')}

Всего примеров: {len(user_posts)}

Выберите пример для просмотра и управления:"""
            
        else:
            keyboard = get_user_posts_menu_keyboard()
            list_text = f"""{result_text}

📝 У вас больше нет примеров постов.
Используйте команду /examples чтобы добавить новые."""
        
        await callback.message.edit_text(
            list_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.info("Пример {} удалён пользователем {}", example_id, callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка удаления примера: {}", str(e))
        await callback.answer("❌ Ошибка удаления", show_alert=True)


@user_posts_router.callback_query(F.data == "clear_all_examples", OwnerFilter())
async def clear_all_examples_callback(callback: CallbackQuery):
    """Очистить все примеры постов (с подтверждением)"""
    try:
        await callback.answer()
        
        user_post_crud = get_user_post_crud()
        examples_count = len(await user_post_crud.get_active_user_posts())
        
        if examples_count == 0:
            await callback.answer("❌ Нет примеров для удаления", show_alert=True)
            return
        
        # Клавиатура подтверждения
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚠️ Да, очистить ВСЁ",
                    callback_data="confirm_clear_all_examples"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="examples_list"
                )
            ]
        ])
        
        warning_text = f"""⚠️ {bold('ВНИМАНИЕ! Очистка всех примеров')}

Вы действительно хотите удалить ВСЕ примеры постов?

📊 {bold('Будет удалено:')}
• Всего примеров: {examples_count}
• Все категории примеров
• Вся статистика использования

🚨 {bold('ЭТО ДЕЙСТВИЕ НЕЛЬЗЯ ОТМЕНИТЬ!')}

Примеры используются AI для анализа вашего стиля. После удаления качество стилизации может ухудшиться."""
        
        await callback.message.edit_text(
            warning_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.warning("Запрос на очистку всех примеров пользователем {}", callback.from_user.id)
        
    except Exception as e:
        logger.error("Ошибка запроса очистки всех примеров: {}", str(e))
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@user_posts_router.callback_query(F.data == "confirm_clear_all_examples", OwnerFilter())
async def confirm_clear_all_examples_callback(callback: CallbackQuery):
    """Подтверждённая очистка всех примеров"""
    try:
        await callback.answer("🗑️ Очищаю все примеры...")
        
        # Показываем процесс очистки
        await callback.message.edit_text(
            "🗑️ Очищаю все примеры постов...\n"
            "Это может занять несколько секунд."
        )
        
        user_post_crud = get_user_post_crud()
        
        # Получаем все примеры для подсчёта
        all_examples = await user_post_crud.get_active_user_posts(limit=1000)
        deleted_count = 0
        failed_count = 0
        
        # Удаляем все примеры
        for example in all_examples:
            try:
                success = await user_post_crud.delete_user_post(example.id)
                if success:
                    deleted_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error("Ошибка удаления примера {}: {}", example.id, str(e))
                failed_count += 1
        
        # Результат очистки
        if deleted_count > 0:
            result_text = format_success_message(
                "Все примеры очищены!",
                f"Успешно удалено: {deleted_count} примеров"
            )
            if failed_count > 0:
                result_text += f"\n\n⚠️ Не удалось удалить: {failed_count} примеров"
        else:
            result_text = format_error_message(
                "Ошибка очистки",
                "Не удалось удалить примеры"
            )
        
        result_text += f"""

📝 {bold('Что дальше?')}
• Добавьте новые примеры ваших постов
• Используйте команду /examples
• Загрузите примеры по ссылкам Telegram

💡 {bold('Рекомендация:')} Добавьте 3-5 качественных примеров вашего стиля для лучшей работы AI."""
        
        keyboard = get_user_posts_menu_keyboard()
        
        await callback.message.edit_text(
            result_text,
            reply_markup=keyboard,
            parse_mode=get_parse_mode()
        )
        
        logger.info("Очищены все примеры пользователем {}: удалено={}, ошибок={}", 
                   callback.from_user.id, deleted_count, failed_count)
        
    except Exception as e:
        logger.error("Ошибка очистки всех примеров: {}", str(e))
        await callback.message.edit_text(
            format_error_message(
                "Ошибка очистки",
                f"Произошла ошибка при очистке примеров: {str(e)[:100]}"
            ),
            parse_mode=get_parse_mode()
        )


@user_posts_router.message(Command("cancel"), StateFilter("*"), OwnerFilter())
async def cancel_handler(message: Message, state: FSMContext):
    """Отменить текущее действие"""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активных действий для отмены")
        return
    
    await state.clear()
    await message.answer("❌ Действие отменено")
    logger.debug("Пользователь {} отменил действие: {}", message.from_user.id, current_state)


@user_posts_router.callback_query(F.data == "ai_stylize_info", UserPostStates.waiting_for_ai_choice, OwnerFilter())
async def ai_stylize_info_callback(callback: CallbackQuery):
    """Показать информацию о AI стилизации"""
    await callback.answer()
    
    info_text = f"""🤖 {bold('Что такое AI стилизация?')}

✨ {bold('AI анализирует ваши примеры')} и применяет ваш стиль к новому посту:
• Адаптирует тон и манеру изложения
• Добавляет характерное форматирование
• Сохраняет ключевую информацию
• Делает пост уникальным

📊 {bold('Что происходит:')}
1. AI изучает ваши существующие примеры
2. Анализирует стилевые особенности
3. Переписывает пост в вашем стиле
4. Добавляет подходящее форматирование

💡 {bold('Рекомендуется:')} Если пост с другого канала - используйте AI для уникализации"""

    keyboard = get_ai_processing_choice_keyboard()
    
    await callback.message.edit_text(
        info_text,
        reply_markup=keyboard,
        parse_mode=get_parse_mode()
    )


@user_posts_router.callback_query(F.data == "ai_stylize_yes", UserPostStates.waiting_for_ai_choice, OwnerFilter())
async def ai_stylize_yes_callback(callback: CallbackQuery, state: FSMContext):
    """Применить AI стилизацию к посту(ам)"""
    await callback.answer()
    
    data = await state.get_data()
    is_multiple = data.get("is_multiple", False)
    
    if is_multiple:
        multiple_posts = data.get("multiple_posts", [])
        posts_count = len(multiple_posts)
        
        await callback.message.edit_text(
            f"🤖 Применяю AI стилизацию к {posts_count} пост{'ам' if posts_count > 1 else 'у'}...\n"
            f"Это может занять {posts_count * 5}-{posts_count * 10} секунд."
        )
        
        ai_processor = get_ai_processor()
        processed_posts = []
        failed_posts = []
        
        for i, post_data in enumerate(multiple_posts):
            try:
                await callback.message.edit_text(
                    f"🤖 Обрабатываю пост {i+1}/{posts_count} через AI...\n"
                    f"Прогресс: {int((i/posts_count)*100)}%"
                )
                
                # Применяем AI стилизацию
                stylization_result = await ai_processor.stylize_user_post(
                    raw_text=post_data["text"],
                    category=None  # Категорию выберем позже
                )
                
                if stylization_result["success"]:
                    processed_posts.append({
                        **post_data,
                        "original_text": post_data["text"],
                        "text": stylization_result["stylized_text"],
                        "ai_processed": True,
                        "quality_score": stylization_result.get("quality_score", 7),
                        "changes_made": stylization_result.get("changes_made", False)
                    })
                else:
                    # В случае ошибки AI, сохраняем оригинал
                    processed_posts.append({
                        **post_data,
                        "ai_processed": False,
                        "ai_error": stylization_result.get("error")
                    })
                    failed_posts.append(post_data["link"])
                    
            except Exception as e:
                logger.error("Ошибка AI обработки поста {}: {}", i+1, str(e))
                processed_posts.append({
                    **post_data,
                    "ai_processed": False,
                    "ai_error": str(e)
                })
                failed_posts.append(post_data["link"])
        
        # Обновляем данные состояния
        await state.update_data(
            multiple_posts=processed_posts,
            ai_processed=True,
            ai_failed_count=len(failed_posts)
        )
        
        success_count = len([p for p in processed_posts if p.get("ai_processed", False)])
        
        result_text = f"✅ AI стилизация завершена!\n\n"
        result_text += f"📊 {bold('Результаты:')}\n"
        result_text += f"• Успешно обработано: {success_count}/{posts_count}\n"
        
        if failed_posts:
            result_text += f"• Ошибки обработки: {len(failed_posts)}\n"
            
        result_text += f"\n📋 {bold('Теперь выберите категорию для всех постов:')}"
        
    else:
        # Обработка одиночного поста
        post_text = data.get("post_text", "")
        
        await callback.message.edit_text(
            "🤖 Применяю AI стилизацию к посту...\n"
            "Это может занять 5-10 секунд."
        )
        
        try:
            ai_processor = get_ai_processor()
            stylization_result = await ai_processor.stylize_user_post(
                raw_text=post_text,
                category=None
            )
            
            if stylization_result["success"]:
                await state.update_data(
                    post_text=stylization_result["stylized_text"],
                    original_text=post_text,
                    ai_processed=True,
                    quality_score=stylization_result.get("quality_score", 7),
                    changes_made=stylization_result.get("changes_made", False)
                )
                
                result_text = f"✅ AI стилизация завершена!\n\n"
                
                if stylization_result.get("changes_made"):
                    result_text += f"🔄 {bold('Пост был изменен')}\n"
                    result_text += f"⭐ Качество: {stylization_result.get('quality_score', 7)}/10\n\n"
                else:
                    result_text += f"📝 {bold('Пост оставлен без изменений')}\n\n"
                    
                result_text += f"📋 {bold('Теперь выберите категорию:')}"
            else:
                await state.update_data(ai_processed=False, ai_error=stylization_result.get("error"))
                result_text = f"❌ Ошибка AI стилизации: {stylization_result.get('error', 'Неизвестная ошибка')}\n\n"
                result_text += f"📝 Пост будет сохранен в оригинальном виде.\n\n"
                result_text += f"📋 {bold('Выберите категорию:')}"
                
        except Exception as e:
            logger.error("Ошибка AI стилизации: {}", str(e))
            await state.update_data(ai_processed=False, ai_error=str(e))
            result_text = f"❌ Ошибка AI стилизации: {str(e)}\n\n"
            result_text += f"📝 Пост будет сохранен в оригинальном виде.\n\n"
            result_text += f"📋 {bold('Выберите категорию:')}"
    
    keyboard = get_category_selection_keyboard()
    
    await callback.message.edit_text(
        result_text,
        reply_markup=keyboard,
        parse_mode=get_parse_mode()
    )
    
    await state.set_state(UserPostStates.waiting_for_category)


@user_posts_router.callback_query(F.data == "ai_stylize_no", UserPostStates.waiting_for_ai_choice, OwnerFilter())  
async def ai_stylize_no_callback(callback: CallbackQuery, state: FSMContext):
    """Сохранить пост без AI стилизации"""
    await callback.answer()
    
    data = await state.get_data()
    is_multiple = data.get("is_multiple", False)
    
    # Помечаем что AI обработка не применялась
    await state.update_data(ai_processed=False)
    
    if is_multiple:
        posts_count = len(data.get("multiple_posts", []))
        result_text = f"📝 Пост{'ы' if posts_count > 1 else ''} сохранен{'ы' if posts_count > 1 else ''} в оригинальном виде\n\n"
    else:
        result_text = f"📝 Пост сохранен в оригинальном виде\n\n"
    
    result_text += f"📋 {bold('Выберите категорию:')}"
    
    keyboard = get_category_selection_keyboard()
    
    await callback.message.edit_text(
        result_text,
        reply_markup=keyboard,
        parse_mode=get_parse_mode()
    )
    
    await state.set_state(UserPostStates.waiting_for_category)


# Функция для регистрации роутера
def get_user_posts_router() -> Router:
    """Получить роутер для примеров постов"""
    return user_posts_router