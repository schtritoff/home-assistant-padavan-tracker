"""Config flow for the Padavan Tracker integration."""

from __future__ import annotations

import logging
from typing import Any, override

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from homeassistant.components.device_tracker import (
    CONF_CONSIDER_HOME,
    DEFAULT_CONSIDER_HOME,
)

from .client import (
    PadavanAuthError,
    PadavanConnectionError,
    PadavanRouterError,
    normalize_host,
    PadavanWebClient,
)
from .const import (
    CONF_REQUIRE_IP,
    CONF_TRACK_UNKNOWN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_REQUIRE_IP,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRACK_UNKNOWN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: Any, data: dict[str, Any]) -> int:
    """Try to reach the router, return the number of clients seen."""
    router = PadavanWebClient(
        host=data[CONF_HOST],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        session=async_get_clientsession(hass),
        verify_ssl=data.get(CONF_VERIFY_SSL, False),
    )
    clients = await router.async_get_connected_devices()
    _LOGGER.debug("Router %s has %d clients", data[CONF_HOST], len(clients))
    return len(clients)


class PadavanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Padavan Tracker config flow."""

    VERSION = 1

    @override
    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                user_input[CONF_HOST] = normalize_host(user_input[CONF_HOST])
            except PadavanConnectionError:
                errors[CONF_HOST] = "invalid_host"
            if not errors:
                try:
                    await validate_input(self.hass, user_input)
                except PadavanAuthError:
                    errors["base"] = "invalid_auth"
                except PadavanRouterError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error in config flow")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(user_input[CONF_HOST])
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input[CONF_HOST], data=user_input
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default="192.168.2.1"): str,
                    vol.Required(CONF_USERNAME, default="admin"): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_VERIFY_SSL, default=False): bool,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> PadavanOptionsFlow:
        """Get the options flow for this handler."""
        return PadavanOptionsFlow()


class PadavanOptionsFlow(config_entries.OptionsFlow):
    """Handle Padavan Tracker options."""

    @override
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        entry = self.config_entry
        current = entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=current.get(
                        CONF_UPDATE_INTERVAL,
                        int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
                vol.Required(
                    CONF_CONSIDER_HOME,
                    default=current.get(
                        CONF_CONSIDER_HOME,
                        int(DEFAULT_CONSIDER_HOME.total_seconds()),
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
                vol.Required(
                    CONF_TRACK_UNKNOWN,
                    default=current.get(CONF_TRACK_UNKNOWN, DEFAULT_TRACK_UNKNOWN),
                ): bool,
                vol.Required(
                    CONF_REQUIRE_IP,
                    default=current.get(CONF_REQUIRE_IP, DEFAULT_REQUIRE_IP),
                ): bool,
            }
        )
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(step_id="init", data_schema=schema)
