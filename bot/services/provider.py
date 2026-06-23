"""
TheMainSMMProvider API client with tenacity retry logic and Redis caching.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import aiohttp
import orjson
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from bot.config.settings import get_settings
from bot.database.redis import get_cached, set_cached

logger = logging.getLogger(__name__)

# Cache TTLs
SERVICES_CACHE_TTL = 1800   # 30 minutes
BALANCE_CACHE_TTL = 300     # 5 minutes

CACHE_KEY_SERVICES = "provider:services"
CACHE_KEY_BALANCE = "provider:balance"


class ProviderAPIError(Exception):
    """Raised when the provider API returns an error."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ProviderAPI:
    """Async client for TheMainSMMProvider API."""

    def __init__(self):
        self.settings = get_settings()
        self.api_url = self.settings.PROVIDER_API_URL
        self.api_key = self.settings.PROVIDER_API_KEY
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                json_serialize=lambda x: orjson.dumps(x).decode(),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        reraise=True,
    )
    async def _request(self, data: dict) -> Any:
        """Make a POST request to the provider API."""
        session = await self._get_session()
        payload = {"key": self.api_key, **data}

        logger.debug("Provider API request: action=%s", data.get("action"))

        async with session.post(
            self.api_url,
            data=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            raw = await resp.read()
            result = orjson.loads(raw)

            # Check for error response
            if isinstance(result, dict) and "error" in result:
                error_msg = result["error"]
                logger.error("Provider API error: %s", error_msg)
                raise ProviderAPIError(error_msg)

            return result

    async def get_services(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch the full service catalogue.
        Cached in Redis for 30 minutes.
        """
        if not force_refresh:
            cached = await get_cached(CACHE_KEY_SERVICES)
            if cached is not None:
                logger.debug("Services loaded from cache (%d items)", len(cached))
                return cached

        services = await self._request({"action": "services"})

        if isinstance(services, list):
            await set_cached(CACHE_KEY_SERVICES, services, ttl=SERVICES_CACHE_TTL)
            logger.info("Services fetched and cached (%d items)", len(services))

        return services

    async def get_balance(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetch provider account balance.
        Cached in Redis for 5 minutes.
        """
        if not force_refresh:
            cached = await get_cached(CACHE_KEY_BALANCE)
            if cached is not None:
                return cached

        result = await self._request({"action": "balance"})
        await set_cached(CACHE_KEY_BALANCE, result, ttl=BALANCE_CACHE_TTL)
        logger.info("Provider balance: %s", result)
        return result

    async def add_order(
        self,
        service_id: str,
        url: str,
        quantity: int,
    ) -> Dict[str, Any]:
        """Place a new order with the provider."""
        result = await self._request({
            "action": "add",
            "service": str(service_id),
            "link": url,
            "quantity": str(quantity),
        })
        logger.info("Order placed: %s", result)
        return result

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Fetch the status of a single order."""
        result = await self._request({
            "action": "status",
            "order": str(order_id),
        })
        return result

    async def get_multi_order_status(
        self, order_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Fetch statuses for multiple orders at once (up to 100).
        Returns a dict mapping order_id → status data.
        """
        ids_str = ",".join(str(oid) for oid in order_ids[:100])
        result = await self._request({
            "action": "status",
            "orders": ids_str,
        })
        return result

    async def refill_order(self, order_id: str) -> Dict[str, Any]:
        """Request a refill for an order."""
        result = await self._request({
            "action": "refill",
            "order": str(order_id),
        })
        logger.info("Refill requested for order %s: %s", order_id, result)
        return result

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Request cancellation of an order."""
        result = await self._request({
            "action": "cancel",
            "order": str(order_id),
        })
        logger.info("Cancel requested for order %s: %s", order_id, result)
        return result

    async def get_services_by_category(
        self, force_refresh: bool = False
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch services and group them by category.
        Returns {category_name: [services...]}.
        """
        services = await self.get_services(force_refresh=force_refresh)
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for svc in services:
            cat = svc.get("category", "Other")
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(svc)
        return grouped

    async def find_service_by_id(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Find a specific service by its ID from the cached catalogue."""
        services = await self.get_services()
        for svc in services:
            if str(svc.get("service")) == str(service_id):
                return svc
        return None


# Module-level singleton
_provider: Optional[ProviderAPI] = None


def get_provider() -> ProviderAPI:
    """Return the singleton ProviderAPI instance."""
    global _provider
    if _provider is None:
        _provider = ProviderAPI()
    return _provider
