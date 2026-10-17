"""Config flow for energy agent."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuthError, EnergyAgentClient, EnergyAgentError
from .const import CONF_API_KEY, CONF_COMMUNITY_ID, CONF_COMMUNITY_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_KEY_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


class EnergyAgentConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup UI."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str = ""
        self._communities: list[dict[str, Any]] = []

    async def _validate(self, api_key: str) -> list[dict[str, Any]]:
        client = EnergyAgentClient(async_get_clientsession(self.hass), api_key)
        await client.whoami()
        return await client.communities()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                communities = await self._validate(api_key)
            except AuthError:
                errors["base"] = "invalid_auth"
            except EnergyAgentError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"
            else:
                if not communities:
                    errors["base"] = "no_communities"
                else:
                    self._api_key = api_key
                    self._communities = communities
                    if len(communities) == 1:
                        return await self._create(communities[0])
                    return await self.async_step_community()

        return self.async_show_form(
            step_id="user", data_schema=STEP_KEY_SCHEMA, errors=errors
        )

    async def async_step_community(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            community = next(
                c for c in self._communities if c["id"] == user_input[CONF_COMMUNITY_ID]
            )
            return await self._create(community)

        options = {c["id"]: c.get("short_name") or c["name"] for c in self._communities}
        return self.async_show_form(
            step_id="community",
            data_schema=vol.Schema({vol.Required(CONF_COMMUNITY_ID): vol.In(options)}),
        )

    async def _create(self, community: dict[str, Any]) -> ConfigFlowResult:
        await self.async_set_unique_id(community["id"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=community["name"],
            data={
                CONF_API_KEY: self._api_key,
                CONF_COMMUNITY_ID: community["id"],
                CONF_COMMUNITY_NAME: community["name"],
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                await self._validate(api_key)
            except AuthError:
                errors["base"] = "invalid_auth"
            except EnergyAgentError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_API_KEY: api_key}
                )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_KEY_SCHEMA, errors=errors
        )
