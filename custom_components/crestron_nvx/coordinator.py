"""Data coordinator for Crestron DM NVX."""

import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from crestron_nvx import (
    NvxAuthenticationError,
    NvxClient,
    NvxConnectionError,
    NvxResponseError,
    NvxSnapshot,
)

from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type CrestronNvxConfigEntry = ConfigEntry["CrestronNvxCoordinator"]


class CrestronNvxCoordinator(DataUpdateCoordinator[NvxSnapshot]):
    """Coordinate efficient reads from one DM NVX endpoint."""

    config_entry: CrestronNvxConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CrestronNvxConfigEntry,
        client: NvxClient,
    ) -> None:
        """Initialize the coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=DEFAULT_SCAN_INTERVAL,
            always_update=False,
        )
        self.client = client

    @override
    async def _async_update_data(self) -> NvxSnapshot:
        """Fetch the current read-only endpoint snapshot."""

        try:
            return await self.client.async_get_snapshot()
        except NvxAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except (NvxConnectionError, NvxResponseError) as err:
            raise UpdateFailed(f"Unable to update DM NVX endpoint: {err}") from err
