"""Base entity for Crestron DM NVX."""

import re

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from crestron_nvx import NvxAvPort

from .const import DOMAIN
from .coordinator import CrestronNvxCoordinator


def av_port_display_name(port: NvxAvPort) -> str:
    """Normalize built-in labels without changing raw names or port identity."""
    if (
        match := re.fullmatch(r"(input|output)\s+([1-9][0-9]{0,2})", port.name, re.I)
    ) and match[1].lower() == port.direction:
        return f"{port.direction.capitalize()} {match[2]}"
    # Firmware can omit the HDMI label, leaving the zero-based group name.
    # Convert it only when the stable topology confirms the same group slot.
    if (
        (match := re.fullmatch(r"(input|output)([0-9]{1,3})", port.name))
        and match[1] == port.direction
        and port.port_id.startswith(f"{port.direction}_slot{match[2]}_")
    ):
        return f"{port.direction.capitalize()} {int(match[2]) + 1}"
    return port.name


class CrestronNvxEntity(CoordinatorEntity[CrestronNvxCoordinator]):
    """Base for entities belonging to one physical endpoint."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CrestronNvxCoordinator, key: str) -> None:
        """Initialize the entity with stable registry identifiers."""

        super().__init__(coordinator)
        device = coordinator.data.device
        self._attr_unique_id = f"{device.device_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)},
            name=device.name,
            manufacturer=device.manufacturer,
            model=device.model,
            serial_number=device.serial_number,
            sw_version=device.firmware_version,
            configuration_url=coordinator.client.configuration_url,
        )
