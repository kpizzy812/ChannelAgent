"""
Анализатор тональности контента
Определяет эмоциональную окраску поста согласно ТЗ
"""

import re
from typing import Dict, List, Tuple
from dataclasses import dataclass
from collections import Counter

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Настройка логгера модуля
logger = logger.bind(module="sentiment_analyzer")


@dataclass  
class SentimentIndicator:
    """Индикатор тональности"""
    words: List[str]
    weight: float
    category: str


class SentimentAnalyzer:
    """
    Анализатор тональности контента
    Определяет позитивную/негативную/нейтральную тональность
    """
    
    def __init__(self):
        """Инициализация анализатора тональности"""
        
        # Позитивные индикаторы для крипто/макроэкономики
        self.positive_indicators = SentimentIndicator(
            words=[
                # Рост и успех
                "рост", "растет", "растут", "вырос", "выросли", "подъем", 
                "увеличение", "прибыль", "profit", "gain", "gains", "up",
                "bull", "бычий", "bullish", "rally", "ралли", "boom", "бум",
                
                # Позитивные новости
                "хорошо", "отлично", "прекрасно", "великолепно", "успех", 
                "успешно", "победа", "достижение", "breakthrough", "прорыв",
                "positive", "позитивно", "good", "great", "excellent",
                "amazing", "awesome", "fantastic", "wonderful",
                
                # Крипто позитив
                "moon", "луна", "ath", "новый максимум", "all time high",
                "adoption", "принятие", "institutional", "институциональный",
                "approval", "одобрение", "etf", "халвинг", "halving",
                "upgrade", "обновление", "partnership", "партнерство",
                
                # Макро позитив  
                "стабильность", "stability", "recovery", "восстановление",
                "employment", "занятость", "expansion", "расширение",
                "stimulus", "стимул", "support", "поддержка", "confidence",
                "уверенность", "strength", "сила", "resilience", "устойчивость",
                
                # Эмодзи и символы
                "🚀", "📈", "💚", "✅", "🎉", "🔥", "💎", "👍", "💰", "🤑",
                "📊", "+", "📶"
            ],
            weight=1.0,
            category="positive"
        )
        
        # Негативные индикаторы
        self.negative_indicators = SentimentIndicator(
            words=[
                # Падение и проблемы
                "падение", "падает", "падают", "упал", "упали", "снижение",
                "спад", "кризис", "крах", "crash", "dump", "дамп", "bear",
                "медвежий", "bearish", "down", "drop", "дроп",
                
                # Негативные эмоции
                "плохо", "ужасно", "катастрофа", "провал", "неудача", 
                "проблема", "проблемы", "bad", "terrible", "awful", "horrible",
                "disaster", "катастрофа", "crisis", "fear", "страх", "panic",
                "паника", "worry", "беспокойство", "concern", "опасение",
                
                # Крипто негатив
                "скам", "scam", "hack", "хак", "взлом", "rug pull", 
                "liquidation", "ликвидация", "rekt", "fud", "фуд",
                "ban", "запрет", "regulation", "регулирование",
                "sec", "lawsuit", "иск", "fine", "штраф",
                
                # Макро негатив
                "inflation", "инфляция", "recession", "рецессия", 
                "unemployment", "безработица", "debt", "долг", "deficit",
                "дефицит", "bubble", "пузырь", "collapse", "коллапс",
                "slowdown", "замедление", "contraction", "сжатие",
                
                # Эмодзи и символы
                "📉", "❌", "🔴", "💔", "😨", "😱", "⚠️", "🚨", "💸", "📊",
                "-", "↓", "⬇️"
            ],
            weight=1.0,
            category="negative"
        )
        
        # Нейтральные индикаторы (факты, аналитика)
        self.neutral_indicators = SentimentIndicator(
            words=[
                # Аналитические термины
                "анализ", "analysis", "данные", "data", "статистика", 
                "statistics", "отчет", "report", "исследование", "research",
                "прогноз", "forecast", "prediction", "предсказание",
                "тренд", "trend", "pattern", "паттерн", "correlation",
                "корреляция", "indicator", "индикатор",
                
                # Фактические термины
                "согласно", "according", "показывает", "shows", "reveals",
                "раскрывает", "indicates", "указывает", "suggests", 
                "предполагает", "confirms", "подтверждает", "demonstrates",
                "демонстрирует", "explains", "объясняет",
                
                # Технические термины
                "технический", "technical", "фундаментальный", "fundamental",
                "volume", "объем", "price", "цена", "level", "уровень",
                "support", "поддержка", "resistance", "сопротивление",
                "moving average", "скользящая средняя", "rsi", "macd",
                
                # Нейтральные эмодзи
                "📊", "📈", "📉", "🔍", "📝", "💭", "🤔", "📋", "📌"
            ],
            weight=0.8,
            category="neutral"
        )
        
        # Усилители тональности
        self.amplifiers = {
            "очень": 1.5, "very": 1.5, "крайне": 1.7, "extremely": 1.7,
            "невероятно": 1.8, "incredibly": 1.8, "исключительно": 1.6,
            "exceptionally": 1.6, "чрезвычайно": 1.7, "extraordinarily": 1.7,
            "супер": 1.4, "super": 1.4, "мега": 1.3, "mega": 1.3,
            "гипер": 1.6, "hyper": 1.6, "ультра": 1.5, "ultra": 1.5
        }
        
        # Ослабители тональности  
        self.diminishers = {
            "немного": 0.7, "slightly": 0.7, "чуть": 0.6, "somewhat": 0.8,
            "довольно": 0.9, "rather": 0.9, "относительно": 0.8, 
            "relatively": 0.8, "частично": 0.7, "partially": 0.7
        }
        
        logger.debug("Инициализирован анализатор тональности")
    
    def analyze_sentiment(
        self, 
        text: str, 
        image_description: str = None
    ) -> Dict[str, any]:
        """
        Анализ тональности контента
        
        Args:
            text: Текст поста
            image_description: Описание изображения (опционально)
            
        Returns:
            Результаты анализа тональности
        """
        try:
            # Подготавливаем текст
            combined_text = self._prepare_text(text, image_description)
            
            # Анализируем тональность
            sentiment_scores = self._calculate_sentiment_scores(combined_text)
            
            # Определяем итоговую тональность
            final_sentiment = self._determine_final_sentiment(sentiment_scores)
            
            # Находим ключевые слова-индикаторы
            found_indicators = self._extract_indicators(combined_text)
            
            result = {
                "sentiment": final_sentiment,
                "scores": sentiment_scores,
                "confidence": self._calculate_confidence(sentiment_scores),
                "found_indicators": found_indicators,
                "text_length": len(combined_text)
            }
            
            logger.debug("Анализ тональности: {}, счета={}, уверенность={:.1f}%", 
                        final_sentiment, sentiment_scores, result["confidence"])
            
            return result
            
        except Exception as e:
            logger.error("Ошибка анализа тональности: {}", str(e))
            return {
                "sentiment": "нейтральная",
                "scores": {"positive": 0, "negative": 0, "neutral": 0},
                "confidence": 0,
                "error": str(e)
            }
    
    def _prepare_text(self, text: str, image_description: str = None) -> str:
        """Подготовить текст для анализа"""
        combined_parts = []
        
        if text:
            combined_parts.append(text)
        
        if image_description:
            combined_parts.append(image_description)
        
        combined_text = " ".join(combined_parts).lower()
        
        # Сохраняем эмодзи и специальные символы для анализа тональности
        return combined_text
    
    def _calculate_sentiment_scores(self, text: str) -> Dict[str, float]:
        """Вычислить счета тональности"""
        
        scores = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
        
        # Разбиваем текст на слова
        words = text.split()
        
        # Анализируем каждое слово с контекстом
        for i, word in enumerate(words):
            # Проверяем позитивные индикаторы
            positive_match = self._check_word_match(word, self.positive_indicators.words)
            if positive_match:
                multiplier = self._get_context_multiplier(words, i)
                scores["positive"] += self.positive_indicators.weight * multiplier
                
            # Проверяем негативные индикаторы
            negative_match = self._check_word_match(word, self.negative_indicators.words)
            if negative_match:
                multiplier = self._get_context_multiplier(words, i)
                scores["negative"] += self.negative_indicators.weight * multiplier
                
            # Проверяем нейтральные индикаторы
            neutral_match = self._check_word_match(word, self.neutral_indicators.words)
            if neutral_match:
                multiplier = self._get_context_multiplier(words, i)
                scores["neutral"] += self.neutral_indicators.weight * multiplier
        
        return scores
    
    def _check_word_match(self, word: str, indicators: List[str]) -> bool:
        """Проверить совпадение слова с индикаторами"""
        word_clean = re.sub(r'[^\w]', '', word).lower()
        
        for indicator in indicators:
            # Точное совпадение
            if word_clean == indicator.lower():
                return True
            
            # Частичное совпадение для длинных слов
            if len(indicator) > 4 and indicator.lower() in word_clean:
                return True
                
            # Совпадение эмодзи
            if indicator in word:
                return True
        
        return False
    
    def _get_context_multiplier(self, words: List[str], position: int) -> float:
        """Получить множитель на основе контекста слова"""
        multiplier = 1.0
        
        # Проверяем усилители перед словом
        if position > 0:
            prev_word = re.sub(r'[^\w]', '', words[position - 1]).lower()
            if prev_word in self.amplifiers:
                multiplier *= self.amplifiers[prev_word]
            elif prev_word in self.diminishers:
                multiplier *= self.diminishers[prev_word]
        
        # Проверяем отрицание
        negation_words = ["не", "нет", "без", "not", "no", "without", "never"]
        for i in range(max(0, position - 2), position):
            if i < len(words):
                prev_word = re.sub(r'[^\w]', '', words[i]).lower()
                if prev_word in negation_words:
                    multiplier *= -0.8  # Инвертируем и ослабляем
                    break
        
        return multiplier
    
    def _determine_final_sentiment(self, scores: Dict[str, float]) -> str:
        """Определить итоговую тональность"""
        
        # Если все счета близки к нулю - нейтральная
        total_score = sum(abs(score) for score in scores.values())
        if total_score < 0.5:
            return "нейтральная"
        
        # Сравниваем позитивные и негативные счета
        positive_score = scores["positive"] 
        negative_score = abs(scores["negative"])  # Берем модуль
        neutral_score = scores["neutral"]
        
        # Определяем доминирующую тональность
        max_score = max(positive_score, negative_score, neutral_score)
        
        if max_score == positive_score and positive_score > negative_score * 1.2:
            return "позитивная"
        elif max_score == negative_score and negative_score > positive_score * 1.2:
            return "негативная"
        else:
            return "нейтральная"
    
    def _calculate_confidence(self, scores: Dict[str, float]) -> float:
        """Вычислить уверенность в определении тональности"""
        
        total_score = sum(abs(score) for score in scores.values())
        if total_score == 0:
            return 0.0
        
        # Находим максимальный и второй по величине счет
        sorted_scores = sorted([abs(score) for score in scores.values()], reverse=True)
        
        if len(sorted_scores) < 2:
            return 50.0
        
        max_score = sorted_scores[0]
        second_score = sorted_scores[1]
        
        # Уверенность зависит от разрыва между первым и вторым местом
        if second_score == 0:
            confidence = 95.0
        else:
            gap = (max_score - second_score) / max_score
            confidence = min(95.0, 50.0 + gap * 45.0)
        
        return round(confidence, 1)
    
    def _extract_indicators(self, text: str) -> Dict[str, List[str]]:
        """Извлечь найденные индикаторы тональности"""
        
        found = {"positive": [], "negative": [], "neutral": []}
        words = text.split()
        
        for word in words:
            # Позитивные
            if self._check_word_match(word, self.positive_indicators.words):
                clean_word = re.sub(r'[^\w\u263a-\U0001f645]', '', word)
                if clean_word and clean_word not in found["positive"]:
                    found["positive"].append(clean_word)
                    
            # Негативные  
            if self._check_word_match(word, self.negative_indicators.words):
                clean_word = re.sub(r'[^\w\u263a-\U0001f645]', '', word)
                if clean_word and clean_word not in found["negative"]:
                    found["negative"].append(clean_word)
                    
            # Нейтральные
            if self._check_word_match(word, self.neutral_indicators.words):
                clean_word = re.sub(r'[^\w\u263a-\U0001f645]', '', word)
                if clean_word and clean_word not in found["neutral"]:
                    found["neutral"].append(clean_word)
        
        return found
    
    def get_sentiment_stats(self) -> Dict[str, int]:
        """Получить статистику индикаторов тональности"""
        return {
            "positive_indicators": len(self.positive_indicators.words),
            "negative_indicators": len(self.negative_indicators.words), 
            "neutral_indicators": len(self.neutral_indicators.words),
            "amplifiers": len(self.amplifiers),
            "diminishers": len(self.diminishers)
        }