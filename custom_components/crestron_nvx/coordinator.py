"""Data coordinator for Crestron DM NVX."""

import asyncio
import logging
from typing import Literal, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from crestron_nvx import (
    NvxApiError,
    NvxAuthenticationError,
    NvxClient,
    NvxConnectionError,
    NvxControlError,
    NvxPreviewInfo,
    NvxResponseError,
    NvxSnapshot,
)

from .const import DEFAULT_SCAN_INTERVAL, SIGNAL_ROUTING_UPDATED

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
            always_update=True,
        )
        self.client = client
        self.preview_info = NvxPreviewInfo()
        self._operation_lock = asyncio.Lock()

    async def async_set_leds_enabled(self, enabled: bool) -> None:
        """Serialize actions with polling and publish only observed state."""
        async with self._operation_lock:
            snapshot = await self.client.async_set_leds_enabled(
                enabled,
                expected_device_id=self.config_entry.unique_id
                or self.data.device.device_id,
            )
            self.async_set_updated_data(snapshot)

    @override
    async def _async_update_data(self) -> NvxSnapshot:
        """Fetch the current read-only endpoint snapshot."""
        async with self._operation_lock:
            return await self._async_read_data()

    async def async_set_video_source(self, source: str) -> None:
        """Serialize source selection with polling and publish verified state."""
        async with self._operation_lock:
            snapshot = await self.client.async_set_video_source(
                source,
                expected_device_id=self.config_entry.unique_id
                or self.data.device.device_id,
            )
            self.async_set_updated_data(snapshot)

    async def async_set_audio_source(self, source: str) -> None:
        """Serialize audio selection with polling and publish verified state."""
        async with self._operation_lock:
            snapshot = await self.client.async_set_audio_source(
                source,
                expected_device_id=self.config_entry.unique_id
                or self.data.device.device_id,
            )
            self.async_set_updated_data(snapshot)

    async def async_reboot(self) -> None:
        """Serialize an explicit reboot request with status polling."""
        async with self._operation_lock:
            await self.client.async_reboot(
                expected_device_id=self.config_entry.unique_id
                or self.data.device.device_id,
            )

    async def async_set_stream_running(
        self, direction: Literal["receive", "transmit"], running: bool
    ) -> None:
        """Serialize explicit stream commands and publish only verified telemetry."""
        async with self._operation_lock:
            snapshot = await self.client.async_set_stream_running(
                direction,
                running,
                expected_device_id=self.config_entry.unique_id
                or self.data.device.device_id,
            )
            self.async_set_updated_data(snapshot)

    @callback
    @override
    def async_update_listeners(self) -> None:
        """Refresh routing choices after telemetry or availability changes."""
        super().async_update_listeners()
        async_dispatcher_send(self.hass, SIGNAL_ROUTING_UPDATED)

    async def async_set_receive_stream_location(self, location: str) -> None:
        """Publish verified routing state, serialized against polling."""
        async with self._operation_lock:
            snapshot = await self.client.async_set_receive_stream_location(
                location,
                expected_device_id=self.config_entry.unique_id
                or self.data.device.device_id,
            )
            self.async_set_updated_data(snapshot)

    async def async_read_routing_source(self) -> NvxSnapshot:
        """Read a transmitter freshly without allowing concurrent control writes."""
        async with self._operation_lock:
            expected_id = self.config_entry.unique_id or self.data.device.device_id
            snapshot = await self.client.async_get_snapshot()
            if snapshot.device.device_id != expected_id:
                raise NvxControlError(
                    "Transmitter identity changed; no route command sent"
                )
            self.async_set_updated_data(snapshot)
            return snapshot

    async def _async_read_data(self) -> NvxSnapshot:
        """Read while holding the operation lock, including optional preview."""

        try:
            snapshot = await self.client.async_get_snapshot()
        except NvxAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except (NvxConnectionError, NvxResponseError) as err:
            raise UpdateFailed(f"Unable to update DM NVX endpoint: {err}") from err
        # Optional preview failure must never hide otherwise valid status data.
        try:
            self.preview_info = await self.client.async_get_preview_info()
        except NvxApiError:
            self.preview_info = NvxPreviewInfo()
        return snapshot
