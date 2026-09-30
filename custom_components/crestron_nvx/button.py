"""Explicit diagnostic reboot button."""

from typing import override

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from crestron_nvx import NvxApiError, NvxAuthenticationError, NvxControlUnsupported

from .const import DOMAIN, SUPPORTED_MODELS
from .coordinator import CrestronNvxConfigEntry, CrestronNvxCoordinator
from .entity import CrestronNvxEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CrestronNvxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Register reboot only for supported device models."""
    if entry.runtime_data.data.device.model.upper() in SUPPORTED_MODELS:
        async_add_entities([NvxRebootButton(entry.runtime_data)])


class NvxRebootButton(CrestronNvxEntity, ButtonEntity):
    """A disabled diagnostic action that never runs during setup or polling."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "reboot"

    def __init__(self, coordinator: CrestronNvxCoordinator) -> None:
        super().__init__(coordinator, "reboot_control")

    @override
    async def async_press(self) -> None:
        if not self.available:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="reboot_unavailable"
            )
        try:
            await self.coordinator.async_reboot()
        except NvxControlUnsupported as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="reboot_unsupported"
            ) from err
        except NvxAuthenticationError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="reboot_auth_failed"
            ) from err
        except NvxApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="reboot_failed"
            ) from err
