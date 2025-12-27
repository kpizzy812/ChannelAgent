"""
Анализ изображений с помощью OpenAI Vision API
Обрабатывает и описывает изображения из постов для последующего анализа
"""

import base64
from typing import Optional, Dict, Any
from pathlib import Path

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.ai.client import get_openai_client
from src.utils.exceptions import AIProcessingError

# Настройка логгера модуля
logger = logger.bind(module="ai_vision")


class VisionAnalyzer:
    """
    Анализатор изображений с помощью OpenAI Vision API
    Предоставляет специализированные методы для анализа контента постов
    """
    
    def __init__(self):
        """Инициализация анализатора изображений"""
        self.openai_client = get_openai_client()
        
        logger.debug("Инициализирован анализатор изображений")
    
    async def analyze_post_image(self, image_data: bytes) -> Dict[str, Any]:
        """
        Анализ изображения из поста с фокусом на криpto/финансовый контент
        
        Args:
            image_data: Байты изображения
            
        Returns:
            Словарь с результатами анализа изображения
        """
        try:
            logger.info("Начинаем анализ изображения поста")
            
            # Получаем базовое описание изображения
            description = await self.openai_client.analyze_image(image_data)
            
            # Дополнительный анализ специфичный для постов
            detailed_analysis = await self._analyze_financial_content(image_data)
            
            result = {
                "description": description,
                "financial_elements": detailed_analysis.get("financial_elements", []),
                "key_objects": detailed_analysis.get("key_objects", []),
                "text_content": detailed_analysis.get("text_content", ""),
                "relevance_indicators": detailed_analysis.get("relevance_indicators", []),
                "chart_data": detailed_analysis.get("chart_data", None)
            }
            
            logger.info("Анализ изображения завершен успешно")
            return result
            
        except Exception as e:
            logger.error("Ошибка анализа изображения поста: {}", str(e))
            return {
                "description": "Ошибка анализа изображения",
                "financial_elements": [],
                "key_objects": [],
                "text_content": "",
                "relevance_indicators": [],
                "chart_data": None,
                "error": str(e)
            }
    
    async def _analyze_financial_content(self, image_data: bytes) -> Dict[str, Any]:
        """
        Специализированный анализ финансового/криптовалютного контента на изображении
        
        Args:
            image_data: Байты изображения
            
        Returns:
            Детальный анализ финансового контента
        """
        try:
            # Кодируем изображение в base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Создаем специализированный промпт для финансового анализа
            response = await self.openai_client.client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """Проанализируй это изображение с фокусом на финансовый/криптовалютный контент:

1. ФИНАНСОВЫЕ ЭЛЕМЕНТЫ: Найди все упоминания криптовалют, цен, графиков, показателей
2. КЛЮЧЕВЫЕ ОБЪЕКТЫ: Логотипы, символы, графики, диаграммы, скриншоты бирж
3. ТЕКСТ НА ИЗОБРАЖЕНИИ: Извлеки весь видимый текст (названия монет, цены, проценты)
4. ИНДИКАТОРЫ РЕЛЕВАНТНОСТИ: Элементы указывающие на криpto/DeFi/макроэкономику
5. ДАННЫЕ ГРАФИКОВ: Если есть графики - опиши тренды, временные рамки, значения

Ответь в JSON формате:
{
  "financial_elements": ["список найденных финансовых элементов"],
  "key_objects": ["список ключевых объектов"],
  "text_content": "весь извлеченный текст",
  "relevance_indicators": ["индикаторы релевантности"],
  "chart_data": {"trend": "восходящий/нисходящий/боковой", "timeframe": "период", "values": "ключевые значения"}
}"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.1,  # Низкая температура для точности
                max_tokens=1000
            )
            
            # Парсим JSON ответ
            response_text = response.choices[0].message.content.strip()
            
            # Пытаемся извлечь JSON из ответа
            try:
                import json
                # Ищем JSON в ответе
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                
                if json_start != -1 and json_end != -1:
                    json_str = response_text[json_start:json_end]
                    result = json.loads(json_str)
                    
                    logger.debug("Успешно распарсен JSON ответ Vision API")
                    return result
                else:
                    logger.warning("JSON не найден в ответе, используем текстовый анализ")
                    return self._parse_text_response(response_text)
                    
            except json.JSONDecodeError:
                logger.warning("Ошибка парсинга JSON, используем текстовый анализ")
                return self._parse_text_response(response_text)
            
        except Exception as e:
            logger.error("Ошибка детального анализа изображения: {}", str(e))
            return {
                "financial_elements": [],
                "key_objects": [],
                "text_content": "",
                "relevance_indicators": [],
                "chart_data": None
            }
    
    def _parse_text_response(self, response_text: str) -> Dict[str, Any]:
        """
        Парсинг текстового ответа если JSON парсинг не удался
        
        Args:
            response_text: Текст ответа от Vision API
            
        Returns:
            Распарсенные данные анализа
        """
        try:
            # Простой парсинг ключевых элементов из текста
            financial_elements = []
            key_objects = []
            text_content = ""
            relevance_indicators = []
            
            lines = response_text.split('\n')
            
            for line in lines:
                line = line.strip()
                if 'bitcoin' in line.lower() or 'btc' in line.lower():
                    financial_elements.append("Bitcoin")
                if 'ethereum' in line.lower() or 'eth' in line.lower():
                    financial_elements.append("Ethereum")
                if 'график' in line.lower() or 'chart' in line.lower():
                    key_objects.append("График/Диаграмма")
                if 'цена' in line.lower() or 'price' in line.lower():
                    relevance_indicators.append("Ценовые данные")
            
            # Извлекаем основной текст
            if len(response_text) > 100:
                text_content = response_text[:500] + "..." if len(response_text) > 500 else response_text
            
            return {
                "financial_elements": list(set(financial_elements)),
                "key_objects": list(set(key_objects)),
                "text_content": text_content,
                "relevance_indicators": list(set(relevance_indicators)),
                "chart_data": None
            }
            
        except Exception as e:
            logger.error("Ошибка парсинга текстового ответа: {}", str(e))
            return {
                "financial_elements": [],
                "key_objects": [],
                "text_content": response_text[:200] if response_text else "",
                "relevance_indicators": [],
                "chart_data": None
            }
    
    async def analyze_image_from_path(self, image_path: str) -> Dict[str, Any]:
        """
        Анализ изображения по пути к файлу
        
        Args:
            image_path: Путь к файлу изображения
            
        Returns:
            Результаты анализа изображения
        """
        try:
            path = Path(image_path)
            
            if not path.exists():
                logger.error("Файл изображения не найден: {}", image_path)
                return {"error": "Файл не найден"}
            
            # Читаем файл
            with open(path, 'rb') as f:
                image_data = f.read()
            
            return await self.analyze_post_image(image_data)
            
        except Exception as e:
            logger.error("Ошибка анализа изображения из файла {}: {}", image_path, str(e))
            return {"error": str(e)}
    
    async def extract_text_from_image(self, image_data: bytes) -> str:
        """
        Извлечение текста из изображения (OCR через Vision API)
        
        Args:
            image_data: Байты изображения
            
        Returns:
            Извлеченный текст
        """
        try:
            # Кодируем изображение в base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Создаем промпт для извлечения текста
            response = await self.openai_client.client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Извлеки ВЕСЬ видимый текст с этого изображения. Сохрани структуру и форматирование. Если текст на английском - оставь как есть, НЕ переводи."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                temperature=0,  # Максимальная точность для OCR
                max_tokens=1000
            )
            
            extracted_text = response.choices[0].message.content.strip()
            
            logger.info("Извлечен текст из изображения: {} символов", len(extracted_text))
            return extracted_text
            
        except Exception as e:
            logger.error("Ошибка извлечения текста из изображения: {}", str(e))
            return ""


# Глобальный экземпляр анализатора
_vision_analyzer: Optional[VisionAnalyzer] = None


def get_vision_analyzer() -> VisionAnalyzer:
    """Получить глобальный экземпляр анализатора изображений"""
    global _vision_analyzer
    
    if _vision_analyzer is None:
        _vision_analyzer = VisionAnalyzer()
    
    return _vision_analyzer