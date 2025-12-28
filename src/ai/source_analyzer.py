"""
Анализ ссылок через GPT-4o-mini для определения источника новости
Использует structured output (Pydantic) для гарантированного JSON
"""

from typing import Optional, List, Dict, Any

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from src.utils.config import get_config

# Настройка логгера модуля
logger = logger.bind(module="source_analyzer")


class SourceAnalysisResult(BaseModel):
    """Результат анализа источника от GPT-4o-mini (structured output)"""
    source_url: Optional[str] = Field(
        default=None,
        description="URL источника новости (x.com, lookonchain, arkham) или null"
    )
    first_verb: Optional[str] = Field(
        default=None,
        description="Первый глагол-действие ТОЧНО как в тексте или null"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Уверенность в результате 0.0-1.0"
    )


# Системный промпт
SYSTEM_PROMPT = """Ты анализатор крипто-новостей. Определяешь источник и первый глагол."""

# Пользовательский промпт
USER_PROMPT_TEMPLATE = """
ТЕКСТ:
{text}

ССЫЛКИ:
{links_formatted}

ЗАДАЧИ:

1. SOURCE_URL — ссылка-первоисточник новости:
   - ✅ x.com, twitter.com, lookonchain, arkham, whale_alert
   - ✅ Новостные: coindesk, cointelegraph, theblock, decrypt
   - ❌ НЕ источник: t.me/, агрегаторы, сокращалки (bit.ly, t.co без контекста)
   - Если сомневаешься → null

2. FIRST_VERB — первый глагол ДЕЙСТВИЯ в тексте:
   - ✅ объявил, запустил, выпустил, раскрыл, сообщил, добавил, перевёл
   - ❌ НЕ подходят: был, является, стал, будет (вспомогательные)
   - Верни глагол ТОЧНО как в тексте (с учётом регистра!)
   - Если нет подходящего → null

3. CONFIDENCE — уверенность в ответе:
   - 0.9-1.0: Точно нашёл источник + глагол в тексте
   - 0.7-0.9: Высокая уверенность
   - <0.7: Сомневаюсь
"""


class SourceAnalyzer:
    """Анализатор ссылок через GPT-4o-mini со structured output"""

    MODEL = "gpt-4o-mini"

    def __init__(self):
        """Инициализация анализатора"""
        self.config = get_config()
        self.client = AsyncOpenAI(api_key=self.config.OPENAI_API_KEY)
        logger.debug("Инициализирован SourceAnalyzer (модель: {})", self.MODEL)

    async def analyze(
        self,
        text: str,
        links: List[Dict[str, Any]],
        max_retries: int = 2
    ) -> SourceAnalysisResult:
        """
        Анализировать текст и ссылки для определения источника

        Args:
            text: Текст поста (переработанный)
            links: Список ссылок [{"url": ..., "display_text": ...}]
            max_retries: Количество повторных попыток

        Returns:
            SourceAnalysisResult с source_url, first_verb, confidence
        """
        if not links:
            logger.debug("Нет ссылок для анализа")
            return SourceAnalysisResult()

        for attempt in range(max_retries):
            try:
                # Форматируем ссылки для промпта
                links_formatted = self._format_links(links)

                # Формируем промпт
                user_prompt = USER_PROMPT_TEMPLATE.format(
                    text=text[:2000],  # Ограничиваем длину текста
                    links_formatted=links_formatted
                )

                # Вызываем GPT-4o-mini со structured output
                response = await self.client.beta.chat.completions.parse(
                    model=self.MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format=SourceAnalysisResult,
                    temperature=0.1,
                    max_tokens=200
                )

                # Получаем распарсенный результат
                result = response.choices[0].message.parsed

                if result:
                    logger.info(
                        "Анализ завершён: source={}, verb={}, confidence={:.2f}",
                        result.source_url[:40] if result.source_url else None,
                        result.first_verb,
                        result.confidence
                    )
                    return result
                else:
                    # Проверяем на отказ
                    refusal = response.choices[0].message.refusal
                    if refusal:
                        logger.warning("GPT отказался анализировать: {}", refusal)
                    return SourceAnalysisResult()

            except Exception as e:
                logger.error(
                    "Ошибка анализа ссылок (попытка {}/{}): {}",
                    attempt + 1, max_retries, str(e)
                )
                if attempt == max_retries - 1:
                    logger.exception("Все попытки анализа исчерпаны")
                    return SourceAnalysisResult()

        return SourceAnalysisResult()

    def _format_links(self, links: List[Dict[str, Any]]) -> str:
        """Форматировать ссылки для промпта"""
        formatted = []
        for i, link in enumerate(links, 1):
            url = link.get("url", "")
            display_text = link.get("display_text")

            if display_text:
                formatted.append(f"{i}. URL: {url} (текст: {display_text})")
            else:
                formatted.append(f"{i}. URL: {url}")

        return "\n".join(formatted)


# Глобальный экземпляр
_source_analyzer: Optional[SourceAnalyzer] = None


def get_source_analyzer() -> SourceAnalyzer:
    """Получить экземпляр SourceAnalyzer"""
    global _source_analyzer
    if _source_analyzer is None:
        _source_analyzer = SourceAnalyzer()
    return _source_analyzer
