"""Explicit, opt-in reboot and primary stream commands."""

from typing import Literal, override

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from crestron_nvx import (
    NvxApiError,
    NvxAuthenticationError,
    NvxControlUnsupported,
    NvxDisplayCommand,
)

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
    entities: list[
        NvxRebootButton | NvxStreamButton | NvxClockSyncButton | NvxDisplayCommandButton
    ] = []
    entities.extend(
        NvxDisplayCommandButton(entry.runtime_data, command)
        for command in entry.runtime_data.capabilities.display_commands
    )
    if entry.runtime_data.capabilities.ntp_sync:
        entities.append(NvxClockSyncButton(entry.runtime_data))
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


class NvxDisplayCommandButton(CrestronNvxEntity, ButtonEntity):
    """Execute a configured display action, not a switch with inferred TV state."""

    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: CrestronNvxCoordinator, command: NvxDisplayCommand
    ) -> None:
        self._output_id = command.output_id
        self._action = command.action
        action_key = {
            "PowerOn": "power_on",
            "PowerOff": "power_off",
            "InputControl": "input_control",
        }[command.action]
        self._attr_translation_key = f"display_{action_key}"
        self._attr_translation_placeholders = {
            "output": f"Output {command.output_id[6:]}"
        }
        super().__init__(
            coordinator, f"{command.output_id.lower()}_display_{action_key}"
        )

    @property
    @override
    def available(self) -> bool:
        return super().available and any(
            command.output_id == self._output_id and command.action == self._action
            for command in self.coordinator.capabilities.display_commands
        )

    @override
    async def async_press(self) -> None:
        if not self.available:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="display_command_unavailable"
            )
        try:
            await self.coordinator.async_send_display_command(
                self._output_id, self._action
            )
        except NvxControlUnsupported as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="display_command_unavailable"
            ) from err
        except NvxAuthenticationError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="display_command_auth_failed"
            ) from err
        except NvxApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="display_command_failed"
            ) from err


class NvxClockSyncButton(CrestronNvxEntity, ButtonEntity):
    """Request NTP sync using existing settings; never infer clock accuracy."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "sync_clock"

    def __init__(self, coordinator: CrestronNvxCoordinator) -> None:
        super().__init__(coordinator, "sync_clock_control")

    @property
    @override
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.capabilities.ntp_sync
            and self.coordinator.clock_info.can_sync
        )

    @override
    async def async_press(self) -> None:
        if not self.available:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="clock_sync_unavailable"
            )
        try:
            await self.coordinator.async_sync_clock()
        except NvxControlUnsupported as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="clock_sync_unavailable"
            ) from err
        except NvxAuthenticationError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="clock_sync_auth_failed"
            ) from err
        except NvxApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="clock_sync_failed"
            ) from err


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
