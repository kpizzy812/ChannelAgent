"""
Главный процессор AI для анализа и обработки постов
Координирует работу всех AI компонентов согласно ТЗ
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.ai.client import get_openai_client
from src.ai.analyzer.relevance import RelevanceAnalyzer
from src.ai.analyzer.sentiment import SentimentAnalyzer
from src.ai.analyzer.vision import get_vision_analyzer
from src.ai.styler.formatter import ContentFormatter
from src.database.models.post import Post, PostSentiment, PostStatus
from src.database.connection import get_db_connection
from src.userbot.media import get_media_processor
from src.utils.config import get_config
from src.utils.exceptions import AIProcessingError
from src.utils.html_formatter import bold

# Настройка логгера модуля
logger = logger.bind(module="ai_processor")


class AIPostProcessor:
    """
    Главный процессор AI для анализа и обработки постов
    Объединяет анализ релевантности, тональности и рестайлинг контента
    """
    
    def __init__(self):
        """Инициализация AI процессора"""
        self.config = get_config()
        self.openai_client = get_openai_client()
        
        # Инициализируем компоненты анализа
        self.relevance_analyzer = RelevanceAnalyzer()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.vision_analyzer = get_vision_analyzer()
        self.content_formatter = ContentFormatter()
        
        # Статистика обработки
        self.processed_count = 0
        self.approved_count = 0
        self.rejected_count = 0
        
        logger.info("Инициализирован AI процессор")
    
    async def process_post(self, post: Post, media_processor=None) -> Dict[str, Any]:
        """
        Полная обработка поста через AI
        
        Args:
            post: Объект поста для обработки
            media_processor: Процессор медиа (опционально)
            
        Returns:
            Результаты обработки
        """
        try:
            self.processed_count += 1
            
            logger.info("Начинается AI обработка поста: {}", post.unique_id)
            
            # 🔍 ДЕБАГ ЛОГ: Полный исходный текст перед ИИ
            logger.debug("📝 ТЕКСТ ДО ИИ (пост={}): {}", post.unique_id, repr(post.original_text or ""))
            
            # Получаем описание изображения если есть фото
            image_description = None
            if post.has_media and media_processor:
                image_description = await self._get_image_description(post, media_processor)
            
            # Получаем примеры стиля пользователя
            user_examples = await self._get_user_style_examples()
            
            # Выполняем комплексный анализ через OpenAI
            analysis_result = await self.openai_client.analyze_relevance_and_sentiment(
                text=post.original_text or "",
                image_description=image_description,
                user_examples=user_examples
            )
            
            # Обрабатываем результаты
            processing_result = await self._process_analysis_result(
                post, analysis_result, image_description
            )
            
            # 🔍 ДЕБАГ ЛОГ: Полный результат ИИ обработки  
            logger.debug("📝 ТЕКСТ ПОСЛЕ ИИ (пост={}): {}", post.unique_id, repr(processing_result.get("processed_text", "")))
            logger.debug("🤖 RAW AI RESPONSE (пост={}): {}", post.unique_id, repr(analysis_result.get("raw_response", "")))
            
            # Обновляем пост в БД
            await self._update_post_with_ai_results(post, processing_result)
            
            # Обновляем статистику
            if processing_result.get("is_relevant", False):
                self.approved_count += 1
            else:
                self.rejected_count += 1
            
            logger.info("AI обработка завершена для поста {}: релевантность={}, тональность={}", 
                       post.unique_id, processing_result.get("relevance_score"), 
                       processing_result.get("sentiment"))
            
            return processing_result
            
        except Exception as e:
            logger.error("Ошибка AI обработки поста {}: {}", post.unique_id, str(e))
            
            # Записываем ошибку в пост
            try:
                post.mark_as_failed(f"AI processing error: {str(e)}")
                await self._update_post_status(post)
            except Exception as update_error:
                logger.error("Не удалось обновить статус поста: {}", str(update_error))
            
            raise AIProcessingError(f"Post processing failed: {str(e)}")
    
    async def _get_image_description(self, post: Post, media_processor) -> Optional[str]:
        """Получить расширенное описание изображения через Vision API"""
        try:
            # Извлекаем путь к фото из информации о медиа
            media_info = await self._extract_media_info_from_post(post)
            
            if not media_info or not media_info.get("photo_path"):
                logger.debug("Нет информации о фото для поста {}", post.id)
                return None
            
            # Получаем байты фото для AI анализа
            photo_bytes = await media_processor.get_photo_for_ai(media_info["photo_path"])
            
            if not photo_bytes:
                logger.warning("Не удалось получить байты фото для поста {}", post.id)
                return None
            
            # Используем расширенный анализатор изображений
            vision_result = await self.vision_analyzer.analyze_post_image(photo_bytes)
            
            # Формируем комплексное описание изображения
            description_parts = []
            
            # Базовое описание
            if vision_result.get("description"):
                description_parts.append(f"ОПИСАНИЕ: {vision_result['description']}")
            
            # Финансовые элементы
            if vision_result.get("financial_elements"):
                financial_str = ", ".join(vision_result["financial_elements"])
                description_parts.append(f"ФИНАНСОВЫЕ ЭЛЕМЕНТЫ: {financial_str}")
            
            # Извлеченный текст
            if vision_result.get("text_content"):
                description_parts.append(f"ТЕКСТ НА ИЗОБРАЖЕНИИ: {vision_result['text_content']}")
            
            # Данные графиков
            if vision_result.get("chart_data"):
                chart_data = vision_result["chart_data"]
                if isinstance(chart_data, dict) and chart_data.get("trend"):
                    description_parts.append(f"ГРАФИК: {chart_data['trend']} тренд")
            
            # Индикаторы релевантности
            if vision_result.get("relevance_indicators"):
                indicators_str = ", ".join(vision_result["relevance_indicators"])
                description_parts.append(f"РЕЛЕВАНТНОСТЬ: {indicators_str}")
            
            final_description = "\n".join(description_parts) if description_parts else vision_result.get("description", "")
            
            logger.info("Получен расширенный анализ изображения для поста {}: финансовые элементы={}, релевантность={}", 
                       post.id, len(vision_result.get("financial_elements", [])), 
                       len(vision_result.get("relevance_indicators", [])))
            
            return final_description
            
        except Exception as e:
            logger.error("Ошибка получения описания изображения: {}", str(e))
            return None
    
    async def _extract_media_info_from_post(self, post: Post) -> Optional[Dict[str, Any]]:
        """Извлечь информацию о медиа из поста"""
        try:
            if not post.ai_analysis:
                return None
            
            # Ищем строку MEDIA_INFO в ai_analysis
            lines = post.ai_analysis.split('\n')
            for line in lines:
                if line.startswith('MEDIA_INFO:'):
                    import json
                    media_json = line.replace('MEDIA_INFO:', '').strip()
                    return json.loads(media_json)
            
            return None
            
        except Exception as e:
            logger.error("Ошибка извлечения медиа информации: {}", str(e))
            return None
    
    async def _get_source_channel_info(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о канале-источнике для удаления брендинга"""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    "SELECT title, username FROM channels WHERE channel_id = ?",
                    (channel_id,)
                )
                row = await cursor.fetchone()

                if row:
                    return {
                        "title": row[0],
                        "username": row[1]
                    }
                return None

        except Exception as e:
            logger.error("Ошибка получения информации о канале {}: {}", channel_id, str(e))
            return None

    async def _get_user_style_examples(self, limit: int = 3) -> List[str]:
        """Получить примеры постов пользователя для анализа стиля"""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT text FROM user_posts 
                       WHERE is_active = 1 
                       ORDER BY quality_score DESC, usage_count ASC 
                       LIMIT ?""",
                    (limit,)
                )
                rows = await cursor.fetchall()
                
                examples = [row[0] for row in rows if row[0]]
                
                logger.debug("Получено {} примеров стиля пользователя", len(examples))
                return examples
                
        except Exception as e:
            logger.error("Ошибка получения примеров стиля: {}", str(e))
            return []
    
    async def _process_analysis_result(
        self, 
        post: Post, 
        analysis_result: Dict[str, Any],
        image_description: Optional[str]
    ) -> Dict[str, Any]:
        """Обработка результатов анализа"""
        
        relevance_score = analysis_result.get("relevance_score", 1)
        sentiment_text = analysis_result.get("sentiment", "нейтральная")
        processed_text = analysis_result.get("processed_text", "")
        
        # Конвертируем тональность в enum
        sentiment_enum = PostSentiment.NEUTRAL
        if sentiment_text == "позитивная":
            sentiment_enum = PostSentiment.POSITIVE
        elif sentiment_text == "негативная":
            sentiment_enum = PostSentiment.NEGATIVE
        
        # Проверяем порог релевантности
        is_relevant = relevance_score >= self.config.RELEVANCE_THRESHOLD
        
        # Создаем детальный анализ
        analysis_details = {
            "relevance_score": relevance_score,
            "sentiment": sentiment_text,
            "is_relevant": is_relevant,
            "processed_text": processed_text,
            "image_description": image_description,
            "analysis_date": datetime.now().isoformat(),
            "model_used": self.config.OPENAI_MODEL,
            "threshold_used": self.config.RELEVANCE_THRESHOLD,
            "raw_ai_response": analysis_result.get("raw_response", "")
        }
        
        return {
            "relevance_score": relevance_score,
            "sentiment": sentiment_enum,
            "processed_text": processed_text,
            "is_relevant": is_relevant,
            "analysis_details": analysis_details
        }
    
    async def _update_post_with_ai_results(self, post: Post, processing_result: Dict[str, Any]):
        """Обновить пост результатами AI обработки"""
        
        # Обновляем объект поста
        post.set_ai_analysis(
            processed_text=processing_result["processed_text"],
            relevance_score=processing_result["relevance_score"], 
            sentiment=processing_result["sentiment"],
            analysis_details=str(processing_result["analysis_details"])
        )
        
        # Определяем статус поста на основе релевантности
        if processing_result["is_relevant"]:
            # Релевантный пост переходит на модерацию (остается PENDING)
            logger.info("Пост {} прошел порог релевантности и отправлен на модерацию", post.unique_id)
            
            # Отправляем уведомление владельцу о новом посте для модерации
            await self._notify_owner_about_new_post_for_moderation(post)
        else:
            # Нерелевантный пост автоматически отклоняется
            post.reject("Автоматически отклонен: релевантность ниже порога")
            logger.info("Пост {} автоматически отклонен: релевантность {}", 
                       post.unique_id, processing_result["relevance_score"])
        
        # Сохраняем изменения в БД
        await self._update_post_in_database(post)
    
    async def _update_post_in_database(self, post: Post):
        """Обновить пост в базе данных"""
        try:
            async with get_db_connection() as conn:
                await conn.execute(
                    """UPDATE posts SET 
                       processed_text = ?,
                       relevance_score = ?,
                       sentiment = ?,
                       status = ?,
                       ai_analysis = ?,
                       moderation_notes = ?,
                       updated_at = datetime('now')
                       WHERE id = ?""",
                    (
                        post.processed_text,
                        post.relevance_score,
                        post.sentiment.value if post.sentiment else None,
                        post.status.value,
                        post.ai_analysis,
                        post.moderation_notes,
                        post.id
                    )
                )
                await conn.commit()
                
                logger.debug("Пост {} обновлен в БД", post.id)
                
        except Exception as e:
            logger.error("Ошибка обновления поста в БД: {}", str(e))
            raise
    
    async def _update_post_status(self, post: Post):
        """Обновить только статус поста в БД"""
        try:
            async with get_db_connection() as conn:
                await conn.execute(
                    """UPDATE posts SET 
                       status = ?,
                       error_message = ?,
                       updated_at = datetime('now')
                       WHERE id = ?""",
                    (post.status.value, post.error_message, post.id)
                )
                await conn.commit()
                
        except Exception as e:
            logger.error("Ошибка обновления статуса поста: {}", str(e))
    
    async def stylize_user_post(self, raw_text: str, category: Optional[str] = None) -> Dict[str, Any]:
        """
        Обработать пост пользователя для добавления в примеры стиля
        Уникализирует и стилизует посты с других каналов
        
        Args:
            raw_text: Исходный текст поста
            category: Категория поста (опционально)
            
        Returns:
            Результат обработки с стилизованным текстом
        """
        try:
            logger.info("Начинается стилизация пользовательского поста: {} символов", len(raw_text))
            
            # Получаем примеры стиля пользователя
            user_examples = await self._get_user_style_examples(limit=5)
            
            # Если нет примеров, возвращаем оригинальный текст
            if not user_examples:
                logger.warning("Нет примеров стиля пользователя, возвращаем оригинальный текст")
                return {
                    "success": True,
                    "stylized_text": raw_text,
                    "original_text": raw_text,
                    "changes_made": False,
                    "message": "Нет примеров стиля для обработки"
                }
            
            # Обрабатываем через OpenAI для стилизации
            stylized_result = await self.openai_client.stylize_user_content(
                original_text=raw_text,
                user_examples=user_examples,
                category=category
            )
            
            stylized_text = stylized_result.get("stylized_text", raw_text)
            
            # Проверяем качество стилизации
            quality_check = await self._assess_stylization_quality(
                original_text=raw_text,
                stylized_text=stylized_text,
                user_examples=user_examples
            )
            
            result = {
                "success": True,
                "stylized_text": stylized_text,
                "original_text": raw_text,
                "changes_made": raw_text != stylized_text,
                "quality_score": quality_check.get("score", 7),
                "style_similarity": quality_check.get("similarity", "средняя"),
                "improvements": quality_check.get("improvements", []),
                "category_detected": stylized_result.get("category", category),
                "processing_time": stylized_result.get("processing_time", 0)
            }
            
            logger.info("Стилизация завершена: изменения={}, качество={}/10", 
                       result["changes_made"], result["quality_score"])
            
            return result
            
        except Exception as e:
            logger.error("Ошибка стилизации пользовательского поста: {}", str(e))
            return {
                "success": False,
                "error": str(e),
                "stylized_text": raw_text,  # Возвращаем оригинал при ошибке
                "original_text": raw_text,
                "changes_made": False
            }
    
    async def two_stage_restyle_post(self, post: Post) -> Dict[str, Any]:
        """
        Двухэтапный рестайлинг поста:
        1. Максимальная уникализация контента
        2. Красивое HTML форматирование

        Args:
            post: Объект поста для обработки

        Returns:
            Результат двухэтапной обработки
        """
        try:
            logger.info("🔄 Начинается двухэтапный рестайлинг поста: {}", post.unique_id)

            # Получаем информацию о канале-источнике для удаления брендинга
            source_channel_title = None
            source_channel_username = None
            try:
                channel_info = await self._get_source_channel_info(post.channel_id)
                if channel_info:
                    source_channel_title = channel_info.get("title")
                    source_channel_username = channel_info.get("username")
                    logger.debug("Канал-источник: {} (@{})", source_channel_title, source_channel_username)
            except Exception as e:
                logger.warning("Не удалось получить информацию о канале-источнике: {}", str(e))

            # Получаем примеры стиля пользователя (больше примеров = лучше понимание стиля)
            user_examples = await self._get_user_style_examples(limit=5)

            # ЭТАП 1: Адаптация под стиль пользователя
            logger.info("🎯 ЭТАП 1: Адаптация контента под стиль пользователя")
            uniqualization_result = await self.openai_client.uniqualize_content(
                original_text=post.original_text or "",
                user_examples=user_examples,
                source_channel_title=source_channel_title,
                source_channel_username=source_channel_username
            )
            
            if not uniqualization_result.get("success"):
                logger.error("Ошибка этапа 1 (уникализация): {}", uniqualization_result.get("error"))
                return {
                    "success": False,
                    "error": f"Этап 1 failed: {uniqualization_result.get('error')}",
                    "stage_1_result": uniqualization_result,
                    "final_text": post.original_text
                }
            
            uniqualized_text = uniqualization_result.get("uniqualized_text", "")
            logger.info("✅ ЭТАП 1 завершен: {} -> {} символов", 
                       len(post.original_text or ""), len(uniqualized_text))
            
            # 🔍 DEBUG: Полный результат этапа 1
            logger.info("📊 КООРДИНАТОР - РЕЗУЛЬТАТ ЭТАПА 1:\n{}", repr(uniqualized_text))
            
            # ЭТАП 2: Markdown форматирование (для Telethon)
            logger.info("🎨 ЭТАП 2: Markdown форматирование")
            formatting_result = await self.openai_client.format_with_markdown(
                text=uniqualized_text
            )
            
            if not formatting_result.get("success"):
                logger.error("Ошибка этапа 2 (форматирование): {}", formatting_result.get("error"))
                return {
                    "success": False,
                    "error": f"Этап 2 failed: {formatting_result.get('error')}",
                    "stage_1_result": uniqualization_result,
                    "stage_2_result": formatting_result,
                    "final_text": uniqualized_text  # Хотя бы уникализированный текст
                }
            
            formatted_text = formatting_result.get("formatted_text", "")
            logger.info("✅ ЭТАП 2 завершен: {} символов Markdown", len(formatted_text))

            # ЭТАП 3-4: Анализ источника и интеграция ссылки
            final_text = formatted_text
            source_url = None
            first_verb = None
            source_integrated = False
            source_confidence = 0.0

            if post.extracted_links:
                try:
                    import json
                    from src.ai.source_analyzer import get_source_analyzer
                    from src.ai.source_integrator import get_source_integrator

                    # ЭТАП 3: Анализ источника через GPT-4o-mini
                    logger.info("🔗 ЭТАП 3: Анализ источника (GPT-4o-mini)")
                    links = json.loads(post.extracted_links)
                    analyzer = get_source_analyzer()
                    analysis = await analyzer.analyze(formatted_text, links)

                    source_url = analysis.source_url
                    first_verb = analysis.first_verb
                    source_confidence = analysis.confidence

                    logger.debug(
                        "GPT анализ: source={}, verb={}, confidence={:.2f}",
                        source_url[:40] if source_url else None,
                        first_verb,
                        source_confidence
                    )

                    # Проверяем порог уверенности
                    if source_confidence < 0.7:
                        logger.info(
                            "Низкая уверенность ({:.2f}), пропускаем интеграцию ссылки",
                            source_confidence
                        )
                    elif source_url and first_verb:
                        # ЭТАП 4: Интеграция ссылки (re.sub, без LLM)
                        logger.info("🔗 ЭТАП 4: Интеграция ссылки на глагол '{}'", first_verb)
                        integrator = get_source_integrator()

                        final_text, source_integrated = integrator.integrate(
                            formatted_text, source_url, first_verb
                        )

                        if source_integrated:
                            logger.info(
                                "✅ Ссылка интегрирована: [{}]({}...)",
                                first_verb, source_url[:40]
                            )
                        else:
                            logger.warning(
                                "⚠️ Интеграция не сработала: глагол '{}' не найден",
                                first_verb
                            )

                except Exception as e:
                    logger.error("Ошибка анализа/интеграции источника: {}", str(e))
                    # Продолжаем с formatted_text без ссылки

            # 🔍 DEBUG: Финальный результат координатора
            logger.info("🏆 КООРДИНАТОР - ФИНАЛЬНЫЙ РЕЗУЛЬТАТ:\n{}", repr(final_text))
            logger.info("🏆 КООРДИНАТОР - ФИНАЛЬНЫЙ ВИЗУАЛЬНО:\n{}", final_text)

            # ✅ Финальный Markdown готов для Telethon
            processing_stages = 4 if source_integrated else (3 if post.extracted_links else 2)
            logger.info("✅ Обработка завершена, {} этапов, Markdown готов", processing_stages)

            # Создаем финальный результат
            result = {
                "success": True,
                "final_text": final_text,
                "original_text": post.original_text,
                "uniqualized_text": uniqualized_text,
                "formatted_text": formatted_text,
                "stage_1_result": uniqualization_result,
                "stage_2_result": formatting_result,
                "source_url": source_url,
                "first_verb": first_verb,
                "source_confidence": source_confidence,
                "source_integrated": source_integrated,
                "changes_made": post.original_text != final_text,
                "processing_stages": processing_stages,
                "final_length": len(final_text),
                "original_length": len(post.original_text or "")
            }

            logger.info(
                "🎉 Рестайлинг завершен для поста {}: {} -> {} символов, источник: {}",
                post.unique_id, len(post.original_text or ""), len(final_text),
                "интегрирован" if source_integrated else "нет"
            )
            
            return result
            
        except Exception as e:
            logger.error("Критическая ошибка двухэтапного рестайлинга поста {}: {}", 
                        post.unique_id, str(e))
            return {
                "success": False,
                "error": f"Critical error: {str(e)}",
                "final_text": post.original_text or "Ошибка обработки",
                "original_text": post.original_text,
                "changes_made": False
            }
    
    async def _assess_stylization_quality(
        self, 
        original_text: str, 
        stylized_text: str, 
        user_examples: List[str]
    ) -> Dict[str, Any]:
        """Оценить качество стилизации"""
        try:
            # Простая эвристическая оценка качества
            quality_factors = []
            
            # Проверяем сохранение ключевой информации
            if len(stylized_text) >= len(original_text) * 0.8:
                quality_factors.append(("информация_сохранена", 2))
            
            # Проверяем добавление форматирования
            formatting_chars = ['**', '*', '__', '`', '>', '||']
            if any(char in stylized_text for char in formatting_chars):
                quality_factors.append(("форматирование_добавлено", 2))
                
            # Проверяем добавление эмодзи
            if any(ord(char) > 127 for char in stylized_text):
                quality_factors.append(("эмодзи_добавлены", 1))
            
            # Проверяем структурирование
            if '\n\n' in stylized_text or stylized_text.count('\n') > original_text.count('\n'):
                quality_factors.append(("структура_улучшена", 1))
            
            # Базовый балл
            base_score = 5
            bonus_score = sum(score for _, score in quality_factors)
            final_score = min(10, base_score + bonus_score)
            
            improvements = [factor for factor, _ in quality_factors]
            
            # Определяем схожесть стиля (упрощенно)
            if final_score >= 8:
                similarity = "высокая"
            elif final_score >= 6:
                similarity = "средняя"
            else:
                similarity = "низкая"
            
            return {
                "score": final_score,
                "similarity": similarity,
                "improvements": improvements,
                "details": dict(quality_factors)
            }
            
        except Exception as e:
            logger.error("Ошибка оценки качества стилизации: {}", str(e))
            return {"score": 5, "similarity": "неизвестна", "improvements": []}
    
    def _validate_html_for_telegram(self, html_text: str) -> Dict[str, Any]:
        """Валидация HTML для Telegram парсинга"""
        try:
            issues = []
            warnings = []
            
            # Проверка базовых тегов
            opening_tags = {}
            closing_tags = {}
            
            # Ищем все теги
            import re
            
            # Находим все открывающие теги
            opening_pattern = r'<(\w+)(?:\s[^>]*)?>'
            for match in re.finditer(opening_pattern, html_text):
                tag = match.group(1).lower()
                if tag not in opening_tags:
                    opening_tags[tag] = 0
                opening_tags[tag] += 1
            
            # Находим все закрывающие теги
            closing_pattern = r'</(\w+)>'
            for match in re.finditer(closing_pattern, html_text):
                tag = match.group(1).lower()
                if tag not in closing_tags:
                    closing_tags[tag] = 0
                closing_tags[tag] += 1
            
            # Проверяем соответствие
            for tag, count in opening_tags.items():
                closing_count = closing_tags.get(tag, 0)
                if count != closing_count:
                    issues.append(f"Несоответствие тегов <{tag}>: открыто {count}, закрыто {closing_count}")
            
            # Проверка вложенных тегов (ЗАПРЕЩЕНО согласно промпту)
            nested_pattern = r'<(\w+)[^>]*>.*?<(\w+)[^>]*>.*?</\2>.*?</\1>'
            if re.search(nested_pattern, html_text, re.DOTALL):
                warnings.append("Обнаружены вложенные теги")
            
            # Проверка эмодзи между тегами
            emoji_between_pattern = r'</\w+>\s*[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+\s*<\w+'
            if re.search(emoji_between_pattern, html_text):
                warnings.append("Эмодзи между тегами (может вызывать проблемы парсинга)")
            
            
            # Проверка невидимых символов
            invisible_chars = ['\u200b', '\u200c', '\u200d', '\ufeff']
            for char in invisible_chars:
                if char in html_text:
                    issues.append(f"Обнаружен невидимый символ: {repr(char)}")
            
            return {
                "status": "error" if issues else ("warning" if warnings else "ok"),
                "issues": issues,
                "warnings": warnings,
                "tag_counts": opening_tags,
                "length": len(html_text)
            }
            
        except Exception as e:
            logger.error("Ошибка валидации HTML: {}", str(e))
            return {"status": "error", "error": str(e)}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику работы AI процессора"""
        return {
            "processed_count": self.processed_count,
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "approval_rate": self.approved_count / max(self.processed_count, 1) * 100,
            "model_used": self.config.OPENAI_MODEL,
            "relevance_threshold": self.config.RELEVANCE_THRESHOLD
        }
    
    async def batch_process_pending_posts(self, limit: int = 10) -> Dict[str, Any]:
        """
        Пакетная обработка ожидающих постов
        
        Args:
            limit: Максимальное количество постов для обработки
            
        Returns:
            Статистика обработки
        """
        try:
            # Получаем посты для обработки
            pending_posts = await self._get_pending_posts(limit)
            
            if not pending_posts:
                logger.debug("Нет постов для AI обработки")
                return {"processed": 0, "approved": 0, "rejected": 0}
            
            logger.info("Начинается пакетная обработка {} постов", len(pending_posts))
            
            processed = 0
            approved = 0
            rejected = 0
            
            for post in pending_posts:
                try:
                    result = await self.process_post(post)
                    processed += 1
                    
                    if result.get("is_relevant"):
                        approved += 1
                    else:
                        rejected += 1
                        
                    # Небольшая задержка между обработкой постов
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error("Ошибка обработки поста {}: {}", post.unique_id, str(e))
                    rejected += 1
            
            logger.info("Пакетная обработка завершена: {} обработано, {} одобрено, {} отклонено", 
                       processed, approved, rejected)
            
            return {
                "processed": processed,
                "approved": approved, 
                "rejected": rejected
            }
            
        except Exception as e:
            logger.error("Ошибка пакетной обработки: {}", str(e))
            return {"processed": 0, "approved": 0, "rejected": 0, "error": str(e)}
    
    async def _get_pending_posts(self, limit: int) -> List[Post]:
        """Получить посты ожидающие AI обработки"""
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(
                    """SELECT * FROM posts 
                       WHERE status = 'pending' AND relevance_score IS NULL
                       ORDER BY created_at ASC 
                       LIMIT ?""",
                    (limit,)
                )
                rows = await cursor.fetchall()
                
                # Преобразуем в объекты Post
                posts = []
                for row in rows:
                    # Создаем Post из данных БД (упрощенный вариант)
                    post = Post(
                        id=row[0],
                        channel_id=row[1],
                        message_id=row[2], 
                        original_text=row[3],
                        processed_text=row[4],
                        photo_file_id=row[5],
                        relevance_score=row[6],
                        sentiment=PostSentiment(row[7]) if row[7] else None,
                        status=PostStatus(row[8]) if row[8] else PostStatus.PENDING,
                        source_link=row[9],
                        # Добавить остальные поля по необходимости
                    )
                    posts.append(post)
                
                return posts
                
        except Exception as e:
            logger.error("Ошибка получения pending постов: {}", str(e))
            return []
    
    async def _notify_owner_about_new_post_for_moderation(self, post) -> None:
        """Отправить уведомление владельцу о новом посте для модерации"""
        try:
            # Импортируем зависимости здесь чтобы избежать циклических импортов
            from src.bot.main import get_bot_instance
            from src.bot.keyboards.inline import get_post_moderation_keyboard  
            from src.bot.handlers.moderation import format_post_caption_for_moderation
            
            config = self.config
            
            # Получаем экземпляр бота
            bot = get_bot_instance()
            
            # Получаем клавиатуру модерации с дополнительной кнопкой повторного анализа
            keyboard = get_post_moderation_keyboard(post.id)
            
            # Добавляем кнопку повторного AI анализа в конец клавиатуры
            from aiogram.types import InlineKeyboardButton
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text="🔄 Повторный AI анализ",
                    callback_data=f"reanalyze_post_{post.id}"
                )
            ])
            
            # Если есть фото, отправляем с фото
            if post.photo_file_id:
                try:
                    # Создаем caption для фото
                    caption = format_post_caption_for_moderation(post)
                    
                    # Telegram ограничение: 1024 символа для caption
                    if len(caption) > 1024:
                        # НЕ обрезаем HTML (ломает теги), показываем краткую информацию
                        caption = f"""📝 {bold(f'Пост #{post.id} готов к модерации')}
📺 Канал: {_get_channel_display_name(post.channel_id) if hasattr(post, 'channel_id') else 'неизвестно'}

📄 Полный текст доступен по кнопке ниже ⬇️"""
                        
                        # Добавляем кнопку "Показать пост" в начало клавиатуры
                        from aiogram.types import InlineKeyboardButton
                        show_post_button = InlineKeyboardButton(
                            text="📄 Показать полный пост",
                            callback_data=f"show_full_post_{post.id}"
                        )
                        keyboard.inline_keyboard.insert(0, [show_post_button])
                        
                        logger.info("Caption слишком длинный ({} символов), добавлена кнопка 'Показать пост'", len(caption))
                    
                    await bot.send_photo(
                        chat_id=config.OWNER_ID,
                        photo=post.photo_file_id,
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    
                    logger.info("🖼️ Уведомление о новом посте с фото {} отправлено владельцу", post.id)
                    
                except Exception as photo_error:
                    logger.warning("Ошибка отправки фото для поста {}: {}, отправляем как текст", 
                                 post.id, str(photo_error))
                    # Если не удалось отправить фото, отправляем как обычное сообщение
                    await self._send_text_moderation_notification(bot, config, post, keyboard)
            else:
                # Пост без фото - отправляем текстовое уведомление
                await self._send_text_moderation_notification(bot, config, post, keyboard)
                
        except Exception as e:
            logger.error("Ошибка отправки уведомления о модерации поста {}: {}", post.id, str(e))
            # Не критичная ошибка, не прерываем основной процесс
    
    async def _send_text_moderation_notification(self, bot, config, post, keyboard):
        """Отправить текстовое уведомление о модерации с умным обрезанием"""
        try:
            from src.bot.handlers.moderation import format_post_for_moderation
            
            # Форматируем полное сообщение для модерации
            moderation_text = format_post_for_moderation(post)
            
            # Добавляем заголовок уведомления
            notification_text = f"""🆕 <b>Новый пост для модерации!</b>

{moderation_text}"""
            
            # Проверяем длину сообщения (лимит Telegram: 4096 символов для текста)
            if len(notification_text) > 4048:
                logger.info("Текстовое уведомление слишком длинное ({} символов), показываю краткую версию", 
                           len(notification_text))
                
                # НЕ обрезаем HTML (ломает теги), показываем краткую информацию
                truncated_text = f"""📄 {bold('Уведомление о посте слишком длинное')}

📊 Размер уведомления: {len(notification_text)} символов
⬇️ Используйте кнопку 'Показать пост' для просмотра полного текста"""
                
                # Добавляем кнопку "Показать полный пост" в начало клавиатуры
                from aiogram.types import InlineKeyboardButton
                show_post_button = InlineKeyboardButton(
                    text="📄 Показать полный пост",
                    callback_data=f"show_full_post_{post.id}"
                )
                keyboard.inline_keyboard.insert(0, [show_post_button])
                
                notification_text = truncated_text
            
            # Отправляем с HTML форматированием без fallback обработки
            await bot.send_message(
                chat_id=config.OWNER_ID,
                text=notification_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            logger.info("📝 Текстовое уведомление о новом посте {} отправлено владельцу", post.id)
            
        except Exception as e:
            logger.error("Критическая ошибка отправки уведомления: {}", str(e))


# Глобальный экземпляр процессора
_ai_processor: Optional[AIPostProcessor] = None


def get_ai_processor() -> AIPostProcessor:
    """Получить глобальный экземпляр AI процессора"""
    global _ai_processor
    
    if _ai_processor is None:
        _ai_processor = AIPostProcessor()
    
    return _ai_processor