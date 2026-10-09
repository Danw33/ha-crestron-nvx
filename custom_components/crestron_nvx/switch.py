"""Explicit, opt-in device LED control; no writes during setup or polling."""

from typing import Any, override

from homeassistant.components.switch import SwitchEntity
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
    """Expose the switch only when a readable boolean capability is present."""
    if entry.runtime_data.data.capabilities.leds_control:
        async_add_entities([NvxLedSwitch(entry.runtime_data)])


class NvxLedSwitch(CrestronNvxEntity, SwitchEntity):
    """Read observed LED state and send only explicit on/off commands."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "device_leds"

    def __init__(self, coordinator: CrestronNvxCoordinator) -> None:
        super().__init__(coordinator, "leds_control")

    @property
    @override
    def is_on(self) -> bool | None:
        return self.coordinator.data.leds_enabled

    @property
    @override
    def available(self) -> bool:
        return super().available and self.coordinator.data.capabilities.leds_control

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, enabled: bool) -> None:
        if not self.available:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="leds_unavailable"
            )
        try:
            await self.coordinator.async_set_leds_enabled(enabled)
        except NvxControlUnsupported as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="leds_unsupported"
            ) from err
        except NvxAuthenticationError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="leds_auth_failed"
            ) from err
        except NvxApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="leds_failed"
            ) from err
