"""
Генерация заголовков для Daily Summary через GPT-4o-mini
Использует structured output (Pydantic) для гарантированного JSON
"""

import asyncio
from datetime import datetime
from typing import Optional, List

from loguru import logger
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from src.database.models.post import Post
from src.utils.config import get_config
from src.utils.post_footer import add_footer_to_post

# Настройка логгера модуля
logger = logger.bind(module="summary_generator")


class PostHeadlineResult(BaseModel):
    """Результат генерации заголовка для поста (structured output)"""
    headline: str = Field(
        description="Краткий заголовок 5-10 слов с субъектом и глаголом"
    )
    first_verb: str = Field(
        description="Первый глагол действия из заголовка"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Уверенность в качестве заголовка 0.0-1.0"
    )


# Системный промпт
SYSTEM_PROMPT = """Ты эксперт по созданию кратких заголовков для крипто-новостей."""

# Пользовательский промпт для генерации заголовка
HEADLINE_PROMPT_TEMPLATE = """
ТЕКСТ НОВОСТИ:
{text}

ЗАДАЧА: Создай информативный заголовок для этой новости

ТРЕБОВАНИЯ:
- Передаёт суть новости
- Содержит глагол действия
- МОЖНО добавить крипто-эмодзи если новость про конкретную монету:
  🪙 Bitcoin/BTC, ⚪️ Ethereum/ETH, 🧬 Solana/SOL, 🐬 TON, 🦄 Uniswap и т.д.
- НЕЛЬЗЯ использовать ✅ или 🟢 (мы добавим их сами как маркер пункта)

ПРИМЕРЫ:
✅ "🪙 MicroStrategy купила ещё 5000 BTC на $500M"
✅ "⚪️ Ethereum Foundation продал 1000 ETH для финансирования разработки"
✅ "Vitalik Buterin запустил новую L2 сеть для масштабирования"
✅ "SEC одобрила Bitcoin ETF заявки от BlackRock и Fidelity"

❌ "✅ Новость про биткоин" (НЕ добавляй ✅!)

ВЕРНИ:
1. headline - информативный заголовок (с крипто-эмодзи если релевантно)
2. first_verb - первый глагол из заголовка (для гиперссылки)
3. confidence - уверенность 0-1
"""


class SummaryGenerator:
    """Генератор заголовков для Daily Summary через GPT-4o-mini"""

    MODEL = "gpt-4o-mini"

    def __init__(self):
        """Инициализация генератора"""
        self.config = get_config()
        self.client = AsyncOpenAI(api_key=self.config.OPENAI_API_KEY)
        logger.debug("Инициализирован SummaryGenerator (модель: {})", self.MODEL)

    async def generate_headline(
        self,
        post: Post,
        max_retries: int = 2
    ) -> Optional[PostHeadlineResult]:
        """
        Сгенерировать заголовок для одного поста

        Args:
            post: Пост для генерации заголовка
            max_retries: Количество повторных попыток

        Returns:
            PostHeadlineResult с заголовком, глаголом и confidence
            None если генерация не удалась
        """
        # Используем обработанный текст или оригинальный
        text = post.processed_text or post.original_text or ""

        if not text.strip():
            logger.warning("Пост {} не имеет текста для генерации заголовка", post.id)
            return None

        for attempt in range(max_retries):
            try:
                # Формируем промпт
                user_prompt = HEADLINE_PROMPT_TEMPLATE.format(
                    text=text[:1500]  # Ограничиваем длину текста
                )

                # Вызываем GPT-4o-mini со structured output
                response = await self.client.beta.chat.completions.parse(
                    model=self.MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format=PostHeadlineResult,
                    temperature=0.3,
                    max_tokens=100
                )

                # Получаем распарсенный результат
                result = response.choices[0].message.parsed

                if result:
                    logger.info(
                        "Заголовок создан для поста {}: '{}', confidence={:.2f}",
                        post.id,
                        result.headline[:50],
                        result.confidence
                    )
                    return result
                else:
                    # Проверяем на отказ
                    refusal = response.choices[0].message.refusal
                    if refusal:
                        logger.warning("GPT отказался генерировать заголовок: {}", refusal)
                    return None

            except Exception as e:
                logger.error(
                    "Ошибка генерации заголовка для поста {} (попытка {}/{}): {}",
                    post.id, attempt + 1, max_retries, str(e)
                )
                if attempt == max_retries - 1:
                    logger.exception("Все попытки генерации заголовка исчерпаны")
                    return None

        return None

    async def create_summary_post(
        self,
        posts: List[Post],
        date: datetime
    ) -> Optional[str]:
        """
        Создать текст Daily Summary поста

        Args:
            posts: Список постов за день
            date: Дата для заголовка

        Returns:
            Текст поста с заголовками и гиперссылками
            None если не удалось создать summary
        """
        if not posts:
            logger.warning("Нет постов для создания summary")
            return None

        # Фильтруем посты без published_message_id
        posts_with_links = [p for p in posts if p.published_message_id]

        if not posts_with_links:
            logger.warning("Ни у одного поста нет published_message_id, невозможно создать гиперссылки")
            return None

        logger.info("Генерация заголовков для {} постов...", len(posts_with_links))

        # Генерируем заголовки параллельно
        tasks = [self.generate_headline(post) for post in posts_with_links]
        headlines = await asyncio.gather(*tasks)

        # Формируем список новостей
        news_items = []
        for post, headline_result in zip(posts_with_links, headlines):
            if not headline_result:
                # Если заголовок не сгенерирован, пропускаем пост
                logger.warning("Пропускаем пост {} - не удалось сгенерировать заголовок", post.id)
                continue

            # Получаем ссылку на опубликованный пост
            post_link = post.published_link

            if not post_link:
                logger.warning("Пропускаем пост {} - нет published_link", post.id)
                continue

            # Формируем строку с гиперссылкой на первый глагол
            headline = headline_result.headline
            first_verb = headline_result.first_verb

            # Заменяем первый глагол на гиперссылку в Markdown формате
            if first_verb in headline:
                headline_with_link = headline.replace(
                    first_verb,
                    f"[{first_verb}]({post_link})",
                    1  # Заменяем только первое вхождение
                )
            else:
                # Если глагол не найден, добавляем ссылку в начало
                logger.warning(
                    "Глагол '{}' не найден в заголовке '{}', добавляем ссылку в начало",
                    first_verb, headline
                )
                headline_with_link = f"[{headline}]({post_link})"

            news_items.append(headline_with_link)

        if not news_items:
            logger.warning("Не удалось создать ни одного заголовка с гиперссылкой")
            return None

        # Реверсируем порядок: новые посты первые
        news_items.reverse()

        # Формируем финальный текст
        date_formatted = date.strftime("%d.%m.%Y")

        summary_text = f"📰 **Новости за {date_formatted}**\n\n"

        # Список новостей с ✅ и пустыми строками между ними
        for item in news_items:
            summary_text += f"✅ {item}\n\n"

        # Убираем лишний перенос в конце перед футером
        summary_text = summary_text.rstrip("\n")

        # Добавляем футер через утилиту
        summary_text = add_footer_to_post(summary_text, parse_mode="Markdown")

        logger.info("Summary пост создан: {} новостей", len(news_items))

        return summary_text


# Глобальный экземпляр
_summary_generator: Optional[SummaryGenerator] = None


def get_summary_generator() -> SummaryGenerator:
    """Получить экземпляр SummaryGenerator"""
    global _summary_generator
    if _summary_generator is None:
        _summary_generator = SummaryGenerator()
    return _summary_generator
