"""Config flow for Crestron DM NVX."""

import logging
from typing import Any, override

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util.network import is_host_valid

from crestron_nvx import (
    NvxApiError,
    NvxAuthenticationError,
    NvxClient,
    NvxConnectionError,
    NvxResponseError,
    NvxSnapshot,
)

from .const import CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _async_validate_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> NvxSnapshot:
    """Validate credentials and return the endpoint identity."""

    client = NvxClient(
        async_get_clientsession(hass),
        user_input[CONF_HOST],
        user_input[CONF_USERNAME],
        user_input[CONF_PASSWORD],
        verify_ssl=user_input[CONF_VERIFY_SSL],
    )
    return await client.async_get_snapshot()


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the endpoint schema."""

    values = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=values.get(CONF_HOST)): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Required(
                CONF_USERNAME, default=values.get(CONF_USERNAME, "admin")
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_VERIFY_SSL,
                default=values.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            ): BooleanSelector(),
        }
    )


class CrestronNvxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Crestron DM NVX config flow."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up one endpoint."""

        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip().lower()
            if not is_host_valid(user_input[CONF_HOST]):
                errors[CONF_HOST] = "invalid_host"
            else:
                try:
                    snapshot = await _async_validate_input(self.hass, user_input)
                except NvxAuthenticationError:
                    errors["base"] = "invalid_auth"
                except NvxConnectionError:
                    errors["base"] = "cannot_connect"
                except NvxResponseError:
                    errors["base"] = "invalid_response"
                except NvxApiError:
                    errors["base"] = "unknown"
                except Exception:
                    _LOGGER.exception("Unexpected error validating DM NVX endpoint")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(snapshot.device.device_id)
                    self._abort_if_unique_id_configured(
                        updates={CONF_HOST: user_input[CONF_HOST]}
                    )
                    return self.async_create_entry(
                        title=snapshot.device.name,
                        data=user_input,
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication."""

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm new endpoint credentials."""

        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                snapshot = await _async_validate_input(self.hass, data)
            except NvxAuthenticationError:
                errors["base"] = "invalid_auth"
            except NvxConnectionError, NvxResponseError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected DM NVX reauthentication error")
                errors["base"] = "unknown"
            else:
                if snapshot.device.device_id != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=entry.data[CONF_USERNAME],
                    ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update endpoint connection settings."""

        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip().lower()
            if not is_host_valid(user_input[CONF_HOST]):
                errors[CONF_HOST] = "invalid_host"
            else:
                try:
                    snapshot = await _async_validate_input(self.hass, user_input)
                except NvxAuthenticationError:
                    errors["base"] = "invalid_auth"
                except NvxConnectionError:
                    errors["base"] = "cannot_connect"
                except NvxResponseError:
                    errors["base"] = "invalid_response"
                except Exception:
                    _LOGGER.exception("Unexpected DM NVX reconfiguration error")
                    errors["base"] = "unknown"
                else:
                    if snapshot.device.device_id != entry.unique_id:
                        return self.async_abort(reason="wrong_device")
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates=user_input,
                        title=snapshot.device.name,
                    )
        defaults = dict(entry.data)
        defaults.pop(CONF_PASSWORD, None)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(defaults),
            errors=errors,
        )
