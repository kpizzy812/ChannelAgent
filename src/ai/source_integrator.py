"""
Интеграция ссылки-источника в переработанный текст
Добавляет гиперссылку на первый глагол через re.sub()
GPT НЕ трогает текст - только код делает замену
"""

import re
from typing import Optional, Tuple

from loguru import logger

# Настройка логгера модуля
logger = logger.bind(module="source_integrator")


class SourceIntegrator:
    """Интегратор ссылки-источника в текст"""

    def integrate(
        self,
        text: str,
        source_url: Optional[str],
        first_verb: Optional[str]
    ) -> Tuple[str, bool]:
        """
        Вставить гиперссылку на первый глагол

        GPT НЕ трогает текст - только код делает re.sub()

        Args:
            text: Переработанный текст (Markdown)
            source_url: URL источника
            first_verb: Первый глагол (ТОЧНО как в тексте)

        Returns:
            Tuple[str, bool]: (текст_с_ссылкой_или_без, успех)
        """
        if not source_url or not first_verb:
            logger.debug("Нет source_url или first_verb, пропускаем интеграцию")
            return text, False

        try:
            # Проверяем что глагол реально есть в тексте
            # Используем \b для границ слова (если глагол кириллический, \b может не работать)
            # Поэтому используем более надёжный паттерн
            pattern = rf'(?<![а-яА-ЯёЁa-zA-Z])({re.escape(first_verb)})(?![а-яА-ЯёЁa-zA-Z])'

            if not re.search(pattern, text, re.IGNORECASE):
                logger.warning(
                    "Глагол '{}' не найден в тексте, пропускаем интеграцию",
                    first_verb
                )
                return text, False

            # Заменяем первое вхождение глагола на гиперссылку
            # Формат Markdown: [текст](url)
            result = re.sub(
                pattern,
                rf'[\1]({source_url})',
                text,
                count=1,
                flags=re.IGNORECASE
            )

            # Проверяем что замена произошла
            if result == text:
                logger.warning(
                    "Замена не произошла для глагола '{}', текст не изменился",
                    first_verb
                )
                return text, False

            # Удаляем дублирующую строку "Источник: URL" после успешной интеграции
            result = self._remove_source_line(result, source_url)

            logger.info(
                "Интегрирована ссылка: [{}]({}...)",
                first_verb,
                source_url[:40]
            )

            return result, True

        except Exception as e:
            logger.error("Ошибка интеграции источника: {}", str(e))
            return text, False

    def _remove_source_line(self, text: str, source_url: str) -> str:
        """
        Удалить строку "Источник: URL" после успешной интеграции ссылки

        Args:
            text: Текст с интегрированной ссылкой
            source_url: URL который был интегрирован

        Returns:
            Текст без дублирующей строки источника
        """
        try:
            # Паттерны для удаления строки с источником
            # Формат: различные варианты "Источник/Подробности/Читать: URL"
            # Может быть с ** форматированием, эмодзи или без
            patterns = [
                # 🔍 **Источник**: URL
                rf'\n*🔍\s*\**Источник\**:?\s*{re.escape(source_url)}\s*',
                # **Источник**: URL
                rf'\n*\**Источник\**:?\s*{re.escape(source_url)}\s*',
                # Источник: URL (без эмодзи)
                rf'\n*Источник:?\s*{re.escape(source_url)}\s*',
                # 🔗 Источник: URL
                rf'\n*🔗\s*\**Источник\**:?\s*{re.escape(source_url)}\s*',
                # 🔗 **Подробности**: URL
                rf'\n*🔗\s*\**Подробности\**:?\s*{re.escape(source_url)}\s*',
                # **Подробности**: URL
                rf'\n*\**Подробности\**:?\s*{re.escape(source_url)}\s*',
                # Подробности: URL
                rf'\n*Подробности:?\s*{re.escape(source_url)}\s*',
                # 📎 Ссылка: URL
                rf'\n*📎\s*\**Ссылка\**:?\s*{re.escape(source_url)}\s*',
                # Читать: URL, Детали: URL
                rf'\n*\**Читать\**:?\s*{re.escape(source_url)}\s*',
                rf'\n*\**Детали\**:?\s*{re.escape(source_url)}\s*',
                # Голый URL в конце поста (отдельной строкой)
                rf'\n+{re.escape(source_url)}\s*$',
            ]

            original_len = len(text)

            for pattern in patterns:
                text = re.sub(pattern, '', text, flags=re.IGNORECASE)

            # Удаляем разделители в начале и конце (артефакты от промпта)
            text = re.sub(r'^---\s*\n*', '', text)
            text = re.sub(r'\n*---\s*$', '', text)
            text = re.sub(r'^<<<\s*\n*', '', text)
            text = re.sub(r'\n*>>>\s*$', '', text)

            # Удаляем лишние переносы строк
            text = text.strip()

            if len(text) < original_len:
                logger.debug("Удалена дублирующая строка 'Источник: URL'")

            return text

        except Exception as e:
            logger.warning("Ошибка удаления строки источника: {}", str(e))
            return text


# Глобальный экземпляр
_source_integrator: Optional[SourceIntegrator] = None


def get_source_integrator() -> SourceIntegrator:
    """Получить экземпляр SourceIntegrator"""
    global _source_integrator
    if _source_integrator is None:
        _source_integrator = SourceIntegrator()
        logger.debug("Инициализирован SourceIntegrator")
    return _source_integrator
