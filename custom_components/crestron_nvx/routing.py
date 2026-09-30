"""Name-based routing among authenticated, configured NVX endpoints."""

from typing import override

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from crestron_nvx import (
    NvxApiError,
    NvxAuthenticationError,
    NvxSnapshot,
    is_valid_stream_location,
)

from .const import DOMAIN, SIGNAL_ROUTING_UPDATED, SUPPORTED_MODELS
from .coordinator import CrestronNvxCoordinator
from .entity import CrestronNvxEntity


def primary_transmit_location(snapshot: NvxSnapshot) -> str | None:
    """Never synthesize URLs or treat a receiver's transmit telemetry as a source."""
    if (
        snapshot.device_mode != "Transmitter"
        or snapshot.device.model.upper() not in SUPPORTED_MODELS
    ):
        return None
    for stream in snapshot.transmit_streams:
        if (
            stream.slot_index == 0
            and stream.processing is False
            and is_valid_stream_location(stream.stream_location)
        ):
            return stream.stream_location
    return None


class NvxReceiverStreamSelect(CrestronNvxEntity, SelectEntity):
    """Explicit primary stream URL selection; no implicit start or source change."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "receiver_stream"

    def __init__(self, coordinator: CrestronNvxCoordinator) -> None:
        super().__init__(coordinator, "receiver_stream_control")

    def _sources(self) -> dict[str, CrestronNvxCoordinator]:
        result: dict[str, CrestronNvxCoordinator] = {}
        registry = dr.async_get(self.coordinator.hass)
        for coord in self.coordinator.hass.data.get(DOMAIN, {}).values():
            if (
                coord is self.coordinator
                or not coord.last_update_success
                or coord.data.device.device_id == self.coordinator.data.device.device_id
                or primary_transmit_location(coord.data) is None
            ):
                continue
            device = registry.async_get_device(
                identifiers={(DOMAIN, coord.data.device.device_id)}
            )
            name = (device.name_by_user if device else None) or coord.config_entry.title
            # The full device identity makes duplicate user-assigned names unambiguous.
            label = f"{name} ({coord.data.device.device_id})"
            result[label] = coord
        return result

    @property
    @override
    def options(self) -> list[str]:
        return sorted(self._sources())

    @property
    @override
    def current_option(self) -> str | None:
        stream = self.coordinator.data.primary_receive_stream
        if stream is None or not stream.stream_location:
            return None
        matches = [
            label
            for label, coord in self._sources().items()
            if primary_transmit_location(coord.data) == stream.stream_location
        ]
        return matches[0] if len(matches) == 1 else None

    @property
    @override
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data.primary_receive_stream is not None
            and bool(self.options)
        )

    @override
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_ROUTING_UPDATED, self._routing_updated
            )
        )

    @callback
    def _routing_updated(self) -> None:
        self.async_write_ha_state()

    @override
    async def async_select_option(self, option: str) -> None:
        source = self._sources().get(option)
        if not self.available or source is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="routing_unavailable"
            )
        expected_id = source.config_entry.unique_id or source.data.device.device_id
        try:
            fresh = await source.async_read_routing_source()
        except NvxAuthenticationError as err:
            source.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="routing_source_failed"
            ) from err
        except NvxApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="routing_source_failed"
            ) from err
        location = primary_transmit_location(fresh)
        if (
            fresh.device.device_id != expected_id
            or location is None
            or source not in self._sources().values()
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="routing_unavailable"
            )
        try:
            await self.coordinator.async_set_receive_stream_location(location)
        except NvxAuthenticationError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="routing_failed"
            ) from err
        except NvxApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="routing_failed"
            ) from err
