"""
HTTP клиент для SyntraAI API
Получение еженедельной аналитики рынка для публикации
"""

import asyncio
from typing import Dict, Any, Optional

import aiohttp
from loguru import logger

from src.utils.config import get_config

# Настройка логгера модуля
logger = logger.bind(module="syntra_client")


class SyntraClient:
    """Клиент для работы с SyntraAI API"""

    def __init__(self):
        config = get_config()
        self.base_url = config.SYNTRA_API_URL
        self.api_key = config.SYNTRA_STATS_API_KEY
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_timeout = 30
        self.max_retries = 3

    def _get_headers(self) -> Dict[str, str]:
        """Получить заголовки для запросов с API ключом"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать HTTP сессию"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def close(self) -> None:
        """Закрыть HTTP сессию"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def get_weekly_analytics(self) -> Optional[Dict[str, Any]]:
        """
        Получить еженедельную аналитику рынка от SyntraAI

        Returns:
            Dict с данными аналитики или None при ошибке

        Формат ответа:
            {
                "market_cycle": {"phase": "growth", "phase_ru": "Рост"},
                "btc": {"price_formatted": "$98,500", ...},
                "eth": {"price_formatted": "$3,450", ...},
                "others_dominance": {"formatted": "31.3%"},
                "fear_greed": {"current": 72, "weekly_average": 68, "emoji": "😃"},
                "ai_analysis": "Текст AI анализа..."
            }
        """
        endpoint = f"{self.base_url}/api/weekly-overview"

        for attempt in range(1, self.max_retries + 1):
            try:
                session = await self._get_session()
                headers = self._get_headers()

                async with session.get(endpoint, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(
                            "✅ Получены данные еженедельной аналитики от SyntraAI: "
                            "BTC {}, F&G {}",
                            data.get("btc", {}).get("price_formatted", "N/A"),
                            data.get("fear_greed", {}).get("current", "N/A")
                        )
                        return data

                    elif response.status == 401:
                        logger.error(
                            "❌ Неверный API ключ для SyntraAI. "
                            "Проверьте SYNTRA_STATS_API_KEY в .env"
                        )
                        return None

                    elif response.status == 503:
                        logger.warning(
                            "⚠️ SyntraAI временно недоступен (503), попытка {}/{}",
                            attempt, self.max_retries
                        )
                    else:
                        error_text = await response.text()
                        logger.error(
                            "❌ Ошибка SyntraAI API: {} - {}",
                            response.status, error_text[:200]
                        )
                        return None

            except aiohttp.ClientConnectorError as e:
                logger.warning(
                    "⚠️ Не удалось подключиться к SyntraAI ({}), попытка {}/{}",
                    str(e), attempt, self.max_retries
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "⚠️ Таймаут запроса к SyntraAI, попытка {}/{}",
                    attempt, self.max_retries
                )
            except Exception as e:
                logger.exception("❌ Неожиданная ошибка при запросе к SyntraAI: {}", e)
                return None

            # Exponential backoff перед повторной попыткой
            if attempt < self.max_retries:
                wait_time = 2 ** attempt
                logger.debug("Ожидание {} секунд перед повторной попыткой", wait_time)
                await asyncio.sleep(wait_time)

        logger.error(
            "❌ Не удалось получить данные от SyntraAI после {} попыток",
            self.max_retries
        )
        return None

    async def check_health(self) -> bool:
        """Проверить доступность SyntraAI API"""
        endpoint = f"{self.base_url}/api/weekly-overview/health"

        try:
            session = await self._get_session()
            async with session.get(endpoint, headers=self._get_headers()) as response:
                if response.status == 200:
                    logger.debug("✅ SyntraAI API доступен")
                    return True
                else:
                    logger.warning("⚠️ SyntraAI API вернул статус {}", response.status)
                    return False
        except Exception as e:
            logger.warning("⚠️ SyntraAI API недоступен: {}", str(e))
            return False


# Глобальный экземпляр клиента
_syntra_client: Optional[SyntraClient] = None


def get_syntra_client() -> SyntraClient:
    """Получить глобальный экземпляр SyntraClient"""
    global _syntra_client
    if _syntra_client is None:
        _syntra_client = SyntraClient()
    return _syntra_client


async def close_syntra_client() -> None:
    """Закрыть глобальный экземпляр SyntraClient"""
    global _syntra_client
    if _syntra_client is not None:
        await _syntra_client.close()
        _syntra_client = None
