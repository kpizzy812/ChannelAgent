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

            logger.info(
                "Интегрирована ссылка: [{}]({}...)",
                first_verb,
                source_url[:40]
            )

            return result, True

        except Exception as e:
            logger.error("Ошибка интеграции источника: {}", str(e))
            return text, False


# Глобальный экземпляр
_source_integrator: Optional[SourceIntegrator] = None


def get_source_integrator() -> SourceIntegrator:
    """Получить экземпляр SourceIntegrator"""
    global _source_integrator
    if _source_integrator is None:
        _source_integrator = SourceIntegrator()
        logger.debug("Инициализирован SourceIntegrator")
    return _source_integrator
