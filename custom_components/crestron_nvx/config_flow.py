"""Config flow for Crestron DM NVX."""

import logging
from ipaddress import IPv4Address
from typing import Any, override

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.discovery_flow import DiscoveryKey
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
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

from .const import CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL, DOMAIN, SUPPORTED_MODELS
from .discovery import (
    DiscoveredDevice,
    DiscoveryBusyError,
    DiscoveryError,
    async_discover,
    parse_target,
)
from .identity import (
    async_configured_addresses,
    async_ipv4_addresses,
    authenticated_entry,
)

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


def _schema(
    defaults: dict[str, Any] | None = None, *, include_host: bool = True
) -> vol.Schema:
    """Build the endpoint schema."""

    values = defaults or {}
    schema = vol.Schema(
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
    if not include_host:
        del schema.schema[CONF_HOST]
        schema = vol.Schema(schema.schema)
    return schema


class CrestronNvxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Crestron DM NVX config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Hold untrusted candidates only for this setup flow."""
        self._devices: dict[str, DiscoveredDevice] = {}
        self._selected: DiscoveredDevice | None = None

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer a bounded search or direct endpoint setup."""
        if user_input is not None:
            return await self.async_step_manual(user_input)
        return self.async_show_menu(step_id="user", menu_options=["scan", "manual"])

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Search only after the user submits the requested scope."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                target = parse_target(user_input.get("target", ""))
            except ValueError:
                errors["target"] = "invalid_target"
            else:
                try:
                    devices = await async_discover(self.hass, target)
                except DiscoveryBusyError:
                    errors["base"] = "discovery_busy"
                except DiscoveryError:
                    errors["base"] = "discovery_failed"
                else:
                    configured = await async_configured_addresses(self.hass)
                    for host in configured:
                        self._async_abort_pending_discovery(host)
                    self._devices = {
                        device.host: device
                        for device in devices
                        if device.host not in configured
                    }
                    if self._devices:
                        self._async_schedule_discoveries()
                        return await self.async_step_select_device()
                    errors["base"] = "no_devices"
        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "target", default=(user_input or {}).get("target", "")
                    ): str
                }
            ),
            errors=errors,
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a candidate before asking for credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_HOST) == "manual":
                return await self.async_step_manual()
            if device := self._devices.get(user_input.get(CONF_HOST, "")):
                self._async_abort_entries_match({CONF_HOST: device.host})
                if device.host in await async_configured_addresses(self.hass):
                    self._async_abort_pending_discovery(device.host)
                    return self.async_abort(reason="already_configured")
                self._selected = device
                self.context["title_placeholders"] = {"name": device.label}
                return await self.async_step_manual()
            errors["base"] = "invalid_selection"
        choices = {host: device.label for host, device in self._devices.items()}
        options: list[SelectOptionDict] = [
            {"value": host, "label": label} for host, label in choices.items()
        ]
        options.append({"value": "manual", "label": "manual"})
        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="discovered_device",
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Ask the user to authenticate a candidate from a previous scan."""
        host = discovery_info.get(CONF_HOST)
        hostname = discovery_info.get("hostname")
        model = discovery_info.get("model")
        firmware = discovery_info.get("firmware")
        build_date = discovery_info.get("build_date")
        if (
            not isinstance(host, str)
            or not host
            or not isinstance(hostname, str)
            or not hostname
            or not isinstance(model, str)
            or not model
        ):
            return self.async_abort(reason="invalid_discovery")

        try:
            if str(IPv4Address(host)) != host or model not in SUPPORTED_MODELS:
                return self.async_abort(reason="invalid_discovery")
            device = DiscoveredDevice(
                host=host,
                hostname=hostname,
                model=model,
                firmware=firmware if isinstance(firmware, str) else None,
                build_date=build_date if isinstance(build_date, str) else None,
            )
        except TypeError, ValueError:
            return self.async_abort(reason="invalid_discovery")

        self._async_abort_entries_match({CONF_HOST: device.host})
        if device.host in await async_configured_addresses(self.hass):
            return self.async_abort(reason="already_configured")

        # This temporary key enables HA's Ignore action. It is never saved as
        # the config-entry identity; successful authentication replaces it with
        # the device ID reported by the documented REST API.
        pending_id = f"udp41794:{device.host}"
        await self.async_set_unique_id(pending_id)
        self._abort_if_unique_id_configured()
        self._selected = device
        self.context["title_placeholders"] = {"name": device.label}
        return await self.async_step_connect()

    def _async_schedule_discoveries(self) -> None:
        """Surface all scan results independently of the scanning dialog."""
        configured_hosts = {
            entry.data.get(CONF_HOST) for entry in self._async_current_entries()
        }
        for device in self._devices.values():
            if device.host in configured_hosts:
                continue
            discovery_flow.async_create_flow(
                self.hass,
                DOMAIN,
                context={
                    "source": config_entries.SOURCE_INTEGRATION_DISCOVERY,
                    "unique_id": f"udp41794:{device.host}",
                },
                data={
                    CONF_HOST: device.host,
                    "hostname": device.hostname,
                    "model": device.model,
                    "firmware": device.firmware,
                    "build_date": device.build_date,
                },
                discovery_key=DiscoveryKey(
                    domain=DOMAIN,
                    key=f"udp41794:{device.host}",
                    version=1,
                ),
            )

    def _async_abort_pending_discovery(self, host: str) -> None:
        """Retire this address's card only after successful authentication."""
        for flow in self.hass.config_entries.flow.async_progress_by_handler(DOMAIN):
            if (
                flow["flow_id"] != self.flow_id
                and flow["context"].get("source")
                == config_entries.SOURCE_INTEGRATION_DISCOVERY
                and flow["context"].get("unique_id") == f"udp41794:{host}"
            ):
                self.hass.config_entries.flow.async_abort(flow["flow_id"])

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Authenticate the selected candidate after explicit user confirmation."""
        return await self.async_step_manual(user_input)

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up one endpoint."""

        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = dict(user_input)
            if self._selected:
                user_input[CONF_HOST] = self._selected.host
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
                    existing = authenticated_entry(self.hass, snapshot.device)
                    await self.async_set_unique_id(
                        existing.unique_id if existing else snapshot.device.device_id
                    )
                    addresses = await async_ipv4_addresses(
                        self.hass, user_input[CONF_HOST]
                    )
                    if existing:
                        addresses |= await async_ipv4_addresses(
                            self.hass, existing.data[CONF_HOST]
                        )
                    for host in addresses:
                        self._async_abort_pending_discovery(host)
                    # An alternate interface is not a request to replace the
                    # working host, credentials or existing entity identities.
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=snapshot.device.name,
                        data=user_input,
                    )
        return self.async_show_form(
            step_id="connect" if self._selected else "manual",
            data_schema=_schema(
                user_input
                or ({CONF_HOST: self._selected.host} if self._selected else None),
                include_host=self._selected is None,
            ),
            description_placeholders={
                "device": self._selected.label if self._selected else "",
                "firmware": (self._selected.firmware or "—") if self._selected else "—",
                "build_date": (self._selected.build_date or "—")
                if self._selected
                else "—",
            },
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
