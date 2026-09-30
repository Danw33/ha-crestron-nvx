"""Explicit configured video-source selection, separate from active telemetry."""

from typing import override

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from crestron_nvx import NvxApiError, NvxAuthenticationError, NvxControlUnsupported

from .const import DOMAIN
from .coordinator import CrestronNvxConfigEntry, CrestronNvxCoordinator
from .entity import CrestronNvxEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CrestronNvxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Register only for recognized sources on supported hardware."""
    if entry.runtime_data.data.video_source_options:
        async_add_entities([NvxVideoSourceSelect(entry.runtime_data)])


class NvxVideoSourceSelect(CrestronNvxEntity, SelectEntity):
    """A disabled-by-default control; enabling it never writes."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "video_source"

    def __init__(self, coordinator: CrestronNvxCoordinator) -> None:
        super().__init__(coordinator, "video_source_control")

    @property
    @override
    def options(self) -> list[str]:
        return list(self.coordinator.data.video_source_options)

    @property
    @override
    def current_option(self) -> str | None:
        source = self.coordinator.data.video_source
        return source if source in self.options else None

    @property
    @override
    def available(self) -> bool:
        return super().available and bool(self.options)

    @override
    async def async_select_option(self, option: str) -> None:
        if not self.available or option not in self.options:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="video_source_unavailable"
            )
        try:
            await self.coordinator.async_set_video_source(option)
        except NvxControlUnsupported as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="video_source_unsupported"
            ) from err
        except NvxAuthenticationError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="video_source_auth_failed"
            ) from err
        except NvxApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="video_source_failed"
            ) from err
