"""Minimal async client for the energy agent public API v0."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import aiohttp

from .const import BASE_URL


class EnergyAgentError(Exception):
    """Generic API error."""


class AuthError(EnergyAgentError):
    """Missing or invalid API key."""


class NotConfiguredError(EnergyAgentError):
    """No forecast set up for this community and target."""


class TransientError(EnergyAgentError):
    """Temporary problem (timeout, 5xx, rate limit) - worth retrying."""


class EnergyAgentClient:
    """Client for the energy agent API."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    @staticmethod
    async def _json_or_empty(resp: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            body = await resp.json(content_type=None)
        except (aiohttp.ClientError, ValueError):
            return {}
        return body if isinstance(body, dict) else {}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with self._session.get(
                f"{BASE_URL}{path}",
                headers={"X-API-Key": self._api_key},
                params=params,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 401:
                    raise AuthError("Invalid or missing API key")
                if resp.status >= 400:
                    body = await self._json_or_empty(resp)
                    code = body.get("error_code")
                    message = body.get("message") or f"HTTP {resp.status}"
                    request_id = body.get("request_id")
                    detail = f"{code or resp.status}: {message}"
                    if request_id:
                        detail += f" (request_id {request_id})"
                    if resp.status == 404 and code == "FORECAST_NOT_CONFIGURED":
                        raise NotConfiguredError(detail)
                    if (
                        resp.status >= 500
                        or resp.status == 429
                        or (code and "TIMEOUT" in code)
                    ):
                        raise TransientError(detail)
                    raise EnergyAgentError(detail)
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise TransientError(f"Connection error: {err}") from err

    async def whoami(self) -> dict[str, Any]:
        return await self._get("/whoami")

    async def communities(self) -> list[dict[str, Any]]:
        return await self._get("/communities")

    async def forecast(
        self, community_id: str, target: str, end: datetime | None = None
    ) -> dict[str, Any]:
        """Return the forecast; without `end` the API returns the next 48 hours."""
        params: dict[str, Any] = {"target": target}
        if end is not None:
            params["end_ts"] = end.strftime("%Y-%m-%dT%H:%M:%SZ")
        return await self._get(f"/communities/{community_id}/forecast", params)
