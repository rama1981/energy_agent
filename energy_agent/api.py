"""Minimal async client for the energy agent public API v0."""
from __future__ import annotations

from typing import Any

import aiohttp

from .const import BASE_URL


class EnergyAgentError(Exception):
    """Generic API error."""


class AuthError(EnergyAgentError):
    """Missing or invalid API key."""


class NotConfiguredError(EnergyAgentError):
    """No forecast set up for this community and target."""


class EnergyAgentClient:
    """Client for the energy agent API."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with self._session.get(
                f"{BASE_URL}{path}",
                headers={"X-API-Key": self._api_key},
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 401:
                    raise AuthError("Invalid or missing API key")
                if resp.status >= 400:
                    try:
                        body = await resp.json(content_type=None)
                    except (aiohttp.ClientError, ValueError):
                        body = {}
                    code = body.get("error_code") if isinstance(body, dict) else None
                    message = (
                        body.get("message") if isinstance(body, dict) else None
                    ) or f"HTTP {resp.status}"
                    if resp.status == 404 and code == "FORECAST_NOT_CONFIGURED":
                        raise NotConfiguredError(message)
                    raise EnergyAgentError(f"{code or resp.status}: {message}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EnergyAgentError(f"Connection error: {err}") from err

    async def whoami(self) -> dict[str, Any]:
        return await self._get("/whoami")

    async def communities(self) -> list[dict[str, Any]]:
        return await self._get("/communities")

    async def forecast(self, community_id: str, target: str) -> dict[str, Any]:
        # Without start_ts/end_ts the API returns the next 48 hours.
        return await self._get(
            f"/communities/{community_id}/forecast", {"target": target}
        )
