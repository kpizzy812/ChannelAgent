"""
Модуль форматирования и стилизации контента
Обеспечивает правильное форматирование согласно Telegram разметке из ТЗ
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Настройка логгера модуля
logger = logger.bind(module="content_formatter")


@dataclass
class FormatPattern:
    """Паттерн форматирования Telegram"""
    markdown: str      # Markdown разметка
    telegram: str      # Telegram разметка
    description: str   # Описание
    priority: int      # Приоритет применения


class ContentFormatter:
    """
    Форматер контента для Telegram
    Обеспечивает правильное форматирование согласно ТЗ
    """
    
    def __init__(self):
        """Инициализация форматера контента"""
        
        # Паттерны форматирования согласно TECHNICAL_SPECIFICATION.md
        self.format_patterns = [
            FormatPattern("**bold**", "**жирный текст**", "Жирный текст", 1),
            FormatPattern("*italic*", "*курсив*", "Курсив", 2), 
            FormatPattern("__underline__", "__подчеркнутый__", "Подчеркнутый текст", 3),
            FormatPattern("||spoiler||", "||спойлер||", "Спойлер", 4),
            FormatPattern(">quote", ">цитата", "Цитата блоком", 5)
        ]
        
        # Эмодзи для разных типов контента
        self.content_emojis = {
            "crypto": ["🚀", "💎", "📈", "💰", "⚡", "🔥", "🌟", "💫", "🎯", "🔮"],
            "macro": ["📊", "📈", "💹", "🏛️", "💵", "📉", "⚖️", "🌍", "📋", "🔍"],
            "web3": ["🌐", "🔗", "🎮", "🖼️", "🎨", "🚀", "⚡", "💎", "🔮", "🌟"],
            "telegram": ["✈️", "💬", "📱", "🤖", "📢", "🔔", "📨", "📧", "💌", "📬"],
            "gamefi": ["🎮", "🏆", "⚔️", "🛡️", "👑", "💎", "🎯", "🎲", "🃏", "🎊"],
            "general": ["📌", "💡", "⭐", "🔥", "💪", "👀", "🎉", "✨", "🎭", "🎪"]
        }
        
        # Структурные элементы
        self.structural_elements = {
            "header": ["🔥", "⚡", "🚀", "💥", "🌟"],
            "bullet": ["•", "▪️", "🔸", "🔹", "◽"],
            "separator": ["━━━━━━━━━", "═══════", "▬▬▬▬▬▬▬", "───────"],
            "footer": ["#", "💭", "📝", "💬", "🔚"]
        }
        
        # Паттерны для разных типов постов
        self.post_templates = {
            "news": {
                "header": "🔥 {title}",
                "body": "{content}",
                "footer": "\n💭 {comment}"
            },
            "analysis": {
                "header": "📊 {title}",
                "body": "{content}",
                "footer": "\n🔍 {insight}"
            },
            "update": {
                "header": "⚡ {title}",
                "body": "{content}",
                "footer": "\n📈 {prediction}"
            }
        }
        
        logger.debug("Инициализирован форматер контента")
    
    def format_post(
        self,
        content: str,
        post_type: str = "general",
        style_preferences: Optional[Dict] = None
    ) -> str:
        """
        Форматировать пост согласно стилю
        
        Args:
            content: Исходный контент
            post_type: Тип поста (news, analysis, update, general)
            style_preferences: Предпочтения стиля
            
        Returns:
            Отформатированный контент
        """
        try:
            logger.debug("Форматирование поста типа: {}", post_type)
            
            # Очищаем контент
            cleaned_content = self._clean_content(content)
            
            # Применяем базовое форматирование
            formatted_content = self._apply_basic_formatting(cleaned_content)
            
            # Добавляем структурные элементы
            structured_content = self._add_structure(formatted_content, post_type)
            
            # Добавляем эмодзи
            final_content = self._add_emojis(structured_content, post_type)
            
            # Финальная очистка и валидация
            final_content = self._final_cleanup(final_content)
            
            logger.debug("Форматирование завершено: {} -> {} символов", 
                        len(content), len(final_content))
            
            return final_content
            
        except Exception as e:
            logger.error("Ошибка форматирования поста: {}", str(e))
            return content  # Возвращаем оригинал при ошибке
    
    def _clean_content(self, content: str) -> str:
        """Очистка контента от лишних элементов"""
        
        # Убираем множественные пробелы
        content = re.sub(r'\s+', ' ', content)
        
        # Убираем множественные переносы строк
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
        
        # Убираем лишние знаки препинания
        content = re.sub(r'[.]{3,}', '...', content)
        content = re.sub(r'[!]{2,}', '!', content)
        content = re.sub(r'[?]{2,}', '?', content)
        
        return content.strip()
    
    def _apply_basic_formatting(self, content: str) -> str:
        """Применить базовое форматирование"""
        
        formatted = content
        
        # Заменяем заголовки
        formatted = re.sub(
            r'^(.{1,50})\n',
            r'**\1**\n',
            formatted,
            flags=re.MULTILINE
        )
        
        # Форматируем числа и проценты
        formatted = re.sub(
            r'(\d+(?:\.\d+)?%)',
            r'**\1**',
            formatted
        )
        
        # Форматируем суммы денег
        formatted = re.sub(
            r'(\$[\d,]+(?:\.\d{2})?)',
            r'**\1**',
            formatted
        )
        
        # Форматируем криптовалюты
        crypto_pattern = r'\b(BTC|ETH|SOL|ADA|DOT|LINK|MATIC|AVAX|ATOM|FTM|NEAR|LUNA|UNI|AAVE|COMP|MKR|SNX|CRV|YFI|SUSHI)\b'
        formatted = re.sub(crypto_pattern, r'**\1**', formatted, flags=re.IGNORECASE)
        
        return formatted
    
    def _add_structure(self, content: str, post_type: str) -> str:
        """Добавить структурные элементы"""
        
        lines = content.split('\n')
        structured_lines = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                structured_lines.append('')
                continue
            
            # Первая строка - заголовок
            if i == 0 and len(line) < 100:
                if post_type == "news":
                    line = f"🔥 {line}"
                elif post_type == "analysis":
                    line = f"📊 {line}"
                elif post_type == "update":
                    line = f"⚡ {line}"
                else:
                    line = f"💡 {line}"
            
            # Добавляем маркеры для списков
            elif line.startswith(('- ', '• ', '* ')):
                line = f"▪️ {line[2:]}"
            
            # Добавляем отступы для цитат
            elif line.startswith(('"', '«', '„')):
                line = f">{line}"
            
            structured_lines.append(line)
        
        return '\n'.join(structured_lines)
    
    def _add_emojis(self, content: str, post_type: str) -> str:
        """Добавить соответствующие эмодзи"""
        
        # Получаем подходящие эмодзи для типа контента
        category_emojis = self._detect_content_category(content)
        
        content_with_emojis = content
        
        # Добавляем эмодзи к ключевым фразам
        key_phrases = {
            "рост": "📈", "падение": "📉", "новости": "📰", 
            "анализ": "📊", "прогноз": "🔮", "мнение": "💭",
            "важно": "❗", "внимание": "⚠️", "результат": "📋",
            "данные": "📊", "отчет": "📄", "исследование": "🔬"
        }
        
        for phrase, emoji in key_phrases.items():
            pattern = r'\b' + re.escape(phrase) + r'\b'
            if re.search(pattern, content_with_emojis, re.IGNORECASE):
                content_with_emojis = re.sub(
                    pattern, 
                    f"{emoji} {phrase}", 
                    content_with_emojis, 
                    count=1, 
                    flags=re.IGNORECASE
                )
        
        return content_with_emojis
    
    def _detect_content_category(self, content: str) -> str:
        """Определить категорию контента для выбора эмодзи"""
        
        content_lower = content.lower()
        
        # Ключевые слова для категорий
        if any(word in content_lower for word in ["bitcoin", "eth", "криптовалют", "блокчейн", "defi"]):
            return "crypto"
        elif any(word in content_lower for word in ["фрс", "инфляция", "экономика", "рынок", "доллар"]):
            return "macro"  
        elif any(word in content_lower for word in ["web3", "nft", "метавселенная", "dapp"]):
            return "web3"
        elif any(word in content_lower for word in ["telegram", "телеграм", "дуров", "ton"]):
            return "telegram"
        elif any(word in content_lower for word in ["игра", "game", "play to earn", "p2e"]):
            return "gamefi"
        else:
            return "general"
    
    def _final_cleanup(self, content: str) -> str:
        """Финальная очистка и валидация"""
        
        # Убираем лишние пробелы вокруг форматирования
        content = re.sub(r'\s+\*\*', '**', content)
        content = re.sub(r'\*\*\s+', '**', content)
        content = re.sub(r'\s+\*', '*', content)
        content = re.sub(r'\*\s+', '*', content)
        
        # Убираем множественные эмодзи
        content = re.sub(r'([\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF])\1+', r'\1', content)
        
        # Ограничиваем длину строк
        lines = content.split('\n')
        formatted_lines = []
        
        for line in lines:
            if len(line) > 200:  # Telegram лимит ~4000 символов на сообщение
                # Разбиваем длинную строку
                words = line.split()
                current_line = ""
                
                for word in words:
                    if len(current_line + word) < 180:
                        current_line += f" {word}" if current_line else word
                    else:
                        formatted_lines.append(current_line)
                        current_line = word
                
                if current_line:
                    formatted_lines.append(current_line)
            else:
                formatted_lines.append(line)
        
        final_content = '\n'.join(formatted_lines)
        
        # Финальная проверка длины
        if len(final_content) > 3800:  # Оставляем запас для Telegram
            final_content = final_content[:3800] + "..."
        
        return final_content.strip()
    
    def validate_telegram_formatting(self, content: str) -> Dict[str, any]:
        """Валидировать Telegram форматирование"""
        
        validation_result = {
            "is_valid": True,
            "issues": [],
            "warnings": [],
            "stats": {}
        }
        
        try:
            # Проверяем длину
            if len(content) > 4000:
                validation_result["issues"].append(f"Сообщение слишком длинное: {len(content)} символов")
                validation_result["is_valid"] = False
            
            # Проверяем парность форматирования
            bold_count = content.count("**")
            if bold_count % 2 != 0:
                validation_result["issues"].append("Непарные символы жирного текста **")
                validation_result["is_valid"] = False
            
            italic_count = content.count("*") - bold_count
            if italic_count % 2 != 0:
                validation_result["warnings"].append("Возможно непарные символы курсива *")
            
            underline_count = content.count("__")
            if underline_count % 2 != 0:
                validation_result["issues"].append("Непарные символы подчеркивания __")
                validation_result["is_valid"] = False
            
            spoiler_count = content.count("||")  
            if spoiler_count % 2 != 0:
                validation_result["issues"].append("Непарные символы спойлера ||")
                validation_result["is_valid"] = False
            
            # Статистика
            validation_result["stats"] = {
                "length": len(content),
                "lines": len(content.split('\n')),
                "bold_pairs": bold_count // 2,
                "italic_pairs": italic_count // 2,
                "underline_pairs": underline_count // 2,
                "spoiler_pairs": spoiler_count // 2,
                "emojis": len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF]', content))
            }
            
        except Exception as e:
            validation_result["issues"].append(f"Ошибка валидации: {str(e)}")
            validation_result["is_valid"] = False
        
        return validation_result
    
    def get_formatting_templates(self) -> Dict[str, str]:
        """Получить шаблоны форматирования"""
        return {
            "crypto_news": """🚀 **{title}**

{content}

📈 *Краткий анализ:* {analysis}

💎 #криптовалюты #новости""",
            
            "macro_analysis": """📊 **{title}**

{content}

🔍 *Ключевые выводы:*
▪️ {point1}
▪️ {point2}

🌍 #макроэкономика #анализ""",
            
            "web3_update": """🌐 **{title}**

{content}

⚡ *Что это означает:* {impact}

🚀 #web3 #блокчейн"""
        }