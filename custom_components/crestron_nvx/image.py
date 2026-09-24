"""On-demand local preview images for capable DM NVX endpoints."""

import asyncio
from time import monotonic

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from crestron_nvx import NvxApiError

from .coordinator import CrestronNvxConfigEntry, CrestronNvxCoordinator
from .entity import CrestronNvxEntity

PARALLEL_UPDATES = 0
_CACHE_SECONDS = 30


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CrestronNvxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the entity when optional capability first becomes known."""
    coordinator = entry.runtime_data
    added = False

    @callback
    def discover() -> None:
        nonlocal added
        if not added and coordinator.preview_info.supported:
            added = True
            async_add_entities([NvxPreviewImageEntity(hass, coordinator)])

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class NvxPreviewImageEntity(CrestronNvxEntity, ImageEntity):
    """Proxy bounded authenticated JPEGs without exposing device URLs."""

    _attr_translation_key = "preview"
    _attr_content_type = "image/jpeg"

    def __init__(
        self, hass: HomeAssistant, coordinator: CrestronNvxCoordinator
    ) -> None:
        ImageEntity.__init__(self, hass)
        CrestronNvxEntity.__init__(self, coordinator, "preview")
        self._frame: bytes | None = None
        self._next_fetch = 0.0
        self._lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        """A supported endpoint may have preview output disabled or no signal."""
        return super().available and self.coordinator.preview_info.path is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        if not self.available:
            self._frame = None
            self._next_fetch = 0
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Fetch only on demand and coalesce repeated or simultaneous requests."""
        async with self._lock:
            if not self.available:
                self._frame = None
                return None
            if monotonic() < self._next_fetch:
                return self._frame
            try:
                image = await self.coordinator.client.async_get_preview()
            except NvxApiError:
                self._frame = None
            else:
                self._frame = image.content
                self._attr_image_last_updated = dt_util.utcnow()
                if self.entity_id:
                    self.async_write_ha_state()
            self._next_fetch = monotonic() + _CACHE_SECONDS
            return self._frame

    async def async_will_remove_from_hass(self) -> None:
        self._frame = None
        await super().async_will_remove_from_hass()
