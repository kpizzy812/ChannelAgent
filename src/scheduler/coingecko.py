"""
Интеграция с CoinGecko API
Получение актуальных данных о криптовалютах
С персистентным SQLite кэшем для устойчивости к сетевым сбоям
"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

# HTTP запросы
import aiohttp

# Логирование (ОБЯЗАТЕЛЬНО loguru)
from loguru import logger

# Локальные импорты
from src.utils.config import get_config
from src.utils.exceptions import CoinGeckoAPIError

# Настройка логгера модуля
logger = logger.bind(module="coingecko_api")

# Константы CoinGecko API
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"
DEFAULT_COINS = ["bitcoin", "ethereum", "solana", "cardano", "polkadot"]

# Константы для персистентного кэша
PERSISTENT_CACHE_KEY = "coingecko_latest"
PERSISTENT_CACHE_MAX_AGE_HOURS = 24  # Максимальный возраст кэша в часах


async def save_to_persistent_cache(cache_key: str, data: Dict[str, Any]) -> bool:
    """
    Сохранить данные в персистентный SQLite кэш

    Args:
        cache_key: Ключ кэша
        data: Данные для сохранения

    Returns:
        True если сохранение успешно
    """
    try:
        from src.database.connection import get_db_connection

        # Сериализуем данные в JSON
        json_data = json.dumps(data, default=str, ensure_ascii=False)

        async with get_db_connection() as conn:
            await conn.execute("""
                INSERT OR REPLACE INTO coingecko_cache (cache_key, data, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (cache_key, json_data))
            await conn.commit()

        logger.debug("Данные сохранены в персистентный кэш: {}", cache_key)
        return True

    except Exception as e:
        logger.error("Ошибка сохранения в персистентный кэш: {}", str(e))
        return False


async def load_from_persistent_cache(cache_key: str, max_age_hours: int = PERSISTENT_CACHE_MAX_AGE_HOURS) -> Optional[Dict[str, Any]]:
    """
    Загрузить данные из персистентного SQLite кэша

    Args:
        cache_key: Ключ кэша
        max_age_hours: Максимальный возраст кэша в часах

    Returns:
        Данные из кэша или None
    """
    try:
        from src.database.connection import get_db_connection

        async with get_db_connection() as conn:
            cursor = await conn.execute("""
                SELECT data, updated_at FROM coingecko_cache
                WHERE cache_key = ?
                AND datetime(updated_at) > datetime('now', ?)
            """, (cache_key, f'-{max_age_hours} hours'))

            row = await cursor.fetchone()

            if row:
                data = json.loads(row[0])
                updated_at = row[1]
                logger.info("Загружены данные из персистентного кэша: {} (обновлено: {})", cache_key, updated_at)
                return data

        return None

    except Exception as e:
        logger.error("Ошибка загрузки из персистентного кэша: {}", str(e))
        return None


class CoinGeckoClient:
    """Клиент для работы с CoinGecko API"""
    
    def __init__(self):
        """Инициализация клиента"""
        self.config = get_config()
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, Any] = {}
        self.cache_expiry: Dict[str, datetime] = {}
        
        # Настройки API
        self.request_timeout = 30
        self.max_retries = 3
        self.retry_delay = 1
        
        logger.debug("Инициализирован CoinGecko клиент")
    
    async def __aenter__(self):
        """Асинхронный контекст менеджер - вход"""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекст менеджер - выход"""
        await self._close_session()
    
    async def _ensure_session(self):
        """Создать HTTP сессию если не существует"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            
            headers = {
                "User-Agent": "ChannelAgent/1.0",
                "Accept": "application/json"
            }
            
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers=headers
            )
    
    async def _close_session(self):
        """Закрыть HTTP сессию"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    def _is_cache_valid(self, cache_key: str, cache_minutes: int = 30) -> bool:
        """Проверить актуальность кэша"""
        if cache_key not in self.cache_expiry:
            return False
        
        expiry_time = self.cache_expiry[cache_key]
        return datetime.now() < expiry_time
    
    def _cache_data(self, cache_key: str, data: Any, cache_minutes: int = 30):
        """Закэшировать данные"""
        self.cache[cache_key] = data
        self.cache_expiry[cache_key] = datetime.now() + timedelta(minutes=cache_minutes)
    
    async def _make_request(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Сделать запрос к CoinGecko API
        
        Args:
            endpoint: API endpoint
            params: Параметры запроса
            
        Returns:
            Ответ API или None при ошибке
        """
        await self._ensure_session()
        
        url = f"{COINGECKO_API_BASE}/{endpoint.lstrip('/')}"
        
        for attempt in range(self.max_retries):
            try:
                logger.debug("Запрос к CoinGecko: {} (попытка {})", endpoint, attempt + 1)
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug("Успешный ответ CoinGecko: {} байт", len(str(data)))
                        return data
                    
                    elif response.status == 429:  # Rate limit
                        logger.warning("Rate limit CoinGecko, ждем {} секунд", self.retry_delay * (attempt + 1))
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                        continue
                    
                    else:
                        error_text = await response.text()
                        logger.error("Ошибка CoinGecko API {}: {}", response.status, error_text)
                        
                        if attempt == self.max_retries - 1:
                            raise CoinGeckoAPIError(response.status, error_text)
            
            except aiohttp.ClientError as e:
                logger.error("Сетевая ошибка CoinGecko (попытка {}): {}", attempt + 1, str(e))
                
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise CoinGeckoAPIError(details=f"Сетевая ошибка: {str(e)}")
            
            except Exception as e:
                logger.error("Неожиданная ошибка CoinGecko API: {}", str(e))
                raise CoinGeckoAPIError(details=str(e))
        
        return None
    
    async def get_coins_data(self, coin_ids: List[str]) -> Optional[List[Dict[str, Any]]]:
        """
        Получить данные о криптовалютах
        
        Args:
            coin_ids: Список ID монет
            
        Returns:
            Данные о монетах
        """
        try:
            cache_key = f"coins_data_{','.join(sorted(coin_ids))}"
            
            # Проверяем кэш (увеличено до 30 минут для снижения rate limit)
            if self._is_cache_valid(cache_key, 30):  # 30 минут
                logger.debug("Используем кэшированные данные монет")
                return self.cache[cache_key]
            
            # Запрос к API
            params = {
                'ids': ','.join(coin_ids),
                'vs_currency': 'usd',
                'include_24hr_change': 'true',
                'include_24hr_vol': 'true',
                'include_market_cap': 'true',
                'include_last_updated_at': 'true'
            }
            
            data = await self._make_request('coins/markets', params)
            
            if data:
                # Кэшируем данные (увеличено время)
                self._cache_data(cache_key, data, 30)
                logger.info("Получены данные {} криптовалют", len(data))
                return data
            
            return None
            
        except Exception as e:
            logger.error("Ошибка получения данных монет: {}", str(e))
            return None
    
    async def get_global_data(self) -> Optional[Dict[str, Any]]:
        """
        Получить глобальные данные рынка
        
        Returns:
            Глобальные данные рынка
        """
        try:
            cache_key = "global_data"
            
            # Проверяем кэш (увеличено до 45 минут для снижения rate limit)
            if self._is_cache_valid(cache_key, 45):  # 45 минут
                logger.debug("Используем кэшированные глобальные данные")
                return self.cache[cache_key]
            
            data = await self._make_request('global')
            
            if data and 'data' in data:
                global_data = data['data']
                
                # Кэшируем данные (увеличено время)
                self._cache_data(cache_key, global_data, 45)
                logger.info("Получены глобальные данные рынка")
                return global_data
            
            return None
            
        except Exception as e:
            logger.error("Ошибка получения глобальных данных: {}", str(e))
            return None
    
    async def get_trending_coins(self) -> Optional[List[Dict[str, Any]]]:
        """
        Получить trending криптовалюты
        
        Returns:
            Список trending монет
        """
        try:
            cache_key = "trending_coins"
            
            # Проверяем кэш
            if self._is_cache_valid(cache_key, 60):  # 1 час
                logger.debug("Используем кэшированные trending данные")
                return self.cache[cache_key]
            
            data = await self._make_request('search/trending')
            
            if data and 'coins' in data:
                trending_coins = data['coins']
                
                # Кэшируем данные
                self._cache_data(cache_key, trending_coins, 60)
                logger.info("Получены trending криптовалюты: {} монет", len(trending_coins))
                return trending_coins
            
            return None
            
        except Exception as e:
            logger.error("Ошибка получения trending монет: {}", str(e))
            return None


# Глобальный клиент
_coingecko_client: Optional[CoinGeckoClient] = None


def get_coingecko_client() -> CoinGeckoClient:
    """Получить глобальный экземпляр CoinGecko клиента"""
    global _coingecko_client
    
    if _coingecko_client is None:
        _coingecko_client = CoinGeckoClient()
    
    return _coingecko_client


async def get_coingecko_data() -> Optional[Dict[str, Any]]:
    """
    Получить актуальные данные криптовалют
    Главная функция для использования в задачах планировщика
    При ошибке сети использует персистентный SQLite кэш

    Returns:
        Объединенные данные CoinGecko
    """
    try:
        logger.info("📊 Получение данных CoinGecko")

        config = get_config()

        # Определяем какие монеты отслеживать
        coins_config = getattr(config, 'COINGECKO_COINS', 'bitcoin,ethereum,solana')
        coin_ids = [coin.strip() for coin in coins_config.split(',')]

        if not coin_ids:
            coin_ids = DEFAULT_COINS

        logger.debug("Отслеживаемые монеты: {}", coin_ids)

        try:
            async with get_coingecko_client() as client:
                # Параллельно получаем разные типы данных
                tasks = [
                    client.get_coins_data(coin_ids),
                    client.get_global_data(),
                    client.get_trending_coins()
                ]

                coins_data, global_data, trending_data = await asyncio.gather(
                    *tasks, return_exceptions=True
                )

                # Обрабатываем исключения
                if isinstance(coins_data, Exception):
                    logger.error("Ошибка получения данных монет: {}", str(coins_data))
                    coins_data = None

                if isinstance(global_data, Exception):
                    logger.error("Ошибка получения глобальных данных: {}", str(global_data))
                    global_data = None

                if isinstance(trending_data, Exception):
                    logger.error("Ошибка получения trending данных: {}", str(trending_data))
                    trending_data = None

                # Объединяем данные
                result = {
                    'coins': coins_data or [],
                    'global': global_data or {},
                    'trending': trending_data or [],
                    'last_updated': datetime.now().isoformat(),
                    'success': bool(coins_data or global_data),
                    'from_cache': False
                }

                if result['success']:
                    logger.info("✅ Данные CoinGecko получены успешно")
                    # Сохраняем в персистентный кэш для будущих сбоев
                    await save_to_persistent_cache(PERSISTENT_CACHE_KEY, result)
                else:
                    logger.warning("⚠️ Не удалось получить данные CoinGecko, пробуем кэш")
                    # Пробуем загрузить из персистентного кэша
                    cached_data = await load_from_persistent_cache(PERSISTENT_CACHE_KEY)
                    if cached_data:
                        cached_data['from_cache'] = True
                        cached_data['success'] = True
                        logger.info("📦 Используются данные из персистентного кэша")
                        return cached_data

                return result

        except (aiohttp.ClientError, CoinGeckoAPIError) as network_error:
            # Сетевая ошибка - пробуем персистентный кэш
            logger.warning("⚠️ Сетевая ошибка CoinGecko: {}, пробуем персистентный кэш", str(network_error))

            cached_data = await load_from_persistent_cache(PERSISTENT_CACHE_KEY)
            if cached_data:
                cached_data['from_cache'] = True
                cached_data['success'] = True
                logger.info("📦 Используются данные из персистентного кэша (сетевая ошибка)")
                return cached_data

            # Если кэш пустой, возвращаем пустые данные с флагом ошибки
            logger.error("❌ Нет данных в кэше, возвращаем пустые данные")
            return {
                'coins': [],
                'global': {},
                'trending': [],
                'last_updated': datetime.now().isoformat(),
                'success': False,
                'from_cache': False,
                'error': str(network_error)
            }

    except Exception as e:
        logger.error("❌ Критическая ошибка получения данных CoinGecko: {}", str(e))

        # Последняя попытка - персистентный кэш
        try:
            cached_data = await load_from_persistent_cache(PERSISTENT_CACHE_KEY)
            if cached_data:
                cached_data['from_cache'] = True
                cached_data['success'] = True
                logger.info("📦 Критическая ошибка, используем персистентный кэш")
                return cached_data
        except Exception:
            pass

        raise CoinGeckoAPIError(details=str(e))


def format_crypto_summary(crypto_data: Dict[str, Any]) -> str:
    """
    Форматировать краткую сводку по криптовалютам
    
    Args:
        crypto_data: Данные от CoinGecko
        
    Returns:
        Отформатированная сводка
    """
    try:
        if not crypto_data or not crypto_data.get('success'):
            return "❌ Нет данных о криптовалютах"
        
        coins = crypto_data.get('coins', [])
        global_data = crypto_data.get('global', {})
        
        summary_parts = []
        
        # Заголовок
        summary_parts.append("📊 **Краткая сводка рынка**")
        
        # Топ монеты
        if coins:
            summary_parts.append("\n🚀 **Топ криптовалюты:**")
            
            for i, coin in enumerate(coins[:3], 1):
                name = coin.get('name', 'Unknown')
                symbol = coin.get('symbol', '').upper()
                price = coin.get('current_price', 0)
                change_24h = coin.get('price_change_percentage_24h', 0)
                
                # Форматирование цены
                if price >= 1:
                    price_str = f"${price:,.2f}"
                else:
                    price_str = f"${price:.6f}".rstrip('0').rstrip('.')
                
                # Эмодзи для изменения
                change_emoji = "📈" if change_24h > 0 else "📉"
                change_sign = "+" if change_24h > 0 else ""
                
                summary_parts.append(
                    f"{i}. **{symbol}**: {price_str} {change_emoji} {change_sign}{change_24h:.2f}%"
                )
        
        # Глобальные данные
        if global_data:
            market_cap = global_data.get('total_market_cap', {}).get('usd', 0)
            market_cap_change = global_data.get('market_cap_change_percentage_24h_usd', 0)
            btc_dominance = global_data.get('market_cap_percentage', {}).get('btc', 0)
            
            if market_cap:
                summary_parts.append("\n💰 **Рынок:**")
                
                market_cap_t = market_cap / 1_000_000_000_000
                change_emoji = "📈" if market_cap_change > 0 else "📉"
                
                summary_parts.append(
                    f"Капитализация: **${market_cap_t:.2f}T** {change_emoji} {market_cap_change:+.2f}%"
                )
                
                if btc_dominance:
                    summary_parts.append(f"Доминация BTC: **{btc_dominance:.1f}%**")
        
        # Время обновления
        last_updated = crypto_data.get('last_updated')
        if last_updated:
            time_str = last_updated.strftime("%H:%M")
            summary_parts.append(f"\n🕐 Обновлено: {time_str}")
        
        return "\n".join(summary_parts)
        
    except Exception as e:
        logger.error("Ошибка форматирования сводки криптовалют: {}", str(e))
        return "❌ Ошибка форматирования данных"


def get_market_sentiment(crypto_data: Dict[str, Any]) -> str:
    """
    Определить настроение рынка
    
    Args:
        crypto_data: Данные CoinGecko
        
    Returns:
        Описание настроения рынка
    """
    try:
        global_data = crypto_data.get('global', {})
        market_cap_change = global_data.get('market_cap_change_percentage_24h_usd', 0)
        
        if market_cap_change > 3:
            return "🟢 Сильный рост - бычий рынок"
        elif market_cap_change > 1:
            return "🟢 Умеренный рост"
        elif market_cap_change > -1:
            return "🟡 Боковое движение"
        elif market_cap_change > -3:
            return "🔴 Умеренное падение"
        else:
            return "🔴 Сильное падение - медвежий рынок"
    
    except Exception:
        return "❓ Настроение неопределено"


async def get_coin_price_with_change(coin_id: str) -> Optional[Dict[str, Any]]:
    """
    Получить курс конкретной криптовалюты с изменением за 24ч
    
    Args:
        coin_id: ID монеты (например, 'bitcoin', 'ethereum')
        
    Returns:
        Данные о цене и изменении
    """
    try:
        async with get_coingecko_client() as client:
            data = await client.get_coins_data([coin_id])
            
            if data and len(data) > 0:
                coin = data[0]
                return {
                    'symbol': coin.get('symbol', '').upper(),
                    'name': coin.get('name', ''),
                    'price': coin.get('current_price', 0),
                    'change_24h': coin.get('price_change_percentage_24h', 0),
                    'formatted_price': format_price(coin.get('current_price', 0)),
                    'formatted_change': format_change(coin.get('price_change_percentage_24h', 0))
                }
            
            return None
            
    except Exception as e:
        logger.error("Ошибка получения курса {}: {}", coin_id, str(e))
        return None


async def get_btc_dominance() -> Optional[float]:
    """
    Получить доминацию Bitcoin в %
    
    Returns:
        Доминация BTC в процентах
    """
    try:
        async with get_coingecko_client() as client:
            global_data = await client.get_global_data()
            
            if global_data:
                dominance = global_data.get('market_cap_percentage', {}).get('btc', 0)
                return round(dominance, 1) if dominance else None
            
            return None
            
    except Exception as e:
        logger.error("Ошибка получения доминации BTC: {}", str(e))
        return None


async def get_total_market_cap() -> Optional[Dict[str, Any]]:
    """
    Получить общую капитализацию крипторынка
    
    Returns:
        Данные о капитализации рынка
    """
    try:
        async with get_coingecko_client() as client:
            global_data = await client.get_global_data()
            
            if global_data:
                market_cap = global_data.get('total_market_cap', {}).get('usd', 0)
                market_cap_change = global_data.get('market_cap_change_percentage_24h_usd', 0)
                
                return {
                    'market_cap': market_cap,
                    'market_cap_trillions': market_cap / 1_000_000_000_000,
                    'change_24h': market_cap_change,
                    'formatted_cap': f"${market_cap / 1_000_000_000_000:.2f}T",
                    'formatted_change': format_change(market_cap_change)
                }
            
            return None
            
    except Exception as e:
        logger.error("Ошибка получения капитализации рынка: {}", str(e))
        return None


def format_price(price: float) -> str:
    """Форматировать цену криптовалюты (моноширинный шрифт)"""
    if price >= 1000:
        return f"`${price:,.0f}`"
    elif price >= 1:
        return f"`${price:,.2f}`"
    else:
        formatted = f"${price:.6f}".rstrip('0').rstrip('.')
        return f"`{formatted}`"


def format_change(change: float) -> str:
    """Форматировать изменение цены (эмодзи + моноширинный)"""
    sign = "+" if change > 0 else ""
    emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
    return f"{emoji} `{sign}{change:.1f}%`"


async def get_template_variables() -> Dict[str, str]:
    """
    Получить все переменные для подстановки в шаблоны
    ОПТИМИЗИРОВАННАЯ ВЕРСИЯ - один запрос вместо множества
    
    Returns:
        Словарь переменных для замены в шаблонах
    """
    try:
        logger.debug("📝 Получение переменных для шаблонов (оптимизированно)")
        
        variables = {}
        
        # ОПТИМИЗАЦИЯ: Один запрос для всех данных (с очисткой кэша для отладки)
        client = get_coingecko_client()
        client.cache.clear()  # Очистка кэша для отладки
        client.cache_expiry.clear()
        
        crypto_data = await get_coingecko_data()
        
        if crypto_data and crypto_data.get('success'):
            # Обрабатываем данные монет
            coins = crypto_data.get('coins', [])
            
            # Создаем мапинг ID -> данные монет
            coin_map = {}
            for coin in coins:
                coin_id = coin.get('id', '').lower()
                coin_map[coin_id] = coin
            
            # Используем монеты из конфигурации (динамически)
            config = get_config()
            coin_ids_config = [coin.strip() for coin in config.COINGECKO_COINS.split(',')]
            
            # Мапинг ID -> символ (расширяемый)
            coin_symbol_map = {
                'bitcoin': 'BTC',
                'ethereum': 'ETH', 
                'solana': 'SOL',
                'cardano': 'ADA',
                'polkadot': 'DOT',
                'binancecoin': 'BNB',
                'ripple': 'XRP',
                'avalanche-2': 'AVAX',
                'polygon': 'MATIC',
                'chainlink': 'LINK'
            }
            
            # Создаем target_coins на основе конфигурации
            target_coins = {}
            for coin_id in coin_ids_config:
                if coin_id in coin_symbol_map:
                    target_coins[coin_id] = coin_symbol_map[coin_id]
                else:
                    logger.warning("Неизвестная монета в конфиге: {}", coin_id)
            
            for coin_id, symbol in target_coins.items():
                if coin_id in coin_map:
                    coin = coin_map[coin_id]
                    price = coin.get('current_price', 0)
                    change_24h = coin.get('price_change_percentage_24h', 0)
                    
                    # Форматирование
                    formatted_price = format_price(price)
                    formatted_change = format_change(change_24h)
                    
                    # Добавляем переменные
                    variables[f"{symbol}_PRICE"] = formatted_price
                    variables[f"{symbol}_CHANGE"] = formatted_change
                    variables[f"{symbol}_CHANGE_NUM"] = f"{change_24h:+.1f}"
                    variables[symbol] = formatted_price
                else:
                    logger.warning("Данные для {} не найдены в ответе API", coin_id)
            
            # Глобальные данные рынка (из того же запроса)
            global_data = crypto_data.get('global', {})
            
            if global_data:
                # Доминация BTC (моноширинный)
                btc_dominance = global_data.get('market_cap_percentage', {}).get('btc', 0)
                if btc_dominance:
                    variables['BTC_DOMINANCE'] = f"`{btc_dominance:.1f}%`"
                    variables['BITCOIN_DOMINANCE'] = f"`{btc_dominance:.1f}%`"

                # Капитализация рынка (моноширинный)
                market_cap = global_data.get('total_market_cap', {}).get('usd', 0)
                market_cap_change = global_data.get('market_cap_change_percentage_24h_usd', 0)

                if market_cap:
                    market_cap_t = market_cap / 1_000_000_000_000
                    variables['MARKET_CAP'] = f"`${market_cap_t:.2f}T`"
                    variables['MARKETCAP'] = variables['MARKET_CAP']  # Алиас
                    variables['MARKET_CHANGE'] = format_change(market_cap_change)
                    variables['MARKET_CHANGE_NUM'] = f"`{market_cap_change:+.1f}`"

            # Алиасы для удобства (без подчёркивания)
            if 'BTC_DOMINANCE' in variables:
                variables['BTCDOMINANCE'] = variables['BTC_DOMINANCE']
            if 'BTC_PRICE' in variables:
                variables['BTCPRICE'] = variables['BTC_PRICE']
            if 'ETH_PRICE' in variables:
                variables['ETHPRICE'] = variables['ETH_PRICE']
            if 'SOL_PRICE' in variables:
                variables['SOLPRICE'] = variables['SOL_PRICE']
            if 'BTC_CHANGE' in variables:
                variables['BTCCHANGE'] = variables['BTC_CHANGE']
            if 'ETH_CHANGE' in variables:
                variables['ETHCHANGE'] = variables['ETH_CHANGE']
            if 'SOL_CHANGE' in variables:
                variables['SOLCHANGE'] = variables['SOL_CHANGE']
        else:
            logger.warning("Не удалось получить данные CoinGecko для переменных")
        
        # Переменные времени (всегда добавляем)
        from datetime import datetime
        now = datetime.now()
        variables['DATE'] = now.strftime("%d.%m.%Y")
        variables['TIME'] = now.strftime("%H:%M")
        variables['WEEKDAY'] = now.strftime("%A")
        
        weekday_ru = {
            'Monday': 'Понедельник',
            'Tuesday': 'Вторник', 
            'Wednesday': 'Среда',
            'Thursday': 'Четверг',
            'Friday': 'Пятница',
            'Saturday': 'Суббота',
            'Sunday': 'Воскресенье'
        }
        variables['WEEKDAY_RU'] = weekday_ru.get(variables['WEEKDAY'], variables['WEEKDAY'])
        
        logger.debug("Получено {} переменных для шаблонов (оптимизированно)", len(variables))
        return variables
        
    except Exception as e:
        logger.error("Ошибка получения переменных шаблонов: {}", str(e))
        
        # Возвращаем хотя бы переменные времени в случае ошибки
        try:
            from datetime import datetime
            now = datetime.now()
            return {
                'DATE': now.strftime("%d.%m.%Y"),
                'TIME': now.strftime("%H:%M"),
                'WEEKDAY_RU': ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'][now.weekday()]
            }
        except:
            return {}


def apply_template_variables(template: str, variables: Dict[str, str]) -> str:
    """
    Применить переменные к шаблону
    
    Args:
        template: Шаблон с переменными в формате {VAR_NAME}
        variables: Словарь переменных
        
    Returns:
        Строка с подставленными значениями
    """
    try:
        result = template
        
        # Применяем переменные к шаблону
        for var_name, var_value in variables.items():
            placeholder = f"{{{var_name}}}"
            if placeholder in result:
                result = result.replace(placeholder, var_value)
        
        # Проверяем остались ли незамененные переменные
        import re
        remaining_vars = re.findall(r'\{([A-Z_]+)\}', result)
        if remaining_vars:
            logger.warning("⚠️ Незамененные переменные: {}", remaining_vars)
        
        return result
        
    except Exception as e:
        logger.error("Ошибка применения переменных шаблона: {}", str(e))
        return template


async def test_coingecko_connection() -> bool:
    """
    Тестировать подключение к CoinGecko API
    
    Returns:
        True если подключение работает
    """
    try:
        logger.info("🔍 Тестирование подключения к CoinGecko API")
        
        async with get_coingecko_client() as client:
            # Простой запрос для тестирования
            data = await client.get_coins_data(['bitcoin'])
            
            if data and len(data) > 0:
                logger.info("✅ Подключение к CoinGecko работает")
                return True
            else:
                logger.error("❌ CoinGecko вернул пустые данные")
                return False
    
    except Exception as e:
        logger.error("❌ Ошибка подключения к CoinGecko: {}", str(e))
        return False