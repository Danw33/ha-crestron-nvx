"""Base entity for Crestron DM NVX."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CrestronNvxCoordinator


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
