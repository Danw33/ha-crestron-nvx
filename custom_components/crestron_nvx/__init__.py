"""Crestron DM NVX integration."""

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from crestron_nvx import NvxClient

from .const import CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL, PLATFORMS
from .coordinator import CrestronNvxConfigEntry, CrestronNvxCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: CrestronNvxConfigEntry) -> bool:
    """Set up Crestron DM NVX from a config entry."""

    client = NvxClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
    )
    coordinator = CrestronNvxCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: CrestronNvxConfigEntry
) -> bool:
    """Unload a Crestron DM NVX config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
