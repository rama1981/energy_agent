"""DataUpdateCoordinator for energy agent."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AuthError, EnergyAgentClient, EnergyAgentError, NotConfiguredError
from .const import DOMAIN, SCAN_INTERVAL, TARGETS

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    timestamp: datetime
    p10: float
    p50: float
    p90: float
    kind: str


@dataclass(frozen=True, slots=True)
class CommunityForecast:
    target: str
    state: str
    points: list[ForecastPoint]


def _parse(raw: dict[str, Any]) -> CommunityForecast:
    points: list[ForecastPoint] = []
    for p in raw.get("points") or []:
        ts = dt_util.parse_datetime(p["timestamp"])
        if ts is None:
            continue
        points.append(
            ForecastPoint(
                dt_util.as_utc(ts),
                p["p10_kwh"],
                p["p50_kwh"],
                p["p90_kwh"],
                p["kind"],
            )
        )
    points.sort(key=lambda x: x.timestamp)
    return CommunityForecast(raw["target"], raw["state"], points)


class EnergyAgentCoordinator(DataUpdateCoordinator[dict[str, CommunityForecast | None]]):
    """Fetches generation and consumption forecasts of one community."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: EnergyAgentClient,
        community_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{community_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.community_id = community_id

    async def _async_update_data(self) -> dict[str, CommunityForecast | None]:
        data: dict[str, CommunityForecast | None] = {}
        for target in TARGETS:
            try:
                raw = await self.client.forecast(self.community_id, target)
            except NotConfiguredError:
                data[target] = None
            except AuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except EnergyAgentError as err:
                raise UpdateFailed(str(err)) from err
            else:
                data[target] = _parse(raw)
        return data


type EnergyAgentConfigEntry = ConfigEntry[EnergyAgentCoordinator]
