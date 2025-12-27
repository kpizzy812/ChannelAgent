"""
Анализатор релевантности контента
Определяет соответствие поста тематике проекта согласно ТЗ
"""

import re
from typing import Dict, List, Set
from dataclasses import dataclass

# Логирование (ОБЯЗАТЕЛЬНО loguru)  
from loguru import logger

# Настройка логгера модуля
logger = logger.bind(module="relevance_analyzer")


@dataclass
class RelevanceCategory:
    """Категория релевантности с ключевыми словами"""
    name: str
    keywords: List[str]
    weight: float
    
    
class RelevanceAnalyzer:
    """
    Анализатор релевантности контента
    Определяет соответствие постов тематике крипто/макроэкономики
    """
    
    def __init__(self):
        """Инициализация анализатора релевантности"""
        
        # Категории релевантности согласно ТЗ (ИСПРАВЛЕНЫ ВЕСЫ!)
        self.categories = {
            "crypto": RelevanceCategory(
                name="Криптовалюты",
                keywords=[
                    "bitcoin", "биткоин", "btc", "ethereum", "эфириум", "eth",
                    "altcoin", "альткоин", "defi", "дефи", "dao", "дао",
                    "nft", "нфт", "blockchain", "блокчейн", "криптовалют",
                    "криптобирж", "binance", "coinbase", "solana", "cardano",
                    "polygon", "avalanche", "chainlink", "polkadot", "luna",
                    "ustc", "usdt", "usdc", "stable", "стейбл", "майнинг",
                    "mining", "асик", "asic", "proof of work", "proof of stake",
                    "pos", "pow", "валидатор", "validator", "стейкинг", "staking",
                    "yield", "йилд", "liquidity", "ликвидност", "dex", "деск",
                    "swap", "своп", "bridge", "мост", "layer", "слой", "scaling",
                    "масштабирован"
                ],
                weight=4.0  # Увеличен с 3.0
            ),
            
            "macro": RelevanceCategory(
                name="Макроэкономика",
                keywords=[
                    "фрс", "fed", "федеральная резервная система", "центробанк",
                    "цб", "центральный банк", "инфляция", "inflation", "ставка",
                    "rate", "процентная ставка", "gdp", "ввп", "валовой внутренний",
                    "рецессия", "recession", "кризис", "crisis", "экономика",
                    "economy", "рынок", "market", "доллар", "dollar", "евро", 
                    "euro", "рубль", "rubl", "курс", "exchange", "девальвация",
                    "дефляция", "deflation", "стагфляция", "stagflation",
                    "безработица", "unemployment", "cpi", "ипц", "индекс цен",
                    "ppi", "производственные цены", "отчет", "report", "данные",
                    "data", "статистика", "статист", "powell", "пауэлл",
                    "йеллен", "yellen", "лагард", "lagarde", "набиуллина",
                    "силуанов", "qe", "количественное смягчение"
                ],
                weight=4.0  # Увеличен с 2.5
            ),
            
            "web3": RelevanceCategory(
                name="Web3",
                keywords=[
                    "web3", "веб3", "метавселенная", "metaverse", "nft", "нфт",
                    "opensea", "опенси", "collectible", "коллекционный",
                    "avatar", "аватар", "virtual", "виртуальн", "augmented",
                    "дополненная реальность", "vr", "ar", "decentralized",
                    "децентрализован", "dapp", "дапп", "приложение", "application",
                    "smart contract", "умный контракт", "смарт контракт",
                    "governance", "управление", "токен", "token", "coin", "коин",
                    "монета", "airdrop", "аирдроп", "дроп", "drop", "snapshot",
                    "снепшот", "whitelist", "вайтлист", "ido", "ico", "ieo",
                    "launchpad", "лончпад", "тестнет", "testnet", "mainnet",
                    "мейннет"
                ],
                weight=3.5  # Увеличен с 2.0
            ),
            
            "telegram": RelevanceCategory(
                name="Telegram",
                keywords=[
                    "telegram", "телеграм", "телеграмм", "tg", "тг", "дуров",
                    "durov", "pavel", "павел", "ton", "тон", "тонкоин", 
                    "toncoin", "gram", "грам", "открытая сеть", "open network",
                    "канал", "channel", "бот", "bot", "стикер", "sticker",
                    "эмодзи", "emoji", "premium", "премиум", "stars", "звезды",
                    "stories", "истории", "voice", "голосов", "video", "видео",
                    "call", "звонок", "group", "группа", "супергруппа", 
                    "supergroup", "чат", "chat", "админ", "admin", "модератор",
                    "moderator"
                ],
                weight=3.0  # Увеличен с 1.5
            ),
            
            "gamefi": RelevanceCategory(
                name="GameFi",
                keywords=[
                    "gamefi", "геймфай", "play to earn", "p2e", "играй и зарабатывай",
                    "axie", "аксии", "sandbox", "сендбокс", "decentraland", 
                    "децентраленд", "enjin", "энжин", "gala", "гала", "immutable",
                    "иммутабл", "wax", "вакс", "matic", "матик", "gaming", 
                    "гейминг", "игровой", "game", "игра", "nft game", "нфт игра",
                    "guild", "гильдия", "clan", "клан", "tournament", "турнир",
                    "esports", "киберспорт", "championship", "чемпионат",
                    "arena", "арена", "battle", "битва", "quest", "квест",
                    "mission", "миссия", "reward", "награда", "prize", "приз",
                    "item", "предмет", "weapon", "оружие", "character", "персонаж",
                    "level", "уровень", "upgrade", "улучшение"
                ],
                weight=3.0  # Увеличен с 1.8
            )
        }
        
        # Стоп-слова для фильтрации
        self.stop_words = {
            "и", "в", "на", "с", "по", "для", "от", "к", "за", "о", "об",
            "but", "and", "or", "the", "a", "an", "is", "are", "was", "were",
            "this", "that", "these", "those", "not", "no", "yes"
        }
        
        logger.debug("Инициализирован анализатор релевантности")
    
    def analyze_relevance(
        self, 
        text: str, 
        image_description: str = None
    ) -> Dict[str, any]:
        """
        Анализировать релевантность контента
        
        Args:
            text: Текст поста
            image_description: Описание изображения (опционально)
            
        Returns:
            Результаты анализа релевантности
        """
        try:
            # Подготавливаем текст для анализа
            combined_text = self._prepare_text(text, image_description)
            
            # Анализируем по категориям
            category_scores = self._analyze_categories(combined_text)
            
            # Вычисляем общий счет релевантности
            total_score = self._calculate_total_score(category_scores)
            
            # Определяем ключевые слова
            found_keywords = self._extract_found_keywords(combined_text)
            
            result = {
                "relevance_score": total_score,
                "category_scores": category_scores,
                "found_keywords": found_keywords,
                "analysis_method": "keyword_based",
                "text_length": len(combined_text)
            }
            
            logger.debug("Анализ релевантности: общий счет={}, категории={}", 
                        total_score, category_scores)
            
            return result
            
        except Exception as e:
            logger.error("Ошибка анализа релевантности: {}", str(e))
            return {
                "relevance_score": 1,
                "category_scores": {},
                "found_keywords": [],
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
        
        # Убираем специальные символы, оставляем буквы, цифры и пробелы
        combined_text = re.sub(r'[^\w\s]', ' ', combined_text)
        
        # Убираем множественные пробелы
        combined_text = re.sub(r'\s+', ' ', combined_text).strip()
        
        return combined_text
    
    def _analyze_categories(self, text: str) -> Dict[str, float]:
        """Анализ по категориям"""
        category_scores = {}
        
        for category_id, category in self.categories.items():
            score = self._calculate_category_score(text, category)
            category_scores[category.name] = score
            
        return category_scores
    
    def _calculate_category_score(self, text: str, category: RelevanceCategory) -> float:
        """Вычислить счет для конкретной категории"""
        
        # Разбиваем текст на слова
        words = set(text.split()) - self.stop_words
        
        # Находим совпадения с ключевыми словами
        matches = 0
        matched_keywords = []
        
        for keyword in category.keywords:
            keyword = keyword.lower()
            
            # Точное совпадение слова
            if keyword in words:
                matches += 1
                matched_keywords.append(keyword)
                continue
            
            # Частичное совпадение (подстрока)
            for word in words:
                if len(keyword) > 3 and keyword in word:
                    matches += 0.5  # Частичное совпадение дает половину очка
                    matched_keywords.append(f"{keyword}*")
                    break
        
        # Вычисляем счет с учетом веса категории
        base_score = min(matches * category.weight, 10.0)  # Максимум 10 баллов
        
        logger.debug("Категория {}: {} совпадений, счет={:.1f}, ключевые слова={}", 
                    category.name, matches, base_score, matched_keywords[:5])
        
        return base_score
    
    def _calculate_total_score(self, category_scores: Dict[str, float]) -> int:
        """Вычислить общий счет релевантности"""
        
        # Берем максимальный счет среди категорий
        max_score = max(category_scores.values()) if category_scores else 0
        
        # Добавляем бонус если несколько категорий имеют высокий счет
        high_score_categories = sum(1 for score in category_scores.values() if score >= 2.0)
        if high_score_categories >= 2:
            max_score += 1.0  # Бонус за межкатегориальную релевантность
        
        # Нормализуем до шкалы 1-10
        final_score = max(1, min(10, int(round(max_score))))
        
        return final_score
    
    def _extract_found_keywords(self, text: str) -> List[str]:
        """Извлечь найденные ключевые слова"""
        words = set(text.split()) - self.stop_words
        found_keywords = []
        
        for category in self.categories.values():
            for keyword in category.keywords:
                keyword_lower = keyword.lower()
                
                # Точное совпадение
                if keyword_lower in words:
                    found_keywords.append(keyword)
                    continue
                
                # Частичное совпадение
                for word in words:
                    if len(keyword_lower) > 3 and keyword_lower in word:
                        found_keywords.append(f"{keyword}*")
                        break
        
        return list(set(found_keywords))  # Убираем дубликаты
    
    def get_category_info(self) -> Dict[str, Dict[str, any]]:
        """Получить информацию о категориях анализа"""
        return {
            category_id: {
                "name": category.name,
                "keywords_count": len(category.keywords),
                "weight": category.weight,
                "sample_keywords": category.keywords[:10]
            }
            for category_id, category in self.categories.items()
        }
    
    def add_custom_keywords(self, category_name: str, keywords: List[str]) -> bool:
        """
        Добавить пользовательские ключевые слова
        
        Args:
            category_name: Название категории  
            keywords: Список ключевых слов
            
        Returns:
            True если добавление успешно
        """
        try:
            category_found = False
            for category in self.categories.values():
                if category.name.lower() == category_name.lower():
                    # Добавляем новые ключевые слова, избегая дубликатов
                    new_keywords = [kw.lower() for kw in keywords if kw.lower() not in category.keywords]
                    category.keywords.extend(new_keywords)
                    category_found = True
                    
                    logger.info("Добавлено {} ключевых слов в категорию '{}'", 
                               len(new_keywords), category_name)
                    break
            
            if not category_found:
                logger.warning("Категория '{}' не найдена", category_name)
                
            return category_found
            
        except Exception as e:
            logger.error("Ошибка добавления ключевых слов: {}", str(e))
            return False