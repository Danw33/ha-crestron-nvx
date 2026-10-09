"""Explicit, opt-in reboot and primary stream commands."""

from typing import Literal, override

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
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
    """Register commands only for observed capabilities on supported models."""
    entities: list[NvxRebootButton | NvxStreamButton] = []
    if entry.runtime_data.data.capabilities.reboot:
        entities.append(NvxRebootButton(entry.runtime_data))
    directions: tuple[Literal["receive", "transmit"], ...] = ("receive", "transmit")
    for direction in directions:
        if entry.runtime_data.data.primary_control_stream(direction) is not None:
            entities.extend(
                NvxStreamButton(entry.runtime_data, direction, running)
                for running in (True, False)
            )
    if entities:
        async_add_entities(entities)


class NvxRebootButton(CrestronNvxEntity, ButtonEntity):
    """A disabled diagnostic action that never runs during setup or polling."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "reboot"

    def __init__(self, coordinator: CrestronNvxCoordinator) -> None:
        super().__init__(coordinator, "reboot_control")

    @property
    @override
    def available(self) -> bool:
        return super().available and self.coordinator.data.capabilities.reboot

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


class NvxStreamButton(CrestronNvxEntity, ButtonEntity):
    """Operational actions, not a toggle inferred from transient command flags."""

    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: CrestronNvxCoordinator,
        direction: Literal["receive", "transmit"],
        running: bool,
    ) -> None:
        self._direction = direction
        self._running = running
        action = "start" if running else "stop"
        self._attr_translation_key = f"{direction}_stream_{action}"
        super().__init__(coordinator, f"{direction}_stream_0_{action}_control")

    @property
    @override
    def available(self) -> bool:
        stream = self.coordinator.data.primary_control_stream(self._direction)
        return super().available and stream is not None and stream.processing is False

    @override
    async def async_press(self) -> None:
        if not self.available:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="stream_unavailable"
            )
        try:
            await self.coordinator.async_set_stream_running(
                self._direction, self._running
            )
        except NvxControlUnsupported as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="stream_unsupported"
            ) from err
        except NvxAuthenticationError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="stream_auth_failed"
            ) from err
        except NvxApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="stream_failed"
            ) from err
