"""Sensors for energy agent forecasts."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_COMMUNITY_NAME, DOMAIN, INTERVAL, KWH_TO_KW, TARGETS
from .coordinator import (
    CommunityForecast,
    EnergyAgentConfigEntry,
    EnergyAgentCoordinator,
    ForecastPoint,
)

STATES = [
    "disabled",
    "preparing",
    "estimated",
    "bootstrap",
    "healthy",
    "blocked",
    "stale",
    "failed",
    "not_eligible",
]


def _current_point(fc: CommunityForecast, now: datetime) -> ForecastPoint | None:
    for p in fc.points:
        if p.timestamp <= now < p.timestamp + INTERVAL:
            return p
    return None


def _current_value(fc: CommunityForecast, now: datetime) -> StateType:
    p = _current_point(fc, now)
    return p.p50 if p else None


def _current_attrs(fc: CommunityForecast, now: datetime) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "forecast": [
            {
                "timestamp": p.timestamp.isoformat(),
                "p10": p.p10,
                "p50": p.p50,
                "p90": p.p90,
                "kind": p.kind,
            }
            for p in fc.points
        ]
    }
    p = _current_point(fc, now)
    if p:
        attrs.update(
            interval_start=p.timestamp.isoformat(),
            p10_kwh=p.p10,
            p90_kwh=p.p90,
            kind=p.kind,
        )
    return attrs


def _current_power_value(fc: CommunityForecast, now: datetime) -> StateType:
    p = _current_point(fc, now)
    return round(p.p50 * KWH_TO_KW, 3) if p else None


def _current_power_attrs(fc: CommunityForecast, now: datetime) -> dict[str, Any]:
    p = _current_point(fc, now)
    if not p:
        return {}
    return {
        "interval_start": p.timestamp.isoformat(),
        "p10_kw": round(p.p10 * KWH_TO_KW, 3),
        "p90_kw": round(p.p90 * KWH_TO_KW, 3),
        "kind": p.kind,
    }


def _next_24h_value(fc: CommunityForecast, now: datetime) -> StateType:
    end = now + timedelta(hours=24)
    vals = [
        p.p50 for p in fc.points if p.timestamp + INTERVAL > now and p.timestamp < end
    ]
    return round(sum(vals), 3) if vals else None


def _state_value(fc: CommunityForecast, now: datetime) -> StateType:
    return fc.state


@dataclass(frozen=True, kw_only=True)
class EnergyAgentSensorDescription(SensorEntityDescription):
    target: str
    value_fn: Callable[[CommunityForecast, datetime], StateType]
    attrs_fn: Callable[[CommunityForecast, datetime], dict[str, Any]] | None = None


def _descriptions(target: str) -> tuple[EnergyAgentSensorDescription, ...]:
    return (
        EnergyAgentSensorDescription(
            key=f"{target}_current",
            translation_key=f"{target}_current",
            target=target,
            device_class=SensorDeviceClass.ENERGY,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            suggested_display_precision=3,
            value_fn=_current_value,
            attrs_fn=_current_attrs,
        ),
        EnergyAgentSensorDescription(
            key=f"{target}_current_power",
            translation_key=f"{target}_current_power",
            target=target,
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.KILO_WATT,
            suggested_display_precision=1,
            value_fn=_current_power_value,
            attrs_fn=_current_power_attrs,
        ),
        EnergyAgentSensorDescription(
            key=f"{target}_next_24h",
            translation_key=f"{target}_next_24h",
            target=target,
            device_class=SensorDeviceClass.ENERGY,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            suggested_display_precision=1,
            value_fn=_next_24h_value,
        ),
        EnergyAgentSensorDescription(
            key=f"{target}_state",
            translation_key=f"{target}_state",
            target=target,
            device_class=SensorDeviceClass.ENUM,
            options=STATES,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=_state_value,
        ),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnergyAgentConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        EnergyAgentSensor(coordinator, entry, desc)
        for target in TARGETS
        if coordinator.data.get(target) is not None
        for desc in _descriptions(target)
    )


class EnergyAgentSensor(CoordinatorEntity[EnergyAgentCoordinator], SensorEntity):
    """A forecast sensor."""

    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({"forecast"})
    entity_description: EnergyAgentSensorDescription

    def __init__(
        self,
        coordinator: EnergyAgentCoordinator,
        entry: EnergyAgentConfigEntry,
        description: EnergyAgentSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.community_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.community_id)},
            name=entry.data[CONF_COMMUNITY_NAME],
            manufacturer="energy agent",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _forecast(self) -> CommunityForecast | None:
        return self.coordinator.data.get(self.entity_description.target)

    @property
    def available(self) -> bool:
        return super().available and self._forecast is not None

    @property
    def native_value(self) -> StateType:
        fc = self._forecast
        return self.entity_description.value_fn(fc, dt_util.utcnow()) if fc else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fc = self._forecast
        fn = self.entity_description.attrs_fn
        return fn(fc, dt_util.utcnow()) if fc and fn else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Switch to the next 15-minute interval without waiting for a poll.
        self.async_on_remove(
            async_track_utc_time_change(
                self.hass, self._tick, minute=(0, 15, 30, 45), second=1
            )
        )

    @callback
    def _tick(self, _now: datetime) -> None:
        self.async_write_ha_state()
