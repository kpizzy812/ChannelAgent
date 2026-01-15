"""
Модуль для добавления футера с полезными ссылками к постам
Каждый публикуемый пост должен иметь футер с ссылками на проекты
"""

from loguru import logger

# Настройка логгера модуля
logger = logger.bind(module="post_footer")


def add_footer_to_post(content: str, parse_mode: str = "Markdown") -> str:
    """
    Добавить футер с полезными ссылками к посту

    Формат футера:
    - Пустая строка (разделитель)
    - Текст с гиперссылками (поддержка Markdown и HTML)

    Args:
        content: Исходный текст поста
        parse_mode: Режим парсинга ("Markdown" или "HTML")

    Returns:
        Текст поста с добавленным футером
    """
    try:
        # Убираем лишние пробелы и переносы в конце
        content = content.rstrip()

        # Формируем футер в зависимости от parse_mode
        if parse_mode.upper() == "HTML":
            footer = (
                "\n\n"  # Пустая строка для разделения
                '<b>📢 <a href="https://t.me/web3_moves">Web3 Moves</a>\n\n'
                '📺 <a href="https://www.youtube.com/@web3moves">YouTube</a> | '
                '🤖 <a href="https://t.me/SyntraAI_bot?startapp=web3">Крипто ИИ</a> | '
                '💬 <a href="https://t.me/+stbL19SueW40Nzk6">Чат</a> | '
                '🧑‍🧒‍🧒 <a href="https://t.me/web3movesbot?startapp">Реф. программа</a></b>'
            )
        else:  # Markdown по умолчанию
            footer = (
                "\n\n"  # Пустая строка для разделения
                "**📢 [Web3 Moves](https://t.me/web3_moves)\n\n"
                "📺 [YouTube](https://www.youtube.com/@web3moves) | "
                "🤖 [Крипто ИИ](https://t.me/SyntraAI_bot?startapp=web3) | "
                "💬 [Чат](https://t.me/+stbL19SueW40Nzk6) | "
                "🧑‍🧒‍🧒 [Реф. программа](https://t.me/web3movesbot?startapp)**"
            )

        # Добавляем футер к контенту
        result = content + footer

        logger.debug("Футер добавлен к посту ({}), длина: {} -> {}",
                    parse_mode, len(content), len(result))

        return result

    except Exception as e:
        logger.error("Ошибка добавления футера к посту: {}", str(e))
        # В случае ошибки возвращаем оригинальный контент
        return content


def remove_footer_from_post(content: str) -> str:
    """
    Удалить футер из поста (если он есть)
    Полезно для редактирования постов

    Args:
        content: Текст поста с футером

    Returns:
        Текст поста без футера
    """
    try:
        # Ищем начало футера
        footer_start_markers = [
            "📢 Web3 Moves",
            "[Web3 Moves]",
            "Web3 Moves",
            # Старые маркеры для совместимости
            "[Сигналы и аналитика от ИИ]",
            "Сигналы и аналитика от ИИ"
        ]

        for marker in footer_start_markers:
            if marker in content:
                # Находим позицию начала футера
                footer_pos = content.find(marker)

                # Убираем пустые строки перед футером
                cleaned_content = content[:footer_pos].rstrip()

                logger.debug("Футер удален из поста, длина: {} -> {}",
                           len(content), len(cleaned_content))

                return cleaned_content

        # Если футер не найден, возвращаем как есть
        logger.debug("Футер не найден в посте")
        return content

    except Exception as e:
        logger.error("Ошибка удаления футера из поста: {}", str(e))
        return content


def has_footer(content: str) -> bool:
    """
    Проверить, есть ли уже футер в посте

    Args:
        content: Текст поста

    Returns:
        True если футер уже добавлен
    """
    try:
        footer_markers = [
            "📢 Web3 Moves",
            "t.me/web3_moves",
            "t.me/+stbL19SueW40Nzk6",
            "youtube.com/@web3moves",
            "t.me/web3movesbot?startapp",
            # Старые маркеры для совместимости
            "[Сигналы и аналитика от ИИ]",
            "t.me/SyntraAI_bot?startapp=web3",
        ]

        # Проверяем наличие хотя бы одного маркера
        return any(marker in content for marker in footer_markers)

    except Exception as e:
        logger.error("Ошибка проверки наличия футера: {}", str(e))
        return False


def ensure_footer(content: str) -> str:
    """
    Гарантировать наличие футера в посте
    Если футер уже есть - не добавляем повторно

    Args:
        content: Текст поста

    Returns:
        Текст поста с футером
    """
    try:
        if has_footer(content):
            logger.debug("Футер уже присутствует в посте")
            return content

        return add_footer_to_post(content)

    except Exception as e:
        logger.error("Ошибка обеспечения футера в посте: {}", str(e))
        return content


def validate_footer_links() -> bool:
    """
    Валидация корректности ссылок в футере
    Проверяет формат ссылок Telegram

    Returns:
        True если все ссылки валидны
    """
    try:
        # Ссылки, которые используются в футере
        links = [
            "https://t.me/web3_moves",
            "https://www.youtube.com/@web3moves",
            "https://t.me/SyntraAI_bot?startapp=web3",
            "https://t.me/+stbL19SueW40Nzk6",
            "https://t.me/web3movesbot?startapp",
        ]

        # Проверяем формат ссылок (Telegram или YouTube)
        for link in links:
            if not (link.startswith("https://t.me/") or link.startswith("https://www.youtube.com/")):
                logger.error("Некорректная ссылка в футере: {}", link)
                return False

        logger.debug("Все ссылки в футере валидны")
        return True

    except Exception as e:
        logger.error("Ошибка валидации ссылок футера: {}", str(e))
        return False


def convert_markdown_to_html(text: str) -> str:
    """
    Конвертировать Markdown разметку в HTML для Bot API

    Args:
        text: Текст с Markdown разметкой

    Returns:
        Текст с HTML разметкой
    """
    import re

    try:
        result = text

        # Конвертируем жирный текст: **text** -> <b>text</b>
        result = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', result)

        # Конвертируем курсив: *text* или _text_ -> <i>text</i>
        # Но не путаем с __underline__
        result = re.sub(r'(?<![_*])\*([^*]+)\*(?![_*])', r'<i>\1</i>', result)

        # Конвертируем подчёркивание: __text__ -> <u>text</u>
        result = re.sub(r'__([^_]+)__', r'<u>\1</u>', result)

        # Конвертируем ссылки: [text](url) -> <a href="url">text</a>
        # Но не трогаем emoji/ и spoiler
        result = re.sub(
            r'\[([^\]]+)\]\((?!emoji/|spoiler)(https?://[^\)]+)\)',
            r'<a href="\2">\1</a>',
            result
        )

        # Конвертируем код: `text` -> <code>text</code>
        result = re.sub(r'`([^`]+)`', r'<code>\1</code>', result)

        # Конвертируем спойлеры: ||text|| -> <tg-spoiler>text</tg-spoiler>
        result = re.sub(r'\|\|([^|]+)\|\|', r'<tg-spoiler>\1</tg-spoiler>', result)

        logger.debug("Конвертирован Markdown -> HTML: {} символов", len(result))
        return result

    except Exception as e:
        logger.error("Ошибка конвертации Markdown -> HTML: {}", str(e))
        return text
