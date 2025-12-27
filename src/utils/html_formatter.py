"""
Утилиты для HTML форматирования сообщений Telegram
Поддержка основных возможностей форматирования
"""

from typing import Optional, Union, List
from aiogram import html
from aiogram.enums import ParseMode

# Модуль для всех HTML форматирований в проекте
DEFAULT_PARSE_MODE = ParseMode.HTML


def bold(text: str) -> str:
    """Жирный текст"""
    return f"<strong>{html.quote(text)}</strong>"


def italic(text: str) -> str:
    """Курсивный текст"""
    return f"<i>{html.quote(text)}</i>"


def underline(text: str) -> str:
    """Подчеркнутый текст"""
    return f"<u>{html.quote(text)}</u>"


def strikethrough(text: str) -> str:
    """Зачеркнутый текст"""
    return f"<s>{html.quote(text)}</s>"


def spoiler(text: str) -> str:
    """Спойлер (размытый текст)"""
    return f"<span class=\"tg-spoiler\">{html.quote(text)}</span>"


def code(text: str) -> str:
    """Моноширинный код"""
    return f"<code>{html.quote(text)}</code>"


def pre(text: str, language: Optional[str] = None) -> str:
    """Блок кода с подсветкой синтаксиса"""
    if language:
        return f"<pre><code class=\"language-{language}\">{html.quote(text)}</code></pre>"
    return f"<pre>{html.quote(text)}</pre>"


def link(text: str, url: str) -> str:
    """Гиперссылка"""
    return f"<a href=\"{html.quote(url)}\">{html.quote(text)}</a>"


def mention_user(text: str, user_id: int) -> str:
    """Упоминание пользователя по ID"""
    return f"<a href=\"tg://user?id={user_id}\">{html.quote(text)}</a>"




def format_user_info(user_name: str, user_id: int) -> str:
    """Форматирование информации о пользователе"""
    return f"👤 Пользователь: {bold(user_name)} (ID: {code(str(user_id))})"


def format_channel_info(channel_title: str, channel_username: Optional[str] = None) -> str:
    """Форматирование информации о канале"""
    info = f"📺 Канал: {bold(channel_title)}"
    if channel_username:
        info += f" (@{bold(channel_username)})"
    return info


def format_post_stats(likes: int = 0, views: int = 0, comments: int = 0) -> str:
    """Форматирование статистики поста"""
    stats = []
    if views > 0:
        stats.append(f"👁 {bold(str(views))} просмотров")
    if likes > 0:
        stats.append(f"👍 {bold(str(likes))} лайков")
    if comments > 0:
        stats.append(f"💬 {bold(str(comments))} комментариев")
    
    return " • ".join(stats) if stats else "📊 Нет статистики"


def format_success_message(title: str, details: Optional[str] = None) -> str:
    """Форматирование успешного сообщения"""
    message = f"✅ {bold(title)}"
    if details:
        message += f"\n\n{details}"
    return message


def format_error_message(title: str, details: Optional[str] = None) -> str:
    """Форматирование сообщения об ошибке"""
    message = f"❌ {bold(title)}"
    if details:
        message += f"\n\n{italic(details)}"
    return message


def format_warning_message(title: str, details: Optional[str] = None) -> str:
    """Форматирование предупреждения"""
    message = f"⚠️ {bold(title)}"
    if details:
        message += f"\n\n{details}"
    return message


def format_info_message(title: str, details: Optional[str] = None) -> str:
    """Форматирование информационного сообщения"""
    message = f"ℹ️ {bold(title)}"
    if details:
        message += f"\n\n{details}"
    return message


def format_list_items(items: List[str], bullet: str = "•") -> str:
    """Форматирование списка элементов"""
    return "\n".join(f"{bullet} {html.quote(item)}" for item in items)


def format_numbered_list(items: List[str]) -> str:
    """Форматирование нумерованного списка"""
    return "\n".join(f"{i+1}. {html.quote(item)}" for i, item in enumerate(items))


def format_key_value_pairs(pairs: dict) -> str:
    """Форматирование пар ключ-значение"""
    return "\n".join(f"{bold(str(key))}: {html.quote(str(value))}" for key, value in pairs.items())


def safe_html_message(text: str) -> str:
    """
    Безопасное экранирование HTML в сообщении
    Используется для пользовательского ввода
    """
    return html.quote(text)


def telegram_message_with_quote(original_text: str, quote_text: str, author: Optional[str] = None) -> str:
    """
    Создает сообщение с цитированием оригинального текста
    
    Args:
        original_text: Основной текст сообщения
        quote_text: Цитируемый текст
        author: Автор цитаты (опционально)
    
    Returns:
        Отформатированное сообщение с цитатой
    """
    message = f"{html.quote(original_text)}\n\n"
    
    if author:
        message += f"{italic(quote_text)}\n{italic(f'— {author}')}"
    else:
        message += italic(quote_text)
    
    return message


def format_ai_analysis_result(
    original_post: str,
    processed_post: str,
    relevance_score: int,
    sentiment: str
) -> str:
    """
    Форматирование результата AI анализа поста
    
    Args:
        original_post: Оригинальный текст поста
        processed_post: Обработанный AI текст
        relevance_score: Балл релевантности (1-10)
        sentiment: Тональность (позитивная/негативная/нейтральная)
    
    Returns:
        Отформатированное сообщение с результатами анализа
    """
    message = f"{bold('🤖 Результат AI анализа')}\n\n"
    
    # Релевантность
    relevance_emoji = "✅" if relevance_score >= 6 else "⚠️" if relevance_score >= 4 else "❌"
    message += f"{bold('📊 Релевантность:')} {relevance_emoji} {bold(str(relevance_score))}/10\n"
    
    # Тональность
    sentiment_emoji = {"позитивная": "😊", "негативная": "😔", "нейтральная": "😐"}.get(sentiment, "❓")
    message += f"{bold('🎭 Тональность:')} {sentiment_emoji} {bold(sentiment)}\n\n"
    
    # Оригинальный пост
    message += f"{bold('📝 Оригинальный пост:')}\n"
    message += f"{italic(original_post[:300] + '...' if len(original_post) > 300 else original_post)}\n\n"
    
    # Обработанный пост
    message += f"{bold('✨ Обработанный пост:')}\n"
    message += f"{italic(processed_post[:300] + '...' if len(processed_post) > 300 else processed_post)}"
    
    return message


def get_parse_mode() -> ParseMode:
    """Возвращает стандартный режим парсинга для проекта"""
    return DEFAULT_PARSE_MODE


async def safe_edit_message(callback, text: str, reply_markup=None, parse_mode=None):
    """
    Безопасное редактирование сообщения (текст или фото)
    
    Args:
        callback: Callback объект
        text: Новый текст
        reply_markup: Клавиатура
        parse_mode: Режим парсинга (по умолчанию HTML)
        
    Returns:
        Message: Объект сообщения после редактирования/отправки
    """
    from loguru import logger
    
    if parse_mode is None:
        parse_mode = get_parse_mode()
    
    try:
        if callback.message.photo or callback.message.video:
            # Если сообщение с медиа (фото или видео), отправляем новое
            await callback.message.delete()
            new_message = await callback.message.answer(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return new_message
        else:
            # Если текстовое сообщение, редактируем
            result = await callback.message.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            # edit_text возвращает Message или True, возвращаем сообщение
            return callback.message if result is True else result
    except Exception as edit_error:
        logger.debug("Не удалось отредактировать сообщение: {}, отправляем новое", str(edit_error))
        try:
            new_message = await callback.message.answer(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return new_message
        except Exception as fallback_error:
            logger.error("Критическая ошибка отправки сообщения: {}", str(fallback_error))
            return None


# Экспорт основных функций для удобства
__all__ = [
    'bold', 'italic', 'underline', 'strikethrough', 'spoiler',
    'code', 'pre', 'link', 'mention_user',
    'format_user_info', 'format_channel_info', 'format_post_stats',
    'format_success_message', 'format_error_message', 'format_warning_message', 'format_info_message',
    'format_list_items', 'format_numbered_list', 'format_key_value_pairs',
    'safe_html_message', 'telegram_message_with_quote', 'format_ai_analysis_result',
    'safe_edit_message', 'get_parse_mode', 'DEFAULT_PARSE_MODE'
]