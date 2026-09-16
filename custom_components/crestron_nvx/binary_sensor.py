"""Binary sensor entities for Crestron DM NVX."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from crestron_nvx import NvxAvPort, NvxSnapshot, NvxStream

from .coordinator import CrestronNvxConfigEntry, CrestronNvxCoordinator
from .entity import CrestronNvxEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class NvxBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a DM NVX binary sensor."""

    value_fn: Callable[[NvxSnapshot], bool | None]


BINARY_SENSORS: tuple[NvxBinarySensorDescription, ...] = (
    NvxBinarySensorDescription(
        key="device_ready",
        translation_key="device_ready",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.device_ready,
    ),
    NvxBinarySensorDescription(
        key="auto_initiation_mode",
        translation_key="auto_initiation_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.auto_initiation_mode,
    ),
    NvxBinarySensorDescription(
        key="auto_input_routing_enabled",
        translation_key="auto_input_routing_enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.auto_input_routing_enabled,
    ),
    NvxBinarySensorDescription(
        key="front_panel_lockout_enabled",
        translation_key="front_panel_lockout_enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.front_panel_lockout_enabled,
    ),
    NvxBinarySensorDescription(
        key="leds_enabled",
        translation_key="leds_enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.leds_enabled,
    ),
    NvxBinarySensorDescription(
        key="show_setup_information_on_osd",
        translation_key="show_setup_information_on_osd",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.show_setup_information_on_osd,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CrestronNvxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors for one endpoint."""

    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        NvxBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.value_fn(coordinator.data) is not None
    ]
    for port in coordinator.data.av_ports:
        if port.direction == "input":
            entities.append(NvxAvPortBinarySensor(coordinator, port, "sync"))
        else:
            entities.extend(
                (
                    NvxAvPortBinarySensor(coordinator, port, "connected"),
                    NvxAvPortBinarySensor(coordinator, port, "transmitting"),
                )
            )
    for streams in (
        coordinator.data.receive_streams,
        coordinator.data.transmit_streams,
    ):
        entities.extend(
            NvxStreamCodecReadyBinarySensor(coordinator, stream, index)
            for index, stream in enumerate(streams, start=1)
        )
    async_add_entities(entities)


class NvxBinarySensor(CrestronNvxEntity, BinarySensorEntity):
    """Represent one endpoint boolean."""

    entity_description: NvxBinarySensorDescription

    def __init__(
        self,
        coordinator: CrestronNvxCoordinator,
        description: NvxBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""

        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    @override
    def is_on(self) -> bool | None:
        """Return endpoint readiness."""

        return self.entity_description.value_fn(self.coordinator.data)


class NvxDeviceReadyBinarySensor(NvxBinarySensor):
    """Backward-compatible named class for the primary readiness entity."""

    def __init__(self, coordinator: CrestronNvxCoordinator) -> None:
        """Initialize the readiness entity."""

        super().__init__(coordinator, BINARY_SENSORS[0])


class NvxAvPortBinarySensor(CrestronNvxEntity, BinarySensorEntity):
    """Represent input sync or output connection/transmission state."""

    def __init__(
        self,
        coordinator: CrestronNvxCoordinator,
        port: NvxAvPort,
        metric: str,
    ) -> None:
        """Initialize an A/V port binary sensor."""

        super().__init__(coordinator, f"{port.direction}_{port.port_id}_{metric}")
        self._port_id = port.port_id
        self._direction = port.direction
        self._metric = metric
        self._attr_translation_key = f"{port.direction}_{metric}"
        self._attr_translation_placeholders = {"port_name": port.name}

    def _port(self) -> NvxAvPort | None:
        """Return the latest matching port."""

        return next(
            (
                port
                for port in self.coordinator.data.av_ports
                if port.port_id == self._port_id and port.direction == self._direction
            ),
            None,
        )

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the selected port state."""

        if (port := self._port()) is None:
            return None
        if self._metric == "sync":
            return port.sync_detected
        if self._metric == "connected":
            return port.sink_connected
        return port.transmitting

    @property
    @override
    def available(self) -> bool:
        """Mark a removed model-specific port unavailable."""

        return super().available and self._port() is not None


class NvxStreamCodecReadyBinarySensor(CrestronNvxEntity, BinarySensorEntity):
    """Represent codec readiness for one stream slot."""

    def __init__(
        self, coordinator: CrestronNvxCoordinator, stream: NvxStream, number: int
    ) -> None:
        """Initialize a stream readiness binary sensor."""

        super().__init__(
            coordinator, f"{stream.direction}_{stream.stream_id}_codec_ready"
        )
        self._stream_id = stream.stream_id
        self._direction = stream.direction
        self._attr_translation_key = f"{stream.direction}_stream_codec_ready"
        self._attr_translation_placeholders = {"stream_number": str(number)}

    def _stream(self) -> NvxStream | None:
        """Return the latest matching stream."""

        streams = (
            self.coordinator.data.receive_streams
            if self._direction == "receive"
            else self.coordinator.data.transmit_streams
        )
        return next(
            (stream for stream in streams if stream.stream_id == self._stream_id),
            None,
        )

    @property
    @override
    def is_on(self) -> bool | None:
        """Return codec readiness."""

        return stream.codec_ready if (stream := self._stream()) else None

    @property
    @override
    def available(self) -> bool:
        """Mark a removed stream slot unavailable."""

        return super().available and self._stream() is not None
